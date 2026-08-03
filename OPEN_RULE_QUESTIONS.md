# 尚待確認的狼人殺規則

基準：`08735ea`
原則：下列項目若未確認，抽離核心時先保持舊程式行為，並以明確 compatibility setting 表示；除非測試證明是程式錯誤，否則不擅自更改。

## 高優先：會影響核心模型或勝負

| 規則名稱 | 目前程式行為 | 可能選項 | 影響範圍 | 建議選項 |
|---|---|---|---|---|
| 好人／狼人勝利條件 | `check_winner()`：狼人全滅＝好人勝；神或村民任一類全滅＝狼人勝；狼數大於等於神+村民＝狼人勝 | A. 屠邊；B. 屠城；C. 人數 parity；D. 每板型獨立 | `BoardConfiguration`、勝負、測試、結算 | 板型明確設定；legacy `standard` 先保留目前「屠邊 + parity」行為，待確認官方規則 |
| 第三方勝利 | 覺醒孤獨少女初始為第三方，但 `check_winner()` 不計第三方，也沒有第三方 winner；她可轉狼或繼承角色 | A. 只有轉化／繼承後跟隨陣營；B. 獨立勝利；C. 與偶像共同勝；D. 板型規則 | 勝負、角色狀態、結算、投影 | 明確定義每個第三方角色的 `win_condition`; 在確認前保留舊轉化／繼承行為，不宣稱第三方勝利完整 |
| 中立／第三方對 parity 的計數 | 現有 parity 只算神與村民，存活第三方不在分母 | A. 不計；B. 計入非狼；C. 依其目前勝利陣營；D. 板型設定 | 勝負邊界 | 依角色即時 `win_team`／板型設定，不直接用 camp 推斷 |
| 狼票平票 | 同票最高目標由 `random.choice()` 隨機成為狼刀目標 | A. 隨機；B. 空刀；C. 重投；D. 狼王／指定玩家決定 | 夜間 resolver、RNG、事件、測試 | 先保留 legacy random，且注入 RNG 使測試可重現；正式規則確認後板型化 |
| 白天放逐平票 | 同票最高時無人出局，立即進下一夜 | A. 無人出局；B. PK 發言後重投；C. 多輪重投；D. 房間設定 | day phase、發言、timer、UI | MVP 若求簡化可保留「無人出局」；若要官方競技流程需新增 PK 子階段 |
| 女巫自救 | 所有回合都禁止女巫救自己 | A. 永不自救；B. 首夜可；C. 僅特定人數／板型可；D. 房間設定 | target validation、BoardConfiguration、UI reason | 板型欄位 `witch_self_save`; legacy profile 設 `never` |
| 同守同救 | 女巫救藥直接移除狼刀，守衛也會擋狼刀；兩者同時指向同一人仍存活，沒有「同守同救死亡」 | A. 存活；B. 同守同救死亡；C. 只耗資源；D. 板型設定 | 夜間優先序、傷害 resolver | 板型欄位明確化；確認前保留存活 |
| 守衛保護範圍 | 一般守衛只擋 `damage_type="wolf"`；不擋毒、查殺或其他技能 | A. 只擋狼刀；B. 擋所有夜間傷害；C. 依技能／板型 | effect/damage type | 保留只擋狼刀，並用 typed damage/effect 寫清楚 |
| 夜間效果優先序 | 所有效果集中在 `start_day()`，順序由程式碼固定：封鎖／保護／魅惑／狼刀／毒／查殺／獵魔／夢語／夜僕／連鎖等 | A. 完全沿用；B. 依官方 priority table；C. 每板型 priority | 最關鍵 resolver、死亡順序、復盤 | 先把目前順序寫成可測 priority table，再逐條和規則來源核對 |
| 多重死亡與勝負時點 | 夜間全部結算後才檢查勝負；白天部分技能會在每段後檢查 | A. 完整 action chain 後；B. 每個 effect 後；C. 特定技能插入勝負判定 | death queue、shoot、third party、replay | 一次完整不可分割 resolution chain 後判勝，除非板型規則明示中止後續效果 |
| Activity MVP 板型 | 需求說 6–12 人、先一套經典板；現有 `standard` 固定 12 人，`auto` 3–20 且角色組合不是明確經典表 | A. MVP 只 12 人 standard；B. 定義 6/7/8/9/10/11/12 經典板；C. 沿用 auto | BoardConfiguration、房間人數、測試、UI | 先選一個明確可測板型。若要 6–12，每個人數建立固定 board ID，不以隱含公式代替正式配置 |

