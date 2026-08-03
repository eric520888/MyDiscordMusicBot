# Discord Activity 狼人殺遷移計畫

基準：`08735ea`
狀態：僅完成階段 0–1 規劃；尚未建立 `werewolf_engine`、FastAPI 或前端。

## 遷移策略

採用漸進式替換（strangler migration）：

1. 把現有 48 項測試當成不可任意破壞的基準。
2. 先建立不依賴 Discord 的核心模型與純規則。
3. 舊 `WerewolfGame` 保持不動，只作規則來源與 parity 對照；不要求舊 Bot 改用新核心。
4. 新核心只服務獨立 Discord Activity 視覺化遊戲。
5. Activity 後端完成伺服器權威與私密投影後，再接 Activity 前端。
6. 每一小步都同時跑新核心測試與現有回歸測試，不能以刪測試換取通過。

## 明確抽離範圍

本工作的交付物是獨立 Discord Activity 視覺化狼人殺，不是重構整個多功能 Bot：

- 抽離 `cogs/werewolf_system/` 中的狼人殺資料、規則、狀態機、事件與復盤資料。
- `cogs/werewolf_bot.py` 和舊 Discord View 只作行為參考，保持原狀，不搬入成品，也不要求改呼叫新核心。
- 第一版不搬既有語音／音樂整合；若之後確定需要 server mute，另做只含狼人殺權限操作的可選 companion Bot。
- 不搬移音樂播放、YouTube、Gemini、Google Sheets、Help 或一般指令功能。
- 不把原本整份 `requirements.txt` 帶進新核心或 Activity 後端。

相依套件分離原則：

- `werewolf_engine`：優先只用 Python 標準函式庫；若採 Pydantic，只宣告 Pydantic，不依賴 `discord.py`、`yt-dlp`、Gemini、gspread 或 oauth2client。
- `activity_backend`：只安裝 FastAPI、ASGI/WebSocket、模型與實際使用的 auth/storage 套件。
- 原 Bot：維持原專案現況，不是 Activity 的執行或部署相依。
- `activity_frontend`：獨立 Node 套件，不與 Python Bot requirements 混用。

本次階段 0 為了驗證原始專案可安裝，曾在被 Git 忽略的 `venv/` 安裝完整既有 requirements；這不是未來狼人殺系統的部署依賴，也沒有被提交。

本計畫不採取以下做法：

- 不把 3,132 行 `game.py` 原封不動搬進新資料夾。
- 不先做 React 畫面再補規則。
- 不讓 FastAPI endpoint 或 WebSocket handler 直接修改遊戲 dict。
- 不同時維護一套 Bot 規則和另一套 Activity 規則。
- 不在規則尚未確認前「修正」舊行為。

## 來源保護與抽離契約

抽離期間必須持續成立：

- 不刪除或修改原專案 `/ww_create`、`/ww_rules`、`/ww_status`、`/ww_force_stop`。
- 現有 23 套固定板型與 3 個彈性板型 ID 不消失。
- 現有 46 個可建立角色不因搬移而遺失。
- 新 Activity 以獨立測試重現大廳、身分、夜間、投票、開槍與復盤；不共用舊 Discord View。
- 現有 48 項測試始終通過；若測試需要更換 import，只能保持同等或更強的行為斷言。
- `LICENSE`、README 的作者／授權說明與 Git 歷史保留。

## 建議目標結構

先新增最小結構，不立即搬動其他音樂 Bot 檔案：

```text
werewolf_engine/
├── __init__.py
├── ids.py
├── models/
│   ├── player.py
│   ├── role.py
│   ├── game.py
│   ├── room.py
│   ├── vote.py
│   ├── action.py
│   ├── event.py
│   ├── settings.py
│   └── replay.py
├── roles/
│   ├── catalog.py
│   └── handlers/
├── boards/
│   ├── catalog.py
│   └── validation.py
├── rules/
│   ├── assignment.py
│   ├── targeting.py
│   ├── voting.py
│   ├── damage.py
│   ├── death.py
│   └── victory.py
├── phases/
│   ├── transitions.py
│   ├── night.py
│   └── day.py
├── actions/
│   ├── commands.py
│   └── service.py
├── events/
│   ├── models.py
│   └── projections.py
├── replay/
│   └── service.py
└── tests/
```

Activity 成品新增自己的 application/backend/frontend，不新增舊 Bot adapter：

