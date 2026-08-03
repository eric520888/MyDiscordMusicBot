# 狼人殺功能矩陣（階段 1）

基準：`08735ea`
判定原則：以實際程式與測試為準，不以 README 的宣稱代替實作證據。

## 分類說明

| 分類 | 意義 |
|---|---|
| 可直接沿用 | 沒有 Discord 物件或 I/O；搬移後只需修正 import、型別與測試 |
| 需重構 | 規則存在且值得保留，但資料模型、事件或職責必須拆分 |
| 需重寫 | Discord View／訊息／討論串等呈現或運輸層，Activity 不能直接使用 |
| 尚未實作 | 只有說明、常數或需求，沒有可執行功能 |
| 保留 Bot adapter | Activity 不使用，但原 Bot 仍需保留並改成消費核心事件 |

## 功能總表

| 功能 | 實際位置與主要函式／類別 | Discord 依賴 | 現況 | 沿用判定 |
|---|---|---|---|---|
| 狼人殺 Cog 與遊戲登錄 | `cogs/werewolf_bot.py`：`WerewolfBot`、`create_game()`、`get_game()` | `commands.Cog`、hybrid command、`ctx.send` | 每 guild 只保存一個記憶體 `WerewolfGame` | 保留 Bot adapter；房間登錄需由後端重寫 |
| 大廳建立／遺失後重建 | `werewolf_bot.py:23-93` | Message、Embed、View、HTTPException | 等待中的大廳訊息可刷新或重建，玩家清單保留在同一程序 | Discord 呈現需重寫；「重建同一房間」語意可保留 |
| 加入／離開 | `game.py:425-450`：`player_join()`、`player_leave()` | `discord.Interaction`、`interaction.user`、`edit_message` | 僅等待階段；最多 20 人；沒有準備、座位、觀戰或轉移房主 | 狀態規則需重構；UI 需重寫 |
| 房主切換板型／開始／關閉 | `game.py:403-552` | Interaction、Bot owner、VoiceClient、Message、Embed、View | 房主或 Bot owner 可操作；開始後不可切板 | 權限規則需抽離；Discord 回應與語音取得重寫 |
| 角色／陣營靜態資料 | `catalog.py`：`RoleInfo`、`ROLE_CATALOG` | 無 | 57 筆資料；ID 目前等於中文顯示名稱 | 資料可沿用；ID 與 i18n 必須重構 |
| 板型靜態資料 | `catalog.py`：`BoardSpec`、`BOARD_SPECS` | 無 | 23 套固定 12 人板型；只有名稱、角色、說明 | 組合可沿用；板型規則欄位需擴充 |
| 自動／舊彈性板型 | `game.py:554-606`：`assign_roles()` | 無直接 I/O | `auto` 3–20 人；`wolf_king` 至少 5；`merchant` 至少 7 | 發牌規則可抽離；板型有效性需確認 |
| 固定板型發牌 | `game.py:554-606` | 無直接 I/O | 檢查固定人數、shuffle、建立角色、重設存活 | 可抽離為純服務，亂數來源應注入 |
| 玩家狀態 | `roles.py:6-19`：`Player` | 直接保存 Discord user | id、user、role、alive/dead | 欄位需重構成可序列化模型 |
| 角色局內狀態 | `roles.py:22-164`：`Role`、46 個角色類別 | 無直接 I/O | 藥、已用技能、停權、上一目標、checked set、任意 `state` dict | 規則可保留；需改成明確 schema、穩定 ID、JSON 型別 |
| 階段狀態機 | `const.py:10-16`；`game.py` 各 `start_*` | 大量 Discord I/O | waiting → starting → night_actions → night_witch → day → role_shoot → ended | 階段常數可沿用；轉移服務需重構 |
| 行動目標合法性 | `game.py:118-188`：`get_active_wolves()`、`get_action_targets()`、`get_night_action_limit()` | 無直接 I/O，但依賴 Discord-coupled Player | 狼刀隊友、隔離狼、自刀例外、相鄰、不可連續等 | 高優先可抽離純規則 |
| 夜晚必做工作 | `game.py:905-982`：`_role_action_available()`、`get_required_night_tasks()`、`get_pending_night_tasks()` | 無直接 I/O | 支援優先技能、封技、選擇性技能與額外行動 | 可抽離；資料結構需型別化 |
| 夜晚 UI | `game.py:770-1058`、`views.py:151-286` | View、Button、Select、Embed、Interaction、Channel | 單一公開按鈕開啟私密面板；大量 300 秒 View timeout | 需重寫為 Activity UI／WebSocket action |
| 狼隊共同擊殺 | `game.py:1126-1134`、`1361-1404` | 回應訊息與私人 Thread | 每名 active wolf 投票；平票候選以亂數決定；可空刀／雙刀 | 投票與結算需抽離；Thread 保留 Bot adapter |
| 狼人私人討論 | `game.py:616-644`：`create_wolf_thread()` | private thread、`add_user`、`send`、`delete` | 每夜建立、天亮刪除；隔離狼不加入 | Activity 要改寫；舊 Bot 可保留 adapter |
| 身分私密顯示 | `game.py:649-746`、`views.py:455-471` | ephemeral Embed、Discord display name | 顯示本人角色與專屬隊友／查驗／資源資訊 | 私密投影規則需抽離；畫面需重寫 |
| 預言家與具體查驗 | `game.py:1135-1156` | Interaction 回應 | 陣營查驗、具體角色查驗、雙人查驗、已查目標 | 規則可抽離；結果改成私密 `GameEvent` |
| 女巫 | `skills.py:94-223`、`game.py:1487-1535` | View、Select、Interaction、Channel | 解藥、毒藥、不能自救、每夜配額；下半夜顯示狼刀 | 規則需抽離；UI 重寫；板型規則待確認 |
| 覺醒女巫協力調毒 | `skills.py:225-335` | 公開 mention、Button、View、Channel | 選未協助玩家，所有人同意才生效 | 規則需重構；私密協作運輸重寫 |
| 奇跡商人／幸運兒 | `game.py:1337-1358`、`skills.py:75-91` | Interaction | 全局一次給查驗／毒／守，給狼人時商人反噬 | 規則可抽離；UI 重寫 |
| 守衛／全傷害保護 | `game.py:129-188`、`1540-1970` | 日結算本身伴隨訊息 | 一般守衛擋狼刀；攝夢、流光、秘密守護、覺醒守衛各有不同範圍 | 核心結算需抽離，規則問題需先確認 |
| 其他夜間特殊角色 | `game.py:1060-1405`、`1540-1970` | Interaction、DM、Channel | 魅惑、查殺、恐懼、封鎖、時波、迷惑、吞噬、夜僕、模仿、轉化、夢語等 | 規則保留並逐角色抽離；呈現重寫 |
| 夜間死亡總結算 | `game.py:1540-2025`：`start_day()` | Channel、Embed、DM、AudioManager、Thread | 單一約 480 行方法處理反彈、保護、傷害、連鎖、公告、勝負與下一 UI | 必須拆成純 resolver + 事件；Discord 外殼重寫 |
| 白天討論 | `game.py:2066-2083` | Channel、Embed、VotingView | 只送出「討論與放逐」提示，沒有發言順序或後端倒數 | 現有 UI 重寫；發言流程尚未實作 |
| 放逐投票 | `game.py:2101-2219`、`views.py:328-405` | Button、Interaction、Channel、Embed | 存活且有票權者一票；全部完成即結算；公開每人投向；平票無人出局 | 計票可抽離；UI／公開策略重寫；平票規則待確認 |
| 白天特殊技能 | `game.py:2224-2856` | 多個臨時 View、Select、Button、sleep、Channel | 定序回溯、河豚、騎士、赤月、自爆、覺醒守護／白狼引爆 | 規則需按技能拆 service；互動全面重寫 |
| 獵人／狼王／覺醒獵人 | `game.py:2046-2064`、`2859-3009`；`views.py:288-326` | Shooter View、Select、Interaction、Channel | 依死亡原因排除部分開槍；支援多槍與連鎖槍手 | 規則需抽離；觸發條件待確認；UI 重寫 |
| 死亡連鎖 | `game.py:1709-1970`、`2354-2400` | 產生公告字串 | 魅惑、攝夢、命運綁定、白貓、孤獨少女、守護等 | 抽離為確定性 damage/death resolver |
| 勝負判定 | `game.py:3014-3024`：`check_winner()` | 無直接 I/O | 無狼＝好人；神或民任一全滅，或狼數達其餘好人數＝狼人 | 可抽離；板型化與第三方規則待確認 |
| 結算與再開 | `game.py:3026-3068` | Embed、Channel、ReplayView、音訊／靜音 | 公布全部身分並顯示復盤；沒有「再來一局」狀態操作 | 結果資料可抽離；畫面重寫；再開尚未實作 |
| 遊戲紀錄／復盤 | `game.py:3097-3104`、`replay.py` | 事件 payload 含顯示名稱；復盤是 Discord UI | 記憶體 list；事件沒有 schema/version；部分事件格式化 | 事件語意需重構；Discord Replay UI 重寫 |
| 強制停止／玩家結束票 | `werewolf_bot.py:125-149`、`game.py:3070-3132` | command、Interaction、Channel | 管理員可 abort；白天過半數可結束 | 核心 command 可保留；transport 重寫；勝者語意待確認 |
| 夜晚靜音／白天恢復 | `game.py:343-398`、`audio.py:25-48` | Guild、Member.voice、`member.edit(mute=...)` | 保存原伺服器靜音；夜晚全靜音；白天死者靜音、活人回原狀；結束恢復 | 保留 Bot voice adapter；核心只發 voice command event |
| 遊戲音效 | `audio.py:50-116`、`game.py:359-369` | VoiceClient、FFmpegOpusAudio | 播放循環 `night.mp3`；可混 `voice_night_start.mp3`（目前檔案不存在） | 保留 Bot adapter；核心改發固定 audio key |
| 音樂系統互斥 | `music.py:1496-1501`、`2992-3050` | Cog lookup、Guild、VoiceClient | 狼人殺開始接管語音，清空音樂佇列；結束後釋放 | 需保留相容 adapter，改用明確 integration event |
| 多語言 | 字串散落於 `catalog.py`、`game.py`、`skills.py`、`views.py`、`replay.py`、Cog | 所有 UI 都是中文硬編碼 | 尚未實作；角色 ID 也使用中文 | 需建立 key-based i18n；不可直接沿用文字作 ID |
| 斷線重連 | 無 | 無 | 只支援「等待中大廳訊息遺失後重建」；不支援玩家／WebSocket／程序重啟恢復 | 尚未實作 |
| 狀態序列化與持久化 | 無 | `Player.user` 等反而阻礙序列化 | 所有房間與復盤只在記憶體 | 尚未實作，階段 2 必須先補模型 |
| Activity／FastAPI／WebSocket | 無 | 無 | 尚未建立 | 本階段禁止建立；後續全新 transport |

