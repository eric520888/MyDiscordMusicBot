"""Check the real extraction and audio pipeline without logging in to Discord."""

import argparse
import importlib.metadata
import json
import logging
import os
import time

from cogs.music import (
    COOKIE_POT_YOUTUBE_ARGS,
    LOW_RESOURCE_YOUTUBE_ARGS,
    Music,
    PlaybackFailure,
    TrackLookupError,
    YTDLPipeAudio,
    _classify_ytdlp_error,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Public YouTube video to check")
    args = parser.parse_args()
    # Only structured, non-secret diagnostics leave this process. In
    # particular, do not print signed URLs, cookies or proxy credentials.
    logging.disable(logging.CRITICAL)
    result = {
        "yt_dlp": importlib.metadata.version("yt-dlp"),
        "cookie_configured": any(
            os.getenv(key) for key in ("YTDLP_COOKIE_FILE", "YTDLP_COOKIES_B64")
        ),
        "proxy_configured": bool(os.getenv("YTDLP_PROXY", "").strip()),
    }
    try:
        result["provider"] = importlib.metadata.version("bgutil-ytdlp-pot-provider")
    except importlib.metadata.PackageNotFoundError:
        result["provider"] = None
    source = None
    started = time.monotonic()
    exit_code = 0
    try:
        track = Music._extract_track_sync(args.url, 0, 0)
        result["metadata_seconds"] = round(time.monotonic() - started, 2)
        result["used_cookie"] = bool(track.auth_label)
        result["profile"] = (
            "po_token" if COOKIE_POT_YOUTUBE_ARGS and
            track.ytdlp_extra_args == COOKIE_POT_YOUTUBE_ARGS else
            "low_resource" if track.ytdlp_extra_args == LOW_RESOURCE_YOUTUBE_ARGS else
            "default"
        )
        source = YTDLPipeAudio(track)
        packets = [source.read() for _ in range(10)]
        result["audio_bytes"] = sum(map(len, packets))
        result["audio_started"] = source.produced_audio
        source.cleanup()
        if source.failed or not source.produced_audio:
            result["status"] = "audio_failed"
            result["failure"] = _classify_ytdlp_error(source.error_summary).name
            exit_code = 3
        else:
            result["status"] = "ok"
    except TrackLookupError as error:
        result["status"] = "lookup_failed"
        result["failure"] = error.failure.name
        result["cookie_rejected"] = error.cookie_rejected
        result["cookie_expired"] = error.failure is PlaybackFailure.COOKIE_EXPIRED
        exit_code = 2
    except Exception as error:
        result["status"] = "error"
        result["error_type"] = type(error).__name__
        exit_code = 4
    finally:
        if source is not None:
            source.cleanup()
        result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    print(json.dumps(result, ensure_ascii=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