```text
werewolf_engine/                      純規則與可序列化狀態
activity_backend/                     Discord 驗證、房間、WebSocket、計時
activity_frontend/                    Discord Activity 視覺化介面
```

不移動或複製 `werewolf_bot.py`、`music.py`、`chat.py`、`General.py` 或其他 Cog。Activity 直接使用自己的後端 transport，不為了目錄外觀改寫無關功能。

## 穩定角色 ID 遷移

目前中文名稱同時作為邏輯 ID、字典 key 與顯示字串。第一個核心提交必須建立 ASCII ID；抽取器／parity fixture 可接受舊中文值，但不修改舊 Bot 的判斷。

| 現有值 | 新 ID | 現有值 | 新 ID |
|---|---|---|---|
| 狼人 | `werewolf` | 平民 | `villager` |
| 預言家 | `seer` | 女巫 | `witch` |
| 獵人 | `hunter` | 愚者 | `fool` |
| 守衛 | `guard` | 狼王 | `wolf_king` |
| 狼美人 | `wolf_beauty` | 騎士 | `knight` |
| 攝夢人 | `dreamer` | 惡夜騎士 | `evil_knight` |
| 石像鬼 | `gargoyle` | 守墓人 | `gravekeeper` |
| 赤月使徒 | `crimson_apostle` | 獵魔人 | `demon_hunter` |
| 噩夢之影 | `nightmare` | 蝕時狼妃 | `time_wolf` |
| 定序王子 | `order_prince` | 狼巫 | `wolf_witch` |
| 純白之女 | `pure_white` | 寂夜導師 | `night_mentor` |
| 白晝學者 | `day_scholar` | 羊駝 | `alpaca` |
| 白貓 | `white_cat` | 子狐 | `young_fox` |
| 熊 | `bear` | 河豚 | `pufferfish` |
| 蝕日侍女 | `eclipse_maid` | 流光伯爵 | `light_earl` |
| 夜之貴族 | `night_noble` | 覺醒愚者 | `awakened_fool` |
| 尋香魅影 | `fragrance_phantom` | 覺醒預言家 | `awakened_seer` |
| 覺醒狼王 | `awakened_wolf_king` | 魔鏡少女 | `mirror_girl` |
| 覺醒隱狼 | `awakened_hidden_wolf` | 覺醒女巫 | `awakened_witch` |
| 覺醒狼美人 | `awakened_wolf_beauty` | 覺醒獵人 | `awakened_hunter` |
| 覺醒孤獨少女 | `awakened_lonely_girl` | 覺醒石像鬼 | `awakened_gargoyle` |
| 覺醒守衛 | `awakened_guard` | 覺醒白狼王 | `awakened_white_wolf_king` |
| 覺醒攝夢人 | `awakened_dreamer` | 奇跡商人 | `merchant` |
| 隱狼 | `hidden_wolf` | 白狼王 | `white_wolf_king` |
| 丘比特 | `cupid` | 千面人 | `thousand_faces` |
| 警長 | `sheriff` | 烏鴉 | `crow` |
| 煉金魔女 | `alchemist` | 狼鴉之爪 | `wolf_crow_claw` |
| 魔術師 | `magician` | 孤獨少女 | `lonely_girl` |
| 咒狐 | `curse_fox` |  |  |

遷移規則：

- 序列化只輸出新 ID。
- 抽取舊規則資料與建立 parity fixtures 時接受中文 alias；新 Activity API 不輸出舊中文 ID。
- UI 只使用 `role.<id>.name`、`role.<id>.description` key。
- Python 類別名不能當持久化 ID。
- 覺醒隱狼模仿後不可再把 `role.name` 改成動態中文；應保留 `role_id=awakened_hidden_wolf`，另存 `mimicked_role_id`。

## 核心資料模型

階段 2 至少建立下列 JSON-safe model。建議使用 Pydantic v2，因後端預定採 FastAPI，且需要明確驗證／schema；若決定 dataclass，必須提供等價的 validation 與 round-trip 測試。

### `PlayerState`

- `player_id: str`
- `discord_user_id: str`
- `seat: int`
- `display_name: str`（只作 snapshot，不作識別）
- `status: PlayerStatus`
- `role_id: RoleId | None`
- `connected: bool`
- `ready: bool`
- `spectator: bool`
- `vote_enabled: bool`

