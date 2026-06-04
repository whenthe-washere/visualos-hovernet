import sys
from PySide6.QtWidgets import QApplication
from hovernet.app import HoverNetPY

def main():
    app = QApplication(sys.argv)
    
 
    # Create a dark palette
    from PySide6.QtGui import QPalette, QColor
    from PySide6.QtCore import Qt
    # i was actually gonna change the accents a little bit but i dont feel like doing it rn GOD DAMN ITS ALMOST MIDNIGHT
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Window, QColor(20, 20, 40))
    dark_palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.WindowText, Qt.white)
    dark_palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Base, QColor(15, 15, 30))
    dark_palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.AlternateBase, QColor(20, 20, 40))
    dark_palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.ToolTipBase, Qt.white)
    dark_palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.ToolTipText, Qt.white)
    dark_palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Text, Qt.white)
    dark_palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Button, QColor(30, 30, 60))
    dark_palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.ButtonText, Qt.white)
    dark_palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.BrightText, Qt.red)
    dark_palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Link, QColor(85, 102, 255))
    dark_palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Highlight, QColor(85, 102, 255))
    dark_palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.HighlightedText, Qt.black)
    app.setPalette(dark_palette)
    
    window = HoverNetPY()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()