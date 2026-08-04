from __future__ import annotations

import unittest
import uuid

from fastapi.testclient import TestClient

from activity_backend.app.auth import AuthError, DiscordAuth, DiscordIdentity
from activity_backend.app.application import ActivityBoardId
from activity_backend.app.main import app, auth
from activity_backend.app.services import build_mvp_board


class DiscordSessionTests(unittest.TestCase):
    def test_signed_session_round_trip_and_tamper_rejection(self) -> None:
        service = DiscordAuth(client_id="client", client_secret="secret", session_secret="session-secret")
        identity = DiscordIdentity("discord-user", "Moon Player")
        token = service.issue_session(identity)

        self.assertEqual(service.verify_session(token), identity)
        payload, signature = token.rsplit(".", 1)
        tampered_signature = ("a" if signature[0] != "a" else "b") + signature[1:]
        with self.assertRaises(AuthError):
            service.verify_session(f"{payload}.{tampered_signature}")


class BoardCompositionTests(unittest.TestCase):
    def test_selectable_boards_cover_three_to_twelve_players(self) -> None:
        for board_id in ActivityBoardId:
            for player_count in range(3, 13):
                board = build_mvp_board(player_count, board_id)
                self.assertEqual(len(board.role_ids), player_count)
                self.assertTrue(board.engine_enabled)
                self.assertGreaterEqual(sum(role.value == "werewolf" for role in board.role_ids), 1)

        with self.assertRaises(ValueError):
            build_mvp_board(2)
        with self.assertRaises(ValueError):
            build_mvp_board(13)
        with self.assertRaises(ValueError):
            build_mvp_board(6, "unknown")


class ActivityTransportTests(unittest.TestCase):
    def test_connect_and_websocket_ready_state_never_leak_discord_user_id(self) -> None:
        client = TestClient(app)
        suffix = uuid.uuid4().hex
        identity = DiscordIdentity(f"discord-{suffix}", "測試玩家")
        token = auth.issue_session(identity)
        context = {
            "instance_id": f"instance-{suffix}",
            "channel_id": f"channel-{suffix}",
            "guild_id": f"guild-{suffix}",
            "locale": "zh-TW",
        }
        response = client.post(
            "/api/rooms/connect",
            json=context,
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        snapshot = response.json()
        self.assertNotIn("discord_user_id", response.text)
        room_id = snapshot["room"]["room_id"]

        query = "&".join(
            [
                f"token={token}",
                f"instance_id={context['instance_id']}",
                f"channel_id={context['channel_id']}",
                f"guild_id={context['guild_id']}",
                "locale=zh-TW",
            ]
        )
        with client.websocket_connect(f"/ws/rooms/{room_id}?{query}") as socket:
            initial = socket.receive_json()
            self.assertEqual(initial["type"], "state")
            self.assertEqual(initial["payload"]["room"]["selected_board_id"], "classic")
            self.assertEqual(len(initial["payload"]["room"]["board_options"]), 3)
            socket.send_json(
                {
                    "type": "set_board",
                    "request_id": f"board-{suffix}",
                    "payload": {"board_id": "power"},
                }
            )
            board_result = socket.receive_json()
            board_updated = socket.receive_json()
            self.assertTrue(board_result["success"])
            self.assertEqual(board_updated["payload"]["room"]["selected_board_id"], "power")
            socket.send_json(
                {
                    "type": "set_ready",
                    "request_id": f"request-{suffix}",
                    "payload": {"ready": True},
                }
            )
            result = socket.receive_json()
            updated = socket.receive_json()
            self.assertTrue(result["success"])
            self.assertTrue(updated["payload"]["room"]["players"][0]["ready"])
            self.assertNotIn("discord_user_id", str(updated))


if __name__ == "__main__":
    unittest.main()
