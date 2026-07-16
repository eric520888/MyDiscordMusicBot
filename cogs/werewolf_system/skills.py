import discord
from discord.ui import View, Select
from .const import *
from .roles import Witch

class SkillManager:
    def __init__(self, game):
        self.game = game

    # --- 夜晚通用行動 (狼人/預言家/女巫跳過/幸運兒) ---
    async def handle_night_action(self, interaction, player, action_type, target_id):
        # 1. 狼人投票
        if action_type == 'wolf_kill':
            self.game.wolf_votes[player.id] = target_id
            self.game.night_actions.add(player.id)
            target_name = "空刀" if target_id == -1 else self.game.get_player(target_id).display_name
            await interaction.response.send_message(f"🩸 你投給了：**{target_name}**", ephemeral=True)
            self.game.log_event(
                "wolf_vote",
                {"voter": player.display_name, "target": target_name},
            )
            
        # 2. 預言家查驗
        elif action_type == 'seer_check':
            self.game.night_actions.add(player.id)
            if target_id == -1:
                await interaction.response.send_message("🔮 驗證結果：空驗", ephemeral=True)
                self.game.log_event("seer_check", {"target": "空驗", "result": "無"})
            else:
                target = self.game.get_player(target_id)
                res = "🐺 狼人 (壞人)" if target.role.camp == CAMP_WOLF else "好人"
                await interaction.response.send_message(f"🔮 驗證結果：**{res}**", ephemeral=True)
                # [新增] 記錄查驗
                self.game.log_event("seer_check", {"target": target.display_name, "result": res})

        # 3. [修正] 女巫跳過
        elif action_type == 'witch_skip':
            self.game.night_actions.add(player.id)
            await interaction.response.send_message("💤 你選擇了什麼都不做", ephemeral=True)
            await self.game.check_phase_2_end() # 呼叫 Phase 2 檢查
            return

        # 4. 幸運兒技能 (Check) - Phase 2
        elif action_type == 'lucky_check':
            self.game.lucky_data["target"] = target_id
            self.game.night_actions.add(player.id)
            target = self.game.get_player(target_id)
            res = "🐺 狼人" if target.role.camp == CAMP_WOLF else "好人"
            await interaction.response.send_message(f"✨ [幸運兒] 查驗結果：**{res}**", ephemeral=True)
            self.game.log_event(
                "lucky_check",
                {"target": target.display_name, "result": res},
            )
            await self.game.check_phase_2_end()
            return 

        # 5. 幸運兒技能 (Poison/Guard)
        elif action_type in ['lucky_poison', 'lucky_guard']:
            self.game.lucky_data["target"] = target_id
            self.game.night_actions.add(player.id)
            msg = "☠️ 已下毒" if action_type == 'lucky_poison' else "🛡️ 已守護"
            await interaction.response.send_message(msg, ephemeral=True)
            target = self.game.get_player(target_id)
            self.game.log_event(
                action_type,
                {"target": target.display_name},
            )
            await self.game.check_phase_2_end()
            return

        # 檢查 Phase 1 結束
        await self.game.check_phase_1_end()

    # --- 商人技能 ---
    async def handle_merchant_skill(self, interaction, player, target_id, skill):
        self.game.lucky_data = {"user_id": target_id, "skill": skill, "target": None}
        self.game.night_actions.add(player.id)
        player.role.used_skill = True
        
        t_player = self.game.get_player(target_id)
        skill_name = {"check": "查驗", "poison": "毒藥", "guard": "守衛"}[skill]
        await interaction.response.send_message(
            f"💰 你給予了 **{t_player.display_name}** **{skill_name}** 技能。",
            ephemeral=True,
        )
        # [新增] 記錄商人給技能
        self.game.log_event(
            "merchant_gift",
            {"target": t_player.display_name, "skill": skill_name},
        )
        await self.game.check_phase_1_end()

    # --- 女巫技能 ---
    async def handle_witch_save(self, interaction, player):
        if (
            self.game.phase != PHASE_NIGHT_2
            or interaction.user.id != player.id
            or self.game.get_player(player.id) is not player
            or player.status != "alive"
            or not isinstance(player.role, Witch)
            or player.id in self.game.night_actions
        ):
            return await interaction.response.send_message(
                "❌ 這個女巫操作已失效。", ephemeral=True
            )
        if not player.role.has_antidote: return await interaction.response.send_message("❌ 解藥已用", ephemeral=True)
        if self.game.wolf_target in {-1, None}: return await interaction.response.send_message("❌ 無人死亡", ephemeral=True)
        
        # [新增] 女巫不能自救
        if self.game.wolf_target == player.id:
            return await interaction.response.send_message("❌ 女巫規則：不能自救！", ephemeral=True)
        
        player.role.has_antidote = False
        saved_name = self.game.get_player(self.game.wolf_target).display_name
        self.game.wolf_target = -1 
        self.game.night_actions.add(player.id)
        await interaction.response.send_message("💊 使用了解藥", ephemeral=True)
        # [新增] 記錄女巫救人
        self.game.log_event("witch_save", {"target": saved_name})
        await self.game.check_phase_2_end()

    async def send_witch_poison_select(self, interaction, player):
        if (
            self.game.phase != PHASE_NIGHT_2
            or interaction.user.id != player.id
            or self.game.get_player(player.id) is not player
            or player.status != "alive"
            or not isinstance(player.role, Witch)
            or player.id in self.game.night_actions
        ):
            return await interaction.response.send_message(
                "❌ 這個女巫操作已失效。", ephemeral=True
            )
        if not player.role.has_poison: return await interaction.response.send_message("❌ 毒藥已用", ephemeral=True)
        
        view = View()
        options = [discord.SelectOption(label=p.display_name, value=str(p.id)) for p in self.game.get_alive_players()]
        select = Select(placeholder="☠️ 選擇毒殺...", options=options)
        
        async def callback(inter):
            target = int(select.values[0])
            target_p = self.game.get_player(target)
            if (
                self.game.phase != PHASE_NIGHT_2
                or inter.user.id != player.id
                or player.id in self.game.night_actions
                or not player.role.has_poison
                or target_p is None
                or target_p.status != "alive"
            ):
                return await inter.response.send_message(
                    "❌ 這個毒藥操作已失效。", ephemeral=True
                )
            self.game.witch_poison_target = target
            player.role.has_poison = False
            self.game.night_actions.add(player.id)
            await inter.response.send_message("☠️ 已下毒", ephemeral=True)
            # [新增] 記錄女巫毒人
            self.game.log_event("witch_poison", {"target": target_p.display_name})
            await self.game.check_phase_2_end()
            
        select.callback = callback
        view.add_item(select)
        await interaction.response.send_message("選擇目標：", view=view, ephemeral=True)
