"""測試狼人殺模組是否能正常載入"""
import sys
sys.path.insert(0, '.')

print("=" * 50)
print("測試狼人殺模組載入")
print("=" * 50)

try:
    print("\n1. 測試 const.py...")
    from cogs.werewolf_system.const import ROLE_WEREWOLF
    print(f"   ✅ const.py OK - ROLE_WEREWOLF = {ROLE_WEREWOLF}")
except Exception as e:
    print(f"   ❌ const.py 錯誤: {e}")
    import traceback
    traceback.print_exc()

try:
    print("\n2. 測試 roles.py...")
    from cogs.werewolf_system.roles import Player, Wolf
    print(f"   ✅ roles.py OK")
except Exception as e:
    print(f"   ❌ roles.py 錯誤: {e}")
    import traceback
    traceback.print_exc()

try:
    print("\n3. 測試 views.py...")
    from cogs.werewolf_system.views import LobbyView
    print(f"   ✅ views.py OK")
except Exception as e:
    print(f"   ❌ views.py 錯誤: {e}")
    import traceback
    traceback.print_exc()

try:
    print("\n4. 測試 game.py...")
    from cogs.werewolf_system.game import WerewolfGame
    print(f"   ✅ game.py OK")
except Exception as e:
    print(f"   ❌ game.py 錯誤: {e}")
    import traceback
    traceback.print_exc()

try:
    print("\n5. 測試 werewolf_bot.py...")
    from cogs.werewolf_bot import WerewolfBot
    print(f"   ✅ werewolf_bot.py OK")
except Exception as e:
    print(f"   ❌ werewolf_bot.py 錯誤: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 50)
print("測試完成")
print("=" * 50)
