🤖 Discord 多功能機器人 (Music + Werewolf + AI)

這是一個基於 discord.py 開發的模組化 Discord 機器人，整合了 音樂播放、狼人殺遊戲 以及 Google Gemini AI 對話 功能。

✨ 主要功能

🎵 音樂系統 (Music)

支援從 YouTube 播放音樂，具備完整的佇列與循環功能。

!play <關鍵字/網址> [時間]：播放音樂 (支援指定開始時間，如 !play song 1:30)。

!pause / !resume：暫停/恢復播放。

!skip：跳過目前歌曲。

!stop：停止播放並清空佇列。

!queue：查看目前的播放清單。

!loop：切換循環模式 (關閉 -> 單曲循環 -> 佇列循環)。

🐺 狼人殺 (Werewolf)

內建互動式按鈕介面的狼人殺遊戲，自動化主持流程。

大廳系統：使用 !ww_create 建立帶有按鈕 (加入/退出/開始) 的圖形化介面。

身分分配：自動分配 🐺 狼人、🔮 預言家、村民，並透過私訊 (DM) 通知。

日夜循環：

夜晚：狼人私訊 !kill <ID> 殺人，預言家私訊 !check <ID> 查驗。

白天：公開討論，使用 !vote @玩家 進行投票處決。

自動判定：自動判斷好人或狼人陣營獲勝。

🧠 AI 對話 (Chat)

整合 Google Gemini API (Flash 模型)，讓機器人擁有智慧對話能力。

Tag 即回：只要在頻道中 @機器人 並輸入文字，機器人就會透過 AI 回覆你。

智慧回應：使用 Google Gemini 1.5 Flash 模型，反應快速且支援繁體中文。

🛠️ 安裝與執行

1. 環境需求

Python 3.8 或以上

FFmpeg (用於音樂播放功能，需加入系統環境變數或安裝於伺服器)

2. 安裝依賴套件

請確保目錄下有 requirements.txt，然後執行：

pip install -r requirements.txt


3. 設定環境變數 (.env)

在專案根目錄建立一個 .env 檔案（或在雲端平台的 Environment Variables 設定），填入以下資訊：

# Discord 機器人 Token (從 Discord Developer Portal 取得)
DISCORD_BOT_TOKEN=你的_Discord_Bot_Token

# Google Gemini API Key (從 Google AI Studio 取得)
GEMINI_API_KEY=你的_Gemini_API_Key


4. 啟動機器人

python main.py


📂 專案結構

.
├── main.py              # 主程式 (負責載入 Cogs 與啟動)
├── requirements.txt     # 套件清單
├── .env                 # 環境變數 (不要上傳到 GitHub)
└── cogs/                # 功能模組資料夾
    ├── music.py         # 音樂功能
    ├── werewolf.py      # 狼人殺功能
    ├── chat.py          # AI 對話功能
    └── general.py       # 一般指令 (Ping, Info 等)


🚀 部署注意事項 (Railway / Render / Heroku)

如果你是部署到雲端平台（如 GitHub 連結 Railway）：

確保 requirements.txt 內包含 python-dotenv 與 PyNaCl。

確保平台已安裝 FFmpeg (Railway 通常需額外設定 Dockerfile 或使用包含 FFmpeg 的 Nixpacks)。

在平台的 Settings -> Variables 中填入 DISCORD_BOT_TOKEN 和 GEMINI_API_KEY。

📝 開發者

Author: Eric

Framework: discord.py

AI Model: Google Gemini 2.5 Flash