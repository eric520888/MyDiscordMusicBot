import discord
if not discord.opus.is_loaded():
    try:
        discord.opus.load_opus('libopus.so.0')
    except discord.opus.OpusError:
        print("Opus library could not be loaded...")
from discord.ext import commands
import yt_dlp
import asyncio
import os


# --- 設定 ---
# 從環境變數讀取 Discord Bot Token（安全方式）
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
# 機器人的指令前綴
PREFIX = '!'

# --- 機器人設定 ---
intents = discord.Intents.default()
intents.message_content = True  # 啟用訊息內容意圖
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# yt-dlp 選項
YDL_OPTIONS = {
    'format':
    'bestaudio/best',
    'noplaylist':
    True,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}

# FFmpeg 選項
FFMPEG_OPTIONS = {
    'before_options':
    '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

# 儲存歌曲佇列
song_queue = {}
# 追蹤每個伺服器的循環狀態 (0: 無循環, 1: 單曲循環, 2: 佇列循環)
loop_states = {}
# 追蹤目前正在播放的歌曲，為了單曲循環
currently_playing = {}


# 檢查佇列並播放下一首歌
# 檢查佇列並根據循環狀態播放下一首歌
async def check_queue(ctx):
    guild_id = ctx.guild.id
    # 取得目前的循環狀態，如果沒有設定過，預設為 0 (無循環)
    loop_state = loop_states.get(guild_id, 0)

    # --- 處理單曲循環 ---
    if loop_state == 1:
        # 重新播放同一首歌
        source = currently_playing[guild_id]
        # 需要重新建立 AudioSource，否則會出錯
        new_source = discord.FFmpegPCMAudio(source.original_url,
                                            **FFMPEG_OPTIONS)
        new_source.title = source.title
        new_source.original_url = source.original_url  # 把 URL 傳下去

        ctx.voice_client.play(
            new_source, after=lambda _: bot.loop.create_task(check_queue(ctx)))
        # 這次就不發訊息了，避免洗頻
        return

    # --- 處理佇列循環 ---
    if loop_state == 2:
        # 把剛剛播完的歌，再加回到佇列的最後面
        finished_song = currently_playing.get(guild_id)
        if finished_song:
            song_queue.setdefault(guild_id, []).append(finished_song)

    # --- 處理正常播放流程 (無循環 & 佇列循環的下一步) ---
    if guild_id in song_queue and song_queue[guild_id]:
        # 從佇列中取出下一首歌
        source = song_queue[guild_id].pop(0)
        currently_playing[guild_id] = source  # 更新正在播放的歌曲
        ctx.voice_client.play(
            source, after=lambda _: bot.loop.create_task(check_queue(ctx)))
        await ctx.send(f'▶️ 正在播放: **{source.title}**')
    else:
        # 佇列為空，過一段時間後自動離開
        currently_playing.pop(guild_id, None)  # 清除播放紀錄
        await asyncio.sleep(180)  # 等待 3 分鐘
        if ctx.voice_client and not ctx.voice_client.is_playing():
            await ctx.voice_client.disconnect()


# --- 指令 ---
@bot.event
async def on_ready():
    print(f'機器人 {bot.user} 已成功登入！')
    # 初始化每個伺服器的佇列
    for guild in bot.guilds:
        song_queue[guild.id] = []


@bot.command(name='play', help='播放YouTube上的音樂或將其加入佇列')
async def play(ctx, *, search: str):
    # 步驟 1: 檢查使用者是否在語音頻道
    if not ctx.author.voice:
        await ctx.send("你必須先加入一個語音頻道！")
        return

    # 步驟 2: 立刻回覆使用者，告訴他你已經在工作了，這樣就不會感覺卡住
    searching_message = await ctx.send(f'🔍 正在搜尋與準備歌曲: **{search}**')

    # 步驟 3: 【先做最慢的事】執行 yt-dlp
    info = None
    try:
        # 使用 async with 來避免阻塞，讓機器人能處理其他事件
        loop = asyncio.get_event_loop()
        # 在另一個執行緒中運行阻塞的 I/O 操作
        info = await loop.run_in_executor(
            None, lambda: yt_dlp.YoutubeDL(YDL_OPTIONS).extract_info(
                f"ytsearch:{search}" if "http" not in search else search,
                download=False))
        if "entries" in info:  # 如果是播放清單或搜尋結果，取第一個
            info = info['entries'][0]

    except Exception as e:
        await searching_message.edit(
            content="❌ 無法找到歌曲，或歌曲格式有問題 (例如需要會員)。請試試別的關鍵字或網址。")
        print(e)
        return

    url = info['url']
    title = info['title']
    source = discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
    source.original_url = url
    source.title = title

    # 步驟 4: 【再做最快的事】連線到語音頻道
    voice_channel = ctx.author.voice.channel
    voice_client = ctx.guild.voice_client  # 使用 ctx.guild.voice_client 獲取最新狀態

    if not voice_client:
        try:
            voice_client = await voice_channel.connect(timeout=30.0)
        except asyncio.TimeoutError:
            await searching_message.edit(content="❌ 連接語音頻道超時，請再試一次。")
            return
    elif voice_client.channel != voice_channel:
        await voice_client.move_to(voice_channel)

    # 步驟 5: 播放或加入佇列
    if voice_client.is_playing() or voice_client.is_paused():
        song_queue.setdefault(ctx.guild.id, []).append(source)
        await searching_message.edit(content=f'✅ **{title}** 已加入播放佇列！')
    else:
        currently_playing[ctx.guild.id] = source
        voice_client.play(
            source, after=lambda e: bot.loop.create_task(check_queue(ctx)))
        # 編輯一開始發送的訊息，而不是發送新訊息，使用者體驗更好！
        await searching_message.edit(content=f'▶️ 正在播放: **{title}**')


@play.error
async def play_error(ctx, error):
    # 檢查是不是「缺少參數」的錯誤
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            "❌ 指令錯誤！請在 `!play` 後面加上歌曲名稱或網址。\n例如：`!play Never Gonna Give You Up`"
        )
    else:
        # 如果是其他未知的錯誤，在後台印出來方便除錯
        print(f"指令 'play' 發生未預期的錯誤: {error}")
        await ctx.send(f"播放時發生了未知的錯誤，請檢查後台日誌。")


