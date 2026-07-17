import discord
import logging
from discord.ext import commands
from .werewolf_system.game import WerewolfGame
from .werewolf_system.const import BOARD_STANDARD
from .werewolf_system.views import (
    BoardRulesView,
    LobbyView,
    create_board_rules_embed,
    create_game_status_embed,
)


log = logging.getLogger(__name__)


# [修正] 在這裡加入 name="Werewolf"，讓 Help 和 Music 模組都能找到它
class WerewolfBot(commands.Cog, name="Werewolf"):
    def __init__(self, bot):
        self.bot = bot
        self.games = {} # {guild_id: WerewolfGame}

    async def _publish_lobby(self, ctx, game):
        """在目前頻道送出可操作的大廳，並更新遊戲保存的訊息引用。"""
        game.channel = ctx.channel
        view = LobbyView(game)
        message = await ctx.send(embed=view.update_embed(), view=view)
        game.lobby_message = message
        return message

    async def _restore_waiting_lobby(self, ctx, game):
        """刷新仍存在的大廳；原訊息遺失時保留玩家並在目前頻道重建。"""
        message = game.lobby_message
        if message is not None:
            try:
                view = LobbyView(game)
                await message.edit(embed=view.update_embed(), view=view)
            except (discord.HTTPException, AttributeError):
                log.info("等待中的狼人殺大廳訊息已遺失，準備重建")
            else:
                jump_url = getattr(message, "jump_url", None)
                text = "♻️ 已刷新等待中的狼人殺大廳。"
                if jump_url:
                    text += f" [前往大廳]({jump_url})"
                await ctx.send(text, ephemeral=True)
                return message

        try:
            restored = await self._publish_lobby(ctx, game)
        except discord.HTTPException:
            log.exception("重建狼人殺大廳訊息失敗")
            await ctx.send(
                "❌ 舊大廳訊息已遺失，但目前無法重建；請檢查機器人的傳送訊息權限。",
                ephemeral=True,
            )
            return None
        await ctx.send(
            "♻️ 原本的大廳訊息已遺失，已保留玩家名單並在這裡重建。",
            ephemeral=True,
        )
        return restored

    @commands.hybrid_command(name='ww_create', description='[狼人殺] 建立遊戲大廳')
    async def create_game(self, ctx):
        if ctx.guild is None:
            return await ctx.send("❌ 這個指令只能在伺服器內使用。", ephemeral=True)

        # 檢查是否有舊遊戲
        if ctx.guild.id in self.games:
            old_game = self.games[ctx.guild.id]
            # 等待中的遊戲可能只是原大廳訊息被刪除；優先刷新或重建。
            if old_game.phase == "waiting":
                return await self._restore_waiting_lobby(ctx, old_game)
            elif old_game.phase == "ended":
                # 舊遊戲已結束，清除並建立新遊戲
                del self.games[ctx.guild.id]
            else:
                # 遊戲進行中
                await ctx.send("❌ 遊戲正在進行中！請先使用 `/ww_force_stop` 結束。", ephemeral=True)
                return

        game = WerewolfGame(self.bot, ctx.channel, ctx.author)
        self.games[ctx.guild.id] = game
        
        try:
            await self._publish_lobby(ctx, game)
        except discord.HTTPException:
            self.games.pop(ctx.guild.id, None)
            log.exception("建立狼人殺大廳訊息失敗")
            return await ctx.send(
                "❌ 無法建立大廳，請檢查機器人的傳送訊息權限。",
                ephemeral=True,
            )

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

    @commands.hybrid_command(
        name="ww_status",
        description="[狼人殺] 查看目前板子、階段、回合與存活名單",
    )
    async def status(self, ctx):
        if ctx.guild is None:
            return await ctx.send("❌ 這個指令只能在伺服器內使用。", ephemeral=True)
        game = self.games.get(ctx.guild.id)
        if not game:
            return await ctx.send("目前沒有狼人殺遊戲；使用 `/ww_create` 建立大廳。", ephemeral=True)
        await ctx.send(embed=create_game_status_embed(game), ephemeral=True)

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
