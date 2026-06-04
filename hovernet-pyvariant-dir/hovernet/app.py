import os
import sys
import json
import subprocess
from urllib.parse import quote_plus
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtCore import Qt, QUrl, QTimer, QSize, QPoint, QStringListModel, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QToolButton, QHBoxLayout, QWidget, QVBoxLayout,
    QMenu, QStackedWidget, QMessageBox, QFileDialog, QDialog, QLabel, QTextEdit,
    QPushButton, QCheckBox, QFrame, QListView, QLineEdit
)
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineDownloadRequest, QWebEngineScript
from PySide6.QtWebEngineWidgets import QWebEngineView

from .ui.widgets.title_bar import ExpandableAppTitle, DragHandleLine
from .ui.widgets.buttons import NewTabButton, TitleBarButton
from .ui.widgets.nav_icons import AnimatedIconButton
from .ui.widgets.entries import UrlLineEdit
from .core.tabs import CustomTabBar
from .core.browser import BrowserView
from .ui.components.bubbles import DownloadBubble, UpdateBubble, PrintyBubble
from .ui.dialogs.autocomplete import AutocompleteDropdown
from .ui.dialogs.modals import DeleteHistoryDialog, ViewDownloadsDialog
from .pages.settings import SettingsView
from .utils.helpers import normalize_input

