import sys
import os
 
# Add current directory to path so we can import app modules
sys.path.append(os.getcwd())

try:
    from app.ui.outlook_sync import get_active_tasks_from_db, sync_outlook_tasks, connect_outlook
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

print("=== DIAGNOSTIC START ===")

# 1. Check DB Data
print("\n[1] Check DB Data Fetching (Future Only)")
try:
    tasks = get_active_tasks_from_db(future_only=True)
    print(f"Rows returned: {len(tasks)}")
except Exception as e:
    print(f"Error fetching DB: {e}")

print("\n[2] Check DB Data Fetching (All)")
try:
    tasks_all = get_active_tasks_from_db(future_only=False)
    print(f"Rows returned: {len(tasks_all)}")
except Exception as e:
    print(f"Error fetching DB (All): {e}")

# 2. Check Outlook Connection (only check, don't sync yet if not needed)
print("\n[3] Check Outlook Connection")
try:
    print("Calling sync_outlook_tasks(future_only=True)...")
    result = sync_outlook_tasks(future_only=True)
    print(f"Sync Result: {result}")
except Exception as e:
    print(f"Sync raised exception: {e}")

print("\n=== DIAGNOSTIC END ===")
