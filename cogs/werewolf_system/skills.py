import discord
from discord.ui import View, Select
from .const import *
from .roles import AwakenedWitch, Witch

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
            or player.role.disabled
            or self.game.is_phase_2_done(player)
        ):
            return await interaction.response.send_message(
                "❌ 這個女巫操作已失效。", ephemeral=True
            )
        if not player.role.has_antidote:
            return await interaction.response.send_message("❌ 解藥已用", ephemeral=True)
        valid_targets = [
            target_id for target_id in self.game.wolf_targets
            if target_id not in {-1, None}
        ] or ([self.game.wolf_target] if self.game.wolf_target not in {-1, None} else [])
        if not valid_targets:
            return await interaction.response.send_message("❌ 無人死亡", ephemeral=True)
        saveable = [target_id for target_id in valid_targets if target_id != player.id]
        if not saveable:
            return await interaction.response.send_message("❌ 女巫規則：不能自救！", ephemeral=True)
        if len(saveable) > 1:
            select = Select(
                placeholder="💊 選擇要救的狼襲目標...",
                options=[
                    discord.SelectOption(
                        label=self.game.get_player(target_id).display_name,
                        value=str(target_id),
                    )
                    for target_id in saveable
                ],
            )
            view = View(timeout=300)

            async def callback(inter):
                await self._apply_witch_save(
                    inter, player, int(select.values[0])
                )

            select.callback = callback
            view.add_item(select)
            return await interaction.response.send_message(
                "本夜有多名狼襲目標，請選擇要救的人：",
                view=view,
                ephemeral=True,
            )
        await self._apply_witch_save(interaction, player, saveable[0])

    async def _apply_witch_save(self, interaction, player, saved_id):
        if (
            self.game.phase != PHASE_NIGHT_2
            or interaction.user.id != player.id
            or self.game.is_phase_2_done(player)
            or not player.role.has_antidote
            or saved_id == player.id
            or saved_id not in (self.game.wolf_targets or [self.game.wolf_target])
        ):
            return await interaction.response.send_message(
                "❌ 這個解藥操作已失效。", ephemeral=True
            )
        player.role.has_antidote = False
        saved_name = self.game.get_player(saved_id).display_name
        if saved_id in self.game.wolf_targets:
            self.game.wolf_targets.remove(saved_id)
        self.game.wolf_target = (
            self.game.wolf_targets[0] if self.game.wolf_targets else -1
        )
        self.game.record_phase_2_action(player)
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
            or player.role.disabled
            or self.game.is_phase_2_done(player)
        ):
            return await interaction.response.send_message(
                "❌ 這個女巫操作已失效。", ephemeral=True
            )
        if isinstance(player.role, AwakenedWitch):
            if player.role.poison_recipes <= 0:
                return await interaction.response.send_message("❌ 三次調毒都已用完", ephemeral=True)
        elif not player.role.has_poison:
            return await interaction.response.send_message("❌ 毒藥已用", ephemeral=True)
        
        view = View()
        options = [discord.SelectOption(label=p.display_name, value=str(p.id)) for p in self.game.get_alive_players()]
        select = Select(placeholder="☠️ 選擇毒殺...", options=options)
        
        async def callback(inter):
            target = int(select.values[0])
            target_p = self.game.get_player(target)
            if (
                self.game.phase != PHASE_NIGHT_2
                or inter.user.id != player.id
                or self.game.is_phase_2_done(player)
                or (
                    not isinstance(player.role, AwakenedWitch)
                    and not player.role.has_poison
                )
                or target_p is None
                or target_p.status != "alive"
            ):
                return await inter.response.send_message(
                    "❌ 這個毒藥操作已失效。", ephemeral=True
                )
            if isinstance(player.role, AwakenedWitch):
                return await self._select_awakened_witch_helpers(
                    inter, player, target_p
                )
            self.game.witch_poison_target = target
            player.role.has_poison = False
            self.game.record_phase_2_action(player)
            await inter.response.send_message("☠️ 已下毒", ephemeral=True)
            self.game.log_event("witch_poison", {"target": target_p.display_name})
            await self.game.check_phase_2_end()
            
        select.callback = callback
        view.add_item(select)
        await interaction.response.send_message("選擇目標：", view=view, ephemeral=True)

    async def _select_awakened_witch_helpers(self, interaction, witch, target):
        used_helpers = witch.role.state.setdefault("helpers_used", set())
        helper_count = 4 - witch.role.poison_recipes
        candidates = [
            player for player in self.game.get_alive_players()
            if player.id != witch.id and player.id not in used_helpers
        ]
        if len(candidates) < helper_count:
            return await interaction.response.send_message(
                "❌ 未協助過的存活玩家不足，無法進行這次調毒。",
                ephemeral=True,
            )

        select = Select(
            placeholder=f"🧪 選擇 {helper_count} 名調毒協助者...",
            min_values=helper_count,
            max_values=helper_count,
            options=[
                discord.SelectOption(label=helper.display_name, value=str(helper.id))
                for helper in candidates
            ],
        )
        view = View(timeout=300)

        async def helper_select_callback(inter):
            if (
                self.game.phase != PHASE_NIGHT_2
                or inter.user.id != witch.id
                or self.game.is_phase_2_done(witch)
                or witch.role.poison_recipes <= 0
            ):
                return await inter.response.send_message(
                    "❌ 這個調毒操作已失效。", ephemeral=True
                )
            helper_ids = {int(value) for value in select.values}
            if len(helper_ids) != helper_count or helper_ids & used_helpers:
                return await inter.response.send_message(
                    "❌ 協助者人數錯誤或有人已協助過。", ephemeral=True
                )
            used_helpers.update(helper_ids)
            await inter.response.send_message(
                f"🧪 已邀請 {helper_count} 名玩家協助調毒，等待所有人表決。",
                ephemeral=True,
            )
            await self._send_awakened_poison_vote(witch, target, helper_ids)

        select.callback = helper_select_callback
        view.add_item(select)
        await interaction.response.send_message(
            f"你選擇毒殺 **{target.display_name}**；請挑選協助者。",
            view=view,
            ephemeral=True,
        )

    async def _send_awakened_poison_vote(self, witch, target, helper_ids):
        votes = {}
        view = View(timeout=300)
        poison_button = discord.ui.Button(
            label="同意下毒", style=discord.ButtonStyle.danger, emoji="☠️"
        )
        refuse_button = discord.ui.Button(
            label="拒絕下毒", style=discord.ButtonStyle.secondary, emoji="✋"
        )

        async def cast_vote(interaction, approve):
            if (
                self.game.phase != PHASE_NIGHT_2
                or interaction.user.id not in helper_ids
                or interaction.user.id in votes
                or self.game.is_phase_2_done(witch)
            ):
                return await interaction.response.send_message(
                    "❌ 你不是本次協助者、已表決，或面板已失效。",
                    ephemeral=True,
                )
            votes[interaction.user.id] = approve
            await interaction.response.send_message("✅ 已秘密提交決定。", ephemeral=True)
            if len(votes) < len(helper_ids):
                return
            succeeded = all(votes.values())
            if succeeded:
                self.game.witch_poison_target = target.id
            witch.role.poison_recipes -= 1
            witch.role.has_poison = witch.role.poison_recipes > 0
            self.game.record_phase_2_action(witch)
            self.game.log_event(
                "awakened_witch_poison",
                {"target": target.display_name, "succeeded": succeeded},
            )
            await self.game.channel.send(
                "🧪 覺醒女巫的調毒表決已完成，結果將於天亮結算。"
            )
            await self.game.check_phase_2_end()

        async def approve_callback(interaction):
            await cast_vote(interaction, True)

        async def refuse_callback(interaction):
            await cast_vote(interaction, False)

        poison_button.callback = approve_callback
        refuse_button.callback = refuse_callback
        view.add_item(poison_button)
        view.add_item(refuse_button)
        mentions = " ".join(
            self.game.get_player(helper_id).mention for helper_id in helper_ids
        )
        await self.game.channel.send(
            f"🧪 {mentions} 你們是本夜調毒協助者，請秘密決定是否讓毒藥生效。",
            view=view,
        )
