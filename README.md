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

### 🐺 狼人殺 (Werewolf)
內建互動式按鈕介面的狼人殺遊戲，全自動化主持流程，無需人工上帝。

* **大廳系統**：使用 `/ww_create` 建立圖形化大廳，支援 **自動配置**、**標準板**、**狼王板**、**奇跡板** 等多種板子。
* **身分分配**：
    * 🐺 **狼人陣營**：狼人、狼王
    * 🔮 **神職陣營**：預言家、女巫、獵人、奇跡商人
    * 👱 **村民陣營**：村民
* **全按鈕操作**：
    * 🌑 **夜晚**：狼人透過按鈕討論戰術與殺人；神職透過下拉選單發動技能 (查驗、救藥/毒藥、給予技能)。
    * ☀️ **白天**：公開頻道討論，使用按鈕介面進行投票，支援平票處理與遺言/開槍環節。
    * 🏆 **復盤系統**：遊戲結束後自動顯示復盤介面，可查看 **遊戲總覽**、**身分揭曉** 以及 **每一回合的詳細過程**。
* **自動判定**：系統即時判斷陣營勝利條件。

### 未來更新

* **更多身分** 預計會有更多身分玩法 (如守衛、白痴等)。
* **遊戲優化** : 狼人殺警徽制。
* **多語言系統** : 未來會加入多語言系統請耐心等候。
## 若對狼人殺系統有興趣，可以協助貢獻開發或聯絡狐狸鬆餅ovo


### 🧠 AI 對話 (Chat)
整合 Google Gemini API，讓機器人擁有智慧對話能力。

* **Tag 即回**：在任何頻道 `@機器人` 並輸入文字，即可觸發回應。
* **智慧模型**：採用 **Google Gemini 2.5 Flash** 模型，反應快速且支援繁體中文語意理解。

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
    ├── werewolf_bot.py  # 狼人殺主程式
    ├── werewolf_system/ # 狼人殺核心系統 (遊戲邏輯/身分/技能/UI)
    ├── chat.py          # AI 對話功能
    ├── custom_help.py   # 自定義 Help 指令
    └── General.py       # 一般指令 (Ping, Info 等)
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

### Owner / 開發者指令

* 本機器人包含少量僅供 bot 擁有者使用的開發與維護指令（例如遊戲強制結束、重載配置、同步指令樹等）。
* 這些指令只會影響狼人殺遊戲本身的狀態，不會進行伺服器層級的管理操作（如 ban/kick）。

### 版權

## License

本專案以 **AGPL-3.0** 授權。

這代表：
* 任何人可以自由使用、修改、部署本專案的程式碼。
* 若以本專案為基礎進行修改，並將其部署為公開可連線使用的服務（例如 Discord Bot 伺服器），則必須公開其對應的原始碼。


### 額外須知
請注意，本專案中包含的以下檔案 **不在** 狐狸鬆餅的版權範圍內：
```bash
├── sounds/
    ├── night.mp3
```
該檔案僅供測試或展示用途，**請使用者務必自行更換為合法授權的音效檔案**，以免侵犯第三方權利。