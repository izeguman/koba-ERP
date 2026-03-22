
import os

file_path = 'app/db.py'

try:
    # Try reading as utf-8 first
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    print("File is valid UTF-8.")
except UnicodeDecodeError:
    print("File is NOT valid UTF-8. Trying to recover...")
    try:
        with open(file_path, 'rb') as f:
            data = f.read()

        # Decode as utf-8, ignoring errors (which might be the BOM or garbage)
        # But for UTF-16 appended to UTF-8, it usually appears as chars followed by nulls.
        text = data.decode('utf-8', errors='ignore')
        
        # Remove null characters which appear when UTF-16 is interpreted as UTF-8 (ASCII chars)
        text = text.replace('\x00', '')
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(text)
            
        print("File recovered (null bytes removed).")
            
    except Exception as e:
        print(f"Recovery failed: {e}")
