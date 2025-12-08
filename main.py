import discord
import os
import asyncio
from discord.ext import commands
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# --- 機器人設定 ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- Opus 載入邏輯 (Linux 環境需要) ---
if not discord.opus.is_loaded():
    try:
        discord.opus.load_opus('libopus.so.0')
    except discord.opus.OpusError:
        print("Opus library could not be loaded.")

@bot.event
async def on_ready():
    print(f'主程式啟動成功：登入身分 {bot.user}')
    await bot.change_presence(activity=discord.Game(name="/help | 多功能機器人"))
    
    # --- 關鍵：同步斜線指令 ---
    # 這行程式碼會把你的指令註冊到 Discord 伺服器上
    try:
        synced = await bot.tree.sync()
        print(f"✅ 已同步 {len(synced)} 個斜線指令 (Slash Commands)")
    except Exception as e:
        print(f"❌ 同步指令失敗: {e}")

async def load_extensions():
    """自動讀取 cogs 資料夾下的所有 .py 檔案並載入"""
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            extension_name = f'cogs.{filename[:-3]}'
            try:
                await bot.load_extension(extension_name)
                print(f'✅ 已載入模組: {extension_name}')
            except Exception as e:
                print(f'❌ 無法載入模組 {extension_name}: {e}')

async def main():
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass