import discord
from discord.ext import commands
from discord.ui import Button, View, Select
import random
import asyncio
import os
from collections import Counter

# --- 設定 ---
SOUND_FOLDER = "./sounds"

# 定義遊戲狀態
PHASE_WAITING = "waiting"
PHASE_NIGHT_1 = "night_wolves_seer" # 上半夜：狼人/預言家
PHASE_NIGHT_2 = "night_witch"       # 下半夜：女巫
PHASE_DAY = "day"
PHASE_HUNTER = "hunter_shoot"       # 獵人開槍階段

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
        self.wolf_target = None # 狼人殺目標
        self.witch_poison_target = None # 女巫毒殺目標
        self.night_actions = set() 
        self.stop_votes = set()
        
        # 道具狀態
        self.witch_potions = {"antidote": True, "poison": True} # 解藥, 毒藥
        self.hunter_status = {"can_shoot": True} 
        self.deaths_tonight = [] # 記錄今晚死亡名單 (用於判定獵人是否被毒)

    def get_role(self, user_id):
        return self.roles.get(user_id, "未知")

    def is_alive(self, user_id):
        return self.status.get(user_id) == "alive"

    def get_alive_players(self):
        return [p for p in self.players if self.is_alive(p.id)]

# --- 1. 大廳介面 ---
class LobbyView(View):
    def __init__(self, cog, game, ctx):
        super().__init__(timeout=120)
        self.cog = cog
        self.game = game
        self.ctx = ctx
        self.message = None

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
        embed = discord.Embed(
            title="🐺 狼人殺遊戲大廳",
            description=f"主持人: {self.game.host.display_name}\n\n**已加入玩家 ({len(self.game.players)}):**\n{player_list}",
            color=discord.Color.dark_red()
        )
        embed.set_footer(text="滿 6 人建議配置: 2狼 1預 1女 1獵")
        return embed

    @discord.ui.button(label="加入遊戲", style=discord.ButtonStyle.green, emoji="✋")
    async def join_button(self, interaction: discord.Interaction, button: Button):
        if self.game.phase != PHASE_WAITING: return await interaction.response.send_message("已開始", ephemeral=True)
        if interaction.user in self.game.players: return await interaction.response.send_message("已加入", ephemeral=True)
        self.game.players.append(interaction.user)
        await interaction.response.edit_message(embed=self.update_embed(), view=self)

    @discord.ui.button(label="退出", style=discord.ButtonStyle.red, emoji="🚪")
    async def leave_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user not in self.game.players: return
        self.game.players.remove(interaction.user)
        await interaction.response.edit_message(embed=self.update_embed(), view=self)

    @discord.ui.button(label="開始遊戲", style=discord.ButtonStyle.blurple, emoji="🚀")
    async def start_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.game.host.id: return await interaction.response.send_message("只有主持人可開始", ephemeral=True)
        if len(self.game.players) < 3: return await interaction.response.send_message("人數不足 (最少 3)", ephemeral=True)
        if interaction.user.voice and not self.ctx.guild.voice_client: await interaction.user.voice.channel.connect()
        self.stop()
        await interaction.response.send_message("遊戲開始！分配身分中...", ephemeral=False)
        await self.cog.start_game_logic(self.ctx)

    @discord.ui.button(label="關閉大廳", style=discord.ButtonStyle.grey, emoji="✖️")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.game.host.id: return
        if self.ctx.guild.id in self.cog.games: del self.cog.games[self.ctx.guild.id]
        self.stop()
        await interaction.response.edit_message(embed=discord.Embed(title="🛑 已關閉", color=discord.Color.light_grey()), view=None)

