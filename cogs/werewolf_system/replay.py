import discord
from discord.ui import Select, View
from .const import CAMP_WOLF, CAMP_GOD, CAMP_VILLAGER

class ReplaySelect(Select):
    """復盤系統下拉選單"""
    def __init__(self, game_log: list, players: list, winner: str, total_rounds: int):
        self.game_log = game_log
        self.players = players
        self.winner = winner
        self.total_rounds = total_rounds
        
        options = [
            discord.SelectOption(label="🏠 遊戲總覽", description="查看遊戲整體摘要", value="overview", emoji="🏠"),
            discord.SelectOption(label="🎭 身分一覽", description="查看所有玩家身分", value="identity", emoji="🎭"),
        ]
        
        # 動態添加各回合選項
        for i in range(1, total_rounds + 1):
            options.append(discord.SelectOption(
                label=f"📜 第 {i} 回合", 
                description=f"查看第 {i} 回合的事件",
                value=f"round_{i}",
                emoji="📜"
            ))
        
        super().__init__(placeholder="📖 選擇要查看的項目...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        
        if value == "overview":
            embed = self._create_overview_embed()
        elif value == "identity":
            embed = self._create_identity_embed()
        elif value.startswith("round_"):
            round_num = int(value.split("_")[1])
            embed = self._create_round_embed(round_num)
        else:
            embed = self._create_overview_embed()
        
        await interaction.response.edit_message(embed=embed, view=self.view)

    def _create_overview_embed(self):
        """產生遊戲總覽 Embed"""
        embed = discord.Embed(
            title="📖 狼人殺復盤 - 遊戲總覽",
            description=f"🏆 **獲勝者：{self.winner}**",
            color=discord.Color.gold()
        )
        
        # 玩家統計
        wolves = [p for p in self.players if p.role.camp == CAMP_WOLF]
        gods = [p for p in self.players if p.role.camp == CAMP_GOD]
        villagers = [p for p in self.players if p.role.camp == CAMP_VILLAGER]
        
        embed.add_field(
            name="👥 玩家分佈", 
            value=f"🐺 狼人：{len(wolves)} 人\n🔮 神職：{len(gods)} 人\n👱 村民：{len(villagers)} 人",
            inline=True
        )
        
        embed.add_field(
            name="📊 遊戲資訊",
            value=f"總回合數：{self.total_rounds}\n總事件數：{len(self.game_log)}",
            inline=True
        )
        
        # 死亡順序
        deaths = [e for e in self.game_log if e["event_type"] in ["night_death", "vote_death", "shoot_death"]]
        if deaths:
            death_list = ""
            for e in deaths:
                death_list += f"• {e['data'].get('name', '未知')} ({e['data'].get('role', '?')}) - {e['data'].get('cause', '?')}\n"
            embed.add_field(name="💀 死亡順序", value=death_list[:1024] or "無", inline=False)
        
        embed.set_footer(text="使用下方選單查看更多詳情")
        return embed

    def _create_identity_embed(self):
        """產生身分一覽 Embed"""
        embed = discord.Embed(
            title="📖 狼人殺復盤 - 身分一覽",
            description="所有玩家的真實身分：",
            color=discord.Color.blue()
        )
        
        # 按陣營分類
        wolves = [p for p in self.players if p.role.camp == CAMP_WOLF]
        gods = [p for p in self.players if p.role.camp == CAMP_GOD]
        villagers = [p for p in self.players if p.role.camp == CAMP_VILLAGER]
        
        if wolves:
            wolf_str = "\n".join([f"• {p.display_name} - **{p.role.name}** {'💀' if p.status == 'dead' else '✅'}" for p in wolves])
            embed.add_field(name="🐺 狼人陣營", value=wolf_str, inline=False)
        
        if gods:
            god_str = "\n".join([f"• {p.display_name} - **{p.role.name}** {'💀' if p.status == 'dead' else '✅'}" for p in gods])
            embed.add_field(name="🔮 神職陣營", value=god_str, inline=False)
        
        if villagers:
            villager_str = "\n".join([f"• {p.display_name} - **{p.role.name}** {'💀' if p.status == 'dead' else '✅'}" for p in villagers])
            embed.add_field(name="👱 村民陣營", value=villager_str, inline=False)
        
        embed.set_footer(text="💀 = 已死亡 | ✅ = 存活")
        return embed

    def _create_round_embed(self, round_num: int):
        """產生特定回合的 Embed"""
        embed = discord.Embed(
            title=f"📖 狼人殺復盤 - 第 {round_num} 回合",
            color=discord.Color.dark_purple()
        )
        
        round_events = [e for e in self.game_log if e["round"] == round_num]
        
        # 夜晚事件
        night_events = [e for e in round_events if "night" in e["phase"].lower()]
        if night_events:
            night_str = ""
            for e in night_events:
                night_str += self._format_event(e) + "\n"
            embed.add_field(name="🌙 夜晚", value=night_str or "無事件", inline=False)
        
        # 白天事件
        day_events = [e for e in round_events if "day" in e["phase"].lower()]
        if day_events:
            day_str = ""
            for e in day_events:
                day_str += self._format_event(e) + "\n"
            embed.add_field(name="☀️ 白天", value=day_str or "無事件", inline=False)
        
        if not round_events:
            embed.description = "此回合沒有記錄到事件。"
        
        return embed

    def _format_event(self, event: dict):
        """格式化單一事件"""
        event_type = event["event_type"]
        data = event["data"]
        
        formats = {
            "wolf_kill": f"🔪 狼人殺害了 **{data.get('target', '?')}**",
            "seer_check": f"🔮 預言家查驗了 **{data.get('target', '?')}**，結果：{data.get('result', '?')}",
            "witch_save": f"💊 女巫救了 **{data.get('target', '?')}**",
            "witch_poison": f"☠️ 女巫毒殺了 **{data.get('target', '?')}**",
            "night_death": f"💀 **{data.get('name', '?')}** 死亡（{data.get('cause', '?')}）",
            "vote_death": f"💀 **{data.get('name', '?')}** 被投票處決",
            "shoot_death": f"🔫 **{data.get('name', '?')}** 被開槍帶走",
            "merchant_gift": f"🎁 商人給予 **{data.get('target', '?')}** 技能",
            "guard_protect": f"🛡️ 幸運兒守護了 **{data.get('target', '?')}**",
        }
        
        return formats.get(event_type, f"📝 {event_type}: {data}")


class ReplayView(View):
    """復盤系統 View 容器"""
    def __init__(self, game_log: list, players: list, winner: str, total_rounds: int):
        super().__init__(timeout=300)  # 5分鐘超時
        self.game_log = game_log
        self.players = players
        self.winner = winner
        self.total_rounds = total_rounds
        self.add_item(ReplaySelect(game_log, players, winner, total_rounds))
    
    def get_initial_embed(self):
        """取得初始的 Overview Embed"""
        # 直接使用 ReplaySelect 的方法
        select = self.children[0]
        return select._create_overview_embed()
