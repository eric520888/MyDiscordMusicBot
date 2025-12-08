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
    
    def is_wolf_team(self, user_id):
        role = self.roles.get(user_id)
        return role in ["狼人", "狼王"]

# --- 1. 大廳與設定 ---
class BoardSelect(Select):
    def __init__(self, game):
        self.game = game
        options = [
            discord.SelectOption(label="🎲 自動配置 (預設)", value="auto", description="依照人數自動平衡 (3-5人無女巫)"),
            discord.SelectOption(label="🔮 標準板 (預女獵)", value="standard", description="強制開啟女巫/獵人"),
            discord.SelectOption(label="👑 狼王板 (預女獵+狼王)", value="wolf_king", description="加入狼王"),
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
        msg = f"你的身分是：**{role}**"
        
        if role in ["狼人", "狼王"]:
            teammates = [p.display_name for p in self.game.players if self.game.is_wolf_team(p.id) and p.id != interaction.user.id]
            msg += f"\n🐺 隊友：{', '.join(teammates) if teammates else '無 (孤狼)'}"
            msg += "\n🔪 目標：與隊友投票殺死村民。"
            if role == "狼王": msg += "\n👑 特殊能力：死後可以開槍帶走一人 (被毒死除外)。"
        elif role == "預言家": msg += "\n🔮 技能：每晚查驗一名玩家是好人還是狼人。"
        elif role == "女巫": msg += "\n🧪 技能：解藥(救人)與毒藥(殺人)，每晚限用一瓶。"
        elif role == "獵人": msg += "\n🔫 技能：死後可開槍帶走一人 (被毒死除外)。"
        elif role == "奇跡商人": msg += "\n💰 技能：限一次，賜予一名玩家(幸運兒) 查驗/毒藥/守衛 技能。\n⚠️ **風險：若選中狼人，你將死亡！**"
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
            res = "🐺 狼人 (壞人)" if role in ["狼人", "狼王"] else "好人"
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
        
        if role in ["狼人", "狼王"]:
            await interaction.response.send_message("🐺 **狼人行動**", view=View().add_item(WolfSelect(self.game, self.cog, self.ctx)), ephemeral=True)
        elif role == "預言家":
            if uid in self.game.night_actions: return await interaction.response.send_message("已行動", ephemeral=True)
            await interaction.response.send_message("🔮 **預言家行動**", view=View().add_item(SeerSelect(self.game, self.cog, self.ctx)), ephemeral=True)
        elif role == "奇跡商人":
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
        res = "🐺 狼人" if role in ["狼人", "狼王"] else "好人"
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
        
        if role == "女巫":
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

        roles = ["狼人"]*w + ["狼王"]*k + ["預言家"]*s + ["女巫"]*wi + ["獵人"]*h + ["奇跡商人"]*m
        while len(roles) < n: roles.append("村民")
        random.shuffle(roles)
        game.roles = {p.id: roles[i] for i, p in enumerate(game.players)}
        game.status = {p.id: "alive" for p in game.players}

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
            
            await game.channel.send("🌃 **上半夜：狼人、預言家、奇跡商人**", view=NightViewPhase1(game, self, ctx))
            
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
        alive_seer = [p for p in game.players if game.is_alive(p.id) and game.roles[p.id] == "預言家"]
        alive_merchant = [p for p in game.players if game.is_alive(p.id) and game.roles[p.id] == "奇跡商人"]
        
        wolves_done = len([v for v in game.wolf_votes.keys() if v in [w.id for w in alive_wolves]]) >= len(alive_wolves)
        seer_done = not alive_seer or alive_seer[0].id in game.night_actions
        merchant_done = True
        if alive_merchant:
            m_id = alive_merchant[0].id
            if not game.merchant_status["used"] and m_id not in game.night_actions:
                merchant_done = False

        if wolves_done and seer_done and merchant_done:
            if game.wolf_votes:
                # 狼人多數決 (平票隨機)
                valid_votes = [t for u, t in game.wolf_votes.items() if u in [w.id for w in alive_wolves]]
                if valid_votes:
                    most = Counter(valid_votes).most_common()
                    max_v = most[0][1]
                    candidates = [t for t, c in most if c == max_v]
                    game.wolf_target = random.choice(candidates)
                else: game.wolf_target = -1
            else: game.wolf_target = -1
            
            # --- [智慧跳夜判斷] ---
            # 檢查是否有任何「角色」存在於板子上 (不是檢查活人，是檢查板子)
            has_witch_role = "女巫" in game.roles.values()
            has_merchant_role = "奇跡商人" in game.roles.values()
            
            # 如果板子上有女巫 或 有奇跡商人(可能有幸運兒)，就必須進下半夜 (哪怕他們死了也要進，這是為了隱藏資訊)
            # 但如果板子上根本沒這兩個角色 (例如3人局)，直接跳天亮
            if not has_witch_role and not has_merchant_role:
                await self.start_day(ctx, game)
            else:
                await self.start_night_phase_2(ctx, game)

    async def start_night_phase_2(self, ctx, game):
        game.phase = PHASE_NIGHT_2
        game.night_actions.clear()
        if game.lucky_data["skill"]: game.lucky_data["target"] = None 
        
        # 發送下半夜面板 (即使沒人活著也要發，假裝有事發生)
        await game.channel.send("🧙‍♀️ **下半夜：女巫與幸運兒**", view=NightViewPhase2(game, self, ctx))
        
        # 檢查是否有活著的行動者
        alive_witches = [p for p in game.players if game.is_alive(p.id) and game.roles[p.id] == "女巫"]
        lucky_id = game.lucky_data["user_id"]
        has_alive_lucky = lucky_id and game.is_alive(lucky_id)
        
        # 如果沒有任何人可以行動 (全死光 或 沒技能)，模擬延遲後自動天亮
        if not alive_witches and not has_alive_lucky:
            await asyncio.sleep(random.randint(5, 10)) # 隨機等待 5-10 秒
            await self.start_day(ctx, game)

    async def check_night_phase_2_end(self, ctx, game):
        # 1. 檢查女巫
        alive_witch = [p for p in game.players if game.is_alive(p.id) and game.roles[p.id] == "女巫"]
        witch_done = not alive_witch or alive_witch[0].id in game.night_actions
        
        # 2. 檢查幸運兒
        lucky_done = True
        lid = game.lucky_data["user_id"]
        # 如果幸運兒活著且有技能，但他還沒選目標 -> 未完成
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
                    if role == "奇跡商人" and game.is_alive(pid):
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
            if role in ["獵人", "狼王"]:
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
        villagers = sum(1 for pid, s in game.status.items() if s=="alive" and not game.is_wolf_team(pid))
        if wolves == 0: return "好人陣營"
        if wolves >= villagers: return "狼人陣營"
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

            if role in ["獵人", "狼王"]:
                game.phase = PHASE_SHOOT
                await game.channel.send(f"🔫 **{role} 發動技能！請開槍帶走一人！**", view=ShooterView(game, self, ctx, role))
            else:
                await self.start_night(ctx, game)

async def setup(bot):
    await bot.add_cog(Werewolf(bot))