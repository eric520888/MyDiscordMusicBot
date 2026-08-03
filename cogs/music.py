from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass, field, replace
from enum import Enum, auto
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import discord
import yt_dlp
from discord.ext import commands


log = logging.getLogger(__name__)

IDLE_TIMEOUT_SECONDS = 180
VOICE_CONNECT_TIMEOUT_SECONDS = 30.0
PANEL_REFRESH_SECONDS = 10.0
METADATA_RETRY_BUDGET_SECONDS = 45.0
LOW_RESOURCE_YOUTUBE_ARGS = (
    "--no-js-runtimes",
    "--extractor-args",
    "youtube:player_client=android_vr",
)

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


class PlaybackFailure(Enum):
    AUTH_REQUIRED = auto()
    COOKIE_CONFIG = auto()
    JS_CHALLENGE = auto()
    RATE_LIMIT = auto()
    NETWORK = auto()
    UNAVAILABLE = auto()
    OTHER = auto()


class TrackLookupError(Exception):
    """Raised when yt-dlp cannot find a playable track."""

    def __init__(
        self,
        message: str,
        failure: PlaybackFailure = PlaybackFailure.OTHER,
        *,
        user_safe: bool = False,
        cookie_rejected: bool = False,
    ) -> None:
        super().__init__(message)
        self.failure = failure
        self.user_safe = user_safe
        self.cookie_rejected = cookie_rejected


class CookieConfigurationError(Exception):
    """Raised when a configured cookie source cannot be used safely."""


def _auth_required_message(*, cookie_rejected: bool, icon: str) -> str:
    if cookie_rejected:
        return (
            f"{icon} YouTube 已讀取 Cookie，但登入驗證仍被拒絕。\n"
            "目前的 Cookie 可能已過期、被 YouTube 輪替或失效；請重新匯出 "
            "cookies.txt，更新 `YTDLP_COOKIES_B64` 後重新部署。"
        )
    return (
        f"{icon} YouTube 要求登入驗證，但目前沒有可用的 Cookie。\n"
        "Railway 請設定 `YTDLP_COOKIES_B64` 後重新部署。"
    )


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
    SEEK = auto()
    STOP = auto()
    LEAVE = auto()


class PlaybackState(Enum):
    IDLE = auto()
    LOADING = auto()
    PLAYING = auto()
    PAUSED = auto()
    SEEKING = auto()
    ERROR = auto()
    EXTERNAL = auto()


@dataclass(frozen=True, slots=True)
class PlaybackControl:
    reason: EndReason
    seek_to: float | None = None
    keep_paused: bool = False
    failure: PlaybackFailure | None = None
    safe_to_retry: bool = False
    halt_queue: bool = False


@dataclass(frozen=True, slots=True)
class YTDLAuth:
    label: str
    cli_args: tuple[str, ...]
    cookiefile: str | None = None
    cookiesfrombrowser: tuple[str, str | None, str | None, str | None] | None = None


@dataclass(frozen=True, slots=True)
class Track:
    title: str
    webpage_url: str
    duration: int | None
    text_channel_id: int
    requester_id: int
    uploader: str | None = None
    thumbnail_url: str | None = None
    start_at: float = 0.0
    auth_args: tuple[str, ...] = ()
    auth_cookiefile: str | None = None
    auth_label: str | None = None
    ytdlp_extra_args: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PlayerSnapshot:
    state: PlaybackState
    current: Track | None
    last_track: Track | None
    queued: tuple[Track, ...]
    loop_mode: LoopMode
    position: float
    playback_id: int
    voice_channel_id: int | None


def parse_time_value(value: str) -> float:
    """Parse seconds, MM:SS, HH:MM:SS, or compact h/m/s notation."""
    raw = value.strip().lower()
    if not raw:
        raise ValueError("請輸入時間，例如 `90`、`1:30` 或 `1h2m3s`。")

    if re.fullmatch(r"\d+(?:\.\d+)?", raw):
        seconds = float(raw)
    elif ":" in raw:
        parts = raw.split(":")
        if len(parts) not in {2, 3} or not all(
            re.fullmatch(r"\d+", part) for part in parts
        ):
            raise ValueError("時間格式錯誤，請使用 `MM:SS` 或 `HH:MM:SS`。")
        numbers = [int(part) for part in parts]
        if numbers[-1] >= 60 or (len(numbers) == 3 and numbers[-2] >= 60):
            raise ValueError("秒數與小時格式中的分鐘必須介於 0 到 59。")
        if len(numbers) == 2:
            seconds = numbers[0] * 60 + numbers[1]
        else:
            seconds = numbers[0] * 3600 + numbers[1] * 60 + numbers[2]
    else:
        unit_match = re.fullmatch(
            r"\s*(?:(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hour|hours|小時|時))?"
            r"\s*(?:(\d+(?:\.\d+)?)\s*(?:m|min|mins|minute|minutes|分鐘|分))?"
            r"\s*(?:(\d+(?:\.\d+)?)\s*(?:s|sec|secs|second|seconds|秒))?\s*",
            raw,
        )
        if not unit_match or not any(unit_match.groups()):
            raise ValueError("時間格式錯誤，請使用 `90`、`1:30` 或 `1h2m3s`。")
        hours, minutes, unit_seconds = (
            float(part) if part is not None else 0.0
            for part in unit_match.groups()
        )
        seconds = hours * 3600 + minutes * 60 + unit_seconds

    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("時間必須是大於或等於 0 的有限數值。")
    return seconds


def format_time_value(seconds: float | int | None) -> str:
    if seconds is None or not math.isfinite(float(seconds)):
        return "未知"
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def progress_bar(position: float, duration: int | None, width: int = 16) -> str:
    if not duration or duration <= 0:
        return "▰" + "▱" * (width - 1)
    ratio = min(1.0, max(0.0, position / duration))
    filled = min(width, max(0, round(ratio * width)))
    return "▰" * filled + "▱" * (width - filled)


def _prefer_low_resource_youtube() -> bool:
    setting = os.getenv("YTDLP_LOW_RESOURCE", "auto").strip().lower()
    if setting in {"1", "true", "yes", "on"}:
        return True
    if setting in {"0", "false", "no", "off"}:
        return False
    return any(
        os.getenv(name)
        for name in (
            "RAILWAY_PROJECT_ID",
            "RAILWAY_SERVICE_ID",
            "RAILWAY_ENVIRONMENT_ID",
        )
    )


def _configure_deno_memory_limit() -> None:
    if os.getenv("DENO_V8_FLAGS"):
        return
    configured = os.getenv("YTDLP_DENO_V8_FLAGS", "").strip()
    on_railway = any(
        os.getenv(name)
        for name in (
            "RAILWAY_PROJECT_ID",
            "RAILWAY_SERVICE_ID",
            "RAILWAY_ENVIRONMENT_ID",
        )
    )
    if not configured and on_railway:
        configured = "--max-old-space-size=64"
    if configured:
        os.environ.setdefault("DENO_V8_FLAGS", configured)


def _classify_ytdlp_error(message: str) -> PlaybackFailure:
    lowered = message.lower()
    if (
        "permission denied" in lowered
        and "cookie" in lowered
    ) or (
        "could not copy" in lowered
        and ("cookie" in lowered or "database" in lowered)
    ):
        return PlaybackFailure.COOKIE_CONFIG
    if any(
        marker in lowered
        for marker in (
            "failed to decrypt",
            "cookie database",
            "cookies database",
            "could not find firefox cookies",
            "could not find chrome cookies",
            "could not find edge cookies",
            "failed to load cookies",
            "does not look like a netscape format",
            "invalid cookies",
        )
    ):
        return PlaybackFailure.COOKIE_CONFIG
    if any(
        marker in lowered
        for marker in (
            "error running deno process",
            "error running node process",
            "challenge solving failed",
            "n challenge solving failed",
            "signature solving failed",
            "only images are available",
            "requested format is not available",
            "no video formats found",
            "no formats found",
        )
    ):
        return PlaybackFailure.JS_CHALLENGE
    if any(
        marker in lowered
        for marker in (
            "sign in to confirm",
            "login required",
            "please log in",
            "not a bot",
            "confirm you’re not a bot",
            "confirm you're not a bot",
            "不是機器人",
            "不是机器人",
            "請登入以確認",
            "请登录以确认",
            "cookies are no longer valid",
            "cookies have expired",
            "cookies have been rotated",
            "account cookies have expired",
            "--cookies-from-browser",
        )
    ):
        return PlaybackFailure.AUTH_REQUIRED
    if any(
        marker in lowered
        for marker in (
            "http error 403",
            "http error 429",
            "status code 403",
            "too many requests",
            "rate limit",
        )
    ):
        return PlaybackFailure.RATE_LIMIT
    if any(
        marker in lowered
        for marker in (
            "timed out",
            "timeout",
            "temporary failure in name resolution",
            "connection reset",
            "connection refused",
            "failed to establish a new connection",
            "remote end closed connection",
            "network is unreachable",
            "unable to download api page",
            "unable to download webpage",
            "winerror 10013",
        )
    ):
        return PlaybackFailure.NETWORK
    if any(
        marker in lowered
        for marker in (
            "private video",
            "video unavailable",
            "not available in your country",
            "has been removed",
        )
    ):
        return PlaybackFailure.UNAVAILABLE
    return PlaybackFailure.OTHER


def _sanitize_ytdlp_message(message: str) -> str:
    sanitized = re.sub(
        r"(?im)^([^\r\n]*(?:cookie|authorization)\s*:\s*)[^\r\n]+$",
        r"\1<redacted>",
        message,
    )
    cookie_file = os.getenv("YTDLP_COOKIE_FILE", "").strip()
    if cookie_file:
        cookie_paths = {cookie_file, os.path.expandvars(cookie_file)}
        try:
            expanded = Path(os.path.expandvars(cookie_file)).expanduser()
            cookie_paths.update({str(expanded), str(expanded.resolve())})
        except OSError:
            pass
        cookie_paths.update(path.replace("\\", "/") for path in tuple(cookie_paths))
        for path in sorted(cookie_paths, key=len, reverse=True):
            if path:
                if os.name == "nt":
                    sanitized = re.sub(
                        re.escape(path),
                        "<cookie-file>",
                        sanitized,
                        flags=re.IGNORECASE,
                    )
                else:
                    sanitized = sanitized.replace(path, "<cookie-file>")
    return sanitized


def _auto_cookie_browser_specs() -> list[str]:
    if os.name != "nt":
        return []
    local = Path(os.getenv("LOCALAPPDATA", ""))
    roaming = Path(os.getenv("APPDATA", ""))
    candidates = (
        ("firefox", roaming / "Mozilla" / "Firefox" / "Profiles"),
        ("chrome", local / "Google" / "Chrome" / "User Data"),
        ("edge", local / "Microsoft" / "Edge" / "User Data"),
        ("brave", local / "BraveSoftware" / "Brave-Browser" / "User Data"),
    )
    return [name for name, path in candidates if str(path) and path.exists()]


def _parse_browser_cookie_spec(spec: str) -> tuple[str, str | None, str | None, str | None]:
    try:
        parsed = yt_dlp.parse_options(
            ["--ignore-config", "--cookies-from-browser", spec]
        ).ydl_opts["cookiesfrombrowser"]
    except Exception as error:
        raise CookieConfigurationError("瀏覽器 cookie 設定格式無效。") from error
    if not isinstance(parsed, tuple) or len(parsed) != 4:
        raise CookieConfigurationError("瀏覽器 cookie 設定格式無效。")
    return parsed


