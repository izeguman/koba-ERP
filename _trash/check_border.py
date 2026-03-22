import openpyxl
from openpyxl.styles.borders import Border, Side

path = r'app/templete/발주서.xlsx'
wb = openpyxl.load_workbook(path)
ws = wb.active

print(f"Checking borders for {path}")
# Check rows 5-11, Cols F(6) to N(14)
for r in range(5, 12):
    row_info = []
    for c in range(6, 15): # F to N
        cell = ws.cell(row=r, column=c)
        b = cell.border
        # Check Right border
        if b.right and b.right.style:
            row_info.append(f"R{r}C{c}-Right:{b.right.style}")
        # Check Left border
        if b.left and b.left.style:
            row_info.append(f"R{r}C{c}-Left:{b.left.style}")
    if row_info:
        print(f"Row {r}: {', '.join(row_info)}")
