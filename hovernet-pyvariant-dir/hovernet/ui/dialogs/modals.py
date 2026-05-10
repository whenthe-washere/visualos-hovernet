import os
from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QListWidget, QListWidgetItem, QMessageBox
from PySide6.QtGui import QDesktopServices

class DeleteHistoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Delete Browsing History")
        self.setFixedWidth(350)
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select what you want to delete:"))
        
        self.chk_temp = QCheckBox("Temporary Internet files and website files")
        self.chk_temp.setChecked(True)
        self.chk_cookies = QCheckBox("Cookies and website data")
        self.chk_cookies.setChecked(True)
        self.chk_history = QCheckBox("History")
        self.chk_history.setChecked(True)
        self.chk_pass = QCheckBox("Passwords")
        
        layout.addWidget(self.chk_temp)
        layout.addWidget(self.chk_cookies)
        layout.addWidget(self.chk_history)
        layout.addWidget(self.chk_pass)
        
        btns = QHBoxLayout()
        btn_del = QPushButton("Delete")
        btn_del.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_del)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)

class ViewDownloadsDialog(QDialog):
    def __init__(self, downloads, parent=None):
        super().__init__(parent)
        self.setWindowTitle("View Downloads")
        self.resize(500, 350)
        
        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        for filename, status, path in downloads:
            item = QListWidgetItem(f"{filename} - {status}")
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)
        
        btns = QHBoxLayout()
        btn_open = QPushButton("Open File")
        btn_open.clicked.connect(self._open_file)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btns.addWidget(btn_open)
        btns.addWidget(btn_close)
        layout.addLayout(btns)

    def _open_file(self):
        item = self.list_widget.currentItem()
        if item:
            path = item.data(Qt.ItemDataRole.UserRole)
            if os.path.exists(path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            else:
                QMessageBox.warning(self, "Error", "File no longer exists.")
