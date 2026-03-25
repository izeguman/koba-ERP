import math
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.logic.pallet_calculator import PalletCalculator

def test_pallet_logic_v2():
    print("=== Pallet Loading Algorithm Test v2 (Continuous Stacking) ===")
    
    # 사용자 요구 케이스
    # 38-101A (10 box), MOD 781 (3 box), MOD 781B (1 box), MOD 29 (1 box)
    # 1단 8개, 2단 나머지 + 다른 품목들
    items = [
        {'item_code': 'B001', 'item_name': 'MOD 29', 'qty': 1, 'box_l': 500, 'box_w': 400, 'box_h': 250, 'items_per_box': 1, 'max_layer': 5},
        {'item_code': 'B002', 'item_name': '38-101A', 'qty': 10, 'box_l': 530, 'box_w': 250, 'box_h': 230, 'items_per_box': 1, 'max_layer': 5},
        {'item_code': 'B003', 'item_name': 'MOD 781', 'qty': 3, 'box_l': 500, 'box_w': 400, 'box_h': 250, 'items_per_box': 1, 'max_layer': 5},
        {'item_code': 'B004', 'item_name': 'MOD 781B', 'qty': 1, 'box_l': 500, 'box_w': 400, 'box_h': 250, 'items_per_box': 1, 'max_layer': 5},
    ]
    
    result = PalletCalculator.calculate_mixed(items)
    print(result['pattern_str'])

if __name__ == "__main__":
    test_pallet_logic_v2()
