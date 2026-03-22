"""CSV Export Utility for Table Widgets"""
import csv
from datetime import datetime
from PySide6.QtWidgets import QFileDialog, QMessageBox, QTableWidget
import os


def export_table_to_csv(parent_widget, table_widget: QTableWidget, default_filename: str = "export.csv"):
    """
    테이블 위젯의 데이터를 CSV 파일로 내보냅니다.
    
    Args:
        parent_widget: 부모 위젯 (파일 다이얼로그 표시용)
        table_widget: 내보낼 QTableWidget
        default_filename: 기본 파일명
    
    Returns:
        bool: 성공 여부
    """
    try:
        # 파일 저장 경로 선택
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suggested_name = f"{default_filename.replace('.csv', '')}_{timestamp}.csv"
        
        file_path, _ = QFileDialog.getSaveFileName(
            parent_widget,
            "CSV 파일 저장",
            suggested_name,
            "CSV Files (*.csv);;All Files (*)"
        )
        
        if not file_path:
            return False
        
        # 헤더 추출
        headers = []
        for col in range(table_widget.columnCount()):
            header_item = table_widget.horizontalHeaderItem(col)
            if header_item:
                headers.append(header_item.text())
            else:
                headers.append(f"Column {col + 1}")
        
        # 데이터 추출
        rows_data = []
        for row in range(table_widget.rowCount()):
            row_data = []
            for col in range(table_widget.columnCount()):
                # 셀 위젯이 있는지 확인 (체크박스 등)
                cell_widget = table_widget.cellWidget(row, col)
                if cell_widget:
                    # 체크박스인 경우
                    from PySide6.QtWidgets import QCheckBox
                    checkbox = cell_widget.findChild(QCheckBox)
                    if checkbox:
                        row_data.append("O" if checkbox.isChecked() else "X")
                    else:
                        row_data.append("")
                else:
                    # 일반 아이템
                    item = table_widget.item(row, col)
                    if item:
                        row_data.append(item.text())
                    else:
                        row_data.append("")
            rows_data.append(row_data)
        
        # CSV 파일 작성 (UTF-8 BOM - Excel 호환)
        with open(file_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(headers)
            writer.writerows(rows_data)
        
        # 성공 메시지
        msg_box = QMessageBox(parent_widget)
        msg_box.setWindowTitle("완료")
        msg_box.setText(f"CSV 파일이 저장되었습니다.\n\n{os.path.basename(file_path)}")
        
        open_folder_btn = msg_box.addButton("폴더 열기", QMessageBox.ActionRole)
        ok_btn = msg_box.addButton("확인", QMessageBox.AcceptRole)
        msg_box.setDefaultButton(ok_btn)
        
        msg_box.exec()
        
        if msg_box.clickedButton() == open_folder_btn:
            folder = os.path.dirname(file_path)
            os.startfile(folder)
        
        return True
        
    except Exception as e:
        QMessageBox.critical(
            parent_widget,
            "오류",
            f"CSV 파일 저장 중 오류가 발생했습니다:\n{str(e)}"
        )
        return False
