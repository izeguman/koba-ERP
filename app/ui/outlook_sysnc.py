# app/ui/outlook_sysnc.py
import win32com.client
import pythoncom  # ✅ 시스템 연결 초기화를 위해 필수
import os
import sqlite3
from PySide6.QtCore import QThread, Signal
from pathlib import Path
from datetime import datetime, date

# ─────────────────────────────────────────────────────────────
# 1. 설정 및 별칭 매핑
# ─────────────────────────────────────────────────────────────
ALIAS_MAP = {
    "B10000852323": "MOD-781B",
    "B10000852308": "MOD-781",
    "B10000851180": "CRPS",
    "B10000850490": "32-450",
    "B10000850460": "32-460",
    "B10000850333": "38-101A",
    "B10000805055": "MOD-29"
}


def get_dynamic_db_path(filename='production.db'):
    """OneDrive 경로를 동적으로 찾아서 DB 경로를 반환"""
    onedrive_paths = [
        os.environ.get("KOBATECH_DB_DIR"),
        os.environ.get("OneDrive"),
        os.environ.get("OneDriveConsumer"),
        os.environ.get("OneDriveCommercial"),
    ]

    base_path = None
    for path in onedrive_paths:
        if path and os.path.exists(path):
            if "KOBATECH_DB" in path:
                return str(Path(path) / filename)
            base_path = Path(path)
            break

    if base_path is None:
        user_profile = os.environ.get("USERPROFILE")
        if user_profile:
            potential_path = Path(user_profile) / "OneDrive"
            if potential_path.exists():
                base_path = potential_path

    if base_path is None:
        return str(Path.home() / "OneDrive" / "KOBATECH_DB" / filename)

    return str(base_path / "KOBATECH_DB" / filename)

def connect_outlook():
    """
    안전하게 Outlook에 연결하는 헬퍼 함수 (강화판)
    주의: 이 함수는 CoInitialize를 호출하지 않습니다. 스레드 내에서 사용 시 호출자가 CoInitialize를 보장해야 합니다.
    """
    try:
        # 2. 강제 연결 시도 (EnsureDispatch는 캐시를 생성하며 연결함)
        try:
            # 먼저 실행 중인 아웃룩 찾기
            outlook = win32com.client.GetActiveObject("Outlook.Application")
        except:
            # 없으면 강제로 새로 실행 및 연결 정보 갱신
            outlook = win32com.client.gencache.EnsureDispatch("Outlook.Application")

        return outlook

    except Exception as e:
        print(f"1차 연결 실패, 일반 Dispatch 시도: {e}")
        try:
            # 3. 최후의 수단 (일반 Dispatch)
            outlook = win32com.client.Dispatch("Outlook.Application")
            return outlook
        except Exception as e2:
            print(f"최종 연결 실패: {e2}")
            return None


def get_active_tasks_from_db(future_only=False):
    """
    DB에서 작업을 가져옵니다.
    future_only=True 이면 '오늘 이후'의 납기 건만 가져옵니다.
    """
    db_path = get_dynamic_db_path()
    if not os.path.exists(db_path):
        return []

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r[0] for r in cursor.fetchall()]
    has_shipments = 'order_shipments' in tables
    has_changes = 'shipment_date_changes' in tables

    sql_base = """
    SELECT 
        o.order_no, oi.id, o.req_due, o.final_due, 
        oi.product_name, oi.item_code, oi.qty, oi.unit_price_cents, o.status
        {company_col}
    FROM order_items oi
    JOIN orders o ON oi.order_id = o.id
    WHERE o.status NOT IN ('완료', '취소', 'Cancelled', 'Delivered', '납품완료')
      AND COALESCE(o.invoice_done, 0) = 0
    """

    try:
        cursor.execute("PRAGMA table_info(orders)")
        cols = [info[1] for info in cursor.fetchall()]
        comp_sql = ", o.company_name" if 'company_name' in cols else ", ''"
        cursor.execute(sql_base.format(company_col=comp_sql))
        items = cursor.fetchall()
    except Exception as e:
        print(f"DB Read Error: {e}")
        return []

    shipment_map = {}
    change_map = {}

    if has_shipments:
        try:
            cursor.execute("SELECT order_item_id, due_date, ship_qty FROM order_shipments")
            for row in cursor.fetchall():
                oid, ship_date, qty = row
                if oid not in shipment_map: shipment_map[oid] = []
                shipment_map[oid].append((ship_date, qty))
        except:
            pass

    if has_changes:
        try:
            cursor.execute(
                "SELECT order_item_id, new_schedule FROM shipment_date_changes ORDER BY change_request_date ASC")
            for row in cursor.fetchall():
                change_map[row[0]] = row[1]
        except:
            pass

    conn.close()

    active_tasks = []
    today_str = date.today().strftime('%Y-%m-%d')

    for row in items:
        order_no, item_id, req_due, final_due, p_name, item_code, qty, price_cents, status, comp_name = row

        effective_due = final_due if final_due else req_due
        display_name = ALIAS_MAP.get(item_code, p_name)

        if item_id in change_map and change_map[item_id]:
            effective_due = change_map[item_id]

        if item_id in shipment_map and shipment_map[item_id]:
            for s_date, s_qty in shipment_map[item_id]:
                target_date = s_date if s_date else effective_due
                if not target_date: continue

                if future_only and target_date < today_str:
                    continue

                active_tasks.append({
                    'order_no': order_no,
                    'subject': f"{display_name}/{s_qty}대/{(s_qty * price_cents / 100.0):,.0f}/{order_no}",
                    'due_date': target_date,
                    'full_body': (f"주문번호: {order_no}\n품목명: {p_name}\n수량: {s_qty}대\n"
                                  f"금액: {(s_qty * price_cents / 100.0):,.0f}\n납품일: {target_date}\n"
                                  f"거래처: {comp_name}\n상태: {status}")
                })
        else:
            if not effective_due: continue
            if future_only and effective_due < today_str:
                continue

            active_tasks.append({
                'order_no': order_no,
                'subject': f"{display_name}/{qty}대/{(qty * price_cents / 100.0):,.0f}/{order_no}",
                'due_date': effective_due,
                'full_body': (f"주문번호: {order_no}\n품목명: {p_name}\n수량: {qty}대\n"
                              f"금액: {(qty * price_cents / 100.0):,.0f}\n납품일: {effective_due}\n"
                              f"거래처: {comp_name}\n상태: {status}")
            })

    return active_tasks


