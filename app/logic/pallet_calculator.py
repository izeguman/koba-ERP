
import math

class PalletCalculator:
    """
    제품 포장 정보 및 주문 수량을 기반으로 팔레트 적재 패턴과 필요 수량을 계산하는 클래스.
    """

    @staticmethod
    def calculate(specs: dict, total_qty: int) -> dict:
        """
        팔레트 적재 계산 (표준) - 1줄 요약 추가
        """
        box_l = specs.get('box_l', 0)
        box_w = specs.get('box_w', 0)
        items_per_box = specs.get('items_per_box', 1)
        max_layer = specs.get('max_layer', 1)
        item_name = specs.get('item_name') or specs.get('item_code') or "제품"
        
        if box_l <= 0 or box_w <= 0 or items_per_box <= 0:
            return {
                'pallet_type': "정보 부족", 'pattern_str': "-", 'layer_count': 0, 'total_pallets': 0, 'summary_text': "계산 불가"
            }
            
        total_boxes = math.ceil(total_qty / items_per_box)
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
        
        # 1줄 요약 생성
        tag = f"1~{display_layer_count}단" if display_layer_count > 1 else "1단"
        summary_text = f"{total_pallets} PLT {pallet_type}, {tag} : {item_name} {total_boxes}박스[{col_count}열x{row_count}행]"

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
            'row_count': row_count,
            'summary_text': summary_text
        }

    @staticmethod
    def calculate_mixed(items: list) -> dict:
        """
        다차종 혼적 계산 (최종 보완: 요약 텍스트 완벽 지원)
        """
        if not items: return {}

        # [Step 1] 데이터 전처리
        size_groups = {}
        for item in items:
            l, w, h = item.get('box_l', 0), item.get('box_w', 0), item.get('box_h', 0)
            key = (l, w, h)
            if key not in size_groups:
                size_groups[key] = {
                    'box_l': l, 'box_w': w, 'box_h': h,
                    'pool': [], 'total_boxes': 0, 'max_weight': 0
                }
            item_boxes = math.ceil(item['qty'] / item.get('items_per_box', 1))
            size_groups[key]['pool'].append({'name': item.get('item_name') or item['item_code'], 'qty': item_boxes})
            size_groups[key]['total_boxes'] += item_boxes
            size_groups[key]['max_weight'] = max(size_groups[key]['max_weight'], item.get('box_weight', 0.0))

        virtual_items = []
        for key, g in size_groups.items():
            v_item = {
                'item_code': f"GRP_{key[0]}x{key[1]}_{key[2]}",
                'box_l': g['box_l'], 'box_w': g['box_w'], 'box_h': g['box_h'],
                'total_boxes': g['total_boxes'], 'weight': g['max_weight'],
                'pool': g['pool'], 'consumed_idx': 0, 'current_item_rem': g['pool'][0]['qty'],
                'total_area': (g['box_l'] * g['box_w']) * g['total_boxes']
            }
            if len(g['pool']) == 1: v_item['item_name'] = g['pool'][0]['name']
            else: v_item['item_name'] = f"{g['pool'][0]['name']} 외 {len(g['pool'])-1}종"
            virtual_items.append(v_item)

        sorted_items = sorted(virtual_items, key=lambda x: (x['total_area'], x['box_l']*x['box_w'], x['weight']), reverse=True)
        base_res = PalletCalculator.calculate(items[0], 0)
        pallet_type_name = base_res['pallet_type']
        pallet_max_layers = items[0].get('max_layer', 5)
        p_w, p_l = 1100, 1100
        if "800 x 800" in pallet_type_name: p_w, p_l = 800, 800

        def consume_from_pool(v_it, count):
             results = []
             c_rem = count
             while c_rem > 0 and v_it['consumed_idx'] < len(v_it['pool']):
                  curr_p = v_it['pool'][v_it['consumed_idx']]
                  take = min(c_rem, v_it['current_item_rem'])
                  results.append({'name': curr_p['name'], 'qty': take})
                  c_rem -= take
                  v_it['current_item_rem'] -= take
                  if v_it['current_item_rem'] <= 0:
                       v_it['consumed_idx'] += 1
                       if v_it['consumed_idx'] < len(v_it['pool']):
                            v_it['current_item_rem'] = v_it['pool'][v_it['consumed_idx']]['qty']
             return results

        def get_layer_info(layer_items):
             if not layer_items: return 0, 0, []
             grouped_by_code = {}
             for it in layer_items:
                  c = it['code']
                  if c not in grouped_by_code: grouped_by_code[c] = {'l': it['l'], 'w': it['w'], 'qty': 0, 'details': []}
                  grouped_by_code[c]['qty'] += it['qty']
                  grouped_by_code[c]['details'].extend(it['details'])
             tw, tl, results = 0, 0, []
             for c, info in grouped_by_code.items():
                  col_c = max(1, math.floor(p_w / info['l']))
                  used_cols = min(info['qty'], col_c)
                  rows_f = info['qty'] / used_cols
                  row_str = f"{rows_f:.1f}".rstrip('0').rstrip('.')
                  unpacked = {}
                  for d in info['details']: unpacked[d['name']] = unpacked.get(d['name'], 0) + d['qty']
                  results.append({
                      'summary': " + ".join([f"{name} ({q} Box)" for name, q in unpacked.items()]),
                      'unpacked': unpacked,
                      'arr': f"[{used_cols}열x{row_str}행]", # 공백 제거 요청 여부 확인 (예시엔 공백 없음)
                      'w': used_cols * info['l'], 'l': math.ceil(rows_f) * info['w']
                  })
                  tw = max(tw, used_cols * info['l'])
                  tl += math.ceil(rows_f) * info['w']
             return tw, tl, results

        # 3. 시뮬레이션
        pallets = []
        for item in sorted_items:
            rem = item['total_boxes']
            while rem > 0:
                packed = 0
                if pallets and pallets[-1]['layers']:
                    ll = pallets[-1]['layers'][-1]
                    pw, pl = 9999, 9999
                    if len(pallets[-1]['layers']) > 1:
                         prev = pallets[-1]['layers'][-2]
                         pw, pl = prev['occ_w'], prev['occ_l']
                    for q in range(1, rem + 1):
                         test = ll['items'] + [{'code': item['item_code'], 'qty': q, 'l': item['box_l'], 'w': item['box_w'], 'details': []}]
                         tw, tl, _ = get_layer_info(test)
                         if tw <= p_w and tl <= p_l and tw <= pw and tl <= pl: packed, bw, bl = q, tw, tl
                         else: break
                    if packed > 0:
                         ll['items'].append({'code': item['item_code'], 'qty': packed, 'l': item['box_l'], 'w': item['box_w'], 'details': consume_from_pool(item, packed)})
                         ll['occ_w'], ll['occ_l'] = bw, bl
                         rem -= packed; continue
                if pallets and len(pallets[-1]['layers']) < pallet_max_layers:
                    cp = pallets[-1]
                    pw, pl = 9999, 9999
                    if cp['layers']:
                         prev = cp['layers'][-1]
                         pw, pl = prev['occ_w'], prev['occ_l']
                    for q in range(1, rem + 1):
                         test = [{'code': item['item_code'], 'qty': q, 'l': item['box_l'], 'w': item['box_w'], 'details': []}]
                         tw, tl, _ = get_layer_info(test)
                         if tw <= p_w and tl <= p_l and tw <= pw and tl <= pl: packed, bw, bl = q, tw, tl
                         else: break
                    if packed > 0:
                         cp['layers'].append({'occ_w': bw, 'occ_l': bl, 'items': [{'code': item['item_code'], 'qty': packed, 'l': item['box_l'], 'w': item['box_w'], 'details': consume_from_pool(item, packed)}]})
                         rem -= packed; continue
                pallets.append({'no': len(pallets)+1, 'layers': []})
                col_c, row_c = max(1, math.floor(p_w/item['box_l'])), max(1, math.floor(p_l/item['box_w']))
                packed = min(rem, col_c * row_c)
                bw, bl, _ = get_layer_info([{'code': item['item_code'], 'qty': packed, 'l': item['box_l'], 'w': item['box_w'], 'details': []}])
                pallets[-1]['layers'].append({'occ_w': bw, 'occ_l': bl, 'items': [{'code': item['item_code'], 'qty': packed, 'l': item['box_l'], 'w': item['box_w'], 'details': consume_from_pool(item, packed)}]})
                rem -= packed

        # 4. 리포트 및 요약 문자열 생성
        report = f"추천 팔레트: {pallet_type_name}\n"
        total_boxes = sum(it['total_boxes'] for it in sorted_items)
        summary_txt = f"{len(pallets)} PLT {pallet_type_name}"
        summary_parts = []

        for p in pallets:
            report += f"\n[팔레트 #{p['no']}]\n"
            grps = []
            for idx, l in enumerate(p['layers']):
                l_no = idx + 1
                tw, tl, details = get_layer_info(l['items'])
                key = (tuple((d['summary'], d['arr']) for d in details), tw, tl)
                if not grps or grps[-1]['key'] != key:
                    grps.append({'start': l_no, 'end': l_no, 'key': key, 'details': details, 'w': tw, 'l': tl})
                else: grps[-1]['end'] = l_no
            
            is_mixed_plt = len(set(it['code'] for l in p['layers'] for it in l['items'])) > 1
            for g in grps:
                num = g['end'] - g['start'] + 1
                parts, s_parts = [], []
                for d in g['details']:
                     sub_parts, s_sub_parts = [], []
                     for name, q in d['unpacked'].items():
                          sub_parts.append(f"{name} ({q * num} Box)")
                          s_sub_parts.append(f"{name} {q * num}박스{d['arr']}")
                     parts.append(f"{' + '.join(sub_parts)} {d['arr']}")
                     s_parts.append(" + ".join(s_sub_parts))
                
                sum_text = " + ".join(parts)
                s_sum_text = " + ".join(s_parts)
                is_mixed_layer = (is_mixed_plt and g['start'] > 1) or len(g['details']) > 1
                if is_mixed_layer:
                     sum_text += " 혼적"
                     s_sum_text += " 혼적"
                
                tag = f"[{g['start']}단]" if g['start'] == g['end'] else f"[{g['start']}~{g['end']}단]"
                report += f"{tag} {sum_text} : {g['w']} x {g['l']} mm\n"
                
                s_tag = f"{g['start']}단" if g['start'] == g['end'] else f"{g['start']}~{g['end']}단"
                summary_parts.append(f"{s_tag} : {s_sum_text}")

        full_summary = f"{summary_txt}, {', '.join(summary_parts)}"

        return {
            'pallet_type': pallet_type_name,
            'pattern_str': report,
            'detailed_pattern_text': report,
            'summary_text': full_summary,
            'total_pallets': len(pallets),
            'total_boxes': total_boxes,
            'mixed_mode': True
        }
