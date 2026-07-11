import asyncio
import logging
import os
import sys
import traceback

import discord
from discord.ext import commands
from dotenv import load_dotenv


# Traditional Windows code pages cannot encode emoji used by status messages.
# Keep the local console readable without letting one print() abort cog loading.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(errors="replace")

load_dotenv()

log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_name, logging.INFO)
logging.basicConfig(
    level=log_level,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
# Voice handshake/reconnect messages are essential when diagnosing UDP, DAVE,
# permissions, or Discord voice close-code failures.
logging.getLogger("discord.voice_state").setLevel(logging.INFO)

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
owner_ids_value = os.getenv("OWNER_IDS", "")
OWNER_IDS = {
    int(owner_id.strip())
    for owner_id in owner_ids_value.split(",")
    if owner_id.strip()
}

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    owner_ids=OWNER_IDS,
    help_command=None,
)


@bot.event
async def on_ready() -> None:
    print(f"機器人啟動成功：登入身分 {bot.user}")
    print(f"Owner IDs: {bot.owner_ids}")
    await bot.change_presence(activity=discord.Game(name="/help | 多功能機器人"))

    if getattr(bot, "_application_commands_synced", False):
        return

    try:
        print("📋 正在同步指令...")
        synced = await bot.tree.sync()
        bot._application_commands_synced = True
        print(f"✅ 已同步 {len(synced)} 個斜線指令")
        for command in synced:
            print(f"  ✓ /{command.name}")
    except Exception:
        logging.getLogger(__name__).exception("同步斜線指令失敗")


async def load_extensions() -> None:
    """自動讀取 cogs 資料夾下的所有 .py 檔案並載入。"""
    if not os.path.exists("./cogs"):
        print("⚠️ 警告：找不到 'cogs' 資料夾")
        return

    print("📂 開始掃描 cogs 資料夾...")
    loaded_count = 0
    failed_count = 0

    for filename in os.listdir("./cogs"):
        full_path = os.path.join("./cogs", filename)
        if os.path.isdir(full_path):
            print(f"   [跳過資料夾] {filename}")
            continue

        if not filename.endswith(".py"):
            continue

        extension_name = f"cogs.{filename[:-3]}"
        try:
            await bot.load_extension(extension_name)
            print(f"   ✅ 已載入模組：{extension_name}")
            loaded_count += 1
        except Exception as error:
            print(f"   ❌ 無法載入模組 {extension_name}")
            print(f"      錯誤類型：{type(error).__name__}")
            print(f"      錯誤詳情：{error}")
            traceback.print_exc()
            print("-" * 30)
            failed_count += 1

    print(f"\n📊 載入結果：{loaded_count} 成功，{failed_count} 失敗")
    print(f"🔧 已載入的 Cogs：{list(bot.cogs.keys())}")


async def main() -> None:
    if not TOKEN:
        raise RuntimeError(
            "缺少 DISCORD_BOT_TOKEN。請複製 .env.example 為 .env，"
            "並填入剛輪替的新 Token。"
        )

    async with bot:
        await load_extensions()
        await bot.start(TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
