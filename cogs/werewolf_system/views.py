import discord
from discord.ui import View, Select, Button
from .const import *

# --- 1. 大廳板子選擇 ---
class BoardSelect(Select):
    def __init__(self, game_state):
        self.game = game_state
        options = [
            discord.SelectOption(label="自動配置", value=BOARD_AUTO, description="3 人起，依人數自動平衡", emoji="🎲"),
            discord.SelectOption(label="標準板", value=BOARD_STANDARD, description="5 人起，無狼王、無商人", emoji="🔮"),
            discord.SelectOption(label="狼王板", value=BOARD_WOLF_KING, description="5 人起，狼隊有一名狼王", emoji="👑"),
            discord.SelectOption(label="奇跡板", value=BOARD_MERCHANT, description="7 人起，加入奇跡商人與狼王", emoji="💰")
        ]
        super().__init__(placeholder="📜 選擇板子...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        # 呼叫 Game 的方法來處理，而不是在這裡寫邏輯
        await self.game.set_board(interaction, self.values[0])

class LobbyView(View):
    def __init__(self, game_state):
        super().__init__(timeout=None) # 大廳不設超時，由 Game loop 控制
        self.game = game_state
        self.add_item(BoardSelect(game_state))
    
    def update_embed(self):
        """產生大廳 Embed"""
        embed = discord.Embed(
            title="🐺 狼人殺大廳",
            description=f"點擊下方按鈕加入遊戲，最多 {MAX_PLAYERS} 人。",
            color=discord.Color.dark_red()
        )
        
        # 玩家列表
        if self.game.players:
            player_list = "\n".join([f"• {p.display_name}" for p in self.game.players])
        else:
            player_list = "（等待玩家加入...）"
        
        embed.add_field(name=f"👥 玩家 ({len(self.game.players)})", value=player_list, inline=False)
        embed.add_field(name="📜 板子", value=BOARD_NAMES.get(self.game.board_id, "未知"), inline=True)
        embed.add_field(name="🎮 房主", value=self.game.host.display_name, inline=True)
        minimum = BOARD_MIN_PLAYERS.get(self.game.board_id, 3)
        embed.set_footer(text=f"目前板子至少需要 {minimum} 人；板子與開始／關閉僅限房主操作")
        
        return embed

    @discord.ui.button(label="加入", style=discord.ButtonStyle.green, emoji="✋")
    async def join(self, interaction: discord.Interaction, button: Button):
        await self.game.player_join(interaction)

    @discord.ui.button(label="退出", style=discord.ButtonStyle.red, emoji="🚪")
    async def leave(self, interaction: discord.Interaction, button: Button):
        await self.game.player_leave(interaction)

    @discord.ui.button(label="開始", style=discord.ButtonStyle.blurple, emoji="🚀")
    async def start(self, interaction: discord.Interaction, button: Button):
        await self.game.start_game(interaction)

    @discord.ui.button(label="關閉", style=discord.ButtonStyle.grey, emoji="✖️")
    async def close(self, interaction: discord.Interaction, button: Button):
        await self.game.close_lobby(interaction)

# --- 2. 身分確認 ---
class IdentityView(View):
    def __init__(self, game_state):
        super().__init__(timeout=None)
        self.game = game_state

    @discord.ui.button(label="🕵️ 查看身分", style=discord.ButtonStyle.primary)
    async def check(self, interaction: discord.Interaction, button: Button):
        await self.game.send_identity(interaction)

    @discord.ui.button(label="強制入夜", style=discord.ButtonStyle.danger)
    async def force(self, interaction: discord.Interaction, button: Button):
        await self.game.force_night(interaction)

# --- 3. 夜晚通用選單 (狼人/預言家/商人) ---
class NightTargetSelect(Select):
    def __init__(self, game_state, player_obj, action_type):
        self.game = game_state
        self.player = player_obj # 操作者
        self.action_type = action_type # 'wolf_kill', 'seer_check', 'merchant_give'
        
        options = []
        
        # 特殊選項 (空刀/空驗)
        if action_type == 'wolf_kill':
            options.append(discord.SelectOption(label="空刀", value="-1", emoji="☮️"))
        elif action_type == 'seer_check':
            options.append(discord.SelectOption(label="空驗", value="-1", emoji="☮️"))

        # 加入活人名單
        for p in game_state.get_alive_players():
            # 商人不能選自己
            if action_type == 'merchant_give' and p.id == player_obj.id:
                continue
            options.append(discord.SelectOption(label=p.display_name, value=str(p.id), emoji="👤"))
        
        ph = "選擇目標..."
        if action_type == 'wolf_kill': ph = "🔪 狼隊投票..."
        elif action_type == 'seer_check': ph = "🔮 查驗對象..."
        elif action_type == 'merchant_give': ph = "💰 選擇幸運兒..."

        super().__init__(placeholder=ph, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        target_id = int(self.values[0])
        await self.game.handle_night_action(interaction, self.player, self.action_type, target_id)

class MerchantSkillSelect(Select):
    def __init__(self, game_state, player_obj, target_id):
        self.game = game_state
        self.player = player_obj
        self.target_id = target_id
        options = [
            discord.SelectOption(label="查驗", value="check", emoji="🔮"),
            discord.SelectOption(label="毒藥", value="poison", emoji="☠️"),
            discord.SelectOption(label="守衛", value="guard", emoji="🛡️")
        ]
        super().__init__(placeholder="💰 選擇給予的技能...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await self.game.handle_merchant_skill(interaction, self.player, self.target_id, self.values[0])

# --- 4. 女巫選單 ---
class WitchView(View):
    def __init__(self, game_state, player_obj):
        super().__init__(timeout=300)
        self.game = game_state
        self.player = player_obj

    @discord.ui.button(label="救", style=discord.ButtonStyle.green, emoji="💊")
    async def save(self, interaction: discord.Interaction, button: Button):
        await self.game.handle_witch_save(interaction, self.player)

    @discord.ui.button(label="毒", style=discord.ButtonStyle.danger, emoji="☠️")
    async def poison(self, interaction: discord.Interaction, button: Button):
        # 毒藥需要選人，這裡發送一個 Select View
        await self.game.send_witch_poison_select(interaction, self.player)

    @discord.ui.button(label="跳過", style=discord.ButtonStyle.grey)
    async def skip(self, interaction: discord.Interaction, button: Button):
        await self.game.handle_night_action(interaction, self.player, "witch_skip", None)

# --- 5. 幸運兒選單 (動態生成) ---
class LuckyView(View):
    def __init__(self, game_state, player_obj, skill_type):
        super().__init__(timeout=300)
        # 這裡直接復用 NightTargetSelect，只是 action_type 不同
        action_map = {
            "check": "lucky_check",
            "poison": "lucky_poison",
            "guard": "lucky_guard"
        }
        self.add_item(NightTargetSelect(game_state, player_obj, action_map[skill_type]))

# --- 6. 開槍與投票 ---
class ShooterSelect(Select):
    def __init__(self, game_state, player_obj):
        self.game = game_state
        self.player = player_obj
        options = [discord.SelectOption(label=p.display_name, value=str(p.id), emoji="🔫") 
                   for p in game_state.get_alive_players()]
        super().__init__(placeholder="🔫 開槍帶走...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await self.game.handle_shoot(interaction, self.player, int(self.values[0]))


class ShooterView(View):
    def __init__(self, game_state, player_obj):
        super().__init__(timeout=300)
        self.game = game_state
        self.player = player_obj
        if game_state.get_alive_players():
            self.add_item(ShooterSelect(game_state, player_obj))

    @discord.ui.button(label="放棄開槍", style=discord.ButtonStyle.grey, emoji="✋")
    async def skip(self, interaction: discord.Interaction, button: Button):
        await self.game.handle_skip_shoot(interaction, self.player)

class VoteButton(Button):
    def __init__(self, game_state, target_player):
        super().__init__(label=target_player.display_name, style=discord.ButtonStyle.secondary)
        self.game = game_state
        self.target_id = target_player.id

    async def callback(self, interaction: discord.Interaction):
        await self.game.handle_vote(interaction, self.target_id)

class VotingView(View):
    def __init__(self, game_state):
        super().__init__(timeout=None)
        self.game = game_state
        for p in game_state.get_alive_players():
            self.add_item(VoteButton(game_state, p))

    @discord.ui.button(label="🏳️ 投票結束遊戲", style=discord.ButtonStyle.danger, row=4)
    async def stop_game(self, interaction: discord.Interaction, button: Button):
        await self.game.handle_stop_vote(interaction)
