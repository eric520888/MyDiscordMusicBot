import discord
from discord.ext import commands
from .werewolf_system.game import WerewolfGame
from .werewolf_system.views import LobbyView

class WerewolfBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games = {} # {guild_id: WerewolfGame}

    @commands.hybrid_command(name='ww_create', description='[狼人殺] 建立遊戲大廳 (新架構)')
    async def create_game(self, ctx):
        if ctx.guild.id in self.games:
            await ctx.send("這裡已經有一場遊戲了！", ephemeral=True)
            return
        
        game = WerewolfGame(self.bot, ctx.channel, ctx.author)
        self.games[ctx.guild.id] = game
        
        view = LobbyView(game)
        msg = await ctx.send(embed=view.update_embed(), view=view)
        game.lobby_message = msg

    @commands.hybrid_command(name='ww_force_stop', description='[管理員] 強制結束遊戲')
    @commands.has_permissions(administrator=True)
    async def force_stop(self, ctx):
        if ctx.guild.id in self.games:
            game = self.games[ctx.guild.id]
            # 這裡簡單處理，理想情況是呼叫 game.end_game 但不分勝負
            # 直接清理資源
            from .werewolf_system.audio import AudioManager
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