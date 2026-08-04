"""Stable, transport-neutral identifiers used by the Activity game."""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from typing import Mapping, TypeVar


class CampId(StrEnum):
    WOLF = "wolf"
    GOD = "god"
    VILLAGER = "villager"
    THIRD_PARTY = "third_party"


class WinnerId(StrEnum):
    GOOD = "good"
    WOLF = "wolf"
    THIRD_PARTY = "third_party"


class RoleId(StrEnum):
    WEREWOLF = "werewolf"
    VILLAGER = "villager"
    SEER = "seer"
    WITCH = "witch"
    HUNTER = "hunter"
    FOOL = "fool"
    GUARD = "guard"
    WOLF_KING = "wolf_king"
    WOLF_BEAUTY = "wolf_beauty"
    KNIGHT = "knight"
    DREAMER = "dreamer"
    EVIL_KNIGHT = "evil_knight"
    GARGOYLE = "gargoyle"
    GRAVEKEEPER = "gravekeeper"
    CRIMSON_APOSTLE = "crimson_apostle"
    DEMON_HUNTER = "demon_hunter"
    NIGHTMARE = "nightmare"
    TIME_WOLF = "time_wolf"
    ORDER_PRINCE = "order_prince"
    WOLF_WITCH = "wolf_witch"
    PURE_WHITE = "pure_white"
    NIGHT_MENTOR = "night_mentor"
    DAY_SCHOLAR = "day_scholar"
    ALPACA = "alpaca"
    WHITE_CAT = "white_cat"
    YOUNG_FOX = "young_fox"
    BEAR = "bear"
    PUFFERFISH = "pufferfish"
    ECLIPSE_MAID = "eclipse_maid"
    LIGHT_EARL = "light_earl"
    NIGHT_NOBLE = "night_noble"
    AWAKENED_FOOL = "awakened_fool"
    FRAGRANCE_PHANTOM = "fragrance_phantom"
    AWAKENED_SEER = "awakened_seer"
    AWAKENED_WOLF_KING = "awakened_wolf_king"
    MIRROR_GIRL = "mirror_girl"
    AWAKENED_HIDDEN_WOLF = "awakened_hidden_wolf"
    AWAKENED_WITCH = "awakened_witch"
    AWAKENED_WOLF_BEAUTY = "awakened_wolf_beauty"
    AWAKENED_HUNTER = "awakened_hunter"
    AWAKENED_LONELY_GIRL = "awakened_lonely_girl"
    AWAKENED_GARGOYLE = "awakened_gargoyle"
    AWAKENED_GUARD = "awakened_guard"
    AWAKENED_WHITE_WOLF_KING = "awakened_white_wolf_king"
    AWAKENED_DREAMER = "awakened_dreamer"
    MERCHANT = "merchant"
    HIDDEN_WOLF = "hidden_wolf"
    WHITE_WOLF_KING = "white_wolf_king"
    CUPID = "cupid"
    THOUSAND_FACES = "thousand_faces"
    SHERIFF = "sheriff"
    CROW = "crow"
    ALCHEMIST = "alchemist"
    WOLF_CROW_CLAW = "wolf_crow_claw"
    MAGICIAN = "magician"
    LONELY_GIRL = "lonely_girl"
    CURSE_FOX = "curse_fox"


class BoardId(StrEnum):
    AUTO = "auto"
    STANDARD = "standard"
    WOLF_BEAUTY_KNIGHT = "wolf_beauty_knight"
    WOLF_KING_GUARD = "wolf_king_guard"
    WOLF_KING_DREAMER = "wolf_king_dreamer"
    EVIL_KNIGHT = "evil_knight"
    GARGOYLE_GRAVEKEEPER = "gargoyle_gravekeeper"
    CRIMSON_DEMON_HUNTER = "crimson_demon_hunter"
    NIGHTMARE = "nightmare"
    ETERNAL_ORDER = "eternal_order"
    PURE_WHITE = "pure_white"
    TIME_WAVE = "time_wave"
    ANIMAL_DREAM = "animal_dream"
    HUNTER_SUN = "hunter_sun"
    AWAKENED_NIGHT = "awakened_night"
    FRAGRANCE_FATE = "fragrance_fate"
    AWAKENED_WOLF_KING = "awakened_wolf_king"
    MIRROR_MAZE = "mirror_maze"
    AWAKENED_WITCH = "awakened_witch"
    DARK_NIGHT_STARS = "dark_night_stars"
    AWAKENED_LONELY_GIRL = "awakened_lonely_girl"
    AWAKENED_GARGOYLE = "awakened_gargoyle"
    MOONFALL_ABYSS = "moonfall_abyss"
    AWAKENED_DREAMER = "awakened_dreamer"
    WOLF_KING = "wolf_king"
    MERCHANT = "merchant"


