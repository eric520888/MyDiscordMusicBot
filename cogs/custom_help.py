import discord
from discord.ext import commands
from discord.ui import Select, View

class HelpSelect(Select):
    def __init__(self, bot):
        self.bot = bot
        options = [
            discord.SelectOption(label="🏠 主頁", description="回到指令主選單", emoji="🏠", value="home"),
            discord.SelectOption(label="🐺 狼人殺", description="狼人殺遊戲相關指令", emoji="🐺", value="Werewolf"),
            discord.SelectOption(label="🎵 音樂", description="音樂播放相關指令", emoji="🎵", value="Music"),
            discord.SelectOption(label="🤖 AI 對話", description="Gemini AI 聊天", emoji="🧠", value="AIChat"),
            discord.SelectOption(label="⚙️ 一般功能", description="其他工具與設定", emoji="⚙️", value="General"),
        ]
        super().__init__(placeholder="請選擇指令分類...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        if value == "home":
            await interaction.response.edit_message(embed=self.view.home_embed, view=self.view)
        else:
            cog = self.bot.get_cog(value)
            if cog:
                embed = discord.Embed(
                    title=f"{self.options[self._get_index(value)].emoji} {value} 指令列表",
                    description=f"這裡是 {value} 模組的所有指令：",
                    color=discord.Color.blue()
                )
                
                # 自動讀取該 Cog 下的所有指令 (包含 slash command)
                # 這裡混合讀取 hybrid_commands 和 app_commands
                commands_list = cog.get_commands()
                if not commands_list:
                    # 嘗試讀取 app_commands (如果該 cog 只有斜線指令)
                    commands_list = cog.get_app_commands()

                for cmd in commands_list:
                    # 處理指令名稱與說明
                    name = cmd.name
                    desc = cmd.description or "暫無說明"
                    
                    # 判斷是否為斜線指令格式
                    prefix = "/" 
                    
                    embed.add_field(name=f"`{prefix}{name}`", value=desc, inline=False)
                
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
    async def help(self, ctx):
        embed = discord.Embed(
            title="🤖 機器人指令中心",
            description="請從下方選單選擇你想查詢的功能分類。",
            color=discord.Color.gold()
        )
        embed.add_field(name="如何使用？", value="輸入 `/` 或 `!` 加上指令名稱即可。", inline=False)
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)
        embed.set_footer(text="由 Discord.py 強力驅動")

        view = HelpView(self.bot, embed)
        await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(CustomHelp(bot))