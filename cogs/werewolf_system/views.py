from collections import Counter

import discord
from discord.ui import View, Select, Button
from .const import *
from .roles import (
    AwakenedGuard,
    AwakenedHunter,
    AwakenedWhiteWolfKing,
    CrimsonApostle,
    Knight,
)


CAMP_STYLE = {
    CAMP_WOLF: ("🐺", discord.Color.dark_red()),
    CAMP_GOD: ("🔮", discord.Color.blurple()),
    CAMP_VILLAGER: ("🌾", discord.Color.green()),
    CAMP_THIRD: ("🎭", discord.Color.gold()),
}


def _split_board_name(spec):
    parts = spec.name.split(" ", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else ("🎲", spec.name)


def _composition_by_camp(roles):
    counts = Counter(roles)
    lines = []
    for camp in (CAMP_WOLF, CAMP_GOD, CAMP_VILLAGER, CAMP_THIRD):
        camp_roles = [
            f"{role}×{count}" if count > 1 else role
            for role, count in counts.items()
            if ROLE_CATALOG[role].camp == camp
        ]
        if camp_roles:
            emoji, _ = CAMP_STYLE[camp]
            lines.append(f"{emoji} **{camp.replace('陣營', '')}**｜{'、'.join(camp_roles)}")
    return "\n".join(lines)


def _progress_bar(current, required, width=10):
    ratio = min(1, current / required) if required else 1
    filled = round(width * ratio)
    return "▰" * filled + "▱" * (width - filled)

# --- 1. 大廳板子選擇 ---
class BoardSelect(Select):
    def __init__(self, game_state):
        self.game = game_state
        options = [discord.SelectOption(
            label="自動配置（朋友局）",
            value=BOARD_AUTO,
            description="3～20 人，依人數自動平衡基礎角色",
            emoji="🎲",
        )]
        options.extend(
            discord.SelectOption(
                label=_split_board_name(BOARD_SPECS[board_id])[1],
                value=board_id,
                description=f"12 人｜{BOARD_SPECS[board_id].description}",
                emoji=_split_board_name(BOARD_SPECS[board_id])[0],
            )
            for board_id in OFFICIAL_BOARD_IDS
        )
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
        minimum = BOARD_MIN_PLAYERS.get(self.game.board_id, 3)
        count = len(self.game.players)
        ready = count == minimum if self.game.board_id in BOARD_SPECS else count >= minimum
        status = "✅ 人數已就緒" if ready else "⏳ 等待玩家"
        embed = discord.Embed(
            title="🐺 狼人殺｜互動遊戲大廳",
            description=(
                f"**{status}**\n"
                f"`{_progress_bar(count, minimum)}` **{count}/{minimum}**\n"
                "使用下方按鈕加入；房主可從選單即時切換板子。"
            ),
            color=discord.Color.green() if ready else discord.Color.dark_red(),
        )
        
        # 玩家列表
        if self.game.players:
            player_list = "\n".join(
                f"`{index:02}` {p.display_name}"
                for index, p in enumerate(self.game.players, start=1)
            )
        else:
            player_list = "（等待玩家加入...）"
        
        embed.add_field(name=f"👥 玩家名單｜{count} 人", value=player_list, inline=False)
        embed.add_field(name="📜 目前板子", value=BOARD_NAMES.get(self.game.board_id, "未知"), inline=True)
        embed.add_field(name="🎮 房主", value=self.game.host.display_name, inline=True)
        if self.game.board_id in BOARD_SPECS:
            spec = BOARD_SPECS[self.game.board_id]
            embed.add_field(
                name="🧩 陣容預覽",
                value=_composition_by_camp(spec.roles),
                inline=False,
            )
            embed.add_field(name="✨ 板子特色", value=spec.description, inline=False)
        count_text = f"固定需要 {minimum} 人" if self.game.board_id in BOARD_SPECS else f"至少需要 {minimum} 人"
        embed.set_footer(text=f"{count_text}｜切板、開始與關閉僅限房主")
        
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
    def __init__(self, game_state, player_obj, action_type, *, mode=None):
        self.game = game_state
        self.player = player_obj # 操作者
        self.action_type = action_type
        self.mode = mode
        
        options = []
        
        # 特殊選項 (空刀/空驗)
        if action_type == 'wolf_kill':
            options.append(discord.SelectOption(label="空刀", value="-1", emoji="☮️"))
        elif action_type == 'seer_check':
            options.append(discord.SelectOption(label="空驗", value="-1", emoji="☮️"))

        for p in game_state.get_action_targets(player_obj, action_type):
            options.append(discord.SelectOption(label=p.display_name, value=str(p.id), emoji="👤"))
        
        ph = "選擇目標..."
        if action_type == 'wolf_kill': ph = "🔪 狼隊投票..."
        elif action_type == 'seer_check': ph = "🔮 查驗對象..."
        elif action_type == 'merchant_give': ph = "💰 選擇幸運兒..."

        labels = {
            "guard": "🛡️ 選擇守護目標...",
            "dream": "🌙 選擇夢遊目標...",
            "charm": "💋 選擇魅惑目標...",
            "awakened_charm": "✨ 選擇魅惑目標...",
            "exact_check": "🗿 選擇查驗目標...",
            "wolf_witch_check": "🔮 選擇查驗目標...",
            "pure_white_check": "⚪ 選擇查驗目標...",
            "hunt": "🏹 選擇狩獵目標...",
            "fear": "🌑 選擇恐懼目標...",
            "block": "⏳ 選擇封鎖目標...",
            "confuse": "🦊 選擇迷惑目標...",
            "devour": "🌘 選擇吞噬目標...",
            "light_guard": "☀️ 選擇庇護目標...",
            "night_servant": "🦇 選擇夜僕目標...",
            "secret_guard": "🃏 選擇保護目標...",
            "mirror_check": "🪞 選擇查驗目標...",
            "mimic": "🎭 選擇模仿目標...",
            "claw_pass": "🐾 選擇狼王爪接收者...",
            "mimic_witch": "☠️ 選擇模仿毒殺目標...",
            "double_check": "🔮 同時選擇兩名玩家...",
            "fate_bind": "🦋 同時選擇兩名玩家...",
            "time_wave": "🌓 選擇作用目標...",
            "choose_idol": "💞 選擇你的偶像...",
            "convert": "🗿 選擇相鄰轉化者...",
            "awakened_guard": "🛡️ 選擇覺醒守護目標...",
            "dream_speech": "🌌 選擇夢語者...",
        }
        ph = labels.get(action_type, ph)

        is_pair = action_type in {"double_check", "fate_bind"}
        boosted = game_state.get_night_action_limit(player_obj, action_type) > 1
        minimum = 2 if is_pair else 1
        maximum = 2 if is_pair or boosted else 1

        super().__init__(placeholder=ph, min_values=minimum, max_values=maximum, options=options)

    async def callback(self, interaction: discord.Interaction):
        target_ids = [int(value) for value in self.values]
        target = target_ids if len(target_ids) > 1 else target_ids[0]
        await self.game.handle_night_action(
            interaction,
            self.player,
            self.action_type,
            target,
            mode=self.mode,
        )


class TimeWaveModeSelect(Select):
    def __init__(self, game_state, player_obj):
        self.game = game_state
        self.player = player_obj
        super().__init__(
            placeholder="🌓 選擇時波效果...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label="增幅", value="boost", description="令目標獲得額外行動", emoji="⬆️"),
                discord.SelectOption(label="削弱", value="weaken", description="令目標當晚無法行動", emoji="⬇️"),
            ],
        )

    async def callback(self, interaction: discord.Interaction):
        await self.game.send_time_wave_target(interaction, self.player, self.values[0])

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
        if isinstance(player_obj.role, AwakenedHunter):
            for label, direction, emoji in (
                ("向左巡獵", "left", "⬅️"),
                ("向右巡獵", "right", "➡️"),
            ):
                direction_button = Button(
                    label=label, style=discord.ButtonStyle.danger, emoji=emoji
                )

                async def callback(interaction, selected=direction):
                    await game_state.handle_awakened_hunt(
                        interaction, player_obj, selected
                    )

                direction_button.callback = callback
                self.add_item(direction_button)
        elif game_state.get_alive_players():
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


