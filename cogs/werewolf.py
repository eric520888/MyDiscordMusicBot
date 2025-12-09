import discord
from discord.ext import commands
from discord.ui import Button, View, Select
import random
import asyncio
import os
import traceback 
from collections import Counter

# --- 設定 ---
SOUND_FOLDER = "./sounds"

# --- [核心架構] 角色與陣營定義 ---
# 只要在這裡新增角色，下方的邏輯就會自動適配
ROLE_WEREWOLF = "狼人"
ROLE_WOLF_KING = "狼王"
WOLF_CAMP = {ROLE_WEREWOLF, ROLE_WOLF_KING}

ROLE_SEER = "預言家"
ROLE_WITCH = "女巫"
ROLE_HUNTER = "獵人"
ROLE_MERCHANT = "奇跡商人"
GOD_CAMP = {ROLE_SEER, ROLE_WITCH, ROLE_HUNTER, ROLE_MERCHANT}

ROLE_VILLAGER = "村民"
VILLAGER_CAMP = {ROLE_VILLAGER}

# 定義能開槍的角色 (死後觸發)
SHOOTER_ROLES = {ROLE_HUNTER, ROLE_WOLF_KING}

# 定義遊戲狀態
PHASE_WAITING = "waiting"
PHASE_NIGHT_1 = "night_wolves_seer_merchant"
PHASE_NIGHT_2 = "night_witch_lucky"
PHASE_DAY = "day"
PHASE_SHOOT = "role_shoot" 

class WerewolfGame:
    def __init__(self, channel, host):
        self.channel = channel
        self.host = host
        self.players = []       
        self.roles = {}         
        self.status = {}        
        self.phase = PHASE_WAITING
        self.votes = {}         
        self.wolf_votes = {}    
        self.wolf_target = None 
        self.witch_poison_target = None 
        self.night_actions = set()
        self.stop_votes = set()
        
        # 遊戲設定
        self.board_id = "auto"
        self.confirmed_players = set()
        
        # 道具與技能
        self.witch_potions = {"antidote": True, "poison": True}
        self.merchant_status = {"used": False} 
        self.lucky_data = {"user_id": None, "skill": None, "target": None} 
        self.guard_target = None
        self.deaths_tonight = [] 

    def get_role(self, user_id):
        return self.roles.get(user_id, "未知")

    def is_alive(self, user_id):
        return self.status.get(user_id) == "alive"

    def get_alive_players(self):
        return [p for p in self.players if self.is_alive(p.id)]
    
    # 判斷是否為狼人陣營 (通用)
    def is_wolf_team(self, user_id):
        return self.get_role(user_id) in WOLF_CAMP

    # 判斷是否為神職
    def is_god(self, user_id):
        return self.get_role(user_id) in GOD_CAMP

    # 判斷是否為村民
    def is_villager(self, user_id):
        return self.get_role(user_id) in VILLAGER_CAMP

