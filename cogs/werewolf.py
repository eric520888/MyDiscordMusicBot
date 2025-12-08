import discord
from discord.ext import commands
from discord.ui import Button, View, Select
import random
import asyncio
import os

# --- 設定 ---
# 請確保專案根目錄下有 'sounds' 資料夾
# 並且放入 'night.mp3' (背景音樂) 和 'voice_night_start.mp3' (語音)
SOUND_FOLDER = "./sounds"

# 定義遊戲狀態
PHASE_WAITING = "waiting"
PHASE_NIGHT = "night"
PHASE_DAY = "day"

class WerewolfGame:
    def __init__(self, channel):
        self.channel = channel
        self.players = []       
        self.roles = {}         
        self.status = {}        
        self.phase = PHASE_WAITING
        self.votes = {}         
        self.wolf_target = None 
        self.night_actions = set() # 記錄今晚已經行動過的玩家 ID
    
    def get_role(self, user_id):
        return self.roles.get(user_id, "未知")

    def is_alive(self, user_id):
        return self.status.get(user_id) == "alive"

# --- 1. 大廳介面 (Lobby) ---
class LobbyView(View):
    def __init__(self, cog, game, ctx):
        super().__init__(timeout=None)
        self.cog = cog
        self.game = game
        self.ctx = ctx

    def update_embed(self):
        player_list = "\n".join([f"- {p.display_name}" for p in self.game.players]) if self.game.players else "目前無人加入"
        embed = discord.Embed(
            title="🐺 狼人殺遊戲大廳",
            description=f"主持人: {self.ctx.author.display_name}\n\n**已加入玩家 ({len(self.game.players)}):**\n{player_list}",
            color=discord.Color.dark_red()
        )
        embed.set_footer(text="湊齊 3 人以上即可開始")
        return embed

    @discord.ui.button(label="加入遊戲", style=discord.ButtonStyle.green, emoji="✋")
    async def join_button(self, interaction: discord.Interaction, button: Button):
        if self.game.phase != PHASE_WAITING:
            await interaction.response.send_message("遊戲已經開始了！", ephemeral=True)
            return
        if interaction.user in self.game.players:
            await interaction.response.send_message("你已經在列表內了！", ephemeral=True)
            return
        self.game.players.append(interaction.user)
        await interaction.response.edit_message(embed=self.update_embed(), view=self)

    @discord.ui.button(label="退出", style=discord.ButtonStyle.red, emoji="🚪")
    async def leave_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user not in self.game.players:
            await interaction.response.send_message("你不在遊戲中！", ephemeral=True)
            return
        self.game.players.remove(interaction.user)
        await interaction.response.edit_message(embed=self.update_embed(), view=self)

    @discord.ui.button(label="開始遊戲", style=discord.ButtonStyle.blurple, emoji="🚀")
    async def start_button(self, interaction: discord.Interaction, button: Button):
        if len(self.game.players) < 3:
            await interaction.response.send_message("人數不足，至少需要 3 人才能開始！", ephemeral=True)
            return
        
        # 嘗試幫主持人連語音，確保能播音樂
        if interaction.user.voice:
            voice_channel = interaction.user.voice.channel
            if not self.ctx.guild.voice_client:
                await voice_channel.connect()
            elif self.ctx.guild.voice_client.channel != voice_channel:
                await self.ctx.guild.voice_client.move_to(voice_channel)
        
        self.stop()
        await interaction.response.send_message("遊戲開始！正在分配身分...", ephemeral=False)
        await self.cog.start_game_logic(self.ctx)

# --- 2. 身分查看介面 ---
class IdentityView(View):
    def __init__(self, game):
        super().__init__(timeout=None)
        self.game = game

    @discord.ui.button(label="🕵️ 點擊查看我的身分", style=discord.ButtonStyle.secondary)
    async def check_identity(self, interaction: discord.Interaction, button: Button):
        if interaction.user not in self.game.players:
            await interaction.response.send_message("你沒有參與這場遊戲喔！", ephemeral=True)
            return
        
        role = self.game.roles.get(interaction.user.id)
        msg = f"你的身分是：**{role}**"
        
        if role == "狼人":
            msg += "\n🔪 你的目標是在晚上殺死所有村民。"
        elif role == "預言家":
            msg += "\n🔮 你每晚可以查驗一名玩家的身分。"
        else:
            msg += "\n🏡 努力活下去，並在白天找出狼人投票處決。"

        await interaction.response.send_message(msg, ephemeral=True)

