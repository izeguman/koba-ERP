import openpyxl
import os

path = r'app/templete/발주서.xlsx'
if not os.path.exists(path):
    print(f"File not found: {path}")
else:
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    print("--- Row Heights ---")
    for r in range(30, 46):
        h = ws.row_dimensions[r].height if r in ws.row_dimensions else 'Not in dims'
        print(f"Row {r}: {h}")