## 角色盤點

### 可建立角色（46）

目前「角色 ID」就是中文 `role.name`；下表的英文是 Python 類別，不是持久化 ID。後續應另建穩定 ASCII ID，並保留中文名稱到 locale key。

| 現有名稱 | Python 類別 | 陣營 | 主要能力／觸發 | 實作狀態 |
|---|---|---|---|---|
| 狼人 | `Wolf` | 狼 | 狼隊投票、自爆 | 可玩；需抽離 |
| 平民 | `Villager` | 村民 | 無夜間技能 | 可玩；可抽離 |
| 預言家 | `Seer` | 神 | 陣營查驗 | 可玩；需事件化 |
| 女巫 | `Witch` | 神 | 解藥、毒藥 | 可玩；需拆 UI |
| 獵人 | `Hunter` | 神 | 死亡後開槍 | 可玩；觸發規則待確認 |
| 愚者 | `Fool` | 神 | 首次放逐免死、失票 | 可玩 |
| 守衛 | `Guard` | 神 | 狼刀守護、不可連守 | 可玩；規則待確認 |
| 狼王 | `WolfKing` | 狼 | 狼刀、開槍、自爆 | 可玩；死因規則待確認 |
| 狼美人 | `WolfBeauty` | 狼 | 魅惑、連帶出局 | 可玩 |
| 騎士 | `Knight` | 神 | 白天決鬥 | 可玩 |
| 攝夢人 | `Dreamer` | 神 | 夢遊保護、連夢、殉夢 | 可玩 |
| 惡夜騎士 | `EvilKnight` | 狼 | 夜間免死、查驗／毒反傷 | 可玩 |
| 石像鬼 | `Gargoyle` | 狼 | 孤立、具體查驗、末狼狼刀 | 可玩 |
| 守墓人 | `Gravekeeper` | 神 | 得知上一放逐陣營 | 可玩；以身分卡查詢顯示 |
| 赤月使徒 | `CrimsonApostle` | 狼 | 自曝封技、末狼延死 | 可玩 |
| 獵魔人 | `DemonHunter` | 神 | 二夜起狩獵、免毒 | 可玩 |
| 噩夢之影 | `Nightmare` | 狼 | 恐懼封技、不可連選 | 可玩 |
| 蝕時狼妃 | `TimeWolf` | 狼 | 封鎖與反彈 | 可玩 |
| 定序王子 | `OrderPrince` | 神 | 首輪放逐後回溯重投 | 可玩；程式未明確限制首輪，需確認 |
| 狼巫 | `WolfWitch` | 狼 | 具體查驗、二夜查殺純白 | 可玩 |
| 純白之女 | `PureWhite` | 神 | 具體查驗、二夜查殺狼人 | 可玩 |
| 寂夜導師 | `NightMentor` | 狼 | 孤立、二夜起增幅／削弱 | 可玩 |
| 白晝學者 | `DayScholar` | 神 | 二夜起各一次增幅／削弱 | 可玩 |
| 羊駝 | `Alpaca` | 村民 | 動物局普通好人 | 可玩 |
| 白貓 | `WhiteCat` | 神 | 首次死亡延至下次投票後 | 可玩 |
| 子狐 | `YoungFox` | 神 | 二夜起迷惑 | 可玩 |
| 熊 | `Bear` | 神 | 清晨檢查存活鄰座狼 | 可玩 |
| 河豚 | `Pufferfish` | 神 | 被放逐後可帶走投票者 | 可玩 |
| 蝕日侍女 | `EclipseMaid` | 狼 | 吞噬好人技能並使用 | 部分角色技能有複製對應，其餘退化為無技能 |
| 流光伯爵 | `LightEarl` | 神 | 二夜起免疫全夜傷害 | 可玩 |
| 夜之貴族 | `NightNoble` | 狼 | 夜僕延時死亡 | 可玩 |
| 覺醒愚者 | `AwakenedFool` | 神 | 秘密身體／夜間保護 | 可玩 |
| 尋香魅影 | `FragrancePhantom` | 狼 | 孤立、雙人命運綁定 | 可玩 |
| 覺醒預言家 | `AwakenedSeer` | 神 | 雙人模糊查驗 | 可玩 |
| 覺醒狼王 | `AwakenedWolfKing` | 狼 | 兩枚狼王爪、自刀／自爆 | 可玩 |
| 魔鏡少女 | `MirrorGirl` | 神 | 不重複具體查驗 | 可玩 |
| 覺醒隱狼 | `AwakenedHiddenWolf` | 狼 | 孤立、模仿身分與技能 | 可玩；直接修改 role 顯示名稱 |
| 覺醒女巫 | `AwakenedWitch` | 神 | 解藥、三次協力調毒 | 可玩 |
| 覺醒狼美人 | `AwakenedWolfBeauty` | 狼 | 隔夜魅惑、幻象替死 | 可玩 |
| 覺醒獵人 | `AwakenedHunter` | 神 | 任意死因巡獵最近狼人 | 可玩 |
| 覺醒孤獨少女 | `AwakenedLonelyGirl` | 第三方 | 選偶像、轉狼或繼承 | 可玩；第三方勝負未完整建模 |
| 覺醒石像鬼 | `AwakenedGargoyle` | 狼 | 首夜相鄰轉化、延遲相認 | 可玩 |
| 覺醒守衛 | `AwakenedGuard` | 神 | 夜或日免疫所有出局 | 可玩 |
| 覺醒白狼王 | `AwakenedWhiteWolfKing` | 狼 | 白天誘導自爆、自爆 | 可玩 |
| 覺醒攝夢人 | `AwakenedDreamer` | 神 | 夢語保護、得知行動、二夜處決 | 可玩；包含 45 秒 Discord 決定流程 |
| 奇跡商人 | `Merchant` | 神 | 給予查驗／毒／守、反噬 | 可玩；屬舊彈性板與一套官方板 |

