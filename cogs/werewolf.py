import discord
from discord.ext import commands
from discord.ui import Button, View
import random
import asyncio

# 定義遊戲狀態常數
PHASE_WAITING = "waiting"
PHASE_NIGHT = "night"
PHASE_DAY = "day"

class WerewolfGame:
    def __init__(self, channel):
        self.channel = channel  # 遊戲發生的頻道
        self.players = []       # 玩家列表 (Member 物件)
        self.roles = {}         # {user_id: "role_name"}
        self.status = {}        # {user_id: "alive" or "dead"}
        self.phase = PHASE_WAITING
        self.votes = {}         # {voter_id: target_id}
        self.wolf_target = None # 狼人晚上的目標
    
    def get_role(self, user_id):
        return self.roles.get(user_id, "未知")

    def is_alive(self, user_id):
        return self.status.get(user_id) == "alive"

# --- 新增：互動式大廳介面 (View) ---
class LobbyView(View):
    def __init__(self, cog, game, ctx):
        super().__init__(timeout=None) # timeout=None 表示按鈕不會自動失效 (或是設一個長時間)
        self.cog = cog
        self.game = game
        self.ctx = ctx

    def update_embed(self):
        """更新大廳的 Embed 內容"""
        player_list = "\n".join([f"- {p.display_name}" for p in self.game.players]) if self.game.players else "目前無人加入"
        embed = discord.Embed(
            title="🐺 狼人殺遊戲大廳",
            description=f"主持人: {self.ctx.author.display_name}\n\n**已加入玩家 ({len(self.game.players)}):**\n{player_list}",
            color=discord.Color.dark_red()
        )
        embed.set_footer(text="按下下方按鈕即可加入或開始遊戲")
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
        # 更新訊息 (Edit Message)
        await interaction.response.edit_message(embed=self.update_embed(), view=self)
        
        # 也可以選擇發送一條隱藏訊息確認
        # await interaction.followup.send(f"{interaction.user.display_name} 加入了遊戲！", ephemeral=True)

    @discord.ui.button(label="退出", style=discord.ButtonStyle.red, emoji="🚪")
    async def leave_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user not in self.game.players:
            await interaction.response.send_message("你不在遊戲中！", ephemeral=True)
            return
            
        self.game.players.remove(interaction.user)
        await interaction.response.edit_message(embed=self.update_embed(), view=self)

    @discord.ui.button(label="開始遊戲", style=discord.ButtonStyle.blurple, emoji="🚀")
    async def start_button(self, interaction: discord.Interaction, button: Button):
        # 只有建立者或管理員可以開始 (這裡簡單判斷：任何人都可以按，或者你可以限制 interaction.user == self.ctx.author)
        if len(self.game.players) < 3:
            await interaction.response.send_message("人數不足，至少需要 3 人才能開始！", ephemeral=True)
            return

        await interaction.response.send_message("遊戲即將開始！分配身分中...", ephemeral=False)
        
        # 停止監聽按鈕 (讓按鈕失效或移除)
        self.stop()
        # 呼叫 Cog 中的開始邏輯
        await self.cog.start_game_logic(self.ctx)


