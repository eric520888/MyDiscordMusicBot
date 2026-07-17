import discord
from discord.ext import commands
from discord.ui import Select, View


CATEGORY_NAMES = {
    "Werewolf": "狼人殺",
    "Music": "音樂",
    "AIChat": "AI 對話",
    "General": "一般功能",
}

MUSIC_USAGE = {
    "play": "<歌名或 YouTube 網址>",
    "play_at": "<時間> <歌名或 YouTube 網址>",
    "seek": "<時間>",
}


class HelpSelect(Select):
    def __init__(self, bot):
        self.bot = bot
        options = [
            discord.SelectOption(label="主頁", description="回到指令主選單", emoji="🏠", value="home"),
            discord.SelectOption(label="狼人殺", description="狼人殺遊戲相關指令", emoji="🐺", value="Werewolf"),
            discord.SelectOption(label="音樂", description="音樂播放相關指令", emoji="🎵", value="Music"),
            discord.SelectOption(label="AI 對話", description="Gemini AI 聊天", emoji="🧠", value="AIChat"),
            discord.SelectOption(label="一般功能", description="其他工具與設定", emoji="⚙️", value="General"),
        ]
        super().__init__(placeholder="請選擇指令分類...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        if value == "home":
            await interaction.response.edit_message(embed=self.view.home_embed, view=self.view)
        else:
            cog = self.bot.get_cog(value)
            if cog:
                category_name = CATEGORY_NAMES.get(value, value)
                embed = discord.Embed(
                    title=f"{self.options[self._get_index(value)].emoji} {category_name}指令",
                    description=f"以下指令可使用 `!指令` 或 `/指令` 執行。",
                    color=discord.Color.blue()
                )

                if value == "Music":
                    embed.add_field(
                        name="⏱️ 指定播放時間",
                        value=(
                            "從指定位置播放：`!play_at 1:30 歌名或網址`\n"
                            "跳轉目前歌曲：`!seek 1:30`\n"
                            "支援格式：`90`、`1:30`、`1:02:03`、`1h2m3s`"
                        ),
                        inline=False,
                    )
                elif value == "Werewolf":
                    embed.add_field(
                        name="🐺 快速開始",
                        value=(
                            "1. `/ww_create` 建立互動大廳並選板\n"
                            "2. 玩家按「加入」，12 人板人數到齊後由房主開始\n"
                            "3. `/ww_status` 隨時查看階段與存活名單\n"
                            "4. `/ww_rules` 開啟 23 套官方板型百科"
                        ),
                        inline=False,
                    )

                # 以名稱去重，避免 Hybrid 指令同時被當成文字與 Slash
                # 指令加入兩次。
                commands_by_name = {}
                for cmd in cog.get_commands():
                    commands_by_name[cmd.name] = {
                        "command": cmd,
                        "prefix": True,
                        "slash": isinstance(cmd, commands.HybridCommand),
                    }

                for cmd in cog.get_app_commands():
                    entry = commands_by_name.setdefault(
                        cmd.name,
                        {"command": cmd, "prefix": False, "slash": False},
                    )
                    entry["slash"] = True

                for name in sorted(commands_by_name):
                    entry = commands_by_name[name]
                    cmd = entry["command"]
                    desc = (
                        getattr(cmd, "description", None)
                        or getattr(cmd, "help", None)
                        or "暫無說明"
                    )

                    labels = []
                    if entry["prefix"]:
                        usage = MUSIC_USAGE.get(name, "") if value == "Music" else ""
                        labels.append(f"!{name}{f' {usage}' if usage else ''}")
                    if entry["slash"]:
                        labels.append(f"/{name}")

                    embed.add_field(
                        name="　•　".join(f"`{label}`" for label in labels),
                        value=desc,
                        inline=False,
                    )
                
                await interaction.response.edit_message(embed=embed, view=self.view)
            else:
                await interaction.response.send_message("找不到該模組功能！", ephemeral=True)

    def _get_index(self, value):
        for i, option in enumerate(self.options):
            if option.value == value:
                return i
        return 0

class HelpView(View):
    def __init__(self, bot, home_embed):
        super().__init__(timeout=180)
        self.home_embed = home_embed
        self.add_item(HelpSelect(bot))

class CustomHelp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="help", description="顯示指令說明選單")
    async def show_help(self, ctx):
        embed = discord.Embed(
            title="🤖 機器人指令中心",
            description="從下方選單選擇功能分類，即可查看指令、用途與使用方式。",
            color=discord.Color.gold()
        )
        embed.add_field(
            name="如何使用？",
            value=(
                "文字指令：輸入 `!` 加上指令名稱，例如 `!play 稻香`\n"
                "斜線指令：輸入 `/` 後從 Discord 選單選擇指令"
            ),
            inline=False,
        )
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)
        embed.set_footer(text="由 Discord.py 強力驅動")

        view = HelpView(self.bot, embed)
        await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(CustomHelp(bot))
