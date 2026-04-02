import win32com.client
import pythoncom
from datetime import datetime
from collections import Counter

def check_outlook():
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
        tasks_folder = namespace.GetDefaultFolder(13)
        items = tasks_folder.Items
        
        print(f"Total tasks count: {items.Count}")
        
        subjects = []
        for i in range(1, items.Count + 1):
            try:
                task = items.Item(i)
                if hasattr(task, 'Subject'):
                    subjects.append(task.Subject)
            except Exception as e:
                pass
                
        c = Counter(subjects)
        duplicates = {k: v for k, v in c.items() if v > 1}
        print("Duplicates found:")
        for k, v in duplicates.items():
            print(f"  - '{k}': {v} times")
            
    except Exception as e:
        print(f"Error checking outlook: {e}")

if __name__ == '__main__':
    check_outlook()