@bot.command(name='pause', help='暫停目前播放的音樂')
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ 音樂已暫停。")
    else:
        await ctx.send("目前沒有音樂正在播放。")


@bot.command(name='loop', help='切換循環模式 (無 -> 單曲 -> 佇列)')
async def loop(ctx):
    guild_id = ctx.guild.id

    # 如果伺服器是第一次使用此功能，先初始化狀態
    if guild_id not in loop_states:
        loop_states[guild_id] = 0

    # 在三種模式之間循環切換 (0 -> 1 -> 2 -> 0)
    loop_states[guild_id] = (loop_states[guild_id] + 1) % 3

    # 根據目前的狀態回覆訊息
    current_state = loop_states[guild_id]
    if current_state == 0:
        await ctx.send("🔁 **循環模式已關閉**")
    elif current_state == 1:
        await ctx.send("🔂 **已設定為單曲循環**")
    elif current_state == 2:
        await ctx.send("🔁 **已設定為佇列循環**")


@bot.command(name='resume', help='恢復播放音樂')
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ 音樂已恢復播放。")
    else:
        await ctx.send("音樂未被暫停。")


@bot.command(name='skip', help='跳過目前歌曲')
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ 已跳過目前歌曲。")
        # stop() 會觸發 after 回調，自動播放下一首
    else:
        await ctx.send("目前沒有音樂正在播放。")


@bot.command(name='queue', help='顯示目前的播放佇列')
async def queue(ctx):
    if ctx.guild.id in song_queue and song_queue[ctx.guild.id]:
        queue_list = "\n".join([
            f"{i+1}. {source.title}"
            for i, source in enumerate(song_queue[ctx.guild.id])
        ])
        embed = discord.Embed(title="🎵 播放佇列",
                              description=queue_list,
                              color=discord.Color.blue())
        await ctx.send(embed=embed)
    else:
        await ctx.send("播放佇列是空的。")


@bot.command(name='stop', help='停止播放並清空佇列')
async def stop(ctx):
    if ctx.voice_client:
        # 清空佇列
        if ctx.guild.id in song_queue:
            song_queue[ctx.guild.id].clear()
        # 停止播放
        ctx.voice_client.stop()
        await ctx.send("⏹️ 播放已停止，佇列已清空。")


@bot.command(name='leave', help='讓機器人離開語音頻道')
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("掰掰！")
    else:
        await ctx.send("我不在任何語音頻道中。")


# --- 執行機器人 ---
if __name__ == "__main__":
    bot.run(TOKEN)