def sync_outlook_tasks(future_only=False):
    """
    DB -> Outlook 동기화
    """
    outlook = connect_outlook()  # ✅ 안전한 연결 함수 사용
    if outlook is None:
        return "Outlook 연결 실패: 실행 중인지 확인하세요."

    try:
        namespace = outlook.GetNamespace("MAPI")
        tasks_folder = namespace.GetDefaultFolder(13)
    except Exception as e:
        return f"Outlook 폴더 접근 실패: {e}"

    active_data = get_active_tasks_from_db(future_only)

    active_subjects_dates = set()
    for task in active_data:
        try:
            d = datetime.strptime(task['due_date'], '%Y-%m-%d').date()
            active_subjects_dates.add((task['subject'], d))
        except:
            pass

    cnt_new = 0
    cnt_update = 0
    cnt_delete = 0

    today_date = date.today()

    # 1. 아웃룩 스캔
    outlook_items = list(tasks_folder.Items)

    for task in outlook_items:
        if not hasattr(task, 'Subject') or task.Complete: continue

        if "ORD-" in task.Subject or "주문번호:" in task.Body:
            try:
                task_date = task.DueDate.date()

                # 미래 동기화 모드면 과거 일정은 건너뜀
                if future_only and task_date < today_date:
                    continue

                if (task.Subject, task_date) not in active_subjects_dates:
                    task.Delete()
                    cnt_delete += 1
            except:
                pass

    # 2. 신규 등록 및 업데이트
    for item in active_data:
        subject = item['subject']
        body = item['full_body']
        due_str = item['due_date']

        try:
            due_date = datetime.strptime(due_str, '%Y-%m-%d')
        except:
            continue

        found = None
        for task in tasks_folder.Items:
            if not task.Complete and task.Subject == subject and task.DueDate.date() == due_date.date():
                found = task
                break

        if found:
            if found.Body.strip() != body.strip():
                found.Body = body
                found.Save()
                cnt_update += 1
        else:
            new_task = outlook.CreateItem(3)
            new_task.Subject = subject
            new_task.DueDate = due_date
            new_task.StartDate = due_date
            new_task.Body = body
            new_task.ReminderSet = True
            new_task.ReminderTime = due_date.replace(hour=9, minute=0, second=0)
            new_task.Save()
            cnt_new += 1

    mode_str = "미래 일정" if future_only else "전체 일정"
    msg = f"[{mode_str}] 동기화 완료: 신규 {cnt_new}, 수정 {cnt_update}, 삭제 {cnt_delete}"
    print(msg)
    return msg


def delete_all_completed_tasks():
    """완료된 일정만 삭제"""
    outlook = connect_outlook()
    if outlook is None: return "Outlook 연결 실패"

    try:
        namespace = outlook.GetNamespace("MAPI")
        tasks_folder = namespace.GetDefaultFolder(13)
        items = tasks_folder.Items
        deleted_count = 0
        for i in range(items.Count, 0, -1):
            try:
                task = items.Item(i)
                if task.Complete:
                    task.Delete()
                    deleted_count += 1
            except:
                continue
        return f"완료된 일정 {deleted_count}개 삭제됨."
    except Exception as e:
        return f"오류: {e}"


def delete_total_tasks():
    """모든 일정 싹 삭제"""
    outlook = connect_outlook()
    if outlook is None: return "Outlook 연결 실패"

    try:
        namespace = outlook.GetNamespace("MAPI")
        tasks_folder = namespace.GetDefaultFolder(13)
        items = tasks_folder.Items
        total_count = items.Count
        for i in range(total_count, 0, -1):
            try:
                items.Item(i).Delete()
            except:
                pass

        return f"전체 일정 {total_count}개 삭제 완료."
    except Exception as e:
        return f"오류: {e}"


class OutlookSyncWorker(QThread):
    sync_finished = Signal(str)
    _active_workers = []  # 실행 중인 워커를 유지하기 위한 클래스 변수

    def __init__(self, future_only=True, mode=None, parent=None):
        super().__init__(parent)
        self.future_only = future_only
        self.mode = mode
        # 워커가 GC되지 않도록 리스트에 추가
        OutlookSyncWorker._active_workers.append(self)
        self.finished.connect(self._cleanup)

    def _cleanup(self):
        """스레드 종료 시 리스트에서 제거"""
        if self in OutlookSyncWorker._active_workers:
            OutlookSyncWorker._active_workers.remove(self)
        self.deleteLater()

    def run(self):
        try:
            pythoncom.CoInitialize()
            if self.mode == "cleanup":
                msg = delete_all_completed_tasks()
            elif self.mode == "delete_all":
                msg = delete_total_tasks()
            elif self.mode == "all":
                 msg = sync_outlook_tasks(future_only=False)
            elif self.mode == "future":
                 msg = sync_outlook_tasks(future_only=True)
            else:
                msg = sync_outlook_tasks(future_only=self.future_only)
        except Exception as e:
            msg = f"작업 중 오류 발생: {e}"
        finally:
            pythoncom.CoUninitialize()
        
        self.sync_finished.emit(msg)