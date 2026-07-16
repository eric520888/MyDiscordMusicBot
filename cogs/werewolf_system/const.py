from pathlib import Path


# 使用檔案位置計算路徑，避免從不同工作目錄啟動 Bot 時找不到音效。
SOUND_FOLDER = str(Path(__file__).resolve().parents[2] / "sounds")

# --- 角色名稱定義 ---
ROLE_WEREWOLF = "狼人"
ROLE_WOLF_KING = "狼王"
ROLE_SEER = "預言家"
ROLE_WITCH = "女巫"
ROLE_HUNTER = "獵人"
ROLE_MERCHANT = "奇跡商人"
ROLE_VILLAGER = "村民"

# --- 陣營定義 ---
CAMP_WOLF = "狼人陣營"
CAMP_GOD = "神職陣營"
CAMP_VILLAGER = "村民陣營"

# --- 遊戲階段定義 ---
PHASE_WAITING = "waiting"
PHASE_STARTING = "starting"
PHASE_NIGHT_1 = "night_wolves_seer_merchant"  # 上半夜
PHASE_NIGHT_2 = "night_witch_lucky"           # 下半夜
PHASE_DAY = "day"
PHASE_SHOOT = "role_shoot"                    # 開槍階段
PHASE_ENDED = "ended"                         # 遊戲結束

# --- 板子 ID ---
BOARD_AUTO = "auto"
BOARD_STANDARD = "standard"
BOARD_WOLF_KING = "wolf_king"
BOARD_MERCHANT = "merchant"

BOARD_NAMES = {
    BOARD_AUTO: "🎲 自動配置",
    BOARD_STANDARD: "🔮 標準板",
    BOARD_WOLF_KING: "👑 狼王板",
    BOARD_MERCHANT: "💰 奇跡板",
}

# 屠邊規則下，固定板至少要同時有狼人、神職與村民。
BOARD_MIN_PLAYERS = {
    BOARD_AUTO: 3,
    BOARD_STANDARD: 5,
    BOARD_WOLF_KING: 5,
    BOARD_MERCHANT: 7,
}

MAX_PLAYERS = 20
