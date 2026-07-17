"""狼人殺角色物件與每局狀態。"""

from .const import *


class Player:
    def __init__(self, user, role_obj):
        self.user = user
        self.id = user.id
        self.role = role_obj
        self.status = "alive"

    @property
    def display_name(self):
        return self.user.display_name

    @property
    def mention(self):
        return self.user.mention


class Role:
    name = "未知"
    camp = "中立"
    description = "無技能"
    night_action = None
    action_from_round = 1
    optional_action = False
    can_shoot = False
    shoot_count = 0
    joins_wolf_vote = False
    isolated_wolf = False

    def __init__(self):
        self.has_antidote = False
        self.has_poison = False
        self.used_skill = False
        self.disabled = False
        self.last_target = None
        self.checked_targets = set()
        self.vote_disabled = False
        self.secret_body = False
        self.state = {}


def _make_role_class(
    class_name,
    role_name,
    *,
    base=Role,
    night_action=None,
    action_from_round=1,
    optional_action=False,
    can_shoot=False,
    shoot_count=0,
    joins_wolf_vote=False,
    isolated_wolf=False,
):
    info = ROLE_CATALOG[role_name]
    attrs = {
        "name": role_name,
        "camp": info.camp,
        "description": info.description,
        "night_action": night_action,
        "action_from_round": action_from_round,
        "optional_action": optional_action,
        "can_shoot": can_shoot,
        "shoot_count": shoot_count,
        "joins_wolf_vote": joins_wolf_vote,
        "isolated_wolf": isolated_wolf,
    }
    return type(class_name, (base,), attrs)


Wolf = _make_role_class("Wolf", ROLE_WEREWOLF, joins_wolf_vote=True)
Villager = _make_role_class("Villager", ROLE_VILLAGER)
Seer = _make_role_class("Seer", ROLE_SEER, night_action="seer_check")
Hunter = _make_role_class("Hunter", ROLE_HUNTER, can_shoot=True, shoot_count=1)
Fool = _make_role_class("Fool", ROLE_FOOL)
Guard = _make_role_class("Guard", ROLE_GUARD, night_action="guard")
WolfKing = _make_role_class("WolfKing", ROLE_WOLF_KING, base=Wolf, can_shoot=True, shoot_count=1, joins_wolf_vote=True)
WolfBeauty = _make_role_class("WolfBeauty", ROLE_WOLF_BEAUTY, base=Wolf, night_action="charm", joins_wolf_vote=True)
Knight = _make_role_class("Knight", ROLE_KNIGHT)
Dreamer = _make_role_class("Dreamer", ROLE_DREAMER, night_action="dream")
EvilKnight = _make_role_class("EvilKnight", ROLE_EVIL_KNIGHT, base=Wolf, joins_wolf_vote=True)
Gargoyle = _make_role_class("Gargoyle", ROLE_GARGOYLE, base=Wolf, night_action="exact_check", isolated_wolf=True)
Gravekeeper = _make_role_class("Gravekeeper", ROLE_GRAVEKEEPER)
CrimsonApostle = _make_role_class("CrimsonApostle", ROLE_CRIMSON_APOSTLE, base=Wolf, joins_wolf_vote=True)
DemonHunter = _make_role_class("DemonHunter", ROLE_DEMON_HUNTER, night_action="hunt", action_from_round=2, optional_action=True)
Nightmare = _make_role_class("Nightmare", ROLE_NIGHTMARE, base=Wolf, night_action="fear", joins_wolf_vote=True)
TimeWolf = _make_role_class("TimeWolf", ROLE_TIME_WOLF, base=Wolf, night_action="block", joins_wolf_vote=True)
OrderPrince = _make_role_class("OrderPrince", ROLE_ORDER_PRINCE)
WolfWitch = _make_role_class("WolfWitch", ROLE_WOLF_WITCH, base=Wolf, night_action="wolf_witch_check", joins_wolf_vote=True)
PureWhite = _make_role_class("PureWhite", ROLE_PURE_WHITE, night_action="pure_white_check")
NightMentor = _make_role_class("NightMentor", ROLE_NIGHT_MENTOR, base=Wolf, night_action="time_wave", action_from_round=2, optional_action=True, isolated_wolf=True)
DayScholar = _make_role_class("DayScholar", ROLE_DAY_SCHOLAR, night_action="time_wave", action_from_round=2, optional_action=True)
Alpaca = _make_role_class("Alpaca", ROLE_ALPACA)
WhiteCat = _make_role_class("WhiteCat", ROLE_WHITE_CAT)
YoungFox = _make_role_class("YoungFox", ROLE_YOUNG_FOX, night_action="confuse", action_from_round=2, optional_action=True)
Bear = _make_role_class("Bear", ROLE_BEAR)
Pufferfish = _make_role_class("Pufferfish", ROLE_PUFFERFISH)
EclipseMaid = _make_role_class("EclipseMaid", ROLE_ECLIPSE_MAID, base=Wolf, night_action="devour", action_from_round=2, optional_action=True, joins_wolf_vote=True)
LightEarl = _make_role_class("LightEarl", ROLE_LIGHT_EARL, night_action="light_guard", action_from_round=2)
NightNoble = _make_role_class("NightNoble", ROLE_NIGHT_NOBLE, base=Wolf, night_action="night_servant", action_from_round=2, optional_action=True, joins_wolf_vote=True)
AwakenedFool = _make_role_class("AwakenedFool", ROLE_AWAKENED_FOOL, night_action="secret_guard", optional_action=True)
FragrancePhantom = _make_role_class("FragrancePhantom", ROLE_FRAGRANCE_PHANTOM, base=Wolf, night_action="fate_bind", isolated_wolf=True)
AwakenedSeer = _make_role_class("AwakenedSeer", ROLE_AWAKENED_SEER, night_action="double_check")
AwakenedWolfKing = _make_role_class("AwakenedWolfKing", ROLE_AWAKENED_WOLF_KING, base=Wolf, night_action="claw_pass", optional_action=True, can_shoot=True, shoot_count=2, joins_wolf_vote=True)
MirrorGirl = _make_role_class("MirrorGirl", ROLE_MIRROR_GIRL, night_action="mirror_check")
AwakenedHiddenWolf = _make_role_class("AwakenedHiddenWolf", ROLE_AWAKENED_HIDDEN_WOLF, base=Wolf, night_action="mimic", optional_action=True, isolated_wolf=True)
AwakenedWolfBeauty = _make_role_class("AwakenedWolfBeauty", ROLE_AWAKENED_WOLF_BEAUTY, base=Wolf, night_action="awakened_charm", optional_action=True, joins_wolf_vote=True)
AwakenedHunter = _make_role_class("AwakenedHunter", ROLE_AWAKENED_HUNTER, can_shoot=True, shoot_count=1)
Merchant = _make_role_class("Merchant", ROLE_MERCHANT, night_action="merchant_give", optional_action=True)