class GamePhase(StrEnum):
    WAITING = "waiting"
    STARTING = "starting"
    NIGHT_ACTIONS = "night_actions"
    NIGHT_WITCH = "night_witch"
    DAY = "day"
    ROLE_SHOOT = "role_shoot"
    ENDED = "ended"


class PlayerStatus(StrEnum):
    ALIVE = "alive"
    DEAD = "dead"


class ActionId(StrEnum):
    WOLF_KILL = "wolf_kill"
    SEER_CHECK = "seer_check"
    WITCH_ANTIDOTE = "witch_antidote"
    WITCH_POISON = "witch_poison"
    HUNTER_SHOOT = "hunter_shoot"
    GUARD = "guard"
    CHARM = "charm"
    KNIGHT_DUEL = "knight_duel"
    DREAM = "dream"
    EXACT_CHECK = "exact_check"
    HUNT = "hunt"
    FEAR = "fear"
    BLOCK = "block"
    WOLF_WITCH_CHECK = "wolf_witch_check"
    PURE_WHITE_CHECK = "pure_white_check"
    TIME_WAVE = "time_wave"
    CONFUSE = "confuse"
    DEVOUR = "devour"
    LIGHT_GUARD = "light_guard"
    NIGHT_SERVANT = "night_servant"
    SECRET_GUARD = "secret_guard"
    FATE_BIND = "fate_bind"
    DOUBLE_CHECK = "double_check"
    CLAW_PASS = "claw_pass"
    MIRROR_CHECK = "mirror_check"
    MIMIC = "mimic"
    AWAKENED_CHARM = "awakened_charm"
    CHOOSE_IDOL = "choose_idol"
    CONVERT = "convert"
    AWAKENED_GUARD = "awakened_guard"
    DREAM_SPEECH = "dream_speech"
    MERCHANT_GIVE = "merchant_give"
    VOTE = "vote"
    ABSTAIN = "abstain"


class EventType(StrEnum):
    GAME_CREATED = "game_created"
    GAME_STARTED = "game_started"
    PHASE_CHANGED = "phase_changed"
    ROLE_ASSIGNED = "role_assigned"
    ACTION_ACCEPTED = "action_accepted"
    SEER_RESULT = "seer_result"
    PLAYER_DIED = "player_died"
    VOTE_CAST = "vote_cast"
    VOTE_RESOLVED = "vote_resolved"
    GAME_ENDED = "game_ended"


class EventVisibility(StrEnum):
    PUBLIC = "public"
    PLAYER_ONLY = "player_only"
    WOLF_TEAM = "wolf_team"
    HOST_ONLY = "host_only"
    AFTER_GAME = "after_game"


class VoteVisibility(StrEnum):
    REVEAL_AFTER_RESULT = "reveal_after_result"
    ANONYMOUS = "anonymous"
    LIVE = "live"


LEGACY_CAMP_ALIASES: Mapping[str, CampId] = MappingProxyType(
    {
        "狼人陣營": CampId.WOLF,
        "神職陣營": CampId.GOD,
        "村民陣營": CampId.VILLAGER,
        "第三方陣營": CampId.THIRD_PARTY,
    }
)