# --- 3. 夜晚選單 (狼人/預言家) ---
class WolfSelect(Select):
    def __init__(self, game, cog, ctx):
        self.game = game
        self.cog = cog
        self.ctx = ctx
        options = []
        for p in game.players:
            if game.is_alive(p.id):
                options.append(discord.SelectOption(label=p.display_name, value=str(p.id), emoji="👤"))
        super().__init__(placeholder="🔪 請選擇今晚的目標...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        target_id = int(self.values[0])
        target_user = interaction.guild.get_member(target_id)
        self.game.wolf_target = target_id
        await interaction.response.send_message(f"🩸 你已選擇殺害 **{target_user.display_name}**。", ephemeral=True)
        # 狼人殺完人後，延遲 2 秒直接天亮
        await asyncio.sleep(2)
        await self.cog.start_day(self.ctx, self.game, self.game.wolf_target)

class SeerSelect(Select):
    def __init__(self, game):
        self.game = game
        options = []
        for p in game.players:
            if game.is_alive(p.id):
                options.append(discord.SelectOption(label=p.display_name, value=str(p.id), emoji="🔍"))
        super().__init__(placeholder="🔮 請選擇要查驗的對象...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id in self.game.night_actions:
            await interaction.response.send_message("❌ 你今晚已經查驗過了！", ephemeral=True)
            return

        target_id = int(self.values[0])
        role = self.game.roles.get(target_id)
        
        # --- [關鍵修復] 預言家查驗邏輯 ---
        # 明確判斷：如果是狼人，就是「壞人/狼人」；否則都是「好人」
        if role == "狼人":
            result_msg = "這人是 **🐺 狼人 (壞人)**！"
        else:
            result_msg = "這人是 **好人** (村民或神職)。"
        # -------------------------------
        
        self.game.night_actions.add(interaction.user.id)
        await interaction.response.send_message(f"🔮 查驗結果：{result_msg}", ephemeral=True)

class NightActionView(View):
    def __init__(self, game, cog, ctx):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog
        self.ctx = ctx

    @discord.ui.button(label="進行夜晚行動", style=discord.ButtonStyle.primary, emoji="🌙")
    async def action_button(self, interaction: discord.Interaction, button: Button):
        user_id = interaction.user.id
        if not self.game.is_alive(user_id):
            await interaction.response.send_message("💀 你已經死了，請安息。", ephemeral=True)
            return

        role = self.game.roles.get(user_id)
        
        if role == "狼人":
            view = View()
            view.add_item(WolfSelect(self.game, self.cog, self.ctx))
            await interaction.response.send_message("🐺 **狼人請現身**，請選擇目標：", view=view, ephemeral=True)
        elif role == "預言家":
            if user_id in self.game.night_actions:
                await interaction.response.send_message("❌ 你今晚已經查驗過了，請等待天亮。", ephemeral=True)
                return
            view = View()
            view.add_item(SeerSelect(self.game))
            await interaction.response.send_message("🔮 **預言家請睜眼**，請選擇查驗對象：", view=view, ephemeral=True)
        else:
            await interaction.response.send_message("💤 你是村民，今晚無事發生，請繼續睡覺。", ephemeral=True)

# --- 4. 白天投票介面 ---
class CandidateButton(Button):
    def __init__(self, player, game, cog, ctx, view):
        super().__init__(label=player.display_name, style=discord.ButtonStyle.secondary)
        self.target_id = player.id
        self.game = game
        self.cog = cog
        self.ctx = ctx
        self.parent_view = view

    async def callback(self, interaction: discord.Interaction):
        if not self.game.is_alive(interaction.user.id):
            await interaction.response.send_message("💀 死人無法投票。", ephemeral=True)
            return

        self.game.votes[interaction.user.id] = self.target_id
        await interaction.response.send_message(f"🗳️ **{interaction.user.display_name}** 投票給了 **{self.label}**")
        
        alive_count = sum(1 for s in self.game.status.values() if s == "alive")
        if len(self.game.votes) >= alive_count:
            self.parent_view.stop()
            await self.cog.tally_votes(self.ctx, self.game)

class VotingView(View):
    def __init__(self, game, cog, ctx):
        super().__init__(timeout=None)
        for player in game.players:
            if game.is_alive(player.id):
                self.add_item(CandidateButton(player, game, cog, ctx, self))

# --- 5. 主程式 ---
class Werewolf(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games = {}

    def get_game(self, ctx):
        return self.games.get(ctx.guild.id)

    # --- [核心功能] 混音播放 ---
    async def play_mixed_audio(self, ctx, bgm_file, voice_file=None):
        """
        利用 FFmpeg 同時播放背景音樂(循環)與人聲(單次)。
        """
        voice_client = ctx.guild.voice_client
        if not voice_client: return

        bgm_path = os.path.join(SOUND_FOLDER, bgm_file)
        if not os.path.exists(bgm_path):
            print(f"❌ 找不到 BGM: {bgm_path}")
            return

        if voice_client.is_playing():
            voice_client.stop()

        # 如果沒有語音檔，就退化成只播 BGM
        if not voice_file:
            source = discord.FFmpegPCMAudio(bgm_path, before_options="-stream_loop -1", options="-vn")
            voice_client.play(source)
            return

        voice_path = os.path.join(SOUND_FOLDER, voice_file)
        if not os.path.exists(voice_path):
            print(f"❌ 找不到語音: {voice_path}")
            source = discord.FFmpegPCMAudio(bgm_path, before_options="-stream_loop -1", options="-vn")
            voice_client.play(source)
            return

        # 混音指令：
        # Input 0: BGM (音量 0.4, 循環)
        # Input 1: Voice (音量 1.5)
        # amix: 混合兩個軌道, duration=first (以 BGM 長度為主/無限)
        ffmpeg_opts = '-vn'
        complex_filter = f'[0:a]volume=0.4[bg];[1:a]volume=1.5[vc];[bg][vc]amix=inputs=2:duration=first:dropout_transition=2'
        before_opts = f'-stream_loop -1 -i "{bgm_path}" -filter_complex "{complex_filter}"'
        
        try:
            # 這裡我們傳入 voice_path 作為主要 source，它會變成 Input 1
            # Input 0 (BGM) 則是在 before_opts 裡引入的
            source = discord.FFmpegPCMAudio(voice_path, before_options=before_opts, options=ffmpeg_opts)
            voice_client.play(source)
        except Exception as e:
            print(f"混音播放失敗: {e}")

    async def stop_bgm(self, ctx):
        voice_client = ctx.guild.voice_client
        if voice_client and voice_client.is_playing(): 
            voice_client.stop()

    # --- 流程控制 ---
    
    @commands.hybrid_command(name='ww_create', description='[狼人殺] 建立遊戲大廳')
    async def create_game(self, ctx):
        if ctx.guild.id in self.games:
            await ctx.send("這裡已經有一場遊戲了！", ephemeral=True)
            return
        game = WerewolfGame(ctx.channel)
        self.games[ctx.guild.id] = game
        view = LobbyView(self, game, ctx)
        await ctx.send(embed=view.update_embed(), view=view)

    async def start_game_logic(self, ctx):
        game = self.get_game(ctx)
        if not game: return
        
        random.shuffle(game.players)
        num_players = len(game.players)
        num_wolves = max(1, num_players // 3)
        roles_list = ["狼人"] * num_wolves + ["預言家"] + ["村民"] * (num_players - num_wolves - 1)
        roles_list = roles_list[:num_players]
        random.shuffle(roles_list)

        game.roles = {}
        game.status = {}
        
        for i, player in enumerate(game.players):
            role = roles_list[i]
            game.roles[player.id] = role
            game.status[player.id] = "alive"

        # 發送查看身分按鈕
        identity_view = IdentityView(game)
        await game.channel.send("🎲 **身分已分配！請點擊下方按鈕查看你的身分** (只有你自己看得到)", view=identity_view)

        await asyncio.sleep(5) 
        await self.start_night(ctx, game)

    async def start_night(self, ctx, game):
        game.phase = PHASE_NIGHT
        game.wolf_target = None
        game.night_actions.clear()
        
        # --- 播放 BGM + 語音 ---
        # 請確保 sounds 資料夾有這些檔案
        await self.play_mixed_audio(ctx, "night.mp3", "voice_night_start.mp3")
        
        view = NightActionView(game, self, ctx)
        await game.channel.send("🌃 **天黑請閉眼...** (背景音樂播放中)\n請點擊下方按鈕進行行動。", view=view)

    async def start_day(self, ctx, game, dead_player_id=None):
        game.phase = PHASE_DAY
        game.votes = {} 
        
        await self.stop_bgm(ctx)
        # 如果有白天音樂，可以用 await self.play_mixed_audio(ctx, "day.mp3", "voice_day_start.mp3")
        
        msg = "🌅 **天亮了！**\n"
        if dead_player_id:
            dead_user = ctx.guild.get_member(dead_player_id)
            game.status[dead_player_id] = "dead"
            msg += f"昨晚 **{dead_user.display_name if dead_user else '有人'}** 慘遭殺害...\n"
        else:
            msg += "昨晚是個平安夜，沒有人死亡。\n"
            
        winner = self.check_winner(game)
        if winner:
            await game.channel.send(f"{msg}\n🏆 **遊戲結束！獲勝者: {winner}**")
            role_reveal = "\n".join([f"{p.display_name}: {game.roles[p.id]}" for p in game.players])
            await game.channel.send(f"**身分揭曉：**\n{role_reveal}")
            del self.games[ctx.guild.id]
            return

        msg += "現在開始討論，並點擊下方按鈕進行投票處決。"
        vote_view = VotingView(game, self, ctx)
        await game.channel.send(msg, view=vote_view)

    def check_winner(self, game):
        wolves = sum(1 for pid, s in game.status.items() if s=="alive" and game.roles[pid]=="狼人")
        villagers = sum(1 for pid, s in game.status.items() if s=="alive" and game.roles[pid]!="狼人")
        
        if wolves == 0: return "好人陣營"
        if wolves >= villagers: return "狼人陣營"
        return None

    async def tally_votes(self, ctx, game):
        vote_counts = {}
        for target_id in game.votes.values():
            vote_counts[target_id] = vote_counts.get(target_id, 0) + 1
        
        if not vote_counts:
            await game.channel.send("沒有人投票，直接進入夜晚。")
            await self.start_night(ctx, game)
            return

        sorted_votes = sorted(vote_counts.items(), key=lambda x: x[1], reverse=True)
        max_votes = sorted_votes[0][1]
        
        candidates = [vid for vid, count in sorted_votes if count == max_votes]

        if len(candidates) > 1:
            await game.channel.send(f"⚖️ 平票 (各 {max_votes} 票)，無人被處決。")
            await self.start_night(ctx, game)
        else:
            eliminated_id = candidates[0]
            eliminated_user = ctx.guild.get_member(eliminated_id)
            game.status[eliminated_id] = "dead"
            
            role = game.roles[eliminated_id]
            await game.channel.send(f"💀 **{eliminated_user.display_name}** 被處決了！\n他的身分是：**{role}**")
            
            winner = self.check_winner(game)
            if winner:
                await game.channel.send(f"🏆 **遊戲結束！獲勝者: {winner}**")
                role_reveal = "\n".join([f"{p.display_name}: {game.roles[p.id]}" for p in game.players])
                await game.channel.send(f"**身分揭曉：**\n{role_reveal}")
                del self.games[ctx.guild.id]
            else:
                await self.start_night(ctx, game)

async def setup(bot):
    await bot.add_cog(Werewolf(bot))