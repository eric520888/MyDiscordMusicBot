import io
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, patch

import yt_dlp
from cogs import music

from cogs.music import _auth_required_message, _stream_transport_from_info


class MusicAuthMessageTests(unittest.TestCase):
    def test_missing_cookie_message_requests_configuration(self) -> None:
        message = _auth_required_message(cookie_rejected=False, icon="❌")

        self.assertIn("沒有可用的 Cookie", message)
        self.assertIn("YTDLP_COOKIES_B64", message)
        self.assertNotIn("YTDLP_COOKIES_FROM_BROWSER", message)

    def test_rejected_cookie_does_not_claim_expiration(self) -> None:
        message = _auth_required_message(cookie_rejected=True, icon="⚠️")

        self.assertIn("已讀取 Cookie", message)
        self.assertIn("IP", message)
        self.assertIn("YTDLP_PROXY", message)
        self.assertNotIn("請重新匯出", message)

    def test_expired_cookie_requests_fresh_export(self) -> None:
        message = _auth_required_message(
            cookie_rejected=True, cookie_expired=True, icon="⚠️"
        )

        self.assertIn("明確回報", message)
        self.assertIn("更新 `YTDLP_COOKIES_B64`", message)

    def test_cookie_usage_hint_is_not_proof_of_an_auth_failure(self) -> None:
        failure = music._classify_ytdlp_error(
            "HTTP Error 429. You may use --cookies-from-browser."
        )
        self.assertIs(failure, music.PlaybackFailure.RATE_LIMIT)

    def test_expired_cookie_warning_survives_final_format_error(self) -> None:
        failure = music._classify_ytdlp_error(
            "Your cookies are no longer valid. "
            "ERROR: Requested format is not available."
        )
        self.assertIs(failure, music.PlaybackFailure.COOKIE_EXPIRED)

    def test_bot_check_survives_final_format_error(self) -> None:
        failure = music._classify_ytdlp_error(
            "Sign in to confirm you're not a bot. "
            "ERROR: Requested format is not available."
        )
        self.assertIs(failure, music.PlaybackFailure.AUTH_REQUIRED)


class MusicLookupFallbackTests(unittest.TestCase):
    URL = "https://www.youtube.com/watch?v=tT7ZwzGFsCg"
    INFO = {
        "title": "test track",
        "webpage_url": URL,
        "duration": 23,
        "url": "https://rr1.example.googlevideo.com/videoplayback?expire=1900000000",
    }
    POT_ARGS = ("--extractor-args", "youtube:player_client=mweb,tv,web_safari")

    def setUp(self) -> None:
        self.calls = []
        self.auth = music.YTDLAuth(
            "test cookies", ("--cookies", "unused.txt"), cookiefile="unused.txt"
        )
        patches = (
            patch.dict("os.environ", {"YTDLP_PROXY": ""}),
            patch.object(music, "COOKIE_POT_YOUTUBE_ARGS", self.POT_ARGS),
            patch.object(music, "_prefer_low_resource_youtube", return_value=False),
            patch.object(music, "_configured_auth_candidates", return_value=[self.auth]),
            patch.object(music, "_create_cookie_snapshot", return_value="snapshot.txt"),
            patch.object(music, "_remove_cookie_snapshot"),
        )
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def extract(self, attempt):
        @contextmanager
        def fake_ydl(options):
            self.calls.append(options)
            yield SimpleNamespace(
                extract_info=lambda *_args, **_kwargs: attempt(options)
            )

        with patch.object(music.yt_dlp, "YoutubeDL", side_effect=fake_ydl):
            return music.Music._extract_track_sync(self.URL, 1, 2)

    @staticmethod
    def has_pot(options):
        return "youtubepot-bgutilscript" in options.get("extractor_args", {})

    def test_public_track_uses_anonymous_provider_before_cookies(self) -> None:
        track = self.extract(lambda options: dict(self.INFO))

        self.assertEqual(len(self.calls), 1)
        self.assertTrue(self.has_pot(self.calls[0]))
        self.assertNotIn("cookiefile", self.calls[0])
        self.assertIsNone(track.auth_label)
        self.assertEqual(track.ytdlp_extra_args, self.POT_ARGS)

    def test_cookie_provider_rejection_falls_back_to_authenticated_defaults(self) -> None:
        def attempt(options):
            if "cookiefile" not in options or self.has_pot(options):
                raise yt_dlp.utils.DownloadError("Sign in to confirm you're not a bot")
            return dict(self.INFO)

        track = self.extract(attempt)

        self.assertEqual(len(self.calls), 3)
        self.assertIn("cookiefile", self.calls[1])
        self.assertIn("cookiefile", self.calls[2])
        self.assertTrue(self.has_pot(self.calls[1]))
        self.assertFalse(self.has_pot(self.calls[2]))
        self.assertEqual(track.auth_label, self.auth.label)
        self.assertEqual(track.ytdlp_extra_args, music.NODE_YOUTUBE_ARGS)

    def test_expired_credentials_are_attempted_only_once(self) -> None:
        def attempt(options):
            if "cookiefile" in options:
                options["logger"].warning("Your cookies are no longer valid")
            raise yt_dlp.utils.DownloadError("Sign in to confirm you're not a bot")

        with self.assertRaises(music.TrackLookupError) as raised:
            self.extract(attempt)

        self.assertIs(raised.exception.failure, music.PlaybackFailure.COOKIE_EXPIRED)
        self.assertTrue(raised.exception.cookie_rejected)
        self.assertEqual(sum("cookiefile" in opts for opts in self.calls), 1)
        self.assertLessEqual(len(self.calls), 4)

    def test_auth_failures_have_a_finite_attempt_budget(self) -> None:
        def attempt(options):
            raise yt_dlp.utils.DownloadError("Sign in to confirm you're not a bot")

        with self.assertRaises(music.TrackLookupError) as raised:
            self.extract(attempt)

        self.assertIs(raised.exception.failure, music.PlaybackFailure.AUTH_REQUIRED)
        self.assertTrue(raised.exception.cookie_rejected)
        self.assertEqual(len(self.calls), 5)

    def test_proxy_is_used_during_metadata_extraction(self) -> None:
        with patch.dict("os.environ", {"YTDLP_PROXY": "http://proxy.example:3128"}):
            self.extract(lambda options: dict(self.INFO))
        self.assertEqual(self.calls[0]["proxy"], "http://proxy.example:3128")