LEGACY_ROLE_ALIASES: Mapping[str, RoleId] = MappingProxyType(
    {
        "狼人": RoleId.WEREWOLF,
        "平民": RoleId.VILLAGER,
        "預言家": RoleId.SEER,
        "女巫": RoleId.WITCH,
        "獵人": RoleId.HUNTER,
        "愚者": RoleId.FOOL,
        "守衛": RoleId.GUARD,
        "狼王": RoleId.WOLF_KING,
        "狼美人": RoleId.WOLF_BEAUTY,
        "騎士": RoleId.KNIGHT,
        "攝夢人": RoleId.DREAMER,
        "惡夜騎士": RoleId.EVIL_KNIGHT,
        "石像鬼": RoleId.GARGOYLE,
        "守墓人": RoleId.GRAVEKEEPER,
        "赤月使徒": RoleId.CRIMSON_APOSTLE,
        "獵魔人": RoleId.DEMON_HUNTER,
        "噩夢之影": RoleId.NIGHTMARE,
        "蝕時狼妃": RoleId.TIME_WOLF,
        "定序王子": RoleId.ORDER_PRINCE,
        "狼巫": RoleId.WOLF_WITCH,
        "純白之女": RoleId.PURE_WHITE,
        "寂夜導師": RoleId.NIGHT_MENTOR,
        "白晝學者": RoleId.DAY_SCHOLAR,
        "羊駝": RoleId.ALPACA,
        "白貓": RoleId.WHITE_CAT,
        "子狐": RoleId.YOUNG_FOX,
        "熊": RoleId.BEAR,
        "河豚": RoleId.PUFFERFISH,
        "蝕日侍女": RoleId.ECLIPSE_MAID,
        "流光伯爵": RoleId.LIGHT_EARL,
        "夜之貴族": RoleId.NIGHT_NOBLE,
        "覺醒愚者": RoleId.AWAKENED_FOOL,
        "尋香魅影": RoleId.FRAGRANCE_PHANTOM,
        "覺醒預言家": RoleId.AWAKENED_SEER,
        "覺醒狼王": RoleId.AWAKENED_WOLF_KING,
        "魔鏡少女": RoleId.MIRROR_GIRL,
        "覺醒隱狼": RoleId.AWAKENED_HIDDEN_WOLF,
        "覺醒女巫": RoleId.AWAKENED_WITCH,
        "覺醒狼美人": RoleId.AWAKENED_WOLF_BEAUTY,
        "覺醒獵人": RoleId.AWAKENED_HUNTER,
        "覺醒孤獨少女": RoleId.AWAKENED_LONELY_GIRL,
        "覺醒石像鬼": RoleId.AWAKENED_GARGOYLE,
        "覺醒守衛": RoleId.AWAKENED_GUARD,
        "覺醒白狼王": RoleId.AWAKENED_WHITE_WOLF_KING,
        "覺醒攝夢人": RoleId.AWAKENED_DREAMER,
        "奇跡商人": RoleId.MERCHANT,
        "隱狼": RoleId.HIDDEN_WOLF,
        "白狼王": RoleId.WHITE_WOLF_KING,
        "丘比特": RoleId.CUPID,
        "千面人": RoleId.THOUSAND_FACES,
        "警長": RoleId.SHERIFF,
        "烏鴉": RoleId.CROW,
        "煉金魔女": RoleId.ALCHEMIST,
        "狼鴉之爪": RoleId.WOLF_CROW_CLAW,
        "魔術師": RoleId.MAGICIAN,
        "孤獨少女": RoleId.LONELY_GIRL,
        "咒狐": RoleId.CURSE_FOX,
    }
)


_EnumT = TypeVar("_EnumT", bound=StrEnum)


def _parse_stable_or_legacy(
    value: str | _EnumT,
    enum_type: type[_EnumT],
    aliases: Mapping[str, _EnumT],
) -> _EnumT:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except ValueError:
        try:
            return aliases[value]
        except KeyError as exc:
            raise ValueError(f"unknown {enum_type.__name__}: {value}") from exc


def parse_camp_id(value: str | CampId) -> CampId:
    return _parse_stable_or_legacy(value, CampId, LEGACY_CAMP_ALIASES)


def parse_role_id(value: str | RoleId) -> RoleId:
    return _parse_stable_or_legacy(value, RoleId, LEGACY_ROLE_ALIASES)


def localization_key(namespace: str, stable_id: StrEnum, field: str) -> str:
    """Build a stable localization key without embedding display text."""

    return f"{namespace}.{stable_id.value}.{field}"
