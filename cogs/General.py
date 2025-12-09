import discord
from discord.ext import commands
from discord.ui import Button, View

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- 測試延遲 ---
    @commands.hybrid_command(name='ping', description='測試機器人延遲')
    async def ping(self, ctx):
        latency = round(self.bot.latency * 1000)
        await ctx.send(f'🏓 Pong! 延遲: {latency}ms')

    # --- [新增] 麥當勞點餐 ---
    @commands.hybrid_command(name='mcdonalds', aliases=['麥當勞', 'mcd'], description='肚子餓了？開啟麥當勞歡樂送網頁')
    async def mcdonalds(self, ctx):
        # 建立一個包含連結按鈕的 View
        view = View()
        
        # style=discord.ButtonStyle.link (連結按鈕) 不需要 callback，只要 url
        btn_delivery = Button(
            label="前往歡樂送訂餐", 
            style=discord.ButtonStyle.link, 
            url="https://www.mcdelivery.com.tw/",
            emoji="🍔"
        )
        
        btn_official = Button(
            label="麥當勞官網", 
            style=discord.ButtonStyle.link, 
            url="https://www.mcdonalds.com/tw/zh-tw.html",
            emoji="🍟"
        )
        
        view.add_item(btn_delivery)
        view.add_item(btn_official)

        embed = discord.Embed(
            title="🍟 麥當勞點餐",
            description="肚子餓了嗎？點擊下方按鈕直接去訂餐！",
            color=discord.Color.red() # 麥當勞紅
        )
        # 可以放一張麥當勞的圖增加食慾 (選用)
        embed.set_thumbnail(url="https://cdn.icon-icons.com/icons2/2699/PNG/512/mcdonalds_logo_icon_169747.png")
        
        await ctx.send(embed=embed, view=view)

    # --- 同步指令 (重要工具) ---
    @commands.command(name='sync', help='[管理員] 強制同步斜線指令')
    @commands.is_owner()
    async def sync(self, ctx):
        await ctx.send("🔄 正在同步指令...")
        try:
            synced = await self.bot.tree.sync()
            await ctx.send(f"✅ 成功同步 {len(synced)} 個指令！")
        except Exception as e:
            await ctx.send(f"❌ 同步失敗: {e}")
@commands.command(name='checkowner')
async def checkowner(self, ctx):
        """檢查你是否為 bot owner"""
        # 這行會自動判斷你在不在 owner_ids 清單內
        is_owner = await self.bot.is_owner(ctx.author)

        if is_owner:
            await ctx.send(f"✅ {ctx.author.mention} 認證通過！歡迎使用主人！")
        else:
            # 這裡做個判斷：如果是多人模式，就顯示 IDs 集合；單人模式就顯示 ID
            # 這樣你才能看到到底設定了哪些 ID
            current_owners = self.bot.owner_ids or {self.bot.owner_id}
            
            await ctx.send(
                f"❌ 你不是狐狸鬆餅，我只認狐狸鬆餅為主人！\n"
                f"目前允許的 Owner IDs: {current_owners}"
            )
async def setup(bot):
    await bot.add_cog(General(bot))