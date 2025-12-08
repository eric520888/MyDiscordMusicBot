import discord
from discord.ext import commands

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name='ping', description='測試機器人延遲')
    async def ping(self, ctx):
        latency = round(self.bot.latency * 1000)
        await ctx.send(f'🏓 Pong! 延遲: {latency}ms')

    @commands.hybrid_command(name='sync', description='[管理員] 強制同步斜線指令')
    @commands.is_owner()
    async def sync(self, ctx):
        await ctx.defer()
        try:
            self.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await self.bot.tree.sync(guild=ctx.guild)
            await ctx.send(f"✅ 成功同步 {len(synced)} 個指令到本伺服器！")
        except Exception as e:
            await ctx.send(f"❌ 同步失敗: {e}")

async def setup(bot):
    await bot.add_cog(General(bot))