## 角色觸發與死亡規則

| 規則名稱 | 目前程式行為 | 可能選項 | 影響範圍 | 建議選項 |
|---|---|---|---|---|
| 獵人可開槍死因 | 一般獵人夜死可開槍，毒死不能；白天投票／獵人射擊等連鎖可觸發，但河豚反擊被排除 | A. 狼刀／放逐可；B. 除毒外都可；C. 依每個 cause；D. 板型設定 | death cause enum、shoot queue | 建立明確 cause → ability permission matrix，先逐項鎖定 legacy 行為 |
| 狼王可開槍死因 | 與一般 `can_shoot` 流程共用；夜間毒死不能，其他多種死亡可能可開槍 | A. 放逐／獵人射殺；B. 狼刀、自爆等不同；C. 板型設定 | shoot rules、特殊狼 | 不用共用布林推斷；每角色定義 trigger set，先保留既有結果 |
| 覺醒獵人死因 | 程式允許任何夜間死因開啟巡獵，且白天多數鏈也可；描述亦寫「任何原因」 | A. 完全任何原因；B. 排除特定自殺／反擊；C. 板型設定 | shoot queue、night special suppression | 請確認「任何原因」是否包括自爆、河豚、反傷、強制結束；未確認先維持現有測試範圍 |
| 愚者陣營 | 現有愚者屬神職，首次被放逐免死並失去投票權 | A. 神職；B. 村民；C. 第三方；D. 板型不同 | victory、board composition | 保留現有神職，直到板型來源確認 |
| 定序王子發動輪次 | 角色說明寫「首輪放逐後」，但 `_prompt_order_prince()` 只檢查未用技能，任何輪次都可能發動 | A. 僅第一輪；B. 全局任一輪一次；C. 板型設定 | action availability、測試 | 這是疑似實作與說明不一致；先補 characterization test 並請確認，不直接修 |
| 河豚清晨翻牌條件 | 目錄說明有「特殊條件下會於清晨翻牌出局」，但程式只明確實作被放逐後選擇帶走投票者；未見完整清晨條件 | A. 只實作放逐；B. 補官方清晨條件；C. 移除宣稱 | role handler、night resolution、文件 | 先標成部分實作；取得規則來源後再補 |
| 蝕日侍女可吞噬技能 | 只對女巫、預言家、攝夢人、流光伯爵有具體複製操作；其他好人會被 disable，但侍女得到 `no_skill` | A. 僅支援白名單；B. 應支援所有有技能角色；C. 板型限制 | action handler、role registry | 以 capability registry 定義；在清單確認前維持目前白名單並在 UI 說明限制 |
| 覺醒隱狼模仿後身分 | 直接修改 `role.name` 為動態中文，保留狼 camp 並取得部分目標技能／射擊 | A. 仍是覺醒隱狼，只複製 ability；B. 完整變成目標角色但狼勝；C. 依官方規則 | role ID、projection、replay、serialization | 穩定 ID 保持 `awakened_hidden_wolf`，另存 `mimicked_role_id`；實際能力範圍待確認 |
| 覺醒石像鬼轉化 | 目標當夜結束轉狼、原技能失效、下一夜才相認；首夜只可選相鄰座位 | A. 維持；B. 立即相認；C. 保留部分技能；D. 座位規則不同 | seat model、projection、wolf team | 先保持現有；Activity 必須建立穩定座位順序 |
| 白貓續命 | 首次死亡不立即死，加入 pending，下一次放逐投票結束後正式出局 | A. 固定；B. 依死亡原因；C. 特定板型例外 | pending effect、winner timing | 把它建成明確 delayed death effect，先保留現有 |

## 白天、資訊與主持