class HoverNetPY(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("visualOS HoverNet - PY Variant")
        self.resize(1200, 800)
        
        self.use_custom_title_bar = True
        self._dragPos = QPoint(0, 0)
        self.use_expandable_title = False
        app_font = QFont("Segoe UI Variable Text", 10)
        if not app_font.exactMatch(): app_font = QFont("Segoe UI", 10)
        self.setFont(app_font)

        try:
            prof = QWebEngineProfile.defaultProfile()
            prof.setHttpUserAgent(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36"
            )
            prof.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
            base_path = os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), "IE12Profile")
            os.makedirs(base_path, exist_ok=True)
            try: prof.setPersistentStoragePath(base_path)
            except: pass
            try:
                prof.setCachePath(os.path.join(base_path, "Cache"))
                prof.setHttpCacheType(QWebEngineProfile.DiskHttpCache)
            except: pass
        except: pass

        central = QWidget()
        central.setMouseTracking(True)
        central.setStyleSheet("QWidget { background-color: rgba(20, 20, 40, 160); border-radius: 10px; }")
        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.setCentralWidget(central)

        self.app_title_text = ExpandableAppTitle(self)
        self.app_title_text.installEventFilter(self)
        
        self.minimize_btn = TitleBarButton('min', self)
        self.minimize_btn.clicked.connect(self.minimize_window)
        
        self.maximize_btn = TitleBarButton('max', self)
        self.maximize_btn.clicked.connect(self.maximize_window)
        
        self.close_btn = TitleBarButton('close', self)
        self.close_btn.clicked.connect(self.close_window)

        self.tab_bar = CustomTabBar(self)
        self.tab_bar.setFont(app_font)
        self.tab_bar.currentChanged.connect(self.switch_tab)
        self.tab_bar.tabMoved.connect(self.on_tab_moved)
        self.tab_bar.setExpanding(True)
        self.tab_bar.setUsesScrollButtons(False)
        self.tab_bar.setElideMode(Qt.TextElideMode.ElideRight)
        self.tab_bar.setIconSize(QSize(16, 16))
        self.tab_bar.setStyleSheet("""
            QTabBar {
                qproperty-drawBase: 0;
            }
            QTabBar::tab {
                min-width: 60px; max-width: 9999px; min-height: 30px;
                padding: 0 12px 0 8px; background: transparent; color: #aaaacc;
                border: none; border-right: 1px solid #1a1a38; border-bottom: 2px solid transparent; font-size: 11px;
            }
            QTabBar::tab:selected { background: transparent; color: #ffffff; font-weight: bold; border-bottom: 2px solid #5566ff; }
            QTabBar::tab:hover:!selected { background: rgba(51, 51, 90, 122); color: #ddddff; }
        """)

        self.url_bar = UrlLineEdit()
        self.url_bar.setPlaceholderText("Search or enter web address")
        self.url_bar.returnPressed.connect(self.load_url)
        self.url_bar.setFont(app_font)

        BTN_H = 30
        nav_pill = QWidget()
        nav_pill.setFixedHeight(BTN_H)
        nav_pill.setObjectName("navPill")
        nav_pill.setStyleSheet("QWidget#navPill { background: transparent; border: 2px solid #0050FF; border-radius: 15px; }")
        _pill_layout = QHBoxLayout(nav_pill)
        _pill_layout.setContentsMargins(2, 0, 2, 0)
        _pill_layout.setSpacing(0)

        _btn_style = "QToolButton {{ background: transparent; border: none; font-size: {fs}px; font-weight: bold; color: {col}; padding: 0 6px; min-width: {mw}px; }} QToolButton:pressed {{ color: #ffffff; }} QToolButton:disabled {{ color: #444466; }}"
        self.back_btn = QToolButton()
        self.back_btn.setText("↩")
        self.back_btn.setEnabled(False)
        self.back_btn.setStyleSheet(_btn_style.format(fs=18, col="#0050FF", mw=28))
        self.back_btn.clicked.connect(self.go_back)

        _sep = QFrame()
        _sep.setFrameShape(QFrame.Shape.VLine)
        _sep.setFixedWidth(1)
        _sep.setFixedHeight(BTN_H - 10)
        _sep.setStyleSheet("QFrame { background: rgba(100,120,255,120); border: none; }")

        self.forward_btn = QToolButton()
        self.forward_btn.setText("↪")
        self.forward_btn.setEnabled(False)
        self.forward_btn.setStyleSheet(_btn_style.format(fs=16, col="#0050FF", mw=24))
        self.forward_btn.clicked.connect(self.go_forward)

        _pill_layout.addWidget(self.back_btn)
        _pill_layout.addWidget(_sep, 0, Qt.AlignmentFlag.AlignVCenter)
        _pill_layout.addWidget(self.forward_btn)

        self.site_info_btn = QToolButton()
        self.site_info_btn.setText("⇌")
        self.site_info_btn.setFixedSize(24, 24)
        self.site_info_btn.setStyleSheet("QToolButton { border: 2px solid #3C993C; border-radius: 12px; color: #3C993C; }")
        self.site_info_btn.clicked.connect(self._show_site_info)

        self.refresh_btn = QToolButton()
        self.refresh_btn.setText("⟳")
        self.refresh_btn.setFixedSize(26, 26)
        self.refresh_btn.setStyleSheet("QToolButton { color: #0050FF; border: 2px solid #0050FF; border-radius: 13px; }")
        self.refresh_btn.clicked.connect(self.go_refresh)

        nav_container = QWidget()
        nav_layout = QHBoxLayout(nav_container)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(6)
        nav_layout.addWidget(nav_pill)
        nav_layout.addWidget(self.url_bar)
        nav_layout.addWidget(self.site_info_btn)
        nav_layout.addWidget(self.refresh_btn)

        self.show_ws_btn = False
        tools_pill = QWidget()
        tools_pill.setObjectName("toolsPill")
        tools_pill.setFixedHeight(28)
        tools_pill.setStyleSheet("QWidget#toolsPill { border: 2px solid #333366; border-radius: 14px; background: transparent; }")
        _tpill_layout = QHBoxLayout(tools_pill)
        _tpill_layout.setContentsMargins(4, 0, 4, 0)
        _tpill_layout.setSpacing(0)

        _tp_btn_style = "QToolButton { background: transparent; border: none; } QToolButton::menu-indicator { width: 0; height: 0; image: none; }"
        self.home_btn = AnimatedIconButton('home')
        self.home_btn.setToolTip("Home")
        self.home_btn.clicked.connect(self.go_home)
        self.home_btn.setStyleSheet(_tp_btn_style)

        self.ws_btn = AnimatedIconButton('ws')
        self.ws_btn.setToolTip("WS")
        self.ws_btn.clicked.connect(self.whenthes_space)
        self.ws_btn.setStyleSheet(_tp_btn_style)

        self.tools_btn = AnimatedIconButton('tools')
        self.tools_btn.setToolTip("Tools")
        self.tools_btn.setStyleSheet(_tp_btn_style)
        
        self._sep_before_ws = self._make_pill_sep()
        self._sep_after_ws = self._make_pill_sep()
        self._sep_before_tools = self._make_pill_sep()

        self.printy_btn = AnimatedIconButton('python')
        self.printy_btn.setToolTip("P")
        self.printy_btn.setStyleSheet(_tp_btn_style)
        self.printy_btn.clicked.connect(self._toggle_printy_bubble)

        _tpill_layout.addWidget(self.home_btn)
        _tpill_layout.addWidget(self._sep_before_ws, 0, Qt.AlignmentFlag.AlignVCenter)
        _tpill_layout.addWidget(self.ws_btn)
        _tpill_layout.addWidget(self._sep_after_ws, 0, Qt.AlignmentFlag.AlignVCenter)
        _tpill_layout.addWidget(self.printy_btn)
        _tpill_layout.addWidget(self._sep_before_tools, 0, Qt.AlignmentFlag.AlignVCenter)
        _tpill_layout.addWidget(self.tools_btn)
        self.set_ws_btn_visible(self.show_ws_btn)

        self.tools_menu = QMenu()
        self.tools_menu.addAction("File", self._act_file)
        zoom_menu = self.tools_menu.addMenu("Zoom")
        zoom_menu.addAction("Zoom In", lambda: self._zoom(1.1))
        zoom_menu.addAction("Zoom Out", lambda: self._zoom(1/1.1))
        zoom_menu.addAction("Reset Zoom", self._zoom_reset)
        safety_menu = self.tools_menu.addMenu("Safety")
        safety_menu.addAction("Delete browsing history", self._show_delete_history_dialog)
        self.tools_menu.addAction("Download History", self._show_downloads_dialog)
        self.tools_menu.addSeparator()
        self.tools_menu.addAction("HoverNet Settings", self._show_hovernet_settings)
        self.tools_menu.addAction("About HoverNet", self._show_about_page)
        self.tools_btn.setMenu(self.tools_menu)
        self.tools_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        bottom_bar = QWidget()
        bottom_bar.setStyleSheet("QWidget { background-color: transparent; }")
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(8, 4, 8, 4)
        bottom_layout.setSpacing(8)
        self.bottom_bar = bottom_bar

        bottom_layout.addWidget(self.app_title_text)
        bottom_layout.addWidget(nav_container, stretch=1)
        bottom_layout.addWidget(tools_pill)
        bottom_layout.addWidget(self.minimize_btn)
        bottom_layout.addWidget(self.maximize_btn)
        bottom_layout.addWidget(self.close_btn)

        self.drag_handle = DragHandleLine(self)
        self.main_layout.addWidget(self.drag_handle)
        
        self.browser_area = QStackedWidget()
        self.main_layout.addWidget(self.browser_area)

        tab_row = QWidget()
        tab_row.setStyleSheet("QWidget { background-color: transparent; }")
        tab_row_layout = QHBoxLayout(tab_row)
        tab_row_layout.setContentsMargins(4, 2, 8, 2)
        tab_row_layout.setSpacing(6)
        tab_row_layout.addWidget(self.tab_bar, stretch=1)
        self.new_tab_btn = NewTabButton()
        self.new_tab_btn.clicked.connect(self.add_tab)
        tab_row_layout.addWidget(self.new_tab_btn, stretch=0)
        
        self.island_widget = QWidget(central)
        self.island_widget.setObjectName("islandWidget")
        self.island_widget.setStyleSheet("""
            QWidget#islandWidget {
                background-color: rgba(30, 30, 60, 215);
                border-radius: 14px;
                border: none;
            }
        """)
        island_layout = QVBoxLayout(self.island_widget)
        island_layout.setContentsMargins(4, 4, 4, 4)
        island_layout.setSpacing(0)
        island_layout.addWidget(tab_row)
        island_layout.addWidget(bottom_bar)

        self._island_visible = False
        self._island_anim = QPropertyAnimation(self.island_widget, b"pos")
        self._island_anim.setDuration(250)
        self._island_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.hover_trigger = QWidget(central)
        self.hover_trigger.setStyleSheet("background: transparent;")
        self.hover_trigger.installEventFilter(self)
        self.island_widget.installEventFilter(self)
        self.add_tab("https://www.google.com")
        self._autocomplete = AutocompleteDropdown(self.url_bar, self)
        
        self._downloads = []
        QWebEngineProfile.defaultProfile().downloadRequested.connect(self._on_download_requested)
        self._download_path = os.path.expanduser('~')
        
        self.apply_custom_title_bar_setting()
        self._install_topbar_drag_filters()
        
        self.HOVERNET_VERSION = "2.30.00"
        self.HOVERNET_VARIANT = "py"
        self._update_bubble = UpdateBubble(self)
        self._update_nam = QNetworkAccessManager(self)
        QTimer.singleShot(3000, self._check_for_updates)
        self._download_bubble = DownloadBubble(self)
        self._download_bubble.set_anchor(self.tools_btn)
        self._printy_bubble = PrintyBubble(self)
        QApplication.instance().installEventFilter(self)

    def _make_pill_sep(self):
        s = QFrame()
        s.setFrameShape(QFrame.Shape.VLine)
        s.setFixedSize(1, 16)
        s.setStyleSheet("background: rgba(80,80,160,140); border: none;")
        return s

    def minimize_window(self): self.showMinimized()
    def maximize_window(self):
        if self.isMaximized():
            self.showNormal()
            self.maximize_btn.set_maximized(False)
        else:
            self.showMaximized()
            self.maximize_btn.set_maximized(True)
    def close_window(self): self.close()

    def set_ws_btn_visible(self, visible):
        self.show_ws_btn = visible
        self.ws_btn.setVisible(visible)
        self._sep_before_ws.setVisible(True)
        self._sep_after_ws.setVisible(visible)

    def _toggle_printy_bubble(self):
        if self._printy_bubble.isVisible(): self._printy_bubble.regenerate()
        self._printy_bubble.show_below(self.printy_btn)

    def add_tab(self, url=None):
        if url is None:
            url = getattr(self, 'edit_newtab_url', "https://www.google.com")
            if hasattr(url, 'text'): url = url.text()
        url = normalize_input(url)
        if url == "hovernet://settings":
            view = SettingsView(self)
            self.browser_area.addWidget(view)
            self.browser_area.setCurrentWidget(view)
            idx = self.tab_bar.addTab("Settings")
            self.tab_bar.setCurrentIndex(idx)
            self.url_bar.setText(url)
            self.new_tab_btn.trigger_animation()
            return view
        browser = BrowserView()
        browser.setUrl(QUrl(url))
        self.browser_area.addWidget(browser)
        self.browser_area.setCurrentWidget(browser)
        idx = self.tab_bar.addTab("New Tab")
        self.tab_bar.setCurrentIndex(idx)
        self.new_tab_btn.trigger_animation()
        browser.urlChanged.connect(lambda q: self.update_url(q, browser))
        browser.loadStarted.connect(lambda: self.on_load_started(browser))
        browser.loadProgress.connect(lambda p: self.on_load_progress(browser, p))
        browser.loadFinished.connect(lambda ok: self.on_load_finished(browser, ok))
        browser.iconChanged.connect(lambda i: self._on_favicon_changed(i, browser))
        return browser

    def on_load_started(self, b):
        idx = self.browser_area.indexOf(b)
        if idx != -1: self.tab_bar.setTabText(idx, "Loading...")
    def on_load_progress(self, b, p):
        idx = self.browser_area.indexOf(b)
        if idx != -1: self.tab_bar.setTabText(idx, f"{p}%")
    def on_load_finished(self, b, ok):
        idx = self.browser_area.indexOf(b)
        if idx != -1: self.tab_bar.setTabText(idx, b.title() or "New Tab")
    def _on_favicon_changed(self, i, b):
        idx = self.browser_area.indexOf(b)
        if idx != -1: self.tab_bar.setTabIcon(idx, i if not i.isNull() else QIcon())

    def load_url(self):
        url = normalize_input(self.url_bar.text())
        if url == "hovernet://settings": self.add_tab(url); return
        cur = self.browser_area.currentWidget()
        if isinstance(cur, BrowserView): cur.setUrl(QUrl(url))
        else: self.add_tab(url)

    def update_url(self, q, b):
        if b == self.browser_area.currentWidget(): self.url_bar.setText(q.toString())

    def switch_tab(self, idx):
        if 0 <= idx < self.browser_area.count():
            self.browser_area.setCurrentIndex(idx)
            cur = self.browser_area.currentWidget()
            if isinstance(cur, BrowserView): self.url_bar.setText(cur.url().toString())
            else: self.url_bar.setText("hovernet://settings")

    def close_tab(self, idx):
        if self.tab_bar.count() > 1:
            w = self.browser_area.widget(idx)
            self.tab_bar.removeTab(idx)
            self.browser_area.removeWidget(w)
            w.deleteLater()

    def on_tab_moved(self, f, t):
        w = self.browser_area.widget(f)
        self.browser_area.removeWidget(w)
        self.browser_area.insertWidget(t, w)
        self.browser_area.setCurrentIndex(self.tab_bar.currentIndex())

    def go_home(self):
        cur = self.browser_area.currentWidget()
        if isinstance(cur, BrowserView): cur.setUrl(QUrl("https://www.google.com"))
    def go_refresh(self):
        cur = self.browser_area.currentWidget()
        if isinstance(cur, BrowserView): cur.reload()
    def go_back(self):
        cur = self.browser_area.currentWidget()
        if isinstance(cur, BrowserView) and cur.history().canGoBack(): cur.back()
    def go_forward(self):
        cur = self.browser_area.currentWidget()
        if isinstance(cur, BrowserView) and cur.history().canGoForward(): cur.forward()

    def whenthes_space(self):
        cur = self.browser_area.currentWidget()
        if isinstance(cur, BrowserView): cur.setUrl(QUrl("https://whenthesspace.vercel.app"))

    def _zoom(self, f):
        cur = self.browser_area.currentWidget()
        if isinstance(cur, BrowserView): cur.setZoomFactor(cur.zoomFactor() * f)
    def _zoom_reset(self):
        cur = self.browser_area.currentWidget()
        if isinstance(cur, BrowserView): cur.setZoomFactor(1.0)

    def _act_file(self): QMessageBox.information(self, "File", "Not implemented")
    def _show_delete_history_dialog(self): DeleteHistoryDialog(self).exec()
    def _show_downloads_dialog(self): ViewDownloadsDialog(self._downloads, self).exec()
    def _show_hovernet_settings(self): self.add_tab("hovernet://settings")
    def _show_about_page(self):
        v = self.add_tab("hovernet://settings")
        if isinstance(v, SettingsView): v.sidebar.setCurrentRow(4)

    def _on_download_requested(self, download):
        path, _ = QFileDialog.getSaveFileName(self, "Save File", os.path.join(self._download_path, download.downloadFileName()))
        if not path: download.cancel(); return
        download.setDownloadDirectory(os.path.dirname(path))
        download.setDownloadFileName(os.path.basename(path))
        download.accept()
        entry = {"filename": os.path.basename(path), "status": "Downloading", "path": path, "item": download}
        self._downloads.append(entry)
        self._download_bubble.add_download(download, entry["filename"])

    def _check_for_updates(self):
        req = QNetworkRequest(QUrl("https://api.github.com/repos/whenthe-washere/visualos-hovernet/releases"))
        reply = self._update_nam.get(req)
        reply.finished.connect(lambda: self._on_update_reply(reply))

    def _on_update_reply(self, reply):
        if reply.error() == QNetworkReply.NetworkError.NoError:
            try:
                data = json.loads(bytes(reply.readAll()).decode())
                if data and isinstance(data, list):
                    latest_tag = data[0].get("tag_name", "")
                    if latest_tag:
                        # Clean version strings for comparison (remove non-numeric prefix like 'ver' or 'v')
                        def clean_v(v):
                            import re
                            cleaned = re.sub(r'^[^0-9]+', '', v.lower())
                            return [int(x) for x in cleaned.split('.') if x.isdigit()]
                        
                        try:
                            curr_v = clean_v(self.HOVERNET_VERSION)
                            new_v = clean_v(latest_tag)
                            
                            # Only show update if new_v > curr_v
                            if new_v > curr_v:
                                self._update_bubble.show_update(latest_tag, self.printy_btn)
                        except:
                            # Fallback to string comparison if splitting fails
                            if latest_tag != self.HOVERNET_VERSION:
                                self._update_bubble.show_update(latest_tag, self.printy_btn)
            except: pass
        reply.deleteLater()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if not hasattr(self, 'hover_trigger'): return
        
        self.hover_trigger.setGeometry(0, self.height() - 16, self.width(), 16)
        
        iw_w = self.width() - 24
        self.island_widget.setFixedWidth(iw_w)
        self.island_widget.adjustSize()
        iw_h = self.island_widget.height()
        
        y = self.height() - iw_h - 12 if self._island_visible else self.height()
        
        if self._island_anim.state() == QPropertyAnimation.State.Running:
            self._island_anim.setEndValue(QPoint(12, y))
        else:
            self.island_widget.setGeometry(12, y, iw_w, iw_h)

    def show_island(self):
        if not self._island_visible:
            self._island_visible = True
            self.island_widget.raise_()
            self._island_anim.stop()
            self._island_anim.setEndValue(QPoint(12, self.height() - self.island_widget.height() - 12))
            self._island_anim.start()

    def hide_island(self):
        if self._island_visible:
            self._island_visible = False
            self._island_anim.stop()
            self._island_anim.setEndValue(QPoint(12, self.height()))
            self._island_anim.start()

    def moveEvent(self, e):
        super().moveEvent(e)
        for b in ['_download_bubble', '_update_bubble', '_printy_bubble']:
            attr = getattr(self, b, None)
            if attr and attr.isVisible(): attr.reposition()

    def _install_topbar_drag_filters(self):
        self.bottom_bar.installEventFilter(self)
        self.app_title_text.installEventFilter(self)
        self.drag_handle.installEventFilter(self)
        for c in self.island_widget.findChildren(QWidget):
            if not isinstance(c, (QPushButton, QToolButton, QLineEdit)): c.installEventFilter(self)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QCursor

        # Guard: widgets may not be initialised yet during __init__
        if not hasattr(self, 'hover_trigger'):
            return super().eventFilter(obj, event)

        if obj is self.hover_trigger and event.type() == QEvent.Type.Enter:
            self.show_island()
        elif obj is self.island_widget and event.type() == QEvent.Type.Leave:
            pos = self.island_widget.mapFromGlobal(QCursor.pos())
            if not self.island_widget.rect().contains(pos):
                trigger_pos = self.hover_trigger.mapFromGlobal(QCursor.pos())
                if not self.hover_trigger.rect().contains(trigger_pos):
                    self.hide_island()

        if event.type() == QEvent.Type.MouseButtonPress and hasattr(self, '_printy_bubble'):
            for b in [self._printy_bubble, self._update_bubble]:
                if b.isVisible() and obj is not b: b.hide()
        
        return super().eventFilter(obj, event)

    def nativeEvent(self, eventType, message):
        """
        VS Code / Electron-style frameless window with full native snap support.
        - WM_NCCALCSIZE: tell Windows the client area = entire window (no drawn title bar).
        - WM_NCHITTEST:  return resize-edge or HTCAPTION codes so Windows handles
                         move, snap, maximise, and the snap-layout flyout natively.
        """
        if self.use_custom_title_bar and eventType == b'windows_generic_MSG':
            import ctypes, ctypes.wintypes
            msg = ctypes.cast(int(message), ctypes.POINTER(ctypes.wintypes.MSG)).contents

            WM_NCCALCSIZE = 0x0083
            WM_NCHITTEST  = 0x0084
            HTCLIENT      = 1
            HTCAPTION     = 2
            HTLEFT        = 10;  HTRIGHT       = 11
            HTTOP         = 12;  HTTOPLEFT     = 13;  HTTOPRIGHT    = 14
            HTBOTTOM      = 15;  HTBOTTOMLEFT  = 16;  HTBOTTOMRIGHT = 17
            BORDER        = 8   # px hit-test resize border

            # Extend client area to the full window rect (hides drawn title bar)
            if msg.message == WM_NCCALCSIZE and msg.wParam:
                return True, 0

            if msg.message == WM_NCHITTEST and hasattr(self, 'drag_handle'):
                x = ctypes.c_int16(msg.lParam & 0xFFFF).value
                y = ctypes.c_int16((msg.lParam >> 16) & 0xFFFF).value
                cursor = QPoint(x, y)
                r = self.frameGeometry()

                on_left   = x <= r.left()   + BORDER
                on_right  = x >= r.right()  - BORDER
                on_top    = y <= r.top()    + BORDER
                on_bottom = y >= r.bottom() - BORDER

                # ── Corners first (highest priority) ──────────────────────
                if on_top    and on_left:  return True, HTTOPLEFT
                if on_top    and on_right: return True, HTTOPRIGHT
                if on_bottom and on_left:  return True, HTBOTTOMLEFT
                if on_bottom and on_right: return True, HTBOTTOMRIGHT

                # ── Drag-handle zone overrides HTTOP for centre-top ───────
                #    This keeps the 4 px strip draggable + shows the line UI
                dh = self.drag_handle
                if dh.isVisible():
                    dh_tl = dh.mapToGlobal(dh.rect().topLeft())
                    dh_br = dh.mapToGlobal(dh.rect().bottomRight())
                    if dh_tl.x() <= x <= dh_br.x() and dh_tl.y() <= y <= dh_br.y():
                        return True, HTCAPTION

                # ── Remaining resize edges ────────────────────────────────
                if on_top:    return True, HTTOP
                if on_bottom: return True, HTBOTTOM
                if on_left:   return True, HTLEFT
                if on_right:  return True, HTRIGHT

                # ── Other caption / drag zones (bottom bar, title text) ───
                for widget in (self.bottom_bar, self.app_title_text):
                    if not widget.isVisible():
                        continue
                    tl = widget.mapToGlobal(widget.rect().topLeft())
                    br = widget.mapToGlobal(widget.rect().bottomRight())
                    if tl.x() <= x <= br.x() and tl.y() <= y <= br.y():
                        local = widget.mapFromGlobal(cursor)
                        child = widget.childAt(local)
                        if child is None or not isinstance(child, (QPushButton, QToolButton, QLineEdit)):
                            return True, HTCAPTION

            # ── Drive DragHandleLine animation via NC mouse messages ──────
            # Qt never delivers enterEvent/leaveEvent for non-client areas,
            # so we manually trigger the drag handle's hover timers here.
            WM_NCMOUSEMOVE  = 0x00A0
            WM_NCMOUSELEAVE = 0x02A2

            if msg.message in (WM_NCMOUSEMOVE, WM_NCMOUSELEAVE) and hasattr(self, 'drag_handle'):
                dh = self.drag_handle
                if msg.message == WM_NCMOUSEMOVE:
                    mx = ctypes.c_int16(msg.lParam & 0xFFFF).value
                    my = ctypes.c_int16((msg.lParam >> 16) & 0xFFFF).value
                    dh_tl = dh.mapToGlobal(dh.rect().topLeft())
                    dh_br = dh.mapToGlobal(dh.rect().bottomRight())
                    over = dh_tl.x() <= mx <= dh_br.x() and dh_tl.y() <= my <= dh_br.y()
                    if over and not getattr(self, '_dh_nc_hovered', False):
                        self._dh_nc_hovered = True
                        dh._leave_timer.stop()
                        dh._hover_timer.start(600)
                    elif not over and getattr(self, '_dh_nc_hovered', False):
                        self._dh_nc_hovered = False
                        dh._hover_timer.stop()
                        dh._leave_timer.start(300)
                else:  # WM_NCMOUSELEAVE
                    self._dh_nc_hovered = False
                    dh._hover_timer.stop()
                    dh._leave_timer.start(300)

        return super().nativeEvent(eventType, message)

    def _apply_win32_frame(self):
        """Re-add WS_THICKFRAME + WS_CAPTION so Windows enables snap/resize/animations.
        Also requests DWM rounded corners (Windows 11+)."""
        import ctypes, ctypes.wintypes
        GWL_STYLE     = -16
        WS_THICKFRAME = 0x00040000
        WS_CAPTION    = 0x00C00000
        hwnd = int(self.winId())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
        style |= WS_THICKFRAME | WS_CAPTION
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)
        # SWP_NOMOVE|SWP_NOSIZE|SWP_NOZORDER|SWP_NOACTIVATE|SWP_FRAMECHANGED
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0037)
        # Ask DWM to round the corners (Windows 11+; silently ignored on Win10)
        try:
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            DWMWCP_ROUND = 2          # round corners
            pref = ctypes.c_int(DWMWCP_ROUND)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(pref),
                ctypes.sizeof(pref)
            )
        except Exception:
            pass

    def apply_custom_title_bar_setting(self):
        flags = self.windowFlags()
        if self.use_custom_title_bar:
            flags |= Qt.WindowType.FramelessWindowHint
        else:
            flags &= ~Qt.WindowType.FramelessWindowHint
        self.setWindowFlags(flags)
        self.app_title_text.setVisible(self.use_custom_title_bar)
        self.show()
        if self.use_custom_title_bar:
            # Re-add Win32 frame bits so snap layouts / Aero Snap still work
            self._apply_win32_frame()

    def set_custom_title_bar_enabled(self, enabled):
        self.use_custom_title_bar = enabled
        self.apply_custom_title_bar_setting()

    def set_expandable_title_enabled(self, e):
        self.use_expandable_title = e
        if not e: self.app_title_text.contract_title()

    def _show_site_info(self): QMessageBox.information(self, "Site Info", f"URL: {self.url_bar.text()}")