### 僅有目錄資料、不可建立的角色（11）

以下角色存在 `ROLE_CATALOG` 說明，但不在 `ROLE_CLASSES`，也沒有完整行動流程。不得在功能宣傳或 Activity 首版中視為已實作。

| 角色 | 現況 |
|---|---|
| 隱狼 | 只有常數、陣營與說明 |
| 白狼王 | 只有常數、陣營與說明 |
| 丘比特 | 只有常數、陣營與說明 |
| 千面人 | 只有常數、陣營與說明 |
| 警長 | 只有常數與「1.5 票／最後發言」說明；沒有競選、警徽或票權實作 |
| 烏鴉 | 只有常數、陣營與說明 |
| 煉金魔女 | 只有常數、陣營與說明 |
| 狼鴉之爪 | 只有常數、陣營與說明 |
| 魔術師 | 只有常數、陣營與說明 |
| 孤獨少女 | 只有常數、陣營與說明 |
| 咒狐 | 只有常數、陣營與說明 |

## 板型盤點

### 固定 12 人板型（23）

| Board ID | 顯示名稱 | 角色組合（壓縮） |
|---|---|---|
| `standard` | 12人標準場 | 狼×4、民×4、預、女、獵、愚 |
| `wolf_beauty_knight` | 狼美人騎士 | 狼×3、狼美、民×4、預、女、騎、守 |
| `wolf_king_guard` | 狼王守衛 | 狼×3、狼王、民×4、預、女、獵、守 |
| `wolf_king_dreamer` | 狼王攝夢人 | 狼×3、狼王、民×4、預、女、獵、攝夢 |
| `evil_knight` | 惡夜騎士 | 狼×3、惡夜、民×4、預、女、獵、守 |
| `gargoyle_gravekeeper` | 石像鬼守墓人 | 狼×3、石像鬼、民×4、預、女、獵、守墓 |
| `crimson_demon_hunter` | 赤月獵魔人 | 狼×3、赤月、民×4、預、女、獵魔、愚 |
| `nightmare` | 噩夢之影 | 狼×3、噩夢、民×4、預、女、獵、攝夢 |
| `eternal_order` | 永序之輪 | 狼×3、蝕時、民×4、預、女、守、定序 |
| `pure_white` | 純白夜影 | 狼×3、狼巫、民×4、純白、女、獵、守 |
| `time_wave` | 時波之亂 | 狼×3、寂夜、民×4、預、女、守、白晝 |
| `animal_dream` | 動物夢境 | 狼×3、狼美、羊駝×4、白貓、子狐、熊、河豚 |
| `hunter_sun` | 獵日逐光 | 狼×3、蝕日、民×4、預、女、攝夢、流光 |
| `awakened_night` | 覺醒之夜 | 狼×3、夜貴、民×4、預、女、獵魔、覺醒愚者 |
| `fragrance_fate` | 尋香識命 | 狼×3、尋香、民×4、覺醒預、女、獵、守 |
| `awakened_wolf_king` | 覺醒狼王 | 狼×3、覺醒狼王、民×4、預、女、商、攝夢 |
| `mirror_maze` | 鏡隱迷蹤 | 狼×3、覺醒隱狼、民×4、魔鏡、女、獵、守 |
| `awakened_witch` | 覺醒女巫 | 狼×3、覺醒狼王、民×4、預、覺醒女巫、獵、守 |
| `dark_night_stars` | 暗夜星辰 | 狼×3、覺醒狼美、民×4、預、女、守、覺醒獵 |
| `awakened_lonely_girl` | 覺醒孤獨少女 | 狼×4、民×3、預、女、攝夢、獵、覺醒孤女 |
| `awakened_gargoyle` | 覺醒石像鬼 | 狼×2、覺醒石像鬼、民×4、預、女、獵、守、守墓 |
| `moonfall_abyss` | 月墜光淵 | 狼×3、覺醒白狼王、民×4、預、女、獵、覺醒守 |
| `awakened_dreamer` | 覺醒攝夢人 | 覺醒石像鬼、狼王、狼、民×4、預、女、獵、守墓、覺醒攝夢 |

