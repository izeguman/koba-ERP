import win32com.client
import sys

def list_outlook_folders():
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
        
        # 1. 현재 Default Store 확인
        default_folder = namespace.GetDefaultFolder(13) # Tasks
        print(f"--- [Default Task Folder Info] ---")
        print(f"Store: {default_folder.Parent.Name}")
        print(f"Folder: {default_folder.Name}")
        print(f"Item Count: {default_folder.Items.Count}")
        print("----------------------------------\n")
        
        # 2. 모든 Store(계정) 순회하며 Tasks 폴더 찾기
        print(f"--- [Scanning All Stores & Folders] ---")
        for store in namespace.Stores:
            print(f"\n[Store]: {store.DisplayName}")
            try:
                root = store.GetRootFolder()
                for folder in root.Folders:
                    try:
                        # 폴더 이름, 타입, 아이템 개수 출력
                        # Folder Type 13 = Tasks
                        count = folder.Items.Count
                        print(f"  - {folder.Name} (Count: {count})")
                        
                        # 만약 0개가 아니라면, 샘플 아이템 제목 출력
                        if count > 0 and (folder.Name == "Tasks" or folder.Name == "작업" or "Task" in folder.Name):
                            first_item = folder.Items.Item(1)
                            print(f"    Sample: {getattr(first_item, 'Subject', 'No Subject')}")
                            
                    except Exception as f_err:
                        print(f"  - {folder.Name} (Error reading: {f_err})")
            except Exception as e:
                print(f"  Error accessing store: {e}")

    except Exception as e:
        print(f"Critical Error: {e}")

if __name__ == "__main__":
    list_outlook_folders()
