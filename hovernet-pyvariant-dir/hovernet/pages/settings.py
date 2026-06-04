import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QStackedWidget, QScrollArea, QLabel, QFrame, QLineEdit, QComboBox,
    QPushButton, QMessageBox, QFileDialog
)
from ..ui.widgets.layout import SettingsRow
from ..ui.widgets.buttons import SettingsToggle

class SettingsView(QWidget):
    """
    A modern, webpage-style settings view with side navigation and scrollable content.
    Integrated into the browser as 'hovernet://settings'.
    """
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setObjectName("settingsPage")
        
        # Main layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Sidebar
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(240)
        self.sidebar.setObjectName("settingsSidebar")
        
        sections = [
            ("Appearance", "🎨"),
            ("Startup", "🚀"),
            ("Downloads", "💾"),
            ("Account", "👤"),
            ("About", "ℹ️")
        ]
        for name, icon in sections:
            item = QListWidgetItem(f"{icon}   {name}")
            self.sidebar.addItem(item)
            
        self.sidebar.currentRowChanged.connect(self.switch_section)
        
        # Content Area (Stacked widget containing scroll areas)
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("settingsContent")
        
        self.setup_pages()
        
        layout.addWidget(self.sidebar)
        layout.addWidget(self.content_stack)
        
        self.sidebar.setCurrentRow(0)
        self.apply_styles()

    def apply_styles(self):
        self.setStyleSheet("""
            QWidget#settingsPage {
                background-color: #0a0a1a;
            }
            QListWidget#settingsSidebar {
                background-color: #0f0f23;
                border: none;
                border-right: 1px solid #1a1a3a;
                padding: 40px 15px;
                color: #8888aa;
                font-size: 14px;
                outline: none;
            }
            QListWidget#settingsSidebar::item {
                padding: 14px 18px;
                border-radius: 10px;
                margin-bottom: 6px;
            }
            QListWidget#settingsSidebar::item:selected {
                background-color: rgba(85, 102, 255, 20);
                color: #5566ff;
                font-weight: bold;
            }
            QListWidget#settingsSidebar::item:hover:!selected {
                background-color: rgba(255, 255, 255, 5);
                color: #ffffff;
            }
            
            QScrollArea {
                border: none;
                background: transparent;
            }
            QWidget#scrollContainer {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0a0a1a, stop:1 #0f0f28);
            }
            
            /* Section Card Styling */
            QFrame.settingsCard {
                background-color: rgba(25, 25, 55, 120);
                border: 1px solid rgba(85, 102, 255, 30);
                border-radius: 16px;
            }
            QLabel.cardTitle {
                color: #ffffff;
                font-size: 28px;
                font-weight: 800;
                padding-bottom: 15px;
                background: transparent;
            }
            
            QLineEdit {
                background: rgba(15, 15, 35, 200);
                border: 1px solid #333366;
                border-radius: 8px;
                padding: 10px 14px;
                color: #ffffff;
                font-size: 13px;
                min-width: 280px;
            }
            QLineEdit:focus {
                border-color: #5566ff;
                background: rgba(20, 20, 50, 255);
            }
            
            QComboBox {
                background: rgba(15, 15, 35, 200);
                border: 1px solid #333366;
                border-radius: 8px;
                padding: 8px 14px;
                color: #ffffff;
                min-width: 280px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox:on { border-color: #5566ff; }
            
            QPushButton.actionButton {
                background: #5566ff;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: 700;
                font-size: 13px;
            }
            QPushButton.actionButton:hover {
                background: #6677ff;
            }
            QPushButton.actionButton:pressed {
                background: #4455ee;
            }
            
            QLabel#relNotes {
                color: #9999bb;
                font-family: 'Consolas', monospace;
                font-size: 12px;
                background: rgba(0, 0, 0, 40);
                padding: 20px;
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 10);
            }
        """)

    def _make_page(self, title_text):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container.setObjectName("scrollContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(25)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        title = QLabel(title_text)
        title.setProperty("class", "cardTitle")
        layout.addWidget(title)
        
        scroll.setWidget(container)
        return scroll, layout

    def _make_card(self):
        card = QFrame()
        card.setProperty("class", "settingsCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        return card, layout

    def setup_pages(self):
        # 1. Appearance
        pg_app, l_app = self._make_page("Appearance")
        card, cl = self._make_card()
        
        sw_title = SettingsToggle()
        sw_title.setChecked(self.main_window.use_custom_title_bar)
        sw_title.toggled.connect(self.main_window.set_custom_title_bar_enabled)
        cl.addWidget(SettingsRow("Custom Title Bar", "Uses the custom HoverNet title bar, which is still experimental.", sw_title))
        
        sw_ws = SettingsToggle()
        sw_ws.setChecked(self.main_window.show_ws_btn)
        sw_ws.toggled.connect(self.main_window.set_ws_btn_visible)
        cl.addWidget(SettingsRow("Show WS Button", "Display the WS/whenthe's space redirect button in the navigation toolbar.", sw_ws))
        
        # Currently bugged, will fix on the next bugfix/hotfix
        # sw_expand = SettingsToggle()
        # sw_expand.setChecked(self.main_window.use_expandable_title)
        # sw_expand.toggled.connect(self.main_window.set_expandable_title_enabled)
        # cl.addWidget(SettingsRow("Expandable Title", "Show the full app name when hovering over the top-left title.", sw_expand))
        
        l_app.addWidget(card)
        self.content_stack.addWidget(pg_app)
        
        # 2. Startup
        pg_start, l_start = self._make_page("On Startup")
        card, cl = self._make_card()
        
        # Fallback if edit_newtab_url is not a widget
        curr_url = "https://www.google.com"
        if hasattr(self.main_window, 'edit_newtab_url'):
            if hasattr(self.main_window.edit_newtab_url, 'text'):
                curr_url = self.main_window.edit_newtab_url.text()
            else:
                curr_url = str(self.main_window.edit_newtab_url)
                
        nt_url = QLineEdit(curr_url)
        nt_url.textChanged.connect(self._update_newtab_url)
        cl.addWidget(SettingsRow("New Tab Page", "The address opened when creating a new tab.", nt_url))
        
        startup_cb = QComboBox()
        startup_cb.addItems(["Open a new tab", "Continue from last session", "Show a blank page"])
        cl.addWidget(SettingsRow("Startup Behavior", "Choose what happens when HoverNet launches.", startup_cb))
        
        l_start.addWidget(card)
        self.content_stack.addWidget(pg_start)
        
        # 3. Downloads
        pg_dl, l_dl = self._make_page("Downloads")
        card, cl = self._make_card()
        
        dl_path = QLineEdit(getattr(self.main_window, '_download_path', os.path.expanduser('~')))
        dl_path.textChanged.connect(self._update_download_path)
        
        btn_browse = QPushButton("Change Location")
        btn_browse.setProperty("class", "actionButton")
        btn_browse.clicked.connect(lambda: self._browse_dl_path(dl_path))
        
        cl.addWidget(SettingsRow("Download Location", "The folder where files will be saved by default.", dl_path))
        cl.addWidget(btn_browse, 0, Qt.AlignmentFlag.AlignRight)
        
        l_dl.addWidget(card)
        self.content_stack.addWidget(pg_dl)

        # 4. Account
        pg_acc, l_acc = self._make_page("Account")
        card, cl = self._make_card()
        
        btn_gmail = QPushButton("Connect G-Mail")
        btn_gmail.setProperty("class", "actionButton")
        btn_gmail.clicked.connect(lambda: QMessageBox.information(self, "Account", "Sync service is currently offline."))
        
        btn_ms = QPushButton("Connect Microsoft")
        btn_ms.setProperty("class", "actionButton")
        btn_ms.clicked.connect(lambda: QMessageBox.information(self, "Account", "Microsoft sync is not implemented yet."))
        
        cl.addWidget(SettingsRow("Google Account", "Sync your history and bookmarks with Google.", btn_gmail))
        cl.addWidget(SettingsRow("Microsoft Account", "Sync with your Microsoft profile.", btn_ms))
        
        l_acc.addWidget(card)
        self.content_stack.addWidget(pg_acc)

        # 5. About
        pg_about, l_about = self._make_page("About HoverNet")
        card, cl = self._make_card()
        
        logo = QLabel("visualOS HoverNet")
        logo.setStyleSheet("font-size: 32px; font-weight: 700; color: #5566ff; background: transparent;")
        cl.addWidget(logo)
        
        cl.addWidget(QLabel(f"App Version: {getattr(self.main_window, 'HOVERNET_VERSION', '2.2')}-py"))
        cl.addWidget(QLabel("visualOS HoverNet by whenthe's space."))
        
        notes = QLabel("What changed (compared to v2.2):\n\n"
                      "• Improved the overall design to match the minimal standards for the visualOS 30O1 design language, these include changes such as:\n"
                      "• • Changed title buttons to use visualOS 30O1's Linear style\n"
                      "• • Moved the toolbar to the bottom\n"
                      "• • Made the toolbar an island\n"
                      "• Added icons for Home, WS, Printy and Tools\n"
                      "• Added Windows-native dragging and Aero snapping using ctypes\n"
                      "• Made the toolbar semi-transparent\n"
                      "• Tweaked backgrounds for tabs(Inactive, Active, Hover)\n"
                      "• Added animations for some toolbar icons and toolbar fade in + out\n"
                      "• Updated the app's icon\n"
                      "N The custom title bar is now considered finished, and is likely to recieve any revamps.\nThis means that in the next few versions, the option to opt out from the custom title bar is likely to be removed")
        notes.setObjectName("relNotes")
        notes.setWordWrap(True)
        cl.addWidget(notes)
        
        l_about.addWidget(card)
        self.content_stack.addWidget(pg_about)

    def switch_section(self, index):
        self.content_stack.setCurrentIndex(index)

    def _update_newtab_url(self, text):
        if hasattr(self.main_window, 'edit_newtab_url'):
            if hasattr(self.main_window.edit_newtab_url, 'setText'):
                self.main_window.edit_newtab_url.setText(text)
            else:
                self.main_window.edit_newtab_url = text

    def _update_download_path(self, text):
        self.main_window._download_path = text

    def _browse_dl_path(self, line_edit):
        path = QFileDialog.getExistingDirectory(self, "Select Download Folder", line_edit.text())
        if path:
            line_edit.setText(path)
            self.main_window._download_path = path
