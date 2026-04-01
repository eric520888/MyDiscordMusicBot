import discord
from discord.ext import commands
import yt_dlp
import asyncio

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'nocheckcertificate': True, 
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36', 
    'headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-us,en;q=0.5',
    }
}

# [🌟 關鍵修正 1] 幫 FFmpeg 加上 User-Agent 偽裝，防止被 YouTube 瞬間 403 阻擋閃退
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -user_agent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"',
    'options': '-vn -b:a 192k', 
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

    def after_play(self, error, ctx):
        """ [🌟 關鍵修正 2] 捕捉並印出 FFmpeg 隱藏的錯誤，以後就不會死得不明不白 """
        if error:
            print(f"⚠️ [音樂播放異常] FFmpeg 發生錯誤: {error}")
        self.bot.loop.create_task(self.check_queue(ctx))

    async def check_queue(self, ctx):
        await asyncio.sleep(1) 
        
        guild_id = ctx.guild.id
        loop_state = self.loop_states.get(guild_id, 0)
        voice_client = ctx.guild.voice_client 

        if not voice_client or not voice_client.is_connected():
            return

        if loop_state == 1:
            if guild_id in self.currently_playing:
                last_info = self.currently_playing[guild_id]
                try:
                    source = self.get_source_from_info(last_info)
                    voice_client.play(source, after=lambda e: self.after_play(e, ctx))
                except Exception as e:
                    print(f"⚠️ [單曲循環異常]: {e}")
            return

        if loop_state == 2:
            last_info = self.currently_playing.get(guild_id)
            if last_info:
                self.song_queue.setdefault(guild_id, []).append(last_info)

        if guild_id in self.song_queue and self.song_queue[guild_id]:
            info = self.song_queue[guild_id].pop(0)
            self.currently_playing[guild_id] = info
            
            try:
                source = self.get_source_from_info(info)
                if loop_state != 1:
                    await ctx.send(f'▶️ 正在播放: **{info.get("title", "未知歌曲")}**')
                voice_client.play(source, after=lambda e: self.after_play(e, ctx))
            except Exception as e:
                print(f"⚠️ [播放下一首異常]: {e}")
                self.bot.loop.create_task(self.check_queue(ctx))
        else:
            self.currently_playing.pop(guild_id, None)
            await asyncio.sleep(180) 
            
            current_vc = ctx.guild.voice_client
            if current_vc and not current_vc.is_playing() and not current_vc.is_paused() and (guild_id not in self.song_queue or not self.song_queue[guild_id]):
                await current_vc.disconnect()

    # [🌟 關鍵修正 3] 獨立寫一個安全連線機制，防止連續點歌造成語音頻道進進出出
    async def ensure_voice(self, ctx):
        voice_channel = ctx.author.voice.channel
        voice_client = ctx.guild.voice_client

        if voice_client is None:
            return await voice_channel.connect(timeout=20.0, self_deaf=True)
        
        if not voice_client.is_connected():
            try:
                await voice_client.disconnect(force=True)
            except:
                pass
            return await voice_channel.connect(timeout=20.0, self_deaf=True)
            
        if voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)
            
        return voice_client

    @commands.hybrid_command(name='play', description='播放 YouTube 音樂')
    async def play(self, ctx, *, query: str):
        ww_cog = self.bot.get_cog("Werewolf")
        if ww_cog:
            game = ww_cog.get_game(ctx)
            if game and game.phase != "waiting":
                await ctx.send("🐺 **狼人殺正在進行中！** 為了保持肅殺氣氛，現在禁止點歌 🤫", ephemeral=True)
                return

        if not ctx.author.voice:
            await ctx.send("❌ 你必須先加入一個語音頻道！", ephemeral=True)
            return
        
        if ctx.interaction:
            await ctx.defer()
            
        searching_msg = await ctx.send(f"🔍 正在連線與搜尋: `{query}` ...")

        try:
            voice_client = await self.ensure_voice(ctx)
        except Exception as e:
            print(f"⚠️ [語音連線錯誤]: {e}")
            await searching_msg.edit(content=f"❌ 無法連線到語音頻道 (錯誤訊息: `{e}`)。")
            return

        try:
            loop = asyncio.get_event_loop()
            search_query = f"ytsearch1:{query}" if not query.startswith("http") else query
            data = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(YDL_OPTIONS).extract_info(search_query, download=False))
            
            info = None
            if 'entries' in data:
                if len(data['entries']) > 0:
                    info = data['entries'][0] 
            else:
                info = data 

            if not info:
                await searching_msg.edit(content="❌ 找不到相關歌曲，請嘗試其他關鍵字。")
                return

            if voice_client.is_playing() or voice_client.is_paused():
                self.song_queue.setdefault(ctx.guild.id, []).append(info)
                await searching_msg.edit(content=f'✅ **{info.get("title", "未知歌曲")}** 已加入佇列')
            else:
                self.currently_playing[ctx.guild.id] = info
                source = self.get_source_from_info(info)
                voice_client.play(source, after=lambda e: self.after_play(e, ctx))
                await searching_msg.edit(content=f'▶️ 正在播放: **{info.get("title", "未知歌曲")}**')

        except Exception as e:
            print(f"⚠️ [搜尋/播放錯誤]: {e}")
            await searching_msg.edit(content="❌ 發生錯誤！可能是 YouTube 阻擋了請求或網址無效，請稍後再試。")

    @commands.hybrid_command(name='skip', description='跳過目前歌曲')
    async def skip(self, ctx):
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
            msg = "\n".join([f"{i+1}. {info.get('title', '未知歌曲')}" for i, info in enumerate(display_list)])
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