import math
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.logic.pallet_calculator import PalletCalculator

def test_pallet_logic_v6():
    print("=== Pallet Loading Algorithm Test v6 (UI vs Storage Separation) ===")
    
    items = [
        {'item_code': 'B001', 'item_name': 'MOD 29', 'qty': 1, 'box_l': 500, 'box_w': 400, 'box_h': 250, 'items_per_box': 1, 'max_layer': 5},
        {'item_code': 'B002', 'item_name': '38-101A', 'qty': 10, 'box_l': 530, 'box_w': 250, 'box_h': 230, 'items_per_box': 1, 'max_layer': 5},
        {'item_code': 'B003', 'item_name': 'MOD 781', 'qty': 3, 'box_l': 500, 'box_w': 400, 'box_h': 250, 'items_per_box': 1, 'max_layer': 5},
        {'item_code': 'B004', 'item_name': 'MOD 781B', 'qty': 1, 'box_l': 500, 'box_w': 400, 'box_h': 250, 'items_per_box': 1, 'max_layer': 5},
    ]
    
    result = PalletCalculator.calculate_mixed(items)
    
    print("\n[UI Label Summary (summary_text)]")
    print(f"Expect: Concise (e.g., 1 PLT, 15 Box)")
    print(f"Actual: {result['summary_text']}")
    
    print("\n[Storage Detail Summary (secondary_packaging_text)]")
    print(f"Expect: Detailed (e.g., 1 PLT (15 Box) | PLT #1: ...)")
    print(f"Actual: {result['secondary_packaging_text']}")
    
    print("\n[Pattern Report (pattern_str)]")
    print(f"Expect: Multi-line, 'Box' text, spaces preserved")
    print(result['pattern_str'])

if __name__ == "__main__":
    test_pallet_logic_v6()
