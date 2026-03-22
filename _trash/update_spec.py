import os

spec_file = 'koba_ERP.spec'
try:
    with open(spec_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace empty hiddenimports with the required ones
    # Using a specific string replacement to ensure we target the right line
    old_str = "hiddenimports=[]"
    new_str = "hiddenimports=['pandas', 'openpyxl']"
    
    if old_str in content:
        new_content = content.replace(old_str, new_str)
        with open(spec_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("Successfully updated koba_ERP.spec with hiddenimports.")
    elif "hiddenimports=['pandas', 'openpyxl']" in content:
        print("koba_ERP.spec is already updated.")
    else:
        print("Could not find 'hiddenimports=[]' pattern to replace. Please check the file.")
        
except Exception as e:
    print(f"Error updating spec file: {e}")
