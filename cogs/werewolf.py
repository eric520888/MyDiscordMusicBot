import discord
from discord.ext import commands
from discord.ui import Button, View, Select
import random
import asyncio
import os

# --- 設定 ---
SOUND_FOLDER = "./sounds"  # 音效檔案資料夾

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
    
    def get_role(self, user_id):
        return self.roles.get(user_id, "未知")

    def is_alive(self, user_id):
        return self.status.get(user_id) == "alive"

# --- [大廳介面] ---
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
        
        # 嘗試加入語音頻道
        if interaction.user.voice:
            voice_channel = interaction.user.voice.channel
            if not self.ctx.guild.voice_client:
                await voice_channel.connect()
            elif self.ctx.guild.voice_client.channel != voice_channel:
                await self.ctx.guild.voice_client.move_to(voice_channel)
        else:
             await interaction.response.send_message("⚠️ 請先加入語音頻道，這樣才有背景音樂喔！(但遊戲仍會繼續)", ephemeral=True)

        self.stop()
        await interaction.response.send_message("遊戲開始！正在分配身分...", ephemeral=False)
        await self.cog.start_game_logic(self.ctx)

# --- [夜晚互動] 選單 ---
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
        target_id = int(self.values[0])
        role = self.game.roles.get(target_id)
        is_good = "好人" if role != "狼人" else "狼人"
        await interaction.response.send_message(f"🔮 查驗結果：此人是 **{is_good}**", ephemeral=True)

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
            view = View()
            view.add_item(SeerSelect(self.game))
            await interaction.response.send_message("🔮 **預言家請睜眼**，請選擇查驗對象：", view=view, ephemeral=True)
        else:
            await interaction.response.send_message("💤 你是村民，今晚無事發生，請繼續睡覺。", ephemeral=True)

class Werewolf(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games = {}

    def get_game(self, ctx):
        return self.games.get(ctx.guild.id)

    # --- BGM 控制功能 ---
    async def play_bgm(self, ctx, filename):
        """播放背景音樂 (會無限循環)"""
        voice_client = ctx.guild.voice_client
        if not voice_client: return # 沒連語音就不播

        # 檢查檔案是否存在
        file_path = os.path.join(SOUND_FOLDER, filename)
        if not os.path.exists(file_path):
            print(f"找不到音效檔: {file_path}")
            return

        # 如果正在播放音樂，先停止 (會切斷原本的 YouTube 音樂)
        if voice_client.is_playing():
            voice_client.stop()

        try:
            # -stream_loop -1 代表無限循環播放
            # options="-vn" 代表只處裡音訊
            source = discord.FFmpegPCMAudio(file_path, before_options="-stream_loop -1", options="-vn")
            voice_client.play(source)
        except Exception as e:
            print(f"BGM 播放失敗: {e}")

    async def stop_bgm(self, ctx):
        """停止播放音樂"""
        voice_client = ctx.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.stop()

    # ------------------

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

        # 為了避免跟 Music Cog 的佇列系統衝突，這裡可以選擇性地清空 Music 的佇列
        # music_cog = self.bot.get_cog("Music")
        # if music_cog:
        #     music_cog.song_queue[ctx.guild.id] = []

        # 身分分配
        random.shuffle(game.players)
        num_players = len(game.players)
        num_wolves = max(1, num_players // 3)
        num_seers = 1
        roles_list = ["狼人"] * num_wolves + ["預言家"] * num_seers
        while len(roles_list) < num_players:
            roles_list.append("村民")
        random.shuffle(roles_list)

        game.roles = {}
        game.status = {}
        
        await game.channel.send("🎲 **正在發牌...請檢查私訊確認身分！**")
        
        for i, player in enumerate(game.players):
            role = roles_list[i]
            game.roles[player.id] = role
            game.status[player.id] = "alive"
            try:
                await player.send(f"你的身分是：**{role}**")
            except:
                pass 

        await self.start_night(ctx, game)

    async def start_night(self, ctx, game):
        game.phase = PHASE_NIGHT
        game.wolf_target = None
        
        # --- 播放夜晚音樂 ---
        await self.play_bgm(ctx, "night.mp3")
        # ------------------

        view = NightActionView(game, self, ctx)
        await game.channel.send("🌃 **天黑請閉眼...**\n(背景音樂已播放)\n請點擊下方按鈕進行行動。", view=view)

    async def start_day(self, ctx, game, dead_player_id=None):
        game.phase = PHASE_DAY
        game.votes = {} 
        
        # --- 停止夜晚音樂 (或播放白天音樂) ---
        await self.stop_bgm(ctx)
        # 如果你有 day.mp3，可以改用: await self.play_bgm(ctx, "day.mp3")
        # --------------------------------

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
            
            # (選用) 播放勝利音樂
            # await self.play_bgm(ctx, "win.mp3")

            role_reveal = "\n".join([f"{p.display_name}: {game.roles[p.id]}" for p in game.players])
            await game.channel.send(f"**身分揭曉：**\n{role_reveal}")
            del self.games[ctx.guild.id]
            return

        msg += "現在開始討論，並使用 `/vote` 進行投票處決。"
        await game.channel.send(msg)

    def check_winner(self, game):
        alive_wolves = 0
        alive_villagers = 0
        for pid, status in game.status.items():
            if status == "alive":
                if game.roles[pid] == "狼人":
                    alive_wolves += 1
                else:
                    alive_villagers += 1
        
        if alive_wolves == 0: return "好人陣營"
        if alive_wolves >= alive_villagers: return "狼人陣營"
        return None

    @commands.hybrid_command(name='vote', description='[狼人殺] 投票處決')
    async def vote(self, ctx, target: discord.Member):
        game = self.get_game(ctx)
        if not game or game.phase != PHASE_DAY:
            await ctx.send("現在不是投票時間。", ephemeral=True)
            return
        if not game.is_alive(ctx.author.id):
            await ctx.send("死人不能投票。", ephemeral=True)
            return
        
        game.votes[ctx.author.id] = target.id
        await ctx.send(f"🗳️ **{ctx.author.display_name}** 投票給了 **{target.display_name}**")

        alive_count = sum(1 for status in game.status.values() if status == "alive")
        if len(game.votes) >= alive_count:
            await self.tally_votes(ctx, game)

    async def tally_votes(self, ctx, game):
        vote_counts = {}
        for target_id in game.votes.values():
            vote_counts[target_id] = vote_counts.get(target_id, 0) + 1
        
        sorted_votes = sorted(vote_counts.items(), key=lambda x: x[1], reverse=True)
        max_votes = sorted_votes[0][1]
        candidates = [vid for vid, count in sorted_votes if count == max_votes]

        if len(candidates) > 1:
            await game.channel.send(f"平票 (各 {max_votes} 票)，無人被處決。")
            await self.start_night(ctx, game)
        else:
            eliminated_id = candidates[0]
            eliminated_user = ctx.guild.get_member(eliminated_id)
            game.status[eliminated_id] = "dead"
            role = game.roles[eliminated_id]
            await game.channel.send(f"💀 **{eliminated_user.display_name}** 被處決了！身分是：**{role}**")
            
            winner = self.check_winner(game)
            if winner:
                await game.channel.send(f"🏆 **遊戲結束！獲勝者: {winner}**")
                del self.games[ctx.guild.id]
            else:
                await self.start_night(ctx, game)

async def setup(bot):
    await bot.add_cog(Werewolf(bot))