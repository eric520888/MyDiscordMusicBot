"""網易《狼人殺官方》角色與 12 人競技板型資料。

板型池依 2025 官方賽事公告整理；角色說明以官方角色卡與板型公告為準。
這個模組只放不可變的規則資料，遊戲流程實作位於 game.py。
"""

from dataclasses import dataclass


CAMP_WOLF = "狼人陣營"
CAMP_GOD = "神職陣營"
CAMP_VILLAGER = "村民陣營"
CAMP_THIRD = "第三方陣營"


@dataclass(frozen=True)
class RoleInfo:
    camp: str
    description: str


@dataclass(frozen=True)
class BoardSpec:
    name: str
    roles: tuple[str, ...]
    description: str
    official: bool = True

    @property
    def player_count(self) -> int:
        return len(self.roles)


# 基礎角色
ROLE_WEREWOLF = "狼人"
ROLE_VILLAGER = "平民"
ROLE_SEER = "預言家"
ROLE_WITCH = "女巫"
ROLE_HUNTER = "獵人"
ROLE_FOOL = "愚者"
ROLE_GUARD = "守衛"
ROLE_WOLF_KING = "狼王"
ROLE_WOLF_BEAUTY = "狼美人"
ROLE_KNIGHT = "騎士"
ROLE_DREAMER = "攝夢人"
ROLE_EVIL_KNIGHT = "惡夜騎士"
ROLE_GARGOYLE = "石像鬼"
ROLE_GRAVEKEEPER = "守墓人"
ROLE_CRIMSON_APOSTLE = "赤月使徒"
ROLE_DEMON_HUNTER = "獵魔人"
ROLE_NIGHTMARE = "噩夢之影"
ROLE_TIME_WOLF = "蝕時狼妃"
ROLE_ORDER_PRINCE = "定序王子"
ROLE_WOLF_WITCH = "狼巫"
ROLE_PURE_WHITE = "純白之女"
ROLE_NIGHT_MENTOR = "寂夜導師"
ROLE_DAY_SCHOLAR = "白晝學者"
ROLE_ALPACA = "羊駝"
ROLE_WHITE_CAT = "白貓"
ROLE_YOUNG_FOX = "子狐"
ROLE_BEAR = "熊"
ROLE_PUFFERFISH = "河豚"
ROLE_ECLIPSE_MAID = "蝕日侍女"
ROLE_LIGHT_EARL = "流光伯爵"
ROLE_NIGHT_NOBLE = "夜之貴族"
ROLE_AWAKENED_FOOL = "覺醒愚者"
ROLE_FRAGRANCE_PHANTOM = "尋香魅影"
ROLE_AWAKENED_SEER = "覺醒預言家"
ROLE_AWAKENED_WOLF_KING = "覺醒狼王"
ROLE_MIRROR_GIRL = "魔鏡少女"
ROLE_AWAKENED_HIDDEN_WOLF = "覺醒隱狼"
ROLE_AWAKENED_WITCH = "覺醒女巫"
ROLE_AWAKENED_WOLF_BEAUTY = "覺醒狼美人"
ROLE_AWAKENED_HUNTER = "覺醒獵人"

# 舊版仍保留的朋友局角色。
ROLE_MERCHANT = "奇跡商人"
ROLE_HIDDEN_WOLF = "隱狼"
ROLE_WHITE_WOLF_KING = "白狼王"
ROLE_CUPID = "丘比特"
ROLE_THOUSAND_FACES = "千面人"
ROLE_SHERIFF = "警長"
ROLE_CROW = "烏鴉"
ROLE_ALCHEMIST = "煉金魔女"
ROLE_WOLF_CROW_CLAW = "狼鴉之爪"
ROLE_MAGICIAN = "魔術師"
ROLE_LONELY_GIRL = "孤獨少女"
ROLE_CURSE_FOX = "咒狐"


