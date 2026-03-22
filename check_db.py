import sys
import os
import traceback

sys.path.append(os.getcwd())

log_file = "check_log.txt"

try:
    with open(log_file, "w", encoding="utf-8") as f:
        # Redirect stdout/stderr to file manually for the import part
        sys.stdout = f
        sys.stderr = f
        
        print("Starting import check...")
        try:
            import app.db
            print("Import successful!")
        except Exception:
            traceback.print_exc()
            print("Import failed with Exception.")
        except SyntaxError:
            traceback.print_exc()
            print("Import failed with SyntaxError.")
        except:
            traceback.print_exc()
            print("Import failed with unknown error.")
            
except Exception as e:
    # If file opening fails (unlikely)
    print(f"Failed to open log file: {e}")