def _materialize_base64_cookie_file() -> str | None:
    """Decode Railway's YTDLP_COOKIES_B64 into a private Netscape cookie file."""
    encoded = os.getenv("YTDLP_COOKIES_B64", "").strip()
    if not encoded:
        return None

    # Be tolerant if the value was pasted with wrapping quotes or line breaks.
    if len(encoded) >= 2 and encoded[0] == encoded[-1] and encoded[0] in {"'", '"'}:
        encoded = encoded[1:-1].strip()
    compact = "".join(encoded.split())

    try:
        cookie_bytes = base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError) as error:
        raise CookieConfigurationError(
            "YTDLP_COOKIES_B64 不是有效的 Base64。"
        ) from error

    if not cookie_bytes:
        raise CookieConfigurationError("YTDLP_COOKIES_B64 解碼後是空檔案。")

    # yt-dlp expects the Netscape cookie-file format.
    check_bytes = cookie_bytes
    if check_bytes.startswith(b"\xef\xbb\xbf"):
        check_bytes = check_bytes[3:]
    first_line = check_bytes.splitlines()[0].strip() if check_bytes.splitlines() else b""
    if first_line not in {
        b"# Netscape HTTP Cookie File",
        b"# HTTP Cookie File",
    }:
        raise CookieConfigurationError(
            "YTDLP_COOKIES_B64 解碼後不是 Netscape cookies.txt 格式。"
        )

    cookie_path = Path(tempfile.gettempdir()) / "discordbot-ytdlp-master-cookies.txt"
    temporary_path = cookie_path.with_name(
        f"{cookie_path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        temporary_path.write_bytes(cookie_bytes)
        try:
            os.chmod(temporary_path, 0o600)
        except OSError:
            pass
        os.replace(temporary_path, cookie_path)
        return str(cookie_path.resolve())
    except OSError as error:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise CookieConfigurationError(
            "無法把 YTDLP_COOKIES_B64 寫入 Railway 暫存檔。"
        ) from error


def _configured_auth_candidates() -> list[YTDLAuth]:
    cookie_file_value = os.getenv("YTDLP_COOKIE_FILE", "").strip()
    if cookie_file_value:
        cookie_path = Path(os.path.expandvars(cookie_file_value)).expanduser()
        if not cookie_path.is_file():
            raise CookieConfigurationError(
                "YTDLP_COOKIE_FILE 指向的 cookie 檔案不存在。"
            )
        resolved = str(cookie_path.resolve())
        return [
            YTDLAuth(
                label="cookie 檔案",
                cli_args=("--cookies", resolved),
                cookiefile=resolved,
            )
        ]

    base64_cookie_file = _materialize_base64_cookie_file()
    if base64_cookie_file:
        return [
            YTDLAuth(
                label="Railway Base64 cookie",
                cli_args=("--cookies", base64_cookie_file),
                cookiefile=base64_cookie_file,
            )
        ]

    # Browser-profile extraction is useful locally, but Railway/Linux normally
    # has no logged-in Chrome/Firefox profile to read.
    browser_default = "auto" if os.name == "nt" else "off"
    browser_setting = os.getenv(
        "YTDLP_COOKIES_FROM_BROWSER",
        browser_default,
    ).strip()
    if browser_setting.lower() in {"", "off", "none", "false", "0"}:
        return []
    specs = (
        _auto_cookie_browser_specs()
        if browser_setting.lower() == "auto"
        else [browser_setting]
    )

    candidates: list[YTDLAuth] = []
    for spec in dict.fromkeys(specs):
        parsed = _parse_browser_cookie_spec(spec)
        candidates.append(
            YTDLAuth(
                label=f"{parsed[0]} 瀏覽器",
                cli_args=("--cookies-from-browser", spec),
                cookiesfrombrowser=parsed,
            )
        )
    return candidates


def _apply_auth_options(options: dict[str, Any], auth: YTDLAuth | None) -> None:
    if auth is None:
        return
    if auth.cookiefile:
        options["cookiefile"] = auth.cookiefile
    if auth.cookiesfrombrowser:
        options["cookiesfrombrowser"] = auth.cookiesfrombrowser


def _create_cookie_snapshot(source: str) -> str:
    """Copy a master Netscape cookie file for one isolated yt-dlp operation."""
    file_descriptor: int | None = None
    snapshot: str | None = None
    try:
        file_descriptor, snapshot = tempfile.mkstemp(
            prefix="discordbot-ytdlp-cookies-",
            suffix=".txt",
        )
        os.close(file_descriptor)
        file_descriptor = None
        shutil.copyfile(source, snapshot)
        try:
            os.chmod(snapshot, 0o600)
        except OSError:
            pass
        return snapshot
    except OSError as error:
        if file_descriptor is not None:
            try:
                os.close(file_descriptor)
            except OSError:
                pass
        try:
            if snapshot:
                os.remove(snapshot)
        except OSError:
            pass
        raise CookieConfigurationError(
            "Cookie 檔案無法建立安全的暫存副本。"
        ) from error


def _remove_cookie_snapshot(snapshot: str | None) -> None:
    if not snapshot:
        return
    try:
        os.remove(snapshot)
    except FileNotFoundError:
        pass
    except OSError:
        log.warning("Could not remove a temporary yt-dlp cookie snapshot")


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
    control: asyncio.Future[PlaybackControl] | None = None
    worker_task: asyncio.Task[None] | None = None
    idle_task: asyncio.Task[None] | None = None
    loop_mode: LoopMode = LoopMode.OFF
    command_epoch: int = 0
    idle_generation: int = 0
    pending_searches: int = 0
    external_audio: bool = False
    state: PlaybackState = PlaybackState.IDLE
    last_track: Track | None = None
    active_source: YTDLPipeAudio | None = None
    playback_id: int = 0
    started_at: float | None = None
    paused_at: float | None = None
    paused_total: float = 0.0
    panel_message: discord.Message | None = None
    panel_update_task: asyncio.Task[None] | None = None
    panel_view: discord.ui.View | None = None
    panel_wake: asyncio.Event = field(default_factory=asyncio.Event)
    panel_generation: int = 0
    panel_disabled: bool = False


class _YTDLLogger:
    def __init__(self, *, suppress_errors: bool = False) -> None:
        self.suppress_errors = suppress_errors
        # DownloadError often contains only the final "format unavailable"
        # line. Keep the warnings that explain the real cause (for example an
        # n-signature challenge failure) so fallback selection is reliable.
        self.messages: deque[str] = deque(maxlen=40)

    def _remember(self, message: str) -> str:
        sanitized = _sanitize_ytdlp_message(message)
        self.messages.append(sanitized)
        return sanitized

    @property
    def summary(self) -> str:
        return "\n".join(self.messages)

    def debug(self, message: str) -> None:
        if message.startswith("[debug]"):
            log.debug("yt-dlp: %s", _sanitize_ytdlp_message(message))

    def info(self, message: str) -> None:
        log.info("yt-dlp: %s", _sanitize_ytdlp_message(message))

    def warning(self, message: str) -> None:
        sanitized = self._remember(message)
        if self.suppress_errors:
            log.debug("yt-dlp recoverable attempt: %s", sanitized)
        else:
            log.warning("yt-dlp: %s", sanitized)

    def error(self, message: str) -> None:
        sanitized = self._remember(message)
        if self.suppress_errors:
            log.debug("yt-dlp recoverable attempt: %s", sanitized)
        else:
            log.error("yt-dlp: %s", sanitized)


class YTDLPipeAudio(discord.AudioSource):
    """Stream through yt-dlp's downloader, then transcode to Opus with FFmpeg.

    Letting yt-dlp perform the HTTP download avoids handing FFmpeg a temporary
    Google Video URL that may require ranged requests, a PO token, or refreshed
    request data. The subprocess is recreated for every playback and loop.
    """

    def __init__(self, track: Track):
        _configure_deno_memory_limit()
        self.track = track
        self.failed = False
        self.produced_audio = False
        self.error_summary = ""
        self._cleanup_lock = threading.Lock()
        self._cleaned = False
        self._terminated_early = False
        self._current_error: Exception | None = None
        self.cleanup_done = threading.Event()
        self._audio: discord.FFmpegOpusAudio | None = None
        self._cookie_snapshot: str | None = None
        self._ytdl_stderr = tempfile.TemporaryFile()
        self._ffmpeg_stderr = tempfile.TemporaryFile()
        if not math.isfinite(track.start_at) or track.start_at < 0:
            raise ValueError("track.start_at must be a finite non-negative value")
        parsed_url = urlparse(track.webpage_url)
        hostname = (parsed_url.hostname or "").lower().rstrip(".")
        if (
            parsed_url.scheme not in {"http", "https"}
            or not (
                hostname in {"youtube.com", "youtu.be"}
                or hostname.endswith(".youtube.com")
            )
        ):
            raise ValueError("track URL must be an allowed YouTube URL")

        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        command = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--ignore-config",
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
        ]
        if track.auth_cookiefile:
            try:
                self._cookie_snapshot = _create_cookie_snapshot(
                    track.auth_cookiefile
                )
            except Exception:
                self._close_logs()
                raise
            command.extend(("--cookies", self._cookie_snapshot))
        else:
            command.extend(track.auth_args)
        command.extend(track.ytdlp_extra_args)
        if track.start_at > 0:
            command.extend(
                ["--download-sections", f"*{track.start_at:.3f}-inf"]
            )
        command.extend(("--", track.webpage_url))

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
            _remove_cookie_snapshot(self._cookie_snapshot)
            self._cookie_snapshot = None
            self._close_logs()
            raise

    def read(self) -> bytes:
        if self._audio is None:
            return b""
        data = self._audio.read()
        if data and not data.startswith((b"OpusHead", b"OpusTags")):
            self.produced_audio = True
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
                self.error_summary = _sanitize_ytdlp_message("\n".join(
                    part for part in (ytdl_log, ffmpeg_log) if part
                )[-4000:])
                log.warning(
                    "Audio pipeline failed for %r (yt-dlp=%s, ffmpeg=%s): %s",
                    self.track.title,
                    ytdl_rc,
                    ffmpeg_rc,
                    self.error_summary or "no stderr output",
                )
        finally:
            _remove_cookie_snapshot(self._cookie_snapshot)
            self._cookie_snapshot = None
            self._close_logs()
            self.cleanup_done.set()


class SeekModal(discord.ui.Modal):
    def __init__(
        self,
        music: Music,
        guild_id: int,
        playback_id: int,
        panel_message_id: int,
    ) -> None:
        super().__init__(title="跳轉播放位置", timeout=60)
        self.music = music
        self.guild_id = guild_id
        self.playback_id = playback_id
        self.panel_message_id = panel_message_id
        self.position_input = discord.ui.TextInput(
            label="要跳到哪裡？",
            placeholder="例如：90、1:30、01:02:03",
            min_length=1,
            max_length=20,
        )
        self.add_item(self.position_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.music._panel_seek_submit(
            interaction,
            self.guild_id,
            self.playback_id,
            self.panel_message_id,
            str(self.position_input.value),
        )

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
    ) -> None:
        log.error(
            "Music seek modal failed",
            exc_info=(type(error), error, error.__traceback__),
        )
        await self.music._respond_interaction(
            interaction,
            "❌ 跳轉失敗，請稍後再試。",
        )


