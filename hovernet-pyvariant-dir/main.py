import sys
from PySide6.QtWidgets import QApplication
from hovernet.app import HoverNetPY

def main():
    app = QApplication(sys.argv)
    
    window = HoverNetPY()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()