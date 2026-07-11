from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
import tempfile
import threading
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any
from urllib.parse import urlparse

import discord
import yt_dlp
from discord.ext import commands


log = logging.getLogger(__name__)

IDLE_TIMEOUT_SECONDS = 180
VOICE_CONNECT_TIMEOUT_SECONDS = 30.0

YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": False,
    "socket_timeout": 20,
    "retries": 3,
    "fragment_retries": 3,
    "extractor_retries": 3,
}


class TrackLookupError(Exception):
    """Raised when yt-dlp cannot find a playable track."""


class VoiceChannelMismatch(Exception):
    """Raised when a requester is not in the bot's active voice channel."""


class PlayCancelled(Exception):
    """Raised when stop/leave/game takeover invalidates a pending /play."""


class LoopMode(Enum):
    OFF = 0
    ONE = 1
    QUEUE = 2


class EndReason(Enum):
    NATURAL = auto()
    ERROR = auto()
    SKIP = auto()
    STOP = auto()
    LEAVE = auto()


@dataclass(frozen=True, slots=True)
class Track:
    title: str
    webpage_url: str
    duration: int | None
    text_channel_id: int


def _set_event() -> asyncio.Event:
    event = asyncio.Event()
    event.set()
    return event


@dataclass(slots=True)
class GuildPlayer:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    voice_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    request_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    queue: deque[Track] = field(default_factory=deque)
    wake: asyncio.Event = field(default_factory=asyncio.Event)
    playback_idle: asyncio.Event = field(default_factory=_set_event)
    current: Track | None = None
    control: asyncio.Future[EndReason] | None = None
    worker_task: asyncio.Task[None] | None = None
    idle_task: asyncio.Task[None] | None = None
    loop_mode: LoopMode = LoopMode.OFF
    command_epoch: int = 0
    idle_generation: int = 0
    pending_searches: int = 0
    external_audio: bool = False


class _YTDLLogger:
    def debug(self, message: str) -> None:
        if message.startswith("[debug]"):
            log.debug("yt-dlp: %s", message)

    def info(self, message: str) -> None:
        log.info("yt-dlp: %s", message)

    def warning(self, message: str) -> None:
        log.warning("yt-dlp: %s", message)

    def error(self, message: str) -> None:
        log.error("yt-dlp: %s", message)


