
import math

class PalletCalculator:
    """
    제품 포장 정보 및 주문 수량을 기반으로 팔레트 적재 패턴과 필요 수량을 계산하는 클래스.
    """

    @staticmethod
    def calculate(specs: dict, total_qty: int) -> dict:
        """
        [이전 로직 - 단일 품목 전용 가이드용]
        """
        box_l = specs.get('box_l', 0)
        box_w = specs.get('box_w', 0)
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
            
        total_boxes = math.ceil(total_qty / items_per_box)
        check_width = box_l * 2
        
        pallet_type = ""
        col_count = 0
        row_count = 0
        
        if check_width > 1200:
            col_count = 1
            row_count = 1 
            if box_l <= 800 and box_w <= 800:
                pallet_type = "800 x 800 mm 목재(4-Way)"
            else:
                pallet_type = "1100 x 1100 mm 표준"
        else:
            pallet_type = "1100 x 1100 mm 플라스틱"
            col_count = math.floor(1100 / box_l)
            row_count = math.floor(1100 / box_w)
            
        box_per_layer = col_count * row_count
        if box_per_layer == 0: box_per_layer = 1
        
        max_boxes_per_pallet = box_per_layer * max_layer
        total_pallets = math.ceil(total_boxes / max_boxes_per_pallet)
        remainder_boxes = total_boxes % max_boxes_per_pallet
        
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
        Heuristic 기반 알고리즘 (실제 적재 수량 기준 Footprint/그리드 계산 개선)
        """
        if not items: return {}

        for item in items:
            item['total_boxes'] = math.ceil(item['qty'] / item.get('items_per_box', 1))
            item['item_name'] = item.get('item_name') or item['item_code']
            item['remaining'] = item['total_boxes']

        addon_candidates = [it for it in items] 
        pallets = []
        current_plt_idx = 1

        while any(it['remaining'] > 0 for it in addon_candidates):
            current_pallet_layers = []
            active_at_start = [it for it in addon_candidates if it['remaining'] > 0]
            if not active_at_start: break
            initial_base_info = sorted(active_at_start, key=lambda x: (x['box_l'] * x['box_w'] * x['remaining']), reverse=True)[0]
            max_pallet_layers = initial_base_info.get('max_layer', 5)
            
            prev_layer_w = 1100
            prev_layer_d = 1100
            
            for layer_no in range(1, max_pallet_layers + 1):
                active_for_layer = [it for it in addon_candidates if it['remaining'] > 0]
                if not active_for_layer: break 
                
                candidates = sorted(active_for_layer, key=lambda x: (x['box_l'] * x['box_w'] * x['remaining']), reverse=True)
                best_layer_base = None
                best_col, best_row = 0, 0
                
                for cand in candidates:
                    cand_l = cand['box_l']
                    cand_w = cand['box_w']
                    if cand_l <= prev_layer_w and cand_w <= prev_layer_d:
                        c_col = math.floor(prev_layer_w / cand_l)
                        c_row = math.floor(prev_layer_d / cand_w)
                        if max(cand_l, cand_w) * 2 > 1200: c_col = 1
                        if c_col * c_row > 0:
                            best_layer_base = cand
                            best_col = c_col
                            best_row = c_row
                            break
                
                if not best_layer_base: break 
                
                base_l = best_layer_base['box_l']
                base_w = best_layer_base['box_w']
                current_layer_items = []
                max_slots = best_col * best_row
                base_box_area = base_l * base_w
                available_area_total = max_slots * base_box_area
                
                # 주인 배치
                take = min(best_layer_base['remaining'], max_slots)
                best_layer_base['remaining'] -= take
                total_placed_slots = take
                current_layer_items.append({'name': best_layer_base['item_name'], 'qty': take})
                
                available_area_now = (max_slots - take) * base_box_area
                
                # 손님(Add-on) 끼워 넣기
                if (total_placed_slots < max_slots or available_area_now > 0) and layer_no < max_pallet_layers:
                    sorted_addons = sorted(addon_candidates, key=lambda x: x['remaining'], reverse=True)
                    for addon in sorted_addons:
                        if addon['remaining'] <= 0: continue
                        if addon == best_layer_base: continue 
                        addon_l = addon['box_l']
                        addon_w = addon['box_w']
                        if addon_l > base_l or addon_w > base_w: continue
                            
                        addon_area = addon_l * addon_w
                        # 빈 슬롯(full slot) 활용
                        if addon_area > 0 and addon_area <= base_box_area and total_placed_slots < max_slots:
                            take_addon = min(addon['remaining'], max_slots - total_placed_slots)
                            addon['remaining'] -= take_addon
                            total_placed_slots += take_addon
                            available_area_now -= (take_addon * base_box_area)
                            existing = next((i for i in current_layer_items if i['name'] == addon['item_name']), None)
                            if existing: existing['qty'] += take_addon
                            else: current_layer_items.append({'name': addon['item_name'], 'qty': take_addon})
                        
                        # 슬롯 내 자투리 면적 활용
                        elif addon_area > 0 and (available_area_now + 5) >= addon_area:
                             can_fit_count = math.floor((available_area_now + 5) / addon_area)
                             if can_fit_count > 0:
                                 take_addon = min(addon['remaining'], can_fit_count)
                                 addon['remaining'] -= take_addon
                                 slots_needed = math.ceil((take_addon * addon_area) / base_box_area)
                                 # 이미 점유된 슬롯의 일부라면 total_placed_slots 증가 불필요?
                                 # 여기서는 단순히 total_placed_slots(Footprint 결정용)를 늘림
                                 # 단, 이미 take 등에 의해 점유된 영역 내라면 늘리지 않아야 함.
                                 # 하지만 heuristic상 복잡하므로, 면적 비례로 슬롯을 더 점유했다고 침.
                                 total_placed_slots += slots_needed 
                                 available_area_now -= (take_addon * addon_area)
                                 existing = next((i for i in current_layer_items if i['name'] == addon['item_name']), None)
                                 if existing: existing['qty'] += take_addon
                                 else: current_layer_items.append({'name': addon['item_name'], 'qty': take_addon})
                        if total_placed_slots >= max_slots: break
                
                if current_layer_items:
                    # [핵심] 실제 점유된 슬롯 기준 행/열 재계산
                    # total_placed_slots를 best_col(가로칸수)로 나누어 실제 몇 행을 쓰는지 도출
                    total_placed_slots = min(total_placed_slots, max_slots)
                    actual_rows = math.ceil(total_placed_slots / best_col)
                    actual_cols = min(total_placed_slots, best_col)
                    
                    current_footprint_w = actual_cols * base_l
                    current_footprint_d = actual_rows * base_w

                    current_pallet_layers.append({
                        'layer_no': layer_no, 
                        'items': current_layer_items,
                        'footprint_w': current_footprint_w,
                        'footprint_d': current_footprint_d,
                        'grid_info': f"{actual_cols}열 x {actual_rows}행"
                    })
                    prev_layer_w = current_footprint_w
                    prev_layer_d = current_footprint_d
            
            if current_pallet_layers:
                pallets.append({
                    'pallet_no': current_plt_idx,
                    'layers': current_pallet_layers
                })
                current_plt_idx += 1

        # Phase 3: 결과 출력 리포트 및 요약 생성
        report_lines = []
        compact_summary_lines = []
        total_boxes_in_all = sum(it['total_boxes'] for it in items)
        
        for plt in pallets:
            report_lines.append(f"[팔레트 #{plt['pallet_no']}]")
            plt_compact_parts = []
            for ly in plt['layers']:
                items_str = " + ".join([f"{it['name']} ({it['qty']} Box)" for it in ly['items']])
                mix_tag = " 혼적" if len(ly['items']) > 1 else ""
                fp_str = f"({ly['footprint_w']} x {ly['footprint_d']})"
                grid_str = f" {ly['grid_info']} |" if ly['grid_info'] else ""
                
                report_lines.append(f"  [{ly['layer_no']}단] {fp_str}{grid_str} {items_str}{mix_tag}")
                
                layer_items_compact = "+".join([f"{it['name']}({it['qty']})" for it in ly['items']])
                plt_compact_parts.append(f"[{ly['layer_no']}단]{layer_items_compact}")
            
            report_lines.append("")
            compact_summary_lines.append(f"PLT #{plt['pallet_no']}: " + " / ".join(plt_compact_parts))

        total_pallets = len(pallets)
        report_lines.append(f"총 필요 팔레트: {total_pallets} PLT")
        full_report = "\n".join(report_lines)
        
        simple_summary = f"{total_pallets} PLT, 총 {total_boxes_in_all} 박스"
        secondary_pkg_text = f"{total_pallets} PLT (총 {total_boxes_in_all} Box)"
        if compact_summary_lines:
             secondary_pkg_text += " | " + " | ".join(compact_summary_lines)
        
        return {
            'pallet_type': "1100 x 1100 mm 플라스틱",
            'pattern_str': full_report,
            'detailed_pattern_text': full_report,
            'summary_text': simple_summary,
            'secondary_packaging_text': secondary_pkg_text,
            'total_pallets': total_pallets,
            'total_boxes': total_boxes_in_all,
            'layers_data': pallets,
            'mixed_mode': True
        }
