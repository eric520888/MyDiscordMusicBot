import discord
import asyncio
import copy
import random
import logging
from collections import Counter
from .const import *
from .roles import *
from .views import (
    IdentityView,
    LobbyView,
    LuckyView,
    MerchantSkillSelect,
    NightTargetSelect,
    ShooterView,
    VotingView,
    WitchView,
    create_identity_embed,
)
from .audio import AudioManager
from .skills import SkillManager # [新增] 引入 SkillManager
from .replay import ReplayView   # [新增] 引入復盤系統


log = logging.getLogger(__name__)

class WerewolfGame:
    def __init__(self, bot, channel, host):
        self.bot = bot
        self.channel = channel
        self.host = host
        self.players = [] # List[Player]
        self.phase = PHASE_WAITING
        self.board_id = BOARD_AUTO
        
        # --- 遊戲數據 ---
        self.night_actions = set() # 記錄已行動的玩家 ID
        self.wolf_votes = {}       # {user_id: target_id}
        self.wolf_target = None    # 狼人最終殺誰
        
        # 女巫數據
        self.witch_poison_target = None
        
        # 奇跡商人/幸運兒數據
        self.lucky_data = {"user_id": None, "skill": None, "target": None}

        # 官方技能板型共用狀態
        self.role_actions = {}      # {actor_id: {type, target, mode}}
        self.night_action_bonuses = {}
        self.extra_wolf_kill = False
        self.wolf_targets = []
        self.phase2_action_counts = Counter()
        self.charmed_target = None
        self.fate_pair = None
        self.fate_triggered = False
        self.previous_dream_target = None
        self.current_dream_target = None
        self.pending_night_servant = None
        self.last_exiled_camp = None
        self.last_exiled_name = None
        self.pending_white_cats = set()
        self.good_skills_sealed = False
        self.crimson_last_stand = None
        self.last_vote_voters = {}
        self.awakened_guard_target = None
        self.awakened_guard_period = None
        self.pending_awakened_white_wolf = None
        self.pending_role_notices = []
        
        # 投票數據
        self.votes = {}     # {user_id: target_id}
        self.stop_votes = set()
        self.deaths_tonight = [] # 今晚死亡名單
        self.pending_shooters = []
        self.shot_players = set()
        self.shots_fired = Counter()
        self.after_shoot = None
        self.pending_exile_id = None
        self.cats_due_after_vote = set()

        # 介面引用
        self.lobby_message = None
        self.wolf_thread = None

        # 狀態轉換與資源清理
        self._state_lock = asyncio.Lock()
        self._ending = False
        self._resolving_day = False
        self._vote_tally_started = False
        self._original_mute_states = {}

        # [新增] 初始化技能管理器
        self.skill_manager = SkillManager(self)
        
        # [新增] 復盤系統數據
        self.game_log = []   # 遊戲事件記錄
        self.round_num = 0   # 回合計數器

    # ==========================
    #      輔助函式 (Helper)
    # ==========================
    def get_player(self, user_id):
        """根據 ID 取得 Player 物件"""
        return next((p for p in self.players if p.id == user_id), None)

    def get_alive_players(self):
        """取得所有活著的玩家"""
        return [p for p in self.players if p.status == "alive"]
    
    def get_players_by_role(self, role_class):
        """取得特定職業的所有玩家 (無論死活)"""
        return [p for p in self.players if isinstance(p.role, role_class)]

    def get_alive_role(self, role_class):
        """取得特定職業且活著的玩家"""
        return [p for p in self.get_alive_players() if isinstance(p.role, role_class)]

    def get_active_wolves(self):
        """取得本夜能參與狼襲的狼人；孤立狼神只在其餘狼人全滅後加入。"""
        alive_wolves = [p for p in self.get_alive_players() if p.role.camp == CAMP_WOLF]
        regular = [
            p for p in alive_wolves
            if p.role.joins_wolf_vote and not p.role.isolated_wolf
        ]
        if regular:
            return regular
        return [p for p in alive_wolves if p.role.isolated_wolf]

    def get_action_targets(self, actor, action_type):
        """依官方技能限制過濾目標，避免狼刀隊友、重複查驗等非法操作。"""
        targets = list(self.get_alive_players())
        no_self = {
            "merchant_give", "charm", "awakened_charm", "exact_check",
            "wolf_witch_check", "pure_white_check", "hunt", "fear",
            "confuse", "devour", "light_guard", "night_servant",
            "mirror_check", "mimic", "double_check", "fate_bind",
            "knight_duel", "claw_pass", "seer_check", "dream", "mimic_witch",
            "choose_idol", "dream_speech", "convert",
        }
        if action_type in no_self:
            targets = [target for target in targets if target.id != actor.id]
        if action_type == "wolf_kill":
            self_kill_wolves = (
                AwakenedGargoyle,
                AwakenedWolfKing,
                AwakenedWhiteWolfKing,
            )
            targets = [
                target for target in targets
                if target.role.camp != CAMP_WOLF
                or isinstance(target.role, self_kill_wolves)
            ]
        if action_type in {"charm", "awakened_charm"}:
            targets = [target for target in targets if target.role.camp != CAMP_WOLF]
        if action_type == "wolf_witch_check":
            targets = [target for target in targets if target.role.camp != CAMP_WOLF]
        if action_type == "devour":
            targets = [target for target in targets if target.role.camp != CAMP_WOLF]
        if action_type == "claw_pass":
            targets = [target for target in targets if target.role.camp == CAMP_WOLF]
        if action_type == "convert":
            actor_index = self.players.index(actor)
            adjacent_ids = {
                self.players[(actor_index - 1) % len(self.players)].id,
                self.players[(actor_index + 1) % len(self.players)].id,
            }
            targets = [target for target in targets if target.id in adjacent_ids]
        if action_type in {"exact_check", "mirror_check"}:
            targets = [
                target for target in targets
                if target.id not in actor.role.checked_targets
            ]
        if action_type in {
            "guard", "fear", "confuse", "devour", "light_guard",
            "awakened_guard", "dream_speech",
        }:
            if actor.role.last_target is not None:
                previous = actor.role.last_target
                previous_ids = set(previous) if isinstance(previous, list) else {previous}
                targets = [target for target in targets if target.id not in previous_ids]
        return targets

    def get_night_action_limit(self, player, action_type):
        if action_type in {"double_check", "fate_bind"}:
            return 2
        if action_type == "wolf_kill" and self.extra_wolf_kill:
            return 2
        return 1 + int(self.night_action_bonuses.get(player.id, 0) > 0)

    def _is_awakened_guarded(self, player):
        return bool(
            player
            and player.status == "alive"
            and self.awakened_guard_target == player.id
            and self.awakened_guard_period in {"night", "day"}
        )

    def _target_acted_tonight(self, player_id):
        if any(
            actor_id == player_id and not data.get("skipped")
            for (actor_id, _), data in self.role_actions.items()
        ):
            return True
        return self.phase2_action_counts[player_id] > 0

    def _resolve_awakened_lonely_idol(self, dead_player, cause):
        """依偶像死因讓覺醒孤獨少女轉狼或繼承偶像。"""
        for girl in list(self.get_alive_role(AwakenedLonelyGirl)):
            if girl.role.disabled:
                continue
            if girl.role.state.get("idol_id") != dead_player.id:
                continue
            if cause == "投票處決":
                girl.role.camp = CAMP_WOLF
                girl.role.night_action = None
                girl.role.joins_wolf_vote = True
                girl.role.isolated_wolf = False
                girl.role.can_self_destruct = True
                girl.role.description = "偶像遭放逐，已覺醒為狼人並加入狼隊。"
                notice = f"💔 {girl.display_name} 的偶像遭放逐，覺醒孤獨少女轉化為狼人！"
                result = "轉化為狼人"
            else:
                inherited_role = copy.deepcopy(dead_player.role)
                inherited_role.state["inherited_by_awakened_lonely_girl"] = True
                girl.role = inherited_role
                notice = (
                    f"💞 {girl.display_name} 的偶像以非放逐方式出局，"
                    f"她繼承了 **{dead_player.role.name}** 的身分與技能。"
                )
                result = f"繼承{dead_player.role.name}"
            self.pending_role_notices.append(notice)
            self.log_event(
                "awakened_lonely_girl",
                {"player": girl.display_name, "idol": dead_player.display_name, "result": result},
            )

    async def _collect_awakened_dreamer_kills(self):
        """天亮前讓覺醒攝夢人得知行動結果，第二夜起決定是否處決。"""
        entries = [
            (self.get_player(actor_id), data)
            for (actor_id, action_type), data in self.role_actions.items()
            if action_type == "dream_speech" and not data.get("skipped")
        ]
        kill_targets = set()
        for dreamer, data in entries:
            target = self.get_player(data["target"])
            if not dreamer or dreamer.status != "alive" or not target:
                continue
            acted = self._target_acted_tonight(target.id)
            dreamer.role.state["last_dream_target"] = target.id
            dreamer.role.state["last_dream_acted"] = acted
            if self.round_num < 2:
                try:
                    await dreamer.user.send(
                        f"🌌 夢語結果：**{target.display_name}** 本夜"
                        f"{'有' if acted else '沒有'}發動行動。第一夜尚不能令其出局。"
                    )
                except (AttributeError, discord.HTTPException):
                    pass
                self.log_event(
                    "dream_speech_result",
                    {
                        "dreamer": dreamer.display_name,
                        "target": target.display_name,
                        "acted": acted,
                        "kill": False,
                    },
                )
                continue
            decision = asyncio.get_running_loop().create_future()
            view = discord.ui.View(timeout=45)
            kill_button = discord.ui.Button(
                label="令其夢語出局", style=discord.ButtonStyle.danger, emoji="🌌"
            )
            spare_button = discord.ui.Button(
                label="本夜放過", style=discord.ButtonStyle.secondary, emoji="✨"
            )

            async def decide(interaction, should_kill):
                if interaction.user.id != dreamer.id or decision.done():
                    return await interaction.response.send_message(
                        "❌ 只有本夜的覺醒攝夢人能決定。", ephemeral=True
                    )
                decision.set_result(should_kill)
                await interaction.response.send_message(
                    f"🌌 **{target.display_name}** 本夜"
                    f"{'有' if acted else '沒有'}發動行動；"
                    f"你選擇{'令其出局' if should_kill else '放過對方'}。",
                    ephemeral=True,
                )
                view.stop()

            async def kill_callback(interaction):
                await decide(interaction, True)

            async def spare_callback(interaction):
                await decide(interaction, False)

            kill_button.callback = kill_callback
            spare_button.callback = spare_callback
            view.add_item(kill_button)
            view.add_item(spare_button)
            try:
                await dreamer.user.send(
                    f"🌌 **{target.display_name}** 本夜"
                    f"{'有' if acted else '沒有'}發動行動。請在 45 秒內決定：",
                    view=view,
                )
            except (AttributeError, discord.HTTPException):
                await self.channel.send(
                    "🌌 夢語已回響，覺醒攝夢人請在 45 秒內完成秘密決定。",
                    view=view,
                )
            try:
                should_kill = await asyncio.wait_for(decision, timeout=45)
            except asyncio.TimeoutError:
                should_kill = False
                view.stop()
                await self.channel.send("⌛ 覺醒攝夢人逾時，本夜不發動夢語出局。")
            if should_kill:
                kill_targets.add(target.id)
            self.log_event(
                "dream_speech_result",
                {
                    "dreamer": dreamer.display_name,
                    "target": target.display_name,
                    "acted": acted,
                    "kill": should_kill,
                },
            )
        return kill_targets

    async def _is_host_or_owner(self, user):
        return user.id == self.host.id or await self.bot.is_owner(user)

    def _unregister(self):
        cog = self.bot.get_cog("Werewolf")
        games = getattr(cog, "games", None)
        guild_id = self.channel.guild.id
        if isinstance(games, dict) and games.get(guild_id) is self:
            games.pop(guild_id, None)

    def _capture_mute_states(self):
        for player in self.players:
            member = self.channel.guild.get_member(player.id)
            if member and member.voice and player.id not in self._original_mute_states:
                self._original_mute_states[player.id] = bool(member.voice.mute)

    async def _mute_for_night(self):
        if self.phase not in {PHASE_NIGHT_1, PHASE_NIGHT_2}:
            return
        self._capture_mute_states()
        await AudioManager.mute_all(self.channel, self.players, True)
        if self.phase == PHASE_ENDED:
            await self._restore_mutes()
        elif self.phase in {PHASE_DAY, PHASE_SHOOT}:
            await self._apply_day_mutes()

    async def _play_night_audio(self):
        if self.phase not in {PHASE_NIGHT_1, PHASE_NIGHT_2}:
            return
        await AudioManager.play_mixed(
            self.channel,
            "night.mp3",
            "voice_night_start.mp3",
        )
        if self.phase not in {PHASE_NIGHT_1, PHASE_NIGHT_2}:
            await AudioManager.stop(self.channel)

    async def _apply_day_mutes(self):
        self._capture_mute_states()
        states = {
            player.id: (
                True
                if player.status == "dead"
                else self._original_mute_states.get(player.id, False)
            )
            for player in self.players
        }
        await AudioManager.set_mute_states(self.channel, states)

    async def _restore_mutes(self):
        if self._original_mute_states:
            await AudioManager.set_mute_states(
                self.channel,
                self._original_mute_states,
            )

    async def _release_game_audio(self):
        music = self.bot.get_cog("Music")
        try:
            if music:
                await music.release_external_audio(self.channel.guild)
            else:
                await AudioManager.stop(self.channel)
        except Exception:
            log.exception("釋放狼人殺語音控制權失敗")
            await AudioManager.stop(self.channel)

    # ==========================
    #      大廳階段 (Lobby)
    # ==========================
    async def set_board(self, interaction, board_id):
        if not await self._is_host_or_owner(interaction.user):
            return await interaction.response.send_message(
                "❌ 只有房主能更換板子。", ephemeral=True
            )
        if self.phase != PHASE_WAITING:
            return await interaction.response.send_message(
                "❌ 遊戲已經開始，不能更換板子。", ephemeral=True
            )
        if board_id not in BOARD_NAMES:
            return await interaction.response.send_message(
                "❌ 不支援的板子。", ephemeral=True
            )

        self.board_id = board_id
        board_name = BOARD_NAMES[board_id]
        
        await interaction.response.send_message(f"✅ 板子更新為：**{board_name}**", ephemeral=True)
        if self.lobby_message:
            view = LobbyView(self)
            await self.lobby_message.edit(embed=view.update_embed(), view=view)

    async def player_join(self, interaction):
        if self.phase != PHASE_WAITING:
            return await interaction.response.send_message(
                "❌ 大廳已關閉或遊戲已經開始。", ephemeral=True
            )
        if self.get_player(interaction.user.id):
            return await interaction.response.send_message("你已經在遊戲中了", ephemeral=True)
        if len(self.players) >= MAX_PLAYERS:
            return await interaction.response.send_message(
                f"❌ 大廳已滿（最多 {MAX_PLAYERS} 人）。", ephemeral=True
            )
        
        self.players.append(Player(interaction.user, None))
        await interaction.response.edit_message(embed=LobbyView(self).update_embed(), view=LobbyView(self))

    async def player_leave(self, interaction):
        if self.phase != PHASE_WAITING:
            return await interaction.response.send_message(
                "❌ 大廳已關閉或遊戲已經開始。", ephemeral=True
            )
        p = self.get_player(interaction.user.id)
        if p:
            self.players.remove(p)
            await interaction.response.edit_message(embed=LobbyView(self).update_embed(), view=LobbyView(self))
        else:
            await interaction.response.send_message("你不在這個大廳中。", ephemeral=True)

    async def close_lobby(self, interaction):
        if not await self._is_host_or_owner(interaction.user):
            return await interaction.response.send_message(
                "❌ 只有房主能關閉大廳。", ephemeral=True
            )
        if self.phase != PHASE_WAITING:
            return await interaction.response.send_message(
                "❌ 大廳已關閉或遊戲已經開始。", ephemeral=True
            )

        self.phase = PHASE_ENDED
        self._unregister()
        await interaction.response.edit_message(embed=discord.Embed(title="🛑 大廳已關閉", color=discord.Color.greyple()), view=None)

    # ==========================
    #      遊戲開始 (Start)
    # ==========================
    async def start_game(self, interaction):
        if interaction.user.id != self.host.id:
            is_dev = await self.bot.is_owner(interaction.user)
            if not is_dev:
                return await interaction.response.send_message(
                    "❌ 權限不足", ephemeral=True
                )

        async with self._state_lock:
            if self.phase != PHASE_WAITING:
                return await interaction.response.send_message(
                    "❌ 遊戲已經開始或大廳已關閉。", ephemeral=True
                )

            n = len(self.players)
            minimum = BOARD_MIN_PLAYERS.get(self.board_id, 3)
            invalid_count = n != minimum if self.board_id in BOARD_SPECS else n < minimum
            if invalid_count:
                requirement = "需要" if self.board_id in BOARD_SPECS else "至少需要"
                return await interaction.response.send_message(
                    f"❌ {BOARD_NAMES.get(self.board_id, '此板子')}{requirement} {minimum} 人，"
                    f"目前只有 {n} 人。",
                    ephemeral=True,
                )

            if not self.assign_roles():
                return await interaction.response.send_message(
                    "❌ 目前人數無法建立有效配置。", ephemeral=True
                )
            self.phase = PHASE_STARTING

        # 語音連線可能超過 Discord 的三秒回應期限，先確認互動。
        await interaction.response.defer()
        guild = self.channel.guild
        voice_channel = (
            interaction.user.voice.channel
            if interaction.user.voice
            else (guild.voice_client.channel if guild.voice_client else None)
        )
        if voice_channel:
            try:
                music = self.bot.get_cog("Music")
                if music:
                    await music.prepare_external_audio(guild, voice_channel)
                elif not guild.voice_client:
                    await voice_channel.connect(
                        timeout=30.0,
                        reconnect=True,
                        self_deaf=True,
                    )
            except Exception:
                log.exception("狼人殺連線語音頻道失敗")

        self._capture_mute_states()
        if self.phase != PHASE_STARTING:
            await self._release_game_audio()
            return
        await interaction.followup.send("🚀 遊戲開始！正在分配身分...", ephemeral=False)
        if self.lobby_message: 
            try:
                await self.lobby_message.delete()
            except discord.HTTPException:
                log.warning("無法刪除狼人殺大廳訊息", exc_info=True)

        await self.create_wolf_thread()
        if self.phase != PHASE_STARTING:
            await self._release_game_audio()
            return
        await self.channel.send(
            embed=discord.Embed(
                title="🎴 身分確認階段",
                description=(
                    "點擊下方按鈕查看自己的身分卡與專屬情報。\n"
                    "⏱️ **10 秒後自動進入第一夜**"
                ),
                color=discord.Color.gold(),
            ),
            view=IdentityView(self),
        )
        
        # 自動入夜：等待 10 秒讓玩家確認身分
        await asyncio.sleep(10)
        if self.phase == PHASE_STARTING:  # 確保還沒被強制入夜
            await self.start_night()

    def assign_roles(self):
        n = len(self.players)
        minimum = BOARD_MIN_PLAYERS.get(self.board_id, 3)
        if n > MAX_PLAYERS:
            return False

        if self.board_id in BOARD_SPECS:
            spec = BOARD_SPECS[self.board_id]
            if n != spec.player_count:
                return False
            role_list = list(spec.roles)
            random.shuffle(role_list)
            for player, role_name in zip(self.players, role_list):
                player.role = create_role(role_name)
                player.status = "alive"
            self._prepare_assigned_role_state()
            return True

        if n < minimum:
            return False

        wolves_count = max(1, n // 3)
        w, k, s, wi, h, m = 0, 0, 0, 0, 0, 0
        
        if self.board_id == BOARD_AUTO:
            if n < 6:
                w, s = 1, 1
            elif n < 10:
                w, k, s, wi, h = wolves_count - 1, 1, 1, 1, 1
            else:
                w, k, s, wi, h, m = wolves_count - 1, 1, 1, 1, 1, 1
        elif self.board_id == BOARD_WOLF_KING:
            s, wi, h, k = 1, 1, 1, 1
            w = max(0, wolves_count - 1)
        elif self.board_id == BOARD_MERCHANT:
            s, wi, h, m, k = 1, 1, 1, 1, 1
            w = max(0, wolves_count - 1)

        total = w + k + s + wi + h + m
        if n < total: return False

        role_list = [ROLE_WEREWOLF]*w + [ROLE_WOLF_KING]*k + [ROLE_SEER]*s + \
                    [ROLE_WITCH]*wi + [ROLE_HUNTER]*h + [ROLE_MERCHANT]*m
        
        while len(role_list) < n: role_list.append(ROLE_VILLAGER)
        random.shuffle(role_list)
        
        for i, p in enumerate(self.players):
            p.role = create_role(role_list[i]) 
            p.status = "alive"

        self._prepare_assigned_role_state()
        return True

    def _prepare_assigned_role_state(self):
        """建立需要依本局座位或隊友決定的初始私密情報。"""
        wolves = [player for player in self.players if player.role.camp == CAMP_WOLF]
        for phantom in self.get_players_by_role(FragrancePhantom):
            candidates = [wolf for wolf in wolves if wolf.id != phantom.id]
            if candidates:
                phantom.role.state["known_wolf_id"] = random.choice(candidates).id

    async def create_wolf_thread(self):
        if self.phase not in {PHASE_STARTING, PHASE_NIGHT_1}:
            return False
        try:
            if self.wolf_thread:
                return True
            thread_name = f"🐺-狼人密謀-{random.randint(100,999)}"
            thread = await self.channel.create_thread(
                name=thread_name, 
                type=discord.ChannelType.private_thread,
                invitable=False
            )
            self.wolf_thread = thread
            mentions = []
            for p in self.players:
                if p.role.camp == CAMP_WOLF and not p.role.isolated_wolf:
                    await thread.add_user(p.user)
                    mentions.append(p.mention)
            await thread.send(f"🐺 **狼人密謀區**\n成員：{' '.join(mentions)}\n天黑請在此討論。")
            if self.phase not in {PHASE_STARTING, PHASE_NIGHT_1}:
                await thread.delete()
                if self.wolf_thread is thread:
                    self.wolf_thread = None
                return False
            return True
        except discord.HTTPException:
            self.wolf_thread = None
            log.exception("無法建立狼人討論串")
            return False

    # ==========================
    #      身分確認 & 入夜
    # ==========================
    async def send_identity(self, interaction):
        if self.phase not in {
            PHASE_STARTING,
            PHASE_NIGHT_1,
            PHASE_NIGHT_2,
            PHASE_DAY,
            PHASE_SHOOT,
        }:
            return await interaction.response.send_message(
                "❌ 目前沒有可查看的遊戲身分。", ephemeral=True
            )
        p = self.get_player(interaction.user.id)
        if not p:
            return await interaction.response.send_message(
                "❌ 你不是這場遊戲的玩家。", ephemeral=True
            )

        embed = create_identity_embed(self, p)
        if p.role.camp == CAMP_WOLF:
            if p.role.isolated_wolf:
                embed.add_field(
                    name="🌑 狼隊情報",
                    value="目前尚未與狼隊相認，也不會進入密謀區。",
                    inline=False,
                )
            else:
                teammates = [
                    member.display_name for member in self.players
                    if member.role.camp == CAMP_WOLF
                    and not member.role.isolated_wolf
                    and member.id != p.id
                ]
                embed.add_field(
                    name="🐺 狼隊情報",
                    value=(
                        f"隊友：{', '.join(teammates) if teammates else '無（孤狼）'}\n"
                        "💬 夜晚請留意狼人密謀區。"
                    ),
                    inline=False,
                )

        if isinstance(p.role, Gravekeeper):
            if self.last_exiled_camp:
                result = "狼人" if self.last_exiled_camp == CAMP_WOLF else "好人"
                embed.add_field(
                    name="🪦 守墓情報",
                    value=f"上一位被放逐者 **{self.last_exiled_name}** 屬於：**{result}**。",
                    inline=False,
                )
            else:
                embed.add_field(name="🪦 守墓情報", value="目前沒有可查的放逐者。", inline=False)
        if isinstance(p.role, AwakenedWitch):
            embed.add_field(name="🧪 技能資源", value=f"剩餘調毒：**{p.role.poison_recipes}** 次", inline=False)
        if isinstance(p.role, AwakenedWolfKing):
            embed.add_field(name="🐾 技能資源", value=f"持有狼王爪：**{p.role.shoot_count}** 枚", inline=False)
        if isinstance(p.role, FragrancePhantom):
            known_wolf = self.get_player(p.role.state.get("known_wolf_id"))
            embed.add_field(
                name="🦋 尋香情報",
                value=(
                    f"你感知到的狼人：**{known_wolf.display_name}**"
                    if known_wolf else "沒有感知到其他狼人"
                ),
                inline=False,
            )
        if isinstance(p.role, AwakenedLonelyGirl):
            idol = self.get_player(p.role.state.get("idol_id"))
            embed.add_field(
                name="💞 偶像",
                value=idol.display_name if idol else "尚未選擇",
                inline=False,
            )
        if isinstance(p.role, AwakenedGuard):
            target = self.get_player(self.awakened_guard_target)
            embed.add_field(
                name="🛡️ 本日守護",
                value=target.display_name if target and p.role.state.get("last_guard_round") == self.round_num else "尚未發動",
                inline=False,
            )
        if isinstance(p.role, AwakenedDreamer):
            target = self.get_player(p.role.last_target)
            embed.add_field(
                name="🌌 上一位夢語者",
                value=target.display_name if target else "尚無",
                inline=False,
            )
            result_target = self.get_player(p.role.state.get("last_dream_target"))
            if result_target:
                embed.add_field(
                    name="🌠 最近夢語結果",
                    value=(
                        f"{result_target.display_name} 本夜"
                        f"{'有' if p.role.state.get('last_dream_acted') else '沒有'}發動行動"
                    ),
                    inline=False,
                )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def force_night(self, interaction):
        if not await self._is_host_or_owner(interaction.user):
            return await interaction.response.send_message(
                "❌ 只有房主能強制入夜。", ephemeral=True
            )
        if self.phase != PHASE_STARTING:
            return await interaction.response.send_message(
                "❌ 現在不能強制入夜。", ephemeral=True
            )

        await interaction.response.defer()
        started = await self.start_night()
        if started:
            await interaction.followup.send("🚨 主持人強制入夜！")
        else:
            await interaction.followup.send(
                "夜晚已由其他操作開始。", ephemeral=True
            )

    # ==========================
    #      夜晚流程 (Night)
    # ==========================
    async def start_night(self):
        async with self._state_lock:
            if self.phase not in {PHASE_STARTING, PHASE_DAY}:
                return False
            self.phase = PHASE_NIGHT_1
            self.round_num += 1
            self.night_actions.clear()
            self.role_actions.clear()
            self.night_action_bonuses.clear()
            self.extra_wolf_kill = False
            self.wolf_targets = []
            self.phase2_action_counts.clear()
            self.wolf_votes.clear()
            self.wolf_target = None
            self.witch_poison_target = None
            self.lucky_data = {"user_id": None, "skill": None, "target": None}
            self.deaths_tonight = []
            self.current_dream_target = None
            self.charmed_target = None
            self.votes = {}
            self.stop_votes = set()
            self._vote_tally_started = False
            self.awakened_guard_target = None
            self.awakened_guard_period = None
            self.pending_awakened_white_wolf = None

            # 覺醒石像鬼的轉化者要到下一夜才與狼隊相認並加入狼刀。
            for player in self.get_alive_players():
                reveal_round = player.role.state.get("wolf_reveal_round")
                if reveal_round and self.round_num >= reveal_round:
                    player.role.isolated_wolf = False
                    player.role.joins_wolf_vote = True
                    player.role.state.pop("wolf_reveal_round", None)

        asyncio.create_task(self._play_night_audio())
        asyncio.create_task(self._mute_for_night())
        await self.create_wolf_thread()

        if self.wolf_thread:
            try:
                await self.wolf_thread.send("🌃 **天黑了，請開始討論戰術！**")
            except discord.HTTPException:
                log.warning("無法傳送狼人夜晚通知", exc_info=True)

        view = discord.ui.View(timeout=None)
        button = discord.ui.Button(
            label="夜晚行動", style=discord.ButtonStyle.primary, emoji="🌙"
        )

        async def action_callback(interaction):
            if self.phase != PHASE_NIGHT_1:
                return await interaction.response.send_message(
                    "❌ 這個夜晚行動按鈕已失效。", ephemeral=True
                )
            player = self.get_player(interaction.user.id)
            if not player or player.status != "alive":
                return await interaction.response.send_message(
                    "❌ 你不是存活玩家。", ephemeral=True
                )
            pending = self.get_pending_night_tasks(player)
            if not pending:
                return await interaction.response.send_message(
                    "💤 你今晚沒有尚未完成的行動。", ephemeral=True
                )
            if len(pending) == 1:
                return await self._send_night_action_panel(
                    interaction, player, pending[0]
                )

            choose_view = discord.ui.View(timeout=300)
            for action_type in pending:
                task_button = discord.ui.Button(
                    label=self._night_action_label(action_type),
                    style=discord.ButtonStyle.secondary,
                )

                async def choose_callback(inte, selected=action_type):
                    await self._send_night_action_panel(inte, player, selected)

                task_button.callback = choose_callback
                choose_view.add_item(task_button)
            await interaction.response.send_message(
                "你今晚有多個行動，請選擇：", view=choose_view, ephemeral=True
            )

        button.callback = action_callback
        view.add_item(button)

        required = self.get_required_night_tasks()
        role_names = sorted({
            self.get_player(player_id).role.name
            for player_id, _ in required
            if self.get_player(player_id)
        })
        night_embed = discord.Embed(
            title=f"🌃 第 {self.round_num} 夜｜上半夜",
            description="存活玩家請點擊「夜晚行動」，系統只會顯示屬於你的操作。",
            color=discord.Color.dark_blue(),
        )
        night_embed.add_field(
            name="本夜行動角色",
            value="、".join(role_names) if role_names else "無角色需要行動",
            inline=False,
        )
        night_embed.add_field(
            name="存活人數",
            value=f"{len(self.get_alive_players())} / {len(self.players)}",
            inline=True,
        )
        night_embed.set_footer(text="所有目標與查驗結果都只對操作者顯示")
        await self.channel.send(embed=night_embed, view=view)
        if not required:
            await self.check_phase_1_end()
        return True

    def _night_action_label(self, action_type):
        return {
            "wolf_kill": "狼隊襲擊", "seer_check": "預言查驗",
            "merchant_give": "商人賜能", "guard": "守護",
            "dream": "攝夢", "charm": "魅惑", "awakened_charm": "覺醒魅惑",
            "exact_check": "具體查驗", "wolf_witch_check": "狼巫查驗",
            "pure_white_check": "純白查驗", "hunt": "狩獵", "fear": "恐懼",
            "block": "封鎖", "time_wave": "時波轉換", "confuse": "迷惑",
            "devour": "吞噬", "light_guard": "流光庇護",
            "night_servant": "夜僕之擁", "secret_guard": "秘密守護",
            "fate_bind": "命運綁定", "double_check": "雙人查驗",
            "mirror_check": "魔鏡查驗", "mimic": "模仿",
            "claw_pass": "轉交狼王爪",
            "mimic_witch": "模仿女巫毒殺",
            "choose_idol": "選擇偶像",
            "convert": "相鄰轉化",
            "awakened_guard": "覺醒守護",
            "dream_speech": "選擇夢語者",
        }.get(action_type, action_type)

    def _role_action_available(self, player):
        role = player.role
        action_type = role.night_action
        effective_round = max(self.round_num, 1)
        if not action_type or role.disabled or effective_round < role.action_from_round:
            return False
        if self.good_skills_sealed and role.camp != CAMP_WOLF:
            return False
        if role.used_skill and action_type in {"merchant_give", "confuse"}:
            return False
        if action_type == "night_servant" and self.pending_night_servant:
            return False
        if action_type == "secret_guard" and (
            role.used_skill or not role.secret_body
        ):
            return False
        if action_type == "time_wave":
            if role.state.get("boost_used") and role.state.get("weaken_used"):
                return False
        if action_type == "awakened_charm" and self.round_num <= role.state.get("cooldown_until", 0):
            return False
        if action_type == "claw_pass" and role.shoot_count <= 0:
            return False
        if action_type == "mimic_witch" and role.state.get("mimic_witch_used"):
            return False
        if action_type in {"choose_idol", "convert"} and (
            self.round_num != 1 or role.used_skill
        ):
            return False
        if action_type == "awakened_guard" and role.state.get("last_guard_round") == self.round_num:
            return False
        if action_type == "fate_bind" and self.fate_triggered:
            return False
        return bool(self.get_action_targets(player, action_type))

    def _disabled_night_ids(self):
        disabled = set()
        fear = next(
            (data for (_, action), data in self.role_actions.items() if action == "fear"),
            None,
        )
        if fear:
            disabled.add(fear["target"])
        for (_, action), data in self.role_actions.items():
            if action == "time_wave" and data.get("mode") == "weaken":
                disabled.add(data["target"])
        return disabled

    def get_required_night_tasks(self):
        tasks = set()
        disabled_ids = self._disabled_night_ids()
        active_wolves = self.get_active_wolves()
        wolf_team_disabled = any(
            player.id in disabled_ids for player in active_wolves
        )
        if not wolf_team_disabled:
            tasks.update((player.id, "wolf_kill") for player in active_wolves)
        for player in self.get_alive_players():
            if player.id in disabled_ids:
                continue
            if self._role_action_available(player):
                tasks.add((player.id, player.role.night_action))
        return tasks

    def get_pending_night_tasks(self, player):
        required = self.get_required_night_tasks()
        priority_actions = {"fear", "block", "time_wave", "confuse", "devour"}
        outstanding_priority = {
            task for task in required
            if task[1] in priority_actions and task not in self.role_actions
        }
        pending = [
            action for player_id, action in sorted(self.get_required_night_tasks())
            if player_id == player.id and (player_id, action) not in self.role_actions
        ]
        if outstanding_priority:
            return [action for action in pending if action in priority_actions]
        return pending

    async def _send_night_action_panel(self, interaction, player, action_type):
        if action_type not in self.get_pending_night_tasks(player):
            return await interaction.response.send_message(
                "❌ 這個行動已完成或已失效。", ephemeral=True
            )
        if action_type == "time_wave":
            from .views import TimeWaveModeSelect

            view = discord.ui.View(timeout=300)
            view.add_item(TimeWaveModeSelect(self, player))
            return await interaction.response.send_message(
                "🌓 選擇增幅或削弱：", view=view, ephemeral=True
            )
        targets = self.get_action_targets(player, action_type)
        if not targets and action_type not in {"wolf_kill", "seer_check"}:
            self.role_actions[(player.id, action_type)] = {
                "type": action_type, "target": None, "skipped": True
            }
            await interaction.response.send_message(
                "💤 沒有合法目標，本夜自動跳過。", ephemeral=True
            )
            return await self.check_phase_1_end()
        action_view = discord.ui.View(timeout=300)
        action_view.add_item(NightTargetSelect(self, player, action_type))
        if player.role.optional_action:
            skip_button = discord.ui.Button(
                label="本夜不發動", style=discord.ButtonStyle.grey
            )

            async def skip_callback(inte):
                await self.handle_night_skip(inte, player, action_type)

            skip_button.callback = skip_callback
            action_view.add_item(skip_button)
        await interaction.response.send_message(
            f"**{self._night_action_label(action_type)}**：",
            view=action_view,
            ephemeral=True,
        )

    async def send_time_wave_target(self, interaction, player, mode):
        if (
            self.phase != PHASE_NIGHT_1
            or interaction.user.id != player.id
            or (player.id, "time_wave") not in self.get_required_night_tasks()
            or (player.id, "time_wave") in self.role_actions
            or mode not in {"boost", "weaken"}
            or player.role.state.get(f"{mode}_used")
        ):
            return await interaction.response.send_message(
                "❌ 這個時波操作已失效或該效果已用過。", ephemeral=True
            )
        view = discord.ui.View(timeout=300)
        view.add_item(NightTargetSelect(self, player, "time_wave", mode=mode))
        await interaction.response.send_message(
            f"選擇要**{'增幅' if mode == 'boost' else '削弱'}**的玩家：",
            view=view,
            ephemeral=True,
        )

    async def handle_night_skip(self, interaction, player, action_type):
        if (
            self.phase != PHASE_NIGHT_1
            or interaction.user.id != player.id
            or action_type not in self.get_pending_night_tasks(player)
            or not player.role.optional_action
        ):
            return await interaction.response.send_message(
                "❌ 這個跳過操作已失效。", ephemeral=True
            )
        self.role_actions[(player.id, action_type)] = {
            "type": action_type, "target": None, "skipped": True
        }
        await interaction.response.send_message("💤 本夜不發動技能。", ephemeral=True)
        await self.check_phase_1_end()

    async def handle_night_action(
        self, interaction, player, action_type, target_id, *, mode=None
    ):
        phase_2_actions = {"witch_skip", "lucky_check", "lucky_poison", "lucky_guard"}
        if action_type in phase_2_actions:
            if self.phase != PHASE_NIGHT_2:
                return await interaction.response.send_message(
                    "❌ 這個下半夜操作已失效。", ephemeral=True
                )
            return await self.skill_manager.handle_night_action(
                interaction, player, action_type, target_id
            )

        if (
            self.phase != PHASE_NIGHT_1
            or self.get_player(interaction.user.id) is not player
            or interaction.user.id != player.id
            or player.status != "alive"
            or action_type not in self.get_pending_night_tasks(player)
        ):
            return await interaction.response.send_message(
                "❌ 這個夜晚操作已失效或不屬於你。", ephemeral=True
            )

        target_ids = target_id if isinstance(target_id, list) else [target_id]
        if action_type in {"double_check", "fate_bind"} and len(target_ids) != 2:
            return await interaction.response.send_message(
                "❌ 此技能必須選擇兩名不同玩家。", ephemeral=True
            )
        if len(target_ids) > self.get_night_action_limit(player, action_type):
            return await interaction.response.send_message(
                "❌ 選擇的目標數超過本夜可行動次數。", ephemeral=True
            )
        legal_ids = {target.id for target in self.get_action_targets(player, action_type)}
        if any(target not in legal_ids and target != -1 for target in target_ids):
            return await interaction.response.send_message(
                "❌ 目標已失效或不符合技能限制。", ephemeral=True
            )
        if action_type == "time_wave" and (
            mode not in {"boost", "weaken"}
            or player.role.state.get(f"{mode}_used")
        ):
            return await interaction.response.send_message(
                "❌ 時波效果無效或已使用。", ephemeral=True
            )

        primary_target = target_ids[0]
        target = self.get_player(primary_target) if primary_target != -1 else None
        if action_type == "merchant_give":
            view = discord.ui.View(timeout=300)
            view.add_item(MerchantSkillSelect(self, player, primary_target))
            return await interaction.response.send_message(
                f"💰 要給 **{target.display_name}** 哪一個技能？",
                view=view,
                ephemeral=True,
            )
        if action_type == "devour":
            return await self._begin_devour(interaction, player, target)

        data = {
            "type": action_type,
            "target": target_ids if len(target_ids) > 1 else primary_target,
            "mode": mode,
        }
        self.role_actions[(player.id, action_type)] = data

        if action_type == "wolf_kill":
            self.wolf_votes[player.id] = target_ids
            target_names = [
                "空刀" if value == -1 else self.get_player(value).display_name
                for value in target_ids
            ]
            target_name = "、".join(target_names)
            message = f"🩸 你的狼刀票：**{target_name}**"
            self.log_event("wolf_vote", {"voter": player.display_name, "target": target_name})
        elif action_type in {"seer_check", "exact_check", "wolf_witch_check", "pure_white_check", "mirror_check"}:
            results = []
            for value in target_ids:
                checked = self.get_player(value) if value != -1 else None
                player.role.checked_targets.add(value)
                if value == -1:
                    result = "空驗"
                    name = "空驗"
                elif action_type == "seer_check":
                    result = "狼人" if checked.role.camp == CAMP_WOLF else "好人"
                    name = checked.display_name
                else:
                    result = checked.role.name
                    name = checked.display_name
                results.append(f"{name}：{result}")
                self.log_event(action_type, {"target": name, "result": result})
            message = "🔮 查驗結果：**" + "；".join(results) + "**"
        elif action_type == "double_check":
            pair = [self.get_player(target_value) for target_value in target_ids]
            result = "至少一名狼人" if any(p.role.camp == CAMP_WOLF for p in pair) else "兩人皆為好人"
            message = f"🔮 **{pair[0].display_name}、{pair[1].display_name}**：{result}"
            self.log_event(action_type, {"targets": [p.display_name for p in pair], "result": result})
        elif action_type == "mimic":
            message = f"🎭 模仿目標 **{target.display_name}** 的身分是：**{target.role.name}**"
            self.log_event(
                "mimic",
                {"actor": player.display_name, "target": target.display_name, "role": target.role.name},
            )
        else:
            names = "、".join(self.get_player(value).display_name for value in target_ids)
            suffix = "（增幅）" if mode == "boost" else "（削弱）" if mode == "weaken" else ""
            message = f"✅ **{self._night_action_label(action_type)}**已選擇：**{names}**{suffix}"
            self.log_event(action_type, {"actor": player.display_name, "target": names, "mode": mode})

        if action_type in {"guard", "fear", "confuse", "devour", "light_guard"}:
            player.role.last_target = target_ids if len(target_ids) > 1 else primary_target
        if action_type == "dream":
            self.current_dream_target = primary_target
        if action_type == "time_wave":
            player.role.state[f"{mode}_used"] = True
            if mode == "boost":
                boosted = self.get_player(primary_target)
                if boosted and boosted.role.camp == CAMP_WOLF:
                    self.extra_wolf_kill = True
                else:
                    self.night_action_bonuses[primary_target] = 1
        if action_type == "confuse":
            player.role.used_skill = True
        if action_type == "awakened_charm":
            player.role.state["cooldown_until"] = self.round_num + 1
        if action_type == "claw_pass":
            player.role.shoot_count -= 1
            target.role.can_shoot = True
            target.role.shoot_count = getattr(target.role, "shoot_count", 0) + 1
            target.role.state["awakened_claws"] = target.role.state.get("awakened_claws", 0) + 1
        if action_type == "mimic_witch":
            player.role.state["mimic_witch_used"] = True
        if action_type == "choose_idol":
            player.role.state["idol_id"] = primary_target
            player.role.used_skill = True
        if action_type == "convert":
            player.role.used_skill = True
            try:
                await target.user.send(
                    "🗿 你已被覺醒石像鬼選為轉化者；本夜結束後將加入狼人陣營，"
                    "原技能會失效，下一夜才與狼隊相認。"
                )
            except (AttributeError, discord.HTTPException):
                pass
        if action_type == "awakened_guard":
            player.role.last_target = primary_target
            player.role.state["last_guard_round"] = self.round_num
            self.awakened_guard_target = primary_target
            self.awakened_guard_period = "night"
        if action_type == "dream_speech":
            player.role.last_target = primary_target

        await interaction.response.send_message(message, ephemeral=True)
        await self.check_phase_1_end()

    async def _begin_devour(self, interaction, actor, victim):
        """蝕日侍女先吞噬技能，再選擇該技能本夜的使用方式。"""
        if victim is None or victim.role.camp == CAMP_WOLF:
            return await interaction.response.send_message(
                "❌ 吞噬目標必須是存活好人。", ephemeral=True
            )

        if isinstance(victim.role, Witch):
            view = discord.ui.View(timeout=300)
            save_button = discord.ui.Button(
                label="使用解藥", style=discord.ButtonStyle.success, emoji="💊"
            )
            poison_button = discord.ui.Button(
                label="使用毒藥", style=discord.ButtonStyle.danger, emoji="☠️"
            )

            async def save_callback(inte):
                await self._complete_devour(
                    inte, actor, victim, "witch_save", None
                )

            async def poison_callback(inte):
                await self._send_devour_target_panel(
                    inte, actor, victim, "witch_poison"
                )

            save_button.callback = save_callback
            poison_button.callback = poison_callback
            view.add_item(save_button)
            view.add_item(poison_button)
            return await interaction.response.send_message(
                f"🌘 已選擇吞噬 **{victim.display_name}** 的女巫技能；要使用哪瓶藥？",
                view=view,
                ephemeral=True,
            )

        copied_action = {
            ROLE_SEER: "seer_check",
            ROLE_DREAMER: "dream",
            ROLE_LIGHT_EARL: "light_guard",
        }.get(victim.role.name)
        if copied_action:
            return await self._send_devour_target_panel(
                interaction, actor, victim, copied_action
            )
        await self._complete_devour(
            interaction, actor, victim, "no_skill", None
        )

    async def _send_devour_target_panel(
        self, interaction, actor, victim, copied_action
    ):
        targets = self.get_action_targets(actor, copied_action)
        if not targets:
            return await self._complete_devour(
                interaction, actor, victim, "no_target", None
            )
        select = discord.ui.Select(
            placeholder="🌘 選擇吞噬技能的施放目標...",
            options=[
                discord.SelectOption(label=target.display_name, value=str(target.id))
                for target in targets
            ],
        )
        view = discord.ui.View(timeout=300)

        async def callback(inte):
            await self._complete_devour(
                inte, actor, victim, copied_action, int(select.values[0])
            )

        select.callback = callback
        view.add_item(select)
        await interaction.response.send_message(
            f"🌘 已吞噬 **{victim.display_name}** 的技能，請選擇施放目標：",
            view=view,
            ephemeral=True,
        )

    async def _complete_devour(
        self, interaction, actor, victim, copied_action, use_target
    ):
        if (
            self.phase != PHASE_NIGHT_1
            or interaction.user.id != actor.id
            or actor.status != "alive"
            or (actor.id, "devour") not in self.get_required_night_tasks()
            or (actor.id, "devour") in self.role_actions
            or victim.status != "alive"
            or victim.role.camp == CAMP_WOLF
        ):
            return await interaction.response.send_message(
                "❌ 這個吞噬操作已失效。", ephemeral=True
            )
        victim.role.disabled = True
        actor.role.last_target = victim.id
        self.role_actions[(actor.id, "devour")] = {
            "type": "devour",
            "target": victim.id,
            "copied_action": copied_action,
            "use_target": use_target,
        }
        result = ""
        if copied_action == "seer_check" and use_target:
            checked = self.get_player(use_target)
            camp = "狼人" if checked.role.camp == CAMP_WOLF else "好人"
            result = f" 查驗 **{checked.display_name}** 的結果為：**{camp}**。"
        await interaction.response.send_message(
            f"🌘 已吞噬 **{victim.display_name}** 的技能並完成施放。{result}",
            ephemeral=True,
        )
        self.log_event(
            "devour",
            {
                "actor": actor.display_name,
                "victim": victim.display_name,
                "copied_action": copied_action,
                "target": self.get_player(use_target).display_name if use_target else None,
            },
        )
        await self.check_phase_1_end()

    async def handle_merchant_skill(self, interaction, player, target_id, skill):
        target = self.get_player(target_id)
        if (
            self.phase != PHASE_NIGHT_1
            or interaction.user.id != player.id
            or self.get_player(player.id) is not player
            or player.status != "alive"
            or not isinstance(player.role, Merchant)
            or player.role.used_skill
            or (player.id, "merchant_give") in self.role_actions
            or target is None
            or target.status != "alive"
            or target.id == player.id
            or skill not in {"check", "poison", "guard"}
        ):
            return await interaction.response.send_message(
                "❌ 這個商人操作已失效。", ephemeral=True
            )
        self.role_actions[(player.id, "merchant_give")] = {
            "type": "merchant_give", "target": target_id, "skill": skill
        }
        await self.skill_manager.handle_merchant_skill(interaction, player, target_id, skill)

    # --- Phase 1 結束檢查 ---
    async def check_phase_1_end(self):
        if self.phase != PHASE_NIGHT_1:
            return
        required = self.get_required_night_tasks()
        if required.issubset(self.role_actions):
            active_wolf_ids = {wolf.id for wolf in self.get_active_wolves()}
            if self.wolf_votes and any(
                (wolf_id, "wolf_kill") in required for wolf_id in active_wolf_ids
            ):
                vote_lists = [
                    targets if isinstance(targets, list) else [targets]
                    for wolf_id, targets in self.wolf_votes.items()
                    if wolf_id in active_wolf_ids
                    and (wolf_id, "wolf_kill") in required
                ]
                slot_count = 2 if self.extra_wolf_kill else 1
                self.wolf_targets = []
                for slot in range(slot_count):
                    slot_votes = [
                        targets[slot] for targets in vote_lists
                        if len(targets) > slot
                    ]
                    if not slot_votes:
                        continue
                    most = Counter(slot_votes).most_common()
                    max_votes = most[0][1]
                    candidates = [target for target, count in most if count == max_votes]
                    self.wolf_targets.append(random.choice(candidates))
                self.wolf_target = self.wolf_targets[0] if self.wolf_targets else -1
            else:
                self.wolf_target = -1
                self.wolf_targets = []

            target_names = [
                self.get_player(target_id).display_name
                if self.get_player(target_id) else "空刀"
                for target_id in self.wolf_targets or [self.wolf_target]
            ]
            self.log_event(
                "wolf_kill",
                {"target": "、".join(target_names)},
            )

            await self.start_night_phase_2()

    # --- 下半夜 (Phase 2) ---
    async def start_night_phase_2(self):
        alive_witch = [
            player
            for player in self.get_alive_role(Witch)
            if not player.role.disabled
            and (player.role.has_antidote or player.role.has_poison)
        ]
        alive_lucky = [
            p
            for p in self.get_alive_players()
            if p.id == self.lucky_data["user_id"]
        ]
        has_witch = bool(alive_witch) and not self.good_skills_sealed
        has_lucky = bool(alive_lucky)
        
        if not has_witch and not has_lucky:
            return await self.start_day()

        async with self._state_lock:
            if self.phase != PHASE_NIGHT_1:
                return False
            self.phase = PHASE_NIGHT_2
            self.night_actions.clear()
        
        view = discord.ui.View(timeout=None)
        btn = discord.ui.Button(label="下半夜行動", style=discord.ButtonStyle.primary, emoji="✨")
        
        async def p2_action(interaction):
            if self.phase != PHASE_NIGHT_2:
                return await interaction.response.send_message(
                    "❌ 這個下半夜行動按鈕已失效。", ephemeral=True
                )
            p = self.get_player(interaction.user.id)
            if not p or p.status != "alive": return await interaction.response.send_message("已死", ephemeral=True)
            
            if isinstance(p.role, Witch) and not self.good_skills_sealed:
                if self.is_phase_2_done(p):
                    return await interaction.response.send_message("已完成本夜行動", ephemeral=True)
                await interaction.response.send_message(
                    self.get_witch_info_msg(), 
                    view=WitchView(self, p), 
                    ephemeral=True
                )
            elif self.lucky_data["user_id"] == p.id:
                if self.lucky_data["target"] is not None: return await interaction.response.send_message("技能已用", ephemeral=True)
                skill = self.lucky_data["skill"]
                skill_name = {
                    "check": "查驗",
                    "poison": "毒藥",
                    "guard": "守衛",
                }.get(skill, skill)
                await interaction.response.send_message(
                    f"✨ 你是幸運兒！獲得 **{skill_name}** 技能！",
                    view=LuckyView(self, p, skill), 
                    ephemeral=True
                )
            else:
                await interaction.response.send_message("💤 繼續睡覺", ephemeral=True)

        btn.callback = p2_action
        view.add_item(btn)

        roles_str = []
        if has_witch: roles_str.append("女巫")
        if has_lucky: roles_str.append("幸運兒")

        await self.channel.send(
            embed=discord.Embed(
                title=f"🌙 第 {self.round_num} 夜｜下半夜",
                description=(
                    f"等待 **{'、'.join(roles_str)}** 完成行動。\n"
                    "點擊按鈕後只會看到自己的技能面板。"
                ),
                color=discord.Color.purple(),
            ),
            view=view,
        )
        
        return True

    def get_witch_info_msg(self):
        targets = self.wolf_targets or [self.wolf_target]
        names = [
            self.get_player(target_id).display_name
            for target_id in targets
            if target_id not in {-1, None} and self.get_player(target_id)
        ]
        return f"今晚狼襲目標：**{'、'.join(names) if names else '無人'}**。"

    def is_phase_2_done(self, player):
        if player.id in self.night_actions:
            return True
        quota = 1 + int(self.night_action_bonuses.get(player.id, 0) > 0)
        return self.phase2_action_counts[player.id] >= quota

    def record_phase_2_action(self, player):
        self.phase2_action_counts[player.id] += 1
        quota = 1 + int(self.night_action_bonuses.get(player.id, 0) > 0)
        has_resource = bool(player.role.has_antidote or player.role.has_poison)
        if self.phase2_action_counts[player.id] >= quota or not has_resource:
            self.night_actions.add(player.id)

    # --- 委派技能邏輯 ---
    async def handle_witch_save(self, interaction, player):
        await self.skill_manager.handle_witch_save(interaction, player)

    async def send_witch_poison_select(self, interaction, player):
        await self.skill_manager.send_witch_poison_select(interaction, player)

    async def check_phase_2_end(self):
        if self.phase != PHASE_NIGHT_2:
            return
        alive_witches = [
            player
            for player in self.get_alive_role(Witch)
            if not player.role.disabled
            and (player.role.has_antidote or player.role.has_poison)
        ]
        witch_done = not alive_witches or self.is_phase_2_done(alive_witches[0])
        
        lucky_done = True
        lid = self.lucky_data["user_id"]
        if lid:
            lp = self.get_player(lid)
            if lp and lp.status == "alive" and self.lucky_data["target"] is None:
                lucky_done = False
                
        if witch_done and lucky_done:
            await self.start_day()

    # ==========================
    #      天亮 (Day)
    # ==========================
    async def start_day(self):
        async with self._state_lock:
            if (
                self.phase not in {PHASE_NIGHT_1, PHASE_NIGHT_2}
                or self._resolving_day
            ):
                return False
            self._resolving_day = True

        try:
            dream_speech_kills = await self._collect_awakened_dreamer_kills()
        except BaseException:
            async with self._state_lock:
                self._resolving_day = False
            raise

        async with self._state_lock:
            if self.phase not in {PHASE_NIGHT_1, PHASE_NIGHT_2}:
                self._resolving_day = False
                return False
            self.phase = PHASE_DAY
            self._resolving_day = False
            self.votes = {}
            self.stop_votes = set()
            self._vote_tally_started = False
        
        await AudioManager.stop(self.channel)
        
        if self.wolf_thread:
            try:
                await self.wolf_thread.delete()
            except discord.HTTPException:
                log.warning("無法刪除狼人討論串", exc_info=True)
            self.wolf_thread = None

        deaths = []
        death_causes = {}
        notices = []
        disabled_ids = self._disabled_night_ids()

        def action_entries(action_type):
            return [
                (self.get_player(actor_id), data)
                for (actor_id, stored_type), data in self.role_actions.items()
                if stored_type == action_type
                and actor_id not in disabled_ids
                and not data.get("skipped")
            ]

        # 夜間覺醒守護只有在技能未被封鎖時才生效，效果延續至本日結束。
        awakened_guard_entries = action_entries("awakened_guard")
        if awakened_guard_entries:
            self.awakened_guard_target = awakened_guard_entries[0][1]["target"]
            self.awakened_guard_period = "night"
        elif self.awakened_guard_period == "night":
            self.awakened_guard_target = None
            self.awakened_guard_period = None

        # 覺醒石像鬼首夜轉化相鄰玩家；轉化者下一夜才與狼隊相認。
        for actor, data in action_entries("convert"):
            target = self.get_player(data["target"])
            if not target or target.status != "alive" or target.role.camp == CAMP_WOLF:
                continue
            original_role = target.role.name
            target.role.camp = CAMP_WOLF
            target.role.disabled = True
            target.role.night_action = None
            target.role.can_shoot = False
            target.role.shoot_count = 0
            target.role.can_self_destruct = True
            target.role.joins_wolf_vote = False
            target.role.isolated_wolf = True
            target.role.state["converted_from"] = original_role
            target.role.state["wolf_reveal_round"] = self.round_num + 1
            target.role.description = (
                f"原身分為 {original_role}；已被覺醒石像鬼轉化，原技能失效，"
                "下一夜與狼隊相認。"
            )
            self.log_event(
                "awakened_gargoyle_convert",
                {"actor": actor.display_name, "target": target.display_name, "original_role": original_role},
            )

        # 蝕時狼妃封鎖：好人的查驗、毒藥、守護若指向封鎖者會反彈。
        block_entries = action_entries("block")
        blocked_id = block_entries[0][1]["target"] if block_entries else None

        def reflected_target(actor, action_type, target_id):
            reflected_actions = {
                "seer_check", "exact_check", "pure_white_check", "mirror_check",
                "double_check", "guard", "dream", "light_guard", "secret_guard",
                "witch_poison",
            }
            if (
                blocked_id is not None
                and action_type in reflected_actions
                and actor
                and actor.role.camp != CAMP_WOLF
                and (
                    target_id == blocked_id
                    or isinstance(target_id, list) and blocked_id in target_id
                )
            ):
                wolf = block_entries[0][0]
                wolf.role.disabled = True
                notices.append(f"⏳ 蝕時封鎖觸發，{actor.role.name} 的技能反彈。")
                return actor.id
            return target_id

        def target_values(value):
            return value if isinstance(value, list) else [value]

        guard_targets = set()
        for actor, data in action_entries("guard"):
            guard_targets.update(
                target_values(reflected_target(actor, "guard", data["target"]))
            )
        if self.lucky_data["skill"] == "guard" and self.lucky_data["target"]:
            guard_targets.add(self.lucky_data["target"])

        all_damage_guards = set()
        for action_type in ("dream", "light_guard", "secret_guard"):
            for actor, data in action_entries(action_type):
                target_id = reflected_target(actor, action_type, data["target"])
                all_damage_guards.update(target_values(target_id))
                if action_type == "secret_guard":
                    actor.role.secret_body = True
        for _, data in action_entries("devour"):
            if data.get("copied_action") in {"dream", "light_guard"} and data.get("use_target"):
                all_damage_guards.add(data["use_target"])

        dream_speech_guards = {
            data["target"] for _, data in action_entries("dream_speech")
        }
        secret_guard_targets = {
            actor.id: data["target"]
            for actor, data in action_entries("secret_guard")
            if actor
        }
        deferred_secret_self_damage = {}
        resolving_secret_fallback = False

        # 魅惑在傷害結算前建立，覺醒狼美人的挽歌幻象才能替死。
        charm_actions = action_entries("charm") + action_entries("awakened_charm")
        if charm_actions:
            charmer, charm_data = charm_actions[0]
            confused = any(
                fox_data["target"] == charmer.id
                for _, fox_data in action_entries("confuse")
            )
            self.charmed_target = None if confused else charm_data["target"]

        raw_wolf_targets = self.wolf_targets or [self.wolf_target]
        night_specials_suppressed = any(
            isinstance(getattr(self.get_player(target_id), "role", None), AwakenedHunter)
            and target_id not in guard_targets
            and target_id not in all_damage_guards
            for target_id in raw_wolf_targets
            if isinstance(target_id, int) and target_id != -1
        ) or any(
            isinstance(getattr(self.get_player(target_id), "role", None), AwakenedHunter)
            for target_id in (
                self.witch_poison_target,
                self.lucky_data.get("target")
                if self.lucky_data.get("skill") == "poison" else None,
            )
            if isinstance(target_id, int)
        )

        def add_death(user_id, cause, damage_type="skill"):
            nonlocal resolving_secret_fallback
            if not isinstance(user_id, int):
                return False
            player = self.get_player(user_id)
            if player is None or player.status != "alive":
                return False
            if self._is_awakened_guarded(player):
                notices.append(f"🛡️ {player.display_name} 受到覺醒守護，免於出局。")
                return False
            if user_id in dream_speech_guards and damage_type != "awakened_dream":
                notices.append(f"🌌 {player.display_name} 身處夢語，免疫了夜間傷害。")
                return False
            protected_target = secret_guard_targets.get(user_id)
            if (
                not resolving_secret_fallback
                and protected_target is not None
                and protected_target != user_id
                and player.role.secret_body
                and protected_target in all_damage_guards
            ):
                deferred_secret_self_damage.setdefault(user_id, []).append(
                    (cause, damage_type)
                )
                return False
            if (
                isinstance(player.role, AwakenedWolfBeauty)
                and not player.role.state.get("illusion_used")
                and self.charmed_target
                and not night_specials_suppressed
            ):
                substitute = self.get_player(self.charmed_target)
                if substitute and substitute.status == "alive":
                    player.role.state["illusion_used"] = True
                    deaths.append(substitute.id)
                    death_causes.setdefault(substitute.id, []).append("挽歌幻象替死")
                    notices.append(
                        f"✨ 覺醒狼美人的挽歌幻象發動，{substitute.display_name} 替代其出局。"
                    )
                    return False
            if damage_type == "wolf" and user_id in guard_targets:
                notices.append(f"🛡️ {player.display_name} 擋下了狼襲。")
                return False
            if user_id in all_damage_guards and damage_type not in {"dream", "follow", "crimson"}:
                all_damage_guards.discard(user_id)
                protector = next(
                    (
                        actor for action in ("secret_guard",)
                        for actor, data in action_entries(action)
                        if data["target"] == user_id
                    ),
                    None,
                )
                if protector:
                    protector.role.secret_body = False
                    protector.role.used_skill = True
                notices.append(f"✨ {player.display_name} 抵消了一次夜間傷害。")
                return False
            if damage_type == "poison" and isinstance(player.role, DemonHunter):
                notices.append(f"🏹 {player.display_name} 免疫了毒藥。")
                return False
            if isinstance(player.role, EvilKnight):
                notices.append(f"🛡️ {player.display_name} 免疫夜間死亡。")
                return False
            deaths.append(user_id)
            causes = death_causes.setdefault(user_id, [])
            if cause not in causes:
                causes.append(cause)
            return True

        # 恐懼或子狐迷惑狼人會令狼隊空刀。
        wolf_blocked = False
        for _, data in action_entries("fear") + action_entries("confuse"):
            target = self.get_player(data["target"])
            if target and target.role.camp == CAMP_WOLF:
                wolf_blocked = True
        wolf_attack_targets = self.wolf_targets or [self.wolf_target]
        if any(
            data.get("copied_action") == "witch_save"
            for _, data in action_entries("devour")
        ):
            wolf_attack_targets = wolf_attack_targets[1:]
        if not wolf_blocked:
            for wolf_target in wolf_attack_targets:
                if isinstance(wolf_target, int) and wolf_target != -1:
                    add_death(wolf_target, "狼人殺害", "wolf")
        if self.crimson_last_stand:
            add_death(self.crimson_last_stand, "赤月使徒延時出局", "crimson")
            self.crimson_last_stand = None

        # 惡夜騎士的反傷只觸發一次。
        evil_knights = self.get_alive_role(EvilKnight)
        if evil_knights and not evil_knights[0].role.used_skill:
            evil = evil_knights[0]
            checked_by = [
                actor for action in ("seer_check", "pure_white_check", "mirror_check")
                for actor, data in action_entries(action)
                if reflected_target(actor, action, data["target"]) == evil.id
            ]
            if checked_by:
                evil.role.used_skill = True
                add_death(checked_by[0].id, "惡夜騎士反傷", "reflect")

        if self.witch_poison_target:
            witches = self.get_alive_role(Witch)
            witch = witches[0] if witches else None
            poison_target = reflected_target(
                witch, "witch_poison", self.witch_poison_target
            )
            poison_player = self.get_player(poison_target)
            if isinstance(getattr(poison_player, "role", None), EvilKnight):
                evil = poison_player
                if not evil.role.used_skill and witch:
                    evil.role.used_skill = True
                    add_death(witch.id, "惡夜騎士反傷", "reflect")
            else:
                add_death(poison_target, "女巫毒殺", "poison")

        if self.lucky_data["skill"] == "poison" and self.lucky_data["target"]:
            add_death(self.lucky_data["target"], "幸運兒毒殺", "poison")
        for _, data in action_entries("devour"):
            if data.get("copied_action") == "witch_poison" and data.get("use_target"):
                add_death(data["use_target"], "蝕日侍女吞噬毒殺", "poison")
        for _, data in action_entries("mimic_witch"):
            add_death(data["target"], "覺醒隱狼模仿毒殺", "poison")

        # 純白之女、狼巫、獵魔人與連續攝夢。
        if self.round_num >= 2:
            for actor, data in action_entries("pure_white_check"):
                target_id = reflected_target(actor, "pure_white_check", data["target"])
                target = self.get_player(target_id)
                if target and target.role.camp == CAMP_WOLF:
                    add_death(target_id, "純白之女查殺", "skill")
            for _, data in action_entries("wolf_witch_check"):
                target = self.get_player(data["target"])
                if isinstance(getattr(target, "role", None), PureWhite):
                    add_death(target.id, "狼巫查殺", "skill")

        for actor, data in action_entries("hunt"):
            target = self.get_player(data["target"])
            if self.pending_night_servant and self.pending_night_servant["target"] == target.id:
                self.pending_night_servant = None
                notices.append(f"🏹 {target.display_name} 的夜僕狀態被解除。")
            elif target.role.camp == CAMP_WOLF:
                add_death(target.id, "獵魔人狩獵", "hunt")
            else:
                add_death(actor.id, "獵魔人狩獵反噬", "hunt")

        for target_id in dream_speech_kills:
            add_death(target_id, "覺醒攝夢人夢語出局", "awakened_dream")

        if (
            self.current_dream_target is not None
            and self.current_dream_target == self.previous_dream_target
        ):
            add_death(self.current_dream_target, "攝夢人連續攝夢", "dream")

        # 上一輪建立的夜僕在本輪天亮時死亡；本輪新指定的夜僕延至下一夜。
        if (
            self.pending_night_servant
            and self.pending_night_servant["due_round"] <= self.round_num
        ):
            add_death(self.pending_night_servant["target"], "夜僕之擁", "servant")
            self.pending_night_servant = None
        servant_actions = action_entries("night_servant")
        if servant_actions and not self.pending_night_servant:
            self.pending_night_servant = {
                "target": servant_actions[0][1]["target"],
                "due_round": self.round_num + 1,
            }

        # 記錄本夜魅惑、命運綁定與技能吞噬。
        bind_actions = action_entries("fate_bind")
        if bind_actions and not self.fate_triggered:
            self.fate_pair = tuple(bind_actions[0][1]["target"])
        for _, data in action_entries("devour"):
            target = self.get_player(data["target"])
            if target and target.role.camp != CAMP_WOLF:
                target.role.disabled = True
                notices.append(f"🌘 {target.display_name} 的角色技能已被吞噬。")

        for actor, data in action_entries("mimic"):
            target = self.get_player(data["target"])
            if not target:
                continue
            copied_action = target.role.night_action
            if isinstance(target.role, Witch):
                copied_action = "mimic_witch"
            actor.role.state["mimicked_role"] = target.role.name
            actor.role.name = f"覺醒隱狼（模仿{target.role.name}）"
            actor.role.description = f"已模仿 {target.role.name}；保留狼人勝利目標並取得其技能。"
            actor.role.night_action = copied_action
            actor.role.action_from_round = 1
            actor.role.optional_action = target.role.optional_action
            actor.role.isolated_wolf = False
            actor.role.joins_wolf_vote = True
            if target.role.can_shoot:
                actor.role.can_shoot = True
                actor.role.shoot_count = max(1, target.role.shoot_count)
            notices.append(f"🎭 覺醒隱狼已完成模仿，從下夜起取得新技能。")

        # 奇跡商人把技能給狼人時遭到反噬。
        if self.lucky_data["user_id"]:
            lucky_player = self.get_player(self.lucky_data["user_id"])
            if lucky_player and lucky_player.role.camp == CAMP_WOLF:
                merchants = self.get_alive_role(Merchant)
                if merchants:
                    add_death(merchants[0].id, "奇跡商人反噬", "skill")

        # 攝夢人死亡會令本夜夢遊者殉死；尋香綁定全局觸發一次。
        dreamers = self.get_alive_role(Dreamer)
        if dreamers and dreamers[0].id in deaths and self.current_dream_target:
            add_death(self.current_dream_target, "攝夢人殉夢", "follow")
        if self.fate_pair and not self.fate_triggered:
            left, right = self.fate_pair
            if left in deaths:
                add_death(right, "尋香命運綁定", "follow")
                self.fate_triggered = True
            elif right in deaths:
                add_death(left, "尋香命運綁定", "follow")
                self.fate_triggered = True

        # 保護目標整夜沒有承受傷害時，秘密之身改為替覺醒愚者自己擋一次。
        resolving_secret_fallback = True
        for actor_id, pending_damage in deferred_secret_self_damage.items():
            actor = self.get_player(actor_id)
            protected_target = secret_guard_targets.get(actor_id)
            if (
                actor
                and actor.role.secret_body
                and protected_target in all_damage_guards
                and pending_damage
            ):
                all_damage_guards.discard(protected_target)
                actor.role.secret_body = False
                actor.role.used_skill = True
                pending_damage = pending_damage[1:]
                notices.append(
                    f"🃏 {actor.display_name} 的秘密之身轉而為自己抵消一次傷害。"
                )
            for cause, damage_type in pending_damage:
                add_death(actor_id, cause, damage_type)
        resolving_secret_fallback = False

        self.deaths_tonight = []
        for user_id in dict.fromkeys(deaths):
            player = self.get_player(user_id)
            if isinstance(player.role, WhiteCat) and not player.role.used_skill:
                player.role.used_skill = True
                self.pending_white_cats.add(player.id)
                notices.append(f"🐱 {player.display_name} 翻牌續命至下一次投票結束。")
                continue
            player.status = "dead"
            self.deaths_tonight.append(user_id)

        for user_id in self.deaths_tonight:
            player = self.get_player(user_id)
            cause = "、".join(death_causes.get(user_id, ["夜間出局"]))
            self._resolve_awakened_lonely_idol(player, cause)

        self.previous_dream_target = self.current_dream_target
        self.good_skills_sealed = False

        # --- 公布結果 ---
        msg = ""
        if not self.deaths_tonight:
            msg += "✨ 昨晚是個平安夜。"
        else:
            msg += "**昨晚死亡名單**\n"
            for uid in self.deaths_tonight:
                p = self.get_player(uid)
                msg += f"💀 **{p.display_name}**\n"
                cause = "、".join(death_causes.get(uid, ["未知原因"]))
                self.log_event("night_death", {"name": p.display_name, "role": p.role.name, "cause": cause})

        await self._apply_day_mutes()

        bear_notice = self._get_bear_notice()
        if bear_notice:
            notices.append(bear_notice)
        if notices:
            msg += "\n" + "\n".join(notices)
        if self.pending_role_notices:
            msg += "\n" + "\n".join(self.pending_role_notices)
            self.pending_role_notices.clear()
        day_embed = discord.Embed(
            title=f"🌅 第 {self.round_num} 天｜天亮",
            description=msg,
            color=discord.Color.gold(),
        )
        day_embed.add_field(
            name="目前存活",
            value=f"{len(self.get_alive_players())} / {len(self.players)} 人",
            inline=True,
        )
        day_embed.set_footer(text="夜間技能已完成結算，準備進入白天討論")
        await self.channel.send(embed=day_embed)

        # --- 獵人/狼王開槍檢查 ---
        shooters = self.get_shooter_deaths()
        if shooters:
            self.phase = PHASE_SHOOT
            self.pending_shooters = [
                player.id for player in shooters
                for _ in range(max(1, player.role.shoot_count))
            ]
            self.after_shoot = "day_vote"
            await self._prompt_next_shooter()
            return

        winner = self.check_winner()
        if winner:
            return await self.end_game(winner)

        # --- 進入投票 ---
        await self._send_voting_view()
        return True

    def _get_bear_notice(self):
        bears = self.get_alive_role(Bear)
        if not bears:
            return None
        bear = bears[0]
        alive_order = [player for player in self.players if player.status == "alive"]
        if len(alive_order) < 2 or bear not in alive_order:
            return "🐻 熊沒有咆哮。"
        index = alive_order.index(bear)
        neighbours = {
            alive_order[(index - 1) % len(alive_order)].id,
            alive_order[(index + 1) % len(alive_order)].id,
        }
        roars = any(
            player.id in neighbours and player.role.camp == CAMP_WOLF
            for player in alive_order
        )
        return "🐻 **熊咆哮了！**" if roars else "🐻 熊沒有咆哮。"

    def get_shooter_deaths(self):
        poisoned_ids = []
        if self.witch_poison_target: poisoned_ids.append(self.witch_poison_target)
        if self.lucky_data["skill"] == "poison": poisoned_ids.append(self.lucky_data["target"])

        shooters = []
        for uid in self.deaths_tonight:
            p = self.get_player(uid)
            if (
                p and p.role.can_shoot
                and (isinstance(p.role, AwakenedHunter) or uid not in poisoned_ids)
            ):
                shooters.append(p)
        return shooters

    def check_shooter_death(self):
        """向下相容：回傳今晚第一位可開槍的玩家。"""
        shooters = self.get_shooter_deaths()
        return shooters[0] if shooters else None

    async def _send_voting_view(self):
        if self.phase != PHASE_DAY:
            return
        embed = discord.Embed(
            title=f"☀️ 第 {self.round_num} 天｜討論與放逐",
            description=(
                "完成討論後，點擊玩家名稱投票。每位存活且有投票權的玩家限投一次。\n"
                "特殊白天技能必須在第一張票投出前使用。"
            ),
            color=discord.Color.orange(),
        )
        embed.add_field(
            name="可投票人數",
            value=str(len([p for p in self.get_alive_players() if not p.role.vote_disabled])),
            inline=True,
        )
        embed.add_field(name="已投票", value=str(len(self.votes)), inline=True)
        await self.channel.send(embed=embed, view=VotingView(self))

    async def _prompt_next_shooter(self):
        if self.phase != PHASE_SHOOT or not self.pending_shooters:
            return
        shooter = self.get_player(self.pending_shooters[0])
        if shooter is None:
            self.pending_shooters.pop(0)
            return await self._finish_shoot_sequence()
        await self.channel.send(
            f"🔫 **{shooter.role.name} {shooter.display_name} 發動技能！** "
            "請本人選擇目標或放棄開槍。",
            view=ShooterView(self, shooter),
        )

    # ==========================
    #      投票與結算
    # ==========================
    async def handle_vote(self, interaction, target_id):
        async with self._state_lock:
            if self.phase != PHASE_DAY:
                return await interaction.response.send_message(
                    "❌ 這個投票面板已失效。", ephemeral=True
                )
            if self.pending_awakened_white_wolf:
                return await interaction.response.send_message(
                    "❌ 覺醒白狼王的引爆尚未結算，暫時不能投票。", ephemeral=True
                )
            p = self.get_player(interaction.user.id)
            target_p = self.get_player(target_id)
            if not p or p.status != "alive":
                return await interaction.response.send_message(
                    "死人或非玩家無法投票。", ephemeral=True
                )
            if p.role.vote_disabled:
                return await interaction.response.send_message(
                    "❌ 你已因愚者翻牌而失去投票權。", ephemeral=True
                )
            if not target_p or target_p.status != "alive":
                return await interaction.response.send_message(
                    "❌ 投票目標已失效。", ephemeral=True
                )
            if p.id in self.votes:
                return await interaction.response.send_message(
                    "❌ 你已經投過票了！", ephemeral=True
                )

            self.votes[p.id] = target_id
            eligible_voters = [
                player for player in self.get_alive_players()
                if not player.role.vote_disabled
            ]
            should_tally = (
                len(self.votes) >= len(eligible_voters)
                and not self._vote_tally_started
            )
            if should_tally:
                self._vote_tally_started = True

        await interaction.response.send_message(f"🗳️ 投給了 **{target_p.display_name}**", ephemeral=True)
        
        # 發送公開訊息讓大家知道有人投票了
        await self.channel.send(
            f"🗳️ **{p.display_name}** 已投票 "
            f"({len(self.votes)}/{len(eligible_voters)})"
        )
        
        if should_tally:
            await self.tally_votes()

    async def tally_votes(self):
        if self.phase != PHASE_DAY:
            return
        # [新增] 公布投票結果
        vote_reveal = ""
        for voter_id, target_id in self.votes.items():
            voter = self.get_player(voter_id)
            target = self.get_player(target_id)
            if voter and target:
                vote_reveal += f"• {voter.display_name} → **{target.display_name}**\n"
        
        await self.channel.send(
            embed=discord.Embed(
                title="📊 放逐投票結果",
                description=vote_reveal or "沒有有效票。",
                color=discord.Color.orange(),
            )
        )
        
        self.cats_due_after_vote = set(self.pending_white_cats)
        counts = Counter(self.votes.values())
        if not counts:
            await self.channel.send("無人投票，直接入夜。")
            return await self._finish_vote_without_exile()

        most = counts.most_common()
        max_v = most[0][1]
        cands = [k for k, v in most if v == max_v]

        if len(cands) > 1:
            await self.channel.send(f"⚖️ 平票 ({max_v}票)，無人被處決。")
            await self._finish_vote_without_exile()
        else:
            dead_id = cands[0]
            player = self.get_player(dead_id)
            if player is None or player.status != "alive":
                await self.channel.send("⚠️ 投票目標已失效，本輪直接入夜。")
                return await self._finish_vote_without_exile()
            princes = [
                prince for prince in self.get_alive_role(OrderPrince)
                if not prince.role.used_skill
            ]
            if princes:
                return await self._prompt_order_prince(princes[0], player)
            if isinstance(player.role, Pufferfish) and not player.role.used_skill:
                return await self._prompt_pufferfish(player)
            await self._resolve_exile(player)

    async def _finalize_due_white_cats(self):
        for cat_id in list(self.cats_due_after_vote):
            cat = self.get_player(cat_id)
            if cat and cat.status == "alive":
                cat.status = "dead"
                self.pending_white_cats.discard(cat_id)
                await self.channel.send(
                    f"🐱 **{cat.display_name}** 的白貓續命結束，正式出局。"
                )
                self.log_event(
                    "vote_death",
                    {"name": cat.display_name, "role": cat.role.name, "cause": "白貓續命結束"},
                )
        self.cats_due_after_vote.clear()

    async def _finish_vote_without_exile(self):
        await self._finalize_due_white_cats()
        await self._apply_day_mutes()
        winner = self.check_winner()
        if winner:
            return await self.end_game(winner)
        return await self.start_night()

    async def _prompt_order_prince(self, prince, exile_target):
        self.pending_exile_id = exile_target.id
        view = discord.ui.View(timeout=90)
        use_button = discord.ui.Button(
            label="發動回溯", style=discord.ButtonStyle.primary, emoji="⏳"
        )
        skip_button = discord.ui.Button(
            label="不發動", style=discord.ButtonStyle.grey
        )

        async def use_callback(interaction):
            if (
                self.phase != PHASE_DAY
                or interaction.user.id != prince.id
                or self.pending_exile_id != exile_target.id
                or prince.role.used_skill
            ):
                return await interaction.response.send_message(
                    "❌ 這個回溯操作已失效。", ephemeral=True
                )
            prince.role.used_skill = True
            self.pending_exile_id = None
            self.votes = {}
            self._vote_tally_started = False
            await interaction.response.send_message(
                f"⏳ **{prince.display_name}** 發動定序回溯，"
                f"**{exile_target.display_name}** 免於放逐並重新投票！"
            )
            await self._send_voting_view()

        async def skip_callback(interaction):
            if (
                self.phase != PHASE_DAY
                or interaction.user.id != prince.id
                or self.pending_exile_id != exile_target.id
            ):
                return await interaction.response.send_message(
                    "❌ 這個回溯操作已失效。", ephemeral=True
                )
            self.pending_exile_id = None
            prince.role.used_skill = True
            await interaction.response.send_message("⏳ 定序王子選擇不回溯。")
            if isinstance(exile_target.role, Pufferfish) and not exile_target.role.used_skill:
                await self._prompt_pufferfish(exile_target)
            else:
                await self._resolve_exile(exile_target)

        use_button.callback = use_callback
        skip_button.callback = skip_callback
        view.add_item(use_button)
        view.add_item(skip_button)
        await self.channel.send(
            f"⏳ **定序王子 {prince.display_name}**：是否回溯本次放逐？",
            view=view,
        )

        async def auto_skip():
            await asyncio.sleep(90)
            if (
                self.phase == PHASE_DAY
                and self.pending_exile_id == exile_target.id
                and not prince.role.used_skill
            ):
                self.pending_exile_id = None
                prince.role.used_skill = True
                await self.channel.send("⌛ 定序王子逾時未選擇，視為不回溯。")
                if isinstance(exile_target.role, Pufferfish) and not exile_target.role.used_skill:
                    await self._prompt_pufferfish(exile_target)
                else:
                    await self._resolve_exile(exile_target)

        asyncio.create_task(auto_skip())

    async def _prompt_pufferfish(self, pufferfish):
        self.pending_exile_id = pufferfish.id
        view = discord.ui.View(timeout=90)
        flip_button = discord.ui.Button(
            label="翻牌反擊", style=discord.ButtonStyle.danger, emoji="🐡"
        )
        skip_button = discord.ui.Button(label="直接出局", style=discord.ButtonStyle.grey)

        async def flip_callback(interaction):
            if (
                self.phase != PHASE_DAY
                or interaction.user.id != pufferfish.id
                or self.pending_exile_id != pufferfish.id
            ):
                return await interaction.response.send_message(
                    "❌ 這個河豚操作已失效。", ephemeral=True
                )
            self.pending_exile_id = None
            pufferfish.role.used_skill = True
            await interaction.response.send_message(
                "🐡 河豚翻牌，所有投給河豚的玩家一同出局！"
            )
            await self._resolve_exile(pufferfish, puffer_flip=True)

        async def skip_callback(interaction):
            if (
                self.phase != PHASE_DAY
                or interaction.user.id != pufferfish.id
                or self.pending_exile_id != pufferfish.id
            ):
                return await interaction.response.send_message(
                    "❌ 這個河豚操作已失效。", ephemeral=True
                )
            self.pending_exile_id = None
            pufferfish.role.used_skill = True
            await interaction.response.send_message("🐡 河豚選擇不翻牌。")
            await self._resolve_exile(pufferfish)

        flip_button.callback = flip_callback
        skip_button.callback = skip_callback
        view.add_item(flip_button)
        view.add_item(skip_button)
        await self.channel.send(
            f"🐡 **{pufferfish.display_name}** 被放逐，是否翻牌反擊？",
            view=view,
        )

        async def auto_skip():
            await asyncio.sleep(90)
            if self.phase == PHASE_DAY and self.pending_exile_id == pufferfish.id:
                self.pending_exile_id = None
                pufferfish.role.used_skill = True
                await self.channel.send("⌛ 河豚逾時未選擇，視為不翻牌。")
                await self._resolve_exile(pufferfish)

        asyncio.create_task(auto_skip())

    def _mark_day_death(self, player, cause):
        """標記白天死亡並處理白貓、魅惑、殉夢與尋香連鎖。"""
        deaths = []

        def mark(target, target_cause):
            if target is None or target.status != "alive":
                return
            if self._is_awakened_guarded(target):
                self.pending_role_notices.append(
                    f"🛡️ {target.display_name} 受到覺醒守護，免於出局。"
                )
                return
            if isinstance(target.role, WhiteCat) and not target.role.used_skill:
                target.role.used_skill = True
                self.pending_white_cats.add(target.id)
                return
            target.status = "dead"
            deaths.append((target, target_cause))
            self._resolve_awakened_lonely_idol(target, target_cause)

        if (
            isinstance(player.role, AwakenedWolfBeauty)
            and not player.role.state.get("illusion_used")
            and self.charmed_target
        ):
            substitute = self.get_player(self.charmed_target)
            if substitute and substitute.status == "alive":
                player.role.state["illusion_used"] = True
                mark(substitute, "挽歌幻象替死")
            else:
                mark(player, cause)
        else:
            mark(player, cause)
        if (
            cause in {"投票處決", "獵人射擊"}
            and isinstance(player.role, WolfBeauty)
            and not isinstance(player.role, AwakenedWolfBeauty)
            and self.charmed_target
        ):
            mark(self.get_player(self.charmed_target), "狼美人魅惑殉情")
        if isinstance(player.role, Dreamer) and self.current_dream_target:
            mark(self.get_player(self.current_dream_target), "攝夢人殉夢")
        if self.fate_pair and not self.fate_triggered and player.id in self.fate_pair:
            partner_id = self.fate_pair[0] if self.fate_pair[1] == player.id else self.fate_pair[1]
            mark(self.get_player(partner_id), "尋香命運綁定")
            self.fate_triggered = True
        return deaths

    async def _resolve_exile(self, player, *, puffer_flip=False):
        if player.status != "alive":
            return await self._finish_vote_without_exile()

        if isinstance(player.role, Fool) and not player.role.used_skill:
            player.role.used_skill = True
            player.role.vote_disabled = True
            await self.channel.send(
                f"🃏 **{player.display_name}** 是愚者，翻牌免疫放逐；之後失去投票權。"
            )
            await self._finalize_due_white_cats()
            return await self.start_night()
        if isinstance(player.role, AwakenedFool) and player.role.secret_body:
            player.role.secret_body = False
            player.role.used_skill = True
            await self.channel.send(
                f"🃏 **{player.display_name}** 的秘密之身抵消了本次放逐。"
            )
            await self._finalize_due_white_cats()
            return await self.start_night()

        other_wolves = [
            wolf for wolf in self.get_alive_players()
            if wolf.role.camp == CAMP_WOLF and wolf.id != player.id
        ]
        if isinstance(player.role, CrimsonApostle) and not other_wolves:
            self.crimson_last_stand = player.id
            player.role.state["doomed"] = True
            deaths = []
            await self.channel.send(
                f"🌕 **{player.display_name}** 是最後的赤月使徒，延至下個天亮才出局！"
            )
        else:
            deaths = self._mark_day_death(player, "投票處決")

        if player.id in self.pending_white_cats and player.status == "alive":
            await self.channel.send(
                f"🐱 **{player.display_name}** 翻牌續命，將在下一次放逐投票結束後出局。"
            )

        if puffer_flip:
            voter_ids = [
                voter_id for voter_id, target_id in self.votes.items()
                if target_id == player.id
            ]
            for voter_id in voter_ids:
                voter = self.get_player(voter_id)
                if voter and voter.status == "alive":
                    deaths.extend(self._mark_day_death(voter, "河豚翻牌反擊"))

        if player.status == "dead":
            self.last_exiled_camp = player.role.camp
            self.last_exiled_name = player.display_name
        await self._finalize_due_white_cats()
        await self._apply_day_mutes()

        if deaths:
            lines = []
            for dead, cause in deaths:
                lines.append(f"💀 **{dead.display_name}**（{dead.role.name}）— {cause}")
                self.log_event(
                    "vote_death",
                    {"name": dead.display_name, "role": dead.role.name, "cause": cause},
                )
            await self.channel.send("\n".join(lines))
        if self.pending_role_notices:
            await self.channel.send("\n".join(self.pending_role_notices))
            self.pending_role_notices.clear()

        shooters = [
            dead for dead, cause in deaths
            if dead.role.can_shoot
            and (isinstance(dead.role, AwakenedHunter) or cause != "河豚翻牌反擊")
        ]
        if shooters:
            self.phase = PHASE_SHOOT
            self.pending_shooters = [
                shooter.id for shooter in shooters
                for _ in range(max(1, shooter.role.shoot_count))
            ]
            self.after_shoot = "night"
            return await self._prompt_next_shooter()

        winner = self.check_winner()
        if winner:
            return await self.end_game(winner)
        return await self.start_night()

    async def send_day_skill_select(self, interaction, action_type):
        if (
            self.phase != PHASE_DAY
            or self.votes
            or self._vote_tally_started
            or self.pending_awakened_white_wolf
        ):
            return await interaction.response.send_message(
                "❌ 白天技能只能在本輪有人投票前使用。", ephemeral=True
            )
        player = self.get_player(interaction.user.id)
        if action_type == "awakened_guard":
            if (
                not player
                or player.status != "alive"
                or not isinstance(player.role, AwakenedGuard)
                or player.role.disabled
                or player.role.state.get("last_guard_round") == self.round_num
            ):
                return await interaction.response.send_message(
                    "❌ 只有本日尚未發動的存活覺醒守衛能使用。", ephemeral=True
                )
            targets = self.get_action_targets(player, "awakened_guard")
            if not targets:
                return await interaction.response.send_message(
                    "❌ 目前沒有合法的守護目標。", ephemeral=True
                )
            select = discord.ui.Select(
                placeholder="🛡️ 選擇本日守護目標...",
                options=[
                    discord.SelectOption(label=target.display_name, value=str(target.id))
                    for target in targets
                ],
            )
            view = discord.ui.View(timeout=300)

            async def guard_callback(inte):
                await self.handle_awakened_guard_day(
                    inte, player, int(select.values[0])
                )

            select.callback = guard_callback
            view.add_item(select)
            return await interaction.response.send_message(
                "選擇覺醒守護目標；本日結束前，目標不會以任何方式出局。",
                view=view,
                ephemeral=True,
            )
        if action_type == "awakened_white_wolf":
            if (
                not player
                or player.status != "alive"
                or not isinstance(player.role, AwakenedWhiteWolfKing)
                or player.role.used_skill
                or self.pending_awakened_white_wolf
            ):
                return await interaction.response.send_message(
                    "❌ 只有尚未發動技能的存活覺醒白狼王能引爆。", ephemeral=True
                )
            select = discord.ui.Select(
                placeholder="🩸 選擇要誘導自爆的玩家...",
                options=[
                    discord.SelectOption(label=target.display_name, value=str(target.id))
                    for target in self.get_alive_players()
                ],
            )
            view = discord.ui.View(timeout=300)

            async def induce_callback(inte):
                await self.handle_awakened_white_wolf_induce(
                    inte, player, int(select.values[0])
                )

            select.callback = induce_callback
            view.add_item(select)
            return await interaction.response.send_message(
                "選擇要誘導自爆的玩家：", view=view, ephemeral=True
            )
        if (
            action_type != "knight_duel"
            or not player
            or player.status != "alive"
            or not isinstance(player.role, Knight)
            or player.role.used_skill
        ):
            return await interaction.response.send_message(
                "❌ 只有尚未發動技能的存活騎士能決鬥。", ephemeral=True
            )
        options = [
            discord.SelectOption(label=target.display_name, value=str(target.id), emoji="⚔️")
            for target in self.get_action_targets(player, "knight_duel")
        ]
        select = discord.ui.Select(placeholder="⚔️ 選擇決鬥目標...", options=options)
        view = discord.ui.View(timeout=300)

        async def callback(inte):
            await self.handle_knight_duel(inte, player, int(select.values[0]))

        select.callback = callback
        view.add_item(select)
        await interaction.response.send_message(
            "選擇騎士決鬥目標：", view=view, ephemeral=True
        )

    async def handle_awakened_guard_day(self, interaction, guard, target_id):
        target = self.get_player(target_id)
        if (
            self.phase != PHASE_DAY
            or self.votes
            or self.pending_awakened_white_wolf
            or interaction.user.id != guard.id
            or guard.status != "alive"
            or not isinstance(guard.role, AwakenedGuard)
            or guard.role.disabled
            or guard.role.state.get("last_guard_round") == self.round_num
            or target not in self.get_action_targets(guard, "awakened_guard")
        ):
            return await interaction.response.send_message(
                "❌ 這個覺醒守護操作已失效。", ephemeral=True
            )
        guard.role.last_target = target.id
        guard.role.state["last_guard_round"] = self.round_num
        self.awakened_guard_target = target.id
        self.awakened_guard_period = "day"
        self.log_event(
            "awakened_guard",
            {"guard": guard.display_name, "target": target.display_name, "period": "day"},
        )
        await interaction.response.send_message(
            f"🛡️ 已守護 **{target.display_name}**；本日結束前無法出局。",
            ephemeral=True,
        )
        await self.channel.send("🛡️ 覺醒守衛已在白天發動技能。")

    async def handle_awakened_white_wolf_induce(self, interaction, wolf, bomber_id):
        bomber = self.get_player(bomber_id)
        if (
            self.phase != PHASE_DAY
            or self.votes
            or interaction.user.id != wolf.id
            or wolf.status != "alive"
            or not isinstance(wolf.role, AwakenedWhiteWolfKing)
            or wolf.role.used_skill
            or self.pending_awakened_white_wolf
            or bomber is None
            or bomber.status != "alive"
        ):
            return await interaction.response.send_message(
                "❌ 這個引爆操作已失效。", ephemeral=True
            )
        wolf.role.used_skill = True
        if self._is_awakened_guarded(bomber):
            await interaction.response.send_message(
                f"🛡️ **{bomber.display_name}** 受到覺醒守護，引爆未能使其出局。"
            )
            self.log_event(
                "awakened_white_wolf",
                {"wolf": wolf.display_name, "bomber": bomber.display_name, "blocked": True},
            )
            return

        self.pending_awakened_white_wolf = {
            "wolf_id": wolf.id,
            "bomber_id": bomber.id,
        }
        await interaction.response.send_message(
            f"🩸 覺醒白狼王發動！**{bomber.display_name}** 被誘導自爆，"
            "請選擇一名玩家一同出局。"
        )
        companions = [
            target for target in self.get_alive_players() if target.id != bomber.id
        ]
        if not companions:
            return await self._finish_awakened_white_wolf(bomber, None)

        select = discord.ui.Select(
            placeholder="🩸 選擇一同出局的玩家...",
            options=[
                discord.SelectOption(label=target.display_name, value=str(target.id))
                for target in companions
            ],
        )
        view = discord.ui.View(timeout=45)

        async def companion_callback(inte):
            if inte.user.id != bomber.id:
                return await inte.response.send_message(
                    "❌ 只有被誘導自爆的玩家能選擇。", ephemeral=True
                )
            companion = self.get_player(int(select.values[0]))
            await inte.response.defer()
            view.stop()
            await self._finish_awakened_white_wolf(bomber, companion)

        select.callback = companion_callback
        view.add_item(select)
        await self.channel.send(
            f"🩸 {bomber.mention} 請在 45 秒內選擇一名玩家一同出局。",
            view=view,
        )

        async def auto_finish():
            await asyncio.sleep(45)
            pending = self.pending_awakened_white_wolf
            if (
                self.phase == PHASE_DAY
                and pending
                and pending.get("bomber_id") == bomber.id
            ):
                view.stop()
                await self.channel.send("⌛ 被誘導者逾時，只有本人自爆出局。")
                await self._finish_awakened_white_wolf(bomber, None)

        asyncio.create_task(auto_finish())

    async def _finish_awakened_white_wolf(self, bomber, companion):
        pending = self.pending_awakened_white_wolf
        if (
            self.phase != PHASE_DAY
            or not pending
            or pending.get("bomber_id") != bomber.id
        ):
            return False
        self.pending_awakened_white_wolf = None
        deaths = self._mark_day_death(bomber, "覺醒白狼王誘導自爆")
        if companion and companion.status == "alive":
            deaths.extend(self._mark_day_death(companion, "引爆連帶出局"))

        lines = ["🩸 **引爆結算**"]
        for dead, cause in deaths:
            role_text = (
                "身分不翻牌"
                if dead.id == bomber.id and dead.role.camp == CAMP_WOLF
                else dead.role.name
            )
            lines.append(f"💀 **{dead.display_name}**（{role_text}）— {cause}")
            self.log_event(
                "awakened_white_wolf_death",
                {"name": dead.display_name, "role": dead.role.name, "cause": cause},
            )
        if len(lines) == 1:
            lines.append("所有出局效果都被覺醒守護擋下。")
        await self.channel.send("\n".join(lines))
        if self.pending_role_notices:
            await self.channel.send("\n".join(self.pending_role_notices))
            self.pending_role_notices.clear()
        await self._apply_day_mutes()
        winner = self.check_winner()
        if winner:
            await self.end_game(winner)
        else:
            await self.start_night()
        return True

    async def handle_knight_duel(self, interaction, knight, target_id):
        target = self.get_player(target_id)
        if (
            self.phase != PHASE_DAY
            or self.votes
            or self.pending_awakened_white_wolf
            or interaction.user.id != knight.id
            or knight.status != "alive"
            or not isinstance(knight.role, Knight)
            or knight.role.disabled
            or knight.role.used_skill
            or target is None
            or target.status != "alive"
            or target.id == knight.id
        ):
            return await interaction.response.send_message(
                "❌ 這個騎士決鬥操作已失效。", ephemeral=True
            )
        knight.role.used_skill = True
        if target.role.camp == CAMP_WOLF:
            if self._is_awakened_guarded(target):
                await interaction.response.send_message(
                    f"🛡️ 決鬥確認 **{target.display_name}** 是狼人，"
                    "但覺醒守護使其免於出局；立即入夜。"
                )
                self.log_event(
                    "knight_duel",
                    {"knight": knight.display_name, "target": target.display_name, "result": "狼人受守護"},
                )
                return await self.start_night()
            target.status = "dead"
            self._resolve_awakened_lonely_idol(target, "騎士決鬥")
            await interaction.response.send_message(
                f"⚔️ 騎士決鬥成功！**{target.display_name}**（{target.role.name}）出局，立即入夜。"
            )
            self.log_event("knight_duel", {"knight": knight.display_name, "target": target.display_name, "result": "狼人出局"})
            winner = self.check_winner()
            if winner:
                return await self.end_game(winner)
            return await self.start_night()
        knight.status = "dead"
        await interaction.response.send_message(
            f"⚔️ 決鬥失敗，目標是好人；騎士 **{knight.display_name}** 出局，白天繼續。"
        )
        self.log_event("knight_duel", {"knight": knight.display_name, "target": target.display_name, "result": "騎士出局"})
        await self._apply_day_mutes()
        winner = self.check_winner()
        if winner:
            return await self.end_game(winner)
        await self._send_voting_view()

    async def handle_crimson_reveal(self, interaction):
        player = self.get_player(interaction.user.id)
        if (
            self.phase != PHASE_DAY
            or self.votes
            or self.pending_awakened_white_wolf
            or not player
            or player.status != "alive"
            or not isinstance(player.role, CrimsonApostle)
            or player.role.disabled
            or player.role.used_skill
        ):
            return await interaction.response.send_message(
                "❌ 只有尚未發動技能的存活赤月使徒能在投票前自曝。", ephemeral=True
            )
        player.role.used_skill = True
        self.good_skills_sealed = True
        await interaction.response.send_message(
            f"🌕 **{player.display_name}** 自曝赤月使徒！立即入夜，本夜所有好人技能封印。"
        )
        await self.start_night()

    async def handle_wolf_self_destruct(self, interaction):
        player = self.get_player(interaction.user.id)
        if (
            self.phase != PHASE_DAY
            or self.votes
            or self.pending_awakened_white_wolf
            or not player
            or player.status != "alive"
            or not player.role.can_self_destruct
            or player.role.state.get("self_destruct_attempted")
        ):
            return await interaction.response.send_message(
                "❌ 你目前不能發動狼人自爆。", ephemeral=True
            )
        player.role.state["self_destruct_attempted"] = True
        deaths = self._mark_day_death(player, "狼人自爆")
        if any(dead.id == player.id for dead, _ in deaths):
            await interaction.response.send_message(
                f"💥 **{player.display_name}** 自爆並翻牌為 **{player.role.name}**，立即入夜！"
            )
            self.log_event(
                "wolf_self_destruct",
                {"player": player.display_name, "role": player.role.name, "blocked": False},
            )
        else:
            await interaction.response.send_message(
                f"🛡️ **{player.display_name}** 發動自爆，但覺醒守護使其免於出局；立即入夜。"
            )
            self.log_event(
                "wolf_self_destruct",
                {"player": player.display_name, "role": player.role.name, "blocked": True},
            )
        if self.pending_role_notices:
            await self.channel.send("\n".join(self.pending_role_notices))
            self.pending_role_notices.clear()
        await self._apply_day_mutes()
        winner = self.check_winner()
        if winner:
            return await self.end_game(winner)
        return await self.start_night()

    # --- 開槍邏輯 ---
    async def handle_awakened_hunt(self, interaction, hunter, direction):
        if (
            self.phase != PHASE_SHOOT
            or not self.pending_shooters
            or self.pending_shooters[0] != hunter.id
            or interaction.user.id != hunter.id
            or not isinstance(hunter.role, AwakenedHunter)
            or direction not in {"left", "right"}
            or self.shots_fired[hunter.id] >= 1
        ):
            return await interaction.response.send_message(
                "❌ 只有目前的覺醒獵人本人能使用這個巡獵面板。",
                ephemeral=True,
            )

        self.pending_shooters.pop(0)
        self.shots_fired[hunter.id] += 1
        self.shot_players.add(hunter.id)
        step = -1 if direction == "left" else 1
        start = self.players.index(hunter)
        target = None
        for offset in range(1, len(self.players)):
            candidate = self.players[(start + step * offset) % len(self.players)]
            if candidate.status == "alive" and candidate.role.camp == CAMP_WOLF:
                target = candidate
                break

        if target:
            # 巡獵直接生效，覺醒狼美人的幻象不能替代這次出局。
            if self._is_awakened_guarded(target):
                await interaction.response.send_message(
                    f"🛡️ 覺醒獵人向{'左' if direction == 'left' else '右'}巡獵，"
                    f"但 **{target.display_name}** 受到覺醒守護，免於出局。"
                )
            else:
                target.status = "dead"
                self._resolve_awakened_lonely_idol(target, "覺醒獵人巡獵")
                await interaction.response.send_message(
                    f"🏹 覺醒獵人向{'左' if direction == 'left' else '右'}巡獵，"
                    f"帶走了 **{target.display_name}**（{target.role.name}）！"
                )
                self.log_event(
                    "awakened_hunt",
                    {"hunter": hunter.display_name, "target": target.display_name, "role": target.role.name},
                )
        else:
            await interaction.response.send_message("🏹 該方向已沒有存活狼人，巡獵落空。")
        await self._apply_day_mutes()
        await self._finish_shoot_sequence()

    async def handle_shoot(self, interaction, shooter, target_id):
        target = self.get_player(target_id)
        if (
            self.phase != PHASE_SHOOT
            or not self.pending_shooters
            or self.pending_shooters[0] != shooter.id
            or interaction.user.id != shooter.id
            or self.get_player(shooter.id) is not shooter
            or self.shots_fired[shooter.id] >= max(1, shooter.role.shoot_count)
            or target is None
            or target.status != "alive"
        ):
            return await interaction.response.send_message(
                "❌ 只有目前的槍手本人能使用這個面板。", ephemeral=True
            )

        self.pending_shooters.pop(0)
        self.shots_fired[shooter.id] += 1
        if shooter.id not in self.pending_shooters:
            self.shot_players.add(shooter.id)
        chained_deaths = self._mark_day_death(target, "獵人射擊")
        target_died = any(dead.id == target.id for dead, _ in chained_deaths)
        if target_died:
            await interaction.response.send_message(
                f"💥 **{shooter.display_name}** 帶走了 "
                f"**{target.display_name}**（{target.role.name}）"
            )
            self.log_event(
                "shoot_death",
                {
                    "shooter": shooter.display_name,
                    "name": target.display_name,
                    "role": target.role.name,
                    "cause": "開槍",
                },
            )
        else:
            await interaction.response.send_message(
                f"🛡️ **{target.display_name}** 受到覺醒守護，擋下了射擊。"
            )
        for dead, cause in chained_deaths:
            if dead.id == target.id:
                continue
            await self.channel.send(
                f"💀 **{dead.display_name}**（{dead.role.name}）— {cause}"
            )
            self.log_event(
                "shoot_death",
                {"name": dead.display_name, "role": dead.role.name, "cause": cause},
            )
        if self.pending_role_notices:
            await self.channel.send("\n".join(self.pending_role_notices))
            self.pending_role_notices.clear()
        new_shooters = [
            dead for dead, cause in chained_deaths
            if dead.id != shooter.id
            and dead.role.can_shoot
            and cause in {"獵人射擊", "狼美人魅惑殉情", "尋香命運綁定"}
        ]
        for new_shooter in new_shooters:
            self.pending_shooters.extend(
                [new_shooter.id] * max(1, new_shooter.role.shoot_count)
            )
        await self._apply_day_mutes()
        await self._finish_shoot_sequence()

    async def handle_skip_shoot(self, interaction, shooter):
        if (
            self.phase != PHASE_SHOOT
            or not self.pending_shooters
            or self.pending_shooters[0] != shooter.id
            or interaction.user.id != shooter.id
        ):
            return await interaction.response.send_message(
                "❌ 只有目前的槍手本人能使用這個面板。", ephemeral=True
            )

        self.pending_shooters.pop(0)
        self.shots_fired[shooter.id] += 1
        if shooter.id not in self.pending_shooters:
            self.shot_players.add(shooter.id)
        await interaction.response.send_message(
            f"✋ **{shooter.display_name}** 放棄開槍。"
        )
        await self._finish_shoot_sequence()

    async def _finish_shoot_sequence(self):
        if self.pending_shooters:
            return await self._prompt_next_shooter()

        winner = self.check_winner()
        if winner:
            return await self.end_game(winner)

        destination = self.after_shoot
        self.after_shoot = None
        self.phase = PHASE_DAY
        if destination == "night":
            await self.start_night()
        else:
            await self._send_voting_view()

    # ==========================
    #      遊戲結束
    # ==========================
    def check_winner(self):
        alive = self.get_alive_players()
        wolves = [p for p in alive if p.role.camp == CAMP_WOLF]
        gods = [p for p in alive if p.role.camp == CAMP_GOD]
        villagers = [p for p in alive if p.role.camp == CAMP_VILLAGER]
        
        if not wolves: return "好人陣營"
        if not gods or not villagers: return "狼人陣營" 
        if len(wolves) >= len(gods) + len(villagers): return "狼人陣營"
        
        return None

    async def end_game(self, winner):
        async with self._state_lock:
            if self.phase == PHASE_ENDED or self._ending:
                return False
            self._ending = True
            self.phase = PHASE_ENDED

        # 先停止遊戲音效，再開放 Music 指令，避免結束瞬間誤停新歌。
        await self._release_game_audio()
        await self._restore_mutes()
        self._unregister()
        
        result_lines = [
            f"`{index:02}` **{p.display_name}**｜{p.role.name}｜{p.role.camp}"
            for index, p in enumerate(self.players, start=1)
        ]
        result_embed = discord.Embed(
            title="🏁 遊戲結束",
            description=f"## {winner} 獲勝",
            color=discord.Color.gold() if winner == "好人陣營" else discord.Color.dark_red(),
        )
        for chunk_index in range(0, len(result_lines), 10):
            result_embed.add_field(
                name="🎭 全員身分揭曉" if chunk_index == 0 else "🎭 身分揭曉（續）",
                value="\n".join(result_lines[chunk_index:chunk_index + 10]),
                inline=False,
            )
        result_embed.add_field(name="總回合", value=str(self.round_num), inline=True)
        result_embed.add_field(name="復盤事件", value=str(len(self.game_log)), inline=True)
        result_embed.set_footer(text="使用下方復盤選單查看每一夜與每一天的關鍵事件")
        await self.channel.send(embed=result_embed)
        
        if self.wolf_thread:
            try:
                await self.wolf_thread.delete()
            except discord.HTTPException:
                log.warning("無法刪除狼人討論串", exc_info=True)
            self.wolf_thread = None
        
        # [新增] 顯示復盤介面
        replay_view = ReplayView(self.game_log, self.players, winner, max(self.round_num, 1))
        await self.channel.send(embed=replay_view.get_initial_embed(), view=replay_view)
        return True

    async def abort(self):
        """強制停止遊戲並完整清理語音、靜音與討論串。"""
        async with self._state_lock:
            if self.phase == PHASE_ENDED:
                self._unregister()
                return False
            was_active = self.phase != PHASE_WAITING
            self.phase = PHASE_ENDED
            self._ending = True

        if was_active:
            await self._release_game_audio()
        await self._restore_mutes()
        if self.wolf_thread:
            try:
                await self.wolf_thread.delete()
            except discord.HTTPException:
                log.warning("無法刪除狼人討論串", exc_info=True)
            self.wolf_thread = None
        if self.lobby_message:
            try:
                await self.lobby_message.edit(view=None)
            except discord.HTTPException:
                log.warning("無法停用狼人殺大廳", exc_info=True)
        self._unregister()
        return True
    
    def log_event(self, event_type: str, data: dict):
        """記錄遊戲事件"""
        self.game_log.append({
            "round": self.round_num,
            "phase": self.phase,
            "event_type": event_type,
            "data": data
        })

    async def handle_stop_vote(self, interaction):
        async with self._state_lock:
            if self.phase != PHASE_DAY:
                return await interaction.response.send_message(
                    "❌ 這個投票面板已失效。", ephemeral=True
                )
            player = self.get_player(interaction.user.id)
            if not player or player.status != "alive":
                return await interaction.response.send_message(
                    "死人或非玩家無法投票。", ephemeral=True
                )
            if interaction.user.id in self.stop_votes:
                return await interaction.response.send_message(
                    "你已經投過結束票。", ephemeral=True
                )

            self.stop_votes.add(interaction.user.id)
            curr = len(self.stop_votes)
            needed = len(self.get_alive_players()) // 2 + 1
        
        await interaction.response.send_message(
            f"🏳️ 提議結束（{curr}/{needed}）"
        )
        
        if curr >= needed:
            await self.channel.send("🛑 **玩家投票強制結束遊戲。**")
            await self.end_game("無 (強制結束)")