# --- 2. 身分查看 ---
class IdentityView(View):
    def __init__(self, game):
        super().__init__(timeout=None)
        self.game = game

    @discord.ui.button(label="🕵️ 查看我的身分", style=discord.ButtonStyle.secondary)
    async def check_identity(self, interaction: discord.Interaction, button: Button):
        if interaction.user not in self.game.players: return
        role = self.game.roles.get(interaction.user.id)
        msg = f"你的身分是：**{role}**"
        
        if role == "狼人":
            teammates = [p.display_name for p in self.game.players if self.game.roles.get(p.id) == "狼人" and p.id != interaction.user.id]
            msg += f"\n🐺 隊友：{', '.join(teammates) if teammates else '無 (孤狼)'}"
            msg += "\n🔪 目標：與隊友投票殺死村民。"
        elif role == "預言家": msg += "\n🔮 技能：每晚查驗一名玩家是好人還是狼人。"
        elif role == "女巫": msg += "\n🧪 技能：擁有一瓶解藥(救人)和一瓶毒藥(殺人)，每晚只能用一瓶。"
        elif role == "獵人": msg += "\n🔫 技能：死後可以開槍帶走一人 (被毒死除外)。"
        else: msg += "\n🏡 技能：無。努力推理並活下去。"
        
        await interaction.response.send_message(msg, ephemeral=True)

