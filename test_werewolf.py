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
    BOARD_SPECS,
    OFFICIAL_BOARD_IDS,
    BOARD_AWAKENED_WOLF_KING,
    BOARD_FRAGRANCE_FATE,
    ROLE_HUNTER,
    ROLE_MERCHANT,
)
from cogs.werewolf_system.game import WerewolfGame
from cogs.werewolf_bot import WerewolfBot
from cogs.werewolf_system.replay import ReplayView
from cogs.werewolf_system.roles import (
    Hunter,
    AwakenedFool,
    AwakenedWolfKing,
    AwakenedHunter,
    AwakenedWolfBeauty,
    AwakenedDreamer,
    AwakenedGargoyle,
    AwakenedGuard,
    AwakenedHiddenWolf,
    AwakenedLonelyGirl,
    AwakenedWhiteWolfKing,
    DayScholar,
    EclipseMaid,
    EvilKnight,
    Fool,
    FragrancePhantom,
    Gargoyle,
    Guard,
    Merchant,
    Player,
    Seer,
    PureWhite,
    Villager,
    Witch,
    Wolf,
    WolfKing,
)
from cogs.werewolf_system.views import (
    BoardRulesView,
    BoardSelect,
    DayActionSelect,
    MerchantSkillSelect,
    ShooterView,
    VotingView,
    create_board_rules_embed,
    create_game_status_embed,
)


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


class FakeLobbyMessage:
    def __init__(self, jump_url="https://discord.test/lobby"):
        self.jump_url = jump_url
        self.edits = []

    async def edit(self, **kwargs):
        self.edits.append(kwargs)


class FakeContext:
    def __init__(self, channel=None, author=None):
        self.channel = channel or FakeChannel()
        self.guild = self.channel.guild
        self.author = author or FakeUser(1, "Host")
        self.sent = []
        self.messages = []

    async def send(self, content=None, **kwargs):
        message = FakeLobbyMessage()
        self.sent.append((content, kwargs, message))
        return message


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


class WerewolfCogTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_recovers_deleted_waiting_lobby(self):
        bot = FakeBot()
        cog = WerewolfBot(bot)
        ctx = FakeContext()
        game = WerewolfGame(bot, ctx.channel, ctx.author)
        game.players = [Player(FakeUser(10), None)]
        game.lobby_message = None
        cog.games[ctx.guild.id] = game

        await cog.create_game.callback(cog, ctx)

        self.assertIsNotNone(game.lobby_message)
        self.assertIs(game.channel, ctx.channel)
        self.assertIn("embed", ctx.sent[0][1])
        self.assertIn("已保留玩家名單", ctx.sent[1][0])

    async def test_create_refreshes_existing_waiting_lobby_with_link(self):
        bot = FakeBot()
        cog = WerewolfBot(bot)
        ctx = FakeContext()
        game = WerewolfGame(bot, ctx.channel, ctx.author)
        message = FakeLobbyMessage()
        game.lobby_message = message
        cog.games[ctx.guild.id] = game

        await cog.create_game.callback(cog, ctx)

        self.assertTrue(message.edits)
        self.assertEqual(len(ctx.sent), 1)
        self.assertIn("前往大廳", ctx.sent[0][0])