ROLE_CATALOG: dict[str, RoleInfo] = {
    ROLE_WEREWOLF: RoleInfo(CAMP_WOLF, "每晚與狼隊共同選擇一名玩家襲擊。"),
    ROLE_VILLAGER: RoleInfo(CAMP_VILLAGER, "沒有夜間技能，依靠發言、推理與投票找出狼人。"),
    ROLE_SEER: RoleInfo(CAMP_GOD, "每晚查驗一名玩家，得知其屬於好人或狼人陣營。"),
    ROLE_WITCH: RoleInfo(CAMP_GOD, "持有一瓶解藥與一瓶毒藥；每晚最多使用一瓶，且不能自救。"),
    ROLE_HUNTER: RoleInfo(CAMP_GOD, "被放逐或遭狼襲死亡時可開槍帶走一人；被毒殺不能開槍。"),
    ROLE_FOOL: RoleInfo(CAMP_GOD, "首次被放逐時翻牌免死，之後失去投票權。"),
    ROLE_GUARD: RoleInfo(CAMP_GOD, "每晚守護一名玩家免受狼襲，不能連續兩晚守護同一人。"),
    ROLE_WOLF_KING: RoleInfo(CAMP_WOLF, "可以參與狼襲；被放逐或遭獵人射殺時可開槍，被毒殺不能開槍。"),
    ROLE_WOLF_BEAUTY: RoleInfo(CAMP_WOLF, "每晚魅惑一名好人；被放逐或遭獵人射殺時，被魅惑者一同出局。"),
    ROLE_KNIGHT: RoleInfo(CAMP_GOD, "白天投票前可決鬥一人：狼人出局並入夜；好人則騎士出局並繼續白天。"),
    ROLE_DREAMER: RoleInfo(CAMP_GOD, "每晚夢遊一人使其免疫夜間傷害；連續兩晚夢同一人則該玩家死亡，攝夢人死亡時夢遊者殉死。"),
    ROLE_EVIL_KNIGHT: RoleInfo(CAMP_WOLF, "夜間不會死亡；全局一次反傷查驗自己的預言家或毒殺自己的女巫。"),
    ROLE_GARGOYLE: RoleInfo(CAMP_WOLF, "與狼隊互不相認；每晚查驗一名玩家的具體身分，其他狼人全滅後才能狼襲。"),
    ROLE_GRAVEKEEPER: RoleInfo(CAMP_GOD, "每晚得知上一個被放逐的玩家屬於好人或狼人陣營。"),
    ROLE_CRIMSON_APOSTLE: RoleInfo(CAMP_WOLF, "白天可自曝入夜並封印當晚好人技能；作為最後一狼被放逐時延至天亮才死亡。"),
    ROLE_DEMON_HUNTER: RoleInfo(CAMP_GOD, "第二晚起可狩獵一人：狼人死亡；好人則自己死亡。免疫女巫毒藥。"),
    ROLE_NIGHTMARE: RoleInfo(CAMP_WOLF, "每晚最先恐懼一人使其當晚不能行動；恐懼狼人會使狼隊無法襲擊，不能連續選同一人。"),
    ROLE_TIME_WOLF: RoleInfo(CAMP_WOLF, "每晚封鎖一人；對該人的查驗、毒殺或守護會反彈給施法者，觸發後次夜失去技能。"),
    ROLE_ORDER_PRINCE: RoleInfo(CAMP_GOD, "全局一次，在首輪放逐後翻牌令其復活並重新投票。"),
    ROLE_WOLF_WITCH: RoleInfo(CAMP_WOLF, "每晚查驗一名非狼玩家的具體身分；第二晚起驗到純白之女會使其死亡。"),
    ROLE_PURE_WHITE: RoleInfo(CAMP_GOD, "每晚查驗一人的具體身分；第二晚起驗到狼人會使其死亡。"),
    ROLE_NIGHT_MENTOR: RoleInfo(CAMP_WOLF, "與狼隊隔離；第二晚起可增幅或削弱一人，其他狼人全滅後才能狼襲。"),
    ROLE_DAY_SCHOLAR: RoleInfo(CAMP_GOD, "第二晚起各一次增幅或削弱；增幅使角色額外行動，削弱使其當晚不能行動。"),
    ROLE_ALPACA: RoleInfo(CAMP_VILLAGER, "動物夢境中的普通好人，沒有夜間技能。"),
    ROLE_WHITE_CAT: RoleInfo(CAMP_GOD, "死亡時翻牌並暫時存活，直到下一次放逐投票結束後才真正出局。"),
    ROLE_YOUNG_FOX: RoleInfo(CAMP_GOD, "第二晚起全局一次迷惑一人；若為狼人則狼隊不能襲擊，若為狼美人則不能魅惑。"),
    ROLE_BEAR: RoleInfo(CAMP_GOD, "每天清晨檢查左右相鄰的存活玩家；其中有狼人便向全場咆哮。"),
    ROLE_PUFFERFISH: RoleInfo(CAMP_GOD, "被放逐後可翻牌帶走所有投票給自己的人；特殊條件下會於清晨翻牌出局。"),
    ROLE_ECLIPSE_MAID: RoleInfo(CAMP_WOLF, "第二晚起吞噬一名好人的技能並於當晚使用；目標失去技能，不能連續選同一人。"),
    ROLE_LIGHT_EARL: RoleInfo(CAMP_GOD, "第二晚起庇護另一名玩家，使其免疫當晚所有夜間傷害，不能連續選同一人。"),
    ROLE_NIGHT_NOBLE: RoleInfo(CAMP_WOLF, "第二晚起指定一名夜僕；若未被獵魔人解除，夜僕在下一晚天亮時死亡。"),
    ROLE_AWAKENED_FOOL: RoleInfo(CAMP_GOD, "秘密之身可免疫一次放逐，或每晚保護一名玩家抵消一次傷害；成功後失去能力。"),
    ROLE_FRAGRANCE_PHANTOM: RoleInfo(CAMP_WOLF, "與狼隊隔離；每晚綁定兩人，其中一人出局時另一人殉死，全局觸發一次。"),
    ROLE_AWAKENED_SEER: RoleInfo(CAMP_GOD, "每晚同時查看兩名玩家，得知兩人之中是否至少有一名狼人。"),
    ROLE_AWAKENED_WOLF_KING: RoleInfo(CAMP_WOLF, "持有兩枚狼王爪，可轉交存活狼隊友；爪的持有者出局時可開槍。"),
    ROLE_MIRROR_GIRL: RoleInfo(CAMP_GOD, "每晚查驗一名未查過玩家的具體身分。"),
    ROLE_AWAKENED_HIDDEN_WOLF: RoleInfo(CAMP_WOLF, "與狼隊隔離；其餘狼人全滅後模仿一名玩家，取得身分與夜間技能。"),
    ROLE_AWAKENED_WITCH: RoleInfo(CAMP_GOD, "有一瓶解藥與三次調毒；調毒需由未協助過的玩家共同決定是否生效。"),
    ROLE_AWAKENED_WOLF_BEAUTY: RoleInfo(CAMP_WOLF, "每隔一晚施放挽歌幻象；首次面臨出局時由當夜魅惑者替代出局且無法被守護，全局生效一次。"),
    ROLE_AWAKENED_HUNTER: RoleInfo(CAMP_GOD, "因任何原因出局都可巡獵，選擇帶走自己左側或右側第一名存活狼人；夜間出局會令特殊狼人技能失效。"),
    ROLE_MERCHANT: RoleInfo(CAMP_GOD, "全局一次賜予玩家查驗、毒藥或守衛技能；選中狼人會遭反噬。"),
    ROLE_HIDDEN_WOLF: RoleInfo(CAMP_WOLF, "預言家查驗顯示為好人；知曉狼隊但在其他狼人全滅前不參與襲擊。"),
    ROLE_WHITE_WOLF_KING: RoleInfo(CAMP_WOLF, "白天可自曝並帶走一名玩家；以其他方式出局不能發動技能。"),
    ROLE_CUPID: RoleInfo(CAMP_THIRD, "首夜連結兩名戀人；其中一人死亡時另一人殉情，特殊組合會形成第三方。"),
    ROLE_THOUSAND_FACES: RoleInfo(CAMP_THIRD, "首夜從兩張候選身分中選擇一張；候選中有狼人時必須選狼人。"),
    ROLE_SHERIFF: RoleInfo(CAMP_GOD, "額外身分：放逐票計 1.5 票並於發言順序中最後發言。"),
    ROLE_CROW: RoleInfo(CAMP_GOD, "每晚詛咒一人，使其隔天被額外計一票；不能連續詛咒同一人。"),
    ROLE_ALCHEMIST: RoleInfo(CAMP_GOD, "全局各一次施放迷霧與靈蛇；可製造三個狼襲候選，或得知並救活狼襲目標。"),
    ROLE_WOLF_CROW_CLAW: RoleInfo(CAMP_WOLF, "存活狼人少於三名後解封；全局一次額外襲擊，無視一般保護。"),
    ROLE_MAGICIAN: RoleInfo(CAMP_GOD, "每晚交換兩名玩家的號碼，使當晚指向兩人的技能目標互換。"),
    ROLE_LONELY_GIRL: RoleInfo(CAMP_THIRD, "首夜選擇偶像，自己的勝利條件跟隨偶像所屬陣營。"),
    ROLE_CURSE_FOX: RoleInfo(CAMP_THIRD, "免疫狼人襲擊，但被預言家查驗時會死亡。"),
}


