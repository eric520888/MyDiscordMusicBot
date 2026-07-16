"""狼人殺核心流程的離線回歸測試。"""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from cogs.werewolf_system.audio import AudioManager
from cogs.werewolf_system.const import (
    BOARD_AUTO,
    BOARD_MERCHANT,
    BOARD_MIN_PLAYERS,
    BOARD_STANDARD,
    BOARD_WOLF_KING,
    CAMP_GOD,
    CAMP_VILLAGER,
    CAMP_WOLF,
    PHASE_DAY,
    PHASE_ENDED,
    PHASE_NIGHT_1,
    PHASE_SHOOT,
    PHASE_STARTING,
    PHASE_WAITING,
)
from cogs.werewolf_system.game import WerewolfGame
from cogs.werewolf_system.replay import ReplayView
from cogs.werewolf_system.roles import (
    Hunter,
    Merchant,
    Player,
    Seer,
    Villager,
    Witch,
    Wolf,
)
from cogs.werewolf_system.views import MerchantSkillSelect, ShooterView


class FakeUser:
    def __init__(self, user_id, name=None):
        self.id = user_id
        self.display_name = name or f"Player {user_id}"
        self.mention = f"<@{user_id}>"
        self.voice = None


class FakeGuild:
    def __init__(self):
        self.id = 100
        self.voice_client = None

    def get_member(self, user_id):
        return None


class FakeChannel:
    def __init__(self):
        self.guild = FakeGuild()
        self.sent = []

    async def send(self, content=None, **kwargs):
        self.sent.append((content, kwargs))
        return None


class FakeBot:
    def __init__(self, owner_ids=()):
        self.owner_ids = set(owner_ids)

    async def is_owner(self, user):
        return user.id in self.owner_ids

    def get_cog(self, name):
        return None


class FakeResponse:
    def __init__(self):
        self.messages = []
        self.edits = []
        self.deferred = False

    async def send_message(self, content=None, **kwargs):
        self.messages.append((content, kwargs))

    async def edit_message(self, **kwargs):
        self.edits.append(kwargs)

    async def defer(self, **kwargs):
        self.deferred = True


class FakeFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, content=None, **kwargs):
        self.messages.append((content, kwargs))


class FakeInteraction:
    def __init__(self, user):
        self.user = user
        self.response = FakeResponse()
        self.followup = FakeFollowup()


def make_game(player_count=0):
    host = FakeUser(1, "Host")
    game = WerewolfGame(FakeBot(), FakeChannel(), host)
    game.players = [Player(FakeUser(i + 10), None) for i in range(player_count)]
    return game


