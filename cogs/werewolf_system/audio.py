import asyncio
import logging
import os

import discord

from .const import SOUND_FOLDER


log = logging.getLogger(__name__)


class AudioManager:
    _locks: dict[int, asyncio.Lock] = {}

    @classmethod
    def _get_lock(cls, guild_id: int) -> asyncio.Lock:
        lock = cls._locks.get(guild_id)
        if lock is None:
            lock = asyncio.Lock()
            cls._locks[guild_id] = lock
        return lock

    @staticmethod
    async def mute_all(ctx, players, mute=True):
        """將所有遊戲玩家靜音或解除靜音。"""
        states = {player.id: mute for player in players}
        await AudioManager.set_mute_states(ctx, states)

    @staticmethod
    async def set_mute_states(ctx, states: dict[int, bool]):
        """依玩家套用伺服器靜音狀態，並保留個別差異。"""
        tasks = []
        for user_id, muted in states.items():
            member = ctx.guild.get_member(user_id)
            if (
                member
                and member.voice
                and bool(member.voice.mute) != bool(muted)
            ):
                tasks.append(member.edit(mute=muted))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    log.warning("更新玩家靜音狀態失敗：%s", result)

    @classmethod
    async def play_mixed(cls, ctx, bgm_file, voice_file=None):
        """播放狼人殺 BGM，必要時混入旁白。"""
        guild = ctx.guild
        async with cls._get_lock(guild.id):
            voice_client = guild.voice_client
            if not voice_client or not voice_client.is_connected():
                log.warning("無法播放狼人殺音效：語音尚未連線")
                return

            bgm_path = os.path.join(SOUND_FOLDER, bgm_file)
            if not os.path.exists(bgm_path):
                log.error("找不到 BGM：%s", bgm_path)
                return

            if voice_client.is_playing() or voice_client.is_paused():
                voice_client.stop()
                await asyncio.sleep(0.1)

            source = None
            try:
                if voice_file:
                    voice_path = os.path.join(SOUND_FOLDER, voice_file)
                    if os.path.exists(voice_path):
                        complex_filter = (
                            "[0:a]volume=0.4[bg];"
                            "[1:a]volume=1.5[voice];"
                            "[bg][voice]amix=inputs=2:duration=first:"
                            "dropout_transition=2"
                        )
                        before_options = (
                            f'-stream_loop -1 -i "{bgm_path}" '
                            f'-filter_complex "{complex_filter}"'
                        )
                        source = discord.FFmpegOpusAudio(
                            voice_path,
                            before_options=before_options,
                            options="-vn",
                            codec=None,
                            bitrate=128,
                        )

                if source is None:
                    source = discord.FFmpegOpusAudio(
                        bgm_path,
                        before_options="-stream_loop -1",
                        options="-vn",
                        codec=None,
                        bitrate=128,
                    )

                voice_client.play(source)
            except Exception:
                if source is not None:
                    await asyncio.to_thread(source.cleanup)
                log.exception("播放狼人殺音效失敗")

    @classmethod
    async def stop(cls, ctx):
        """停止狼人殺音效。"""
        guild = ctx.guild
        async with cls._get_lock(guild.id):
            voice_client = guild.voice_client
            if voice_client and (
                voice_client.is_playing() or voice_client.is_paused()
            ):
                voice_client.stop()
                await asyncio.sleep(0.1)
