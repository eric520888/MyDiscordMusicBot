import discord
import os
import asyncio
from .const import SOUND_FOLDER

class AudioManager:
    @staticmethod
    async def mute_all(ctx, players, mute=True):
        """將所有遊戲玩家靜音或解除靜音"""
        # 使用 asyncio.gather 並行處理，速度會比 for loop 快
        tasks = []
        for p in players:
            try:
                # 重新抓取 member 以獲取最新語音狀態
                member = ctx.guild.get_member(p.id)
                if member and member.voice:
                    tasks.append(member.edit(mute=mute))
            except:
                pass
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    async def play_mixed(ctx, bgm_file, voice_file=None):
        """混音播放"""
        vc = ctx.guild.voice_client
        if not vc: return

        bgm_path = os.path.join(SOUND_FOLDER, bgm_file)
        if not os.path.exists(bgm_path):
            print(f"❌ 找不到 BGM: {bgm_path}")
            return

        if vc.is_playing():
            vc.stop()

        # 設定 FFmpeg 參數
        opts = '-vn'
        
        # 如果有語音，進行混音
        if voice_file:
            voice_path = os.path.join(SOUND_FOLDER, voice_file)
            if os.path.exists(voice_path):
                # BGM 音量 0.4 (背景), Voice 音量 1.5 (前景)
                complex_filter = f'[0:a]volume=0.4[bg];[1:a]volume=1.5[vc];[bg][vc]amix=inputs=2:duration=first:dropout_transition=2'
                # Input 0 是 BGM (循環), Input 1 是 Voice (單次)
                before = f'-stream_loop -1 -i "{bgm_path}" -filter_complex "{complex_filter}"'
                
                try:
                    source = discord.FFmpegPCMAudio(voice_path, before_options=before, options=opts)
                    vc.play(source)
                    return
                except Exception as e:
                    print(f"混音錯誤: {e}")

        # 如果沒語音或混音失敗，只播 BGM
        try:
            source = discord.FFmpegPCMAudio(bgm_path, before_options="-stream_loop -1", options=opts)
            vc.play(source)
        except Exception as e:
            print(f"播放錯誤: {e}")

    @staticmethod
    async def stop(ctx):
        """停止播放"""
        vc = ctx.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()