class Witch(Role):
    name = ROLE_WITCH
    camp = ROLE_CATALOG[ROLE_WITCH].camp
    description = ROLE_CATALOG[ROLE_WITCH].description

    def __init__(self):
        super().__init__()
        self.has_antidote = True
        self.has_poison = True


class AwakenedWitch(Witch):
    name = ROLE_AWAKENED_WITCH
    description = ROLE_CATALOG[ROLE_AWAKENED_WITCH].description

    def __init__(self):
        super().__init__()
        self.poison_recipes = 3


ROLE_CLASSES = {
    role_class.name: role_class
    for role_class in (
        Wolf, Villager, Seer, Witch, Hunter, Fool, Guard, WolfKing,
        WolfBeauty, Knight, Dreamer, EvilKnight, Gargoyle, Gravekeeper,
        CrimsonApostle, DemonHunter, Nightmare, TimeWolf, OrderPrince,
        WolfWitch, PureWhite, NightMentor, DayScholar, Alpaca, WhiteCat,
        YoungFox, Bear, Pufferfish, EclipseMaid, LightEarl, NightNoble,
        AwakenedFool, FragrancePhantom, AwakenedSeer, AwakenedWolfKing,
        MirrorGirl, AwakenedHiddenWolf, AwakenedWitch,
        AwakenedWolfBeauty, AwakenedHunter, Merchant,
    )
}


def create_role(role_name):
    role_class = ROLE_CLASSES.get(role_name)
    if role_class is None:
        raise ValueError(f"未知的狼人殺角色：{role_name}")
    role = role_class()
    if role_name == ROLE_AWAKENED_FOOL:
        role.secret_body = True
    return role
