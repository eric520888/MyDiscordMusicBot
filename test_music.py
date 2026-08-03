import unittest

from cogs.music import _auth_required_message


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


if __name__ == "__main__":
    unittest.main()
