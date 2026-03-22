
import win32com.client
import pythoncom
import logging
import sys

# Configure logging to stdout
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TestOutlook")

def connect_to_outlook():
    print("DEBUG: CoInitialize...")
    pythoncom.CoInitialize()
    
    print("DEBUG: Attempting GetActiveObject...")
    try:
        outlook = win32com.client.GetActiveObject("Outlook.Application")
        print("SUCCESS: Connected to ActiveObject")
        return outlook
    except Exception as e:
        print(f"FAILED: GetActiveObject failed: {e}")
        
    print("DEBUG: Attempting Dispatch...")
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        print("SUCCESS: Connected via Dispatch")
        return outlook
    except Exception as e:
        print(f"FAILED: Dispatch failed: {e}")
        return None

if __name__ == "__main__":
    print("Starting Outlook Connection Test...")
    app = connect_to_outlook()
    if app:
        print("Outlook Application Object obtained.")
        try:
            ns = app.GetNamespace("MAPI")
            print("Namespace MAPI obtained.")
            folder = ns.GetDefaultFolder(13)
            print(f"Tasks Folder obtained. Item count: {folder.Items.Count}")
        except Exception as e:
            print(f"Error accessing folder: {e}")
    else:
        print("Could not connect to Outlook.")
    
    print("Test Finished.")
