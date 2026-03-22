# app/ui/outlook_sync.py
import win32com.client
import win32timezone  # ✅ PyInstaller 패키징 강제 포함을 위해 명시적 import 추가
import pythoncom  # ✅ 시스템 연결 초기화를 위해 필수
import os
import sqlite3
import logging
import logging.handlers
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import QProgressDialog, QApplication
from pathlib import Path
from datetime import datetime, date
import time  # ✅ 안정화를 위한 time 모듈 import

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


def setup_sync_logger():
    """Outlook 동기화 전용 로거 설정"""
    log_dir = os.path.join(os.getcwd(), "log")
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir)
        except:
            pass
    
    logger = logging.getLogger("OutlookSync")
    logger.setLevel(logging.DEBUG)
    
    # 중복 핸들러 방지
    if not logger.handlers:
        log_file = os.path.join(log_dir, "outlook_sync.log")
        try:
            # 1MB 단위로 5개까지 보관
            handler = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=1*1024*1024, backupCount=5, encoding='utf-8'
            )
            formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        except Exception as e:
            print(f"로거 설정 실패: {e}")
            
    return logger

def _to_local_date(pywintypes_dt):
    """Outlook COM이 반환하는 pywintypes.datetime(UTC)을 로컬 날짜로 변환"""
    if hasattr(pywintypes_dt, 'tzinfo') and pywintypes_dt.tzinfo is not None:
        local_dt = pywintypes_dt.astimezone(tz=None)  # 시스템 로컬 시간대(KST)로 변환
        return local_dt.date()
    return pywintypes_dt.date()


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
    WHERE {conditions}
    """

    # ✅ 동적 조건 생성 (한글 깨짐 방지 위해 유니코드 이스케이프 사용)
    # '취소': \ucde8\uc18c, '완료': \uc644\ub8cc
    base_conditions = "o.status NOT IN ('\ucde8\uc18c', 'Cancelled')"
    
    if future_only:
        # 미래 일정: 완료된 것도 제외 + 청구 완료된 것도 제외
        conditions = f"{base_conditions} AND o.status NOT IN ('\uc644\ub8cc', 'Delivered') AND (o.invoice_done IS NULL OR o.invoice_done = 0)"
    else:
        # 전체 일정: 완료된 것도 포함 (취소만 제외)
        conditions = base_conditions

    try:
        cursor.execute("PRAGMA table_info(orders)")
        cols = [info[1] for info in cursor.fetchall()]
        comp_sql = ", o.company_name" if 'company_name' in cols else ", ''"
        final_sql = sql_base.format(company_col=comp_sql, conditions=conditions)
        # print(f"DEBUG: Executing SQL with future_only={future_only}")
        # print(f"DEBUG SQL: {final_sql}")
        cursor.execute(final_sql)
        items = cursor.fetchall()
        # print(f"DEBUG: Fetched {len(items)} items from DB")
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
    # print(f"DEBUG: Today is {today_str}") # ✅ 오늘 날짜 출력 (디버깅)

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
                    # print(f"DEBUG: Skip past shipment {order_no} ({target_date} < {today_str})")
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
                # print(f"DEBUG: Skip past task {order_no} ({effective_due} < {today_str}), Status={status}")
                continue
            
            # Status Hex 값 출력
            # status_hex = ' '.join(f"{ord(c):04X}" for c in status) if status else "None"
            # print(f"DEBUG: Checking Item {order_no}, Status='{status}', Hex=[{status_hex}]")

            active_tasks.append({
                'order_no': order_no,
                'subject': f"{display_name}/{qty}대/{(qty * price_cents / 100.0):,.0f}/{order_no}",
                'due_date': effective_due,
                'full_body': (f"주문번호: {order_no}\n품목명: {p_name}\n수량: {qty}대\n"
                              f"금액: {(qty * price_cents / 100.0):,.0f}\n납품일: {effective_due}\n"
                              f"거래처: {comp_name}\n상태: {status}")
            })
            
    # ✅ 최종 결과 요약 출력 (디버깅 완료 후 주석 처리)
    # if future_only:
    #     print("--- Active Tasks (Future Only) ---")
    #     for t in active_tasks:
    #         # Body에서 Status 라인 추출 및 Hex 출력
    #         status_line = t['full_body'].splitlines()[-1]
    #         status_val = status_line.replace("상태: ", "").strip()
    #         if ":" in status_line:
    #             status_val = status_line.split(":")[-1].strip()
    #         status_hex = ' '.join(f"{ord(c):04X}" for c in status_val)
    #         print(f"Task: {t['order_no']} / Due: {t['due_date']} / Status Hex: [{status_hex}]")
    #     print("----------------------------------")

    return active_tasks


def sync_outlook_tasks(future_only=False, progress_callback=None):
    """
    DB -> Outlook 동기화
    """
    logger = setup_sync_logger()
    logger.info("=== Outlook 동기화 시작 ===")
    
    if progress_callback:
        progress_callback(0, "Outlook 연결 중...")

    outlook = connect_outlook()  # ✅ 안전한 연결 함수 사용
    if outlook is None:
        logger.error("Outlook 연결 실패")
        return "Outlook 연결 실패: 실행 중인지 확인하세요."

    try:
        namespace = outlook.GetNamespace("MAPI")
        tasks_folder = namespace.GetDefaultFolder(13)
    except Exception as e:
        logger.error(f"Outlook 폴더 접근 실패: {e}")
        return f"Outlook 폴더 접근 실패: {e}"

    if progress_callback:
        progress_callback(10, "DB 데이터 가져오는 중...")

    active_data = get_active_tasks_from_db(future_only)
    logger.info(f"DB에서 가져온 활성 작업 수: {len(active_data)}")
    
    # 작업 수 계산 (스캔 + 업데이트)
    # 대략적으로 스캔은 전체 아이템 수, 업데이트는 DB 아이템 수만큼 반복
    outlook_items = list(tasks_folder.Items)
    logger.info(f"현재 Outlook 작업 항목 수: {len(outlook_items)}")
    
    total_steps = len(outlook_items) + len(active_data)
    current_step = 0
    
    # 진행률 계산 헬퍼
    def update_progress(step, msg):
        if progress_callback and total_steps > 0:
            pct = 10 + int((step / total_steps) * 85) # 10% ~ 95% 구간 사용
            progress_callback(pct, msg)
        QApplication.processEvents()

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
    deleted_items_log = [] # 디버깅용 로그

    # 1. 아웃룩 스캔 및 불필요 항목 삭제
    update_progress(current_step, "기존 항목 스캔 및 정리 중...")
    
    items_count = tasks_folder.Items.Count
    for i in range(items_count, 0, -1):
        try:
            task = tasks_folder.Items.Item(i)
            current_step += 1
            if current_step % 5 == 0: # 너무 빈번한 업데이트 방지
                update_progress(current_step, f"항목 스캔 중... ({current_step}/{total_steps})")

            if not hasattr(task, 'Subject') or task.Complete: continue

            if "ORD-" in task.Subject or "주문번호:" in task.Body:
                task_date = _to_local_date(task.DueDate)

                # 미래 동기화 모드면 과거 일정은 건너뜀
                if future_only and task_date < today_date:
                    continue

                if (task.Subject, task_date) not in active_subjects_dates:
                    subject = task.Subject
                    task.Delete()
                    cnt_delete += 1
                    deleted_items_log.append(f"{subject} ({task_date})")
                    logger.info(f"[DELETE] 항목 삭제됨: {subject} (Due: {task_date})")
                    time.sleep(0.1) # ✅ 삭제 안정화 대기 (0.02 -> 0.1로 증가)
        except Exception as e:
            logger.warning(f"항목 스캔/삭제 중 오류: {e}")
            pass
            
    # 스캔 단계 완료 후 step 보정
    current_step = len(outlook_items)

    # 2. 신규 등록 및 업데이트
    new_items_log = [] # 디버깅용: 새로 추가된 항목들
    
    for idx, item in enumerate(active_data):
        current_step += 1
        # ✅ 매 항목마다 프로그래스 업데이트 (부드러운 진행)
        if idx % 1 == 0: 
             update_progress(current_step, f"데이터 동기화 중 ({idx+1}/{len(active_data)})...")
             
        subject = item['subject']
        body = item['full_body']
        due_str = item['due_date']

        try:
            due_date = datetime.strptime(due_str, '%Y-%m-%d')
        except:
            logger.warning(f"날짜 변환 실패: {due_str} for {subject}")
            continue

        found = None
        # 효율성을 위해 필터링 사용 권장하지만, 현재 구조 유지 시 루프
        for task in tasks_folder.Items:
            if not task.Complete and task.Subject == subject and _to_local_date(task.DueDate) == due_date.date():
                found = task
                break

        if found:
            if found.Body.strip() != body.strip():
                try:
                    found.Body = body
                    found.Save()
                    cnt_update += 1
                    logger.info(f"[UPDATE] 항목 업데이트: {subject}")
                    time.sleep(0.1)
                except Exception as e:
                    logger.error(f"항목 업데이트 실패 ({subject}): {e}")
            else:
                # logger.debug(f"[SKIP] 변경 없음: {subject}")
                pass
        else:
            try:
                new_task = outlook.CreateItem(3)
                new_task.Subject = subject
                new_task.DueDate = due_date
                new_task.StartDate = due_date
                new_task.Body = body
                new_task.ReminderSet = True
                new_task.ReminderTime = due_date.replace(hour=9, minute=0, second=0)
                new_task.Save()
                cnt_new += 1
                new_items_log.append(f"{subject} [DueDate: {due_date.date()}]")
                logger.info(f"[NEW] 신규 항목 생성: {subject} (Due: {due_date.date()})")
                time.sleep(0.2)  # ✅ 생성 안정화 대기 (0.05 -> 0.2로 대폭 증가)
            except Exception as e:
                logger.error(f"[ERROR] 항목 생성 실패 ({subject}): {e}")
                print(f"항목 생성 실패 ({subject}): {e}")

    if progress_callback:
        progress_callback(100, "동기화 완료!")

    mode_str = "미래 일정" if future_only else "전체 일정"
    msg = f"[{mode_str}] 동기화 완료: 신규 {cnt_new}, 수정 {cnt_update}, 삭제 {cnt_delete}"
    logger.info(msg)
    
    # 상세 로그는 이제 파일로 기록되므로 콘솔 출력은 줄임
    print(msg)
    
    return msg


def delete_all_completed_tasks(progress_callback=None):
    """완료된 일정만 삭제"""
    if progress_callback: progress_callback(0, "Outlook 연결 중...")
    outlook = connect_outlook()
    if outlook is None: return "Outlook 연결 실패"

    try:
        namespace = outlook.GetNamespace("MAPI")
        tasks_folder = namespace.GetDefaultFolder(13)
        items = tasks_folder.Items
        total = items.Count
        deleted_count = 0
        
        for i in range(total, 0, -1):
            if progress_callback and i % 5 == 0:
                pct = int((total - i) / total * 100)
                progress_callback(pct, f"삭제 중... ({deleted_count}개 삭제)")
                QApplication.processEvents()
                
            try:
                task = items.Item(i)
                if task.Complete:
                    task.Delete()
                    deleted_count += 1
            except:
                continue
                
        if progress_callback: progress_callback(100, "삭제 완료")
        return f"완료된 일정 {deleted_count}개 삭제됨."
    except Exception as e:
        return f"오류: {e}"


def delete_total_tasks(progress_callback=None):
    """모든 일정 싹 삭제"""
    if progress_callback: progress_callback(0, "Outlook 연결 중...")
    outlook = connect_outlook()
    if outlook is None: return "Outlook 연결 실패"

    try:
        namespace = outlook.GetNamespace("MAPI")
        tasks_folder = namespace.GetDefaultFolder(13)
        items = tasks_folder.Items
        total_count = items.Count
        
        for i in range(total_count, 0, -1):
            if progress_callback and i % 10 == 0:
                pct = int( (total_count - i) / total_count * 100 )
                progress_callback(pct, f"전체 삭제 중... ({total_count - i}/{total_count})")
                QApplication.processEvents()

            try:
                items.Item(i).Delete()
            except:
                pass

        if progress_callback: progress_callback(100, "삭제 완료")
        return f"전체 일정 {total_count}개 삭제 완료."
    except Exception as e:
        return f"오류: {e}"


class OutlookSyncWorker(QThread):
    sync_finished = Signal(str)
    progress_updated = Signal(int, str) # 진행률 시그널 추가
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
        
    def report_progress(self, pct, msg):
        self.progress_updated.emit(pct, msg)

    def run(self):
        try:
            pythoncom.CoInitialize()
            
            # 콜백 함수 전달
            cb = self.report_progress
            
            if self.mode == "cleanup":
                msg = delete_all_completed_tasks(progress_callback=cb)
            elif self.mode == "delete_all":
                msg = delete_total_tasks(progress_callback=cb)
            elif self.mode == "all":
                 msg = sync_outlook_tasks(future_only=False, progress_callback=cb)
            elif self.mode == "future":
                 msg = sync_outlook_tasks(future_only=True, progress_callback=cb)
            else:
                msg = sync_outlook_tasks(future_only=self.future_only, progress_callback=cb)
        except Exception as e:
            msg = f"작업 중 오류 발생: {e}"
        finally:
            pythoncom.CoUninitialize()
        
        self.sync_finished.emit(msg)


def execute_outlook_operation_sync(parent, mode):
    """
    Outlook 작업을 동기적으로 수행하며 진행 대화상자를 표시합니다.
    """
    # 1. 진행 대화상자 표시
    progress = QProgressDialog("Outlook 작업 준비 중...", "취소", 0, 100, parent)
    progress.setWindowTitle("Outlook 동기화")
    progress.setWindowModality(Qt.WindowModal)
    progress.setMinimumDuration(0) # 즉시 표시
    progress.setCancelButton(None) # 취소 불가 (동기 작업이므로)
    # 스타일링
    progress.setMinimumWidth(400)
    progress.show()
    
    QApplication.processEvents()

    # 콜백 함수 정의
    def update_ui(pct, text):
        progress.setValue(pct)
        progress.setLabelText(text)
        QApplication.processEvents()

    msg = ""
    try:
        if mode == "cleanup":
            msg = delete_all_completed_tasks(progress_callback=update_ui)
        elif mode == "delete_all":
            msg = delete_total_tasks(progress_callback=update_ui)
        elif mode == "all":
            msg = sync_outlook_tasks(future_only=False, progress_callback=update_ui)
        elif mode == "future":
            msg = sync_outlook_tasks(future_only=True, progress_callback=update_ui)
        else:
            msg = f"알 수 없는 모드입니다: {mode}"
            
    except Exception as e:
        msg = f"작업 중 심각한 오류 발생: {e}"
        import traceback
        traceback.print_exc()

    finally:
        progress.close()
    
    return msg