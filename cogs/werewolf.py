import discord
from discord.ext import commands
from discord.ui import Button, View, Select
import random
import asyncio
import os

# --- 設定 ---
SOUND_FOLDER = "./sounds"

# 定義遊戲狀態
PHASE_WAITING = "waiting"
PHASE_NIGHT = "night"
PHASE_DAY = "day"

class WerewolfGame:
    def __init__(self, channel, host):
        self.channel = channel
        self.host = host        # 遊戲主持人
        self.players = []       
        self.roles = {}         
        self.status = {}        
        self.phase = PHASE_WAITING
        self.votes = {}         # 白天投票
        self.wolf_votes = {}    # 狼人殺投票 {wolf_id: target_id}
        self.wolf_target = None # 最終狼人殺目標
        self.night_actions = set() # 記錄今晚已經行動過的玩家 ID (狼人/預言家)
        self.stop_votes = set() # 記錄投票結束遊戲的玩家 ID
    
    def get_role(self, user_id):
        return self.roles.get(user_id, "未知")

    def is_alive(self, user_id):
        return self.status.get(user_id) == "alive"

    def get_alive_players(self):
        return [p for p in self.players if self.is_alive(p.id)]

# --- 1. 大廳介面 (Lobby) ---
class LobbyView(View):
    def __init__(self, cog, game, ctx):
        super().__init__(timeout=120) # 120秒後自動超時
        self.cog = cog
        self.game = game
        self.ctx = ctx
        self.message = None

    async def on_timeout(self):
        # 超時自動關閉
        if self.game.phase == PHASE_WAITING:
            if self.ctx.guild.id in self.cog.games:
                del self.cog.games[self.ctx.guild.id]
            if self.message:
                try:
                    timeout_embed = discord.Embed(
                        title="⏳ 大廳已關閉", 
                        description="因閒置過久 (120秒)，遊戲大廳已自動解散。", 
                        color=discord.Color.greyple()
                    )
                    await self.message.edit(embed=timeout_embed, view=None)
                except:
                    pass

    def update_embed(self):
        player_list = "\n".join([f"- {p.display_name}" for p in self.game.players]) if self.game.players else "目前無人加入"
        embed = discord.Embed(
            title="🐺 狼人殺遊戲大廳",
            description=f"主持人: {self.game.host.display_name}\n\n**已加入玩家 ({len(self.game.players)}):**\n{player_list}",
            color=discord.Color.dark_red()
        )
        embed.set_footer(text="主持人可開始遊戲，120秒閒置將自動關閉")
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
        # 限制只有主持人可以開始
        if interaction.user.id != self.game.host.id:
            await interaction.response.send_message(f"❌ 只有主持人 **{self.game.host.display_name}** 可以開始遊戲！", ephemeral=True)
            return

        if len(self.game.players) < 3:
            await interaction.response.send_message("人數不足，至少需要 3 人才能開始！", ephemeral=True)
            return
        
        # 嘗試連語音
        if interaction.user.voice:
            voice_channel = interaction.user.voice.channel
            if not self.ctx.guild.voice_client:
                await voice_channel.connect()
            elif self.ctx.guild.voice_client.channel != voice_channel:
                await self.ctx.guild.voice_client.move_to(voice_channel)
        
        self.stop() # 停止監聽 (不會觸發 on_timeout)
        await interaction.response.send_message("遊戲開始！正在分配身分...", ephemeral=False)
        await self.cog.start_game_logic(self.ctx)

    @discord.ui.button(label="關閉大廳", style=discord.ButtonStyle.grey, emoji="✖️")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.game.host.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有主持人或管理員可以關閉大廳。", ephemeral=True)
            return
        
        if self.ctx.guild.id in self.cog.games:
            del self.cog.games[self.ctx.guild.id]
        
        self.stop()
        embed = discord.Embed(title="🛑 遊戲大廳已關閉", description="主持人取消了遊戲。", color=discord.Color.light_grey())
        await interaction.response.edit_message(embed=embed, view=None)

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
            msg += "\n🔪 你的目標是在晚上與隊友殺死所有村民。"
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
        # 新增空刀選項
        options.append(discord.SelectOption(label="不殺 (空刀)", value="-1", emoji="☮️", description="今晚不殺任何人"))
        
        for p in game.players:
            if game.is_alive(p.id):
                options.append(discord.SelectOption(label=p.display_name, value=str(p.id), emoji="👤"))
        
        super().__init__(placeholder="🔪 狼人請投票選擇目標...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        # 狼人投票邏輯
        target_id = int(self.values[0])
        self.game.wolf_votes[interaction.user.id] = target_id
        self.game.night_actions.add(interaction.user.id) # 標記此狼人已行動
        
        target_name = "不殺 (空刀)"
        if target_id != -1:
            target_user = interaction.guild.get_member(target_id)
            target_name = target_user.display_name if target_user else "未知"

        await interaction.response.send_message(f"🩸 你投給了：**{target_name}**", ephemeral=True)
        
        # 檢查是否所有活著的狼人都投完票了
        alive_wolves = [pid for pid in self.game.players if self.game.is_alive(pid) and self.game.roles[pid] == "狼人"]
        
        if len([v for v in self.game.wolf_votes.keys() if v in alive_wolves]) >= len(alive_wolves):
            # 結算狼人目標 (多數決)
            from collections import Counter
            valid_votes = [target for uid, target in self.game.wolf_votes.items() if uid in alive_wolves]
            
            if valid_votes:
                vote_counts = Counter(valid_votes)
                # 取票數最高的，如果平票取第一個 (或隨機)
                most_common = vote_counts.most_common()
                max_votes = most_common[0][1]
                candidates = [tid for tid, count in most_common if count == max_votes]
                final_target = random.choice(candidates) # 平票隨機
                
                self.game.wolf_target = final_target
            else:
                self.game.wolf_target = -1

            # 嘗試觸發天亮判定
            await self.cog.check_night_end(self.ctx, self.game)

class SeerSelect(Select):
    def __init__(self, game, cog, ctx):
        self.game = game
        self.cog = cog
        self.ctx = ctx
        options = []
        # 新增空驗選項
        options.append(discord.SelectOption(label="不驗 (空驗)", value="-1", emoji="☮️", description="今晚不查驗任何人"))

        for p in game.players:
            if game.is_alive(p.id):
                options.append(discord.SelectOption(label=p.display_name, value=str(p.id), emoji="👤"))
        super().__init__(placeholder="🔮 請選擇要查驗的對象...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id in self.game.night_actions:
            await interaction.response.send_message("❌ 你今晚已經查驗過了！", ephemeral=True)
            return

        target_id = int(self.values[0])
        self.game.night_actions.add(interaction.user.id) # 標記預言家已行動

        if target_id == -1:
            await interaction.response.send_message("🔮 你選擇了 **不查驗**。", ephemeral=True)
        else:
            role = self.game.roles.get(target_id)
            if role == "狼人":
                result_msg = "這人是 **🐺 狼人 (壞人)**！"
            else:
                result_msg = "這人是 **好人** (村民或神職)。"
            await interaction.response.send_message(f"🔮 查驗結果：{result_msg}", ephemeral=True)
        
        # 嘗試觸發天亮判定
        await self.cog.check_night_end(self.ctx, self.game)

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
            await interaction.response.send_message("🐺 **狼人請現身**，請與隊友投票選擇目標：", view=view, ephemeral=True)
        elif role == "預言家":
            if user_id in self.game.night_actions:
                await interaction.response.send_message("❌ 你今晚已經查驗過了，請等待天亮。", ephemeral=True)
                return
            view = View()
            view.add_item(SeerSelect(self.game, self.cog, self.ctx))
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
        
        alive_count = len(self.game.get_alive_players())
        if len(self.game.votes) >= alive_count:
            self.parent_view.stop()
            await self.cog.tally_votes(self.ctx, self.game)

class VotingView(View):
    def __init__(self, game, cog, ctx):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog
        self.ctx = ctx
        
        # 活人投票按鈕
        for player in game.players:
            if game.is_alive(player.id):
                self.add_item(CandidateButton(player, game, cog, ctx, self))

    # 新增：投票強制結束遊戲按鈕
    @discord.ui.button(label="🏳️ 投票結束遊戲", style=discord.ButtonStyle.danger, row=4)
    async def stop_vote_button(self, interaction: discord.Interaction, button: Button):
        if not self.game.is_alive(interaction.user.id):
            await interaction.response.send_message("💀 死人無法發起結束投票。", ephemeral=True)
            return
            
        if interaction.user.id in self.game.stop_votes:
            await interaction.response.send_message("你已經投過結束票了。", ephemeral=True)
            return
            
        self.game.stop_votes.add(interaction.user.id)
        alive_players = self.game.get_alive_players()
        current_votes = len(self.game.stop_votes)
        needed = len(alive_players) // 2 + 1
        
        await interaction.response.send_message(f"🏳️ **{interaction.user.display_name}** 提議結束遊戲 ({current_votes}/{needed})")
        
        if current_votes >= needed:
            self.stop()
            await self.cog.stop_game(self.ctx) # 呼叫統一的結束處理

# --- 5. 主程式 ---
class Werewolf(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games = {}

    def get_game(self, ctx):
        return self.games.get(ctx.guild.id)

    # --- 靜音控制功能 ---
    async def mute_all_players(self, ctx, game, mute=True):
        """將所有遊戲玩家靜音或解除靜音"""
        for player in game.players:
            if player.voice: # 只處理在語音頻道的玩家
                try:
                    await player.edit(mute=mute)
                except discord.Forbidden:
                    print(f"❌ 無法更改 {player.display_name} 的靜音狀態 (權限不足)")
                except Exception as e:
                    print(f"⚠️ 靜音錯誤: {e}")

    # --- 混音播放 ---
    async def play_mixed_audio(self, ctx, bgm_file, voice_file=None):
        voice_client = ctx.guild.voice_client
        if not voice_client: return

        bgm_path = os.path.join(SOUND_FOLDER, bgm_file)
        if not os.path.exists(bgm_path): return

        if voice_client.is_playing(): voice_client.stop()

        if not voice_file:
            source = discord.FFmpegPCMAudio(bgm_path, before_options="-stream_loop -1", options="-vn")
            voice_client.play(source)
            return

        voice_path = os.path.join(SOUND_FOLDER, voice_file)
        if not os.path.exists(voice_path):
            source = discord.FFmpegPCMAudio(bgm_path, before_options="-stream_loop -1", options="-vn")
            voice_client.play(source)
            return

        ffmpeg_opts = '-vn'
        complex_filter = f'[0:a]volume=0.4[bg];[1:a]volume=1.5[vc];[bg][vc]amix=inputs=2:duration=first:dropout_transition=2'
        before_opts = f'-stream_loop -1 -i "{bgm_path}" -filter_complex "{complex_filter}"'
        
        try:
            source = discord.FFmpegPCMAudio(voice_path, before_options=before_opts, options=ffmpeg_opts)
            voice_client.play(source)
        except Exception as e:
            print(f"混音播放失敗: {e}")

    async def stop_bgm(self, ctx):
        voice_client = ctx.guild.voice_client
        if voice_client and voice_client.is_playing(): 
            voice_client.stop()

    async def stop_game(self, ctx):
        """統一的遊戲結束清理"""
        if ctx.guild.id in self.games:
            game = self.games[ctx.guild.id]
            # 遊戲結束，解除所有靜音
            await self.mute_all_players(ctx, game, mute=False)
            await self.stop_bgm(ctx)
            del self.games[ctx.guild.id]
            await ctx.send("🛑 **遊戲已結束。**")

    # --- Commands ---
    
    @commands.hybrid_command(name='ww_create', description='[狼人殺] 建立遊戲大廳')
    async def create_game(self, ctx):
        if ctx.guild.id in self.games:
            await ctx.send("這裡已經有一場遊戲了！", ephemeral=True)
            return
        
        game = WerewolfGame(ctx.channel, ctx.author)
        self.games[ctx.guild.id] = game
        
        view = LobbyView(self, game, ctx)
        msg = await ctx.send(embed=view.update_embed(), view=view)
        view.message = msg 

    @commands.hybrid_command(name='ww_force_stop', description='[管理員] 強制結束目前的狼人殺遊戲')
    @commands.has_permissions(administrator=True)
    async def force_stop_game(self, ctx):
        if ctx.guild.id in self.games:
            await self.stop_game(ctx)
        else:
            await ctx.send("目前沒有進行中的遊戲。", ephemeral=True)

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

        identity_view = IdentityView(game)
        await game.channel.send("🎲 **身分已分配！請點擊下方按鈕查看你的身分** (只有你自己看得到)", view=identity_view)

        await asyncio.sleep(5) 
        await self.start_night(ctx, game)

    async def check_night_end(self, ctx, game):
        """檢查是否所有夜間角色都行動完畢"""
        alive_night_roles = []
        for pid in game.players:
            if game.is_alive(pid.id):
                role = game.roles.get(pid.id)
                if role in ["狼人", "預言家"]:
                    alive_night_roles.append(pid.id)
        
        if set(alive_night_roles).issubset(game.night_actions):
            await self.start_day(ctx, game, game.wolf_target)

    async def start_night(self, ctx, game):
        game.phase = PHASE_NIGHT
        game.wolf_target = None
        game.wolf_votes.clear()
        game.night_actions.clear()
        
        # 1. 播放音樂與語音
        await self.play_mixed_audio(ctx, "night.mp3", "voice_night_start.mp3")
        
        # 2. 全體靜音
        await self.mute_all_players(ctx, game, mute=True)
        
        view = NightActionView(game, self, ctx)
        await game.channel.send("🌃 **天黑請閉眼...** (全員已靜音)\n請點擊下方按鈕進行行動。", view=view)

    async def start_day(self, ctx, game, dead_player_id=None):
        game.phase = PHASE_DAY
        game.votes = {} 
        game.stop_votes.clear() 
        
        await self.stop_bgm(ctx)
        
        # 1. 解除靜音
        await self.mute_all_players(ctx, game, mute=False)
        
        msg = "🌅 **天亮了！** (解除靜音)\n"
        
        if dead_player_id and dead_player_id != -1:
            dead_user = ctx.guild.get_member(dead_player_id)
            if dead_user:
                game.status[dead_player_id] = "dead"
                msg += f"昨晚 **{dead_user.display_name}** 慘遭殺害...\n"
                # 讓死者保持靜音 (選擇性)
                try: await dead_user.edit(mute=True)
                except: pass
            else:
                msg += "昨晚有人死亡，但找不到玩家資料。\n"
        else:
            msg += "昨晚是個平安夜，沒有人死亡。\n"
            
        winner = self.check_winner(game)
        if winner:
            await game.channel.send(f"{msg}\n🏆 **遊戲結束！獲勝者: {winner}**")
            role_reveal = "\n".join([f"{p.display_name}: {game.roles[p.id]}" for p in game.players])
            await game.channel.send(f"**身分揭曉：**\n{role_reveal}")
            
            # 遊戲結束解除靜音
            await self.mute_all_players(ctx, game, mute=False)
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
            
            # 讓被處決者靜音
            if eliminated_user and eliminated_user.voice:
                try: await eliminated_user.edit(mute=True)
                except: pass
            
            winner = self.check_winner(game)
            if winner:
                await game.channel.send(f"🏆 **遊戲結束！獲勝者: {winner}**")
                role_reveal = "\n".join([f"{p.display_name}: {game.roles[p.id]}" for p in game.players])
                await game.channel.send(f"**身分揭曉：**\n{role_reveal}")
                # 解除所有靜音
                await self.mute_all_players(ctx, game, mute=False)
                del self.games[ctx.guild.id]
            else:
                await self.start_night(ctx, game)

async def setup(bot):
    await bot.add_cog(Werewolf(bot))