class DayActionSelect(Select):
    def __init__(self, game_state):
        self.game = game_state
        alive = game_state.get_alive_players()
        options = [
            discord.SelectOption(
                label="提議結束遊戲",
                value="stop_game",
                description="超過半數存活玩家同意後強制結束",
                emoji="🏳️",
            )
        ]
        if any(
            isinstance(p.role, Knight) and not p.role.disabled and not p.role.used_skill
            for p in alive
        ):
            options.append(discord.SelectOption(label="騎士決鬥", value="knight_duel", emoji="⚔️"))
        if any(
            isinstance(p.role, CrimsonApostle)
            and not p.role.disabled
            and not p.role.used_skill
            for p in alive
        ):
            options.append(discord.SelectOption(label="赤月自曝", value="crimson_reveal", emoji="🌕"))
        if any(
            isinstance(p.role, AwakenedGuard)
            and not p.role.disabled
            and p.role.state.get("last_guard_round") != game_state.round_num
            for p in alive
        ):
            options.append(discord.SelectOption(label="覺醒守護", value="awakened_guard", emoji="🛡️"))
        if any(
            isinstance(p.role, AwakenedWhiteWolfKing) and not p.role.used_skill
            for p in alive
        ):
            options.append(discord.SelectOption(label="白狼引爆", value="awakened_white_wolf", emoji="🩸"))
        if any(
            p.role.can_self_destruct
            and not p.role.state.get("self_destruct_attempted")
            for p in alive
        ):
            options.append(discord.SelectOption(label="狼人自爆", value="wolf_self_destruct", emoji="💥"))
        super().__init__(
            placeholder="☀️ 白天特殊行動...",
            min_values=1,
            max_values=1,
            options=options,
            row=4,
        )

    async def callback(self, interaction: discord.Interaction):
        action = self.values[0]
        if action == "stop_game":
            return await self.game.handle_stop_vote(interaction)
        if action == "crimson_reveal":
            return await self.game.handle_crimson_reveal(interaction)
        if action == "wolf_self_destruct":
            return await self.game.handle_wolf_self_destruct(interaction)
        await self.game.send_day_skill_select(interaction, action)

