# 專案稽核報告（階段 0）

稽核日期：2026-08-04
基準提交：`08735ea`（`main`）
工作分支：`codex/feature-discord-activity-werewolf`
稽核範圍：整個儲存庫、85 個 Git 提交快照，以及 `cogs/werewolf_system/` 的完整實作。

## 結論摘要

- 專案可以在 Windows、Python 3.12.2 的隔離環境中完整安裝；`pip check` 回報沒有相依衝突。
- `discord.py[voice]` 實際安裝版本為 2.7.1，與 `requirements.txt` 和 README 一致。
- 所有 Python 檔案均可編譯；目前 48 項測試全部通過。
- 5 個 Cog（AIChat、CustomHelp、General、Music、Werewolf）均可在不登入 Discord 的情況下成功載入。
- 未提供真正 Token 時，`main.py` 會在連線前以 `RuntimeError` 安全停止。因此本次沒有登入 Discord，也沒有執行線上語音／權限測試。
- 狼人殺入口是 `cogs/werewolf_bot.py` 的 `WerewolfBot` Cog；實際遊戲集中於 `cogs/werewolf_system/game.py` 的 `WerewolfGame`。
- 狼人殺目前是記憶體內、每個 guild 一局的 Bot 遊戲。它沒有可序列化房間狀態、斷線恢復、Activity 前後端或多語言系統。
- `catalog.py` 是最接近純領域資料的檔案；`game.py` 則把規則、狀態機、Discord UI、私訊、討論串、語音、計時與復盤混在同一類別中，是後續遷移的主要風險。
- 授權檔為完整 AGPL-3.0。README 明確指出 `sounds/night.mp3` 不在作者版權範圍，僅供展示，正式發布前必須更換或補齊可驗證授權。
- 以常見憑證格式掃描目前樹和全部 85 個提交快照，沒有發現實際 Token、API key、私鑰或敏感檔名；只有 `.env.example` 的示範值和 `os.getenv(...)` 程式敘述命中一般指派規則。

## 儲存庫概況

| 項目 | 結果 |
|---|---|
| 遠端 | `https://github.com/eric520888/MyDiscordMusicBot.git` |
| 預設分支 | `main` |
| 稽核分支 | `codex/feature-discord-activity-werewolf` |
| 追蹤檔案 | 25 |
| Git 提交 | 85 |
| Git 作者身分 | 2 |
| Python 最低版本 | README：3.10+；Docker：3.11；本次驗證：3.12.2 |
| 狼人殺程式入口 | `cogs/werewolf_bot.py:18` 的 `WerewolfBot` |
| 狼人殺遊戲入口 | `cogs/werewolf_system/game.py:27` 的 `WerewolfGame` |
| 部署入口 | `main.py:104` 的 `main()`；Docker `CMD ["python", "main.py"]` |
| 現有測試 | `test_werewolf.py`、`test_music.py` |
| 授權 | GNU AGPL-3.0 |

### 主要檔案大小

| 檔案 | 位元組 | 判讀 |
|---|---:|---|
| `sounds/night.mp3` | 811,329 | 最大檔；未超過 1 MiB，但授權不明，README 已警告需替換 |
| `cogs/werewolf_system/game.py` | 137,252 | 3,132 行；規則與 Discord 運輸層高度混合 |
| `cogs/music.py` | 136,626 | 音樂系統；含狼人殺語音所有權整合 |
| `test_werewolf.py` | 31,299 | 46 項狼人殺回歸測試 |
| `cogs/werewolf_system/views.py` | 21,613 | 全部是 Discord View／Select／Button／Embed |
| `cogs/werewolf_system/catalog.py` | 17,606 | 角色和板型靜態資料，適合優先抽離 |

排除 `.git/` 與本次建立、且被 `.gitignore` 忽略的 `venv/` 後，沒有超過 1 MiB 的工作樹檔案。`check_result.txt` 是 0 位元組、沒有程式引用，屬疑似遺留檔；本階段依要求沒有刪除。

## 專案結構與用途

