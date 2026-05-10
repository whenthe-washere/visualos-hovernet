import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTabBar
from PySide6.QtGui import QIcon

class CustomTabBar(QTabBar):
    def __init__(self, main_window=None):
        super().__init__(main_window)
        self.main_window = main_window
        self.setMovable(True)
        self.setTabsClosable(True)
        self.tabCloseRequested.connect(self.close_tab)

    def new_tab_requested(self):
        if self.main_window:
            self.main_window.add_tab()

    def close_tab(self, index):
        if self.main_window:
            self.main_window.close_tab(index)
