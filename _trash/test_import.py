
import sys
import os

# Adds the current directory to sys.path
sys.path.append(os.getcwd())

try:
    import app.ui.product_widget
    print("Import Successful")
except Exception as e:
    import traceback
    traceback.print_exc()
