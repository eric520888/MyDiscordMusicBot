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
    can_shoot = False
    used_skill = False # 用於商人/女巫等
    
    def __init__(self):
        self.has_antidote = False
        self.has_poison = False

class Wolf(Role):
    name = ROLE_WEREWOLF
    camp = CAMP_WOLF
    description = "目標：與隊友投票殺死村民。"

class WolfKing(Wolf):
    name = ROLE_WOLF_KING
    description = "特殊能力：死後可以開槍帶走一人 (被毒死除外)。"
    can_shoot = True

class Seer(Role):
    name = ROLE_SEER
    camp = CAMP_GOD
    description = "技能：每晚查驗一名玩家是好人還是狼人。"

class Witch(Role):
    name = ROLE_WITCH
    camp = CAMP_GOD
    description = "技能：解藥(救人)與毒藥(殺人)，每晚限用一瓶。"
    def __init__(self):
        self.has_antidote = True
        self.has_poison = True

class Hunter(Role):
    name = ROLE_HUNTER
    camp = CAMP_GOD
    description = "技能：死後可開槍帶走一人 (被毒死除外)。"
    can_shoot = True

class Merchant(Role):
    name = ROLE_MERCHANT
    camp = CAMP_GOD
    description = "技能：限一次，賜予玩家查驗/毒藥/守衛技能。若選中狼人則死亡。"

class Villager(Role):
    name = ROLE_VILLAGER
    camp = CAMP_VILLAGER
    description = "技能：無。努力推理並活下去。"

def create_role(role_name):
    mapping = {
        ROLE_WEREWOLF: Wolf,
        ROLE_WOLF_KING: WolfKing,
        ROLE_SEER: Seer,
        ROLE_WITCH: Witch,
        ROLE_HUNTER: Hunter,
        ROLE_MERCHANT: Merchant,
        ROLE_VILLAGER: Villager
    }
    role_class = mapping.get(role_name, Villager)
    return role_class()