| 規則名稱 | 目前程式行為 | 可能選項 | 影響範圍 | 建議選項 |
|---|---|---|---|---|
| 警長／警徽 | 只有 catalog 說明；沒有上警、退水、投票、警徽流、移交／撕毀、1.5 票實作 | A. MVP 不含；B. MVP 含完整警長；C. 房間可選 | phase graph、vote weight、speech、UI | MVP 明確排除並在 capability 中標 unavailable；後續以獨立 phase/role modifier 實作 |
| 白天發言順序 | 只送討論提示後立即顯示投票面板；沒有順序、發言者或倒數 | A. 自由討論；B. 固定座位順序；C. 警長指定方向；D. 房間設定 | timers、voice commands、UI | MVP 可先自由討論 + 房主開始投票；若要自動主持需新增 discussion/speech/vote 子階段 |
| 投票公開程度 | 投票時公開「某人已投票」但不公開目標；全員投完後公布每人投向 | A. 全公開；B. 匿名只公布票數；C. 即時公開投向；D. 板型／房間設定 | event visibility、replay、UI | 建立 `vote_visibility` 設定；legacy profile 為結算後公開明票 |
| 死亡是否翻牌 | 夜晚公告只顯示死亡姓名；白天放逐、射擊等多處會顯示角色；部分特殊角色又刻意不翻牌 | A. 一律翻；B. 一律不翻；C. 依死因／角色／板型 | public projection、replay | 不能由 presenter 猜；BoardConfiguration + role override 明確設定，legacy 行為先逐死因鎖定 |
| 死亡玩家資訊權限 | 現在 Discord Bot 沒有持久私密 projection；死者仍可按查看本人身分，遊戲結束公開全部 | A. 死者只看原資訊；B. 死後看全局；C. 房間設定；D. 觀戰另計 | projection security、spectator | 預設死者不看額外秘密；房間設定可於結束後公開 |
| 狼人討論方式 | 每夜建立 Discord 私人 Thread、天亮刪除 | A. Activity 私密聊天室；B. 保留 Discord Thread；C. 只靠語音；D. 混合 | Bot integration、Activity chat、安全 | Activity MVP 可保留 Bot Thread 作 adapter；若做 Activity chat，訊息必須 server-authorized wolf-team scope |
| 玩家提議強制結束 | 只在白天，過半數存活玩家同意即 `end_game("無 (強制結束)")` 並公開全部身分 | A. 保留並公開；B. 房主／管理員確認；C. 不公開；D. 任意階段 | ended reason、privacy、voice cleanup | 核心用 `ended_reason=player_vote_abort`，不要偽裝 winner；是否公開依房間規則 |

## 房間、計時與連線

| 規則名稱 | 目前程式行為 | 可能選項 | 影響範圍 | 建議選項 |
|---|---|---|---|---|
| 房間唯一鍵 | Cog 以 `guild_id` 索引，一個 guild 只能一局 | A. guild；B. voice channel；C. Activity instance；D. guild+channel+instance | RoomState、auth、Bot integration | Activity 以驗證後的 instance/channel/guild binding 產生 opaque room ID；不要信任前端自填 |
| 房主離開／斷線 | 等待中可退出，但 host 本人退出不會轉移房主；遊戲中不能離開，沒有 reconnect model | A. 自動轉移；B. 關房；C. 保留 host 一段時間；D. co-host | room service、timer、UI | 等待中轉移給最早加入者；遊戲中保留 host 權限並允許 reconnect，逾時再依設定處理 |
| 準備與觀戰 | 沒有 ready、spectator、seat claim | A. 全部加入即算準備；B. 顯式 ready；C. 觀戰；D. 房主可強制 | RoomState、開始驗證、UI | Activity 使用顯式 ready；觀戰第一版可禁用但 schema 預留 |
| 身分確認倒數 | 發牌後固定 `asyncio.sleep(10)`，程序重啟即遺失 | A. 固定 10 秒；B. 全員確認即提前；C. 房間設定 | server timer、reconnect | 後端保存 deadline；全員確認可提前，但 deadline 到仍前進 |
| 夜晚／白天 timeout | 夜晚與投票主要靠玩家全部完成；沒有 phase deadline。部分 View 300 秒 timeout 後沒有自動提交，可能永久卡住 | A. 強制 deadline + 預設跳過；B. 房主手動；C. 永久等待 | timer service、commands、reconnect | 必須有 server deadline；到期對未提交者套明確 default（通常 skip／棄票），並產生事件 |
| 最後一秒 action | 沒有 `phase_ends_at` 與 revision；callback 只看當下 phase／內部欄位 | A. 以 server received time；B. client timestamp；C. grace window | concurrency、idempotency | 只信 server received time，搭配 expected revision；是否給小 grace 明確設定 |
| 重複 request／重播 | Discord interaction 以已投票／已 action 等狀態阻擋部分重複，沒有 request ID | A. request ID cache；B. revision；C. 兩者 | WebSocket security、reconnect | 同時使用 request ID 冪等結果 + expected revision；玩家 scope 下唯一 |
| 全部提早完成 | phase 1/2 與投票在全部完成時立即前進 | A. 立即；B. 等 deadline；C. 房間設定 | timer cancellation、UX | 保留立即前進；timer transition 必須 compare-and-set，避免重複觸發 |
| 玩家短暫離開語音 | 不影響核心玩家狀態，也沒有通知／逾時策略 | A. 允許重連；B. 自動死亡；C. 轉 AI；D. 暫停 | room presence、voice、fairness | MVP 允許 grace reconnect，不自動重新發牌或死亡；逾時策略需房間設定 |

