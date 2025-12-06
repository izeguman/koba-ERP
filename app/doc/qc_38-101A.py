import google.generativeai as genai
import json
import os
import pandas as pd
import math
import re
import unicodedata
import platform

# ---------------------------------------------------------
# 1. API 키 설정
# ---------------------------------------------------------
raw_api_key = "AIzaSyCQgEVkwdervsG8zdauyN4bw7sKH96eBGA"
api_key = raw_api_key.strip()

os.environ["GOOGLE_API_KEY"] = api_key
genai.configure(api_key=api_key)

# ---------------------------------------------------------
# 2. 검사 기준 (Criteria)
# ---------------------------------------------------------
criteria_5_4 = {
    "TESTER +15V": {"min": 14.25, "max": 15.75},
    "TESTER -15V": {"min": -15.75, "max": -14.25},
    "TESTER +5V": {"min": 4.75, "max": 5.25},
    "TESTER +3.3V": {"min": 3.135, "max": 3.465},
    "TESTER +1.2V": {"min": 1.14, "max": 1.26},
    "DUT_ZERO_CHECK": {"min": -1.2, "max": 1.2}
}

criteria_5_10 = {
    "DUT +5V Voltage": {"min": 4.5, "max": 5.2},
    "DUT +5V Current": {"min": 0.0, "max": 1.0},
    "DUT +15V Voltage": {"min": 14.25, "max": 15.75},
    "DUT -15V Voltage": {"min": -15.75, "max": -14.25},
    "DUT +15V Current": {"min": 0.0, "max": 0.5},
    "DUT ACROSS R51": {"min": -13.0, "max": 13.0}
}

criteria_7_3 = {
    "+15V": {"min": 14.25, "max": 15.75},
    "-15V": {"min": -15.75, "max": -14.25},
    "+1.2V": {"min": 1.14, "max": 1.26},
    "+5V": {"min": 4.6, "max": 5.4},
    "+3.3V": {"min": 3.135, "max": 3.465}
}

# 7.6 (us 단위)
criteria_7_6 = {
    "Period": {"min": 919, "max": 921},
    "Vmax": {"min": 1.08, "max": 1.32},
    "Vmin": {"min": -1.32, "max": -1.08}
}

# 7.7 (ms 단위 - 보통 7.6과 전압 스펙은 동일)
criteria_7_7 = {
    "Period": {"min": 919, "max": 921},
    "Vmax": {"min": 1.08, "max": 1.32},
    "Vmin": {"min": -1.32, "max": -1.08}
}

# 7.8 (ms 단위)
criteria_7_8 = {
    "Period": {"min": 919, "max": 921},
    "Vmax": {"min": 1.08, "max": 1.32},
    "Vmin": {"min": -1.32, "max": -1.08}
}