```text
main.py                         Bot 建立、Cog 自動載入、Discord 登入
cogs/
├── werewolf_bot.py             狼人殺 Cog、指令、每 guild 遊戲登錄表
├── werewolf_system/
│   ├── __init__.py             對外重新匯出 WerewolfGame 與常數
│   ├── catalog.py              陣營、57 筆角色資料、23 套官方 12 人板型
│   ├── const.py                階段、板型顯示資料、人數限制、音效路徑
│   ├── roles.py                Player、Role、46 個可建立角色類別與局內狀態
│   ├── game.py                 大廳、發牌、夜晚、白天、投票、死亡、勝負、Discord I/O
│   ├── skills.py               商人／女巫／幸運兒操作；仍直接操作 Discord UI
│   ├── views.py                Discord 按鈕、選單、Embed 與所有可見文字
│   ├── audio.py                Discord 語音靜音、BGM、旁白混音
│   └── replay.py               Discord 復盤選單與 Embed 格式化
├── music.py                    音樂播放；與狼人殺互斥並提供語音所有權切換
├── custom_help.py              顯示狼人殺指令與 23 套板型說明
├── chat.py                     Gemini 聊天
└── General.py                  一般指令
test_werewolf.py                狼人殺離線回歸測試
test_music.py                   音樂認證訊息測試
requirements.txt                Python 相依套件
Dockerfile / nixpacks.toml      目前 Bot 的部署設定
.env.example                    環境變數範例
LICENSE                         AGPL-3.0 全文
```

## 安裝與執行檢查

### 本機工具

| 工具 | 結果 |
|---|---|
| Python launcher | 可用 |
| Python | 3.12.2 |
| pip | 隔離環境中可用 |
| FFmpeg | 可用；2025-10-30 build |
| Git | 2.42.0.windows.2 |
| Docker | 未安裝，無法執行 Docker build/run 驗證 |

### 相依套件

執行：

```powershell
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m pip check
```

結果：安裝成功；`No broken requirements found.`

注意事項：

- `aiohttp`、`discord.py`、`yt-dlp` 等核心套件有固定版本。
- `python-dotenv`、`google-generativeai`、`gspread`、`oauth2client` 沒有固定版本，重建環境的結果不完全可重現。
- 載入 `cogs/chat.py` 時，套件本身警告 `google.generativeai` 已停止支援，建議未來改用 `google.genai`。這不是階段 0–1 的修改範圍。
- `requirements.txt` 沒有分離 Bot 執行相依與開發／測試相依；目前測試只用標準函式庫 `unittest`。

### Bot 啟動能力

離線載入檢查：

```powershell
.\venv\Scripts\python.exe -c "import asyncio, main; asyncio.run(main.load_extensions())"
```

結果：5 個 Cog 成功、0 個失敗；狼人殺 Cog 可正常匯入與註冊。

完整入口檢查：

```powershell
.\venv\Scripts\python.exe main.py
```

結果：結束碼 1，原因是缺少 `DISCORD_BOT_TOKEN`；失敗發生在 `bot.start()` 前，符合安全預期。因本次不得使用或要求真正 Token，以下項目尚未線上驗證：

- Discord Gateway 登入與斜線指令同步。
- 建立私人討論串與成員加入。
- 伺服器靜音權限與恢復。
- 語音頻道連線及 FFmpeg 實際播放。
- 私訊無法傳送時的 Discord 真實錯誤行為。

## 語法與測試結果

執行：

```powershell
.\venv\Scripts\python.exe -m compileall -q . -x "(^|[\\/])venv([\\/]|$)"
.\venv\Scripts\python.exe -m unittest discover -v
```

結果：

- 語法／bytecode 編譯：通過。
- 測試：48 通過、0 失敗、0 錯誤，耗時約 0.389 秒。
- 狼人殺測試：46 項。
- 音樂測試：2 項。

測試已涵蓋部分板型、人數、角色分配、目標合法性、夜晚傷害、特殊角色、權限、舊面板失效、投票／射擊流程與復盤選單上限。尚未涵蓋：

- 狀態 JSON 序列化／反序列化。
- 程序重啟、斷線重連與重送去重。
- 多語言、角色內部 ID、WebSocket 或私密投影。
- 可持久化計時器、多 worker 互斥與伺服器重啟恢復。
- Discord 真實 API、語音權限與端到端遊戲。
- 23 套板型每一個角色組合的完整整局回歸。

## 敏感資料檢查

### 掃描範圍與方法

- 目前所有追蹤檔。
- `git rev-list --all` 的 85 個提交快照。
- 31 個曾出現在歷史中的唯一路徑。
- 規則包含 Discord Token、Google API key、GitHub Token、AWS access key、PEM 私鑰，以及常見敏感環境變數的非空指派。
- 機器上沒有 `gitleaks`、`trufflehog` 或 `detect-secrets`，因此使用本機唯讀 Git 掃描；沒有把候選值輸出到報告或終端摘要。

### 結果

- 沒有符合實際憑證格式的候選。
- 一般指派規則只命中：
  - `.env.example` 的示範／提醒文字。
  - `cogs/chat.py` 的 `os.getenv('GEMINI_API_KEY')`。
- Git 歷史中未曾出現 `.env`、私鑰、cookie、credentials 或 token 命名檔案；只有 `.env.example`。
- `.gitignore` 與 `.dockerignore` 均排除 `.env`、其他 `.env.*`、cookie、log、cache 與 `secrets/`，並僅放行 `.env.example`。