class MusicControlsView(discord.ui.View):
    def __init__(
        self,
        music: Music,
        guild_id: int,
        generation: int,
        snapshot: PlayerSnapshot,
    ) -> None:
        super().__init__(timeout=None)
        self.music = music
        self.guild_id = guild_id
        self.generation = generation
        self.playback_id = snapshot.playback_id

        externally_controlled = snapshot.state is PlaybackState.EXTERNAL
        active = snapshot.current is not None and snapshot.state in {
            PlaybackState.PLAYING,
            PlaybackState.PAUSED,
        }
        toggle = discord.ui.Button(
            label="繼續" if snapshot.state is PlaybackState.PAUSED else "暫停",
            emoji="▶️" if snapshot.state is PlaybackState.PAUSED else "⏸️",
            style=(
                discord.ButtonStyle.success
                if snapshot.state is PlaybackState.PAUSED
                else discord.ButtonStyle.primary
            ),
            disabled=not active,
            row=0,
        )
        toggle.callback = self._toggle_pause
        self.add_item(toggle)

        skip = discord.ui.Button(
            label="跳過",
            emoji="⏭️",
            style=discord.ButtonStyle.secondary,
            disabled=externally_controlled or snapshot.current is None,
            row=0,
        )
        skip.callback = self._skip
        self.add_item(skip)

        loop_labels = {
            LoopMode.OFF: "循環：關",
            LoopMode.ONE: "循環：單曲",
            LoopMode.QUEUE: "循環：佇列",
        }
        loop_button = discord.ui.Button(
            label=loop_labels[snapshot.loop_mode],
            emoji="🔁",
            style=(
                discord.ButtonStyle.success
                if snapshot.loop_mode is not LoopMode.OFF
                else discord.ButtonStyle.secondary
            ),
            disabled=externally_controlled or (
                snapshot.current is None and not snapshot.queued
            ),
            row=0,
        )
        loop_button.callback = self._loop
        self.add_item(loop_button)

        seek = discord.ui.Button(
            label="跳轉",
            emoji="⏱️",
            style=discord.ButtonStyle.secondary,
            disabled=(
                not active
                or snapshot.current is None
                or snapshot.current.duration is None
            ),
            row=0,
        )
        seek.callback = self._seek
        self.add_item(seek)

        stop = discord.ui.Button(
            label="停止",
            emoji="⏹️",
            style=discord.ButtonStyle.danger,
            disabled=externally_controlled or (
                snapshot.current is None and not snapshot.queued
            ),
            row=0,
        )
        stop.callback = self._stop
        self.add_item(stop)

        queue = discord.ui.Button(
            label=f"佇列（{len(snapshot.queued)}）",
            emoji="📜",
            style=discord.ButtonStyle.secondary,
            disabled=snapshot.current is None and not snapshot.queued,
            row=1,
        )
        queue.callback = self._queue
        self.add_item(queue)

        leave = discord.ui.Button(
            label="離開",
            emoji="🚪",
            style=discord.ButtonStyle.danger,
            disabled=externally_controlled or snapshot.voice_channel_id is None,
            row=1,
        )
        leave.callback = self._leave
        self.add_item(leave)

        if (
            snapshot.current
            and Music._is_url(snapshot.current.webpage_url)
            and len(snapshot.current.webpage_url) <= 512
        ):
            self.add_item(
                discord.ui.Button(
                    label="在 YouTube 開啟",
                    emoji="🔗",
                    style=discord.ButtonStyle.link,
                    url=snapshot.current.webpage_url,
                    row=1,
                )
            )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        valid = await self.music._is_current_panel(
            interaction,
            self.guild_id,
            self.generation,
        )
        if not valid:
            await self.music._respond_interaction(
                interaction,
                "⚠️ 這個播放器面板已過期，請使用最新的面板。",
            )
        return valid

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item[Any],
    ) -> None:
        log.error(
            "Music control button failed",
            exc_info=(type(error), error, error.__traceback__),
        )
        await self.music._respond_interaction(
            interaction,
            "❌ 播放器操作失敗，請稍後再試。",
        )

    async def _toggle_pause(self, interaction: discord.Interaction) -> None:
        await self.music._panel_toggle_pause(
            interaction, self.guild_id, self.playback_id
        )

    async def _skip(self, interaction: discord.Interaction) -> None:
        await self.music._panel_skip(interaction, self.guild_id, self.playback_id)

    async def _loop(self, interaction: discord.Interaction) -> None:
        await self.music._panel_loop_mode(interaction, self.guild_id)

    async def _seek(self, interaction: discord.Interaction) -> None:
        await self.music._panel_open_seek(
            interaction, self.guild_id, self.playback_id
        )

    async def _stop(self, interaction: discord.Interaction) -> None:
        await self.music._panel_stop(interaction, self.guild_id)

    async def _queue(self, interaction: discord.Interaction) -> None:
        await self.music._panel_queue(interaction, self.guild_id)

    async def _leave(self, interaction: discord.Interaction) -> None:
        await self.music._panel_leave(interaction, self.guild_id)


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
                player.control.set_result(PlaybackControl(EndReason.STOP))
            if player.worker_task:
                player.worker_task.cancel()
                tasks.append(player.worker_task)
            if player.idle_task:
                player.idle_task.cancel()
                tasks.append(player.idle_task)
            if player.panel_update_task:
                player.panel_update_task.cancel()
                tasks.append(player.panel_update_task)
            if player.panel_view:
                player.panel_view.stop()

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

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        player = self.players.pop(guild.id, None)
        if player is None:
            return
        if player.control and not player.control.done():
            player.control.set_result(PlaybackControl(EndReason.LEAVE))
        tasks = [
            task
            for task in (
                player.worker_task,
                player.idle_task,
                player.panel_update_task,
            )
            if task and task is not asyncio.current_task() and not task.done()
        ]
        for task in tasks:
            task.cancel()
        if player.panel_view:
            player.panel_view.stop()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

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
        if player.panel_update_task is None or player.panel_update_task.done():
            player.panel_update_task = asyncio.create_task(
                self._panel_updater(guild_id),
                name=f"music-panel-{guild_id}",
            )
        return player

    @staticmethod
    def _is_url(query: str) -> bool:
        parsed = urlparse(query)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _is_youtube_url(query: str) -> bool:
        if not Music._is_url(query):
            return False
        hostname = (urlparse(query).hostname or "").lower().rstrip(".")
        return (
            hostname in {"youtube.com", "youtu.be"}
            or hostname.endswith(".youtube.com")
        )

    @staticmethod
    def _extract_track_sync(
        query: str,
        text_channel_id: int,
        requester_id: int,
        start_at: float = 0.0,
    ) -> Track:
        _configure_deno_memory_limit()
        if Music._is_url(query) and not Music._is_youtube_url(query):
            raise TrackLookupError(
                "為了安全，點歌網址只接受 youtube.com 或 youtu.be。",
                user_safe=True,
            )
        search_query = query if Music._is_url(query) else f"ytsearch1:{query}"
        allow_cookie_auth = not Music._is_url(query) or Music._is_youtube_url(query)
        if not math.isfinite(start_at) or start_at < 0:
            raise TrackLookupError("指定的開始時間無效。", user_safe=True)

        last_attempt_log = ""

        def extract(auth: YTDLAuth | None, *, low_resource: bool) -> Any:
            nonlocal last_attempt_log
            options = dict(YDL_OPTIONS)
            attempt_logger = _YTDLLogger(suppress_errors=True)
            options["logger"] = attempt_logger
            if low_resource:
                options["js_runtimes"] = {}
                options["extractor_args"] = {
                    "youtube": {"player_client": ["android_vr"]}
                }
            cookie_snapshot: str | None = None
            operation_auth = auth
            if auth and auth.cookiefile:
                cookie_snapshot = _create_cookie_snapshot(auth.cookiefile)
                operation_auth = replace(
                    auth,
                    cookiefile=cookie_snapshot,
                    cli_args=("--cookies", cookie_snapshot),
                )
            try:
                _apply_auth_options(options, operation_auth)
                with yt_dlp.YoutubeDL(options) as ydl:
                    return ydl.extract_info(search_query, download=False)
            finally:
                last_attempt_log = attempt_logger.summary
                _remove_cookie_snapshot(cookie_snapshot)

        selected_auth: YTDLAuth | None = None
        used_low_resource = False
        preferred_low_resource = _prefer_low_resource_youtube()
        attempts: deque[tuple[YTDLAuth | None, bool, bool]] = deque()
        queued_attempts: set[tuple[YTDLAuth | None, bool, bool]] = set()
        attempted: set[tuple[YTDLAuth | None, bool]] = set()
        retried: set[tuple[YTDLAuth | None, bool]] = set()
        auth_candidates_loaded = False
        auth_candidates: list[YTDLAuth] = []
        cookie_rejected = False
        best_error: Exception | None = None
        best_failure = PlaybackFailure.OTHER
        failure_priority = {
            PlaybackFailure.OTHER: 0,
            PlaybackFailure.UNAVAILABLE: 10,
            PlaybackFailure.NETWORK: 20,
            PlaybackFailure.JS_CHALLENGE: 30,
            PlaybackFailure.RATE_LIMIT: 40,
            PlaybackFailure.AUTH_REQUIRED: 50,
            PlaybackFailure.COOKIE_CONFIG: 60,
        }

        def remember_failure(error: Exception, failure: PlaybackFailure) -> None:
            nonlocal best_error, best_failure
            if (
                best_error is None
                or failure_priority[failure] > failure_priority[best_failure]
            ):
                best_error = error
                best_failure = failure

        def schedule_attempt(
            auth: YTDLAuth | None,
            low_resource: bool,
            *,
            retry: bool = False,
            front: bool = False,
        ) -> None:
            # android_vr is deliberately anonymous; cookie-authenticated
            # extraction must use a client that supports account cookies.
            if low_resource:
                auth = None
            key = (auth, low_resource)
            item = (auth, low_resource, retry)
            if item in queued_attempts:
                return
            if retry:
                if key in retried:
                    return
            elif key in attempted:
                return
            queued_attempts.add(item)
            if front:
                attempts.appendleft(item)
            else:
                attempts.append(item)

        schedule_attempt(None, preferred_low_resource)
        lookup_started = time.monotonic()

        while attempts:
            if (
                (attempted or retried)
                and time.monotonic() - lookup_started
                >= METADATA_RETRY_BUDGET_SECONDS
            ):
                attempts.clear()
                continue
            auth, low_resource, is_retry = attempts.popleft()
            attempt_key = (auth, low_resource)
            queued_attempts.discard((auth, low_resource, is_retry))
            if is_retry:
                if attempt_key in retried:
                    continue
                retried.add(attempt_key)
                # A short bounded delay helps after a transient CDN/API miss
                # without making /play appear stuck.
                time.sleep(0.4)
            else:
                if attempt_key in attempted:
                    continue
                attempted.add(attempt_key)
            try:
                data = extract(auth, low_resource=low_resource)
            except CookieConfigurationError as error:
                remember_failure(error, PlaybackFailure.COOKIE_CONFIG)
                continue
            except yt_dlp.utils.DownloadError as error:
                diagnostic = "\n".join(
                    part for part in (last_attempt_log, str(error)) if part
                )
                failure = _classify_ytdlp_error(diagnostic)
                if failure is PlaybackFailure.AUTH_REQUIRED and auth is not None:
                    cookie_rejected = True
                remember_failure(error, failure)

                if failure in {
                    PlaybackFailure.JS_CHALLENGE,
                    PlaybackFailure.RATE_LIMIT,
                    PlaybackFailure.NETWORK,
                    PlaybackFailure.UNAVAILABLE,
                    PlaybackFailure.OTHER,
                }:
                    # YouTube clients fail independently. Always give the
                    # alternate profile one bounded chance in either direction.
                    schedule_attempt(auth, not low_resource, front=True)
                    if failure is not PlaybackFailure.UNAVAILABLE:
                        schedule_attempt(
                            auth,
                            low_resource,
                            retry=True,
                            front=failure is PlaybackFailure.NETWORK,
                        )

                if (
                    failure is PlaybackFailure.AUTH_REQUIRED
                    and allow_cookie_auth
                    and not auth_candidates_loaded
                ):
                    if auth is None:
                        schedule_attempt(None, not low_resource, front=True)
                    try:
                        auth_candidates = _configured_auth_candidates()
                    except CookieConfigurationError as config_error:
                        remember_failure(
                            config_error,
                            PlaybackFailure.COOKIE_CONFIG,
                        )
                        auth_candidates = []
                    auth_candidates_loaded = True
                    for candidate in auth_candidates:
                        schedule_attempt(candidate, False)
                continue
            else:
                selected_auth = auth
                used_low_resource = low_resource
                break
        else:
            assert best_error is not None
            if (
                best_failure is PlaybackFailure.AUTH_REQUIRED
                and auth_candidates_loaded
                and not auth_candidates
            ):
                raise TrackLookupError(
                    "YouTube 要求登入驗證，但目前沒有可用的 cookie 來源。",
                    PlaybackFailure.AUTH_REQUIRED,
                    user_safe=True,
                ) from best_error
            raise TrackLookupError(
                str(best_error),
                best_failure,
                cookie_rejected=cookie_rejected,
            ) from best_error

        info = data
        if data and "entries" in data:
            info = next((entry for entry in data["entries"] if entry), None)

        if not info:
            raise TrackLookupError("找不到符合的歌曲", user_safe=True)

        webpage_url = (
            info.get("webpage_url")
            or info.get("original_url")
            or (query if Music._is_url(query) else None)
        )
        if not webpage_url:
            raise TrackLookupError(
                "搜尋結果沒有可重新解析的網址", user_safe=True
            )
        if not Music._is_youtube_url(webpage_url):
            raise TrackLookupError(
                "搜尋結果不是可接受的 YouTube 網址。",
                user_safe=True,
            )

        duration = info.get("duration")
        if not isinstance(duration, int):
            duration = int(duration) if isinstance(duration, float) else None

        if start_at > 0 and duration is None:
            raise TrackLookupError(
                "這首歌曲沒有可確認的長度，無法指定開始時間。",
                user_safe=True,
            )
        if duration is not None and start_at >= duration:
            raise TrackLookupError(
                f"開始時間必須小於歌曲長度 {format_time_value(duration)}。",
                user_safe=True,
            )

        return Track(
            title=info.get("title") or "未知歌曲",
            webpage_url=webpage_url,
            duration=duration,
            text_channel_id=text_channel_id,
            requester_id=requester_id,
            uploader=info.get("uploader") or info.get("channel"),
            thumbnail_url=info.get("thumbnail"),
            start_at=start_at,
            auth_args=(
                selected_auth.cli_args
                if selected_auth and not selected_auth.cookiefile
                else ()
            ),
            auth_cookiefile=(
                selected_auth.cookiefile if selected_auth else None
            ),
            auth_label=selected_auth.label if selected_auth else None,
            ytdlp_extra_args=(
                LOW_RESOURCE_YOUTUBE_ARGS if used_low_resource else ()
            ),
        )

    def _game_is_active(self, ctx: commands.Context) -> bool:
        werewolf = self.bot.get_cog("Werewolf")
        if not werewolf:
            return False
        game = werewolf.get_game(ctx)
        return bool(game and game.phase not in {"waiting", "ended"})

    @staticmethod
    def _safe_title(title: str, limit: int = 180) -> str:
        escaped = discord.utils.escape_mentions(
            discord.utils.escape_markdown(title.strip() or "未知歌曲")
        )
        return escaped[:limit]

    def _track_link(
        self,
        track: Track,
        *,
        title_limit: int = 180,
        url_limit: int = 180,
    ) -> str:
        title = self._safe_title(track.title, title_limit)
        if self._is_url(track.webpage_url) and len(track.webpage_url) <= url_limit:
            safe_url = track.webpage_url.replace("(", "%28").replace(")", "%29")
            return f"[{title}]({safe_url})"
        return f"**{title}**"

    @staticmethod
    def _position_locked(player: GuildPlayer, now: float) -> float:
        track = player.current
        if track is None:
            return 0.0
        position = track.start_at
        if player.started_at is not None:
            end = player.paused_at if player.paused_at is not None else now
            position += max(0.0, end - player.started_at - player.paused_total)
        if track.duration is not None:
            position = min(float(track.duration), position)
        return max(0.0, position)

    def _snapshot_locked(
        self,
        guild: discord.Guild,
        player: GuildPlayer,
    ) -> PlayerSnapshot:
        voice_client = guild.voice_client
        channel = voice_client.channel if voice_client else None
        return PlayerSnapshot(
            state=player.state,
            current=player.current,
            last_track=player.last_track,
            queued=tuple(player.queue),
            loop_mode=player.loop_mode,
            position=self._position_locked(player, asyncio.get_running_loop().time()),
            playback_id=player.playback_id,
            voice_channel_id=getattr(channel, "id", None),
        )

    def _build_player_embed(
        self,
        guild: discord.Guild,
        snapshot: PlayerSnapshot,
    ) -> discord.Embed:
        state_settings = {
            PlaybackState.IDLE: ("⏹️ 播放已結束", discord.Color.dark_grey()),
            PlaybackState.LOADING: ("⏳ 正在載入", discord.Color.blurple()),
            PlaybackState.PLAYING: ("🎶 正在播放", discord.Color.green()),
            PlaybackState.PAUSED: ("⏸️ 已暫停", discord.Color.gold()),
            PlaybackState.SEEKING: ("⏩ 正在跳轉", discord.Color.blurple()),
            PlaybackState.ERROR: ("⚠️ 播放失敗", discord.Color.red()),
            PlaybackState.EXTERNAL: ("🐺 遊戲音效接管中", discord.Color.red()),
        }
        title, color = state_settings[snapshot.state]
        track = snapshot.current or snapshot.last_track
        embed = discord.Embed(title=title, color=color)

        if track:
            embed.description = self._track_link(track)
            if track.uploader:
                embed.description += f"\n由 {self._safe_title(track.uploader, 100)} 上傳"
            if track.thumbnail_url and self._is_url(track.thumbnail_url):
                embed.set_thumbnail(url=track.thumbnail_url)
        else:
            embed.description = "佇列目前是空的，使用 `/play` 加入歌曲。"

        if snapshot.current:
            duration_label = format_time_value(snapshot.current.duration)
            embed.add_field(
                name="播放進度",
                value=(
                    f"`{format_time_value(snapshot.position)} / {duration_label}`\n"
                    f"`{progress_bar(snapshot.position, snapshot.current.duration)}`"
                ),
                inline=False,
            )
            if snapshot.current.start_at > 0:
                embed.add_field(
                    name="開始位置",
                    value=f"`{format_time_value(snapshot.current.start_at)}`",
                    inline=True,
                )
            embed.add_field(
                name="點歌者",
                value=f"<@{snapshot.current.requester_id}>",
                inline=True,
            )

        next_track = snapshot.queued[0] if snapshot.queued else None
        embed.add_field(
            name="下一首",
            value=self._safe_title(next_track.title, 100) if next_track else "—",
            inline=True,
        )
        embed.add_field(
            name="佇列",
            value=f"{len(snapshot.queued)} 首",
            inline=True,
        )
        loop_labels = {
            LoopMode.OFF: "關閉",
            LoopMode.ONE: "單曲循環",
            LoopMode.QUEUE: "佇列循環",
        }
        embed.add_field(
            name="循環",
            value=loop_labels[snapshot.loop_mode],
            inline=True,
        )
        embed.add_field(
            name="語音頻道",
            value=(
                f"<#{snapshot.voice_channel_id}>"
                if snapshot.voice_channel_id is not None
                else "未連線"
            ),
            inline=True,
        )
        embed.set_footer(
            text="控制按鈕限同語音頻道成員使用；伺服器管理員可遠端控制"
        )
        return embed

    def _build_queue_embed_from_snapshot(
        self,
        snapshot: PlayerSnapshot,
    ) -> discord.Embed:
        lines: list[str] = []
        if snapshot.current:
            current = snapshot.current
            lines.append(
                f"**正在播放**\n{self._track_link(current, title_limit=140)}"
                f"\n`{format_time_value(snapshot.position)} / {format_time_value(current.duration)}`"
            )
        if snapshot.queued:
            lines.append("\n**接下來**")
            for index, track in enumerate(snapshot.queued[:10], start=1):
                offset = (
                    f" · 從 `{format_time_value(track.start_at)}` 開始"
                    if track.start_at > 0
                    else ""
                )
                lines.append(
                    f"`{index:02d}.` {self._track_link(track, title_limit=110)}"
                    f" · `{format_time_value(track.duration)}`{offset}"
                )
            if len(snapshot.queued) > 10:
                lines.append(f"… 以及其他 {len(snapshot.queued) - 10} 首")

        description = "\n".join(lines) if lines else "佇列目前是空的。"
        if len(description) > 4000:
            description = description[:3997] + "..."
        embed = discord.Embed(
            title=f"🎵 播放佇列 · {len(snapshot.queued)} 首等待中",
            description=description,
            color=discord.Color.blurple(),
        )
        return embed

    async def _queue_embed(self, guild: discord.Guild) -> discord.Embed:
        player = self._get_player(guild.id)
        async with player.lock:
            snapshot = self._snapshot_locked(guild, player)
        return self._build_queue_embed_from_snapshot(snapshot)

    async def _panel_updater(self, guild_id: int) -> None:
        player = self.players[guild_id]
        retry_delay = 5.0
        try:
            while True:
                await player.panel_wake.wait()
                player.panel_wake.clear()
                guild = self.bot.get_guild(guild_id)
                if guild is None:
                    if player.panel_view:
                        player.panel_view.stop()
                    for task in (player.worker_task, player.idle_task):
                        if task and not task.done():
                            task.cancel()
                    if self.players.get(guild_id) is player:
                        self.players.pop(guild_id, None)
                    return

                async with player.lock:
                    snapshot = self._snapshot_locked(guild, player)
                    message = player.panel_message
                    disabled = player.panel_disabled
                    generation = player.panel_generation + 1

                if disabled or (message is None and snapshot.current is None):
                    continue

                embed = self._build_player_embed(guild, snapshot)
                view = MusicControlsView(
                    self,
                    guild_id,
                    generation,
                    snapshot,
                )
                new_message = message
                try:
                    if message is None:
                        channel_id = snapshot.current.text_channel_id
                        channel = self.bot.get_channel(channel_id)
                        if channel is None or not hasattr(channel, "send"):
                            view.stop()
                            log.warning(
                                "Could not find music panel channel %s in guild %s",
                                channel_id,
                                guild_id,
                            )
                            continue
                        new_message = await channel.send(embed=embed, view=view)
                    else:
                        await message.edit(embed=embed, view=view)
                except discord.NotFound:
                    view.stop()
                    async with player.lock:
                        if player.panel_message is message:
                            old_view = player.panel_view
                            player.panel_message = None
                            player.panel_view = None
                            if snapshot.current is not None:
                                player.panel_wake.set()
                        else:
                            old_view = None
                    if old_view:
                        old_view.stop()
                    if snapshot.current is not None:
                        await asyncio.sleep(1.0)
                        player.panel_wake.set()
                    continue
                except discord.Forbidden:
                    view.stop()
                    log.warning("Missing permission to create/update music panel in guild %s", guild_id)
                    async with player.lock:
                        player.panel_disabled = True
                    continue
                except discord.HTTPException:
                    view.stop()
                    log.exception("Could not update music panel in guild %s", guild_id)
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(60.0, retry_delay * 2)
                    player.panel_wake.set()
                    continue

                async with player.lock:
                    old_view = player.panel_view
                    player.panel_message = new_message
                    player.panel_view = view
                    player.panel_generation = generation
                if old_view and old_view is not view:
                    old_view.stop()
                retry_delay = 5.0

                if snapshot.state is PlaybackState.PLAYING:
                    try:
                        await asyncio.wait_for(
                            player.panel_wake.wait(),
                            timeout=PANEL_REFRESH_SECONDS,
                        )
                    except asyncio.TimeoutError:
                        player.panel_wake.set()
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("Music panel updater crashed in guild %s", guild_id)

    async def _respond_interaction(
        self,
        interaction: discord.Interaction,
        content: str | None = None,
        *,
        embed: discord.Embed | None = None,
        ephemeral: bool = True,
    ) -> None:
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    content=content,
                    embed=embed,
                    ephemeral=ephemeral,
                )
            else:
                await interaction.response.send_message(
                    content=content,
                    embed=embed,
                    ephemeral=ephemeral,
                )
        except discord.HTTPException:
            log.exception("Could not answer music interaction")

    async def _is_current_panel(
        self,
        interaction: discord.Interaction,
        guild_id: int,
        generation: int,
    ) -> bool:
        if interaction.guild_id != guild_id or interaction.message is None:
            return False
        player = self.players.get(guild_id)
        if player is None:
            return False
        async with player.lock:
            return bool(
                player.panel_message
                and player.panel_message.id == interaction.message.id
                and player.panel_generation == generation
            )

    async def _controller_error(
        self,
        guild: discord.Guild,
        member: discord.Member | discord.User,
    ) -> str | None:
        player = self._get_player(guild.id)
        async with player.lock:
            if player.external_audio:
                return "🐺 狼人殺正在使用語音，現在不能控制音樂。"

        voice_client = guild.voice_client
        if not voice_client or not voice_client.is_connected():
            return "機器人目前不在語音頻道。"
        if isinstance(member, discord.Member):
            if member.guild_permissions.manage_guild:
                return None
            voice_state = member.voice
            if voice_state and voice_state.channel and voice_state.channel.id == voice_client.channel.id:
                return None
        return "請先加入機器人目前所在的語音頻道。"

    async def _toggle_pause_action(
        self,
        guild: discord.Guild,
        expected_playback_id: int | None = None,
        desired_paused: bool | None = None,
    ) -> tuple[bool, str]:
        player = self._get_player(guild.id)
        voice_client = guild.voice_client
        async with player.lock:
            if expected_playback_id is not None and player.playback_id != expected_playback_id:
                return False, "歌曲已切換，請使用最新的播放器面板。"
            source = player.active_source
            control = player.control
            if not player.current or not source or not voice_client:
                return False, "目前沒有音樂正在播放。"
            if (
                player.state not in {PlaybackState.PLAYING, PlaybackState.PAUSED}
                or not control
                or control.done()
            ):
                return False, "播放器正在切換歌曲，請稍後再試。"
            if getattr(voice_client, "source", None) is not source:
                return False, "播放器正在切換歌曲，請稍後再試。"

            now = asyncio.get_running_loop().time()
            if voice_client.is_paused():
                if desired_paused is True:
                    return False, "目前已經是暫停狀態。"
                voice_client.resume()
                if player.paused_at is not None:
                    player.paused_total += max(0.0, now - player.paused_at)
                player.paused_at = None
                player.state = PlaybackState.PLAYING
                message = "▶️ 繼續播放。"
            elif voice_client.is_playing():
                if desired_paused is False:
                    return False, "目前已經在播放。"
                voice_client.pause()
                player.paused_at = now
                player.state = PlaybackState.PAUSED
                message = "⏸️ 已暫停。"
            else:
                return False, "播放器正在切換歌曲，請稍後再試。"
            player.panel_wake.set()
        return True, message

    async def _skip_action(
        self,
        guild: discord.Guild,
        expected_playback_id: int | None = None,
    ) -> tuple[bool, str]:
        player = self._get_player(guild.id)
        async with player.lock:
            if expected_playback_id is not None and player.playback_id != expected_playback_id:
                return False, "歌曲已切換，請使用最新的播放器面板。"
            control = player.control
            if not player.current or not control or control.done():
                return False, "目前沒有音樂正在播放。"
            source = player.active_source
            control.set_result(PlaybackControl(EndReason.SKIP))
            player.state = PlaybackState.LOADING
            player.panel_wake.set()

        voice_client = guild.voice_client
        if (
            source
            and voice_client
            and getattr(voice_client, "source", None) is source
            and (voice_client.is_playing() or voice_client.is_paused())
        ):
            voice_client.stop()
        return True, "⏭️ 已跳過。"

    async def _stop_action(self, guild: discord.Guild) -> tuple[bool, str]:
        player = self._get_player(guild.id)
        async with player.lock:
            had_work = bool(
                player.current or player.queue or player.pending_searches
            )
            player.command_epoch += 1
            player.loop_mode = LoopMode.OFF
            player.queue.clear()
            player.wake.clear()
            self._cancel_idle_locked(player)
            control = player.control
            source = player.active_source
            if control and not control.done():
                control.set_result(PlaybackControl(EndReason.STOP))
            player.state = PlaybackState.IDLE
            player.panel_wake.set()
            if player.current is None:
                self._arm_idle_locked(guild, player)

        voice_client = guild.voice_client
        if (
            source
            and voice_client
            and getattr(voice_client, "source", None) is source
            and (voice_client.is_playing() or voice_client.is_paused())
        ):
            voice_client.stop()
        if not had_work:
            return False, "目前沒有音樂或等待中的點歌。"
        return True, "⏹️ 已停止並清空佇列。"

    async def _cycle_loop_action(self, guild: discord.Guild) -> tuple[bool, str]:
        player = self._get_player(guild.id)
        modes = [LoopMode.OFF, LoopMode.ONE, LoopMode.QUEUE]
        labels = {
            LoopMode.OFF: "關閉",
            LoopMode.ONE: "單曲循環",
            LoopMode.QUEUE: "佇列循環",
        }
        async with player.lock:
            if not player.current and not player.queue:
                return False, "目前沒有歌曲可以設定循環。"
            index = (modes.index(player.loop_mode) + 1) % len(modes)
            player.loop_mode = modes[index]
            label = labels[player.loop_mode]
            player.panel_wake.set()
        return True, f"🔁 循環模式：{label}。"

    async def _seek_action(
        self,
        guild: discord.Guild,
        target: float,
        expected_playback_id: int | None = None,
    ) -> tuple[bool, str]:
        if not math.isfinite(target) or target < 0:
            return False, "時間必須是大於或等於 0 的有限數值。"

        player = self._get_player(guild.id)
        async with player.lock:
            if expected_playback_id is not None and player.playback_id != expected_playback_id:
                return False, "歌曲已切換，請重新開啟跳轉視窗。"
            track = player.current
            control = player.control
            if not track or not control:
                return False, "目前沒有音樂正在播放。"
            if control.done():
                return False, "播放器正在處理上一個操作，請稍後再試。"
            if track.duration is None:
                return False, "這首歌曲沒有可確認的長度，無法跳轉。"
            if target >= track.duration:
                return False, (
                    f"跳轉時間必須小於歌曲長度 "
                    f"`{format_time_value(track.duration)}`。"
                )
            current_position = self._position_locked(
                player, asyncio.get_running_loop().time()
            )
            if abs(current_position - target) < 0.5:
                return True, f"目前已在 `{format_time_value(target)}` 附近。"

            source = player.active_source
            keep_paused = player.state is PlaybackState.PAUSED
            control.set_result(
                PlaybackControl(
                    EndReason.SEEK,
                    seek_to=target,
                    keep_paused=keep_paused,
                )
            )
            player.state = PlaybackState.SEEKING
            player.panel_wake.set()

        voice_client = guild.voice_client
        if (
            source
            and voice_client
            and getattr(voice_client, "source", None) is source
            and (voice_client.is_playing() or voice_client.is_paused())
        ):
            voice_client.stop()
        return True, f"⏩ 正在跳轉到 `{format_time_value(target)}`。"

    async def _leave_action(self, guild: discord.Guild) -> tuple[bool, str]:
        player = self._get_player(guild.id)
        async with player.lock:
            player.command_epoch += 1
            player.loop_mode = LoopMode.OFF
            player.queue.clear()
            player.wake.clear()
            self._cancel_idle_locked(player)
            control = player.control
            source = player.active_source
            if control and not control.done():
                control.set_result(PlaybackControl(EndReason.LEAVE))
            player.state = PlaybackState.IDLE
            player.panel_wake.set()

        async with player.voice_lock:
            voice_client = guild.voice_client
            if not voice_client:
                return False, "我不在語音頻道中。"
            if (
                source
                and getattr(voice_client, "source", None) is source
                and (voice_client.is_playing() or voice_client.is_paused())
            ):
                voice_client.stop()
            try:
                await voice_client.disconnect()
            except Exception as error:
                log.warning(
                    "Voice disconnect failed in guild %s; forcing cleanup: %s",
                    guild.id,
                    error,
                )
                await voice_client.disconnect(force=True)
        return True, "👋 已離開語音頻道。"

    async def _panel_toggle_pause(
        self,
        interaction: discord.Interaction,
        guild_id: int,
        playback_id: int,
    ) -> None:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            await self._respond_interaction(interaction, "伺服器已無法存取。")
            return
        error = await self._controller_error(guild, interaction.user)
        if error:
            await self._respond_interaction(interaction, error)
            return
        _, message = await self._toggle_pause_action(guild, playback_id)
        await self._respond_interaction(interaction, message)

    async def _panel_skip(
        self,
        interaction: discord.Interaction,
        guild_id: int,
        playback_id: int,
    ) -> None:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            await self._respond_interaction(interaction, "伺服器已無法存取。")
            return
        error = await self._controller_error(guild, interaction.user)
        if error:
            await self._respond_interaction(interaction, error)
            return
        _, message = await self._skip_action(guild, playback_id)
        await self._respond_interaction(interaction, message)

    async def _panel_loop_mode(
        self,
        interaction: discord.Interaction,
        guild_id: int,
    ) -> None:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            await self._respond_interaction(interaction, "伺服器已無法存取。")
            return
        error = await self._controller_error(guild, interaction.user)
        if error:
            await self._respond_interaction(interaction, error)
            return
        _, message = await self._cycle_loop_action(guild)
        await self._respond_interaction(interaction, message)

    async def _panel_open_seek(
        self,
        interaction: discord.Interaction,
        guild_id: int,
        playback_id: int,
    ) -> None:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            await self._respond_interaction(interaction, "伺服器已無法存取。")
            return
        error = await self._controller_error(guild, interaction.user)
        if error:
            await self._respond_interaction(interaction, error)
            return

        player = self._get_player(guild_id)
        async with player.lock:
            current = player.current
            panel_message = player.panel_message
            valid = bool(
                current
                and current.duration is not None
                and player.playback_id == playback_id
                and panel_message
            )
            message_id = panel_message.id if panel_message else 0
        if not valid:
            await self._respond_interaction(
                interaction,
                "歌曲已切換，或目前的歌曲無法跳轉。",
            )
            return
        await interaction.response.send_modal(
            SeekModal(self, guild_id, playback_id, message_id)
        )

    async def _panel_seek_submit(
        self,
        interaction: discord.Interaction,
        guild_id: int,
        playback_id: int,
        panel_message_id: int,
        value: str,
    ) -> None:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            await self._respond_interaction(interaction, "伺服器已無法存取。")
            return
        error = await self._controller_error(guild, interaction.user)
        if error:
            await self._respond_interaction(interaction, error)
            return
        player = self._get_player(guild_id)
        async with player.lock:
            panel_is_current = bool(
                player.panel_message
                and player.panel_message.id == panel_message_id
                and player.playback_id == playback_id
            )
        if not panel_is_current:
            await self._respond_interaction(
                interaction,
                "歌曲已切換，請在最新播放器重新開啟跳轉視窗。",
            )
            return
        try:
            target = parse_time_value(value)
        except ValueError as error:
            await self._respond_interaction(interaction, f"❌ {error}")
            return
        _, message = await self._seek_action(guild, target, playback_id)
        await self._respond_interaction(interaction, message)

    async def _panel_stop(
        self,
        interaction: discord.Interaction,
        guild_id: int,
    ) -> None:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            await self._respond_interaction(interaction, "伺服器已無法存取。")
            return
        error = await self._controller_error(guild, interaction.user)
        if error:
            await self._respond_interaction(interaction, error)
            return
        _, message = await self._stop_action(guild)
        await self._respond_interaction(interaction, message)

    async def _panel_queue(
        self,
        interaction: discord.Interaction,
        guild_id: int,
    ) -> None:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            await self._respond_interaction(interaction, "伺服器已無法存取。")
            return
        embed = await self._queue_embed(guild)
        await self._respond_interaction(interaction, embed=embed)

    async def _panel_leave(
        self,
        interaction: discord.Interaction,
        guild_id: int,
    ) -> None:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            await self._respond_interaction(interaction, "伺服器已無法存取。")
            return
        error = await self._controller_error(guild, interaction.user)
        if error:
            await self._respond_interaction(interaction, error)
            return
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)
        _, message = await self._leave_action(guild)
        await self._respond_interaction(interaction, message)

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
    ) -> bool:
        cleaned = await asyncio.to_thread(source.cleanup_done.wait, 3.0)
        if cleaned:
            return True
        log.warning("Audio cleanup timed out in guild %s; forcing cleanup", guild_id)
        await asyncio.to_thread(source.cleanup)
        cleaned = await asyncio.to_thread(source.cleanup_done.wait, 3.0)
        if not cleaned:
            log.error("Audio cleanup did not finish in guild %s", guild_id)
        return cleaned

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

            disconnected = False
            try:
                await asyncio.shield(voice_client.disconnect())
                disconnected = True
                log.info("Disconnected idle voice client in guild %s", guild_id)
            except Exception:
                log.exception("Failed to disconnect idle voice client in guild %s", guild_id)
                try:
                    await asyncio.shield(voice_client.disconnect(force=True))
                    disconnected = True
                except Exception:
                    log.exception(
                        "Forced idle disconnect also failed in guild %s", guild_id
                    )
                    async with player.lock:
                        self._arm_idle_locked(guild, player)
            if disconnected:
                async with player.lock:
                    player.state = PlaybackState.IDLE
                    player.panel_wake.set()

    async def _ensure_voice(
        self,
        guild: discord.Guild,
        voice_channel: discord.abc.Connectable,
        *,
        allow_move: bool,
        expected_epoch: int | None = None,
    ) -> discord.VoiceClient:
        player = self._get_player(guild.id)

        async def ensure_not_cancelled() -> None:
            if expected_epoch is None:
                return
            async with player.lock:
                if (
                    expected_epoch != player.command_epoch
                    or player.external_audio
                ):
                    raise PlayCancelled

        async with player.voice_lock:
            await ensure_not_cancelled()

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

                # stop/leave may have happened while the voice handshake was
                # blocking. Do not clean up and then create a brand-new
                # connection for an already-cancelled /play request.
                await ensure_not_cancelled()
                if voice_client is not None and not connected:
                    log.warning("Cleaning up a stale voice handshake in guild %s", guild.id)
                    try:
                        await voice_client.disconnect(force=True)
                    except Exception:
                        log.exception("Failed to clean up stale voice client")
                    voice_client = None

            if voice_client is None:
                await ensure_not_cancelled()
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
                await ensure_not_cancelled()
                if not allow_move:
                    raise VoiceChannelMismatch(
                        f"請先加入機器人目前所在的語音頻道：{voice_client.channel.name}"
                    )
                await voice_client.move_to(voice_channel)

            try:
                await ensure_not_cancelled()
            except PlayCancelled:
                if created_voice_client and voice_client.is_connected():
                    try:
                        await voice_client.disconnect()
                    except Exception:
                        await voice_client.disconnect(force=True)
                raise

            return voice_client

    async def _play_track(
        self,
        guild: discord.Guild,
        player: GuildPlayer,
        track: Track,
        control: asyncio.Future[PlaybackControl],
        *,
        start_paused: bool = False,
    ) -> PlaybackControl:
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
                    return PlaybackControl(EndReason.ERROR, failure=PlaybackFailure.NETWORK)
                if voice_client.is_playing() or voice_client.is_paused():
                    log.error("Voice client was already busy before playing %r", track.title)
                    return PlaybackControl(EndReason.ERROR)

                source = await asyncio.to_thread(YTDLPipeAudio, track)
                async with player.lock:
                    if (
                        player.control is not control
                        or control.done()
                        or player.external_audio
                    ):
                        cancel_action = (
                            control.result()
                            if control.done()
                            else PlaybackControl(EndReason.STOP)
                        )
                    else:
                        cancel_action = None
                        voice_client.play(
                            source,
                            after=lambda error: loop.call_soon_threadsafe(
                                self._settle_audio, audio_done, error
                            ),
                        )
                        if start_paused:
                            voice_client.pause()
                        now = loop.time()
                        player.active_source = source
                        player.started_at = now
                        player.paused_at = now if start_paused else None
                        player.paused_total = 0.0
                        player.state = (
                            PlaybackState.PAUSED
                            if start_paused
                            else PlaybackState.PLAYING
                        )
                        player.panel_wake.set()
                if cancel_action is not None:
                    await asyncio.to_thread(source.cleanup)
                    return cancel_action

            await asyncio.wait(
                {audio_done, control},
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Explicit user controls win if stop() and the audio callback arrive
            # during the same event-loop turn.
            if control.done():
                action = control.result()
                voice_client = guild.voice_client
                if voice_client and getattr(voice_client, "source", None) is source:
                    voice_client.stop()
                if not audio_done.done():
                    try:
                        await asyncio.wait_for(asyncio.shield(audio_done), timeout=2.0)
                    except asyncio.TimeoutError:
                        log.warning(
                            "Audio callback timed out after %s in guild %s",
                            action.reason,
                            guild.id,
                        )
                if source:
                    cleanup_complete = await self._wait_for_source_cleanup(
                        source, guild.id
                    )
                    if not cleanup_complete and action.reason in {
                        EndReason.SEEK,
                        EndReason.SKIP,
                    }:
                        return PlaybackControl(
                            EndReason.ERROR,
                            halt_queue=True,
                        )
                return action

            error = audio_done.result()
            # AudioPlayer calls source.cleanup() immediately after the callback;
            # wait for its explicit signal rather than racing a fixed sleep.
            cleanup_complete = True
            if source:
                cleanup_complete = await self._wait_for_source_cleanup(
                    source, guild.id
                )
            # A control can arrive after audio_done won the wait but while the
            # AudioPlayer thread is still cleaning up. It must still win over
            # NATURAL so skip/seek never accidentally triggers a loop.
            if control.done():
                return control.result()
            if not cleanup_complete:
                return PlaybackControl(EndReason.ERROR, halt_queue=True)
            if error is not None or (source and source.failed):
                if error:
                    log.warning("Discord audio player failed in guild %s: %s", guild.id, error)
                failure = (
                    _classify_ytdlp_error(source.error_summary)
                    if source and source.error_summary
                    else PlaybackFailure.OTHER
                )
                return PlaybackControl(
                    EndReason.ERROR,
                    failure=failure,
                    safe_to_retry=bool(source and not source.produced_audio),
                )
            voice_client = guild.voice_client
            if not voice_client or not voice_client.is_connected():
                return PlaybackControl(
                    EndReason.ERROR,
                    failure=PlaybackFailure.NETWORK,
                )
            return PlaybackControl(EndReason.NATURAL)
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
        except CookieConfigurationError as error:
            log.warning(
                "Could not prepare YouTube cookies in guild %s: %s",
                guild.id,
                _sanitize_ytdlp_message(str(error)),
            )
            if source:
                await asyncio.to_thread(source.cleanup)
            return PlaybackControl(
                EndReason.ERROR,
                failure=PlaybackFailure.COOKIE_CONFIG,
                safe_to_retry=True,
            )
        except Exception:
            log.exception("Could not play %r in guild %s", track.title, guild.id)
            if source:
                await asyncio.to_thread(source.cleanup)
            return PlaybackControl(EndReason.ERROR)

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
                    player.last_track = track
                    player.playback_idle.clear()
                    player.state = PlaybackState.LOADING
                    player.active_source = None
                    player.started_at = None
                    player.paused_at = None
                    player.paused_total = 0.0
                    player.panel_wake.set()
                    track_epoch = player.command_epoch

                attempt = track
                start_paused = False
                seeking = False
                playback_attempt_counts: dict[
                    tuple[tuple[str, ...], str | None, tuple[str, ...]], int
                ] = {}
                challenge_failure_seen = False
                cookie_auth_attempted = bool(track.auth_label)
                playback_auth_config_error: str | None = None
                if self._is_youtube_url(track.webpage_url):
                    try:
                        playback_auth_fallbacks = [
                            auth
                            for auth in _configured_auth_candidates()
                            if not (
                                (
                                    auth.cookiefile
                                    and auth.cookiefile
                                    == track.auth_cookiefile
                                )
                                or (
                                    not auth.cookiefile
                                    and track.auth_cookiefile is None
                                    and auth.cli_args == track.auth_args
                                )
                            )
                        ]
                    except CookieConfigurationError as error:
                        playback_auth_fallbacks = []
                        playback_auth_config_error = str(error)
                else:
                    playback_auth_fallbacks = []
                while True:
                    async with player.lock:
                        if (
                            player.command_epoch != track_epoch
                            or player.external_audio
                        ):
                            action = PlaybackControl(EndReason.STOP)
                            break
                        player.current = attempt
                        player.last_track = attempt
                        player.playback_id += 1
                        player.state = (
                            PlaybackState.SEEKING
                            if seeking
                            else PlaybackState.LOADING
                        )
                        player.active_source = None
                        player.started_at = None
                        player.paused_at = None
                        player.paused_total = 0.0
                        control = asyncio.get_running_loop().create_future()
                        player.control = control
                        player.panel_wake.set()

                    profile_key = (
                        attempt.auth_args,
                        attempt.auth_cookiefile,
                        attempt.ytdlp_extra_args,
                    )
                    playback_attempt_counts[profile_key] = (
                        playback_attempt_counts.get(profile_key, 0) + 1
                    )

                    action = await self._play_track(
                        guild,
                        player,
                        attempt,
                        control,
                        start_paused=start_paused,
                    )

                    async with player.lock:
                        retry_paused = (
                            player.state is PlaybackState.PAUSED
                            or (start_paused and player.active_source is None)
                        )
                        if player.control is control:
                            player.control = None
                        player.active_source = None
                        player.started_at = None
                        player.paused_at = None
                        player.paused_total = 0.0

                    if (
                        action.reason is EndReason.ERROR
                        and action.failure
                        in {
                            PlaybackFailure.AUTH_REQUIRED,
                            PlaybackFailure.COOKIE_CONFIG,
                        }
                        and action.safe_to_retry
                        and playback_auth_fallbacks
                    ):
                        auth = playback_auth_fallbacks.pop(0)
                        cookie_auth_attempted = True
                        attempt = replace(
                            attempt,
                            auth_args=(
                                auth.cli_args if not auth.cookiefile else ()
                            ),
                            auth_cookiefile=auth.cookiefile,
                            auth_label=auth.label,
                            ytdlp_extra_args=(),
                        )
                        start_paused = retry_paused
                        seeking = attempt.start_at > 0
                        log.info(
                            "Retrying %r with %s cookies in guild %s",
                            track.title,
                            auth.label,
                            guild_id,
                        )
                        continue

                    if (
                        action.reason is EndReason.ERROR
                        and action.safe_to_retry
                        and action.failure
                        in {
                            PlaybackFailure.JS_CHALLENGE,
                            PlaybackFailure.RATE_LIMIT,
                            PlaybackFailure.NETWORK,
                            PlaybackFailure.UNAVAILABLE,
                            PlaybackFailure.OTHER,
                        }
                    ):
                        if action.failure is PlaybackFailure.JS_CHALLENGE:
                            challenge_failure_seen = True

                        # A network miss is most likely transient, so retry the
                        # same pipeline once before changing YouTube clients.
                        current_count = playback_attempt_counts.get(profile_key, 0)
                        if (
                            action.failure is PlaybackFailure.NETWORK
                            and current_count < 2
                        ):
                            await asyncio.sleep(0.4)
                            start_paused = retry_paused
                            seeking = attempt.start_at > 0
                            log.info(
                                "Retrying transient YouTube network failure for %r "
                                "in guild %s",
                                track.title,
                                guild_id,
                            )
                            continue

                        using_low_resource = (
                            attempt.ytdlp_extra_args == LOW_RESOURCE_YOUTUBE_ARGS
                        )
                        if using_low_resource:
                            alternate = replace(
                                attempt,
                                ytdlp_extra_args=(),
                            )
                            alternate_label = "default YouTube client"
                        else:
                            alternate = replace(
                                attempt,
                                auth_args=(),
                                auth_cookiefile=None,
                                auth_label=None,
                                ytdlp_extra_args=LOW_RESOURCE_YOUTUBE_ARGS,
                            )
                            alternate_label = "low-resource YouTube client"
                        alternate_key = (
                            alternate.auth_args,
                            alternate.auth_cookiefile,
                            alternate.ytdlp_extra_args,
                        )
                        # Each profile gets at most two pre-audio attempts. This
                        # permits a transient recovery without profile ping-pong.
                        if playback_attempt_counts.get(alternate_key, 0) < 2:
                            attempt = alternate
                            start_paused = retry_paused
                            seeking = attempt.start_at > 0
                            log.warning(
                                "YouTube playback setup failed for %r in guild %s "
                                "(%s); retrying with the %s",
                                track.title,
                                guild_id,
                                action.failure.name,
                                alternate_label,
                            )
                            continue

                        if current_count < 2:
                            await asyncio.sleep(0.4)
                            start_paused = retry_paused
                            seeking = attempt.start_at > 0
                            continue

                    if action.reason is not EndReason.SEEK:
                        if (
                            action.reason is EndReason.ERROR
                            and challenge_failure_seen
                            and action.failure
                            in {
                                PlaybackFailure.AUTH_REQUIRED,
                                PlaybackFailure.UNAVAILABLE,
                                PlaybackFailure.OTHER,
                            }
                        ):
                            action = replace(
                                action,
                                failure=PlaybackFailure.JS_CHALLENGE,
                            )
                        if (
                            action.reason is EndReason.ERROR
                            and action.failure is PlaybackFailure.AUTH_REQUIRED
                            and playback_auth_config_error
                        ):
                            log.warning(
                                "YouTube cookie configuration is invalid in guild %s: %s",
                                guild_id,
                                _sanitize_ytdlp_message(
                                    playback_auth_config_error
                                ),
                            )
                            action = replace(
                                action,
                                failure=PlaybackFailure.COOKIE_CONFIG,
                            )
                        break
                    if action.seek_to is None or not math.isfinite(action.seek_to):
                        action = PlaybackControl(EndReason.ERROR)
                        break

                    async with player.lock:
                        if (
                            player.command_epoch != track_epoch
                            or player.external_audio
                        ):
                            action = PlaybackControl(EndReason.STOP)
                            break
                    attempt = replace(attempt, start_at=action.seek_to)
                    start_paused = action.keep_paused
                    seeking = True
                    playback_attempt_counts.clear()
                    challenge_failure_seen = False

                async with player.lock:
                    player.current = None
                    player.last_track = attempt
                    player.active_source = None
                    player.started_at = None
                    player.paused_at = None
                    player.paused_total = 0.0
                    player.playback_idle.set()

                    voice_client = guild.voice_client
                    connection_lost = action.reason is EndReason.ERROR and (
                        not voice_client or not voice_client.is_connected()
                    )

                    if action.halt_queue:
                        player.loop_mode = LoopMode.OFF
                        player.queue.clear()
                    elif connection_lost:
                        player.queue.appendleft(replace(attempt, start_at=0.0))
                    elif action.reason is EndReason.NATURAL:
                        loop_track = replace(attempt, start_at=0.0)
                        if player.loop_mode is LoopMode.ONE:
                            player.queue.appendleft(loop_track)
                        elif player.loop_mode is LoopMode.QUEUE:
                            player.queue.append(loop_track)

                    if player.external_audio:
                        player.state = PlaybackState.EXTERNAL
                    elif action.reason is EndReason.ERROR:
                        player.state = PlaybackState.ERROR
                    else:
                        player.state = PlaybackState.IDLE
                    player.panel_wake.set()

                    if action.halt_queue:
                        player.wake.clear()
                    elif connection_lost:
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
                elif action.reason is EndReason.ERROR:
                    if action.halt_queue:
                        failure_message = (
                            "⚠️ 音訊程序未能安全結束，已停止並清空佇列。"
                            "請重新啟動機器人後再點歌。"
                        )
                    elif action.failure is PlaybackFailure.JS_CHALLENGE:
                        failure_message = (
                            "⚠️ YouTube JS challenge 解題失敗，低資源備援也無法取得音訊。"
                            "請確認主機有足夠記憶體，且 yt-dlp、yt-dlp-ejs 與 Deno 都是最新版。"
                        )
                    elif action.failure is PlaybackFailure.AUTH_REQUIRED:
                        failure_message = _auth_required_message(
                            cookie_rejected=cookie_auth_attempted,
                            icon="⚠️",
                        )
                    elif action.failure is PlaybackFailure.COOKIE_CONFIG:
                        failure_message = (
                            "⚠️ YouTube cookie 無法讀取；請確認 "
                            "`YTDLP_COOKIES_B64` 是完整 Base64，"
                            "或用 `YTDLP_COOKIE_FILE` 指向 cookies.txt。"
                        )
                    elif action.failure is PlaybackFailure.RATE_LIMIT:
                        failure_message = "⚠️ YouTube 暫時限制請求，請稍後再點歌。"
                    else:
                        failure_message = (
                            f"⚠️ **{track.title}** 播放失敗，已嘗試播放下一首。"
                        )
                    await self._notify(
                        track.text_channel_id,
                        failure_message,
                    )
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("Music worker crashed in guild %s", guild_id)
            async with player.lock:
                player.current = None
                player.control = None
                player.active_source = None
                player.started_at = None
                player.paused_at = None
                player.paused_total = 0.0
                player.state = PlaybackState.ERROR
                player.panel_wake.set()
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
            source = player.active_source
            if player.control and not player.control.done():
                player.control.set_result(PlaybackControl(EndReason.STOP))
            player.state = PlaybackState.EXTERNAL
            player.panel_wake.set()

        voice_client = guild.voice_client
        if (
            source
            and voice_client
            and getattr(voice_client, "source", None) is source
            and (voice_client.is_playing() or voice_client.is_paused())
        ):
            voice_client.stop()

        try:
            await asyncio.wait_for(player.playback_idle.wait(), timeout=6.0)
            return await self._ensure_voice(guild, voice_channel, allow_move=True)
        except Exception:
            async with player.lock:
                player.external_audio = False
                player.state = PlaybackState.IDLE
                player.panel_wake.set()
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
                player.control.set_result(PlaybackControl(EndReason.STOP))
            player.state = PlaybackState.IDLE
            player.panel_wake.set()

        voice_client = guild.voice_client
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()

        try:
            await asyncio.wait_for(player.playback_idle.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            log.warning("Timed out waiting for external audio in guild %s", guild.id)

        async with player.lock:
            self._arm_idle_locked(guild, player)

    async def _enqueue_query(
        self,
        ctx: commands.Context,
        query: str,
        start_at: float,
    ) -> None:
        if ctx.guild is None:
            await ctx.send("❌ 點歌只能在伺服器內使用。", ephemeral=True)
            return
        if self._game_is_active(ctx):
            await ctx.send(
                "🐺 **狼人殺正在進行中！** 現在暫停點歌功能。",
                ephemeral=True,
            )
            return

        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("❌ 你必須先加入一個語音頻道！", ephemeral=True)
            return

        player = self._get_player(ctx.guild.id)
        async with player.lock:
            invocation_epoch = player.command_epoch
            player.pending_searches += 1
            self._cancel_idle_locked(player)

        # Register the request before the first response await. Otherwise a
        # stop/leave issued while Discord is sending "searching" cannot cancel
        # this /play, and the bot may connect again after it was told to leave.
        try:
            if ctx.interaction:
                await ctx.defer()

            start_label = (
                f"（從 `{format_time_value(start_at)}` 開始）"
                if start_at > 0
                else ""
            )
            searching_message = await ctx.send(
                f"🔍 正在搜尋：`{query}` {start_label}..."
            )
        except BaseException:
            async with player.lock:
                player.pending_searches = max(0, player.pending_searches - 1)
                self._arm_idle_locked(ctx.guild, player)
            raise

        result_message: str | None = "❌ 點歌失敗，請稍後再試。"
        result_embed: discord.Embed | None = None
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
                    ctx.author.id,
                    start_at,
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

                had_voice_connection = bool(
                    ctx.guild.voice_client
                    and ctx.guild.voice_client.is_connected()
                )
                connected_voice = await self._ensure_voice(
                    ctx.guild,
                    voice_state.channel,
                    allow_move=allow_move,
                    expected_epoch=invocation_epoch,
                )

                # The requester can leave or switch channels during Discord's
                # voice handshake. Never start playing alone in the old room.
                current_voice = ctx.author.voice
                if (
                    not current_voice
                    or not current_voice.channel
                    or current_voice.channel.id != voice_state.channel.id
                ):
                    result_message = (
                        "⚠️ 你在連線期間離開或切換了語音頻道，這次點歌已取消。"
                    )
                    async with player.lock:
                        disconnect_unused = (
                            not had_voice_connection
                            and player.current is None
                            and not player.queue
                            and player.pending_searches == 1
                        )
                    if disconnect_unused:
                        async with player.voice_lock:
                            if (
                                ctx.guild.voice_client is connected_voice
                                and not connected_voice.is_playing()
                                and not connected_voice.is_paused()
                            ):
                                try:
                                    await connected_voice.disconnect()
                                except Exception:
                                    await connected_voice.disconnect(force=True)
                    return

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
                    player.panel_disabled = False
                    player.panel_wake.set()
                    position = len(player.queue) + (1 if player.current else 0)

                result_message = None
                result_embed = discord.Embed(
                    title="✅ 準備播放" if was_idle else "✅ 已加入佇列",
                    description=self._track_link(track),
                    color=discord.Color.green(),
                )
                if track.thumbnail_url and self._is_url(track.thumbnail_url):
                    result_embed.set_thumbnail(url=track.thumbnail_url)
                result_embed.add_field(
                    name="長度",
                    value=f"`{format_time_value(track.duration)}`",
                    inline=True,
                )
                result_embed.add_field(
                    name="播放順序",
                    value="即將播放" if was_idle else f"第 {position} 首",
                    inline=True,
                )
                if track.start_at > 0:
                    result_embed.add_field(
                        name="從這裡開始",
                        value=f"`{format_time_value(track.start_at)}`",
                        inline=True,
                    )
                result_embed.set_footer(text=f"由 {ctx.author.display_name} 點歌")
        except PlayCancelled:
            result_message = "⚠️ 這次點歌已被停止、離開或遊戲音效取消。"
        except VoiceChannelMismatch as error:
            result_message = f"❌ {error}"
        except TrackLookupError as error:
            log.warning(
                "Track lookup failed for %r: %s",
                query,
                _sanitize_ytdlp_message(str(error)),
            )
            if error.failure is PlaybackFailure.AUTH_REQUIRED:
                result_message = _auth_required_message(
                    cookie_rejected=error.cookie_rejected,
                    icon="❌",
                )
            elif error.failure is PlaybackFailure.COOKIE_CONFIG:
                result_message = (
                    "❌ YouTube cookie 無法讀取。請確認 `YTDLP_COOKIES_B64` "
                    "是完整 Base64，或使用 `YTDLP_COOKIE_FILE` "
                    "指向 Netscape cookies.txt。"
                )
            elif error.failure is PlaybackFailure.JS_CHALLENGE:
                result_message = (
                    "❌ YouTube JS challenge 解題失敗，低資源備援也無法取得音訊。"
                    "請確認主機記憶體足夠，並重新安裝 requirements.txt。"
                )
            elif error.failure is PlaybackFailure.RATE_LIMIT:
                result_message = "❌ YouTube 暫時限制請求，請稍後再試。"
            elif error.failure is PlaybackFailure.NETWORK:
                result_message = "❌ 連線 YouTube 逾時，請檢查網路後重試。"
            elif error.failure is PlaybackFailure.UNAVAILABLE:
                result_message = "❌ 影片不可用、為私人影片，或受到地區限制。"
            else:
                detail = str(error)
                if error.user_safe and detail and len(detail) <= 180:
                    result_message = (
                        f"❌ {discord.utils.escape_mentions(detail)}"
                    )
                elif self._is_youtube_url(query):
                    result_message = (
                        "⚠️ YouTube 暫時無法取得這支影片的音訊；"
                        "已自動重試兩種播放模式，請稍後再試。"
                    )
                else:
                    result_message = (
                        "❌ 找不到可播放的歌曲，請換一個關鍵字或網址。"
                    )
        except yt_dlp.utils.DownloadError as error:
            log.warning(
                "Unexpected yt-dlp lookup failure for %r: %s",
                query,
                _sanitize_ytdlp_message(str(error)),
            )
            result_message = "❌ YouTube 無法解析這首歌曲，請換一個網址或稍後再試。"
        except Exception as error:
            log.exception("Play command failed in guild %s", ctx.guild.id)
            result_message = f"❌ 點歌失敗（{type(error).__name__}），請稍後再試。"
        finally:
            async with player.lock:
                player.pending_searches = max(0, player.pending_searches - 1)
                self._arm_idle_locked(ctx.guild, player)
            try:
                await searching_message.edit(
                    content=result_message,
                    embed=result_embed,
                )
            except discord.HTTPException:
                log.exception("Could not update play search response")

    @commands.hybrid_command(name="play", description="播放 YouTube 音樂")
    async def play(self, ctx: commands.Context, *, query: str) -> None:
        await self._enqueue_query(ctx, query, 0.0)

    @commands.hybrid_command(
        name="play_at",
        description="從指定時間開始播放 YouTube 音樂",
    )
    async def play_at(
        self,
        ctx: commands.Context,
        start_time: str,
        *,
        query: str,
    ) -> None:
        try:
            start_at = parse_time_value(start_time)
        except ValueError as error:
            await ctx.send(f"❌ {error}", ephemeral=True)
            return
        await self._enqueue_query(ctx, query, start_at)

    @commands.hybrid_command(name="skip", description="跳過目前歌曲")
    async def skip(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.send("這個指令只能在伺服器內使用。", ephemeral=True)
            return
        if self._game_is_active(ctx):
            await ctx.send("🐺 狼人殺進行中，不能控制遊戲音效。", ephemeral=True)
            return
        error = await self._controller_error(ctx.guild, ctx.author)
        if error:
            await ctx.send(error, ephemeral=True)
            return
        ok, message = await self._skip_action(ctx.guild)
        await ctx.send(message, ephemeral=not ok)

    @commands.hybrid_command(name="pause", description="暫停")
    async def pause(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.send("這個指令只能在伺服器內使用。", ephemeral=True)
            return
        if self._game_is_active(ctx):
            await ctx.send("🐺 狼人殺進行中，不能控制遊戲音效。", ephemeral=True)
            return
        error = await self._controller_error(ctx.guild, ctx.author)
        if error:
            await ctx.send(error, ephemeral=True)
            return
        ok, message = await self._toggle_pause_action(
            ctx.guild, desired_paused=True
        )
        await ctx.send(message, ephemeral=not ok)

    @commands.hybrid_command(name="resume", description="恢復")
    async def resume(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.send("這個指令只能在伺服器內使用。", ephemeral=True)
            return
        if self._game_is_active(ctx):
            await ctx.send("🐺 狼人殺進行中，不能控制遊戲音效。", ephemeral=True)
            return
        error = await self._controller_error(ctx.guild, ctx.author)
        if error:
            await ctx.send(error, ephemeral=True)
            return
        ok, message = await self._toggle_pause_action(
            ctx.guild, desired_paused=False
        )
        await ctx.send(message, ephemeral=not ok)

    @commands.hybrid_command(
        name="seek",
        description="跳轉目前歌曲的播放時間",
    )
    async def seek(self, ctx: commands.Context, *, position: str) -> None:
        if ctx.guild is None:
            await ctx.send("這個指令只能在伺服器內使用。", ephemeral=True)
            return
        if self._game_is_active(ctx):
            await ctx.send("🐺 狼人殺進行中，不能控制遊戲音效。", ephemeral=True)
            return
        error = await self._controller_error(ctx.guild, ctx.author)
        if error:
            await ctx.send(error, ephemeral=True)
            return
        try:
            target = parse_time_value(position)
        except ValueError as error:
            await ctx.send(f"❌ {error}", ephemeral=True)
            return
        ok, message = await self._seek_action(ctx.guild, target)
        await ctx.send(message, ephemeral=not ok)

    @commands.hybrid_command(name="stop", description="停止並清空佇列")
    async def stop(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.send("這個指令只能在伺服器內使用。", ephemeral=True)
            return
        if self._game_is_active(ctx):
            await ctx.send("🐺 狼人殺進行中，不能停止遊戲音效。", ephemeral=True)
            return
        if ctx.guild.voice_client and ctx.guild.voice_client.is_connected():
            error = await self._controller_error(ctx.guild, ctx.author)
            if error:
                await ctx.send(error, ephemeral=True)
                return
        ok, message = await self._stop_action(ctx.guild)
        await ctx.send(message, ephemeral=not ok)

    @commands.hybrid_command(name="queue", description="查看播放清單")
    async def queue(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.send("這個指令只能在伺服器內使用。", ephemeral=True)
            return
        embed = await self._queue_embed(ctx.guild)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="loop", description="切換循環模式")
    async def loop(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.send("這個指令只能在伺服器內使用。", ephemeral=True)
            return
        if self._game_is_active(ctx):
            await ctx.send("🐺 狼人殺進行中，不能變更循環模式。", ephemeral=True)
            return
        error = await self._controller_error(ctx.guild, ctx.author)
        if error:
            await ctx.send(error, ephemeral=True)
            return
        ok, message = await self._cycle_loop_action(ctx.guild)
        await ctx.send(message, ephemeral=not ok)

    @commands.hybrid_command(name="leave", description="讓機器人離開")
    async def leave(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.send("這個指令只能在伺服器內使用。", ephemeral=True)
            return
        if self._game_is_active(ctx):
            await ctx.send("🐺 狼人殺還沒結束，我不能離開。", ephemeral=True)
            return
        if ctx.guild.voice_client and ctx.guild.voice_client.is_connected():
            error = await self._controller_error(ctx.guild, ctx.author)
            if error:
                await ctx.send(error, ephemeral=True)
                return
        ok, message = await self._leave_action(ctx.guild)
        await ctx.send(message, ephemeral=not ok)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))