def analyze_pdf(file_path):
    print(f"🔄 분석 시작: {file_path}")

    if not os.path.exists(file_path):
        print("❌ 오류: 파일을 찾을 수 없습니다.")
        return []

    try:
        model = genai.GenerativeModel('gemini-2.5-pro')
        sample_file = genai.upload_file(path=file_path, display_name="Test Sheet Final V4")

        # [Page 1 Analysis] - 수정됨: Readback-Value 명시 강화
        prompt_p1 = """
        이 문서의 **1페이지**만 정밀 분석해줘.
        목표:
        1. Serial No, Date 추출.
        2. Visual Inspection (Item 1~4) Pass 확인.
        3. **Item 5 (ADC Readbacks)**:
           - 표의 'Readback-Value' 열의 값을 table_value로 추출.
           - **주의**: 'VALUE' 열(예: 15.0, 5.0)은 기준값이므로 절대 추출하지 말 것. 반드시 실제 측정값인 **'Readback-Value'** 열(예: 15.307)을 가져와야 함.
           - 이미지의 값(Image Value)과 비교.
           - TESTER 항목은 라벨 불일치 주의 (표: 'TESTER +15V' -> 이미지: '+15V').

        추출 데이터 구조 (JSON):
        {
          "meta_info": { "serial_no": "...", "date": "..." },
          "visual_inspection": [ {"id": "...", "result": "..."} ],
          "measurements": [ 
             {"item": "...", "table_value": 0.0, "image_value": 0.0, "table_result": "Pass"} 
          ]
        }
        """
        print("🤖 Page 1 분석 중...")
        res_p1 = model.generate_content([sample_file, prompt_p1])

        # [Page 2 Analysis] - 수정됨: Readback-Value 명시 강화
        prompt_p2 = """
        이 문서의 **2페이지**만 정밀 분석해줘.
        목표:
        1. Resistance (Item 6) - Pin, Measured(단위포함), Result.
        2. LEDs (Item 7).
        3. **Section 5.10 (Item 8)**:
           - 표의 **'Readback-Value'** 열의 값을 table_value로 추출.
           - **주의**: 'VALUE' 열(예: +5V, +0.990A)이나 'TOLERANCE' 열은 무시할 것. 오직 Readback-Value 값만 추출.
           - 이미지 값(Image Value)도 추출.

        추출 데이터 구조 (JSON):
        {
          "resistance_tests": [ {"pin": "...", "measured": "...", "result": "..."} ],
          "led_tests": [ {"led": "...", "result": "..."} ],
          "section_5_10": [ {"item": "...", "table_value": 0.0, "image_value": 0.0, "table_result": "..."} ]
        }
        """
        print("🤖 Page 2 분석 중...")
        res_p2 = model.generate_content([sample_file, prompt_p2])

        # [Page 3 Analysis] - 수정됨: Readback-Value 명시 강화
        prompt_p3 = """
        이 문서의 **3페이지**만 정밀 분석해줘.
        목표:
        1. **Item 9 (Section 7.3) Voltage Monitors**:
           - 표의 **'Readback-Value'** 열의 값을 table_value로 추출.
           - **주의**: 'VALUE' 열(예: +15V, +1.2V)은 무시. 반드시 **Readback-Value** 열의 측정값(예: 15.315)을 가져올 것.
           - 이미지 분석 필수: 우측 하단 Voltage Monitors 영역 값 추출.

        2. **Item 10 (Section 7.6) J6A 파형**:
           - 표의 'J6A Period', 'Vmax', 'Vmin' 값 (Readback-Value 열).
           - 파형 이미지의 'Vmax', 'Vmin', 'Vpp', 'Frequency(kHz)' 값 추출.
           - Frequency 소수점 정확히 인식할 것.

        추출 데이터 구조 (JSON):
        {
          "voltage_monitors": [ {"item": "...", "table_value": 0.0, "image_value": 0.0, "table_result": "..."} ],
          "waveform_J6A": {
             "table_rows": [ {"item": "...", "value": 0.0} ],
             "image_data": { "Vmax": 0.0, "Vmin": 0.0, "Vpp": 0.0, "Frequency_kHz": 0.0 }
          }
        }
        """
        print("🤖 Page 3 분석 중 (Voltage Monitors, J6A)...")
        res_p3 = model.generate_content([sample_file, prompt_p3])

        # [Page 4 Analysis] - Waveform J6B (Item 10) + J7A (Item 11)
        prompt_p4 = """
        이 문서의 **4페이지**만 정밀 분석해줘.
        목표:
        1. **Item 10 (Section 7.6) J6B 파형** (페이지 상단):
           - 표의 'Readback-Value' 추출 (J6B Period 등).
           - 해당 파형 이미지의 Vmax, Vmin, Vpp, Frequency 값.
        2. **Item 11 (Section 7.7) J7A 파형** (페이지 하단):
           - 표의 'Readback-Value' 추출 (J7A Period 등).
           - 해당 파형 이미지의 Vmax, Vmin, Vpp, Frequency 값.

        추출 데이터 구조 (JSON):
        {
          "waveform_J6B": {
             "table_rows": [ {"item": "...", "value": 0.0} ],
             "image_data": { "Vmax": 0.0, "Vmin": 0.0, "Vpp": 0.0, "Frequency_kHz": 0.0 }
          },
          "waveform_J7A": {
             "table_rows": [ {"item": "...", "value": 0.0} ],
             "image_data": { "Vmax": 0.0, "Vmin": 0.0, "Vpp": 0.0, "Frequency_kHz": 0.0 }
          }
        }
        """
        print("🤖 Page 4 분석 중 (J6B, J7A)...")
        res_p4 = model.generate_content([sample_file, prompt_p4])

        # [Page 5 Analysis] - Waveform J7B (Item 11) + J9A (Item 12)
        prompt_p5 = """
        이 문서의 **5페이지**만 정밀 분석해줘.
        목표:
        1. **Item 11 (Section 7.7) J7B 파형** (페이지 상단):
           - 표의 'Readback-Value' 추출 (J7B Period 등).
           - 해당 파형 이미지의 Vmax, Vmin, Vpp, Frequency 값.
        2. **Item 12 (Section 7.8) J9A 파형**:
           - 표의 'Readback-Value' 추출 (J9A Period 등).
           - 해당 파형 이미지의 Vmax, Vmin, Vpp, Frequency 값.

        추출 데이터 구조 (JSON):
        {
          "waveform_J7B": {
             "table_rows": [ {"item": "...", "value": 0.0} ],
             "image_data": { "Vmax": 0.0, "Vmin": 0.0, "Vpp": 0.0, "Frequency_kHz": 0.0 }
          },
          "waveform_J9A": {
             "table_rows": [ {"item": "...", "value": 0.0} ],
             "image_data": { "Vmax": 0.0, "Vmin": 0.0, "Vpp": 0.0, "Frequency_kHz": 0.0 }
          }
        }
        """
        print("🤖 Page 5 분석 중 (J7B, J9A)...")
        res_p5 = model.generate_content([sample_file, prompt_p5])

        # Merge Results
        def parse_json(text):
            match = re.search(r'\{.*\}', text, re.DOTALL)
            return json.loads(match.group(0)) if match else {}

        data1 = parse_json(res_p1.text)
        data2 = parse_json(res_p2.text)
        data3 = parse_json(res_p3.text)
        data4 = parse_json(res_p4.text)
        data5 = parse_json(res_p5.text)

        merged_data = {**data1, **data2, **data3, **data4, **data5}
        return merged_data

    except Exception as e:
        print(f"❌ 분석 중 오류 발생: {e}")
        return None


