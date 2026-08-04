"""Immutable role metadata extracted from the legacy game."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from ..ids import ActionId, CampId, RoleId, localization_key, parse_role_id


@dataclass(frozen=True, slots=True)
class RoleDefinition:
    role_id: RoleId
    camp: CampId
    night_action: ActionId | None = None
    action_from_round: int = 1
    optional_action: bool = False
    can_shoot: bool = False
    shoot_count: int = 0
    joins_wolf_vote: bool = False
    isolated_wolf: bool = False
    can_self_destruct: bool = False
    implemented_in_legacy: bool = True
    activity_mvp: bool = False

    def __post_init__(self) -> None:
        if self.action_from_round < 1:
            raise ValueError("action_from_round must be positive")
        if self.shoot_count < 0:
            raise ValueError("shoot_count cannot be negative")
        if self.can_shoot != (self.shoot_count > 0):
            raise ValueError("can_shoot and shoot_count must agree")

    @property
    def name_key(self) -> str:
        return localization_key("role", self.role_id, "name")

    @property
    def description_key(self) -> str:
        return localization_key("role", self.role_id, "description")


def _role(
    role_id: RoleId,
    camp: CampId,
    *,
    night_action: ActionId | None = None,
    action_from_round: int = 1,
    optional_action: bool = False,
    can_shoot: bool = False,
    shoot_count: int = 0,
    joins_wolf_vote: bool = False,
    isolated_wolf: bool = False,
    can_self_destruct: bool = False,
    implemented_in_legacy: bool = True,
    activity_mvp: bool = False,
) -> RoleDefinition:
    return RoleDefinition(
        role_id=role_id,
        camp=camp,
        night_action=night_action,
        action_from_round=action_from_round,
        optional_action=optional_action,
        can_shoot=can_shoot,
        shoot_count=shoot_count,
        joins_wolf_vote=joins_wolf_vote,
        isolated_wolf=isolated_wolf,
        can_self_destruct=can_self_destruct,
        implemented_in_legacy=implemented_in_legacy,
        activity_mvp=activity_mvp,
    )


_CATALOG = {
    RoleId.WEREWOLF: _role(RoleId.WEREWOLF, CampId.WOLF, joins_wolf_vote=True, can_self_destruct=True, activity_mvp=True),
    RoleId.VILLAGER: _role(RoleId.VILLAGER, CampId.VILLAGER, activity_mvp=True),
    RoleId.SEER: _role(RoleId.SEER, CampId.GOD, night_action=ActionId.SEER_CHECK, activity_mvp=True),
    RoleId.WITCH: _role(RoleId.WITCH, CampId.GOD, activity_mvp=True),
    RoleId.HUNTER: _role(RoleId.HUNTER, CampId.GOD, can_shoot=True, shoot_count=1, activity_mvp=True),
    RoleId.FOOL: _role(RoleId.FOOL, CampId.GOD),
    RoleId.GUARD: _role(RoleId.GUARD, CampId.GOD, night_action=ActionId.GUARD),
    RoleId.WOLF_KING: _role(RoleId.WOLF_KING, CampId.WOLF, can_shoot=True, shoot_count=1, joins_wolf_vote=True, can_self_destruct=True),
    RoleId.WOLF_BEAUTY: _role(RoleId.WOLF_BEAUTY, CampId.WOLF, night_action=ActionId.CHARM, joins_wolf_vote=True),
    RoleId.KNIGHT: _role(RoleId.KNIGHT, CampId.GOD),
    RoleId.DREAMER: _role(RoleId.DREAMER, CampId.GOD, night_action=ActionId.DREAM),
    RoleId.EVIL_KNIGHT: _role(RoleId.EVIL_KNIGHT, CampId.WOLF, joins_wolf_vote=True),
    RoleId.GARGOYLE: _role(RoleId.GARGOYLE, CampId.WOLF, night_action=ActionId.EXACT_CHECK, isolated_wolf=True),
    RoleId.GRAVEKEEPER: _role(RoleId.GRAVEKEEPER, CampId.GOD),
    RoleId.CRIMSON_APOSTLE: _role(RoleId.CRIMSON_APOSTLE, CampId.WOLF, joins_wolf_vote=True),
    RoleId.DEMON_HUNTER: _role(RoleId.DEMON_HUNTER, CampId.GOD, night_action=ActionId.HUNT, action_from_round=2, optional_action=True),
    RoleId.NIGHTMARE: _role(RoleId.NIGHTMARE, CampId.WOLF, night_action=ActionId.FEAR, joins_wolf_vote=True),
    RoleId.TIME_WOLF: _role(RoleId.TIME_WOLF, CampId.WOLF, night_action=ActionId.BLOCK, joins_wolf_vote=True),
    RoleId.ORDER_PRINCE: _role(RoleId.ORDER_PRINCE, CampId.GOD),
    RoleId.WOLF_WITCH: _role(RoleId.WOLF_WITCH, CampId.WOLF, night_action=ActionId.WOLF_WITCH_CHECK, joins_wolf_vote=True),
    RoleId.PURE_WHITE: _role(RoleId.PURE_WHITE, CampId.GOD, night_action=ActionId.PURE_WHITE_CHECK),
    RoleId.NIGHT_MENTOR: _role(RoleId.NIGHT_MENTOR, CampId.WOLF, night_action=ActionId.TIME_WAVE, action_from_round=2, optional_action=True, isolated_wolf=True),
    RoleId.DAY_SCHOLAR: _role(RoleId.DAY_SCHOLAR, CampId.GOD, night_action=ActionId.TIME_WAVE, action_from_round=2, optional_action=True),
    RoleId.ALPACA: _role(RoleId.ALPACA, CampId.VILLAGER),
    RoleId.WHITE_CAT: _role(RoleId.WHITE_CAT, CampId.GOD),
    RoleId.YOUNG_FOX: _role(RoleId.YOUNG_FOX, CampId.GOD, night_action=ActionId.CONFUSE, action_from_round=2, optional_action=True),
    RoleId.BEAR: _role(RoleId.BEAR, CampId.GOD),
    RoleId.PUFFERFISH: _role(RoleId.PUFFERFISH, CampId.GOD),
    RoleId.ECLIPSE_MAID: _role(RoleId.ECLIPSE_MAID, CampId.WOLF, night_action=ActionId.DEVOUR, action_from_round=2, optional_action=True, joins_wolf_vote=True),
    RoleId.LIGHT_EARL: _role(RoleId.LIGHT_EARL, CampId.GOD, night_action=ActionId.LIGHT_GUARD, action_from_round=2),
    RoleId.NIGHT_NOBLE: _role(RoleId.NIGHT_NOBLE, CampId.WOLF, night_action=ActionId.NIGHT_SERVANT, action_from_round=2, optional_action=True, joins_wolf_vote=True),
    RoleId.AWAKENED_FOOL: _role(RoleId.AWAKENED_FOOL, CampId.GOD, night_action=ActionId.SECRET_GUARD, optional_action=True),
    RoleId.FRAGRANCE_PHANTOM: _role(RoleId.FRAGRANCE_PHANTOM, CampId.WOLF, night_action=ActionId.FATE_BIND, isolated_wolf=True),
    RoleId.AWAKENED_SEER: _role(RoleId.AWAKENED_SEER, CampId.GOD, night_action=ActionId.DOUBLE_CHECK),
    RoleId.AWAKENED_WOLF_KING: _role(RoleId.AWAKENED_WOLF_KING, CampId.WOLF, night_action=ActionId.CLAW_PASS, optional_action=True, can_shoot=True, shoot_count=2, joins_wolf_vote=True, can_self_destruct=True),
    RoleId.MIRROR_GIRL: _role(RoleId.MIRROR_GIRL, CampId.GOD, night_action=ActionId.MIRROR_CHECK),
    RoleId.AWAKENED_HIDDEN_WOLF: _role(RoleId.AWAKENED_HIDDEN_WOLF, CampId.WOLF, night_action=ActionId.MIMIC, optional_action=True, isolated_wolf=True),
    RoleId.AWAKENED_WITCH: _role(RoleId.AWAKENED_WITCH, CampId.GOD),
    RoleId.AWAKENED_WOLF_BEAUTY: _role(RoleId.AWAKENED_WOLF_BEAUTY, CampId.WOLF, night_action=ActionId.AWAKENED_CHARM, optional_action=True, joins_wolf_vote=True),
    RoleId.AWAKENED_HUNTER: _role(RoleId.AWAKENED_HUNTER, CampId.GOD, can_shoot=True, shoot_count=1),
    RoleId.AWAKENED_LONELY_GIRL: _role(RoleId.AWAKENED_LONELY_GIRL, CampId.THIRD_PARTY, night_action=ActionId.CHOOSE_IDOL),
    RoleId.AWAKENED_GARGOYLE: _role(RoleId.AWAKENED_GARGOYLE, CampId.WOLF, night_action=ActionId.CONVERT, joins_wolf_vote=True, can_self_destruct=True),
    RoleId.AWAKENED_GUARD: _role(RoleId.AWAKENED_GUARD, CampId.GOD, night_action=ActionId.AWAKENED_GUARD, optional_action=True),
    RoleId.AWAKENED_WHITE_WOLF_KING: _role(RoleId.AWAKENED_WHITE_WOLF_KING, CampId.WOLF, joins_wolf_vote=True, can_self_destruct=True),
    RoleId.AWAKENED_DREAMER: _role(RoleId.AWAKENED_DREAMER, CampId.GOD, night_action=ActionId.DREAM_SPEECH),
    RoleId.MERCHANT: _role(RoleId.MERCHANT, CampId.GOD, night_action=ActionId.MERCHANT_GIVE, optional_action=True),
    RoleId.HIDDEN_WOLF: _role(RoleId.HIDDEN_WOLF, CampId.WOLF, implemented_in_legacy=False),
    RoleId.WHITE_WOLF_KING: _role(RoleId.WHITE_WOLF_KING, CampId.WOLF, implemented_in_legacy=False),
    RoleId.CUPID: _role(RoleId.CUPID, CampId.THIRD_PARTY, implemented_in_legacy=False),
    RoleId.THOUSAND_FACES: _role(RoleId.THOUSAND_FACES, CampId.THIRD_PARTY, implemented_in_legacy=False),
    RoleId.SHERIFF: _role(RoleId.SHERIFF, CampId.GOD, implemented_in_legacy=False),
    RoleId.CROW: _role(RoleId.CROW, CampId.GOD, implemented_in_legacy=False),
    RoleId.ALCHEMIST: _role(RoleId.ALCHEMIST, CampId.GOD, implemented_in_legacy=False),
    RoleId.WOLF_CROW_CLAW: _role(RoleId.WOLF_CROW_CLAW, CampId.WOLF, implemented_in_legacy=False),
    RoleId.MAGICIAN: _role(RoleId.MAGICIAN, CampId.GOD, implemented_in_legacy=False),
    RoleId.LONELY_GIRL: _role(RoleId.LONELY_GIRL, CampId.THIRD_PARTY, implemented_in_legacy=False),
    RoleId.CURSE_FOX: _role(RoleId.CURSE_FOX, CampId.THIRD_PARTY, implemented_in_legacy=False),
}

ROLE_CATALOG: Mapping[RoleId, RoleDefinition] = MappingProxyType(_CATALOG)


def get_role_definition(role_id: RoleId | str) -> RoleDefinition:
    return ROLE_CATALOG[parse_role_id(role_id)]
