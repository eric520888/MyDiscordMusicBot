import discord
import os
import asyncio
from discord.ext import commands
from dotenv import load_dotenv

# 1. 載入環境變數
load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# 2. 處理 Owner IDs (移到最上方處理)
owner_ids_str = os.getenv('OWNER_IDS')
OWNER_IDS = set(map(int, owner_ids_str.split(','))) if owner_ids_str else set()

# 3. 機器人設定 (只定義這一次！)
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix='!', 
    intents=intents,
    owner_ids=OWNER_IDS  # 在這裡直接傳入 owner_ids
    help_command=None  # 關閉預設幫助指令
)

# --- Opus 載入邏輯 (Linux 環境需要，若為 Windows 開發可忽略) ---
if not discord.opus.is_loaded():
    try:
        discord.opus.load_opus('libopus.so.0')
    except discord.opus.OpusError:
        print("Opus library could not be loaded.")

@bot.event
async def on_ready():
    print(f'主程式啟動成功：登入身分 {bot.user}')
    print(f'Owner IDs: {bot.owner_ids}') # 檢查一下是否有成功讀取
    await bot.change_presence(activity=discord.Game(name="/help | 多功能機器人"))
    
    # --- 同步斜線指令 ---
    try:
        synced = await bot.tree.sync()
        print(f"✅ 已同步 {len(synced)} 個斜線指令 (Slash Commands)")
    except Exception as e:
        print(f"❌ 同步指令失敗: {e}")

async def load_extensions():
    """自動讀取 cogs 資料夾下的所有 .py 檔案並載入"""
    # 確保 cogs 資料夾存在，避免報錯
    if not os.path.exists('./cogs'):
        print("⚠️ 警告: 找不到 'cogs' 資料夾")
        return

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