### 彈性板型（3 個 ID）

| Board ID | 人數 | 實際行為 |
|---|---:|---|
| `auto` | 3–20 | 依人數放 1/3 左右狼人，6 人起加入狼王／女巫／獵人，10 人起加入商人，其餘平民 |
| `wolf_king` | 最少 5 | 狼王、預言家、女巫、獵人，補普通狼人與平民 |
| `merchant` | 最少 7 | 狼王、預言家、女巫、獵人、商人，補普通狼人與平民 |

## 階段盤點

| 常數 | 值 | 進入點 | 離開條件 | 問題 |
|---|---|---|---|---|
| `PHASE_WAITING` | `waiting` | 建立 `WerewolfGame` | 房主開始或關閉 | 無準備／座位／觀戰模型 |
| `PHASE_STARTING` | `starting` | 發牌完成 | 10 秒 sleep 或房主強制 | 計時不持久、依賴程序 |
| `PHASE_NIGHT_1` | `night_actions` | `start_night()` | 所有 required task 完成 | 沒有全域 timeout，可能永久卡住 |
| `PHASE_NIGHT_2` | `night_witch` | 狼刀與一般技能完成 | 女巫／幸運兒完成 | 同樣沒有可靠 phase deadline |
| `PHASE_DAY` | `day` | 夜間傷害結算完成 | 投票／特殊技能／結束票 | 沒有發言順序或討論 deadline |
| `PHASE_SHOOT` | `role_shoot` | 可開槍角色死亡 | 所有槍手操作完成 | View 300 秒後沒有伺服器自動處理 |
| `PHASE_ENDED` | `ended` | 勝負、abort、關閉大廳 | 無 | Cog 會移除局；沒有可重啟房間狀態 |

