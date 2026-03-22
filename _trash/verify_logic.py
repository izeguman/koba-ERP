import sys
import os

# Add the project root to sys.path
sys.path.append(os.getcwd())

from app.db import get_yearly_inventory_status

# Run for the current year (assume 2024 or 2025)
try:
    items = get_yearly_inventory_status(2025, True)
    total_val = sum(item['total_value'] for item in items)
    total_rev = sum(item.get('potential_revenue', 0) for item in items)
    
    print(f"Total Value: {total_val}")
    print(f"Total Revenue: {total_rev}")
    
    if items:
        print("Sample Item:", items[0])
except Exception as e:
    print(e)
