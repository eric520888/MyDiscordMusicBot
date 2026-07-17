from pathlib import Path

from .catalog import *


# 使用檔案位置計算路徑，避免從不同工作目錄啟動 Bot 時找不到音效。
SOUND_FOLDER = str(Path(__file__).resolve().parents[2] / "sounds")

# 遊戲階段
PHASE_WAITING = "waiting"
PHASE_STARTING = "starting"
PHASE_NIGHT_1 = "night_actions"
PHASE_NIGHT_2 = "night_witch"
PHASE_DAY = "day"
PHASE_SHOOT = "role_shoot"
PHASE_ENDED = "ended"

# 選單顯示資料。官方板型固定 12 人；舊朋友局保留向下相容。
BOARD_NAMES = {BOARD_AUTO: "🎲 自動配置"}
BOARD_NAMES.update({board_id: spec.name for board_id, spec in BOARD_SPECS.items()})
BOARD_NAMES.update({
    BOARD_WOLF_KING: "👑 狼王板（彈性）",
    BOARD_MERCHANT: "💰 奇跡商人（彈性）",
})

BOARD_MIN_PLAYERS = {BOARD_AUTO: 3}
BOARD_MIN_PLAYERS.update({board_id: spec.player_count for board_id, spec in BOARD_SPECS.items()})
BOARD_MIN_PLAYERS.update({BOARD_WOLF_KING: 5, BOARD_MERCHANT: 7})

MAX_PLAYERS = 20
