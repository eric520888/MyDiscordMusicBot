import io
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

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

    def test_ffmpeg_forbidden_response_is_not_rate_limiting(self) -> None:
        for message in (
            "HTTP Error 403: Forbidden",
            "HTTP error 403 Forbidden",
            "Server returned 403 Forbidden (access denied)",
            "status code 403",
        ):
            with self.subTest(message=message):
                self.assertIs(
                    music._classify_ytdlp_error(message),
                    music.PlaybackFailure.MEDIA_FORBIDDEN,
                )


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
        validator = patch.object(music, "_validate_audio_stream")
        self.validator = validator.start()
        self.addCleanup(validator.stop)

    def extract(self, attempt):
        @contextmanager
        def fake_ydl(options):
            self.calls.append(options)
            yield SimpleNamespace(
                extract_info=lambda *_args, **_kwargs: attempt(options),
                params=options,
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

    def test_cdn_rejection_uses_cookie_before_voice_connection(self) -> None:
        def validate(ydl, info):
            if "cookiefile" not in ydl.params:
                raise yt_dlp.utils.DownloadError("Audio validation failed: HTTP Error 403")

        self.validator.side_effect = validate
        track = self.extract(lambda options: dict(self.INFO))

        self.assertEqual(len(self.calls), 2)
        self.assertNotIn("cookiefile", self.calls[0])
        self.assertIn("cookiefile", self.calls[1])
        self.assertEqual(track.auth_label, self.auth.label)
        self.assertEqual(self.validator.call_count, 2)

    def test_search_generator_is_not_consumed_twice(self) -> None:
        track = self.extract(lambda options: {"entries": iter([dict(self.INFO)])})

        self.assertEqual(track.title, self.INFO["title"])
        self.validator.assert_called_once()


class AudioStreamValidationTests(unittest.TestCase):
    INFO = {
        "url": "https://rr1.example.googlevideo.com/videoplayback?signature=private-signature",
        "http_headers": {"User-Agent": "test", "Cookie": "private-cookie"},
    }

    def test_reads_one_byte_without_forwarding_secret_headers(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"x"
        ydl = Mock()
        ydl.urlopen.return_value = response

        music._validate_audio_stream(ydl, self.INFO)

        request = ydl.urlopen.call_args.args[0]
        self.assertEqual(request.headers["Range"], "bytes=0-0")
        self.assertNotIn("Cookie", request.headers)
        response.read.assert_called_once_with(1)

    def test_http_failure_closes_connection_and_preserves_status(self) -> None:
        for status, expected in (
            (403, music.PlaybackFailure.MEDIA_FORBIDDEN),
            (429, music.PlaybackFailure.RATE_LIMIT),
        ):
            with self.subTest(status=status):
                response = SimpleNamespace(status=status, reason="rejected", close=Mock())
                ydl = Mock()
                ydl.urlopen.side_effect = music.HTTPError(response)

                with self.assertRaises(yt_dlp.utils.DownloadError) as raised:
                    music._validate_audio_stream(ydl, self.INFO)

                response.close.assert_called_once()
                self.assertIs(music._classify_ytdlp_error(str(raised.exception)), expected)
                self.assertNotIn("private-signature", str(raised.exception))

    def test_empty_response_is_a_retryable_network_failure(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b""
        ydl = Mock()
        ydl.urlopen.return_value = response

        with self.assertRaises(yt_dlp.utils.DownloadError) as raised:
            music._validate_audio_stream(ydl, self.INFO)

        self.assertIs(
            music._classify_ytdlp_error(str(raised.exception)), music.PlaybackFailure.NETWORK
        )

    def test_untrusted_media_host_is_never_requested(self) -> None:
        ydl = Mock()
        music._validate_audio_stream(ydl, {"url": "https://example.com/private"})
        ydl.urlopen.assert_not_called()


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
                self.assertEqual(command[command.index("--http-chunk-size") + 1], "1M")
            finally:
                source.cleanup()

    def test_proxy_credentials_are_redacted_from_diagnostics(self) -> None:
        proxy = "http://username:password@proxy.example:3128"
        with patch.dict("os.environ", {"YTDLP_PROXY": proxy}):
            sanitized = music._sanitize_ytdlp_message(f"Proxy connection failed: {proxy}")
        self.assertNotIn("password", sanitized)
        self.assertNotIn("username", sanitized)

    def test_signed_media_urls_are_redacted_from_diagnostics(self) -> None:
        message = music._sanitize_ytdlp_message(
            "HTTP error 403 https://rr1.example.googlevideo.com/videoplayback"
            "?signature=private-token Error opening input"
        )
        self.assertNotIn("private-token", message)
        self.assertIn("HTTP error 403", message)


class RangeAudioReaderTests(unittest.TestCase):
    URL = "https://rr1.example.googlevideo.com/videoplayback?signature=private-token"

    @staticmethod
    def response(data: bytes, content_range: str | None = None) -> io.BytesIO:
        response = io.BytesIO(data)
        response.status = 206 if content_range else 200
        response.headers = {"Content-Range": content_range} if content_range else {}
        return response

    def test_downloads_contiguous_ranges_and_stops_at_total(self) -> None:
        responses = [
            self.response(b"abcd", "bytes 0-3/10"),
            self.response(b"efgh", "bytes 4-7/10"),
            self.response(b"ij", "bytes 8-9/10"),
        ]
        ydl = Mock()
        ydl.urlopen.side_effect = responses
        with (
            patch.object(music.yt_dlp, "YoutubeDL", return_value=ydl) as factory,
            patch.object(music._RangeAudioReader, "CHUNK_SIZE", 4),
        ):
            reader = music._RangeAudioReader(self.URL, (("Cookie", "private"),))
            self.assertEqual(b"".join(reader.read(2) for _ in range(5)), b"abcdefghij")
            self.assertEqual(reader.read(2), b"")
            reader.close()
            reader.close()
            self.assertEqual(reader.read(2), b"")

        requests = [call.args[0] for call in ydl.urlopen.call_args_list]
        self.assertEqual([r.headers["Range"] for r in requests],
                         ["bytes=0-3", "bytes=4-7", "bytes=8-9"])
        self.assertTrue(all("Cookie" not in r.headers for r in requests))
        self.assertTrue(all(r.headers["Accept-Encoding"] == "identity" for r in requests))
        self.assertEqual(factory.call_args.args[0]["source_address"], "0.0.0.0")
        self.assertTrue(all(response.closed for response in responses))
        ydl.close.assert_called_once()

    def test_full_response_is_not_downloaded_again_after_eof(self) -> None:
        response = self.response(b"abc")
        ydl = Mock()
        ydl.urlopen.return_value = response
        with patch.object(music.yt_dlp, "YoutubeDL", return_value=ydl):
            reader = music._RangeAudioReader(self.URL, ())
            try:
                self.assertEqual(reader.read(10), b"abc")
                self.assertEqual(reader.read(10), b"")
                self.assertEqual(reader.read(10), b"")
                ydl.urlopen.assert_called_once()
            finally:
                reader.close()

    def test_invalid_initial_range_closes_transport(self) -> None:
        response = self.response(b"abcd", "bytes 1-4/10")
        ydl = Mock()
        ydl.urlopen.return_value = response
        with patch.object(music.yt_dlp, "YoutubeDL", return_value=ydl):
            with self.assertRaises(yt_dlp.utils.DownloadError) as raised:
                music._RangeAudioReader(self.URL, ())
        self.assertNotIn("private-token", str(raised.exception))
        self.assertTrue(response.closed)
        ydl.close.assert_called_once()

    def test_forbidden_next_range_is_reported_without_repeating(self) -> None:
        response = self.response(b"abcd", "bytes 0-3/10")
        denied = SimpleNamespace(status=403, reason="rejected", close=Mock())
        ydl = Mock()
        ydl.urlopen.side_effect = [response, music.HTTPError(denied)]
        with (
            patch.object(music.yt_dlp, "YoutubeDL", return_value=ydl),
            patch.object(music._RangeAudioReader, "CHUNK_SIZE", 4),
        ):
            reader = music._RangeAudioReader(self.URL, ())
            try:
                self.assertEqual(reader.read(4), b"abcd")
                self.assertEqual(reader.read(4), b"")
                self.assertEqual(reader.read(4), b"")
                self.assertIs(music._classify_ytdlp_error(reader.error_summary),
                              music.PlaybackFailure.MEDIA_FORBIDDEN)
                self.assertEqual(ydl.urlopen.call_count, 2)
                denied.close.assert_called_once()
            finally:
                reader.close()

    def test_empty_range_does_not_loop_forever(self) -> None:
        ydl = Mock()
        ydl.urlopen.return_value = self.response(b"", "bytes 0-3/10")
        with patch.object(music.yt_dlp, "YoutubeDL", return_value=ydl):
            reader = music._RangeAudioReader(self.URL, ())
            try:
                self.assertEqual(reader.read(4), b"")
                self.assertIs(music._classify_ytdlp_error(reader.error_summary),
                              music.PlaybackFailure.NETWORK)
                ydl.urlopen.assert_called_once()
            finally:
                reader.close()

    def test_stop_during_read_does_not_become_a_network_failure(self) -> None:
        response = Mock(status=200, headers={})
        ydl = Mock()
        ydl.urlopen.return_value = response
        with patch.object(music.yt_dlp, "YoutubeDL", return_value=ydl):
            reader = music._RangeAudioReader(self.URL, ())
            def stop_during_read(size):
                reader.close()
                raise OSError("closed by stop")
            response.read.side_effect = stop_during_read
            self.assertEqual(reader.read(8), b"")
            self.assertEqual(reader.error_summary, "")
            ydl.close.assert_called_once()


class RangedAudioPipelineTests(unittest.TestCase):
    def test_reuses_media_url_and_seeks_after_pipe_input(self) -> None:
        track = music.Track(
            title="test", webpage_url=MusicLookupFallbackTests.URL,
            duration=23, text_channel_id=1, requester_id=2, start_at=5,
            stream_url=RangeAudioReaderTests.URL,
        )
        reader = Mock(error_summary="")
        process = Mock()
        process.poll.return_value = 0
        audio = SimpleNamespace(_process=process, _current_error=None, cleanup=Mock())
        with (
            patch.dict("os.environ", {"YTDLP_PROXY": ""}),
            patch.object(music, "_RangeAudioReader", return_value=reader) as factory,
            patch.object(music.subprocess, "Popen") as spawn,
            patch.object(music.discord, "FFmpegOpusAudio", return_value=audio) as ffmpeg,
        ):
            source = music.YTDLPipeAudio(track)
            source.cleanup()
            source.cleanup()
        factory.assert_called_once_with(track.stream_url, ())
        spawn.assert_not_called()
        self.assertIs(ffmpeg.call_args.args[0], reader)
        self.assertTrue(ffmpeg.call_args.kwargs["pipe"])
        self.assertIn("-ss 5.000", ffmpeg.call_args.kwargs["options"])
        self.assertNotIn("before_options", ffmpeg.call_args.kwargs)
        reader.close.assert_called_once()
        self.assertFalse(source.failed)

    def test_range_failure_marks_audio_pipeline_failed(self) -> None:
        track = music.Track(
            title="test", webpage_url=MusicLookupFallbackTests.URL,
            duration=23, text_channel_id=1, requester_id=2,
            stream_url=RangeAudioReaderTests.URL,
        )
        reader = Mock(error_summary="Audio download failed: HTTP Error 403")
        process = Mock()
        process.poll.return_value = 0
        audio = SimpleNamespace(_process=process, _current_error=None, cleanup=Mock())
        with (
            patch.dict("os.environ", {"YTDLP_PROXY": ""}),
            patch.object(music, "_RangeAudioReader", return_value=reader),
            patch.object(music.discord, "FFmpegOpusAudio", return_value=audio),
        ):
            source = music.YTDLPipeAudio(track)
            with self.assertLogs("cogs.music", level="WARNING"):
                source.cleanup()
        self.assertTrue(source.failed)
        self.assertIs(music._classify_ytdlp_error(source.error_summary),
                      music.PlaybackFailure.MEDIA_FORBIDDEN)


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