## 可直接抽離的純規則候選

以下程式沒有直接呼叫 Discord API，但仍需先換成可序列化模型，才能放入 `werewolf_engine`：

- `catalog.py` 的陣營資料、角色能力說明與板型組合。
- `roles.py` 的 `Role` 能力旗標、藥與已使用狀態；不包含 `Player.user`。
- `game.py` 的：
  - `get_alive_players()`、`get_players_by_role()`、`get_alive_role()`。
  - `get_active_wolves()`。
  - `get_action_targets()`、`get_night_action_limit()`。
  - `_is_awakened_guarded()`、`_target_acted_tonight()`。
  - `assign_roles()`、`_prepare_assigned_role_state()`。
  - `_role_action_available()`、`_disabled_night_ids()`。
  - `get_required_night_tasks()`、`get_pending_night_tasks()`。
  - `is_phase_2_done()`、`record_phase_2_action()`。
  - `_get_bear_notice()` 的判定部分、`get_shooter_deaths()`。
  - `_mark_day_death()` 的狀態轉移部分。
  - `check_winner()`。
  - `log_event()` 的概念，但 payload 必須改用 ID/key，不保存可見名稱或中文句子。

不能整段直接搬移的高價值規則包括 `handle_night_action()`、`check_phase_1_end()`、`start_day()`、`tally_votes()`、`_resolve_exile()` 與射擊流程；它們必須拆成「純 command handler／resolver」和「Discord adapter」。

## 必須重寫的 Discord UI

- `views.py` 全檔：所有 View、Button、Select、Embed 與硬編碼文字。
- `replay.py` 的 Discord View／Select／Embed；事件資料本身另行抽離。
- `skills.py` 的所有互動回應、選單、協助者投票面板與 mention。
- `game.py` 中動態建立的 View／Button／Select、ephemeral 回應、頻道公告、DM 與私人 Thread。
- `werewolf_bot.py` 的大廳／狀態／規則呈現；保留指令入口作為舊 Bot adapter。

Activity 前端不得複製這些方法內的規則；它只呈現後端給該玩家的可見投影並送出 command。