## 語音與音效

| 規則名稱 | 目前程式行為 | 可能選項 | 影響範圍 | 建議選項 |
|---|---|---|---|---|
| 白天語音控制 | 天亮後存活玩家恢復遊戲開始前各自 mute 狀態，死亡玩家保持 server mute；沒有逐一發言控制 | A. 自由發言；B. 只解鎖當前發言者；C. 房間設定 | voice command、speech phase | legacy 為自由發言；自動主持模式新增 speaker queue，不改核心勝負規則 |
| 原始 mute 狀態 | 只在找到 guild member 且有 voice state 時保存；結束／abort 時嘗試恢復 | A. 保存 server mute；B. 同時保存 self mute/deaf（Bot 無法改 self）；C. 只恢復被 Bot 改動者 | Bot adapter cleanup | 保存並恢復 Bot 可控制的 server mute，使用 voice lease 與冪等 restore；記錄失敗但不吞例外 |
| 音效 key 與素材 | 規則直接要求 `night.mp3`、`voice_night_start.mp3`；後者目前不存在，前者授權不明 | A. 固定 key + locale asset；B. TTS；C. 無語音 | event schema、assets、license | 核心只發 `night_start` 等 key；先更換有授權素材，缺檔時安全退化成文字 |

## 資料來源與本地化

| 規則名稱 | 目前程式行為 | 可能選項 | 影響範圍 | 建議選項 |
|---|---|---|---|---|
| 23 套「官方」板型來源 | `catalog.py` 註解宣稱依截至 2026-07 正式上線資料，README 也稱官方；儲存庫沒有來源 URL、版本、擷取日期或規則逐條引用 | A. 補官方來源；B. 改稱專案板型；C. 由使用者提供規則文件 | 正確性、授權、OPEN questions | 在動特殊板型規則前補 `RULE_SOURCES.md` 或資料欄位；無法驗證者不要擴大「官方」宣稱 |
| 角色／板型顯示名稱 | 角色中文名稱是邏輯 ID；板型 ID 已是 ASCII | A. 一次全面改 ID；B. alias 漸進遷移 | serialization、i18n、舊測試 | 採 alias 漸進遷移：寫新 ID、讀新舊值、UI 用 locale key |
| 公共公告語言 | 所有 Bot 公告固定繁中 | A. 房間語言；B. 發起者語言；C. 每人不同（公共訊息不可能） | localization、voice | 公共公告／主持／語音是房間設定；私密 UI 採玩家 locale |

## 建議的確認順序

1. 先確認 MVP 板型、人數與勝利條件。
2. 確認女巫／守衛／狼票／投票平票等核心優先序。
3. 確認獵人、狼王、第三方與死亡翻牌。
4. 確認發言、警長、語音、timeout 與斷線政策。
5. 最後逐套特殊／覺醒板型補來源與差異規則。

若只要開始階段 2 的資料模型，可以先不回答全部問題；但模型必須以設定與 typed effect 預留差異，不能把目前單一行為硬編成所有板型的永久規則。
