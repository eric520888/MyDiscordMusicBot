import discord
import logging
from discord.ext import commands
from .werewolf_system.game import WerewolfGame
from .werewolf_system.const import BOARD_STANDARD
from .werewolf_system.views import BoardRulesView, LobbyView, create_board_rules_embed


log = logging.getLogger(__name__)


# [修正] 在這裡加入 name="Werewolf"，讓 Help 和 Music 模組都能找到它
class WerewolfBot(commands.Cog, name="Werewolf"):
    def __init__(self, bot):
        self.bot = bot
        self.games = {} # {guild_id: WerewolfGame}

    @commands.hybrid_command(name='ww_create', description='[狼人殺] 建立遊戲大廳')
    async def create_game(self, ctx):
        if ctx.guild is None:
            return await ctx.send("❌ 這個指令只能在伺服器內使用。", ephemeral=True)

        # 檢查是否有舊遊戲
        if ctx.guild.id in self.games:
            old_game = self.games[ctx.guild.id]
            # 如果舊遊戲已結束或在等待中，可以覆蓋
            if old_game.phase == "waiting":
                await ctx.send("這裡已經有一個等待中的大廳了！", ephemeral=True)
                return
            elif old_game.phase == "ended":
                # 舊遊戲已結束，清除並建立新遊戲
                del self.games[ctx.guild.id]
            else:
                # 遊戲進行中
                await ctx.send("❌ 遊戲正在進行中！請先使用 `/ww_force_stop` 結束。", ephemeral=True)
                return

        game = WerewolfGame(self.bot, ctx.channel, ctx.author)
        self.games[ctx.guild.id] = game
        
        view = LobbyView(game)
        try:
            msg = await ctx.send(embed=view.update_embed(), view=view)
        except discord.HTTPException:
            self.games.pop(ctx.guild.id, None)
            log.exception("建立狼人殺大廳訊息失敗")
            return await ctx.send(
                "❌ 無法建立大廳，請檢查機器人的傳送訊息權限。",
                ephemeral=True,
            )
        game.lobby_message = msg

    # 取得遊戲實例 (給 Music 模組檢查用)
    def get_game(self, ctx):
        return self.games.get(ctx.guild.id) if ctx.guild else None

    @commands.hybrid_command(
        name="ww_rules",
        description="[狼人殺] 查看網易官方 12 人板型、配置與角色技能",
    )
    async def rules(self, ctx):
        """顯示官方板型百科，不需要先建立遊戲。"""
        await ctx.send(
            embed=create_board_rules_embed(BOARD_STANDARD),
            view=BoardRulesView(),
            ephemeral=True,
        )

    @commands.hybrid_command(name='ww_force_stop', description='[管理員] 強制結束遊戲')
    @commands.has_permissions(administrator=True)
    async def force_stop(self, ctx):
        if ctx.guild is None:
            return await ctx.send("❌ 這個指令只能在伺服器內使用。", ephemeral=True)

        if ctx.guild.id in self.games:
            game = self.games[ctx.guild.id]
            await game.abort()
            await ctx.send("🛑 管理員強制結束了遊戲。")
        else:
            await ctx.send("目前沒有進行中的遊戲。", ephemeral=True)

    @force_stop.error
    async def force_stop_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ 只有管理員能強制結束遊戲。", ephemeral=True)
            return
        log.exception("強制結束狼人殺時發生錯誤", exc_info=error)
        await ctx.send("❌ 強制結束失敗，請稍後再試。", ephemeral=True)

    async def cog_unload(self):
        for game in list(self.games.values()):
            try:
                await game.abort()
            except Exception:
                log.exception("卸載狼人殺模組時清理遊戲失敗")

async def setup(bot):
    await bot.add_cog(WerewolfBot(bot))
