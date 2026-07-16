import discord
import asyncio
import random
import logging
from collections import Counter
from .const import *
from .roles import Merchant, Player, Seer, Witch, Wolf, create_role
from .views import (
    IdentityView,
    LobbyView,
    LuckyView,
    MerchantSkillSelect,
    NightTargetSelect,
    ShooterView,
    VotingView,
    WitchView,
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
        
        # 投票數據
        self.votes = {}     # {user_id: target_id}
        self.stop_votes = set()
        self.deaths_tonight = [] # 今晚死亡名單
        self.pending_shooters = []
        self.shot_players = set()
        self.after_shoot = None

        # 介面引用
        self.lobby_message = None
        self.wolf_thread = None

        # 狀態轉換與資源清理
        self._state_lock = asyncio.Lock()
        self._ending = False
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
            if n < minimum:
                return await interaction.response.send_message(
                    f"❌ {BOARD_NAMES.get(self.board_id, '此板子')}至少需要 {minimum} 人，"
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
        await self.channel.send("🎲 **請確認身分** (10秒後自動入夜)", view=IdentityView(self))
        
        # 自動入夜：等待 10 秒讓玩家確認身分
        await asyncio.sleep(10)
        if self.phase == PHASE_STARTING:  # 確保還沒被強制入夜
            await self.start_night()

    def assign_roles(self):
        n = len(self.players)
        minimum = BOARD_MIN_PLAYERS.get(self.board_id, 3)
        if n < minimum or n > MAX_PLAYERS:
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
        elif self.board_id == BOARD_STANDARD:
            s, wi, h = 1, 1, 1
            w = max(1, wolves_count)
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
            
        return True

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
                if p.role.camp == CAMP_WOLF:
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

        msg = f"你的身分是：**{p.role.name}** ({p.role.camp})\n{p.role.description}"
        if p.role.camp == CAMP_WOLF:
            teammates = [m.display_name for m in self.players if m.role.camp == CAMP_WOLF and m.id != p.id]
            msg += f"\n🐺 隊友: {', '.join(teammates) if teammates else '無 (孤狼)'}"
            msg += "\n💬 請留意 **狼人密謀區** 討論串。"

        await interaction.response.send_message(msg, ephemeral=True)

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
            self.wolf_votes.clear()
            self.wolf_target = None
            self.witch_poison_target = None
            self.lucky_data = {"user_id": None, "skill": None, "target": None}
            self.deaths_tonight = []
            self.votes = {}
            self.stop_votes = set()
            self._vote_tally_started = False
        
        asyncio.create_task(self._play_night_audio())
        asyncio.create_task(self._mute_for_night())

        # 白天會刪除密謀串，因此每個新夜晚都要重新建立。
        await self.create_wolf_thread()
        
        if self.wolf_thread:
            try:
                await self.wolf_thread.send("🌃 **天黑了，請開始討論戰術！**")
            except discord.HTTPException:
                log.warning("無法傳送狼人夜晚通知", exc_info=True)

        view = discord.ui.View(timeout=None)
        btn = discord.ui.Button(label="夜晚行動", style=discord.ButtonStyle.primary, emoji="🌙")
        
        async def action_callback(interaction):
            if self.phase != PHASE_NIGHT_1:
                return await interaction.response.send_message(
                    "❌ 這個上半夜行動按鈕已失效。", ephemeral=True
                )
            p = self.get_player(interaction.user.id)
            if not p or p.status != "alive": 
                return await interaction.response.send_message("你無法行動 (已死亡)", ephemeral=True)
            
            if isinstance(p.role, Wolf): 
                if p.id in self.wolf_votes:
                    return await interaction.response.send_message(
                        "❌ 你今晚已經投過票。", ephemeral=True
                    )
                view = discord.ui.View()
                view.add_item(NightTargetSelect(self, p, 'wolf_kill'))
                await interaction.response.send_message("🔪 **狼人投票**：", view=view, ephemeral=True)
                
            elif isinstance(p.role, Seer):
                if p.id in self.night_actions: return await interaction.response.send_message("❌ 已查驗過", ephemeral=True)
                view = discord.ui.View()
                view.add_item(NightTargetSelect(self, p, 'seer_check'))
                await interaction.response.send_message("🔮 **預言家查驗**：", view=view, ephemeral=True)
                
            elif isinstance(p.role, Merchant):
                if p.role.used_skill or p.id in self.night_actions: 
                     return await interaction.response.send_message("❌ 技能已使用或本回合已行動", ephemeral=True)
                
                view = discord.ui.View()
                view.add_item(NightTargetSelect(self, p, 'merchant_give'))
                
                async def skip(inte):
                    if (
                        self.phase != PHASE_NIGHT_1
                        or inte.user.id != p.id
                        or p.role.used_skill
                        or p.id in self.night_actions
                    ):
                        return await inte.response.send_message(
                            "❌ 這個操作已失效。", ephemeral=True
                        )
                    self.night_actions.add(p.id)
                    await inte.response.send_message("💤 選擇不發動", ephemeral=True)
                    await self.check_phase_1_end()
                
                skip_btn = discord.ui.Button(label="不發動", style=discord.ButtonStyle.grey)
                skip_btn.callback = skip
                view.add_item(skip_btn)
                
                await interaction.response.send_message("💰 **奇跡商人** 請選擇幸運兒：", view=view, ephemeral=True)
                
            else:
                await interaction.response.send_message("💤 你現在無需行動。", ephemeral=True)

        btn.callback = action_callback
        view.add_item(btn)
        
        roles_str = []
        alive_players = self.get_alive_players()
        if any(isinstance(p.role, Wolf) for p in alive_players):
            roles_str.append("狼人")
        if any(isinstance(p.role, Seer) for p in alive_players):
            roles_str.append("預言家")
        if any(
            isinstance(p.role, Merchant) and not p.role.used_skill
            for p in alive_players
        ):
            roles_str.append("奇跡商人")
        
        await self.channel.send(f"🌃 **上半夜：{'、'.join(roles_str)}**", view=view)
        return True

    # --- 委派技能邏輯 ---
    async def handle_night_action(self, interaction, player, action_type, target_id):
        phase_1_actions = {"wolf_kill", "seer_check", "merchant_give"}
        phase_2_actions = {
            "witch_skip",
            "lucky_check",
            "lucky_poison",
            "lucky_guard",
        }
        expected_phase = (
            PHASE_NIGHT_1 if action_type in phase_1_actions else PHASE_NIGHT_2
        )
        if action_type not in phase_1_actions | phase_2_actions:
            return await interaction.response.send_message(
                "❌ 未知的夜晚行動。", ephemeral=True
            )
        if self.phase != expected_phase:
            return await interaction.response.send_message(
                "❌ 這個夜晚操作已經失效。", ephemeral=True
            )
        current_player = self.get_player(interaction.user.id)
        if (
            current_player is not player
            or interaction.user.id != player.id
            or player.status != "alive"
        ):
            return await interaction.response.send_message(
                "❌ 你不能代替其他玩家行動。", ephemeral=True
            )

        target = self.get_player(target_id) if target_id != -1 else None
        if target_id not in {-1, None} and (
            target is None or target.status != "alive"
        ):
            return await interaction.response.send_message(
                "❌ 目標已失效，請重新選擇。", ephemeral=True
            )

        role_actions = {
            "wolf_kill": isinstance(player.role, Wolf),
            "seer_check": isinstance(player.role, Seer),
            "merchant_give": isinstance(player.role, Merchant),
            "witch_skip": isinstance(player.role, Witch),
            "lucky_check": self.lucky_data["user_id"] == player.id,
            "lucky_poison": self.lucky_data["user_id"] == player.id,
            "lucky_guard": self.lucky_data["user_id"] == player.id,
        }
        if not role_actions[action_type]:
            return await interaction.response.send_message(
                "❌ 你的身分不能使用這個操作。", ephemeral=True
            )

        if action_type == "wolf_kill" and player.id in self.wolf_votes:
            return await interaction.response.send_message(
                "❌ 你今晚已經投過票。", ephemeral=True
            )
        if action_type in {"seer_check", "witch_skip"} and player.id in self.night_actions:
            return await interaction.response.send_message(
                "❌ 你今晚已經行動過。", ephemeral=True
            )
        if action_type.startswith("lucky_"):
            expected_skill = action_type.removeprefix("lucky_")
            if (
                self.lucky_data["skill"] != expected_skill
                or self.lucky_data["target"] is not None
            ):
                return await interaction.response.send_message(
                    "❌ 幸運兒技能已使用或技能不符。", ephemeral=True
                )

        if action_type == "merchant_give":
            if (
                player.role.used_skill
                or player.id in self.night_actions
                or target_id == player.id
            ):
                return await interaction.response.send_message(
                    "❌ 技能已使用、已行動，或不能選擇自己。", ephemeral=True
                )
            view = discord.ui.View(timeout=300)
            view.add_item(MerchantSkillSelect(self, player, target_id))
            return await interaction.response.send_message(
                f"💰 要給 **{target.display_name}** 哪一個技能？",
                view=view,
                ephemeral=True,
            )

        await self.skill_manager.handle_night_action(interaction, player, action_type, target_id)

    async def handle_merchant_skill(self, interaction, player, target_id, skill):
        target = self.get_player(target_id)
        if (
            self.phase != PHASE_NIGHT_1
            or interaction.user.id != player.id
            or self.get_player(player.id) is not player
            or player.status != "alive"
            or not isinstance(player.role, Merchant)
            or player.role.used_skill
            or player.id in self.night_actions
            or target is None
            or target.status != "alive"
            or target.id == player.id
            or skill not in {"check", "poison", "guard"}
        ):
            return await interaction.response.send_message(
                "❌ 這個商人操作已失效。", ephemeral=True
            )
        await self.skill_manager.handle_merchant_skill(interaction, player, target_id, skill)

    # --- Phase 1 結束檢查 ---
    async def check_phase_1_end(self):
        if self.phase != PHASE_NIGHT_1:
            return
        alive_wolves = self.get_alive_role(Wolf) 
        wolves_done = len([v for v in self.wolf_votes.keys() if v in [p.id for p in alive_wolves]]) >= len(alive_wolves)
        
        alive_seers = self.get_alive_role(Seer)
        seer_done = not alive_seers or alive_seers[0].id in self.night_actions
        
        alive_merchants = self.get_alive_role(Merchant)
        merchant_done = True
        if alive_merchants:
            merch = alive_merchants[0]
            if not merch.role.used_skill and merch.id not in self.night_actions:
                merchant_done = False
                
        if wolves_done and seer_done and merchant_done:
            if self.wolf_votes:
                valid_votes = [t for u, t in self.wolf_votes.items() if u in [w.id for w in alive_wolves]]
                if valid_votes:
                    most = Counter(valid_votes).most_common()
                    max_v = most[0][1]
                    candidates = [t for t, c in most if c == max_v]
                    self.wolf_target = random.choice(candidates)
                else: self.wolf_target = -1
            else: self.wolf_target = -1

            target = self.get_player(self.wolf_target)
            self.log_event(
                "wolf_kill",
                {"target": target.display_name if target else "空刀"},
            )

            await self.start_night_phase_2()

    # --- 下半夜 (Phase 2) ---
    async def start_night_phase_2(self):
        alive_witch = [
            player
            for player in self.get_alive_role(Witch)
            if player.role.has_antidote or player.role.has_poison
        ]
        alive_lucky = [
            p
            for p in self.get_alive_players()
            if p.id == self.lucky_data["user_id"]
        ]
        has_witch = bool(alive_witch)
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
            
            if isinstance(p.role, Witch):
                if p.id in self.night_actions: return await interaction.response.send_message("已行動", ephemeral=True)
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

        await self.channel.send(f"🧙‍♀️ **下半夜：{'、'.join(roles_str)}**", view=view)
        
        return True

    def get_witch_info_msg(self):
        dead_name = "無人"
        if self.wolf_target != -1:
            dead_p = self.get_player(self.wolf_target)
            if dead_p: dead_name = dead_p.display_name
        return f"今晚 **{dead_name}** 被狼人殺害了。"

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
            if player.role.has_antidote or player.role.has_poison
        ]
        witch_done = not alive_witches or alive_witches[0].id in self.night_actions
        
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
            if self.phase not in {PHASE_NIGHT_1, PHASE_NIGHT_2}:
                return False
            self.phase = PHASE_DAY
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

        # --- 結算死亡 ---
        deaths = []
        death_causes = {}

        def add_death(user_id, cause):
            if not isinstance(user_id, int) or self.get_player(user_id) is None:
                return
            deaths.append(user_id)
            causes = death_causes.setdefault(user_id, [])
            if cause not in causes:
                causes.append(cause)
        
        # 1. 狼刀 (檢查守衛)
        guard_target = -1
        if self.lucky_data["skill"] == "guard":
            guard_target = self.lucky_data["target"]

        if (
            isinstance(self.wolf_target, int)
            and self.wolf_target != -1
            and self.wolf_target != guard_target
        ):
            add_death(self.wolf_target, "狼人殺害")
            
        # 2. 女巫毒
        if self.witch_poison_target:
            add_death(self.witch_poison_target, "女巫毒殺")
            
        # 3. 幸運兒毒
        if self.lucky_data["skill"] == "poison" and self.lucky_data["target"]:
            add_death(self.lucky_data["target"], "幸運兒毒殺")
            
        # 4. 商人反噬
        if self.lucky_data["user_id"]:
            lucky_p = self.get_player(self.lucky_data["user_id"])
            if lucky_p and isinstance(lucky_p.role, Wolf):
                merchants = self.get_alive_role(Merchant)
                if merchants:
                    add_death(merchants[0].id, "奇跡商人反噬")

        # 去重但保留結算順序，也排除已失效的目標。
        self.deaths_tonight = list(
            dict.fromkeys(
                user_id for user_id in deaths
            )
        )
        
        for uid in self.deaths_tonight:
            p = self.get_player(uid)
            if p: p.status = "dead"

        # --- 公布結果 ---
        msg = "🌅 **天亮了！**\n"
        if not self.deaths_tonight:
            msg += "昨晚是個平安夜。"
        else:
            msg += "昨晚死亡名單：\n"
            for uid in self.deaths_tonight:
                p = self.get_player(uid)
                msg += f"💀 **{p.display_name}**\n"
                cause = "、".join(death_causes.get(uid, ["未知原因"]))
                self.log_event("night_death", {"name": p.display_name, "role": p.role.name, "cause": cause})

        await self._apply_day_mutes()

        await self.channel.send(msg)

        # --- 獵人/狼王開槍檢查 ---
        shooters = self.get_shooter_deaths()
        if shooters:
            self.phase = PHASE_SHOOT
            self.pending_shooters = [player.id for player in shooters]
            self.after_shoot = "day_vote"
            await self._prompt_next_shooter()
            return

        winner = self.check_winner()
        if winner:
            return await self.end_game(winner)

        # --- 進入投票 ---
        await self._send_voting_view()
        return True

    def get_shooter_deaths(self):
        poisoned_ids = []
        if self.witch_poison_target: poisoned_ids.append(self.witch_poison_target)
        if self.lucky_data["skill"] == "poison": poisoned_ids.append(self.lucky_data["target"])

        shooters = []
        for uid in self.deaths_tonight:
            p = self.get_player(uid)
            if p and p.role.can_shoot and uid not in poisoned_ids:
                shooters.append(p)
        return shooters

    def check_shooter_death(self):
        """向下相容：回傳今晚第一位可開槍的玩家。"""
        shooters = self.get_shooter_deaths()
        return shooters[0] if shooters else None

    async def _send_voting_view(self):
        if self.phase != PHASE_DAY:
            return
        await self.channel.send(
            "現在開始討論，並點擊下方按鈕投票。",
            view=VotingView(self),
        )

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
            p = self.get_player(interaction.user.id)
            target_p = self.get_player(target_id)
            if not p or p.status != "alive":
                return await interaction.response.send_message(
                    "死人或非玩家無法投票。", ephemeral=True
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
            should_tally = (
                len(self.votes) >= len(self.get_alive_players())
                and not self._vote_tally_started
            )
            if should_tally:
                self._vote_tally_started = True

        await interaction.response.send_message(f"🗳️ 投給了 **{target_p.display_name}**", ephemeral=True)
        
        # 發送公開訊息讓大家知道有人投票了
        await self.channel.send(f"🗳️ **{p.display_name}** 已投票 ({len(self.votes)}/{len(self.get_alive_players())})")
        
        if should_tally:
            await self.tally_votes()

    async def tally_votes(self):
        if self.phase != PHASE_DAY:
            return
        # [新增] 公布投票結果
        vote_reveal = "📊 **投票結果公開：**\n"
        for voter_id, target_id in self.votes.items():
            voter = self.get_player(voter_id)
            target = self.get_player(target_id)
            if voter and target:
                vote_reveal += f"• {voter.display_name} → **{target.display_name}**\n"
        
        await self.channel.send(vote_reveal)
        
        counts = Counter(self.votes.values())
        if not counts:
            await self.channel.send("無人投票，直接入夜。")
            return await self.start_night()

        most = counts.most_common()
        max_v = most[0][1]
        cands = [k for k, v in most if v == max_v]

        if len(cands) > 1:
            await self.channel.send(f"⚖️ 平票 ({max_v}票)，無人被處決。")
            await self.start_night()
        else:
            dead_id = cands[0]
            p = self.get_player(dead_id)
            if p is None or p.status != "alive":
                await self.channel.send("⚠️ 投票目標已失效，本輪直接入夜。")
                return await self.start_night()
            p.status = "dead"
            await self._apply_day_mutes()
            
            await self.channel.send(f"💀 **{p.display_name}** 被處決了！\n身分是：**{p.role.name}**")
            # [新增] 記錄投票死亡
            self.log_event(
                "vote_death",
                {
                    "name": p.display_name,
                    "role": p.role.name,
                    "cause": "投票處決",
                },
            )
            
            winner = self.check_winner()
            if winner: return await self.end_game(winner)

            if p.role.can_shoot:
                self.phase = PHASE_SHOOT
                self.pending_shooters = [p.id]
                self.after_shoot = "night"
                await self._prompt_next_shooter()
            else:
                await self.start_night()

    # --- 開槍邏輯 ---
    async def handle_shoot(self, interaction, shooter, target_id):
        target = self.get_player(target_id)
        if (
            self.phase != PHASE_SHOOT
            or not self.pending_shooters
            or self.pending_shooters[0] != shooter.id
            or interaction.user.id != shooter.id
            or self.get_player(shooter.id) is not shooter
            or shooter.id in self.shot_players
            or target is None
            or target.status != "alive"
        ):
            return await interaction.response.send_message(
                "❌ 只有目前的槍手本人能使用這個面板。", ephemeral=True
            )

        self.pending_shooters.pop(0)
        self.shot_players.add(shooter.id)
        target.status = "dead"
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
        
        text = "**遊戲結束！獲勝者：** " + winner + "\n\n**身分揭曉：**\n"
        for p in self.players:
            text += f"{p.display_name}: {p.role.name}\n"
        
        await self.channel.send(text)
        
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