# --- 3. 夜間選單 (上半夜: 狼/預) ---
class WolfSelect(Select):
    def __init__(self, game, cog, ctx):
        self.game = game
        self.cog = cog
        self.ctx = ctx
        options = [discord.SelectOption(label="不殺 (空刀)", value="-1", emoji="☮️")]
        options += [discord.SelectOption(label=p.display_name, value=str(p.id), emoji="👤") for p in game.players if game.is_alive(p.id)]
        super().__init__(placeholder="🔪 狼人投票...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        target_id = int(self.values[0])
        self.game.wolf_votes[interaction.user.id] = target_id
        self.game.night_actions.add(interaction.user.id)
        target_name = "空刀" if target_id == -1 else interaction.guild.get_member(target_id).display_name
        await interaction.response.send_message(f"🩸 你投給了：**{target_name}**", ephemeral=True)
        
        # 檢查是否所有活狼都投了
        alive_wolves = [p for p in self.game.players if self.game.is_alive(p.id) and self.game.roles[p.id] == "狼人"]
        valid_votes = [uid for uid in self.game.wolf_votes if uid in [w.id for w in alive_wolves]]
        
        if len(valid_votes) >= len(alive_wolves):
            # 結算狼人目標
            targets = [t for u, t in self.game.wolf_votes.items() if u in [w.id for w in alive_wolves]]
            if targets:
                most_common = Counter(targets).most_common()
                max_v = most_common[0][1]
                candidates = [t for t, c in most_common if c == max_v]
                self.game.wolf_target = random.choice(candidates)
            else:
                self.game.wolf_target = -1
            
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
            res = "🐺 狼人 (壞人)" if role == "狼人" else "好人"
            await interaction.response.send_message(f"🔮 查驗結果：{res}", ephemeral=True)
        
        await self.cog.check_night_phase_1_end(self.ctx, self.game)

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
        
        if role == "狼人":
            await interaction.response.send_message("🐺 **狼人行動**", view=View().add_item(WolfSelect(self.game, self.cog, self.ctx)), ephemeral=True)
        elif role == "預言家":
            if uid in self.game.night_actions: return await interaction.response.send_message("已行動", ephemeral=True)
            await interaction.response.send_message("🔮 **預言家行動**", view=View().add_item(SeerSelect(self.game, self.cog, self.ctx)), ephemeral=True)
        else:
            await interaction.response.send_message("💤 你現在無需行動，請等待。", ephemeral=True)

# --- 4. 夜間選單 (下半夜: 女巫) ---
class WitchActionView(View):
    def __init__(self, game, cog, ctx):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog
        self.ctx = ctx
        self.target_id = game.wolf_target
    
    @discord.ui.button(label="使用解藥 (救)", style=discord.ButtonStyle.green, emoji="💊")
    async def save_btn(self, interaction: discord.Interaction, button: Button):
        if not self.game.witch_potions["antidote"]:
            return await interaction.response.send_message("❌ 解藥已用完。", ephemeral=True)
        if self.target_id == -1:
            return await interaction.response.send_message("❌ 今晚沒人被殺，無需使用解藥。", ephemeral=True)
        
        # 使用解藥
        self.game.witch_potions["antidote"] = False
        self.game.wolf_target = -1 # 救活
        self.game.night_actions.add(interaction.user.id) # 標記女巫已動
        await interaction.response.send_message("💊 你使用了解藥，今晚平安夜。", ephemeral=True)
        self.stop()
        await self.cog.start_day(self.ctx, self.game)

    @discord.ui.button(label="使用毒藥 (毒)", style=discord.ButtonStyle.danger, emoji="☠️")
    async def poison_btn(self, interaction: discord.Interaction, button: Button):
        if not self.game.witch_potions["poison"]:
            return await interaction.response.send_message("❌ 毒藥已用完。", ephemeral=True)
        
        # 顯示毒藥選單
        view = View()
        select = Select(placeholder="☠️ 選擇要毒殺的玩家...", options=[
            discord.SelectOption(label=p.display_name, value=str(p.id)) 
            for p in self.game.players if self.game.is_alive(p.id)
        ])
        
        async def poison_callback(ctx_inter):
            target = int(select.values[0])
            self.game.witch_poison_target = target
            self.game.witch_potions["poison"] = False
            self.game.night_actions.add(interaction.user.id)
            await ctx_inter.response.send_message(f"☠️ 你毒殺了目標。", ephemeral=True)
            self.stop() # 停止女巫面板
            await self.cog.start_day(self.ctx, self.game)

        select.callback = poison_callback
        view.add_item(select)
        await interaction.response.send_message("選擇毒殺對象：", view=view, ephemeral=True)

    @discord.ui.button(label="什麼都不做", style=discord.ButtonStyle.grey)
    async def skip_btn(self, interaction: discord.Interaction, button: Button):
        self.game.night_actions.add(interaction.user.id)
        await interaction.response.send_message("💤 你選擇什麼都不做。", ephemeral=True)
        self.stop()
        await self.cog.start_day(self.ctx, self.game)

class NightViewPhase2(View):
    def __init__(self, game, cog, ctx):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog
        self.ctx = ctx

    @discord.ui.button(label="女巫請睜眼", style=discord.ButtonStyle.primary, emoji="🧙‍♀️")
    async def witch_wake(self, interaction: discord.Interaction, button: Button):
        uid = interaction.user.id
        if self.game.roles.get(uid) != "女巫":
            return await interaction.response.send_message("你不是女巫。", ephemeral=True)
        if not self.game.is_alive(uid):
            return await interaction.response.send_message("你已死亡，無法使用技能。", ephemeral=True)
        if uid in self.game.night_actions:
            return await interaction.response.send_message("你已行動過。", ephemeral=True)

        # 告知女巫昨晚情況
        dead_name = "無人"
        if self.game.wolf_target != -1:
            obj = self.ctx.guild.get_member(self.game.wolf_target)
            if obj: dead_name = obj.display_name
        
        msg = f"🧙‍♀️ 今晚 **{dead_name}** 被狼人殺害了。\n你有 **{int(self.game.witch_potions['antidote'])}** 瓶解藥，**{int(self.game.witch_potions['poison'])}** 瓶毒藥。"
        
        await interaction.response.send_message(msg, view=WitchActionView(self.game, self.cog, self.ctx), ephemeral=True)

# --- 5. 獵人開槍介面 ---
class HunterShootSelect(Select):
    def __init__(self, game, cog, ctx):
        self.game = game
        self.cog = cog
        self.ctx = ctx
        options = [discord.SelectOption(label=p.display_name, value=str(p.id), emoji="🔫") 
                   for p in game.players if game.is_alive(p.id)]
        super().__init__(placeholder="🔫 獵人請選擇帶走一人...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        target_id = int(self.values[0])
        target_user = interaction.guild.get_member(target_id)
        
        self.game.status[target_id] = "dead"
        role = self.game.roles.get(target_id)
        
        await interaction.response.send_message(f"💥 砰！獵人開槍帶走了 **{target_user.display_name}** (身分: {role})")
        
        # 檢查勝負
        winner = self.cog.check_winner(self.game)
        if winner:
            await self.cog.end_game(self.ctx, self.game, winner)
        else:
            # 獵人開完槍後，繼續原本的流程 (天亮 -> 投票)
            # 因為獵人可能是在投票後死的，這裡簡單處理：如果是白天死，進入天黑；如果是晚上死，進入白天
            # 簡化：獵人結算完，總是檢查是否還在白天，如果是就繼續投票(或直接進夜晚)
            # 這裡簡單導向：開槍完直接進夜晚 (如果是在投票階段死)
            await self.cog.start_night(self.ctx, self.game)

class HunterView(View):
    def __init__(self, game, cog, ctx):
        super().__init__(timeout=None)
        self.add_item(HunterShootSelect(game, cog, ctx))

# --- 6. 白天投票 ---
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

# --- 7. 主程式 Cog ---
class Werewolf(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games = {}

    def get_game(self, ctx):
        return self.games.get(ctx.guild.id)

    async def mute_all(self, ctx, game, mute=True):
        for p in game.players:
            if p.voice: 
                try: await p.edit(mute=mute)
                except: pass

    async def play_bgm(self, ctx, bgm, voice=None):
        vc = ctx.guild.voice_client
        if not vc: return
        bgm_p = os.path.join(SOUND_FOLDER, bgm)
        if not os.path.exists(bgm_p): return
        if vc.is_playing(): vc.stop()
        
        opts = '-vn'
        if voice:
            vp = os.path.join(SOUND_FOLDER, voice)
            if os.path.exists(vp):
                # 混音
                complex_filter = f'[0:a]volume=0.4[bg];[1:a]volume=1.5[vc];[bg][vc]amix=inputs=2:duration=first:dropout_transition=2'
                before = f'-stream_loop -1 -i "{bgm_p}" -filter_complex "{complex_filter}"'
                vc.play(discord.FFmpegPCMAudio(vp, before_options=before, options=opts))
                return
        
        vc.play(discord.FFmpegPCMAudio(bgm_p, before_options="-stream_loop -1", options=opts))

    async def stop_bgm(self, ctx):
        vc = ctx.guild.voice_client
        if vc and vc.is_playing(): vc.stop()

    # --- 流程 ---
    @commands.hybrid_command(name='ww_create')
    async def create_game(self, ctx):
        if ctx.guild.id in self.games: return await ctx.send("已有遊戲", ephemeral=True)
        game = WerewolfGame(ctx.channel, ctx.author)
        self.games[ctx.guild.id] = game
        msg = await ctx.send(embed=LobbyView(self, game, ctx).update_embed(), view=LobbyView(self, game, ctx))
        view = LobbyView(self, game, ctx) # Re-instantiate to keep ref if needed, or better use the one above
        view.message = msg

    @commands.hybrid_command(name='ww_force_stop')
    @commands.has_permissions(administrator=True)
    async def force_stop(self, ctx):
        await self.stop_game(ctx, "管理員強制結束")

    async def stop_game(self, ctx, reason=""):
        if ctx.guild.id in self.games:
            game = self.games[ctx.guild.id]
            await self.mute_all(ctx, game, False)
            await self.stop_bgm(ctx)
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
        
        # 身分分配邏輯
        n = len(game.players)
        if n < 6: # 測試局
            wolves, seers, witches, hunters = 1, 1, 1, 0
        elif n < 9: # 6-8人
            wolves, seers, witches, hunters = 2, 1, 1, 1
        else: # 9人+
            wolves, seers, witches, hunters = 3, 1, 1, 1
            
        roles = ["狼人"]*wolves + ["預言家"]*seers + ["女巫"]*witches + ["獵人"]*hunters
        while len(roles) < n: roles.append("村民")
        random.shuffle(roles)
        
        game.roles = {p.id: roles[i] for i, p in enumerate(game.players)}
        game.status = {p.id: "alive" for p in game.players}

        await game.channel.send("🎲 **身分已分配！**", view=IdentityView(game))
        await asyncio.sleep(5)
        await self.start_night(ctx, game)

    async def start_night(self, ctx, game):
        game.phase = PHASE_NIGHT_1
        game.wolf_target = None
        game.wolf_votes.clear()
        game.night_actions.clear()
        game.witch_poison_target = None
        game.deaths_tonight = []
        
        await self.play_mixed_audio(ctx, "night.mp3", "voice_night_start.mp3")
        await self.mute_all(ctx, game, True)
        
        await game.channel.send("🌃 **上半夜：狼人與預言家** (請點擊行動)", view=NightViewPhase1(game, self, ctx))

    async def check_night_phase_1_end(self, ctx, game):
        # 檢查狼人與預言家是否都動了
        alive_wolves = [p for p in game.players if game.is_alive(p.id) and game.roles[p.id] == "狼人"]
        alive_seer = [p for p in game.players if game.is_alive(p.id) and game.roles[p.id] == "預言家"]
        
        wolves_done = len([v for v in game.wolf_votes.keys() if v in [w.id for w in alive_wolves]]) >= len(alive_wolves)
        seer_done = True
        if alive_seer and alive_seer[0].id not in game.night_actions: seer_done = False
        
        if wolves_done and seer_done:
            await self.start_night_phase_2(ctx, game)

    async def start_night_phase_2(self, ctx, game):
        # 女巫階段
        game.phase = PHASE_NIGHT_2
        # 清除上一階段的 action 記錄 (讓女巫可以被標記)
        # 注意：不要清掉狼人的 vote，但 night_actions 可以清給女巫用
        # 但為了簡單，我們只檢查女巫 ID 是否在 night_actions
        
        alive_witch = [p for p in game.players if game.is_alive(p.id) and game.roles[p.id] == "女巫"]
        
        if not alive_witch:
            # 女巫已死，直接天亮
            await self.start_day(ctx, game)
        else:
            # 只有女巫還活著才叫醒
            # 清除預言家的行動標記，讓 night_actions 專門追蹤女巫是否行動 (如果想嚴謹可以用不同變數)
            # 這裡我們不動 night_actions，只要檢查女巫 ID 有沒有加進去即可
            await game.channel.send("🧙‍♀️ **下半夜：女巫請睜眼**", view=NightViewPhase2(game, self, ctx))

    async def start_day(self, ctx, game):
        game.phase = PHASE_DAY
        game.votes = {}
        game.stop_votes.clear()
        
        await self.stop_bgm(ctx)
        await self.mute_all(ctx, game, False)
        
        # 結算死亡
        deaths = []
        if game.wolf_target != -1: deaths.append(game.wolf_target)
        if game.witch_poison_target: deaths.append(game.witch_poison_target)
        
        game.deaths_tonight = list(set(deaths)) # 去重
        
        msg = "🌅 **天亮了！**\n"
        if not game.deaths_tonight:
            msg += "昨晚是個平安夜，無人死亡。"
        else:
            msg += "昨晚死亡名單：\n"
            for uid in game.deaths_tonight:
                user = ctx.guild.get_member(uid)
                game.status[uid] = "dead"
                msg += f"💀 **{user.display_name if user else '未知'}**\n"
                if user: await user.edit(mute=True) # 死人靜音

        winner = self.check_winner(game)
        if winner: return await self.end_game(ctx, game, winner)
        
        await game.channel.send(msg)

        # 處理獵人開槍 (檢查死亡名單中有沒有獵人)
        # 規則：獵人被毒死不能開槍
        hunter_died = False
        for uid in game.deaths_tonight:
            if game.roles.get(uid) == "獵人":
                # 如果是被女巫毒死 (poison target)，不能開槍
                if uid == game.witch_poison_target:
                    await game.channel.send("🚫 獵人被毒殺，無法開槍！")
                else:
                    hunter_died = True
                    hunter_uid = uid
        
        if hunter_died:
            game.phase = PHASE_HUNTER
            await game.channel.send(f"🔫 **獵人發動技能！請開槍帶走一人！**", view=HunterView(game, self, ctx))
            return # 暫停進入投票，等待獵人開槍回調

        # 正常進入投票
        await game.channel.send("現在開始討論，並點擊下方按鈕投票。", view=VotingView(game, self, ctx))

    def check_winner(self, game):
        wolves = sum(1 for pid, s in game.status.items() if s=="alive" and game.roles[pid]=="狼人")
        villagers = sum(1 for pid, s in game.status.items() if s=="alive" and game.roles[pid]!="狼人") # 簡化判定：狼人殺光好人就算贏
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
            if user: await user.edit(mute=True)
            
            await game.channel.send(f"💀 **{user.display_name}** 被處決了！身分：**{role}**")
            
            winner = self.check_winner(game)
            if winner: return await self.end_game(ctx, game, winner)

            # 檢查獵人是否被票死 (被票死可以開槍)
            if role == "獵人":
                game.phase = PHASE_HUNTER
                await game.channel.send(f"🔫 **獵人發動技能！請開槍帶走一人！**", view=HunterView(game, self, ctx))
            else:
                await self.start_night(ctx, game)

async def setup(bot):
    await bot.add_cog(Werewolf(bot))