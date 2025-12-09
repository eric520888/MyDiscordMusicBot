import discord
import asyncio
import random
from collections import Counter
from .const import *
from .roles import create_role, Player, Wolf, WolfKing, Seer, Witch, Hunter, Merchant, Villager
from .views import LobbyView, IdentityView, NightTargetSelect, MerchantSkillSelect, WitchView, LuckyView, ShooterSelect, VotingView
from .audio import AudioManager

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
        self.witch_save_used = False # 標記是否用了解藥 (防止同夜又毒) - *進階規則可擴充
        
        # 奇跡商人/幸運兒數據
        self.lucky_data = {"user_id": None, "skill": None, "target": None}
        
        # 守衛數據 (若未來擴充)
        self.guard_target = None
        
        # 投票數據
        self.votes = {}     # {user_id: target_id}
        self.stop_votes = set()
        self.deaths_tonight = [] # 今晚死亡名單

        # 介面引用 (用於更新大廳訊息)
        self.lobby_message = None
        self.wolf_thread = None

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

    # ==========================
    #      大廳階段 (Lobby)
    # ==========================
    async def set_board(self, interaction, board_id):
        """切換板子"""
        # 權限檢查由 View 層處理，這裡只做邏輯
        self.board_id = board_id
        board_name = {
            BOARD_AUTO: "🎲 自動配置",
            BOARD_STANDARD: "🔮 標準板",
            BOARD_WOLF_KING: "👑 狼王板",
            BOARD_MERCHANT: "💰 奇跡板"
        }.get(board_id, "未知")
        
        await interaction.response.send_message(f"✅ 板子更新為：**{board_name}**", ephemeral=True)
        if self.lobby_message:
            view = LobbyView(self)
            await self.lobby_message.edit(embed=view.update_embed(), view=view)

    async def player_join(self, interaction):
        """玩家加入"""
        if self.get_player(interaction.user.id):
            return await interaction.response.send_message("你已經在遊戲中了", ephemeral=True)
        
        # 建立一個暫時的 Player 物件 (還沒分配角色)
        self.players.append(Player(interaction.user, None))
        
        # 更新大廳介面
        await interaction.response.edit_message(embed=LobbyView(self).update_embed(), view=LobbyView(self))

    async def player_leave(self, interaction):
        """玩家退出"""
        p = self.get_player(interaction.user.id)
        if p:
            self.players.remove(p)
            await interaction.response.edit_message(embed=LobbyView(self).update_embed(), view=LobbyView(self))

    async def close_lobby(self, interaction):
        """關閉大廳"""
        # 停止 View 的監聽
        if self.lobby_message:
            await self.lobby_message.edit(view=None)
        
        # 清除遊戲實例 (這部分需要在 Bot 層做，這裡先只回應)
        await interaction.response.edit_message(embed=discord.Embed(title="🛑 大廳已關閉", color=discord.Color.greyple()), view=None)
        # 實際刪除 game object 的邏輯需在 Cog 層處理，或者這裡發送訊號

    # ==========================
    #      遊戲開始 (Start)
    # ==========================
    async def start_game(self, interaction):
        # 1. 檢查權限 (主持人/開發者)
        is_dev = await self.bot.is_owner(interaction.user)
        if interaction.user.id != self.host.id and not is_dev:
            return await interaction.response.send_message("❌ 權限不足", ephemeral=True)
        
        # 2. 檢查人數
        n = len(self.players)
        if n < 3:
            return await interaction.response.send_message("❌ 人數不足 (最少 3 人)", ephemeral=True)

        # 3. 嘗試連接語音
        if interaction.user.voice and not self.channel.guild.voice_client:
            try:
                await interaction.user.voice.channel.connect()
            except: pass

        # 4. 分配身分
        if not self.assign_roles():
            return await interaction.response.send_message("❌ 人數不足以開啟此板子", ephemeral=True)

        await interaction.response.send_message("🚀 遊戲開始！正在分配身分...", ephemeral=False)
        if self.lobby_message: 
            try: await self.lobby_message.delete()
            except: pass

        # 5. 建立狼人討論串
        await self.create_wolf_thread()

        # 6. 發送身分確認卡
        await self.channel.send("🎲 **請確認身分**", view=IdentityView(self))

    def assign_roles(self):
        """根據板子分配角色"""
        n = len(self.players)
        wolves_count = max(1, n // 3)
        
        # 預設配置變數
        w, k, s, wi, h, m = 0, 0, 0, 0, 0, 0
        
        if self.board_id == BOARD_AUTO:
            if n < 6: w, k, s, wi, h, m = 1, 0, 1, 0, 0, 0 # 3-5人: 1狼1預
            elif n < 9: w, k, s, wi, h, m = 1, 1, 1, 1, 1, 0
            elif n < 10: w, k, s, wi, h, m = 2, 1, 1, 1, 1, 0
            else: w, k, s, wi, h, m = 2, 1, 1, 1, 1, 1
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
        if n < total: return False # 人數不足

        # 產生角色列表
        role_list = [ROLE_WEREWOLF]*w + [ROLE_WOLF_KING]*k + [ROLE_SEER]*s + \
                    [ROLE_WITCH]*wi + [ROLE_HUNTER]*h + [ROLE_MERCHANT]*m
        
        # 補滿村民
        while len(role_list) < n: role_list.append(ROLE_VILLAGER)
        random.shuffle(role_list)
        
        # 分配給玩家
        for i, p in enumerate(self.players):
            p.role = create_role(role_list[i]) # 使用工廠模式建立角色物件
            p.status = "alive"
            
        return True

    async def create_wolf_thread(self):
        try:
            if self.wolf_thread: await self.wolf_thread.delete()
            
            thread_name = f"🐺-狼人密謀-{random.randint(100,999)}"
            self.wolf_thread = await self.channel.create_thread(name=thread_name, type=discord.ChannelType.private_thread)
            
            mentions = []
            for p in self.players:
                if p.role.camp == CAMP_WOLF:
                    await self.wolf_thread.add_user(p.user)
                    mentions.append(p.mention)
            
            await self.wolf_thread.send(f"🐺 **狼人密謀區**\n成員：{' '.join(mentions)}\n天黑請在此討論。")
        except Exception as e:
            print(f"無法建立討論串: {e}")

    # ==========================
    #      身分確認 & 入夜
    # ==========================
    async def send_identity(self, interaction):
        """發送身分給玩家 (Ephemeral)"""
        p = self.get_player(interaction.user.id)
        if not p: return

        # 組合身分訊息
        msg = f"你的身分是：**{p.role.name}** ({p.role.camp})\n{p.role.description}"
        
        # 狼人可以看到隊友
        if p.role.camp == CAMP_WOLF:
            teammates = [m.display_name for m in self.players if m.role.camp == CAMP_WOLF and m.id != p.id]
            msg += f"\n🐺 隊友: {', '.join(teammates) if teammates else '無 (孤狼)'}"
            msg += "\n💬 請留意 **狼人密謀區** 討論串。"

        await interaction.response.send_message(msg, ephemeral=True)
        
        # 更新確認進度 (顯示在 View 的訊息上)
        # 這裡需要透過 View 內部的邏輯來更新，或直接在這裡處理
        # 為了簡化，View 層級會處理 confirmed_players 的添加

    async def force_night(self, interaction):
        """強制入夜 (跳過確認)"""
        await interaction.response.send_message("🚨 主持人強制入夜！", ephemeral=False)
        await self.start_night()

    # ==========================
    #      夜晚流程 (Night)
    # ==========================
    async def start_night(self):
        self.phase = PHASE_NIGHT_1
        # 重置夜晚數據
        self.night_actions.clear()
        self.wolf_votes.clear()
        self.wolf_target = None
        self.witch_poison_target = None
        self.witch_save_used = False
        self.lucky_data = {"user_id": None, "skill": None, "target": None}
        self.guard_target = None
        self.deaths_tonight = []
        
        # 音效與靜音 (背景執行)
        asyncio.create_task(AudioManager.play_mixed(self.channel, "night.mp3", "voice_night_start.mp3"))
        asyncio.create_task(AudioManager.mute_all(self.channel, self.players, True))
        
        # 提醒狼人討論串
        if self.wolf_thread:
            try: await self.wolf_thread.send("🌃 **天黑了，請開始討論戰術！**")
            except: pass

        # 產生動態面板
        view = discord.ui.View(timeout=None)
        
        # 使用動態按鈕，點擊後根據身分回傳不同選單
        btn = discord.ui.Button(label="夜晚行動", style=discord.ButtonStyle.primary, emoji="🌙")
        
        async def action_callback(interaction):
            p = self.get_player(interaction.user.id)
            if not p or p.status != "alive": 
                return await interaction.response.send_message("你無法行動 (已死亡)", ephemeral=True)
            
            # --- 根據角色給予不同介面 ---
            if isinstance(p.role, Wolf): # 包含狼王
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
                
                # 商人也可以選擇不發動
                async def skip(inte):
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
        
        # 顯示上半夜角色
        roles_str = []
        if any(isinstance(p.role, Wolf) for p in self.players): roles_str.append("狼人")
        if any(isinstance(p.role, Seer) for p in self.players): roles_str.append("預言家")
        if any(isinstance(p.role, Merchant) for p in self.players): roles_str.append("奇跡商人")
        
        await self.channel.send(f"🌃 **上半夜：{'、'.join(roles_str)}**", view=view)

    # --- Phase 1 處理 ---
    async def handle_night_action(self, interaction, player, action_type, target_id):
        # 狼人投票
        if action_type == 'wolf_kill':
            self.wolf_votes[player.id] = target_id
            self.night_actions.add(player.id)
            target_name = "空刀" if target_id == -1 else self.get_player(target_id).display_name
            await interaction.response.send_message(f"🩸 你投給了：**{target_name}**", ephemeral=True)
            
        # 預言家查驗
        elif action_type == 'seer_check':
            self.night_actions.add(player.id)
            if target_id == -1:
                await interaction.response.send_message("🔮 驗證結果：空驗", ephemeral=True)
            else:
                target = self.get_player(target_id)
                # 狼人與狼王都是壞人
                res = "🐺 狼人 (壞人)" if target.role.camp == CAMP_WOLF else "好人"
                await interaction.response.send_message(f"🔮 驗證結果：**{res}**", ephemeral=True)

        # 幸運兒技能 (Check)
        elif action_type == 'lucky_check':
            # 這是 Phase 2 的動作
            self.lucky_data["target"] = target_id # 標記已用
            target = self.get_player(target_id)
            res = "🐺 狼人" if target.role.camp == CAMP_WOLF else "好人"
            await interaction.response.send_message(f"✨ [幸運兒] 查驗結果：**{res}**", ephemeral=True)
            await self.check_phase_2_end()
            return # 提早結束，不跑 phase 1 check

        # 幸運兒技能 (Poison/Guard) - 這些只需要記錄 target
        elif action_type in ['lucky_poison', 'lucky_guard']:
            self.lucky_data["target"] = target_id
            msg = "☠️ 已下毒" if action_type == 'lucky_poison' else "🛡️ 已守護"
            await interaction.response.send_message(msg, ephemeral=True)
            await self.check_phase_2_end()
            return

        # 檢查 Phase 1 是否結束
        await self.check_phase_1_end()

    # 商人給技能處理
    async def handle_merchant_skill(self, interaction, player, target_id, skill):
        self.lucky_data = {"user_id": target_id, "skill": skill, "target": None}
        self.night_actions.add(player.id)
        player.role.used_skill = True # 標記已用
        
        t_player = self.get_player(target_id)
        await interaction.response.send_message(f"💰 你給予了 **{t_player.display_name}** **{skill}** 技能。", ephemeral=True)
        await self.check_phase_1_end()

    # --- Phase 1 結束檢查 ---
    async def check_phase_1_end(self):
        # 1. 檢查狼人
        alive_wolves = self.get_alive_role(Wolf) # 包含狼王 (因為 WolfKing 繼承 Wolf)
        wolves_done = len([v for v in self.wolf_votes.keys() if v in [p.id for p in alive_wolves]]) >= len(alive_wolves)
        
        # 2. 檢查預言家
        alive_seers = self.get_alive_role(Seer)
        seer_done = not alive_seers or alive_seers[0].id in self.night_actions
        
        # 3. 檢查商人
        alive_merchants = self.get_alive_role(Merchant)
        merchant_done = True
        if alive_merchants:
            merch = alive_merchants[0]
            # 如果還沒用過技能 且 還沒行動過 -> 未完成
            if not merch.role.used_skill and merch.id not in self.night_actions:
                merchant_done = False
                
        # 全部完成 -> 進下一階段
        if wolves_done and seer_done and merchant_done:
            # 結算狼刀
            if self.wolf_votes:
                # 只算活著狼人的票
                valid_votes = [t for u, t in self.wolf_votes.items() if u in [w.id for w in alive_wolves]]
                if valid_votes:
                    most = Counter(valid_votes).most_common()
                    # 平票隨機
                    max_v = most[0][1]
                    candidates = [t for t, c in most if c == max_v]
                    self.wolf_target = random.choice(candidates)
                else: self.wolf_target = -1
            else: self.wolf_target = -1

            await self.start_night_phase_2()

    # --- 下半夜 (Phase 2) ---
    async def start_night_phase_2(self):
        # 智慧跳過：如果沒有女巫且沒有幸運兒，直接天亮
        has_witch = any(isinstance(p.role, Witch) for p in self.players) # 看板子有沒有，不是看活人
        has_lucky = self.lucky_data["user_id"] is not None
        
        if not has_witch and not has_lucky:
            return await self.start_day()
            
        self.phase = PHASE_NIGHT_2
        self.night_actions.clear() # 清空 Phase 1 的動作記錄給 Phase 2 用
        
        # 顯示下半夜介面 (女巫/幸運兒)
        view = discord.ui.View(timeout=None)
        btn = discord.ui.Button(label="下半夜行動", style=discord.ButtonStyle.primary, emoji="✨")
        
        async def p2_action(interaction):
            p = self.get_player(interaction.user.id)
            if not p or p.status != "alive": return await interaction.response.send_message("已死", ephemeral=True)
            
            # 女巫
            if isinstance(p.role, Witch):
                if p.id in self.night_actions: return await interaction.response.send_message("已行動", ephemeral=True)
                await interaction.response.send_message(
                    self.get_witch_info_msg(), 
                    view=WitchView(self, p), 
                    ephemeral=True
                )
            
            # 幸運兒
            elif self.lucky_data["user_id"] == p.id:
                if self.lucky_data["target"] is not None: return await interaction.response.send_message("技能已用", ephemeral=True)
                skill = self.lucky_data["skill"]
                await interaction.response.send_message(
                    f"✨ 你是幸運兒！獲得 **{skill}** 技能！", 
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
        
        # 檢查是否需要自動跳過 (若女巫和幸運兒都死了)
        alive_witch = self.get_alive_role(Witch)
        alive_lucky = [p for p in self.get_alive_players() if p.id == self.lucky_data["user_id"]]
        
        if not alive_witch and not alive_lucky:
            await asyncio.sleep(random.randint(5, 10)) # 假裝思考時間
            await self.start_day()

    def get_witch_info_msg(self):
        dead_name = "無人"
        if self.wolf_target != -1:
            dead_p = self.get_player(self.wolf_target)
            if dead_p: dead_name = dead_p.display_name
        return f"今晚 **{dead_name}** 被狼人殺害了。"

    async def handle_witch_save(self, interaction, player):
        if not player.role.has_antidote: return await interaction.response.send_message("❌ 解藥已用", ephemeral=True)
        if self.wolf_target == -1: return await interaction.response.send_message("❌ 無人死亡", ephemeral=True)
        
        player.role.has_antidote = False
        self.wolf_target = -1 # 救活
        self.night_actions.add(player.id)
        await interaction.response.send_message("💊 使用了解藥", ephemeral=True)
        await self.check_phase_2_end()

    async def send_witch_poison_select(self, interaction, player):
        if not player.role.has_poison: return await interaction.response.send_message("❌ 毒藥已用", ephemeral=True)
        
        view = discord.ui.View()
        # 這裡重用 NightTargetSelect，但傳入特殊 callback 邏輯較麻煩
        # 簡單起見，我們直接在這裡做一個 Select
        options = [discord.SelectOption(label=p.display_name, value=str(p.id)) for p in self.get_alive_players()]
        select = Select(placeholder="☠️ 選擇毒殺...", options=options)
        
        async def callback(inter):
            target = int(select.values[0])
            self.witch_poison_target = target
            player.role.has_poison = False
            self.night_actions.add(player.id)
            await inter.response.send_message("☠️ 已下毒", ephemeral=True)
            await self.check_phase_2_end()
            
        select.callback = callback
        view.add_item(select)
        await interaction.response.send_message("選擇目標：", view=view, ephemeral=True)

    async def check_phase_2_end(self):
        alive_witches = self.get_alive_role(Witch)
        witch_done = not alive_witches or alive_witches[0].id in self.night_actions
        
        lucky_done = True
        lid = self.lucky_data["user_id"]
        # 如果幸運兒活著 且 尚未指定目標(使用技能)
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
        self.phase = PHASE_DAY
        self.votes = {}
        self.stop_votes = set()
        
        # 停止音樂與靜音 (背景執行)
        asyncio.create_task(AudioManager.stop(self.channel))
        asyncio.create_task(AudioManager.mute_all(self.channel, self.players, False))
        
        # 刪除狼人討論串
        if self.wolf_thread:
            try: await self.wolf_thread.delete()
            except: pass
            self.wolf_thread = None

        # --- 結算死亡 ---
        deaths = []
        
        # 1. 狼刀 (檢查守衛)
        # 注意: 幸運兒守衛的 target 存在 lucky_data["target"]
        guard_target = -1
        if self.lucky_data["skill"] == "guard":
            guard_target = self.lucky_data["target"]

        if self.wolf_target != -1 and self.wolf_target != guard_target:
            deaths.append(self.wolf_target)
            
        # 2. 女巫毒 (無視守衛)
        if self.witch_poison_target:
            deaths.append(self.witch_poison_target)
            
        # 3. 幸運兒毒 (無視守衛)
        if self.lucky_data["skill"] == "poison" and self.lucky_data["target"]:
            deaths.append(self.lucky_data["target"])
            
        # 4. 商人反噬 (若選中狼人)
        if self.lucky_data["user_id"]:
            lucky_p = self.get_player(self.lucky_data["user_id"])
            if lucky_p and isinstance(lucky_p.role, Wolf): # 包含狼王
                # 商人死亡
                merchants = self.get_alive_role(Merchant)
                if merchants: deaths.append(merchants[0].id)

        self.deaths_tonight = list(set(deaths)) # 去重
        
        # 處理玩家狀態
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
                # 嘗試靜音死者
                member = self.channel.guild.get_member(uid)
                if member: asyncio.create_task(member.edit(mute=True))

        # 檢查勝負
        winner = self.check_winner()
        if winner: return await self.end_game(winner)
        
        await self.channel.send(msg)

        # --- 獵人/狼王開槍檢查 ---
        shooter = self.check_shooter_death()
        if shooter:
            self.phase = PHASE_SHOOT
            await self.channel.send(f"🔫 **{shooter.role.name} 發動技能！** 請開槍帶走一人！", 
                                    view=View().add_item(ShooterSelect(self, shooter)))
            return

        # --- 進入投票 ---
        await self.channel.send("現在開始討論，並點擊下方按鈕投票。", view=VotingView(self))

    def check_shooter_death(self):
        """檢查昨晚死亡的人是否有人能開槍"""
        # 規則：被毒死不能開槍 (女巫毒 or 幸運兒毒)
        poisoned_ids = []
        if self.witch_poison_target: poisoned_ids.append(self.witch_poison_target)
        if self.lucky_data["skill"] == "poison": poisoned_ids.append(self.lucky_data["target"])

        for uid in self.deaths_tonight:
            p = self.get_player(uid)
            if p and p.role.can_shoot and uid not in poisoned_ids:
                return p # 回傳第一個能開槍的人 (簡化處理)
        return None

    # ==========================
    #      投票與結算
    # ==========================
    async def handle_vote(self, interaction, target_id):
        p = self.get_player(interaction.user.id)
        if not p or p.status != "alive": return await interaction.response.send_message("死人無法投票", ephemeral=True)
        
        self.votes[p.id] = target_id
        target_p = self.get_player(target_id)
        await interaction.response.send_message(f"🗳️ 投給了 **{target_p.display_name}**")
        
        # 檢查是否全票
        if len(self.votes) >= len(self.get_alive_players()):
            await self.tally_votes()

    async def tally_votes(self):
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
            p.status = "dead"
            
            # 靜音
            member = self.channel.guild.get_member(dead_id)
            if member: asyncio.create_task(member.edit(mute=True))
            
            await self.channel.send(f"💀 **{p.display_name}** 被處決了！\n身分是：**{p.role.name}**")
            
            winner = self.check_winner()
            if winner: return await self.end_game(winner)

            # 檢查是否能開槍 (被票死通常可以開槍，除非有特殊規則，這裡設定為可)
            if p.role.can_shoot:
                self.phase = PHASE_SHOOT
                await self.channel.send(f"🔫 **{p.role.name} 發動技能！**", 
                                        view=View().add_item(ShooterSelect(self, p)))
            else:
                await self.start_night()

    async def handle_shoot(self, interaction, shooter, target_id):
        target_p = self.get_player(target_id)
        target_p.status = "dead"
        
        # 靜音
        member = self.channel.guild.get_member(target_id)
        if member: asyncio.create_task(member.edit(mute=True))

        await interaction.response.send_message(f"💥 帶走了 **{target_p.display_name}** ({target_p.role.name})")
        
        winner = self.check_winner()
        if winner: return await self.end_game(winner)
        
        # 槍響後進入夜晚
        await self.start_night()

    # ==========================
    #      遊戲結束
    # ==========================
    def check_winner(self):
        alive = self.get_alive_players()
        wolves = [p for p in alive if p.role.camp == CAMP_WOLF]
        gods = [p for p in alive if p.role.camp == CAMP_GOD]
        villagers = [p for p in alive if p.role.camp == CAMP_VILLAGER]
        
        if not wolves: return "好人陣營"
        if not gods or not villagers: return "狼人陣營" # 屠邊
        if len(wolves) >= len(gods) + len(villagers): return "狼人陣營" # 綁票
        
        return None

    async def end_game(self, winner):
        # 顯示身分
        text = "**遊戲結束！獲勝者：** " + winner + "\n\n**身分揭曉：**\n"
        for p in self.players:
            text += f"{p.display_name}: {p.role.name}\n"
        
        await self.channel.send(text)
        
        # 解除靜音 & 停止音樂
        asyncio.create_task(AudioManager.mute_all(self.channel, self.players, False))
        asyncio.create_task(AudioManager.stop(self.channel))
        
        # 刪除討論串
        if self.wolf_thread:
            try: await self.wolf_thread.delete()
            except: pass
            
        # 移除遊戲實例 (需要 Bot 層配合，這裡先只發訊息)
        # 實際應用中，Bot 層應該監聽這個狀態來移除 self.games[guild_id]

    async def handle_stop_vote(self, interaction):
        if not self.get_player(interaction.user.id).status == "alive":
            return await interaction.response.send_message("死人無法投票", ephemeral=True)
            
        if interaction.user.id in self.stop_votes:
            return await interaction.response.send_message("已投過", ephemeral=True)
            
        self.stop_votes.add(interaction.user.id)
        curr = len(self.stop_votes)
        needed = len(self.get_alive_players()) // 2 + 1
        
        await interaction.response.send_message(f"🏳️ 提議結束 ({curr}/{needed})")
        
        if curr >= needed:
            await self.channel.send("🛑 **玩家投票強制結束遊戲。**")
            await self.end_game("無 (強制結束)")