def parse_resistance_str(val_str):
    if not val_str: return 0.0
    s = str(val_str).upper().replace("OHM", "").replace(" ", "")
    multiplier = 1.0
    if "K" in s:
        multiplier = 1000.0
        s = s.replace("K", "")
    elif "M" in s:
        multiplier = 1000000.0
        s = s.replace("M", "")
    try:
        val = float(s)
        return val * multiplier
    except ValueError:
        return 0.0


def parse_voltage_current_str(val_str):
    if not val_str: return 0.0
    s = str(val_str).replace(" ", "")
    multiplier = 1.0
    if "mV" in s or "mA" in s:
        multiplier = 0.001
        s = s.replace("mV", "").replace("mA", "")
    elif "kHz" in s:
        multiplier = 1.0
        s = s.replace("kHz", "")
    elif "V" in s or "A" in s:
        s = s.replace("V", "").replace("A", "")

    try:
        return float(s) * multiplier
    except ValueError:
        try:
            return float(s)
        except:
            return 0.0


def check_value_consistency(table_val, image_val, item_name=""):
    if image_val is None:
        return "⚠️ 이미지 값 못 찾음"
    compared_img_val = image_val
    rounded_img_val = round(compared_img_val, 3)
    if abs(table_val - rounded_img_val) < 0.01:
        return "✅ 일치"
    truncated = int(compared_img_val * 1000) / 1000.0
    if abs(table_val - truncated) < 0.01:
        return "✅ 일치"
    return f"❌ 불일치 (이미지: {rounded_img_val})"


def save_to_excel(results, source_pdf_path, output_filename="정밀검사결과.xlsx"):
    try:
        folder_path = os.path.dirname(source_pdf_path)
        full_path = os.path.join(folder_path, output_filename)
        pd.DataFrame(results).to_excel(full_path, index=False)
        print(f"💾 엑셀 저장 완료! 위치: {full_path}")
    except Exception as e:
        print(f"⚠️ 엑셀 저장 실패: {e}")