class YTDLPipeAudio(discord.AudioSource):
    """Stream through yt-dlp's downloader, then transcode to Opus with FFmpeg.

    Letting yt-dlp perform the HTTP download avoids handing FFmpeg a temporary
    Google Video URL that may require ranged requests, a PO token, or refreshed
    request data. The subprocess is recreated for every playback and loop.
    """

    def __init__(self, track: Track):
        self.track = track
        self.failed = False
        self.error_summary = ""
        self._cleanup_lock = threading.Lock()
        self._cleaned = False
        self._terminated_early = False
        self._current_error: Exception | None = None
        self.cleanup_done = threading.Event()
        self._audio: discord.FFmpegOpusAudio | None = None
        self._ytdl_stderr = tempfile.TemporaryFile()
        self._ffmpeg_stderr = tempfile.TemporaryFile()

        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        command = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--format",
            "bestaudio/best",
            "--no-playlist",
            "--no-progress",
            "--no-part",
            "--retries",
            "3",
            "--fragment-retries",
            "3",
            "--extractor-retries",
            "3",
            "--socket-timeout",
            "20",
            "--output",
            "-",
            track.webpage_url,
        ]

        try:
            self._ytdl_process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=self._ytdl_stderr,
                creationflags=creation_flags,
            )
            if self._ytdl_process.stdout is None:
                raise RuntimeError("yt-dlp did not create an audio pipe")

            # codec=None makes FFmpeg encode to Opus. Discord can send this
            # directly, so the Python process does not need a platform-specific
            # libopus path.
            self._audio = discord.FFmpegOpusAudio(
                self._ytdl_process.stdout,
                pipe=True,
                codec=None,
                bitrate=128,
                stderr=self._ffmpeg_stderr,
                options="-vn",
            )
        except Exception:
            self._terminate_ytdl()
            self._close_logs()
            raise

    def read(self) -> bytes:
        if self._audio is None:
            return b""
        data = self._audio.read()
        if not data:
            inner_error = getattr(self._audio, "_current_error", None)
            if inner_error is not None:
                # discord.py inspects the outer source for _current_error.
                self._current_error = inner_error
        return data

    def is_opus(self) -> bool:
        return True

    @staticmethod
    def _read_log(handle: Any) -> str:
        try:
            handle.flush()
            handle.seek(0)
            data = handle.read()
            if isinstance(data, bytes):
                return data.decode("utf-8", errors="replace")[-4000:].strip()
            return str(data)[-4000:].strip()
        except Exception:
            return ""

    def _terminate_ytdl(self) -> int | None:
        process = getattr(self, "_ytdl_process", None)
        if process is None:
            return None

        try:
            running = process.poll() is None
        except OSError:
            running = False

        if running:
            try:
                process.wait(timeout=0.25)
            except (subprocess.TimeoutExpired, OSError):
                self._terminated_early = True
                try:
                    process.terminate()
                except OSError:
                    pass
                try:
                    process.wait(timeout=1.0)
                except (subprocess.TimeoutExpired, OSError):
                    try:
                        process.kill()
                    except OSError:
                        pass
                    try:
                        process.wait(timeout=1.0)
                    except (subprocess.TimeoutExpired, OSError):
                        log.warning("yt-dlp process %s did not terminate cleanly", process.pid)

        if process.stdout is not None:
            try:
                process.stdout.close()
            except Exception:
                pass
        return process.poll()

    def _close_logs(self) -> None:
        for handle in (self._ytdl_stderr, self._ffmpeg_stderr):
            try:
                handle.close()
            except Exception:
                pass

    def cleanup(self) -> None:
        with self._cleanup_lock:
            if self._cleaned:
                return
            self._cleaned = True

        try:
            ytdl_rc = self._terminate_ytdl()
            ffmpeg_rc = None
            cleanup_failed = False

            if self._audio is not None:
                process = getattr(self._audio, "_process", None)
                if process is not None:
                    ffmpeg_rc = process.poll()
                try:
                    self._audio.cleanup()
                except Exception:
                    cleanup_failed = True
                    log.exception("FFmpeg cleanup failed for %r", self.track.title)
                if process is not None:
                    ffmpeg_rc = process.poll()
                inner_error = getattr(self._audio, "_current_error", None)
                if inner_error is not None:
                    self._current_error = inner_error

            ytdl_log = self._read_log(self._ytdl_stderr)
            ffmpeg_log = self._read_log(self._ffmpeg_stderr)
            logged_failure = (
                "ERROR:" in ytdl_log
                or "Error opening" in ffmpeg_log
                or "Conversion failed" in ffmpeg_log
            )

            self.failed = (
                cleanup_failed
                or self._current_error is not None
                or logged_failure
                or (
                    not self._terminated_early
                    and (
                        ytdl_rc not in (None, 0)
                        or ffmpeg_rc not in (None, 0)
                    )
                )
            )
            if self.failed:
                self.error_summary = "\n".join(
                    part for part in (ytdl_log, ffmpeg_log) if part
                )[-4000:]
                log.warning(
                    "Audio pipeline failed for %r (yt-dlp=%s, ffmpeg=%s): %s",
                    self.track.title,
                    ytdl_rc,
                    ffmpeg_rc,
                    self.error_summary or "no stderr output",
                )
        finally:
            self._close_logs()
            self.cleanup_done.set()


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players: dict[int, GuildPlayer] = {}

    async def cog_unload(self) -> None:
        tasks: list[asyncio.Task[Any]] = []
        disconnects = []
        for guild_id, player in self.players.items():
            player.command_epoch += 1
            if player.control and not player.control.done():
                player.control.set_result(EndReason.STOP)
            if player.worker_task:
                player.worker_task.cancel()
                tasks.append(player.worker_task)
            if player.idle_task:
                player.idle_task.cancel()
                tasks.append(player.idle_task)

            guild = self.bot.get_guild(guild_id)
            voice_client = guild.voice_client if guild else None
            if (
                not player.external_audio
                and player.current is not None
                and voice_client
                and (voice_client.is_playing() or voice_client.is_paused())
            ):
                voice_client.stop()
            if (
                not player.external_audio
                and voice_client
                and voice_client.is_connected()
            ):
                disconnects.append(voice_client.disconnect())

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if disconnects:
            await asyncio.gather(*disconnects, return_exceptions=True)

    def _get_player(self, guild_id: int) -> GuildPlayer:
        player = self.players.get(guild_id)
        if player is None:
            player = GuildPlayer()
            self.players[guild_id] = player

        if player.worker_task is None or player.worker_task.done():
            player.worker_task = asyncio.create_task(
                self._player_worker(guild_id),
                name=f"music-player-{guild_id}",
            )
        return player

    @staticmethod
    def _is_url(query: str) -> bool:
        parsed = urlparse(query)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _extract_track_sync(query: str, text_channel_id: int) -> Track:
        search_query = query if Music._is_url(query) else f"ytsearch1:{query}"
        options = dict(YDL_OPTIONS)
        options["logger"] = _YTDLLogger()

        with yt_dlp.YoutubeDL(options) as ydl:
            data = ydl.extract_info(search_query, download=False)

        info = data
        if data and "entries" in data:
            info = next((entry for entry in data["entries"] if entry), None)

        if not info:
            raise TrackLookupError("找不到符合的歌曲")

        webpage_url = (
            info.get("webpage_url")
            or info.get("original_url")
            or (query if Music._is_url(query) else None)
        )
        if not webpage_url:
            raise TrackLookupError("搜尋結果沒有可重新解析的網址")

        duration = info.get("duration")
        if not isinstance(duration, int):
            duration = int(duration) if isinstance(duration, float) else None

        return Track(
            title=info.get("title") or "未知歌曲",
            webpage_url=webpage_url,
            duration=duration,
            text_channel_id=text_channel_id,
        )

    def _game_is_active(self, ctx: commands.Context) -> bool:
        werewolf = self.bot.get_cog("Werewolf")
        if not werewolf:
            return False
        game = werewolf.get_game(ctx)
        return bool(game and game.phase not in {"waiting", "ended"})

    @staticmethod
    def _settle_audio(
        future: asyncio.Future[Exception | None], error: Exception | None
    ) -> None:
        if not future.done():
            future.set_result(error)

    @staticmethod
    async def _wait_for_source_cleanup(
        source: YTDLPipeAudio,
        guild_id: int,
    ) -> None:
        cleaned = await asyncio.to_thread(source.cleanup_done.wait, 3.0)
        if cleaned:
            return
        log.warning("Audio cleanup timed out in guild %s; forcing cleanup", guild_id)
        await asyncio.to_thread(source.cleanup)

    def _cancel_idle_locked(self, player: GuildPlayer) -> None:
        player.idle_generation += 1
        task = player.idle_task
        player.idle_task = None
        if task and task is not asyncio.current_task() and not task.done():
            task.cancel()

    def _arm_idle_locked(
        self,
        guild: discord.Guild,
        player: GuildPlayer,
    ) -> None:
        self._cancel_idle_locked(player)
        voice_client = guild.voice_client
        if (
            player.external_audio
            or player.current is not None
            or player.queue
            or player.pending_searches
            or not voice_client
            or not voice_client.is_connected()
            or voice_client.is_playing()
            or voice_client.is_paused()
        ):
            return

        generation = player.idle_generation
        player.idle_task = asyncio.create_task(
            self._idle_disconnect(guild.id, voice_client, generation),
            name=f"music-idle-{guild.id}",
        )

    async def _idle_disconnect(
        self,
        guild_id: int,
        voice_client: discord.VoiceClient,
        generation: int,
    ) -> None:
        try:
            await asyncio.sleep(IDLE_TIMEOUT_SECONDS)
        except asyncio.CancelledError:
            return

        player = self.players.get(guild_id)
        guild = self.bot.get_guild(guild_id)
        if not player or not guild:
            return

        async with player.voice_lock:
            async with player.lock:
                if (
                    generation != player.idle_generation
                    or player.idle_task is not asyncio.current_task()
                    or guild.voice_client is not voice_client
                    or player.external_audio
                    or player.current is not None
                    or player.queue
                    or player.pending_searches
                    or voice_client.is_playing()
                    or voice_client.is_paused()
                ):
                    return
                # Clear before disconnecting so a new /play cannot cancel this
                # task halfway through the voice cleanup.
                player.idle_task = None

            try:
                await asyncio.shield(voice_client.disconnect())
                log.info("Disconnected idle voice client in guild %s", guild_id)
            except Exception:
                log.exception("Failed to disconnect idle voice client in guild %s", guild_id)
                try:
                    await asyncio.shield(voice_client.disconnect(force=True))
                except Exception:
                    log.exception(
                        "Forced idle disconnect also failed in guild %s", guild_id
                    )
                    async with player.lock:
                        self._arm_idle_locked(guild, player)

    async def _ensure_voice(
        self,
        guild: discord.Guild,
        voice_channel: discord.abc.Connectable,
        *,
        allow_move: bool,
        expected_epoch: int | None = None,
    ) -> discord.VoiceClient:
        player = self._get_player(guild.id)
        async with player.voice_lock:
            if expected_epoch is not None:
                async with player.lock:
                    if (
                        expected_epoch != player.command_epoch
                        or player.external_audio
                    ):
                        raise PlayCancelled

            voice_client = guild.voice_client
            created_voice_client = False

            # A VoiceClient is cached before its handshake completes. Wait for
            # that handshake instead of force-disconnecting it immediately.
            if voice_client is not None and not voice_client.is_connected():
                wait_until_connected = getattr(
                    voice_client, "wait_until_connected", None
                )
                if callable(wait_until_connected):
                    connected = await asyncio.to_thread(
                        wait_until_connected,
                        VOICE_CONNECT_TIMEOUT_SECONDS,
                    )
                else:
                    connected = False
                    for _ in range(int(VOICE_CONNECT_TIMEOUT_SECONDS * 10)):
                        await asyncio.sleep(0.1)
                        current = guild.voice_client
                        if current is None:
                            voice_client = None
                            break
                        voice_client = current
                        if voice_client.is_connected():
                            connected = True
                            break

                if voice_client is not None and not connected:
                    log.warning("Cleaning up a stale voice handshake in guild %s", guild.id)
                    try:
                        await voice_client.disconnect(force=True)
                    except Exception:
                        log.exception("Failed to clean up stale voice client")
                    voice_client = None

            if voice_client is None:
                try:
                    voice_client = await voice_channel.connect(
                        timeout=VOICE_CONNECT_TIMEOUT_SECONDS,
                        reconnect=True,
                        self_deaf=True,
                    )
                    created_voice_client = True
                except Exception:
                    stale = guild.voice_client
                    if stale and not stale.is_connected():
                        try:
                            await stale.disconnect(force=True)
                        except Exception:
                            log.exception("Failed to clean up failed voice connection")
                    raise
            elif voice_client.channel.id != voice_channel.id:
                if not allow_move:
                    raise VoiceChannelMismatch(
                        f"請先加入機器人目前所在的語音頻道：{voice_client.channel.name}"
                    )
                await voice_client.move_to(voice_channel)

            if expected_epoch is not None:
                async with player.lock:
                    cancelled = (
                        expected_epoch != player.command_epoch
                        or player.external_audio
                    )
                if cancelled:
                    if created_voice_client and voice_client.is_connected():
                        await voice_client.disconnect()
                    raise PlayCancelled

            return voice_client

    async def _play_track(
        self,
        guild: discord.Guild,
        player: GuildPlayer,
        track: Track,
        control: asyncio.Future[EndReason],
    ) -> EndReason:
        if control.done():
            return control.result()

        loop = asyncio.get_running_loop()
        audio_done: asyncio.Future[Exception | None] = loop.create_future()
        source: YTDLPipeAudio | None = None

        try:
            async with player.voice_lock:
                if control.done():
                    return control.result()

                voice_client = guild.voice_client
                if not voice_client or not voice_client.is_connected():
                    return EndReason.ERROR
                if voice_client.is_playing() or voice_client.is_paused():
                    log.error("Voice client was already busy before playing %r", track.title)
                    return EndReason.ERROR

                source = await asyncio.to_thread(YTDLPipeAudio, track)
                cancel_reason = None
                async with player.lock:
                    if (
                        player.control is not control
                        or control.done()
                        or player.external_audio
                    ):
                        cancel_reason = (
                            control.result() if control.done() else EndReason.STOP
                        )
                if cancel_reason is not None:
                    await asyncio.to_thread(source.cleanup)
                    return cancel_reason
                voice_client.play(
                    source,
                    after=lambda error: loop.call_soon_threadsafe(
                        self._settle_audio, audio_done, error
                    ),
                )

            # A slow Discord message must never delay stop/leave/game takeover.
            asyncio.create_task(
                self._notify(track.text_channel_id, f"▶️ 正在播放：**{track.title}**"),
                name=f"music-notify-{guild.id}",
            )

            await asyncio.wait(
                {audio_done, control},
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Explicit user controls win if stop() and the audio callback arrive
            # during the same event-loop turn.
            if control.done():
                reason = control.result()
                voice_client = guild.voice_client
                if voice_client and getattr(voice_client, "source", None) is source:
                    voice_client.stop()
                if not audio_done.done():
                    try:
                        await asyncio.wait_for(asyncio.shield(audio_done), timeout=2.0)
                    except asyncio.TimeoutError:
                        log.warning("Audio callback timed out after %s in guild %s", reason, guild.id)
                if source:
                    await self._wait_for_source_cleanup(source, guild.id)
                return reason

            error = audio_done.result()
            # AudioPlayer calls source.cleanup() immediately after the callback;
            # wait for its explicit signal rather than racing a fixed sleep.
            if source:
                await self._wait_for_source_cleanup(source, guild.id)
            if error is not None or (source and source.failed):
                if error:
                    log.warning("Discord audio player failed in guild %s: %s", guild.id, error)
                return EndReason.ERROR
            return EndReason.NATURAL
        except asyncio.CancelledError:
            voice_client = guild.voice_client
            if voice_client and getattr(voice_client, "source", None) is source:
                voice_client.stop()
            if source:
                cleanup_task = asyncio.create_task(asyncio.to_thread(source.cleanup))
                try:
                    await asyncio.shield(cleanup_task)
                except asyncio.CancelledError:
                    pass
            raise
        except Exception:
            log.exception("Could not play %r in guild %s", track.title, guild.id)
            if source:
                await asyncio.to_thread(source.cleanup)
            return EndReason.ERROR

    async def _player_worker(self, guild_id: int) -> None:
        player = self.players[guild_id]
        try:
            while True:
                await player.wake.wait()
                guild = self.bot.get_guild(guild_id)
                if guild is None:
                    return

                async with player.lock:
                    if player.external_audio or not player.queue:
                        player.wake.clear()
                        if not player.external_audio:
                            self._arm_idle_locked(guild, player)
                        continue

                    track = player.queue.popleft()
                    if not player.queue:
                        player.wake.clear()
                    player.current = track
                    player.playback_idle.clear()
                    control = asyncio.get_running_loop().create_future()
                    player.control = control

                reason = await self._play_track(guild, player, track, control)

                async with player.lock:
                    if player.control is control:
                        player.control = None
                    player.current = None
                    player.playback_idle.set()

                    voice_client = guild.voice_client
                    connection_lost = reason is EndReason.ERROR and (
                        not voice_client or not voice_client.is_connected()
                    )

                    if connection_lost:
                        player.queue.appendleft(track)
                    elif reason is EndReason.NATURAL:
                        if player.loop_mode is LoopMode.ONE:
                            player.queue.appendleft(track)
                        elif player.loop_mode is LoopMode.QUEUE:
                            player.queue.append(track)

                    if connection_lost:
                        player.wake.clear()
                    elif player.queue and not player.external_audio:
                        player.wake.set()
                    else:
                        player.wake.clear()
                        if not player.external_audio:
                            self._arm_idle_locked(guild, player)

                if connection_lost:
                    await self._notify(
                        track.text_channel_id,
                        "⚠️ 語音連線已中斷；歌曲已保留，請重新使用 `/play` 連線。",
                    )
                elif reason is EndReason.ERROR:
                    await self._notify(
                        track.text_channel_id,
                        f"⚠️ **{track.title}** 播放失敗，已嘗試播放下一首。",
                    )
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("Music worker crashed in guild %s", guild_id)
            async with player.lock:
                player.current = None
                player.control = None
                player.playback_idle.set()
                if player.queue and not player.external_audio:
                    player.wake.set()
                else:
                    player.wake.clear()
                    guild = self.bot.get_guild(guild_id)
                    if guild and not player.external_audio:
                        self._arm_idle_locked(guild, player)

            # Do not leave an existing queue without a consumer.
            player.worker_task = asyncio.create_task(
                self._player_worker(guild_id),
                name=f"music-player-{guild_id}-recovery",
            )

    async def _notify(self, channel_id: int, content: str) -> None:
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            return
        try:
            await channel.send(content)
        except Exception:
            log.exception("Failed to send music status to channel %s", channel_id)

    async def prepare_external_audio(
        self,
        guild: discord.Guild,
        voice_channel: discord.abc.Connectable,
    ) -> discord.VoiceClient:
        """Give a game exclusive ownership of the guild VoiceClient."""
        player = self._get_player(guild.id)
        async with player.lock:
            player.command_epoch += 1
            player.external_audio = True
            player.loop_mode = LoopMode.OFF
            player.queue.clear()
            player.wake.clear()
            self._cancel_idle_locked(player)
            if player.control and not player.control.done():
                player.control.set_result(EndReason.STOP)

        voice_client = guild.voice_client
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()

        try:
            await asyncio.wait_for(player.playback_idle.wait(), timeout=6.0)
            return await self._ensure_voice(guild, voice_channel, allow_move=True)
        except Exception:
            async with player.lock:
                player.external_audio = False
                player.playback_idle.set()
                self._arm_idle_locked(guild, player)
            raise

    async def release_external_audio(self, guild: discord.Guild) -> None:
        """Stop game audio and return the VoiceClient to the music worker."""
        player = self._get_player(guild.id)
        async with player.lock:
            player.command_epoch += 1
            player.external_audio = False
            player.loop_mode = LoopMode.OFF
            player.queue.clear()
            player.wake.clear()
            if player.control and not player.control.done():
                player.control.set_result(EndReason.STOP)

        voice_client = guild.voice_client
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()

        try:
            await asyncio.wait_for(player.playback_idle.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            log.warning("Timed out waiting for external audio in guild %s", guild.id)

        async with player.lock:
            self._arm_idle_locked(guild, player)

    @commands.hybrid_command(name="play", description="播放 YouTube 音樂")
    async def play(self, ctx: commands.Context, *, query: str) -> None:
        if self._game_is_active(ctx):
            await ctx.send(
                "🐺 **狼人殺正在進行中！** 現在暫停點歌功能。",
                ephemeral=True,
            )
            return

        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("❌ 你必須先加入一個語音頻道！", ephemeral=True)
            return

        if ctx.interaction:
            await ctx.defer()

        searching_message = await ctx.send(f"🔍 正在搜尋：`{query}` ...")
        player = self._get_player(ctx.guild.id)

        async with player.lock:
            invocation_epoch = player.command_epoch
            player.pending_searches += 1
            self._cancel_idle_locked(player)

        result_message = "❌ 點歌失敗，請稍後再試。"
        try:
            # Preserve command order while keeping skip/stop responsive.
            async with player.request_lock:
                async with player.lock:
                    if (
                        invocation_epoch != player.command_epoch
                        or player.external_audio
                    ):
                        result_message = "⚠️ 這次點歌已被停止或遊戲音效取消。"
                        return

                track = await asyncio.to_thread(
                    self._extract_track_sync,
                    query,
                    ctx.channel.id,
                )

                if self._game_is_active(ctx):
                    result_message = "⚠️ 狼人殺已開始，這次點歌已取消。"
                    return

                voice_state = ctx.author.voice
                if not voice_state or not voice_state.channel:
                    result_message = "⚠️ 你已離開語音頻道，這次點歌已取消。"
                    return

                async with player.lock:
                    if (
                        invocation_epoch != player.command_epoch
                        or player.external_audio
                    ):
                        result_message = "⚠️ 這次點歌已被停止或遊戲音效取消。"
                        return
                    allow_move = player.current is None and not player.queue

                await self._ensure_voice(
                    ctx.guild,
                    voice_state.channel,
                    allow_move=allow_move,
                    expected_epoch=invocation_epoch,
                )

                async with player.lock:
                    if (
                        invocation_epoch != player.command_epoch
                        or player.external_audio
                    ):
                        result_message = "⚠️ 這次點歌已被停止或遊戲音效取消。"
                        return

                    was_idle = player.current is None and not player.queue
                    player.queue.append(track)
                    player.wake.set()
                    self._cancel_idle_locked(player)
                    position = len(player.queue) + (1 if player.current else 0)

                if was_idle:
                    result_message = f"✅ 已找到 **{track.title}**，準備播放。"
                else:
                    result_message = (
                        f"✅ **{track.title}** 已加入佇列（目前第 {position} 首）。"
                    )
        except PlayCancelled:
            result_message = "⚠️ 這次點歌已被停止、離開或遊戲音效取消。"
        except VoiceChannelMismatch as error:
            result_message = f"❌ {error}"
        except (TrackLookupError, yt_dlp.utils.DownloadError) as error:
            log.warning("Track lookup failed for %r: %s", query, error)
            result_message = "❌ 找不到可播放的歌曲，請換一個關鍵字或網址。"
        except Exception as error:
            log.exception("Play command failed in guild %s", ctx.guild.id)
            result_message = f"❌ 點歌失敗（{type(error).__name__}），請稍後再試。"
        finally:
            async with player.lock:
                player.pending_searches = max(0, player.pending_searches - 1)
                self._arm_idle_locked(ctx.guild, player)
            await searching_message.edit(content=result_message)

    @commands.hybrid_command(name="skip", description="跳過目前歌曲")
    async def skip(self, ctx: commands.Context) -> None:
        if self._game_is_active(ctx):
            await ctx.send("🐺 狼人殺進行中，不能控制遊戲音效。", ephemeral=True)
            return

        player = self._get_player(ctx.guild.id)
        async with player.lock:
            control = player.control
            can_skip = bool(player.current and control and not control.done())
            if can_skip:
                control.set_result(EndReason.SKIP)

        if not can_skip:
            await ctx.send("目前沒有音樂正在播放。", ephemeral=True)
            return

        voice_client = ctx.guild.voice_client
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
        await ctx.send("⏭️ 已跳過。")

    @commands.hybrid_command(name="pause", description="暫停")
    async def pause(self, ctx: commands.Context) -> None:
        if self._game_is_active(ctx):
            await ctx.send("🐺 狼人殺進行中，不能控制遊戲音效。", ephemeral=True)
            return
        voice_client = ctx.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            await ctx.send("⏸️ 已暫停")
        else:
            await ctx.send("目前沒有音樂正在播放。", ephemeral=True)

    @commands.hybrid_command(name="resume", description="恢復")
    async def resume(self, ctx: commands.Context) -> None:
        if self._game_is_active(ctx):
            await ctx.send("🐺 狼人殺進行中，不能控制遊戲音效。", ephemeral=True)
            return
        voice_client = ctx.guild.voice_client
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await ctx.send("▶️ 繼續播放")
        else:
            await ctx.send("目前沒有暫停中的音樂。", ephemeral=True)

    @commands.hybrid_command(name="stop", description="停止並清空佇列")
    async def stop(self, ctx: commands.Context) -> None:
        if self._game_is_active(ctx):
            await ctx.send("🐺 狼人殺進行中，不能停止遊戲音效。", ephemeral=True)
            return

        player = self._get_player(ctx.guild.id)
        async with player.lock:
            player.command_epoch += 1
            player.loop_mode = LoopMode.OFF
            player.queue.clear()
            player.wake.clear()
            self._cancel_idle_locked(player)
            if player.control and not player.control.done():
                player.control.set_result(EndReason.STOP)

        voice_client = ctx.guild.voice_client
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()

        async with player.lock:
            self._arm_idle_locked(ctx.guild, player)
        await ctx.send("⏹️ 已停止並清空佇列。")

    @commands.hybrid_command(name="queue", description="查看播放清單")
    async def queue(self, ctx: commands.Context) -> None:
        player = self._get_player(ctx.guild.id)
        async with player.lock:
            current = player.current
            queued = list(player.queue)

        if not current and not queued:
            await ctx.send("佇列是空的。")
            return

        lines = []
        if current:
            lines.append(f"正在播放：**{current.title}**")
        lines.extend(
            f"{index}. {track.title}"
            for index, track in enumerate(queued[:10], start=1)
        )
        if len(queued) > 10:
            lines.append(f"... 以及其他 {len(queued) - 10} 首")

        embed = discord.Embed(
            title="🎵 播放佇列",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="loop", description="切換循環模式")
    async def loop(self, ctx: commands.Context) -> None:
        if self._game_is_active(ctx):
            await ctx.send("🐺 狼人殺進行中，不能變更循環模式。", ephemeral=True)
            return

        player = self._get_player(ctx.guild.id)
        modes = [LoopMode.OFF, LoopMode.ONE, LoopMode.QUEUE]
        labels = {
            LoopMode.OFF: "關閉",
            LoopMode.ONE: "單曲循環",
            LoopMode.QUEUE: "佇列循環",
        }
        async with player.lock:
            index = (modes.index(player.loop_mode) + 1) % len(modes)
            player.loop_mode = modes[index]
            label = labels[player.loop_mode]
        await ctx.send(f"🔁 循環模式：{label}")

    @commands.hybrid_command(name="leave", description="讓機器人離開")
    async def leave(self, ctx: commands.Context) -> None:
        if self._game_is_active(ctx):
            await ctx.send("🐺 狼人殺還沒結束，我不能離開。", ephemeral=True)
            return

        player = self._get_player(ctx.guild.id)
        async with player.lock:
            player.command_epoch += 1
            player.loop_mode = LoopMode.OFF
            player.queue.clear()
            player.wake.clear()
            self._cancel_idle_locked(player)
            if player.control and not player.control.done():
                player.control.set_result(EndReason.LEAVE)

        async with player.voice_lock:
            # Re-read while holding the same lock used by connect(). A pending
            # /play may have created the VoiceClient after leave incremented
            # command_epoch.
            voice_client = ctx.guild.voice_client
            if not voice_client:
                disconnected = False
            else:
                if voice_client.is_playing() or voice_client.is_paused():
                    voice_client.stop()
                await voice_client.disconnect()
                disconnected = True

        if disconnected:
            await ctx.send("掰掰！")
        else:
            await ctx.send("我不在語音頻道中。", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))