class MusicProxyTransportTests(unittest.TestCase):
    def test_proxy_download_never_fetches_signed_url_directly(self) -> None:
        track = music.Track(
            title="test", webpage_url=MusicLookupFallbackTests.URL,
            duration=23, text_channel_id=1, requester_id=2,
            stream_url="https://rr1.example.googlevideo.com/videoplayback",
        )
        process = Mock(stdout=io.BytesIO(), returncode=0)
        process.poll.return_value = 0
        process.wait.return_value = 0
        audio = SimpleNamespace(
            _process=process, _current_error=None, cleanup=lambda: None
        )
        with (
            patch.dict("os.environ", {"YTDLP_PROXY": "http://proxy.example:3128"}),
            patch.object(music.subprocess, "Popen", return_value=process) as spawn,
            patch.object(music.discord, "FFmpegOpusAudio", return_value=audio) as ffmpeg,
        ):
            source = music.YTDLPipeAudio(track)
            try:
                command = spawn.call_args.args[0]
                self.assertEqual(command[command.index("--proxy") + 1],
                                 "http://proxy.example:3128")
                self.assertIs(ffmpeg.call_args.args[0], process.stdout)
                self.assertTrue(ffmpeg.call_args.kwargs["pipe"])
            finally:
                source.cleanup()

    def test_proxy_credentials_are_redacted_from_diagnostics(self) -> None:
        proxy = "http://username:password@proxy.example:3128"
        with patch.dict("os.environ", {"YTDLP_PROXY": proxy}):
            sanitized = music._sanitize_ytdlp_message(f"Proxy connection failed: {proxy}")
        self.assertNotIn("password", sanitized)
        self.assertNotIn("username", sanitized)


class StreamTransportTests(unittest.TestCase):
    def test_accepts_googlevideo_url_and_removes_secret_headers(self) -> None:
        url, headers, expires_at = _stream_transport_from_info(
            {
                "url": (
                    "https://rr1---sn.example.googlevideo.com/videoplayback"
                    "?expire=1900000000"
                ),
                "http_headers": {
                    "User-Agent": "yt-dlp-test",
                    "Cookie": "must-not-be-retained",
                    "Bad\nHeader": "ignored",
                },
            }
        )

        self.assertIsNotNone(url)
        self.assertEqual(headers, (("User-Agent", "yt-dlp-test"),))
        self.assertEqual(expires_at, 1900000000.0)

    def test_rejects_untrusted_stream_host(self) -> None:
        self.assertEqual(
            _stream_transport_from_info(
                {"url": "https://example.com/private-audio"}
            ),
            (None, (), None),
        )

if __name__ == "__main__":
    unittest.main()
