import os

def fix_db():
    file_path = 'app/db.py'
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Lines are 0-indexed in list
    # We want to delete 2528 to 2621 (1-based)
    # 2528 1-based -> index 2527
    # 2621 1-based -> index 2620
    # So we want lines[:2527] + lines[2621:]
    
    # Let's verify the content at boundaries
    print(f"Line 2528 (will be deleted): {lines[2527]}")
    print(f"Line 2621 (will be deleted): {lines[2620]}")
    print(f"Line 2622 (will be kept): {lines[2621]}")
    
    # Check if Line 2528 starts with 'def get_yearly_financials'
    if 'def get_yearly_financials' not in lines[2527]:
        print("WARNING: Line 2528 does not look like start of get_yearly_financials")
        # return
    
    # Check if Line 2622 starts with 'def get_yearly_financials'
    if 'def get_yearly_financials' not in lines[2621]:
        print("WARNING: Line 2622 does not look like start of get_yearly_financials")
        # return

    new_lines = lines[:2527] + lines[2621:]
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    print("Successfully removed lines 2528-2621")

if __name__ == "__main__":
    fix_db()
