# 🤖 Discord 多功能機器人 (Music + Werewolf + AI)

![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)
![Discord.py](https://img.shields.io/badge/Discord.py-2.0%2B-5865F2?logo=discord&logoColor=white)
![Gemini AI](https://img.shields.io/badge/AI-Gemini%201.5%20Flash-4285F4?logo=google&logoColor=white)

這是一個基於 `discord.py` 開發的模組化 Discord 機器人，整合了 **音樂播放**、**狼人殺遊戲** 以及 **Google Gemini AI 對話** 功能。旨在為伺服器提供全方位的娛樂體驗。

---

## ✨ 主要功能

### 🎵 音樂系統 (Music)
支援從 YouTube 播放音樂，具備完整的佇列管理與多種循環模式。

| 指令 | 說明 | 範例 |
| :--- | :--- | :--- |
| `!play <關鍵字/網址> [時間]` | 播放音樂 (支援指定開始時間) | `!play song 1:30` |
| `!pause` / `!resume` | 暫停 / 恢復播放 | |
| `!skip` | 跳過目前歌曲 | |
| `!stop` | 停止播放並清空佇列 | |
| `!queue` | 查看目前的播放清單 | |
| `!loop` | 切換循環模式 | 關閉 ➡ 單曲 ➡ 佇列 |

### 🐺 狼人殺 (Werewolf) (Bug修復中......)
內建互動式按鈕介面的狼人殺遊戲，全自動化主持流程，無需人工上帝。

* **大廳系統**：使用 `!ww_create` 建立帶有 UI 按鈕 (加入/退出/開始) 的圖形化介面。
* **身分分配**：自動分配 **🐺 狼人**、**🔮 預言家**、**👱 村民**，並透過私訊 (DM) 通知身分。
* **日夜循環**：
    * 🌑 **夜晚**：狼人私訊 `!kill <ID>` 殺人，預言家私訊 `!check <ID>` 查驗。
    * ☀️ **白天**：公開頻道討論，使用 `!vote @玩家` 進行投票處決。
* **自動判定**：系統自動判斷好人或狼人陣營獲勝條件。

### 🧠 AI 對話 (Chat)
整合 Google Gemini API，讓機器人擁有智慧對話能力。

* **Tag 即回**：在任何頻道 `@機器人` 並輸入文字，即可觸發回應。
* **智慧模型**：採用 **Google Gemini 1.5 Flash** 模型，反應快速且支援繁體中文語意理解。

---

## 🛠️ 安裝與執行

### 1. 環境需求
* [Python 3.8](https://www.python.org/) 或以上
* **FFmpeg** (由系統環境變數呼叫，用於音樂播放)

### 2. 安裝依賴套件
請確保目錄下有 `requirements.txt`，然後執行：
### 🛠️ 安裝與執行

```bash
├── main.py              # 主程式 (負責載入 Cogs 與啟動)
├── requirements.txt     # 套件清單
├── .env                 # 環境變數 (請勿上傳到 GitHub)
└── cogs/                # 功能模組資料夾
    ├── music.py         # 音樂功能
    ├── werewolf.py      # 狼人殺功能
    ├── chat.py          # AI 對話功能
    └── general.py       # 一般指令 (Ping, Info 等)
```

```bash
 pip install -r requirements.txt
```

### 3. 設定環境變數
請在目錄下建立 `.env` 檔案，並填入以下環境變數：
```bash
# Discord 機器人 Token (從 Discord Developer Portal 取得)
DISCORD_BOT_TOKEN=你的_Discord_Bot_Token

# Google Gemini API Key (從 Google AI Studio 取得)
GEMINI_API_KEY=你的_Gemini_API_Key
```

### 4. 執行機器人
```bash
python main.py
```

---


## 📚 文件
* [Discord.py 官方文件](https://discordpy.readthedocs.io/)
* [Google Gemini API 文件](https://cloud.google.com/ai-platform/gemini)