目前沒有撤銷 Token 的證據需求。這是模式掃描而不是絕對保證；若過去曾在 GitHub、Railway 設定、Issue、聊天或未追蹤檔中貼過憑證，仍應在各服務端輪替。

## 環境變數

目前 `.env.example` 包含：

- `DISCORD_BOT_TOKEN`
- `GEMINI_API_KEY`
- `OWNER_IDS`
- `LOG_LEVEL`
- `YTDLP_COOKIES_FROM_BROWSER`
- `YTDLP_COOKIE_FILE`
- `YTDLP_COOKIES_B64`
- `YTDLP_LOW_RESOURCE`
- `YTDLP_DENO_V8_FLAGS`

Activity 目標需要但目前尚未存在的鍵（例如 Discord Client ID／Secret、Activity URL、API／WebSocket URL、Redis、Database、JWT）應等相應元件建立時加入；本階段未修改 `.env.example`。

## 授權與素材

- `LICENSE` 是 GNU Affero General Public License v3 完整本文，不得在遷移中移除。
- README 說明專案採 AGPL-3.0，並保留作者聯絡文字。
- Git 紀錄主要作者為 Eric520888；遷移時需保留歷史與作者資訊，禁止 squash／force push 破壞來源追溯。
- `sounds/night.mp3` 被 README 明確排除在作者版權範圍，且未提供來源、作者、授權或 checksum。正式 Activity 或 Bot 發布前，應以自有／明確授權素材替換，或補齊可稽核授權資料。
- 目前沒有第三方套件授權清單、SBOM 或 notices 檔。這不是階段 0–1 的阻斷項，但部署前應建立。

## 狼人殺現況與風險

### 已確認存在

- 23 套固定 12 人官方板型，加上自動配置與 2 個舊彈性板型 ID。
- 57 筆角色目錄資料，其中 46 個有可建立的角色類別，11 個僅有目錄說明。
- 7 個階段：等待、身分確認、上半夜、下半夜、白天、出局技能、結束。
- 發牌、狼隊投票、查驗、女巫、守護、特殊技能、白天投票、平票、死亡連鎖、射擊、勝負、復盤。
- 夜晚全員靜音、白天恢復存活玩家原始靜音狀態、死亡玩家保持靜音、結束／中止恢復原始狀態。
- 狼人私人討論串、身分私密 Embed、操作權限及部分舊面板失效檢查。

### 高風險問題

| 風險 | 證據 | 影響 |
|---|---|---|
| 領域狀態不可序列化 | `Player.user` 保存 Discord user；`WerewolfGame` 保存 bot、channel、message、thread、lock、future 類資源 | 不能直接放 Redis、不能重連或多 worker |
| 規則與 Discord I/O 混合 | `game.py` 幾乎每個階段方法同時判定規則並 `send_message`／建立 View | Activity 無法安全重用，測試必須偽造 Discord |
| 角色 ID 使用中文顯示名稱 | `ROLE_WEREWOLF = "狼人"` 等同時作為資料鍵與 UI 文字 | 無法穩定多語言，改名會影響邏輯／資料 |
| 房間只以 guild ID 索引 | `WerewolfBot.games[guild_id]` | 同 guild 不可多房；不能對應 Activity instance/channel |
| 計時器不可持久化 | `asyncio.sleep()` 與 View timeout；沒有 `phase_started_at`／`phase_ends_at` | 重啟後遺失，無法安全多 worker |
| 復盤只在記憶體 | `game_log` 保存可見名稱與中文文字，結束後只產生 Discord UI | 無持久化、無版本化 schema、難做私密投影 |
| 多語言不存在 | 可見字串分散於 `game.py`、`skills.py`、`views.py`、`replay.py`、Cog | 不能按玩家語言顯示 |
| 規則不是板型設定 | `BoardSpec` 只有名稱、角色、說明 | 勝利、女巫、警長、發言、翻牌等規則不能按板型調整 |
| 素材授權不明 | README 對 `night.mp3` 的警告 | 正式發布的法律／下架風險 |

## 階段 0 結論

基準版本目前可安裝、可匯入、可通過所有現有測試，適合採「保留舊 Bot、逐步抽離核心」策略。不得直接把 `WerewolfGame` 搬到 FastAPI；應先建立可序列化模型與純規則服務，再以 Discord adapter 維持舊行為。詳細功能去留、相依關係與遷移順序分別見：

- `WEREWOLF_FEATURE_MATRIX.md`
- `WEREWOLF_DEPENDENCY_MAP.md`
- `MIGRATION_PLAN.md`
- `OPEN_RULE_QUESTIONS.md`

本階段沒有修改任何狼人殺實際行為、沒有建立前端或 FastAPI，也沒有刪除檔案。