def get_dynamic_onedrive_path(stored_path: str) -> str:
    if not stored_path: return ""
    onedrive_root = os.environ.get("OneDrive")
    if not onedrive_root:
        onedrive_root = os.environ.get("OneDriveConsumer")
    if not onedrive_root:
        onedrive_root = os.environ.get("OneDriveCommercial")
    if not onedrive_root:
        onedrive_root = os.path.join(os.path.expanduser("~"), "OneDrive")
    final_path = stored_path
    if "OneDrive" in stored_path:
        norm_stored = os.path.normpath(stored_path)
        try:
            idx = norm_stored.find("OneDrive")
            if idx != -1:
                relative_path = norm_stored[idx + 8:]
                if relative_path.startswith(os.sep): relative_path = relative_path[1:]
                new_path = os.path.join(onedrive_root, relative_path)
                new_path = unicodedata.normalize('NFC', new_path)
                final_path = new_path
        except Exception as e:
            print(f"경로 변환 중 오류: {e}")
    if os.path.exists(final_path): return final_path
    path_nfd = unicodedata.normalize('NFD', final_path)
    if os.path.exists(path_nfd): return path_nfd
    if platform.system() == 'Windows' and len(final_path) > 200:
        long_path = "\\\\?\\" + os.path.abspath(final_path)
        if os.path.exists(long_path): return long_path
    return final_path


# ---------------------------------------------------------
# 파형 분석 공통 함수 (출력 및 리스트 추가용)
# ---------------------------------------------------------
def process_waveform(wf_key, title, data_dict, criteria, final_results_list, unit_label="us"):
    print(f"\n=== {title} ===")
    print(f"{'항목':<12} | {'표값':<8} | {'이미지값(계산)':<15} | {'일치여부'} | {'스펙체크'}")
    print("-" * 100)

    wf_data = data_dict.get(wf_key, {})
    if not wf_data:
        print(f"⚠️ 데이터 없음: {wf_key}")
        return

    t_rows = wf_data.get("table_rows", [])
    img_data = wf_data.get("image_data", {})

    img_freq_khz = parse_voltage_current_str(img_data.get("Frequency_kHz"))
    img_vmax = parse_voltage_current_str(img_data.get("Vmax"))
    img_vmin = parse_voltage_current_str(img_data.get("Vmin"))
    img_vpp = parse_voltage_current_str(img_data.get("Vpp"))

    calc_period = 0.0
    if img_freq_khz > 0:
        calc_period = (1.0 / img_freq_khz) * 1000.0

    print(f"ℹ️ 이미지 분석: Freq={img_freq_khz}kHz → Period={round(calc_period, 1)}{unit_label}, Vpp={img_vpp}V")

    for row in t_rows:
        item_name = row.get("item")
        t_val = parse_voltage_current_str(row.get("value"))

        compared_val = 0.0
        note = ""

        if "Period" in item_name:
            compared_val = calc_period
            note = "(Freq환산)"
        elif "Vmax" in item_name:
            compared_val = img_vmax
        elif "Vmin" in item_name:
            compared_val = img_vmin

        consist = "✅ 일치"
        if abs(t_val - compared_val) > 0.1:
            if "Period" in item_name and abs(t_val - img_vpp) < 0.1:
                consist = f"❌실수의심(Vpp값기입: {t_val})"
            else:
                consist = f"❌ 불일치({round(compared_val, 2)})"

        spec_check = "-"
        for key in criteria:
            if key in item_name:
                spec = criteria[key]
                if spec['min'] <= t_val <= spec['max']:
                    spec_check = "✅Pass"
                else:
                    spec_check = f"❌Fail({spec['min']}~{spec['max']})"
                break

        print(
            f"{item_name:<12} | {str(t_val):<8} | {str(round(compared_val, 2)):<10} {note:<5} | {consist} | {spec_check}")

        final_results_list.append({
            "Page": title, "Category": wf_key, "Item": item_name,
            "Value": t_val, "Result": consist, "Note": f"{consist}, {spec_check}"
        })