### `RoleState`

- `role_id`
- `camp`
- `disabled`
- `used_abilities: set[str]`（序列化為 list）
- `resources: dict[str, int | bool]`，但 key 必須註冊，不接受任意物件
- `last_target_ids: list[str]`
- `checked_target_ids: list[str]`
- `effects: list[EffectState]`

### `GameState`

- `game_id`、`room_id`、`board_id`、`settings`
- `phase`、`round_number`、`revision`
- `phase_started_at`、`phase_ends_at`
- `players`
- `night_actions`、`vote_state`
- `pending_effects`、`pending_decisions`
- `winner`、`ended_reason`
- `event_sequence`

### 死亡翻牌房間設定

- `GameSettings.reveal_roles_on_death: bool` 由房主在大廳設定。
- 開始遊戲後鎖定設定，避免中途改變公開資訊規則。
- 一般死亡公開事件只有在設定開啟時才包含 `role_id`；關閉時只包含玩家與死因等允許公開的資料。
- 完整角色仍保存在伺服器權威狀態，且遊戲結算是否全員公開可另設獨立設定。
- 愚者、白貓、河豚等「翻牌本身就是技能」的角色是否覆蓋房間設定，尚待確認，先保持舊角色行為。

### 其他必要模型

- `RoomState`：Discord instance/guild/channel 綁定、host、成員、game ID、過期時間。
- `VoteState`：eligible voters、ballots、公開策略、tie state。
- `NightAction`：actor、action ID、targets、mode、submitted_at、request ID。
- `GameEvent`：event ID、sequence、type/key、visibility scope、recipients、payload、schema version。
- `GameSettings`：語言、觀戰、死亡資訊、計時、勝利與規則選項。
- `BoardConfiguration`：角色組合與所有板型規則。
- `ReplayEntry`：不可變事件 reference／摘要，不保存 Discord 物件。

所有模型都必須測試：`model -> JSON -> model` 等價、無 set/tuple key/Discord object、未知欄位策略明確。

## 階段 2：抽離狼人殺核心

### 2.1 建立 characterization tests

在搬移前，先針對目前未被充分鎖定的純 helper 補測試：

- 每個板型 ID、12 人組合與角色 ID alias。
- `get_action_targets()` 的每個特殊分支。
- `get_required_night_tasks()` 的封技／優先技能／孤立狼。
- 狼票平票、雙刀、空刀。
- `check_winner()` 的所有邊界，包括第三方存在時的目前行為。
- 投票平票、愚者、白貓、河豚、定序、射擊死亡原因。

這些測試先描述舊行為；規則有疑問者標記對應 `OPEN_RULE_QUESTIONS.md`，不自行修改。

### 2.2 建立 ID、enum 與靜態 catalog

- 新增 camp、role、board、phase、action、event 的穩定 enum／字串常數。
- 搬 `catalog.py` 的不可變資料，但顯示文字先改成 localization key。
- 保留 legacy Chinese alias map。
- `BoardSpec` 擴充為 `BoardConfiguration`；未確認欄位先明確使用 legacy/default 值，不猜新規則。

提交建議：`refactor: add stable werewolf ids and catalogs`

### 2.3 建立可序列化 models

- 建立前述模型及 schema version。
- 區分 durable state、derived state、runtime-only lock/timer/session。
- 寫 round-trip、invalid input、schema compatibility 測試。
- 不修改舊 `WerewolfGame` 的行為。

提交建議：`refactor: extract serializable werewolf domain models`

### 2.4 抽離第一批純規則

按風險由低到高：

1. 玩家／陣營查詢。
2. 板型與人數驗證。
3. 角色分配（注入 RNG）。
4. 目標過濾與行動配額。
5. 夜間必做工作計算。
6. 基礎勝負判定。

每項採 dual-run 或對照測試：同一 fixture 同時跑 legacy helper 和 engine helper，輸出必須一致。

提交建議：`refactor: extract core werewolf rules`

### 2.5 抽離事件與投影

- command handler 不傳送訊息，只回傳 `GameEvent[]` 與新 state/revision。
- 定義 `PUBLIC`、`PLAYER_ONLY`、`WOLF_TEAM`、`HOST_ONLY`、`AFTER_GAME` visibility。
- 建立 `project_state_for_player()`，任何 private role/result 只在本人投影出現。
- replay 使用同一事件來源，但依房間死亡資訊規則過濾。