class WerewolfRulesTests(unittest.TestCase):
    def test_each_board_minimum_creates_all_three_camps(self):
        for board_id in (
            BOARD_AUTO,
            BOARD_STANDARD,
            BOARD_WOLF_KING,
            BOARD_MERCHANT,
        ):
            with self.subTest(board=board_id):
                game = make_game(BOARD_MIN_PLAYERS[board_id])
                game.board_id = board_id
                self.assertTrue(game.assign_roles())
                camps = {player.role.camp for player in game.players}
                self.assertEqual(camps, {CAMP_WOLF, CAMP_GOD, CAMP_VILLAGER})

    def test_fixed_board_rejects_too_few_players(self):
        game = make_game(BOARD_MIN_PLAYERS[BOARD_MERCHANT] - 1)
        game.board_id = BOARD_MERCHANT
        self.assertFalse(game.assign_roles())

    def test_auto_board_scales_wolves_for_large_lobbies(self):
        game = make_game(20)
        game.board_id = BOARD_AUTO
        self.assertTrue(game.assign_roles())
        wolves = [p for p in game.players if p.role.camp == CAMP_WOLF]
        self.assertEqual(len(wolves), 20 // 3)

    def test_long_replay_stays_within_discord_select_limit(self):
        view = ReplayView([], [], "test", 50)
        self.assertEqual(len(view.children[0].options), 25)
        self.assertEqual(view.children[0].options[-1].value, "round_50")

    def test_shooter_can_still_skip_when_no_targets_remain(self):
        game = make_game()
        shooter = Player(FakeUser(10), Hunter())
        shooter.status = "dead"
        game.players = [shooter]
        view = ShooterView(game, shooter)
        self.assertEqual(len(view.children), 1)


class WerewolfInteractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_host_cannot_force_night(self):
        game = make_game()
        game.phase = PHASE_STARTING
        interaction = FakeInteraction(FakeUser(99, "Guest"))

        await game.force_night(interaction)

        self.assertEqual(game.phase, PHASE_STARTING)
        self.assertIn("只有房主", interaction.response.messages[0][0])

    async def test_non_host_cannot_close_lobby(self):
        game = make_game()
        interaction = FakeInteraction(FakeUser(99, "Guest"))

        await game.close_lobby(interaction)

        self.assertEqual(game.phase, PHASE_WAITING)
        self.assertFalse(interaction.response.edits)

    async def test_host_can_close_and_end_lobby(self):
        game = make_game()
        interaction = FakeInteraction(game.host)

        await game.close_lobby(interaction)

        self.assertEqual(game.phase, PHASE_ENDED)
        self.assertTrue(interaction.response.edits)

    async def test_merchant_target_continues_to_skill_selection(self):
        game = make_game()
        merchant = Player(FakeUser(10, "Merchant"), Merchant())
        target = Player(FakeUser(11, "Target"), Villager())
        wolf = Player(FakeUser(12, "Wolf"), Wolf())
        game.players = [merchant, target, wolf]
        game.phase = PHASE_NIGHT_1
        interaction = FakeInteraction(merchant.user)

        await game.handle_night_action(
            interaction,
            merchant,
            "merchant_give",
            target.id,
        )

        view = interaction.response.messages[0][1]["view"]
        self.assertIsInstance(view.children[0], MerchantSkillSelect)

        game.check_phase_1_end = AsyncMock()
        skill_interaction = FakeInteraction(merchant.user)
        await game.handle_merchant_skill(
            skill_interaction,
            merchant,
            target.id,
            "guard",
        )
        self.assertTrue(merchant.role.used_skill)
        self.assertEqual(game.lucky_data["user_id"], target.id)
        self.assertEqual(game.lucky_data["skill"], "guard")

    async def test_stale_vote_panel_cannot_vote_at_night(self):
        game = make_game()
        voter = Player(FakeUser(10), Villager())
        target = Player(FakeUser(11), Wolf())
        game.players = [voter, target]
        game.phase = PHASE_NIGHT_1
        interaction = FakeInteraction(voter.user)

        await game.handle_vote(interaction, target.id)

        self.assertEqual(game.votes, {})
        self.assertIn("已失效", interaction.response.messages[0][0])

    async def test_non_shooter_cannot_fire_for_shooter(self):
        game = make_game()
        shooter = Player(FakeUser(10, "Hunter"), Hunter())
        shooter.status = "dead"
        intruder = Player(FakeUser(11, "Intruder"), Villager())
        target = Player(FakeUser(12, "Target"), Wolf())
        game.players = [shooter, intruder, target]
        game.phase = PHASE_SHOOT
        game.pending_shooters = [shooter.id]
        interaction = FakeInteraction(intruder.user)

        await game.handle_shoot(interaction, shooter, target.id)

        self.assertEqual(target.status, "alive")
        self.assertIn("槍手本人", interaction.response.messages[0][0])

    async def test_new_night_recreates_wolf_thread(self):
        game = make_game()
        game.players = [
            Player(FakeUser(10), Wolf()),
            Player(FakeUser(11), Villager()),
        ]
        game.phase = PHASE_DAY
        game.create_wolf_thread = AsyncMock()

        with (
            patch.object(AudioManager, "play_mixed", new=AsyncMock()),
            patch.object(game, "_mute_for_night", new=AsyncMock()),
        ):
            started = await game.start_night()
            await asyncio.sleep(0)

        self.assertTrue(started)
        game.create_wolf_thread.assert_awaited_once()

    async def test_night_actions_reach_day_and_finish_game(self):
        game = make_game()
        wolf = Player(FakeUser(10, "Wolf"), Wolf())
        seer = Player(FakeUser(11, "Seer"), Seer())
        villager = Player(FakeUser(12, "Villager"), Villager())
        game.players = [wolf, seer, villager]
        game.phase = PHASE_NIGHT_1
        game.round_num = 1

        await game.handle_night_action(
            FakeInteraction(wolf.user),
            wolf,
            "wolf_kill",
            villager.id,
        )
        await game.handle_night_action(
            FakeInteraction(seer.user),
            seer,
            "seer_check",
            wolf.id,
        )

        self.assertEqual(villager.status, "dead")
        self.assertEqual(game.phase, PHASE_ENDED)
        self.assertTrue(
            any(event["event_type"] == "night_death" for event in game.game_log)
        )

    async def test_witch_with_no_potions_does_not_block_night(self):
        game = make_game()
        wolf = Player(FakeUser(10), Wolf())
        witch = Player(FakeUser(11), Witch())
        witch.role.has_antidote = False
        witch.role.has_poison = False
        villager = Player(FakeUser(12), Villager())
        game.players = [wolf, witch, villager]
        game.phase = PHASE_NIGHT_1

        await game.start_night_phase_2()

        self.assertEqual(game.phase, PHASE_DAY)


if __name__ == "__main__":
    unittest.main()
