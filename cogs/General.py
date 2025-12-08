import discord
from discord.ext import commands

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return
        if message.content.lower() == 'hello':
            await message.channel.send('Hi there!')

    @commands.command(name='ping', help='測試機器人延遲')
    async def ping(self, ctx):
        latency = round(self.bot.latency * 1000)
        await ctx.send(f'🏓 Pong! 延遲: {latency}ms')

    # --- 新增這個指令 ---
    @commands.command(name='sync', help='[管理員專用] 強制同步斜線指令到目前伺服器')
    @commands.is_owner() # 只有機器人擁有者能用 (避免路人亂按)
    async def sync(self, ctx):
        await ctx.send("🔄 正在同步指令到本伺服器...")
        try:
            # 將全域指令複製到目前的伺服器 (Guild)
            self.bot.tree.copy_global_to(guild=ctx.guild)
            # 開始同步
            synced = await self.bot.tree.sync(guild=ctx.guild)
            await ctx.send(f"✅ 成功同步 {len(synced)} 個斜線指令！現在應該可以秒用了。")
        except Exception as e:
            await ctx.send(f"❌ 同步失敗: {e}")

async def setup(bot):
    await bot.add_cog(General(bot))