提交建議：`refactor: add werewolf events and private projections`

### 2.6 抽離階段與結算

不要一次處理全部角色。第一批只做 MVP 板型所需：

- 狼人、平民、預言家、女巫、獵人。
- 夜晚 command、狼票、查驗、用藥。
- 夜間傷害、白天投票、射擊、死亡與勝負。

其他 41 個可玩角色維持 legacy path；以 board capability/engine coverage flag 禁止新後端誤啟尚未搬完的板型。完成一個角色就新增 handler、fixtures 與 legacy parity tests。

## 階段 3：核心測試門檻

新增 `werewolf_engine/tests/`，至少涵蓋原需求中的：

- 角色分配與人數檢查。
- 夜晚行動合法性、重複行動、死者行動阻擋。
- 狼人投票、查驗、女巫、獵人、守衛。
- 白天投票、平票、死亡順序、勝負。
- 不同板型設定。
- JSON round-trip 與 schema validation。
- 斷線恢復所需 state projection。
- 每個事件的可見範圍，確保角色秘密不外洩。
- 同一 command/request ID 的冪等性。

通過條件：

- 新 engine 測試 100% 通過。
- 現有 48 項測試仍 100% 通過。
- `werewolf_engine` 的 import graph 中沒有 `discord`、FastAPI、WebSocket 或 Redis。
- 靜態檢查確認核心 model JSON 可序列化。

提交建議：`test: add werewolf engine tests`

## 階段 4：Activity application service

在 FastAPI transport 前先建立只服務視覺化遊戲的 application layer：

- `create_room`、`join_room`、`leave_room`、`set_ready`、`start_game`。
- `submit_action`、`submit_vote`、`advance_phase`、`abort_game`。
- 房主與玩家授權、request ID 冪等、expected revision。
- 依 event visibility 建立公開、狼隊與單一玩家投影。
- 依 `reveal_roles_on_death` 過濾公開死亡事件。
- repository 與 timer port；第一版使用 in-memory fake 寫測試。

這一層不得 import `discord.py`、FastAPI 或舊 `werewolf_bot.py`。它讓 WebSocket transport 保持很薄，也方便在沒有 Discord 連線時完成整局測試。

提交建議：`feat: add werewolf activity application service`

## 階段 5：Activity 後端

前提：MVP 核心與 Activity application service 已通過測試。

### 最小元件

- FastAPI app 與 health endpoint。
- Discord OAuth／Embedded App token 驗證。
- 以可信 Discord context 建立 room binding，不信任任意前端 room ID。
- In-memory repository port 的第一版實作。
- WebSocket session manager。
- command envelope、request ID 去重、expected revision。
- public／private projection fan-out。
- server-side timer service，保存 started/ends at。
- reconnect：用 Discord user ID 恢復本人 projection，不重新發牌。
- room lock、rate limit、過期清理。

### 後端不可做

- 不保存 Discord SDK object 到 `GameState`。
- 不把完整 state broadcast 給所有 socket。
- 不信任前端角色、死亡、勝負或可用 action。
- 不在 WebSocket handler 複製任何角色規則。

提交建議拆分：

- `feat: create activity backend foundation`
- `feat: add websocket room synchronization`
- `feat: add reconnect and idempotent actions`

## 階段 6：Activity 前端

前提：後端可用測試 client 完成整局 MVP，且 private projection 測試通過。

- React + TypeScript strict + Vite + Discord Embedded App SDK。
- SDK 初始化、OAuth、loading/error/reconnect。
- 大廳、座位、準備、角色、夜晚、白天、結算。
- store 只保存後端給本人的 projection。
- 所有 action 使用 typed command；UI 不計算技能結果。
- responsive/mobile-first；使用實際 viewport 測試，不固定 1920×1080。
- 可見文字從第一個元件起使用 i18n key，即使完整翻譯在階段 7 補齊。

## 階段 7：多語言

- 首批 `zh-TW`、`zh-CN`、`en-US`。
- role、board、phase、action、event、error 都使用穩定 key。
- 後端 event 只帶 key 與參數；不能帶已格式化中文。
- 玩家 UI locale 與房間主持／語音／公共公告 locale 分開。
- fallback：玩家設定 → Discord locale → 房間預設 → `en-US`。
- CI 檢查三個 locale key 集合一致、無 UI literal 漏網。