class WerewolfRulesTests(unittest.TestCase):
    def test_all_official_boards_are_fixed_twelve_player_compositions(self):
        self.assertEqual(len(OFFICIAL_BOARD_IDS), 23)
        for board_id, spec in BOARD_SPECS.items():
            with self.subTest(board=board_id):
                self.assertEqual(len(spec.roles), 12)
                game = make_game(12)
                game.board_id = board_id
                self.assertTrue(game.assign_roles())
                self.assertCountEqual(
                    [player.role.name for player in game.players],
                    spec.roles,
                )

    def test_official_board_rejects_non_twelve_player_lobby(self):
        for count in (11, 13):
            with self.subTest(count=count):
                game = make_game(count)
                game.board_id = OFFICIAL_BOARD_IDS[0]
                self.assertFalse(game.assign_roles())

    def test_official_board_selects_fit_discord_limit(self):
        self.assertEqual(len(BoardSelect(make_game()).options), 24)
        self.assertEqual(len(BoardRulesView().children[0].options), 23)

    def test_awakened_wolf_king_uses_official_merchant_composition(self):
        roles = BOARD_SPECS[BOARD_AWAKENED_WOLF_KING].roles
        self.assertIn(ROLE_MERCHANT, roles)
        self.assertNotIn(ROLE_HUNTER, roles)

    def test_fragrance_phantom_learns_one_random_wolf(self):
        game = make_game(12)
        game.board_id = BOARD_FRAGRANCE_FATE
        self.assertTrue(game.assign_roles())
        phantom = game.get_players_by_role(FragrancePhantom)[0]
        known = game.get_player(phantom.role.state["known_wolf_id"])
        self.assertEqual(known.role.camp, CAMP_WOLF)
        self.assertNotEqual(known.id, phantom.id)

    def test_awakened_gargoyle_can_only_choose_adjacent_players(self):
        game = make_game()
        left = Player(FakeUser(10), Villager())
        gargoyle = Player(FakeUser(11), AwakenedGargoyle())
        right = Player(FakeUser(12), Wolf())
        far = Player(FakeUser(13), Seer())
        game.players = [left, gargoyle, right, far]
        targets = game.get_action_targets(gargoyle, "convert")
        self.assertEqual({target.id for target in targets}, {left.id, right.id})

    def test_visual_embeds_show_board_and_live_status(self):
        game = make_game(3)
        game.board_id = BOARD_STANDARD
        rules = create_board_rules_embed(BOARD_STANDARD)
        status = create_game_status_embed(game)
        self.assertIn("12 人官方板型", rules.description)
        self.assertIn("即時戰況", status.title)
        self.assertTrue(any(field.name == "📜 板子" for field in status.fields))

    def test_twenty_player_vote_panel_stays_within_discord_limits(self):
        game = make_game(20)
        for player in game.players:
            player.role = Villager()
        view = VotingView(game)
        self.assertEqual(len(view.children), 21)
        self.assertIsInstance(view.children[-1], DayActionSelect)

    def test_wolf_cannot_target_wolf_teammate(self):
        game = make_game()
        wolf = Player(FakeUser(10), Wolf())
        wolf_king = Player(FakeUser(11), WolfKing())
        villager = Player(FakeUser(12), Villager())
        game.players = [wolf, wolf_king, villager]
        targets = game.get_action_targets(wolf, "wolf_kill")
        self.assertEqual([target.id for target in targets], [villager.id])

    def test_wolf_team_can_choose_awakened_self_kill_role(self):
        game = make_game()
        wolf = Player(FakeUser(10), Wolf())
        gargoyle = Player(FakeUser(11), AwakenedGargoyle())
        villager = Player(FakeUser(12), Villager())
        game.players = [wolf, gargoyle, villager]
        targets = game.get_action_targets(wolf, "wolf_kill")
        self.assertEqual({target.id for target in targets}, {gargoyle.id, villager.id})
        self.assertFalse(AwakenedWolfBeauty().can_self_destruct)

    def test_isolated_wolf_joins_kill_only_after_regular_wolves_die(self):
        game = make_game()
        wolf = Player(FakeUser(10), Wolf())
        gargoyle = Player(FakeUser(11), Gargoyle())
        villager = Player(FakeUser(12), Villager())
        game.players = [wolf, gargoyle, villager]
        self.assertEqual(game.get_active_wolves(), [wolf])
        wolf.status = "dead"
        self.assertEqual(game.get_active_wolves(), [gargoyle])

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
    async def test_awakened_hidden_wolf_mimics_while_pack_is_alive(self):
        game = make_game()
        hidden = Player(FakeUser(10), AwakenedHiddenWolf())
        wolf = Player(FakeUser(11), Wolf())
        seer = Player(FakeUser(12), Seer())
        villager = Player(FakeUser(13), Villager())
        game.players = [hidden, wolf, seer, villager]
        game.phase = PHASE_NIGHT_1
        game.round_num = 1

        self.assertTrue(game._role_action_available(hidden))
        game.check_phase_1_end = AsyncMock()
        interaction = FakeInteraction(hidden.user)
        await game.handle_night_action(interaction, hidden, "mimic", seer.id)

        self.assertIn("預言家", interaction.response.messages[0][0])

    async def test_supported_wolf_can_self_destruct_during_day(self):
        game = make_game()
        actor = Player(FakeUser(10), Wolf())
        teammate = Player(FakeUser(11), Wolf())
        seer = Player(FakeUser(12), Seer())
        villagers = [Player(FakeUser(i), Villager()) for i in range(13, 15)]
        game.players = [actor, teammate, seer, *villagers]
        game.phase = PHASE_DAY

        with patch.object(game, "start_night", new=AsyncMock(return_value=True)):
            await game.handle_wolf_self_destruct(FakeInteraction(actor.user))

        self.assertEqual(actor.status, "dead")

    async def test_awakened_gargoyle_converts_and_reveals_target_next_night(self):
        game = make_game()
        gargoyle = Player(FakeUser(10), AwakenedGargoyle())
        target = Player(FakeUser(11), Seer())
        wolf = Player(FakeUser(12), Wolf())
        witch = Player(FakeUser(13), Witch())
        villagers = [Player(FakeUser(i), Villager()) for i in range(14, 17)]
        game.players = [gargoyle, target, wolf, witch, *villagers]
        game.phase = PHASE_NIGHT_1
        game.round_num = 1
        game.wolf_target = -1
        game.role_actions[(gargoyle.id, "convert")] = {
            "type": "convert", "target": target.id, "mode": None
        }

        await game.start_day()

        self.assertEqual(target.role.camp, CAMP_WOLF)
        self.assertTrue(target.role.isolated_wolf)
        self.assertFalse(target.role.joins_wolf_vote)
        self.assertTrue(target.role.disabled)

        game.create_wolf_thread = AsyncMock()
        with (
            patch.object(AudioManager, "play_mixed", new=AsyncMock()),
            patch.object(game, "_mute_for_night", new=AsyncMock()),
        ):
            await game.start_night()

        self.assertFalse(target.role.isolated_wolf)
        self.assertTrue(target.role.joins_wolf_vote)

    async def test_awakened_lonely_girl_transforms_when_idol_is_exiled(self):
        game = make_game()
        girl = Player(FakeUser(10), AwakenedLonelyGirl())
        idol = Player(FakeUser(11), Villager())
        girl.role.state["idol_id"] = idol.id
        game.players = [girl, idol]

        game._mark_day_death(idol, "投票處決")

        self.assertEqual(girl.role.camp, CAMP_WOLF)
        self.assertTrue(girl.role.joins_wolf_vote)

    async def test_awakened_lonely_girl_inherits_non_exiled_idol(self):
        game = make_game()
        girl = Player(FakeUser(10), AwakenedLonelyGirl())
        idol = Player(FakeUser(11), Seer())
        girl.role.state["idol_id"] = idol.id
        game.players = [girl, idol]

        game._mark_day_death(idol, "狼人殺害")

        self.assertIsInstance(girl.role, Seer)
        self.assertEqual(girl.role.camp, CAMP_GOD)

    async def test_awakened_guard_blocks_all_night_damage(self):
        game = make_game()
        guard = Player(FakeUser(10), AwakenedGuard())
        target = Player(FakeUser(11), Villager())
        wolf = Player(FakeUser(12), Wolf())
        seer = Player(FakeUser(13), Seer())
        game.players = [guard, target, wolf, seer]
        game.phase = PHASE_NIGHT_1
        game.round_num = 1
        game.wolf_target = target.id
        game.role_actions[(guard.id, "awakened_guard")] = {
            "type": "awakened_guard", "target": target.id, "mode": None
        }

        await game.start_day()

        self.assertEqual(target.status, "alive")
        self.assertEqual(game.awakened_guard_target, target.id)

    async def test_awakened_fool_guard_falls_back_to_self(self):
        game = make_game()
        fool = Player(FakeUser(10), AwakenedFool())
        fool.role.secret_body = True
        protected = Player(FakeUser(11), Villager())
        wolf = Player(FakeUser(12), Wolf())
        seer = Player(FakeUser(13), Seer())
        game.players = [fool, protected, wolf, seer]
        game.phase = PHASE_NIGHT_1
        game.round_num = 1
        game.wolf_target = fool.id
        game.role_actions[(fool.id, "secret_guard")] = {
            "type": "secret_guard", "target": protected.id, "mode": None
        }

        await game.start_day()

        self.assertEqual(fool.status, "alive")
        self.assertFalse(fool.role.secret_body)

    async def test_awakened_white_wolf_induction_eliminates_two_players(self):
        game = make_game()
        white_wolf = Player(FakeUser(10), AwakenedWhiteWolfKing())
        bomber = Player(FakeUser(11), Villager())
        companion = Player(FakeUser(12), Seer())
        other = Player(FakeUser(13), Villager())
        game.players = [white_wolf, bomber, companion, other]
        game.phase = PHASE_DAY
        game.pending_awakened_white_wolf = {
            "wolf_id": white_wolf.id, "bomber_id": bomber.id
        }

        with patch.object(game, "start_night", new=AsyncMock(return_value=True)):
            await game._finish_awakened_white_wolf(bomber, companion)

        self.assertEqual(bomber.status, "dead")
        self.assertEqual(companion.status, "dead")

    async def test_awakened_dreamer_protects_dream_speaker(self):
        game = make_game()
        dreamer = Player(FakeUser(10), AwakenedDreamer())
        target = Player(FakeUser(11), Seer())
        wolf = Player(FakeUser(12), Wolf())
        villagers = [Player(FakeUser(i), Villager()) for i in range(13, 15)]
        game.players = [dreamer, target, wolf, *villagers]
        game.phase = PHASE_NIGHT_1
        game.round_num = 1
        game.wolf_target = target.id
        game.role_actions[(dreamer.id, "dream_speech")] = {
            "type": "dream_speech", "target": target.id, "mode": None
        }

        await game.start_day()

        self.assertEqual(target.status, "alive")
        self.assertFalse(dreamer.role.state["last_dream_acted"])

    async def test_awakened_dreamer_can_eliminate_from_second_night(self):
        game = make_game()
        dreamer = Player(FakeUser(10), AwakenedDreamer())
        target = Player(FakeUser(11), Villager())
        wolf = Player(FakeUser(12), Wolf())
        seer = Player(FakeUser(13), Seer())
        villager = Player(FakeUser(14), Villager())
        game.players = [dreamer, target, wolf, seer, villager]
        game.phase = PHASE_NIGHT_1
        game.round_num = 2
        game.wolf_target = -1
        game.role_actions[(dreamer.id, "dream_speech")] = {
            "type": "dream_speech", "target": target.id, "mode": None
        }

        with patch.object(
            game,
            "_collect_awakened_dreamer_kills",
            new=AsyncMock(return_value={target.id}),
        ):
            await game.start_day()

        self.assertEqual(target.status, "dead")

    async def test_time_wave_boost_gives_wolves_second_kill(self):
        game = make_game()
        scholar = Player(FakeUser(10), DayScholar())
        wolf_a = Player(FakeUser(11), Wolf())
        wolf_b = Player(FakeUser(12), Wolf())
        villager_a = Player(FakeUser(13), Villager())
        villager_b = Player(FakeUser(14), Villager())
        seer = Player(FakeUser(15), Seer())
        game.players = [scholar, wolf_a, wolf_b, villager_a, villager_b, seer]
        game.phase = PHASE_NIGHT_1
        game.round_num = 2

        await game.handle_night_action(
            FakeInteraction(scholar.user),
            scholar,
            "time_wave",
            wolf_a.id,
            mode="boost",
        )
        for wolf in (wolf_a, wolf_b):
            await game.handle_night_action(
                FakeInteraction(wolf.user),
                wolf,
                "wolf_kill",
                [villager_a.id, villager_b.id],
            )
        await game.handle_night_action(
            FakeInteraction(seer.user), seer, "seer_check", wolf_a.id
        )

        self.assertEqual(villager_a.status, "dead")
        self.assertEqual(villager_b.status, "dead")

    async def test_awakened_wolf_beauty_illusion_substitutes_charmed_player(self):
        game = make_game()
        beauty = Player(FakeUser(10), AwakenedWolfBeauty())
        wolf = Player(FakeUser(11), Wolf())
        charmed = Player(FakeUser(12), Villager())
        witch = Player(FakeUser(13), Witch())
        villager = Player(FakeUser(14), Villager())
        game.players = [beauty, wolf, charmed, witch, villager]
        game.phase = PHASE_NIGHT_1
        game.round_num = 1
        game.wolf_target = -1
        game.witch_poison_target = beauty.id
        game.role_actions[(beauty.id, "awakened_charm")] = {
            "type": "awakened_charm", "target": charmed.id, "mode": None
        }

        await game.start_day()

        self.assertEqual(beauty.status, "alive")
        self.assertEqual(charmed.status, "dead")
        self.assertTrue(beauty.role.state["illusion_used"])

    async def test_awakened_hunter_patrols_first_wolf_in_direction(self):
        game = make_game()
        hunter = Player(FakeUser(10), AwakenedHunter())
        hunter.status = "dead"
        villager = Player(FakeUser(11), Villager())
        wolf = Player(FakeUser(12), Wolf())
        other_wolf = Player(FakeUser(13), Wolf())
        game.players = [hunter, villager, wolf, other_wolf]
        game.phase = PHASE_SHOOT
        game.pending_shooters = [hunter.id]
        game.after_shoot = "night"
        interaction = FakeInteraction(hunter.user)

        with patch.object(game, "start_night", new=AsyncMock(return_value=True)):
            await game.handle_awakened_hunt(interaction, hunter, "right")

        self.assertEqual(wolf.status, "dead")
        self.assertEqual(other_wolf.status, "alive")

    async def test_eclipse_maid_devour_disables_victim_skill(self):
        game = make_game()
        maid = Player(FakeUser(10), EclipseMaid())
        wolf = Player(FakeUser(11), Wolf())
        seer = Player(FakeUser(12), Seer())
        villager = Player(FakeUser(13), Villager())
        game.players = [maid, wolf, seer, villager]
        game.phase = PHASE_NIGHT_1
        game.round_num = 2

        await game._complete_devour(
            FakeInteraction(maid.user), maid, seer, "seer_check", wolf.id
        )

        self.assertTrue(seer.role.disabled)
        self.assertIn((maid.id, "devour"), game.role_actions)

    async def test_guard_blocks_wolf_kill(self):
        game = make_game()
        wolf = Player(FakeUser(10), Wolf())
        guard = Player(FakeUser(11), Guard())
        villager = Player(FakeUser(12), Villager())
        seer = Player(FakeUser(13), Seer())
        game.players = [wolf, guard, villager, seer]
        game.phase = PHASE_NIGHT_1
        game.round_num = 1
        game.wolf_target = villager.id
        game.role_actions[(guard.id, "guard")] = {
            "type": "guard", "target": villager.id, "mode": None
        }

        await game.start_day()

        self.assertEqual(villager.status, "alive")
        self.assertEqual(game.deaths_tonight, [])

    async def test_pure_white_kills_checked_wolf_from_second_night(self):
        game = make_game()
        wolf = Player(FakeUser(10), Wolf())
        pure_white = Player(FakeUser(11), PureWhite())
        villager = Player(FakeUser(12), Villager())
        game.players = [wolf, pure_white, villager]
        game.phase = PHASE_NIGHT_1
        game.round_num = 2
        game.wolf_target = -1
        game.role_actions[(pure_white.id, "pure_white_check")] = {
            "type": "pure_white_check", "target": wolf.id, "mode": None
        }

        await game.start_day()

        self.assertEqual(wolf.status, "dead")

    async def test_evil_knight_reflects_first_seer_check(self):
        game = make_game()
        evil = Player(FakeUser(10), EvilKnight())
        wolf = Player(FakeUser(11), Wolf())
        seer = Player(FakeUser(12), Seer())
        villager = Player(FakeUser(13), Villager())
        game.players = [evil, wolf, seer, villager]
        game.phase = PHASE_NIGHT_1
        game.round_num = 1
        game.wolf_target = -1
        game.role_actions[(seer.id, "seer_check")] = {
            "type": "seer_check", "target": evil.id, "mode": None
        }

        await game.start_day()

        self.assertEqual(seer.status, "dead")
        self.assertTrue(evil.role.used_skill)

    async def test_fool_survives_first_exile_and_loses_vote(self):
        game = make_game()
        fool = Player(FakeUser(10), Fool())
        wolf = Player(FakeUser(11), Wolf())
        villager = Player(FakeUser(12), Villager())
        game.players = [fool, wolf, villager]
        game.phase = PHASE_DAY
        game.votes = {wolf.id: fool.id, villager.id: fool.id, fool.id: fool.id}

        with patch.object(game, "start_night", new=AsyncMock(return_value=True)):
            await game._resolve_exile(fool)

        self.assertEqual(fool.status, "alive")
        self.assertTrue(fool.role.vote_disabled)

    async def test_awakened_wolf_king_can_pass_one_claw(self):
        game = make_game()
        king = Player(FakeUser(10), AwakenedWolfKing())
        wolf = Player(FakeUser(11), Wolf())
        villager = Player(FakeUser(12), Villager())
        game.players = [king, wolf, villager]
        game.phase = PHASE_NIGHT_1
        game.round_num = 1

        await game.handle_night_action(
            FakeInteraction(king.user), king, "claw_pass", wolf.id
        )

        self.assertEqual(king.role.shoot_count, 1)
        self.assertEqual(wolf.role.shoot_count, 1)
        self.assertTrue(wolf.role.can_shoot)

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
