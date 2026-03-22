import sys
import os
from datetime import datetime
from app.db import get_next_delivery_number, get_conn

# Encoding fix
sys.stdout.reconfigure(encoding='utf-8')

def test_gen():
    try:
        today = datetime.now()
        print(f"Testing for date: {today}")
        next_no = get_next_delivery_number(today.year, today.month, today.day)
        print(f"Generated Number: {next_no}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_gen()