# --- 1. 大廳與設定 ---
class BoardSelect(Select):
    def __init__(self, game):
        self.game = game
        options = [
            discord.SelectOption(label="🎲 自動配置 (預設)", value="auto", description="依照人數自動平衡"),
            discord.SelectOption(label="🔮 標準板 (預女獵)", value="standard", description="無狼王、無商人"),
            discord.SelectOption(label="👑 狼王板 (預女獵+狼王)", value="wolf_king", description="狼隊有一名狼王"),
            discord.SelectOption(label="💰 奇跡板 (狼王+商人)", value="merchant", description="加入奇跡商人")
        ]
        super().__init__(placeholder="📜 請選擇遊戲板子...", min_values=1, max_values=1, options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        is_dev = await self.view.cog.bot.is_owner(interaction.user)
        if interaction.user.id != self.game.host.id and not is_dev:
            return await interaction.response.send_message("❌ 權限不足。", ephemeral=True)
        
        self.game.board_id = self.values[0]
        board_name = {
            "auto": "🎲 自動配置", "standard": "🔮 標準板",
            "wolf_king": "👑 狼王板", "merchant": "💰 奇跡板"
        }.get(self.values[0], "未知")
        
        await interaction.response.send_message(f"✅ 板子更新為：**{board_name}**", ephemeral=True)
        view: LobbyView = self.view
        await interaction.message.edit(embed=view.update_embed())

class LobbyView(View):
    def __init__(self, cog, game, ctx):
        super().__init__(timeout=300) 
        self.cog = cog
        self.game = game
        self.ctx = ctx
        self.message = None
        self.add_item(BoardSelect(game))

    async def on_timeout(self):
        if self.game.phase == PHASE_WAITING:
            if self.ctx.guild.id in self.cog.games:
                del self.cog.games[self.ctx.guild.id]
            if self.message:
                try:
                    embed = discord.Embed(title="⏳ 大廳已關閉", description="閒置過久自動解散。", color=discord.Color.greyple())
                    await self.message.edit(embed=embed, view=None)
                except: pass

    def update_embed(self):
        player_list = "\n".join([f"- {p.display_name}" for p in self.game.players]) if self.game.players else "目前無人加入"
        board_map = {
            "auto": "🎲 自動配置", "standard": "🔮 標準板",
            "wolf_king": "👑 狼王板", "merchant": "💰 奇跡板"
        }
        current_board = board_map.get(self.game.board_id, "未知")

        embed = discord.Embed(
            title="🐺 狼人殺遊戲大廳",
            description=f"主持人: {self.game.host.display_name}\n\n**目前板子**: {current_board}\n\n**已加入玩家 ({len(self.game.players)}):**\n{player_list}",
            color=discord.Color.dark_red()
        )
        return embed

    @discord.ui.button(label="加入遊戲", style=discord.ButtonStyle.green, emoji="✋", row=1)
    async def join_button(self, interaction: discord.Interaction, button: Button):
        if self.game.phase != PHASE_WAITING: return await interaction.response.send_message("已開始", ephemeral=True)
        if interaction.user in self.game.players: return await interaction.response.send_message("已加入", ephemeral=True)
        self.game.players.append(interaction.user)
        await interaction.response.edit_message(embed=self.update_embed(), view=self)

    @discord.ui.button(label="退出", style=discord.ButtonStyle.red, emoji="🚪", row=1)
    async def leave_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user not in self.game.players: return
        self.game.players.remove(interaction.user)
        await interaction.response.edit_message(embed=self.update_embed(), view=self)

    @discord.ui.button(label="開始遊戲", style=discord.ButtonStyle.blurple, emoji="🚀", row=1)
    async def start_button(self, interaction: discord.Interaction, button: Button):
        is_dev = await self.cog.bot.is_owner(interaction.user)
        if interaction.user.id != self.game.host.id and not is_dev:
            return await interaction.response.send_message("權限不足", ephemeral=True)
        
        if len(self.game.players) < 3: return await interaction.response.send_message("人數不足 (最少 3)", ephemeral=True)
        if interaction.user.voice and not self.ctx.guild.voice_client: await interaction.user.voice.channel.connect()
        
        success = await self.cog.start_game_logic(self.ctx)
        if success:
            self.stop()
            await interaction.response.send_message("遊戲開始！分配身分中...", ephemeral=False)

    @discord.ui.button(label="關閉大廳", style=discord.ButtonStyle.grey, emoji="✖️", row=1)
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        is_dev = await self.cog.bot.is_owner(interaction.user)
        is_admin = interaction.user.guild_permissions.administrator
        if interaction.user.id != self.game.host.id and not is_admin and not is_dev: return
        if self.ctx.guild.id in self.cog.games: del self.cog.games[self.ctx.guild.id]
        self.stop()
        await interaction.response.edit_message(embed=discord.Embed(title="🛑 已關閉", color=discord.Color.light_grey()), view=None)

# --- 2. 身分確認 ---
class IdentityView(View):
    def __init__(self, game, cog, ctx):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog
        self.ctx = ctx
        self.started = False 

    @discord.ui.button(label="🕵️ 查看身分 (並確認)", style=discord.ButtonStyle.primary)
    async def check_identity(self, interaction: discord.Interaction, button: Button):
        if interaction.user not in self.game.players: return
        
        role = self.game.roles.get(interaction.user.id)
        
        camp = "未知"
        if role in WOLF_CAMP: camp = "🐺 狼人陣營"
        elif role in GOD_CAMP: camp = "🔱 神職陣營"
        elif role in VILLAGER_CAMP: camp = "👱 村民陣營"
        
        msg = f"你的身分是：**{role}** ({camp})"
        
        # [修正] 使用 WOLF_CAMP 判斷，自動涵蓋狼王
        if role in WOLF_CAMP:
            teammates = [p.display_name for p in self.game.players if self.game.is_wolf_team(p.id) and p.id != interaction.user.id]
            msg += f"\n🐺 隊友：{', '.join(teammates) if teammates else '無 (孤狼)'}"
            msg += "\n🔪 目標：**屠邊** (殺光神職 或 殺光村民)。"
            msg += "\n💬 **請注意：狼人聊天室已建立，請在頻道列表中查看並進入討論。**"
            if role == ROLE_WOLF_KING: msg += "\n👑 特殊能力：死後可以開槍帶走一人 (被毒死除外)。"
        elif role == ROLE_SEER: msg += "\n🔮 技能：每晚查驗一名玩家是好人還是狼人。"
        elif role == ROLE_WITCH: msg += "\n🧪 技能：解藥(救人)與毒藥(殺人)，每晚限用一瓶。"
        elif role == ROLE_HUNTER: msg += "\n🔫 技能：死後可開槍帶走一人 (被毒死除外)。"
        elif role == ROLE_MERCHANT: msg += "\n💰 技能：限一次，賜予一名玩家(幸運兒) 查驗/毒藥/守衛 技能。\n⚠️ **風險：若選中狼人，你將死亡！**"
        else: msg += "\n🏡 技能：無。努力推理並活下去。"
        
        self.game.confirmed_players.add(interaction.user.id)
        checked = len(self.game.confirmed_players)
        total = len(self.game.players)
        
        await interaction.response.send_message(msg, ephemeral=True)

        try:
            content = f"🎲 **身分已分配！請確認身分以開始遊戲**\n(目前確認進度: **{checked}/{total}**)"
            await interaction.message.edit(content=content)
        except: pass

        if checked >= total and not self.started:
            self.started = True
            self.stop()
            await self.ctx.send("🌕 **全員已確認身分，天黑請閉眼...**")
            await self.cog.start_night(self.ctx, self.game)

    @discord.ui.button(label="強制入夜", style=discord.ButtonStyle.danger)
    async def force_start(self, interaction: discord.Interaction, button: Button):
        is_dev = await self.cog.bot.is_owner(interaction.user)
        if interaction.user.id != self.game.host.id and not is_dev:
            return await interaction.response.send_message("權限不足", ephemeral=True)
        
        if not self.started:
            self.started = True
            self.stop()
            await interaction.response.send_message("🚨 強制進入夜晚！", ephemeral=False)
            await self.cog.start_night(self.ctx, self.game)

# --- 3. 夜間選單 ---
class WolfSelect(Select):
    def __init__(self, game, cog, ctx):
        self.game = game
        self.cog = cog
        self.ctx = ctx
        options = [discord.SelectOption(label="不殺 (空刀)", value="-1", emoji="☮️")]
        options += [discord.SelectOption(label=p.display_name, value=str(p.id), emoji="👤") for p in game.players if game.is_alive(p.id)]
        super().__init__(placeholder="🔪 狼隊投票...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        target_id = int(self.values[0])
        self.game.wolf_votes[interaction.user.id] = target_id
        self.game.night_actions.add(interaction.user.id)
        
        target_obj = interaction.guild.get_member(target_id)
        target_name = "空刀" if target_id == -1 else (target_obj.display_name if target_obj else "未知")
        
        await interaction.response.send_message(f"🩸 你投給了：**{target_name}**", ephemeral=True)
        
        # [修正] 使用 is_wolf_team 確保狼王也算在內
        alive_wolves = [p for p in self.game.players if self.game.is_alive(p.id) and self.game.is_wolf_team(p.id)]
        valid_votes = [uid for uid in self.game.wolf_votes.keys() if uid in [w.id for w in alive_wolves]]
        
        if len(valid_votes) >= len(alive_wolves):
            await self.cog.check_night_phase_1_end(self.ctx, self.game)

class SeerSelect(Select):
    def __init__(self, game, cog, ctx):
        self.game = game
        self.cog = cog
        self.ctx = ctx
        options = [discord.SelectOption(label="不驗 (空驗)", value="-1", emoji="☮️")]
        options += [discord.SelectOption(label=p.display_name, value=str(p.id), emoji="🔍") for p in game.players if game.is_alive(p.id)]
        super().__init__(placeholder="🔮 預言家查驗...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id in self.game.night_actions: return await interaction.response.send_message("已查驗過", ephemeral=True)
        target_id = int(self.values[0])
        self.game.night_actions.add(interaction.user.id)
        
        if target_id == -1:
            await interaction.response.send_message("🔮 你選擇不查驗。", ephemeral=True)
        else:
            role = self.game.roles.get(target_id)
            # [修正] 使用 WOLF_CAMP 判斷壞人
            res = "🐺 狼人 (壞人)" if role in WOLF_CAMP else "好人"
            await interaction.response.send_message(f"🔮 查驗結果：{res}", ephemeral=True)
        
        await self.cog.check_night_phase_1_end(self.ctx, self.game)

class MerchantSkillSelect(Select):
    def __init__(self, game, cog, ctx, target_id):
        self.game = game
        self.cog = cog
        self.ctx = ctx
        self.target_id = target_id
        options = [
            discord.SelectOption(label="給予 查驗 技能", value="check", emoji="🔮"),
            discord.SelectOption(label="給予 毒藥 技能", value="poison", emoji="☠️"),
            discord.SelectOption(label="給予 守衛 技能", value="guard", emoji="🛡️")
        ]
        super().__init__(placeholder="💰 請選擇要給予的技能...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        skill = self.values[0]
        self.game.lucky_data = {"user_id": self.target_id, "skill": skill, "target": None}
        self.game.merchant_status["used"] = True
        self.game.night_actions.add(interaction.user.id)
        
        target_obj = interaction.guild.get_member(self.target_id)
        t_name = target_obj.display_name if target_obj else "未知"
        await interaction.response.send_message(f"💰 給予了 **{t_name}** **{skill}** 技能。", ephemeral=True)
        await self.cog.check_night_phase_1_end(self.ctx, self.game)

class MerchantTargetSelect(Select):
    def __init__(self, game, cog, ctx):
        self.game = game
        self.cog = cog
        self.ctx = ctx
        options = [discord.SelectOption(label=p.display_name, value=str(p.id), emoji="👤") 
                   for p in game.players if game.is_alive(p.id) and p.id != interaction.user.id] 
        super().__init__(placeholder="💰 請選擇一名幸運兒...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        target_id = int(self.values[0])
        view = View()
        view.add_item(MerchantSkillSelect(self.game, self.cog, self.ctx, target_id))
        await interaction.response.send_message("請選擇要給予的技能：", view=view, ephemeral=True)

class NightViewPhase1(View):
    def __init__(self, game, cog, ctx):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog
        self.ctx = ctx

    @discord.ui.button(label="進行夜晚行動", style=discord.ButtonStyle.primary, emoji="🌙")
    async def action(self, interaction: discord.Interaction, button: Button):
        uid = interaction.user.id
        if not self.game.is_alive(uid): return await interaction.response.send_message("你已死亡", ephemeral=True)
        role = self.game.roles.get(uid)
        
        # [修正] 使用 WOLF_CAMP 判斷是否顯示狼人選單
        if role in WOLF_CAMP:
            await interaction.response.send_message("🐺 **狼人行動**", view=View().add_item(WolfSelect(self.game, self.cog, self.ctx)), ephemeral=True)
        elif role == ROLE_SEER:
            if uid in self.game.night_actions: return await interaction.response.send_message("已行動", ephemeral=True)
            await interaction.response.send_message("🔮 **預言家行動**", view=View().add_item(SeerSelect(self.game, self.cog, self.ctx)), ephemeral=True)
        elif role == ROLE_MERCHANT:
            if self.game.merchant_status["used"] or uid in self.game.night_actions: 
                return await interaction.response.send_message("已行動或技能已用。", ephemeral=True)
            view = View()
            view.add_item(MerchantTargetSelect(self.game, self.cog, self.ctx))
            async def skip_callback(inter):
                self.game.night_actions.add(inter.user.id)
                await inter.response.send_message("💤 選擇不發動。", ephemeral=True)
                await self.cog.check_night_phase_1_end(self.ctx, self.game)
            skip_btn = Button(label="今晚不發動", style=discord.ButtonStyle.grey)
            skip_btn.callback = skip_callback
            view.add_item(skip_btn)
            await interaction.response.send_message("💰 **奇跡商人**，是否給予技能？", view=view, ephemeral=True)
        else:
            await interaction.response.send_message("💤 無需行動。", ephemeral=True)

# --- 4. 下半夜 (女巫/幸運兒) ---
class WitchActionView(View):
    def __init__(self, game, cog, ctx):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog
        self.ctx = ctx
        self.target_id = game.wolf_target
    
    @discord.ui.button(label="解藥 (救)", style=discord.ButtonStyle.green, emoji="💊")
    async def save_btn(self, interaction: discord.Interaction, button: Button):
        if not self.game.witch_potions["antidote"]: return await interaction.response.send_message("❌ 解藥已用完。", ephemeral=True)
        if self.target_id == -1: return await interaction.response.send_message("❌ 無人被殺。", ephemeral=True)
        self.game.witch_potions["antidote"] = False
        self.game.wolf_target = -1 
        self.game.night_actions.add(interaction.user.id)
        await interaction.response.send_message("💊 使用了解藥。", ephemeral=True)
        await self.cog.check_night_phase_2_end(self.ctx, self.game)

    @discord.ui.button(label="毒藥 (毒)", style=discord.ButtonStyle.danger, emoji="☠️")
    async def poison_btn(self, interaction: discord.Interaction, button: Button):
        if not self.game.witch_potions["poison"]: return await interaction.response.send_message("❌ 毒藥已用完。", ephemeral=True)
        view = View()
        select = Select(placeholder="☠️ 選擇毒殺...", options=[discord.SelectOption(label=p.display_name, value=str(p.id)) for p in self.game.players if self.game.is_alive(p.id)])
        async def poison_callback(ctx_inter):
            self.game.witch_poison_target = int(select.values[0])
            self.game.witch_potions["poison"] = False
            self.game.night_actions.add(interaction.user.id)
            await ctx_inter.response.send_message(f"☠️ 已下毒。", ephemeral=True)
            await self.cog.check_night_phase_2_end(self.ctx, self.game)
        select.callback = poison_callback
        view.add_item(select)
        await interaction.response.send_message("選擇毒殺對象：", view=view, ephemeral=True)

    @discord.ui.button(label="什麼都不做", style=discord.ButtonStyle.grey)
    async def skip_btn(self, interaction: discord.Interaction, button: Button):
        self.game.night_actions.add(interaction.user.id)
        await interaction.response.send_message("💤 什麼都不做。", ephemeral=True)
        await self.cog.check_night_phase_2_end(self.ctx, self.game)

class LuckyOneView(View):
    def __init__(self, game, cog, ctx, skill):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog
        self.ctx = ctx
        self.skill = skill
        options = [discord.SelectOption(label=p.display_name, value=str(p.id)) for p in game.players if game.is_alive(p.id)]
        if skill == "check":
            select = Select(placeholder="🔮 [幸運兒] 請查驗...", options=options)
            select.callback = self.check_callback
        elif skill == "poison":
            select = Select(placeholder="☠️ [幸運兒] 請下毒...", options=options)
            select.callback = self.poison_callback
        elif skill == "guard":
            select = Select(placeholder="🛡️ [幸運兒] 請守護...", options=options)
            select.callback = self.guard_callback
        self.add_item(select)

    async def check_callback(self, interaction: discord.Interaction):
        target = int(interaction.data['values'][0])
        role = self.game.roles.get(target)
        # [修正] 幸運兒查驗也統一用 WOLF_CAMP
        res = "🐺 狼人" if role in WOLF_CAMP else "好人"
        self.game.lucky_data["target"] = target 
        await interaction.response.send_message(f"🔮 查驗結果：{res}", ephemeral=True)
        await self.cog.check_night_phase_2_end(self.ctx, self.game)

    async def poison_callback(self, interaction: discord.Interaction):
        target = int(interaction.data['values'][0])
        self.game.lucky_data["target"] = target 
        await interaction.response.send_message("☠️ 發動毒藥。", ephemeral=True)
        await self.cog.check_night_phase_2_end(self.ctx, self.game)

    async def guard_callback(self, interaction: discord.Interaction):
        target = int(interaction.data['values'][0])
        self.game.guard_target = target
        self.game.lucky_data["target"] = target
        await interaction.response.send_message("🛡️ 發動守護。", ephemeral=True)
        await self.cog.check_night_phase_2_end(self.ctx, self.game)

class NightViewPhase2(View):
    def __init__(self, game, cog, ctx):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog
        self.ctx = ctx

    @discord.ui.button(label="下半夜行動", style=discord.ButtonStyle.primary, emoji="✨")
    async def action(self, interaction: discord.Interaction, button: Button):
        uid = interaction.user.id
        role = self.game.roles.get(uid)
        
        if role == ROLE_WITCH:
            if not self.game.is_alive(uid): return await interaction.response.send_message("已死", ephemeral=True)
            if uid in self.game.night_actions: return await interaction.response.send_message("已行動", ephemeral=True)
            dead_name = "無人"
            if self.game.wolf_target != -1:
                obj = self.ctx.guild.get_member(self.game.wolf_target)
                if obj: dead_name = obj.display_name
            msg = f"🧙‍♀️ 今晚 **{dead_name}** 被狼人殺害了。"
            await interaction.response.send_message(msg, view=WitchActionView(self.game, self.cog, self.ctx), ephemeral=True)
            return

        if self.game.lucky_data["user_id"] == uid and self.game.lucky_data["target"] is None:
            if not self.game.is_alive(uid): return await interaction.response.send_message("已死", ephemeral=True)
            skill = self.game.lucky_data["skill"]
            await interaction.response.send_message(f"✨ 你是幸運兒！獲得 **{skill}** 技能！", view=LuckyOneView(self.game, self.cog, self.ctx, skill), ephemeral=True)
            return

        await interaction.response.send_message("💤 繼續睡覺。", ephemeral=True)

# --- 5. 獵人/狼王 ---
class ShooterSelect(Select):
    def __init__(self, game, cog, ctx, role_name):
        self.game = game
        self.cog = cog
        self.ctx = ctx
        self.role_name = role_name
        options = [discord.SelectOption(label=p.display_name, value=str(p.id), emoji="🔫") for p in game.players if game.is_alive(p.id)]
        super().__init__(placeholder=f"🔫 {role_name}開槍...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        target_id = int(self.values[0])
        self.game.status[target_id] = "dead"
        role = self.game.roles.get(target_id)
        target_user = interaction.guild.get_member(target_id)
        if target_user: 
            try: await target_user.edit(mute=True)
            except: pass
        await interaction.response.send_message(f"💥 {self.role_name} 帶走了 **{target_user.display_name}** ({role})")
        winner = self.cog.check_winner(self.game)
        if winner: await self.cog.end_game(self.ctx, self.game, winner)
        else: await self.cog.start_night(self.ctx, self.game)

class ShooterView(View):
    def __init__(self, game, cog, ctx, role_name):
        super().__init__(timeout=None)
        self.add_item(ShooterSelect(game, cog, ctx, role_name))

# --- 6. 投票 ---
class CandidateButton(Button):
    def __init__(self, player, game, cog, ctx, view):
        super().__init__(label=player.display_name, style=discord.ButtonStyle.secondary)
        self.target_id = player.id
        self.game = game
        self.cog = cog
        self.ctx = ctx
        self.parent_view = view

    async def callback(self, interaction: discord.Interaction):
        if not self.game.is_alive(interaction.user.id): return await interaction.response.send_message("已死", ephemeral=True)
        self.game.votes[interaction.user.id] = self.target_id
        await interaction.response.send_message(f"🗳️ 投給了 **{self.label}**")
        if len(self.game.votes) >= len(self.game.get_alive_players()):
            self.parent_view.stop()
            await self.cog.tally_votes(self.ctx, self.game)

class VotingView(View):
    def __init__(self, game, cog, ctx):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog
        self.ctx = ctx
        for p in game.players:
            if game.is_alive(p.id): self.add_item(CandidateButton(p, game, cog, ctx, self))

    @discord.ui.button(label="🏳️ 投票結束遊戲", style=discord.ButtonStyle.danger, row=4)
    async def stop_vote(self, interaction: discord.Interaction, button: Button):
        if not self.game.is_alive(interaction.user.id): return await interaction.response.send_message("已死", ephemeral=True)
        if interaction.user.id in self.game.stop_votes: return await interaction.response.send_message("已投", ephemeral=True)
        self.game.stop_votes.add(interaction.user.id)
        curr, need = len(self.game.stop_votes), len(self.game.get_alive_players()) // 2 + 1
        await interaction.response.send_message(f"🏳️ 提議結束 ({curr}/{need})")
        if curr >= need:
            self.stop()
            await self.cog.stop_game(self.ctx, "玩家投票強制結束")

# --- 7. 主程式 ---
class Werewolf(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games = {}

    def get_game(self, ctx):
        return self.games.get(ctx.guild.id)

    async def mute_all(self, ctx, game, mute=True):
        """安全靜音"""
        for p in game.players:
            try:
                member = ctx.guild.get_member(p.id)
                if member and member.voice:
                    await member.edit(mute=mute)
            except: pass

    async def play_mixed_audio(self, ctx, bgm, voice=None):
        vc = ctx.guild.voice_client
        if not vc: return
        bgm_p = os.path.join(SOUND_FOLDER, bgm)
        if not os.path.exists(bgm_p): return
        if vc.is_playing(): vc.stop()
        opts = '-vn'
        if voice:
            vp = os.path.join(SOUND_FOLDER, voice)
            if os.path.exists(vp):
                complex_filter = f'[0:a]volume=0.4[bg];[1:a]volume=1.5[vc];[bg][vc]amix=inputs=2:duration=first:dropout_transition=2'
                before = f'-stream_loop -1 -i "{bgm_p}" -filter_complex "{complex_filter}"'
                vc.play(discord.FFmpegPCMAudio(vp, before_options=before, options=opts))
                return
        vc.play(discord.FFmpegPCMAudio(bgm_p, before_options="-stream_loop -1", options=opts))

    async def stop_bgm(self, ctx):
        vc = ctx.guild.voice_client
        if vc and vc.is_playing(): vc.stop()

    @commands.hybrid_command(name='ww_create')
    async def create_game(self, ctx):
        if ctx.guild.id in self.games: return await ctx.send("已有遊戲", ephemeral=True)
        game = WerewolfGame(ctx.channel, ctx.author)
        self.games[ctx.guild.id] = game
        msg = await ctx.send(embed=LobbyView(self, game, ctx).update_embed(), view=LobbyView(self, game, ctx))
        view = LobbyView(self, game, ctx) 
        view.message = msg

    @commands.hybrid_command(name='ww_force_stop')
    @commands.has_permissions(administrator=True)
    async def force_stop(self, ctx):
        await self.stop_game(ctx, "管理員強制結束")

    async def stop_game(self, ctx, reason=""):
        if ctx.guild.id in self.games:
            game = self.games[ctx.guild.id]
            
            if game.wolf_thread:
                try: await game.wolf_thread.delete()
                except: pass
            
            asyncio.create_task(self.mute_all(ctx, game, False))
            asyncio.create_task(self.stop_bgm(ctx))
            del self.games[ctx.guild.id]
            await ctx.send(f"🛑 **遊戲結束**: {reason}")

    async def end_game(self, ctx, game, winner):
        await ctx.send(f"🏆 **遊戲結束！獲勝者: {winner}**")
        role_reveal = "\n".join([f"{p.display_name}: {game.roles[p.id]}" for p in game.players])
        await ctx.send(f"**身分揭曉：**\n{role_reveal}")
        await self.stop_game(ctx, "正常結束")

    async def start_game_logic(self, ctx):
        game = self.get_game(ctx)
        if not game: return
        n = len(game.players)
        
        wolves_count = max(1, n // 3)
        w, k, s, wi, h, m = wolves_count, 0, 0, 0, 0, 0
        
        if game.board_id == "auto":
            if n < 6: w, k, s, wi, h, m = 1, 0, 1, 0, 0, 0 
            elif n < 9: w, k, s, wi, h, m = 1, 1, 1, 1, 1, 0
            elif n < 10: w, k, s, wi, h, m = 2, 1, 1, 1, 1, 0
            else: w, k, s, wi, h, m = 2, 1, 1, 1, 1, 1
        elif game.board_id == "standard":
            s, wi, h = 1, 1, 1
            w = max(1, wolves_count)
        elif game.board_id == "wolf_king":
            s, wi, h, k = 1, 1, 1, 1
            w = max(0, wolves_count - 1)
        elif game.board_id == "merchant":
            s, wi, h, m, k = 1, 1, 1, 1, 1
            w = max(0, wolves_count - 1)

        total_needed = w + k + s + wi + h + m
        if n < total_needed:
            await ctx.send(f"❌ 人數不足！此板子至少需要 {total_needed} 人。")
            return False

        roles = [ROLE_WEREWOLF]*w + [ROLE_WOLF_KING]*k + [ROLE_SEER]*s + [ROLE_WITCH]*wi + [ROLE_HUNTER]*h + [ROLE_MERCHANT]*m
        while len(roles) < n: roles.append(ROLE_VILLAGER)
        random.shuffle(roles)
        game.roles = {p.id: roles[i] for i, p in enumerate(game.players)}
        game.status = {p.id: "alive" for p in game.players}
        
        try:
            thread = await ctx.channel.create_thread(name=f"🐺-狼人-{random.randint(100,999)}", type=discord.ChannelType.private_thread, invitable=False)
            game.wolf_thread = thread
            mentions = []
            for pid, role in game.roles.items():
                if role in WOLF_CAMP:
                    mem = ctx.guild.get_member(pid)
                    if mem: 
                        await thread.add_user(mem)
                        mentions.append(mem.mention)
            await thread.send(f"🐺 **狼人密謀區**\n成員：{' '.join(mentions)}\n天黑請在此討論。")
        except Exception as e:
            print(f"無法建立狼人討論串: {e}")

        await game.channel.send("🎲 **身分已分配！請確認身分以開始遊戲**", view=IdentityView(game, self, ctx))
        return True

    async def start_night(self, ctx, game):
        try:
            game.phase = PHASE_NIGHT_1
            game.wolf_target = None
            game.wolf_votes.clear()
            game.night_actions.clear()
            game.witch_poison_target = None
            game.deaths_tonight = []
            game.guard_target = None
            game.lucky_data = {"user_id": None, "skill": None, "target": None}
            game.confirmed_players.clear()
            
            # --- [動態生成夜晚訊息] ---
            has_witch_role = ROLE_WITCH in game.roles.values()
            has_merchant_role = ROLE_MERCHANT in game.roles.values()
            needs_phase_2 = has_witch_role or has_merchant_role

            p1_roles = []
            if any(r in game.roles.values() for r in WOLF_CAMP): p1_roles.append("狼人")
            if ROLE_SEER in game.roles.values(): p1_roles.append("預言家")
            if ROLE_MERCHANT in game.roles.values(): p1_roles.append("奇跡商人")
            
            title = "🌃 上半夜" if needs_phase_2 else "🌃 夜晚"
            roles_str = "、".join(p1_roles) if p1_roles else "無人"
            
            if game.wolf_thread:
                try: await game.wolf_thread.send("🌃 **天黑了，請開始討論戰術！**")
                except: pass
            
            await game.channel.send(f"{title}：{roles_str} (請點擊行動)", view=NightViewPhase1(game, self, ctx))
            
            asyncio.create_task(self.safe_play_audio(ctx))
            asyncio.create_task(self.mute_all(ctx, game, True))
            
        except Exception as e:
            print(traceback.format_exc())
            await ctx.send(f"⚠️ 入夜發生錯誤: {e}")

    async def safe_play_audio(self, ctx):
        try:
            await self.play_mixed_audio(ctx, "night.mp3", "voice_night_start.mp3")
        except Exception as e:
            print(f"音效播放失敗: {e}")

    async def check_night_phase_1_end(self, ctx, game):
        alive_wolves = [p for p in game.players if game.is_alive(p.id) and game.is_wolf_team(p.id)]
        alive_seer = [p for p in game.players if game.is_alive(p.id) and game.roles[p.id] == ROLE_SEER]
        alive_merchant = [p for p in game.players if game.is_alive(p.id) and game.roles[p.id] == ROLE_MERCHANT]
        
        wolves_done = len([v for v in game.wolf_votes.keys() if v in [w.id for w in alive_wolves]]) >= len(alive_wolves)
        seer_done = not alive_seer or alive_seer[0].id in game.night_actions
        merchant_done = True
        if alive_merchant:
            m_id = alive_merchant[0].id
            if not game.merchant_status["used"] and m_id not in game.night_actions:
                merchant_done = False

        # Debug print
        print(f"[Debug] 狼隊({len(alive_wolves)}): {wolves_done}, 預({len(alive_seer)}): {seer_done}, 商({len(alive_merchant)}): {merchant_done}")

        if wolves_done and seer_done and merchant_done:
            if game.wolf_votes:
                valid_votes = [t for u, t in game.wolf_votes.items() if u in [w.id for w in alive_wolves]]
                if valid_votes:
                    most = Counter(valid_votes).most_common()
                    candidates = [t for t, c in most if c == most[0][1]]
                    game.wolf_target = random.choice(candidates)
                else: game.wolf_target = -1
            else: game.wolf_target = -1
            
            # --- [智慧跳夜判斷] ---
            has_witch_role = ROLE_WITCH in game.roles.values()
            has_merchant_role = ROLE_MERCHANT in game.roles.values()
            
            if not has_witch_role and not has_merchant_role:
                await self.start_day(ctx, game)
            else:
                await self.start_night_phase_2(ctx, game)

    async def start_night_phase_2(self, ctx, game):
        game.phase = PHASE_NIGHT_2
        game.night_actions.clear()
        if game.lucky_data["skill"]: game.lucky_data["target"] = None 
        
        p2_roles = []
        if ROLE_WITCH in game.roles.values(): p2_roles.append("女巫")
        if game.lucky_data["user_id"]: p2_roles.append("幸運兒")
        roles_str = "、".join(p2_roles) if p2_roles else "無"

        await game.channel.send(f"🧙‍♀️ **下半夜：{roles_str}**", view=NightViewPhase2(game, self, ctx))
        
        alive_witches = [p for p in game.players if game.is_alive(p.id) and game.roles[p.id] == ROLE_WITCH]
        lucky_id = game.lucky_data["user_id"]
        has_alive_lucky = lucky_id and game.is_alive(lucky_id)
        
        if not alive_witches and not has_alive_lucky:
            await asyncio.sleep(random.randint(5, 10)) 
            await self.start_day(ctx, game)

    async def check_night_phase_2_end(self, ctx, game):
        alive_witch = [p for p in game.players if game.is_alive(p.id) and game.roles[p.id] == ROLE_WITCH]
        witch_done = not alive_witch or alive_witch[0].id in game.night_actions
        
        lucky_done = True
        lid = game.lucky_data["user_id"]
        if lid and game.is_alive(lid) and game.lucky_data["target"] is None:
             lucky_done = False
        
        if witch_done and lucky_done: 
            await self.start_day(ctx, game)

    async def start_day(self, ctx, game):
        game.phase = PHASE_DAY
        game.votes = {}
        game.stop_votes.clear()
        
        asyncio.create_task(self.stop_bgm(ctx))
        asyncio.create_task(self.mute_all(ctx, game, False))
        
        deaths = []
        if game.wolf_target != -1 and game.wolf_target != game.guard_target: deaths.append(game.wolf_target)
        if game.witch_poison_target: deaths.append(game.witch_poison_target)
        if game.lucky_data["skill"] == "poison" and game.lucky_data["target"]: deaths.append(game.lucky_data["target"])

        if game.lucky_data["user_id"]:
            lucky_id = game.lucky_data["user_id"]
            if game.is_wolf_team(lucky_id): 
                for pid, role in game.roles.items():
                    if role == ROLE_MERCHANT and game.is_alive(pid):
                        deaths.append(pid)
                        break

        game.deaths_tonight = list(set(deaths))
        
        msg = "🌅 **天亮了！**\n"
        if not game.deaths_tonight: msg += "昨晚是個平安夜。"
        else:
            msg += "昨晚死亡名單：\n"
            for uid in game.deaths_tonight:
                user = ctx.guild.get_member(uid)
                game.status[uid] = "dead"
                msg += f"💀 **{user.display_name if user else '未知'}**\n"
                if user: 
                    try: await user.edit(mute=True)
                    except: pass

        winner = self.check_winner(game)
        if winner: return await self.end_game(ctx, game, winner)
        await game.channel.send(msg)

        shooter_died = False
        shooter_role = ""
        for uid in game.deaths_tonight:
            role = game.roles.get(uid)
            # [修正] 使用 SHOOTER_ROLES
            if role in SHOOTER_ROLES:
                is_poisoned = (uid == game.witch_poison_target) or (game.lucky_data["skill"] == "poison" and uid == game.lucky_data["target"])
                if is_poisoned:
                    await game.channel.send(f"🚫 {role} 被毒殺，無法開槍！")
                else:
                    shooter_died = True
                    shooter_role = role
        
        if shooter_died:
            game.phase = PHASE_SHOOT
            await game.channel.send(f"🔫 **{shooter_role} 發動技能！請開槍帶走一人！**", view=ShooterView(game, self, ctx, shooter_role))
            return

        await game.channel.send("現在開始討論，並點擊下方按鈕投票。", view=VotingView(game, self, ctx))

    def check_winner(self, game):
        wolves = sum(1 for pid, s in game.status.items() if s=="alive" and game.is_wolf_team(pid))
        gods = sum(1 for pid, s in game.status.items() if s=="alive" and game.is_god(pid))
        villagers = sum(1 for pid, s in game.status.items() if s=="alive" and game.is_villager(pid))
        
        if wolves == 0: return "好人陣營"
        if gods == 0 or villagers == 0: return "狼人陣營"
        if wolves >= (gods + villagers): return "狼人陣營"
        
        return None

    async def tally_votes(self, ctx, game):
        vote_counts = Counter(game.votes.values())
        if not vote_counts:
            await game.channel.send("無人投票，直接入夜。")
            return await self.start_night(ctx, game)

        most = vote_counts.most_common()
        max_v = most[0][1]
        cands = [k for k, v in most if v == max_v]

        if len(cands) > 1:
            await game.channel.send(f"⚖️ 平票 ({max_v}票)，無人被處決。")
            await self.start_night(ctx, game)
        else:
            dead_id = cands[0]
            game.status[dead_id] = "dead"
            user = ctx.guild.get_member(dead_id)
            role = game.roles[dead_id]
            if user: 
                try: await user.edit(mute=True)
                except: pass
            
            await game.channel.send(f"💀 **{user.display_name}** 被處決了！身分：**{role}**")
            
            winner = self.check_winner(game)
            if winner: return await self.end_game(ctx, game, winner)

            # [修正] 使用 SHOOTER_ROLES
            if role in SHOOTER_ROLES:
                game.phase = PHASE_SHOOT
                await game.channel.send(f"🔫 **{role} 發動技能！請開槍帶走一人！**", view=ShooterView(game, self, ctx, role))
            else:
                await self.start_night(ctx, game)

async def setup(bot):
    await bot.add_cog(Werewolf(bot))