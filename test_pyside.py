import sys
from PySide6.QtWidgets import QApplication, QWidget

try:
    print("Testing PySide6 initialization...")
    app = QApplication(sys.argv)
    window = QWidget()
    window.setWindowTitle("Test")
    print("PySide6 initialized successfully.")
    # We won't call app.exec() as we are in a headless environment
except Exception as e:
    print(f"PySide6 initialization failed: {e}")
    sys.exit(1)

print("Success!")
