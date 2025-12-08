import discord
from discord.ext import commands
import yt_dlp
import asyncio

# --- yt-dlp 設定 ---
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto', 
    'source_address': '0.0.0.0',
}

# --- FFmpeg 設定 ---
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.song_queue = {}        
        self.loop_states = {}       
        self.currently_playing = {} 

    def get_source_from_info(self, info):
        url = info['url']
        source = discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
        source.title = info.get('title', '未知標題')
        source.url = info.get('url')
        source.web_url = info.get('webpage_url')
        source.duration = info.get('duration')
        return source

    async def check_queue(self, ctx):
        guild_id = ctx.guild.id
        loop_state = self.loop_states.get(guild_id, 0)
        voice_client = ctx.voice_client

        if not voice_client:
            return

        if loop_state == 1:
            if guild_id in self.currently_playing:
                last_info = self.currently_playing[guild_id]
                source = self.get_source_from_info(last_info)
                ctx.voice_client.play(source, after=lambda _: self.bot.loop.create_task(self.check_queue(ctx)))
            return

        if loop_state == 2:
            last_info = self.currently_playing.get(guild_id)
            if last_info:
                self.song_queue.setdefault(guild_id, []).append(last_info)

        if guild_id in self.song_queue and self.song_queue[guild_id]:
            info = self.song_queue[guild_id].pop(0)
            self.currently_playing[guild_id] = info
            source = self.get_source_from_info(info)
            
            if loop_state != 1:
                await ctx.send(f'▶️ 正在播放: **{info["title"]}**')
            
            ctx.voice_client.play(source, after=lambda _: self.bot.loop.create_task(self.check_queue(ctx)))
        else:
            self.currently_playing.pop(guild_id, None)
            await asyncio.sleep(180) 
            if voice_client and not voice_client.is_playing() and (guild_id not in self.song_queue or not self.song_queue[guild_id]):
                await voice_client.disconnect()

    @commands.hybrid_command(name='play', description='播放 YouTube 音樂')
    async def play(self, ctx, *, query: str):
        # ---------------------------------------------------------
        # 🛑 [優先權檢查] 如果狼人殺正在進行，拒絕點歌
        # ---------------------------------------------------------
        ww_cog = self.bot.get_cog("Werewolf") # 嘗試取得狼人殺模組
        if ww_cog:
            game = ww_cog.get_game(ctx)
            # 如果遊戲存在 且 狀態不是等待中 (代表遊戲已經開始)
            if game and game.phase != "waiting":
                await ctx.send("🐺 **狼人殺正在進行中！** 為了保持肅殺氣氛，現在禁止點歌 🤫", ephemeral=True)
                return
        # ---------------------------------------------------------

        if not ctx.author.voice:
            await ctx.send("❌ 你必須先加入一個語音頻道！", ephemeral=True)
            return
        
        if ctx.interaction:
            await ctx.defer()
            
        voice_channel = ctx.author.voice.channel
        voice_client = ctx.guild.voice_client

        if not voice_client:
            voice_client = await voice_channel.connect()
        elif voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)

        searching_msg = None
        if not ctx.interaction:
            searching_msg = await ctx.send(f"🔍 正在搜尋: `{query}` ...")

        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(YDL_OPTIONS).extract_info(f"ytsearch:{query}", download=False))
            
            info = None
            if 'entries' in data:
                info = data['entries'][0] 
            else:
                info = data 

            if not info:
                msg = "❌ 找不到相關歌曲。"
                if searching_msg: await searching_msg.edit(content=msg)
                else: await ctx.send(msg)
                return

            if voice_client.is_playing() or voice_client.is_paused():
                self.song_queue.setdefault(ctx.guild.id, []).append(info)
                msg = f'✅ **{info["title"]}** 已加入佇列'
                if searching_msg: await searching_msg.edit(content=msg)
                else: await ctx.send(msg)
            else:
                self.currently_playing[ctx.guild.id] = info
                source = self.get_source_from_info(info)
                voice_client.play(source, after=lambda _: self.bot.loop.create_task(self.check_queue(ctx)))
                msg = f'▶️ 正在播放: **{info["title"]}**'
                if searching_msg: await searching_msg.edit(content=msg)
                else: await ctx.send(msg)

        except Exception as e:
            print(f"Play error: {e}")
            msg = "❌ 發生錯誤，無法播放此歌曲。"
            if searching_msg: await searching_msg.edit(content=msg)
            else: await ctx.send(msg)

    @commands.hybrid_command(name='skip', description='跳過目前歌曲')
    async def skip(self, ctx):
        # 這裡也可以選擇性加入檢查，例如狼人殺期間也不准跳過背景音樂
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("⏭️ 已跳過。")
        else:
            await ctx.send("目前沒有音樂正在播放。", ephemeral=True)

    @commands.hybrid_command(name='pause', description='暫停')
    async def pause(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("⏸️ 已暫停")
            
    @commands.hybrid_command(name='resume', description='恢復')
    async def resume(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("▶️ 繼續播放")

    @commands.hybrid_command(name='stop', description='停止並清空佇列')
    async def stop(self, ctx):
        # 為了避免有人誤觸 stop 把狼人殺 BGM 關掉，也可以加上檢查
        ww_cog = self.bot.get_cog("Werewolf")
        if ww_cog:
            game = ww_cog.get_game(ctx)
            if game and game.phase != "waiting":
                await ctx.send("🐺 狼人殺進行中，無法停止背景音樂！", ephemeral=True)
                return

        if ctx.voice_client:
            self.song_queue[ctx.guild.id] = []
            ctx.voice_client.stop()
            await ctx.send("⏹️ 已停止並清空佇列。")

    @commands.hybrid_command(name='queue', description='查看播放清單')
    async def queue(self, ctx):
        q = self.song_queue.get(ctx.guild.id, [])
        if not q:
            await ctx.send("佇列是空的。")
        else:
            display_list = q[:10]
            msg = "\n".join([f"{i+1}. {info['title']}" for i, info in enumerate(display_list)])
            if len(q) > 10: msg += f"\n... 以及其他 {len(q)-10} 首"
            
            embed = discord.Embed(title="🎵 播放佇列", description=msg, color=discord.Color.blue())
            await ctx.send(embed=embed)

    @commands.hybrid_command(name='loop', description='切換循環模式')
    async def loop(self, ctx):
        guild_id = ctx.guild.id
        self.loop_states[guild_id] = (self.loop_states.get(guild_id, 0) + 1) % 3
        states = ["關閉", "單曲循環", "佇列循環"]
        await ctx.send(f"🔁 循環模式: {states[self.loop_states[guild_id]]}")

    @commands.hybrid_command(name='leave', description='讓機器人離開')
    async def leave(self, ctx):
        # 防止有人把機器人踢出語音頻道導致狼人殺沒聲音
        ww_cog = self.bot.get_cog("Werewolf")
        if ww_cog:
            game = ww_cog.get_game(ctx)
            if game and game.phase != "waiting":
                await ctx.send("🐺 狼人殺還沒結束，我不能走！", ephemeral=True)
                return

        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.send("掰掰！")
        else:
            await ctx.send("我不在語音頻道中。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Music(bot))