import discord
import os
import asyncio
from discord.ext import commands
from dotenv import load_dotenv

# 1. 載入環境變數
load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# 2. 處理 Owner IDs
owner_ids_str = os.getenv('OWNER_IDS')
OWNER_IDS = set(map(int, owner_ids_str.split(','))) if owner_ids_str else set()

# 3. 機器人設定
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix='!', 
    intents=intents,
    owner_ids=OWNER_IDS,
    help_command=None
)

# --- Opus 載入邏輯 ---
if not discord.opus.is_loaded():
    try:
        discord.opus.load_opus('libopus.so.0')
    except discord.opus.OpusError:
        print("Opus library could not be loaded.")

@bot.event
async def on_ready():
    print(f'機器人啟動成功：登入身分 {bot.user}')
    print(f'Owner IDs: {bot.owner_ids}')
    await bot.change_presence(activity=discord.Game(name="/help | 多功能機器人"))
    
    # 同步指令
    try:
        print("📋 正在同步指令...")
        synced = await bot.tree.sync()
        print(f"✅ 已同步 {len(synced)} 個斜線指令")
        for cmd in synced:
            print(f"  ✓ /{cmd.name}")
    except Exception as e:
        print(f"❌ 同步指令失敗: {e}")

async def load_extensions():
    """自動讀取 cogs 資料夾下的所有 .py 檔案並載入"""
    if not os.path.exists('./cogs'):
        print("⚠️ 警告: 找不到 'cogs' 資料夾")
        return

    print("📂 開始掃描 cogs 資料夾...") 

    for filename in os.listdir('./cogs'):
        # 排除 __pycache__ 資料夾
        if filename == "__pycache__" or os.path.isdir(os.path.join('./cogs', filename)):
            continue

        print(f"   -> 發現檔案: {filename}") 

        if filename.endswith('.py'):
            extension_name = f'cogs.{filename[:-3]}'
            try:
                await bot.load_extension(extension_name)
                print(f'   ✅ 已載入模組: {extension_name}')
            except Exception as e:
                # 這裡就是抓出兇手的關鍵
                print(f'   ❌ 無法載入模組 {extension_name}')
                print(f'      錯誤詳情: {e}') 
                import traceback
                traceback.print_exc() # 印出詳細錯誤位置
                print("-" * 30)

async def main():
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass