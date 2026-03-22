import sys
import os

# 현재 디렉토리를 sys.path에 추가하여 app 모듈을 찾을 수 있게 함
sys.path.append(os.getcwd())

from app.db import init_db

if __name__ == "__main__":
    print("Initializing DB and running migrations...")
    init_db()
    print("Done.")
