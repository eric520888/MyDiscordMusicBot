import discord
from discord.ext import commands
import google.generativeai as genai
import os
import asyncio

# --- 設定 ---
# 請確保你的環境變數中有 'GEMINI_API_KEY'
# 獲取金鑰: https://aistudio.google.com/app/apikey
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# 模型名稱 (如果未來有 gemini-2.5-flash，請在此更改)
# 目前穩定快速版通常是 gemini-1.5-flash
MODEL_NAME = "gemini-2.5-flash"

class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.configure_ai()
        # 對話歷史紀錄 (簡單版：只保留最近的對話以節省 token，這裡先做單次回應)
        # 若要做連續對話，需要建立一個字典來存每個頻道的 history

    def configure_ai(self):
        if not GEMINI_API_KEY:
            print("⚠️ 警告: 未偵測到 GEMINI_API_KEY，AI 功能將無法使用。")
            return
        
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            self.model = genai.GenerativeModel(MODEL_NAME)
            print(f"✅ Gemini AI ({MODEL_NAME}) 已載入")
        except Exception as e:
            print(f"❌ AI 初始化失敗: {e}")

    @commands.Cog.listener()
    async def on_message(self, message):
        # 1. 忽略機器人自己的訊息
        if message.author == self.bot.user:
            return

        # 2. 檢查機器人是否被 Tag (提及)
        # self.bot.user.mentioned_in(message) 會檢查訊息中是否有 @機器人
        # 同時避免 @everyone 或 @here 觸發
        if self.bot.user in message.mentions and not message.mention_everyone:
            
            # 檢查是否有 API Key
            if not hasattr(self, 'model'):
                await message.channel.send("❌ 腦袋空空 (未設定 API Key)")
                return

            # 顯示「正在輸入...」的狀態
            async with message.channel.typing():
                try:
                    # 3. 清理訊息內容
                    # 把 <@123456789> 這種 tag 字串從內容中移除，只留下使用者的問題
                    clean_content = message.content.replace(f'<@!{self.bot.user.id}>', '') \
                                                   .replace(f'<@{self.bot.user.id}>', '') \
                                                   .strip()
                    
                    if not clean_content:
                        await message.channel.send("找我什麼事？(請在 Tag 後面輸入問題)")
                        return

                    # 4. 呼叫 Gemini API
                    # 設定一些簡單的 Prompt 讓他知道自己是誰
                    prompt = f"你是 Discord 機器人，請用繁體中文簡短回答以下問題：{clean_content}"
                    
                    response = await self.model.generate_content_async(prompt)
                    response_text = response.text

                    # 5. 處理 Discord 訊息長度限制 (2000字)
                    if len(response_text) > 2000:
                        # 如果太長，拆分傳送
                        chunks = [response_text[i:i+1900] for i in range(0, len(response_text), 1900)]
                        for chunk in chunks:
                            await message.channel.send(chunk)
                    else:
                        await message.reply(response_text)

                except Exception as e:
                    print(f"AI 生成錯誤: {e}")
                    await message.channel.send("😵 腦袋打結了，請稍後再試。")

async def setup(bot):
    await bot.add_cog(AIChat(bot))