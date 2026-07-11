import discord
from discord.ext import commands
from .werewolf_system.game import WerewolfGame
from .werewolf_system.views import LobbyView

# [修正] 在這裡加入 name="Werewolf"，讓 Help 和 Music 模組都能找到它
class WerewolfBot(commands.Cog, name="Werewolf"):
    def __init__(self, bot):
        self.bot = bot
        self.games = {} # {guild_id: WerewolfGame}

    @commands.hybrid_command(name='ww_create', description='[狼人殺] 建立遊戲大廳')
    async def create_game(self, ctx):
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
        msg = await ctx.send(embed=view.update_embed(), view=view)
        game.lobby_message = msg

    # 取得遊戲實例 (給 Music 模組檢查用)
    def get_game(self, ctx):
        return self.games.get(ctx.guild.id)

    @commands.hybrid_command(name='ww_force_stop', description='[管理員] 強制結束遊戲')
    @commands.has_permissions(administrator=True)
    async def force_stop(self, ctx):
        if ctx.guild.id in self.games:
            game = self.games[ctx.guild.id]
            
            # 清理資源
            from .werewolf_system.audio import AudioManager
            music = self.bot.get_cog("Music")
            if music and game.phase not in {"waiting", "ended"}:
                await music.release_external_audio(ctx.guild)
            elif not music:
                await AudioManager.stop(ctx.channel)
            await AudioManager.mute_all(ctx.channel, game.players, False)
            if game.wolf_thread:
                try: await game.wolf_thread.delete()
                except: pass
            
            del self.games[ctx.guild.id]
            await ctx.send("🛑 管理員強制結束了遊戲。")
        else:
            await ctx.send("目前沒有進行中的遊戲。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(WerewolfBot(bot))
