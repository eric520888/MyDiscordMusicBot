import discord
from discord.ext import commands
import yt_dlp
import asyncio

# yt-dlp 和 FFmpeg 設定維持不變
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

def convert_to_seconds(time_str):
    try:
        parts = list(map(int, time_str.split(':')))
        if len(parts) == 1: return parts[0]
        if len(parts) == 2: return parts[0] * 60 + parts[1]
        if len(parts) == 3: return parts[0] * 3600 + parts[1] * 60 + parts[2]
    except ValueError:
        return 0
    return 0

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 將原本的全域變數改為類別屬性
        self.song_queue = {}
        self.loop_states = {}
        self.currently_playing = {}

    async def check_queue(self, ctx):
        guild_id = ctx.guild.id
        loop_state = self.loop_states.get(guild_id, 0)

        # --- 單曲循環 ---
        if loop_state == 1:
            source = self.currently_playing[guild_id]
            # 必須重新建立 source
            new_source = discord.FFmpegPCMAudio(source.original_url, **FFMPEG_OPTIONS)
            new_source.title = source.title
            new_source.original_url = source.original_url
            ctx.voice_client.play(new_source, after=lambda _: self.bot.loop.create_task(self.check_queue(ctx)))
            return

        # --- 佇列循環 ---
        if loop_state == 2:
            finished_song = self.currently_playing.get(guild_id)
            if finished_song:
                new_source = discord.FFmpegPCMAudio(finished_song.original_url, **FFMPEG_OPTIONS)
                new_source.title = finished_song.title
                new_source.original_url = finished_song.original_url
                self.song_queue.setdefault(guild_id, []).append(new_source)

        # --- 正常播放 ---
        if guild_id in self.song_queue and self.song_queue[guild_id]:
            source = self.song_queue[guild_id].pop(0)
            self.currently_playing[guild_id] = source
            ctx.voice_client.play(source, after=lambda _: self.bot.loop.create_task(self.check_queue(ctx)))
            await ctx.send(f'▶️ 正在播放: **{source.title}**')
        else:
            self.currently_playing.pop(guild_id, None)
            await asyncio.sleep(180)
            if ctx.voice_client and not ctx.voice_client.is_playing() and (guild_id not in self.song_queue or not self.song_queue[guild_id]):
                await ctx.voice_client.disconnect()

    @commands.command(name='play', help='播放音樂')
    async def play(self, ctx, *, search: str):
        if not ctx.author.voice:
            await ctx.send("你必須先加入一個語音頻道！")
            return

        # 時間解析邏輯
        parts = search.split()
        start_time = 0
        real_search = search
        if len(parts) > 1:
            potential_time = parts[-1]
            seconds = convert_to_seconds(potential_time)
            if seconds > 0 or (potential_time.isdigit() and int(potential_time) == 0):
                start_time = seconds
                real_search = " ".join(parts[:-1])

        searching_message = await ctx.send(f'🔍 正在搜尋: **{real_search}**')

        info = None
        try:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(YDL_OPTIONS).extract_info(f"ytsearch:{real_search}", download=False))
            if "entries" in info:
                info = info['entries'][0]
        except Exception as e:
            await searching_message.edit(content="❌ 搜尋失敗。")
            print(e)
            return

        url = info['url']
        title = info['title']
        
        current_ffmpeg_options = FFMPEG_OPTIONS.copy()
        if start_time > 0:
            current_ffmpeg_options['before_options'] += f' -ss {start_time}'

        source = discord.FFmpegPCMAudio(url, **current_ffmpeg_options)
        source.original_url = url
        source.title = title

        voice_channel = ctx.author.voice.channel
        voice_client = ctx.guild.voice_client

        if not voice_client:
            await voice_channel.connect()
            voice_client = ctx.guild.voice_client
        elif voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)

        if voice_client.is_playing() or voice_client.is_paused():
            self.song_queue.setdefault(ctx.guild.id, []).append(source)
            await searching_message.edit(content=f'✅ **{title}** 已加入佇列')
        else:
            self.currently_playing[ctx.guild.id] = source
            voice_client.play(source, after=lambda e: self.bot.loop.create_task(self.check_queue(ctx)))
            await searching_message.edit(content=f'▶️ 正在播放: **{title}**')

    @commands.command(name='pause', help='暫停目前播放的音樂')
    async def pause(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("⏸️ 音樂已暫停。")
        else:
            await ctx.send("目前沒有音樂正在播放。")

    @commands.command(name='resume', help='恢復播放音樂')
    async def resume(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("▶️ 音樂已恢復播放。")
        else:
            await ctx.send("音樂未被暫停。")

    @commands.command(name='skip', help='跳過目前歌曲')
    async def skip(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("⏭️ 已跳過。")

    @commands.command(name='queue', help='顯示目前的播放佇列')
    async def queue(self, ctx):
        if ctx.guild.id in self.song_queue and self.song_queue[ctx.guild.id]:
            queue_list = "\n".join([
                f"{i+1}. {source.title}"
                for i, source in enumerate(self.song_queue[ctx.guild.id])
            ])
            embed = discord.Embed(title="🎵 播放佇列",
                                  description=queue_list,
                                  color=discord.Color.blue())
            await ctx.send(embed=embed)
        else:
            await ctx.send("播放佇列是空的。")

    @commands.command(name='stop', help='停止播放並清空佇列')
    async def stop(self, ctx):
        if ctx.voice_client:
            self.song_queue[ctx.guild.id] = []
            ctx.voice_client.stop()
            await ctx.send("⏹️ 已停止。")

    @commands.command(name='leave', help='讓機器人離開語音頻道')
    async def leave(self, ctx):
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.send("掰掰！")
        else:
            await ctx.send("我不在任何語音頻道中。")

    @commands.command(name='loop', help='切換循環模式')
    async def loop(self, ctx):
        guild_id = ctx.guild.id
        self.loop_states[guild_id] = (self.loop_states.get(guild_id, 0) + 1) % 3
        states = ["關閉", "單曲循環", "佇列循環"]
        await ctx.send(f"🔁 循環模式: {states[self.loop_states[guild_id]]}")

# 這是必須的 setup 函式，用來讓 main.py 載入這個 Cog
async def setup(bot):
    await bot.add_cog(Music(bot))