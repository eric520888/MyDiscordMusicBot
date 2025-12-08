import discord
from discord.ext import commands
import google.generativeai as genai
import os

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
MODEL_NAME = "gemini-1.5-flash"

class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.configure_ai()

    def configure_ai(self):
        if not GEMINI_API_KEY:
            print("⚠️ 警告: 未偵測到 GEMINI_API_KEY")
            return
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            self.model = genai.GenerativeModel(MODEL_NAME)
        except Exception as e:
            print(f"❌ AI 初始化失敗: {e}")

    async def generate_response(self, prompt):
        if not hasattr(self, 'model'): return "腦袋空空 (未設定 API Key)"
        try:
            response = await self.model.generate_content_async(prompt)
            return response.text
        except Exception as e:
            return f"生成錯誤: {e}"

    # --- 1. 斜線指令版本 ---
    @commands.hybrid_command(name='ask', description='詢問 AI 機器人問題')
    async def ask(self, ctx, *, question: str):
        await ctx.defer() # 因為 AI 生成比較慢，先轉圈圈
        response = await self.generate_response(question)
        if len(response) > 2000:
            await ctx.send(response[:2000] + "...")
        else:
            await ctx.send(response)

    # --- 2. 傳統 Tag 觸發版本 ---
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return
        if self.bot.user in message.mentions and not message.mention_everyone:
            async with message.channel.typing():
                clean_content = message.content.replace(f'<@!{self.bot.user.id}>', '').replace(f'<@{self.bot.user.id}>', '').strip()
                if not clean_content:
                    await message.channel.send("找我什麼事？")
                    return
                response = await self.generate_response(clean_content)
                if len(response) > 2000:
                    await message.channel.send(response[:2000])
                else:
                    await message.reply(response)

async def setup(bot):
    await bot.add_cog(AIChat(bot))