## 階段 8：可選的 Discord 語音 companion

這不是第一版視覺化 Activity 的必要條件，也不使用原音樂 Bot。只有確認需要自動 server mute 時才建立：

- 最小 Discord Bot，只接受後端簽署的狼人殺 voice command。
- 不含音樂、AI、Help 或一般指令。
- 保存並冪等恢復原始 server mute state。
- 測試正常結束、強制結束、socket 全斷、後端例外與 companion 重啟。

## 階段 9：部署準備

- Backend／Frontend Dockerfile 與 compose。
- Redis adapter；PostgreSQL 只做玩家設定／歷史等必要資料，不過度設計經濟系統。
- health/readiness、結構化 log、敏感欄位 redact、metrics。
- HTTPS tunnel 與 Discord Portal 設定指南。
- dependency license inventory／SBOM。
- 更換或補授權 `sounds/night.mp3`。
- `.env.example` 加 Activity 所需鍵，但不放真值。
- production security tests 與備份／復原演練。

部署產物只包含狼人殺 engine、Activity backend/frontend；可選語音 companion 使用獨立映像。不把舊 Bot、音樂、AI 或其他 Cog 打包進狼人殺服務。

## 每階段測試閘門

| 階段 | 必跑檢查 | 必須結果 |
|---|---|---|
| 2 每個提交 | compileall、engine unit、legacy unittest | 全通過；無 Discord import 進 engine |
| 3 | serialization、property/boundary、private projection、legacy parity | 全通過；未確認規則維持 legacy |
| 4 | application service、authorization、projection、repository/timer fakes | 可離線完成整局且不 import Discord/FastAPI |
| 5 | API/WebSocket auth、room、idempotency、reconnect、privacy、timer | 非法／重播／越權操作全部拒絕 |
| 6 | TypeScript typecheck、component、responsive、socket reconnect | strict 無錯；秘密不進其他玩家 store |
| 7 | locale key parity、fallback、三語 UI | 無硬編碼可見文字 |
| 8（可選） | companion auth、voice failure matrix | 所有終止路徑恢復語音 |
| 9 | Docker build、compose smoke、health、security、deployment runbook | 可由乾淨環境重現 |

## 建議提交順序

階段 0–1：

1. `docs: audit existing werewolf system`

後續：

2. `refactor: add stable werewolf ids and catalogs`
3. `refactor: extract serializable werewolf domain models`
4. `refactor: extract core werewolf rules`
5. `refactor: add werewolf events and private projections`
6. `test: add werewolf engine tests`
7. `feat: add werewolf activity application service`
8. `feat: create activity backend foundation`
9. `feat: add websocket room synchronization`
10. `feat: add reconnect and idempotent actions`
11. `feat: create activity frontend`
12. `feat: add discord embedded app sdk`
13. `feat: add localization system`
14. `feat: add optional werewolf voice companion`
15. `docs: add local development and deployment guide`

每個提交只做一個可驗證責任，不混入音樂 Bot 的無關格式化或重寫，不 force push。

## 回滾策略

- 新 engine 與 Activity 目錄是 additive；原 Bot 完全不切換，回滾只需停用新服務。
- parity fixtures 以舊系統輸出作比較，但不從舊檔刪除規則或 View。
- Activity 功能以獨立 feature flag／room capability 漸進開放，不改動原 Bot 的部署。
- 狀態 schema 必須有版本；任何不相容變更提供 migration function 與 fixture。
- backend room repository 先以 interface 包裝，in-memory 與 Redis 可替換，不讓 engine 知道儲存實作。

## 開始階段 2 前的必要決策

以下問題會改變模型或結果，必須先從 `OPEN_RULE_QUESTIONS.md` 確認或明確採「維持舊行為」：

- 各板型的勝利條件與第三方勝利。
- 女巫自救、同守同救、狼刀／技能優先序。
- 狼票與白天票平票處理。
- 特殊角色的強制翻牌是否覆蓋房間的死亡翻牌設定，以及死亡玩家／觀戰資訊。
- 獵人／狼王各死因是否可開槍。
- 警長、發言與語音主持規則。
- Activity MVP 是否只開 `standard`，以及實際 6–12 人板型組合。

若尚未回答，第一批 engine 以現有 `standard` 行為為 compatibility profile，疑義用明確設定欄位保留，不發明新規則。
