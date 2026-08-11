import unittest

from cogs.music import _auth_required_message, _stream_transport_from_info


class MusicAuthMessageTests(unittest.TestCase):
    def test_missing_cookie_message_requests_configuration(self) -> None:
        message = _auth_required_message(cookie_rejected=False, icon="❌")

        self.assertIn("沒有可用的 Cookie", message)
        self.assertIn("YTDLP_COOKIES_B64", message)
        self.assertNotIn("YTDLP_COOKIES_FROM_BROWSER", message)

    def test_rejected_cookie_message_requests_fresh_export(self) -> None:
        message = _auth_required_message(cookie_rejected=True, icon="⚠️")

        self.assertIn("已讀取 Cookie", message)
        self.assertIn("可能已過期", message)
        self.assertIn("更新 `YTDLP_COOKIES_B64`", message)
        self.assertNotIn("YTDLP_COOKIES_FROM_BROWSER", message)


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
