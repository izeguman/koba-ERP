import shutil
import win32com
import os

# win32com의 gen_py 캐시 폴더 찾기
try:
    gen_py_path = os.path.join(win32com.__gen_path__, "gen_py")
    if os.path.exists(gen_py_path):
        print(f"캐시 폴더 발견: {gen_py_path}")
        shutil.rmtree(gen_py_path)
        print("✅ 캐시 폴더를 삭제했습니다. 이제 다시 프로그램을 실행해 보세요.")
    else:
        print("캐시 폴더가 없어서 삭제할 필요가 없습니다.")
except Exception as e:
    # win32com 모듈 위치 기반으로 수동 추적
    try:
        base_path = os.path.dirname(win32com.__file__)
        gen_py_manual = os.path.join(base_path, "gen_py")
        if os.path.exists(gen_py_manual):
            shutil.rmtree(gen_py_manual)
            print("✅ (수동 경로) 캐시 폴더를 삭제했습니다.")
        else:
            print("삭제할 캐시가 없습니다.")
    except Exception as e2:
        print(f"삭제 실패: {e2}")