class Werewolf(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games = {} # {guild_id: WerewolfGame}

    def get_game(self, ctx):
        return self.games.get(ctx.guild.id)

    @commands.command(name='ww_create', help='[狼人殺] 建立一個新的互動式遊戲大廳')
    async def create_game(self, ctx):
        if ctx.guild.id in self.games:
            await ctx.send("這裡已經有一場遊戲正在準備或進行中了！")
            return
        
        game = WerewolfGame(ctx.channel)
        # 預設把發起人加入
        # game.players.append(ctx.author) 
        
        self.games[ctx.guild.id] = game
        
        # 建立互動式 View
        view = LobbyView(self, game, ctx)
        embed = view.update_embed()
        
        await ctx.send(embed=embed, view=view)

    # 保留舊指令作為備用，但主要鼓勵使用按鈕
    @commands.command(name='ww_join', help='[狼人殺] 加入遊戲 (建議使用按鈕)')
    async def join_game(self, ctx):
        game = self.get_game(ctx)
        if not game or game.phase != PHASE_WAITING:
            return
        if ctx.author not in game.players:
            game.players.append(ctx.author)
            await ctx.send(f"✅ **{ctx.author.display_name}** 加入了遊戲！")

    # 將原本的 start_game 拆分成邏輯函式，方便按鈕呼叫
    async def start_game_logic(self, ctx):
        game = self.get_game(ctx)
        if not game: return

        # --- 分配身分 ---
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
        
        await game.channel.send("🎲 **身分分配中，請查看您的私訊 (DM)...**")
        
        for i, player in enumerate(game.players):
            role = roles_list[i]
            game.roles[player.id] = role
            game.status[player.id] = "alive"
            
            try:
                if role == "狼人":
                    await player.send(f"🐺 你的身分是 **狼人**！\n晚上請使用 `!kill <ID>` 指令告訴我你要殺誰。")
                elif role == "預言家":
                    await player.send(f"🔮 你的身分是 **預言家**！\n晚上請使用 `!check <ID>` 查驗別人的身分。")
                else:
                    await player.send(f"xxxx 你的身分是 **村民**。\n請在白天找出狼人並投票處決他。")
            except discord.Forbidden:
                await game.channel.send(f"❌ 無法傳送私訊給 {player.mention}，請開啟私訊功能後重新開始。")
                del self.games[ctx.guild.id]
                return

        await self.start_night(ctx, game)

    # 這是原本的指令入口
    @commands.command(name='ww_start', help='[狼人殺] 開始遊戲')
    async def start_game(self, ctx):
        game = self.get_game(ctx)
        if not game or game.phase != PHASE_WAITING:
            await ctx.send("無法開始遊戲。")
            return
        if len(game.players) < 3:
            await ctx.send("人數不足，至少需要 3 人。")
            return
        await self.start_game_logic(ctx)

    async def start_night(self, ctx, game):
        game.phase = PHASE_NIGHT
        game.wolf_target = None
        await game.channel.send("🌃 **天黑請閉眼...** (進入夜晚階段)\n狼人請私訊我殺人類，預言家請私訊我查驗。")

    async def start_day(self, ctx, game, dead_player_id=None):
        game.phase = PHASE_DAY
        game.votes = {} 
        
        msg = "🌅 **天亮了！**\n"
        if dead_player_id:
            dead_user = ctx.guild.get_member(dead_player_id)
            game.status[dead_player_id] = "dead"
            msg += f"昨晚 **{dead_user.display_name if dead_user else '有人'}** 慘遭殺害...\n"
        else:
            msg += "昨晚是個平安夜，沒有人死亡。\n"
            
        winner = self.check_winner(game)
        if winner:
            msg += f"\n🏆 **遊戲結束！獲勝者: {winner}**"
            await game.channel.send(msg)
            role_reveal = "\n".join([f"{p.display_name}: {game.roles[p.id]}" for p in game.players])
            await game.channel.send(f"**身分揭曉：**\n{role_reveal}")
            del self.games[ctx.guild.id]
            return

        msg += "現在開始討論，並使用 `!vote @玩家` 進行投票處決。"
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
        
        if alive_wolves == 0:
            return "好人陣營 (村民/預言家)"
        if alive_wolves >= alive_villagers:
            return "狼人陣營"
        return None

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.guild is not None:
            return

        content = message.content.strip().split()
        if not content: return
        cmd = content[0].lower()
        
        target_game = None
        target_guild_id = None
        
        for gid, g in self.games.items():
            if message.author in g.players and g.phase == PHASE_NIGHT:
                target_game = g
                target_guild_id = gid
                break
        
        if not target_game: return

        if cmd == "!kill":
            if target_game.roles[message.author.id] != "狼人":
                await message.channel.send("你不是狼人。")
                return
            
            if len(content) < 2:
                alive_list = "\n".join([f"{p.display_name} (ID: {p.id})" for p in target_game.players if target_game.status[p.id] == "alive"])
                await message.channel.send(f"請輸入 `!kill <玩家ID>`。\n存活玩家:\n{alive_list}")
                return
            
            try:
                target_id = int(content[1])
                if target_game.status.get(target_id) != "alive":
                    await message.channel.send("無效的目標。")
                    return
                
                target_game.wolf_target = target_id
                await message.channel.send(f"🔪 已鎖定目標 ID: {target_id}")
                
                await asyncio.sleep(2) 
                guild = self.bot.get_guild(target_guild_id)
                if guild:
                    # 使用 channel 物件發送，避免依賴 ctx
                    ctx_mock = type('obj', (object,), {'guild': guild, 'send': target_game.channel.send})
                    await self.start_day(ctx_mock, target_game, target_game.wolf_target)

            except ValueError:
                await message.channel.send("ID 格式錯誤。")

        elif cmd == "!check":
            if target_game.roles[message.author.id] != "預言家":
                await message.channel.send("你不是預言家。")
                return
            
            if len(content) < 2:
                alive_list = "\n".join([f"{p.display_name} (ID: {p.id})" for p in target_game.players if target_game.status[p.id] == "alive" and p.id != message.author.id])
                await message.channel.send(f"請輸入 `!check <玩家ID>`。\n可查驗對象:\n{alive_list}")
                return

            try:
                target_id = int(content[1])
                role = target_game.roles.get(target_id)
                if not role:
                    await message.channel.send("無效的目標。")
                else:
                    is_good = "好人" if role != "狼人" else "狼人"
                    await message.channel.send(f"🔮 查驗結果：ID {target_id} 是 **{is_good}**")
            except ValueError:
                await message.channel.send("ID 格式錯誤。")

    @commands.command(name='vote', help='[狼人殺] 投票處決 (僅限白天)')
    async def vote(self, ctx, target: discord.Member):
        game = self.get_game(ctx)
        if not game or game.phase != PHASE_DAY:
            await ctx.send("現在不是投票時間。")
            return
        
        if not game.is_alive(ctx.author.id):
            await ctx.send("死人不能投票。")
            return
            
        if not game.is_alive(target.id):
            await ctx.send("你不能投給死人。")
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
        
        if not vote_counts:
            await game.channel.send("沒有人投票，直接進入夜晚。")
            await self.start_night(ctx, game)
            return

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
            await game.channel.send(f"💀 **{eliminated_user.display_name}** 被處決了！\n他的身分是：**{role}**")
            
            winner = self.check_winner(game)
            if winner:
                await game.channel.send(f"\n🏆 **遊戲結束！獲勝者: {winner}**")
                role_reveal = "\n".join([f"{p.display_name}: {game.roles[p.id]}" for p in game.players])
                await game.channel.send(f"**身分揭曉：**\n{role_reveal}")
                del self.games[ctx.guild.id]
            else:
                await self.start_night(ctx, game)

async def setup(bot):
    await bot.add_cog(Werewolf(bot))