
import math

class PalletCalculator:
    """
    제품 포장 정보 및 주문 수량을 기반으로 팔레트 적재 패턴과 필요 수량을 계산하는 클래스.
    """

    @staticmethod
    def calculate(specs: dict, total_qty: int) -> dict:
        """
        specs: {
            'box_l': int,      # mm
            'box_w': int,      # mm
            'box_h': int,      # mm
            'items_per_box': int,
            'max_layer': int
        }
        total_qty: 주문 총 수량 (Products)
        
        return: {
            'pallet_type': str,      # '800x800 목재(4-Way)' or '1100x1100 플라스틱' or '1100x1100 목재' 등
            'pattern_str': str,      # '1열 x 1행'
            'layer_count': int,      # 적재 단수
            'box_per_layer': int,    # 한 단의 박스 수
            'total_pallets': int,    # 필요 팔레트 수
            'boxes_per_pallet': int, # 팔레트당 최대 박스 수
            'total_boxes': int,      # 총 박스 수
            'remainder_boxes': int   # 마지막 팔레트의 박스 수 (0이면 딱 떨어짐)
        }
        """
        
        # 0. 입력값 검증 및 초기화
        box_l = specs.get('box_l', 0)
        box_w = specs.get('box_w', 0)
        # box_h = specs.get('box_h', 0) # 높이는 적재 높이 계산용 (필요시)
        items_per_box = specs.get('items_per_box', 1)
        max_layer = specs.get('max_layer', 1)
        
        if box_l <= 0 or box_w <= 0 or items_per_box <= 0:
            return {
                'pallet_type': "정보 부족",
                'pattern_str': "-",
                'layer_count': 0,
                'total_pallets': 0,
                'error': "박스 크기 또는 수량 정보가 올바르지 않습니다."
            }
            
        # 총 박스 수 계산 (올림)
        total_boxes = math.ceil(total_qty / items_per_box)
        
        # 1. 팔레트 및 적재 패턴 결정
        check_width = box_l * 2
        
        pallet_type = ""
        col_count = 0
        row_count = 0
        
        # Rule 1: Width Check
        if check_width > 1200:
            # 1열 강제
            col_count = 1
            row_count = 1 # 기본적으로 1행 (가로/세로 비율에 따라 달라질 수 있으나, 일단 1박스/단 가정)
            
            # 팔레트 선정
            if box_l <= 800 and box_w <= 800:
                pallet_type = "800 x 800 mm 목재(4-Way)"
            else:
                pallet_type = "1100 x 1100 mm 표준" # 재질은 상황에 따라 (보통 이정도 크기면 플라스틱/목재 혼용이나 로직상 표준)
                # User Request: "표준 팔레트 (1100x1100) 사용"이라고만 되어 있음.
                
        else: # check_width <= 1200
            # 다열 적재 가능 -> 표준 플라스틱 팔레트
            pallet_type = "1100 x 1100 mm 플라스틱"
            
            # 1100 기준 최대 열/행 계산
            # 박스 방향 회전 고려는 복잡하므로, 일단 정방향(L이 1100쪽) 가정? 
            # 아니면 L, W 중 긴 쪽을 최적화?
            # User Algorithm: 
            # Col_Count = Floor(1100 / Box_L)
            # Row_Count = Floor(1100 / Box_W)
            
            col_count = math.floor(1100 / box_l)
            row_count = math.floor(1100 / box_w)
            
            # 예외: 530*2 = 1060 <= 1200. Col=2.
        
        # 한 단 적재량
        box_per_layer = col_count * row_count
        if box_per_layer == 0: box_per_layer = 1 # 방어 코드
        
        # 2. 필요 팔레트 수량 계산
        # 팔레트당 최대 박스 수 = 한 단 박스 수 * 최대 적재 단수
        max_boxes_per_pallet = box_per_layer * max_layer
        
        # 총 필요 팔레트 수 (올림)
        total_pallets = math.ceil(total_boxes / max_boxes_per_pallet)
        
        # 나머지 계산 (마지막 팔레트에 몇 박스?)
        remainder_boxes = total_boxes % max_boxes_per_pallet
        
        # [수정] 표시용 적재 단수 계산
        # 1개 팔레트만 나올 경우, 실제 적재된 단수를 사용 (예: 10박스, 단당 8개 -> 2단)
        # 여러 팔레트일 경우 표준(최대) 단수 표시
        if total_pallets == 1:
            display_layer_count = math.ceil(total_boxes / box_per_layer)
        else:
            display_layer_count = max_layer
        
        return {
            'pallet_type': pallet_type,
            'pattern_str': f"{col_count}열 x {row_count}행",
            'layer_count': display_layer_count,
            'box_per_layer': box_per_layer,
            'total_pallets': total_pallets,
            'boxes_per_pallet': max_boxes_per_pallet,
            'total_boxes': total_boxes,
            'remainder_boxes': remainder_boxes,
            'items_per_box': items_per_box,
            'col_count': col_count,
            'row_count': row_count
        }

    @staticmethod
    def calculate_mixed(items: list) -> dict:
        """
        다차종 혼적 계산 (주인+손님 전략)
        items: list of dict { 'item_code', 'item_name', 'qty', 'box_l', 'box_w', 'box_h', 'items_per_box', 'max_layer' }
        """
        if not items: return {}
        
        # 1. Base Product 선정 (총 부피 기준)
        for item in items:
            item['total_boxes'] = math.ceil(item['qty'] / item.get('items_per_box', 1))
            vol = item.get('box_l', 0) * item.get('box_w', 0) * item.get('box_h', 0)
            item['total_volume'] = vol * item['total_boxes']
            item['item_name'] = item.get('item_name') or item['item_code']
            
        sorted_items = sorted(items, key=lambda x: x['total_volume'], reverse=True)
        base_item = sorted_items[0]
        others = sorted_items[1:]
        
        # 2. Base Product 적재 계산
        base_res = PalletCalculator.calculate(base_item, base_item['qty'])
        
        total_pallets = base_res['total_pallets']
        box_per_layer = base_res['box_per_layer']
        boxes_on_last_pallet = base_res['remainder_boxes']
        
        if boxes_on_last_pallet == 0 and total_pallets > 0:
            boxes_on_last_pallet = base_res['boxes_per_pallet']
            
        # 잔여 공간(Top Layer Empty Slots) 확인
        used_on_top = boxes_on_last_pallet % box_per_layer
        
        free_slots = 0
        if used_on_top > 0:
            free_slots = box_per_layer - used_on_top
            
        # 면적 기준으로 잔여 공간 가용성 판단
        base_box_area = base_item.get('box_l', 0) * base_item.get('box_w', 0)
        available_area = free_slots * base_box_area
        
        addon_summary = []
        addon_details = []
        
        for addon in others:
            addon_boxes = addon['total_boxes']
            addon_area = addon.get('box_l', 0) * addon.get('box_w', 0)
            needed_area = addon_boxes * addon_area
            
            # 조건: 잔여 공간이 있고, Add-on이 그 공간에 물리적으로 들어가는지 (면적 비교)
            if free_slots > 0 and available_area >= needed_area:
                 # 혼적 성공
                 available_area -= needed_area # 공간 차감
                 addon_summary.append(f"{addon['item_name']} {addon_boxes}박스(혼적)")
                 addon['loaded_on_base'] = True
                 addon_details.append(addon)
            else:
                 # 혼적 불가 -> 개별 팔레트 추가
                 addon_res = PalletCalculator.calculate(addon, addon['qty'])
                 total_pallets += addon_res['total_pallets']
                 addon_summary.append(f"{addon['item_name']} {addon_res['total_pallets']} PLT(개별)")
        
        # 3. 상세 리포트 텍스트 생성
        base_name = base_item['item_name']
        
        # (1) 기본 원칙
        report = f"적재 패턴 (Stacking Pattern) 기본 원칙: 바닥 면적이 넓은 [{base_name}]를 1단에 깔고, 남은 공간에 잔여 박스와 부가 제품을 적재.\n\n"
        
        # (2) Bottom Layer (Full Layers)
        # 마지막 팔레트의 꽉 찬 단 수
        full_layers_cnt = boxes_on_last_pallet // box_per_layer
        if full_layers_cnt > 0:
            report += f"{full_layers_cnt}단 (Bottom): [{base_name}] x {full_layers_cnt * box_per_layer} Box\n"
            
        # (3) 배열 및 면적
        # 보통 L이 열(Column), W가 행(Row) 대응
        col_c = base_res['col_count']
        row_c = base_res['row_count']
        occ_w = col_c * base_item.get('box_l', 0)
        occ_h = row_c * base_item.get('box_w', 0)
        
        report += f"배열: {col_c}열({base_item.get('box_l')}쪽) X {row_c}행({base_item.get('box_w')}쪽)\n"
        report += f"점유 면적: {occ_w}mm X {occ_h}mm (팔레트 내 안정적 안착)\n\n"
        
        # (4) Top Layer (Mixed)
        top_layer_num = full_layers_cnt + 1
        base_top_qty = boxes_on_last_pallet % box_per_layer
        
        mixed_items_str = f"[{base_name}] X {base_top_qty} Box"
        for ad in addon_details:
             mixed_items_str += f" + [{ad['item_name']}] X {ad['total_boxes']} Box"
             
        report += f"{top_layer_num}단 (Top): {mixed_items_str} 중앙 정렬하여 적재.\n"
        
        # (5) Height Difference
        for ad in addon_details:
             b_h = base_item.get('box_h', 0)
             a_h = ad.get('box_h', 0)
             diff_cm = abs(b_h - a_h) / 10.0
             report += f"[{ad['item_name']}]({a_h}mm)와 [{base_name}]({b_h}mm)의 높이 차({diff_cm}cm)는 랩핑으로 커버 가능.\n"

        # 결과 종합: 사용자 요청 포맷 적용
        # 예: 1 PLT, 2단 2 x 4 배열 11박스, 1100 x 1100 mm 플라스틱, 1단 : 38-101A 8박스, 2단 : 38101A 2박스 + MOD 29 1박스
        
        # 1. 기본 정보
        summary_text = f"{base_res['total_pallets']} PLT, {base_res['layer_count']}단 {base_res['col_count']} x {base_res['row_count']} 배열 {sum(i['total_boxes'] for i in items)}박스, {base_res['pallet_type']}"
        
        # 2. 1단 & 상단 정보 (혼적일 경우에만 표시)
        if addon_details:
            # 1단 정보 (Base Item)
            summary_text += f", 1단 : {base_item['item_name']} {base_res['box_per_layer']}박스"
            
            # 상단(Top) 또는 혼적 정보
            top_layer_num = base_res['layer_count'] # 전체 단수와 동일하다고 가정 (Top Layer)
            
            # Top Layer 구성원
            top_items = []
            if base_top_qty > 0:
                top_items.append(f"{base_item['item_name']} {base_top_qty}박스")
            for ad in addon_details:
                 top_items.append(f"{ad['item_name']} {ad['total_boxes']}박스") # Addon은 모두 Top에 있다고 가정 (혼적 성공 시)

            if top_items:
                summary_text += f", {top_layer_num}단 : {' + '.join(top_items)}"
        
        # (옵션) 혼적되지 않고 개별 팔레트로 떨어진 부가 제품들
        # 별도 표기? " / [개별] 품명 X PLT"
        # 요청 포맷에는 없지만 데이터 유실 방지를 위해 뒤에 붙임
        non_mixed = [f"{item['item_name']} {item['total_boxes']}박스(개별)" for item in others if not item.get('loaded_on_base')]
        if non_mixed:
             summary_text += " / " + ", ".join(non_mixed)
             
        # summary_text = f"메인: {base_item['item_name']} {base_res['total_pallets']} PLT"
        # if addon_summary:
        #     summary_text += " / " + ", ".join(addon_summary)
            
        return {
            'pallet_type': base_res['pallet_type'],
            'pattern_str': report, # Use detailed report as pattern string for UI
            'detailed_pattern_text': report,
            'summary_text': summary_text, # Short summary for Excel/DB
            
            'layer_count': base_res['layer_count'],
            'total_pallets': total_pallets,
            'total_boxes': sum(i['total_boxes'] for i in items),
            'mixed_mode': True,
            
            # UI 호환용 필드
            'box_per_layer': base_res['box_per_layer'],
            'col_count': base_res['col_count'],
            'row_count': base_res['row_count'],
            'boxes_per_pallet': base_res['boxes_per_pallet']
        }