class VotingView(View):
    def __init__(self, game_state):
        super().__init__(timeout=None)
        self.game = game_state
        for p in game_state.get_alive_players():
            self.add_item(VoteButton(game_state, p))
        self.add_item(DayActionSelect(game_state))


class BoardRulesSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=_split_board_name(spec)[1],
                value=board_id,
                description=spec.description,
                emoji=_split_board_name(spec)[0],
            )
            for board_id, spec in BOARD_SPECS.items()
        ]
        super().__init__(placeholder="📚 選擇要查看的官方板型...", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            embed=create_board_rules_embed(self.values[0]),
            view=self.view,
        )


def create_board_rules_embed(board_id):
    spec = BOARD_SPECS[board_id]
    counts = {}
    for role in spec.roles:
        counts[role] = counts.get(role, 0) + 1
    embed = discord.Embed(
        title=f"📚 {spec.name}",
        description=(
            f"### 12 人官方板型\n"
            f"{_composition_by_camp(spec.roles)}\n\n"
            f"✨ **核心玩法**｜{spec.description}"
        ),
        color=discord.Color.dark_purple(),
    )
    for role in counts:
        info = ROLE_CATALOG[role]
        emoji, _ = CAMP_STYLE[info.camp]
        embed.add_field(
            name=f"{emoji} {role}",
            value=info.description[:1024],
            inline=True,
        )
    embed.set_footer(
        text=f"角色種類 {len(counts)}｜配置與技能依網易《狼人殺官方》正式上線板型整理"
    )
    return embed


def create_identity_embed(game, player):
    emoji, color = CAMP_STYLE.get(
        player.role.camp, ("❔", discord.Color.greyple())
    )
    embed = discord.Embed(
        title=f"{emoji} 你的身分｜{player.role.name}",
        description=player.role.description,
        color=color,
    )
    embed.add_field(name="陣營", value=player.role.camp, inline=True)
    embed.add_field(
        name="存活狀態",
        value="🟢 存活" if player.status == "alive" else "⚫ 已出局",
        inline=True,
    )
    embed.add_field(name="目前回合", value=f"第 {max(game.round_num, 1)} 輪", inline=True)
    return embed


def create_game_status_embed(game):
    phase_names = {
        PHASE_WAITING: "⏳ 大廳等待中",
        PHASE_STARTING: "🎴 身分確認",
        PHASE_NIGHT_1: "🌃 上半夜行動",
        PHASE_NIGHT_2: "🌙 下半夜行動",
        PHASE_DAY: "☀️ 白天討論／投票",
        PHASE_SHOOT: "🔫 出局技能結算",
        PHASE_ENDED: "🏁 遊戲已結束",
    }
    alive = game.get_alive_players()
    dead = [player for player in game.players if player.status != "alive"]
    color = (
        discord.Color.dark_blue()
        if game.phase in {PHASE_NIGHT_1, PHASE_NIGHT_2}
        else discord.Color.gold()
        if game.phase == PHASE_DAY
        else discord.Color.dark_red()
    )
    embed = discord.Embed(
        title="🐺 狼人殺｜即時戰況",
        description=phase_names.get(game.phase, game.phase),
        color=color,
    )
    embed.add_field(
        name="📜 板子",
        value=BOARD_NAMES.get(game.board_id, "未知"),
        inline=True,
    )
    embed.add_field(name="🔄 回合", value=f"第 {game.round_num} 輪", inline=True)
    embed.add_field(
        name="👥 存活",
        value=f"{len(alive)} / {len(game.players)}",
        inline=True,
    )
    embed.add_field(
        name="🟢 存活玩家",
        value="、".join(player.display_name for player in alive) or "無",
        inline=False,
    )
    embed.add_field(
        name="⚫ 已出局玩家",
        value="、".join(player.display_name for player in dead) or "尚無",
        inline=False,
    )
    embed.set_footer(text="戰況卡不會公開尚未揭曉的角色身分")
    return embed


class BoardRulesView(View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(BoardRulesSelect())