def _roles(*items: tuple[str, int]) -> tuple[str, ...]:
    result: list[str] = []
    for role, count in items:
        result.extend([role] * count)
    return tuple(result)


BOARD_AUTO = "auto"
BOARD_STANDARD = "standard"
BOARD_WOLF_BEAUTY_KNIGHT = "wolf_beauty_knight"
BOARD_WOLF_KING_GUARD = "wolf_king_guard"
BOARD_WOLF_KING_DREAMER = "wolf_king_dreamer"
BOARD_EVIL_KNIGHT = "evil_knight"
BOARD_GARGOYLE_GRAVEKEEPER = "gargoyle_gravekeeper"
BOARD_CRIMSON_DEMON_HUNTER = "crimson_demon_hunter"
BOARD_NIGHTMARE = "nightmare"
BOARD_ETERNAL_ORDER = "eternal_order"
BOARD_PURE_WHITE = "pure_white"
BOARD_TIME_WAVE = "time_wave"
BOARD_ANIMAL_DREAM = "animal_dream"
BOARD_HUNTER_SUN = "hunter_sun"
BOARD_AWAKENED_NIGHT = "awakened_night"
BOARD_FRAGRANCE_FATE = "fragrance_fate"
BOARD_AWAKENED_WOLF_KING = "awakened_wolf_king"
BOARD_MIRROR_MAZE = "mirror_maze"
BOARD_AWAKENED_WITCH = "awakened_witch"
BOARD_DARK_NIGHT_STARS = "dark_night_stars"