if __name__ == "__main__":
    raw_target_file = r"C:\Users\권성관\OneDrive\ULVAC-PHI\8. 검사성적서 및 라벨\1. 38-101A\New\2025-11-04 출하(KT212-KT221)\KT212\38-101A Test Sheet_Rev.E7_KT212.pdf"
    target_file = get_dynamic_onedrive_path(raw_target_file)
    print(f"📂 분석 대상 파일: {target_file}")

    data = analyze_pdf(target_file)

    if data:
        final_results = []
        meta = data.get("meta_info", {})
        print(f"\n=== [Page 1] 기본 정보: {meta.get('serial_no')} / {meta.get('date')} ===")

        # 2. Visual
        print("\n=== [Page 1] 시각 검사 ===")
        for v in data.get("visual_inspection", []):
            print(f"Item {v.get('id'):<5}: {'✅' if v.get('result') == 'Pass' else '❌'} {v.get('result')}")

        # 3. Measurement (Page 1)
        print("\n=== [Page 1] 정밀 측정 (5번) ===")
        print(f"{'항목':<18} | {'표값':<8} | {'이미지값':<8} | {'비교'} | {'스펙체크'} | {'Table판정'}")
        for rec in data.get("measurements", []):
            item_name = rec.get('item')
            t_val = rec.get("table_value")
            i_val = rec.get("image_value")
            t_res = rec.get("table_result")
            consist = check_value_consistency(t_val, i_val)

            spec_check = "-"
            matched_key = None
            for key in criteria_5_4:
                if key != "DUT_ZERO_CHECK" and key in item_name:
                    matched_key = key;
                    break

            spec_min, spec_max = None, None
            if matched_key:
                spec_min = criteria_5_4[matched_key]['min']
                spec_max = criteria_5_4[matched_key]['max']
            elif item_name.startswith("DUT"):
                spec_min = criteria_5_4["DUT_ZERO_CHECK"]['min']
                spec_max = criteria_5_4["DUT_ZERO_CHECK"]['max']

            if spec_min is not None and spec_max is not None:
                if spec_min <= t_val <= spec_max:
                    spec_check = "✅Pass"
                else:
                    spec_check = f"❌Fail({spec_min}~{spec_max})"
            else:
                spec_check = "❓기준없음"

            res_icon = "✅" if t_res == "Pass" else "❌"
            print(
                f"{item_name:<18} | {str(t_val):<8} | {str(round(i_val, 3) if i_val else 'None'):<8} | {consist} | {spec_check} | {res_icon} {t_res}")
            rec['Note'] = f"{consist}, {spec_check}"
            final_results.append(rec)

        # 4. Resistance (Page 2)
        print("\n=== [Page 2] 저항 검사 (6번) ===")
        print(f"{'Pin':<5} | {'Measured':<8} | {'Ohm':<8} | {'판단'} | {'Table판정'}")
        for r in data.get("resistance_tests", []):
            measured_str = r.get("measured")
            ohm = parse_resistance_str(measured_str)
            status = "Short" if ohm <= 10 else "Not short"
            res_icon = "✅" if r.get("result") == "Pass" else "❌"
            print(
                f"{str(r.get('pin')):<5} | {str(measured_str):<8} | {str(ohm):<8} | {str(status):<8} | {res_icon} {str(r.get('result'))}")
            final_results.append(r)

        # 5. LEDs (Page 2)
        print("\n=== [Page 2] LED 검사 (7번) ===")
        for l in data.get("led_tests", []):
            res_val = l.get('result')
            icon = '✅' if (res_val == "Pass" or res_val == "ON") else '❌'
            print(f"LED {str(l.get('led')):<10}: {icon} {str(res_val)}")
            final_results.append(l)

        # 6. Item 8 (Page 2, Section 5.10)
        print("\n=== [Page 2] 추가 정밀 측정 (8번/5.10) ===")
        print(f"{'항목':<18} | {'표값':<8} | {'이미지값':<8} | {'계산비교'} | {'스펙체크'} | {'Table판정'}")
        print("-" * 100)
        section_8 = data.get("section_5_10", [])
        for rec in section_8:
            item = rec.get("item")
            t_val_raw = rec.get("table_value")
            i_val = rec.get("image_value")
            t_res = rec.get("table_result")
            t_val = parse_voltage_current_str(t_val_raw)
            comparison_note = ""
            compared_img = i_val
            if item and "DUT +5V Current" in item:
                compared_img = i_val * 2 if i_val else 0
                comparison_note = "(x2)"
            consist = "✅ 일치"
            if item and ("DUT ACROSS R51" in item or "R51" in item):
                consist = "-"
            elif i_val is not None:
                if abs(t_val - compared_img) < 0.01:
                    consist = "✅ 일치"
                else:
                    consist = f"❌ 불일치({round(compared_img, 3)})"
            else:
                consist = "⚠️ Img값 없음"
            spec_check = "-"
            matched_key = None
            for key in criteria_5_10:
                if key in item: matched_key = key; break
            if matched_key:
                spec = criteria_5_10[matched_key]
                if spec['min'] <= t_val <= spec['max']:
                    spec_check = "✅Pass"
                else:
                    spec_check = f"❌Fail({spec['min']}~{spec['max']})"
            elif item and "R51" in item:
                if abs(t_val) <= 13.0:
                    spec_check = "✅R51≤13"
                else:
                    spec_check = f"❌R51초과({t_val})"
            res_icon = "✅" if t_res in ["Pass", "Good"] else "❌"
            print(
                f"{str(item):<18} | {str(t_val):<8} | {str(round(i_val, 3) if i_val else '-'):<8} | {consist} {comparison_note} | {spec_check} | {res_icon} {str(t_res)}")
            final_results.append({"Page": 2, "Category": "Section 5.10", "Item": item, "Value": t_val, "Result": t_res,
                                  "Note": f"{consist}, {spec_check}"})

        # 7. Item 9 (Page 3, Section 7.3)
        print("\n=== [Page 3] Voltage Monitors (9번/7.3) ===")
        print(f"{'항목':<10} | {'표값':<8} | {'이미지값':<8} | {'일치여부'} | {'스펙체크'} | {'Table판정'}")
        print("-" * 100)
        vol_mons = data.get("voltage_monitors", [])
        for rec in vol_mons:
            item = rec.get("item")
            t_val = rec.get("table_value")
            i_val = rec.get("image_value")
            t_res = rec.get("table_result")
            consist = "✅ 일치"
            if i_val is None:
                consist = "⚠️ Img없음"
            else:
                if abs(t_val - i_val) < 0.01:
                    consist = "✅ 일치"
                else:
                    consist = f"❌ 불일치({round(i_val, 3)})"
            spec_check = "-"
            matched_key = None
            for key in criteria_7_3:
                if key in str(item).replace(" ", ""): matched_key = key; break
            if matched_key:
                spec = criteria_7_3[matched_key]
                if spec['min'] <= t_val <= spec['max']:
                    spec_check = "✅Pass"
                else:
                    spec_check = f"❌Fail({spec['min']}~{spec['max']})"
            res_icon = "✅" if t_res == "Pass" else "❌"
            print(
                f"{str(item):<10} | {str(t_val):<8} | {str(round(i_val, 3) if i_val else '-'):<8} | {consist} | {spec_check} | {res_icon} {str(t_res)}")
            final_results.append({"Page": 3, "Category": "Section 7.3", "Item": item, "Value": t_val, "Result": t_res,
                                  "Note": f"{consist}, {spec_check}"})

        # 8. Waveform Checks (J6A, J6B, J7A, J7B, J9A)
        process_waveform("waveform_J6A", "[Page 3] Waveform Check (10번/7.6 - J6A)", data, criteria_7_6, final_results,
                         "us")
        process_waveform("waveform_J6B", "[Page 4] Waveform Check (10번/7.6 - J6B)", data, criteria_7_6, final_results,
                         "us")
        process_waveform("waveform_J7A", "[Page 4] Waveform Check (11번/7.7 - J7A)", data, criteria_7_7, final_results,
                         "ms")
        process_waveform("waveform_J7B", "[Page 5] Waveform Check (11번/7.7 - J7B)", data, criteria_7_7, final_results,
                         "ms")
        process_waveform("waveform_J9A", "[Page 5] Waveform Check (12번/7.8 - J9A)", data, criteria_7_8, final_results,
                         "ms")

        save_to_excel(final_results, target_file)
    else:
        print("데이터 추출 실패")