# 相容舊設定名稱。
BOARD_WOLF_KING = "wolf_king"
BOARD_MERCHANT = "merchant"


BOARD_SPECS: dict[str, BoardSpec] = {
    BOARD_STANDARD: BoardSpec("🔮 12人標準場", _roles((ROLE_WEREWOLF, 4), (ROLE_VILLAGER, 4), (ROLE_SEER, 1), (ROLE_WITCH, 1), (ROLE_HUNTER, 1), (ROLE_FOOL, 1)), "預女獵愚經典板"),
    BOARD_WOLF_BEAUTY_KNIGHT: BoardSpec("💋 狼美人騎士", _roles((ROLE_WEREWOLF, 3), (ROLE_WOLF_BEAUTY, 1), (ROLE_VILLAGER, 4), (ROLE_SEER, 1), (ROLE_WITCH, 1), (ROLE_KNIGHT, 1), (ROLE_GUARD, 1)), "魅惑殉情與白天決鬥"),
    BOARD_WOLF_KING_GUARD: BoardSpec("👑 狼王守衛", _roles((ROLE_WEREWOLF, 3), (ROLE_WOLF_KING, 1), (ROLE_VILLAGER, 4), (ROLE_SEER, 1), (ROLE_WITCH, 1), (ROLE_HUNTER, 1), (ROLE_GUARD, 1)), "雙槍與守護博弈"),
    BOARD_WOLF_KING_DREAMER: BoardSpec("🌙 狼王攝夢人", _roles((ROLE_WEREWOLF, 3), (ROLE_WOLF_KING, 1), (ROLE_VILLAGER, 4), (ROLE_SEER, 1), (ROLE_WITCH, 1), (ROLE_HUNTER, 1), (ROLE_DREAMER, 1)), "夢遊保護與連夢死亡"),
    BOARD_EVIL_KNIGHT: BoardSpec("🛡️ 惡夜騎士", _roles((ROLE_WEREWOLF, 3), (ROLE_EVIL_KNIGHT, 1), (ROLE_VILLAGER, 4), (ROLE_SEER, 1), (ROLE_WITCH, 1), (ROLE_HUNTER, 1), (ROLE_GUARD, 1)), "反傷預言家與女巫"),
    BOARD_GARGOYLE_GRAVEKEEPER: BoardSpec("🪦 石像鬼守墓人", _roles((ROLE_WEREWOLF, 3), (ROLE_GARGOYLE, 1), (ROLE_VILLAGER, 4), (ROLE_SEER, 1), (ROLE_WITCH, 1), (ROLE_HUNTER, 1), (ROLE_GRAVEKEEPER, 1)), "孤立狼神與放逐查驗"),
    BOARD_CRIMSON_DEMON_HUNTER: BoardSpec("🌕 赤月獵魔人", _roles((ROLE_WEREWOLF, 3), (ROLE_CRIMSON_APOSTLE, 1), (ROLE_VILLAGER, 4), (ROLE_SEER, 1), (ROLE_WITCH, 1), (ROLE_DEMON_HUNTER, 1), (ROLE_FOOL, 1)), "封印與狩獵"),
    BOARD_NIGHTMARE: BoardSpec("🌑 噩夢之影", _roles((ROLE_WEREWOLF, 3), (ROLE_NIGHTMARE, 1), (ROLE_VILLAGER, 4), (ROLE_SEER, 1), (ROLE_WITCH, 1), (ROLE_HUNTER, 1), (ROLE_DREAMER, 1)), "恐懼封技與攝夢"),
    BOARD_ETERNAL_ORDER: BoardSpec("⏳ 永序之輪", _roles((ROLE_WEREWOLF, 3), (ROLE_TIME_WOLF, 1), (ROLE_VILLAGER, 4), (ROLE_SEER, 1), (ROLE_WITCH, 1), (ROLE_GUARD, 1), (ROLE_ORDER_PRINCE, 1)), "技能反彈與放逐回溯"),
    BOARD_PURE_WHITE: BoardSpec("⚪ 純白夜影", _roles((ROLE_WEREWOLF, 3), (ROLE_WOLF_WITCH, 1), (ROLE_VILLAGER, 4), (ROLE_PURE_WHITE, 1), (ROLE_WITCH, 1), (ROLE_HUNTER, 1), (ROLE_GUARD, 1)), "具體查驗與純白狼巫對決"),
    BOARD_TIME_WAVE: BoardSpec("🌓 時波之亂", _roles((ROLE_WEREWOLF, 3), (ROLE_NIGHT_MENTOR, 1), (ROLE_VILLAGER, 4), (ROLE_SEER, 1), (ROLE_WITCH, 1), (ROLE_GUARD, 1), (ROLE_DAY_SCHOLAR, 1)), "增幅與削弱"),
    BOARD_ANIMAL_DREAM: BoardSpec("🐾 動物夢境", _roles((ROLE_WEREWOLF, 3), (ROLE_WOLF_BEAUTY, 1), (ROLE_ALPACA, 4), (ROLE_WHITE_CAT, 1), (ROLE_YOUNG_FOX, 1), (ROLE_BEAR, 1), (ROLE_PUFFERFISH, 1)), "動物角色特殊生存規則"),
    BOARD_HUNTER_SUN: BoardSpec("☀️ 獵日逐光", _roles((ROLE_WEREWOLF, 3), (ROLE_ECLIPSE_MAID, 1), (ROLE_VILLAGER, 4), (ROLE_SEER, 1), (ROLE_WITCH, 1), (ROLE_DREAMER, 1), (ROLE_LIGHT_EARL, 1)), "吞噬技能與全傷害庇護"),
    BOARD_AWAKENED_NIGHT: BoardSpec("🎪 覺醒之夜", _roles((ROLE_WEREWOLF, 3), (ROLE_NIGHT_NOBLE, 1), (ROLE_VILLAGER, 4), (ROLE_SEER, 1), (ROLE_WITCH, 1), (ROLE_DEMON_HUNTER, 1), (ROLE_AWAKENED_FOOL, 1)), "夜僕延時死亡與秘密之身"),
    BOARD_FRAGRANCE_FATE: BoardSpec("🦋 尋香識命", _roles((ROLE_WEREWOLF, 3), (ROLE_FRAGRANCE_PHANTOM, 1), (ROLE_VILLAGER, 4), (ROLE_AWAKENED_SEER, 1), (ROLE_WITCH, 1), (ROLE_HUNTER, 1), (ROLE_GUARD, 1)), "雙人查驗與命運綁定"),
    BOARD_AWAKENED_WOLF_KING: BoardSpec("❄️ 覺醒狼王", _roles((ROLE_WEREWOLF, 3), (ROLE_AWAKENED_WOLF_KING, 1), (ROLE_VILLAGER, 4), (ROLE_SEER, 1), (ROLE_WITCH, 1), (ROLE_HUNTER, 1), (ROLE_DREAMER, 1)), "兩枚可轉移狼王爪"),
    BOARD_MIRROR_MAZE: BoardSpec("🪞 鏡隱迷蹤", _roles((ROLE_WEREWOLF, 3), (ROLE_AWAKENED_HIDDEN_WOLF, 1), (ROLE_VILLAGER, 4), (ROLE_MIRROR_GIRL, 1), (ROLE_WITCH, 1), (ROLE_HUNTER, 1), (ROLE_GUARD, 1)), "具體查驗與模仿"),
    BOARD_AWAKENED_WITCH: BoardSpec("🧪 覺醒女巫", _roles((ROLE_WEREWOLF, 3), (ROLE_AWAKENED_WOLF_KING, 1), (ROLE_VILLAGER, 4), (ROLE_SEER, 1), (ROLE_AWAKENED_WITCH, 1), (ROLE_HUNTER, 1), (ROLE_GUARD, 1)), "協力調毒與狼王爪"),
    BOARD_DARK_NIGHT_STARS: BoardSpec("✨ 暗夜星辰", _roles((ROLE_WEREWOLF, 3), (ROLE_AWAKENED_WOLF_BEAUTY, 1), (ROLE_VILLAGER, 4), (ROLE_SEER, 1), (ROLE_WITCH, 1), (ROLE_GUARD, 1), (ROLE_AWAKENED_HUNTER, 1)), "覺醒魅惑與追獵"),
}


OFFICIAL_BOARD_IDS = tuple(BOARD_SPECS)
