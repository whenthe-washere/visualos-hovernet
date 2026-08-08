import os
import sys
import json
import subprocess
from urllib.parse import quote_plus
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtCore import Qt, QUrl, QTimer, QSize, QPoint, QRect, QStringListModel, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QToolButton, QHBoxLayout, QWidget, QVBoxLayout,
    QMenu, QStackedWidget, QMessageBox, QFileDialog, QDialog, QLabel, QTextEdit,
    QPushButton, QCheckBox, QFrame, QListView, QLineEdit, QLayout, QGraphicsOpacityEffect
)
from PySide6.QtGui import QFont, QIcon, QPalette, QColor
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineDownloadRequest, QWebEngineScript, QWebEngineSettings, QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView

from .utils.easing import curve_linear_out

from .ui.widgets.title_bar import ExpandableAppTitle, DragHandleLine
from .ui.widgets.buttons import NewTabButton, TitleBarButton
from .ui.widgets.nav_icons import AnimatedIconButton
from .ui.widgets.entries import UrlLineEdit
from .core.tabs import CustomTabBar
from .core.browser import BrowserView
from .ui.components.bubbles import DownloadBubble, DownloadHoverBubble, UpdateBubble, PrintyBubble, ZoomBubble, FindBubble
from .ui.dialogs.autocomplete import AutocompleteDropdown
from .ui.dialogs.site_info import SiteInfoDialog
from .pages.history import HistoryView
from .pages.settings import SettingsView
from .utils.helpers import normalize_input
from .utils.oauth import OAuthManager
from .utils.sso import SSOInterceptor


# ZoomWidget removed - replaced by zoom indicator inside UrlLineEdit and ZoomBubble


class HoverNetPY(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("visualOS HoverNet")
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
            base_path = os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), "HoverNet")
            os.makedirs(base_path, exist_ok=True)
            try: prof.setPersistentStoragePath(base_path)
            except: pass
            try:
                prof.setCachePath(os.path.join(base_path, "Cache"))
                prof.setHttpCacheType(QWebEngineProfile.DiskHttpCache)
            except: pass
        except: pass

        # SSO interceptor for auto Bearer token injection
        self.oauth_manager = OAuthManager()
        self._sso_interceptor = SSOInterceptor(self._get_bearer_token)
        prof = QWebEngineProfile.defaultProfile()
        try:
            prof.setRequestInterceptor(self._sso_interceptor)
        except Exception:
            pass

        self.cloud_storage = "Local"  # "Local", "Google Drive", "OneDrive"
        self.cloud_folder = {"Google Drive": None, "OneDrive": None}  # {'id':..., 'name':...} per provider

        central = QWidget()
        central.setMouseTracking(True)
        self._central_widget = central  # Store ref for dynamic restyling
        central.setStyleSheet("QWidget { background-color: transparent; border-radius: 10px; }")
        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.setCentralWidget(central)

        # Load Layout & Accent settings
        self.ACCENT_COLORS = {
            "WS 3.5 Arc": {
                "primary": "#558EFF",
                "secondary": "#0055FF",
                "border": "#334466",
                "rgb": (85, 142, 255)
            },
            "Neon Purple": {
                "primary": "#A855F7",
                "secondary": "#7C3AED",
                "border": "#4C2A8A",
                "rgb": (168, 85, 247)
            },
            "Emerald Green": {
                "primary": "#10B981",
                "secondary": "#059669",
                "border": "#1B4D3E",
                "rgb": (16, 185, 129)
            },
            "Sunset Orange": {
                "primary": "#F97316",
                "secondary": "#EA580C",
                "border": "#5C2D18",
                "rgb": (249, 115, 22)
            },
            "Cyberpunk Pink": {
                "primary": "#EC4899",
                "secondary": "#DB2777",
                "border": "#631E43",
                "rgb": (236, 72, 153)
            }
        } # so this fucker was the reason i couldnt update the whole app's accents
        self.layout_style = "standard"
        self.accent_color_name = "WS 3.5 Arc"
        self.browser_theme = "System"
        self.load_hovernet_settings()
        
        # Apply theme before layout
        self.apply_browser_theme()
        
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
        self.tab_bar.setUsesScrollButtons(False)
        self.tab_bar.setElideMode(Qt.TextElideMode.ElideRight)
        self.tab_bar.setIconSize(QSize(16, 16))

        self.url_bar = UrlLineEdit()
        self.url_bar.setPlaceholderText("Search or enter web address")
        self.url_bar.returnPressed.connect(self.load_url)
        self.url_bar.setFont(app_font)

        self.back_btn = AnimatedIconButton('back')
        self.back_btn.setEnabled(False)
        self.back_btn.clicked.connect(self.go_back)

        self.forward_btn = AnimatedIconButton('forward')
        self.forward_btn.setEnabled(False)
        self.forward_btn.clicked.connect(self.go_forward)

        self.site_info_btn = AnimatedIconButton('site_info')
        self.site_info_btn.clicked.connect(self._show_site_info)

        self.refresh_btn = AnimatedIconButton('refresh')
        self.refresh_btn.clicked.connect(self.go_refresh)

        self.show_ws_btn = False
        
        _tp_btn_style = "QToolButton { background: transparent; border: none; } QToolButton::menu-indicator { width: 0; height: 0; image: none; }"
        self.home_btn = AnimatedIconButton('home')
        self.home_btn.setToolTip("Home")
        self.home_btn.clicked.connect(self.go_home)
        self.home_btn.setStyleSheet(_tp_btn_style)

        self.ws_btn = AnimatedIconButton('ws')
        self.ws_btn.setToolTip("whenthe's space")
        self.ws_btn.clicked.connect(self.whenthes_space)
        self.ws_btn.setStyleSheet(_tp_btn_style)

        self.tools_btn = AnimatedIconButton('tools')
        self.tools_btn.setToolTip("Tools")
        self.tools_btn.setStyleSheet(_tp_btn_style)
        
        self._sep_before_ws = self._make_pill_sep()
        self._sep_after_ws = self._make_pill_sep()
        self._sep_before_tools = self._make_pill_sep()

        self.printy_btn = AnimatedIconButton('python')
        self.printy_btn.setToolTip("Printy")
        self.printy_btn.setStyleSheet(_tp_btn_style)
        self.printy_btn.clicked.connect(self._toggle_printy_bubble)

        from PySide6.QtGui import QShortcut, QKeySequence

        self.tools_menu = QMenu()
        act_new_window = self.tools_menu.addAction("New Window")
        act_new_window.setShortcut(QKeySequence("Ctrl+N"))
        act_new_window.triggered.connect(self._new_window)

        act_print = self.tools_menu.addAction("Print Page")
        act_print.setShortcut(QKeySequence("Ctrl+P"))
        act_print.triggered.connect(self._print_page)

        find_menu = self.tools_menu.addMenu("Find and edit")
        act_find = find_menu.addAction("Find")
        act_find.setShortcut(QKeySequence("Ctrl+F"))
        act_find.triggered.connect(self._act_find)

        find_menu.addSeparator()

        act_cut = find_menu.addAction("Cut")
        act_cut.setShortcut(QKeySequence("Ctrl+X"))
        act_cut.triggered.connect(self._act_cut)

        act_copy = find_menu.addAction("Copy")
        act_copy.setShortcut(QKeySequence("Ctrl+C"))
        act_copy.triggered.connect(self._act_copy)

        act_paste = find_menu.addAction("Paste")
        act_paste.setShortcut(QKeySequence("Ctrl+V"))
        act_paste.triggered.connect(self._act_paste)

        self.tools_menu.addSeparator()

        act_fullscreen = self.tools_menu.addAction("Fullscreen")
        act_fullscreen.setShortcut(QKeySequence("F11"))
        act_fullscreen.triggered.connect(self._toggle_fullscreen)

        self.tools_menu.addSeparator()

        history_menu = self.tools_menu.addMenu("History")
        act_browse_hist = history_menu.addAction("View full history")
        act_browse_hist.setShortcut(QKeySequence("Ctrl+H"))
        act_browse_hist.triggered.connect(self._show_browsing_history)

        history_menu.addSeparator()
        self._history_menu = history_menu

        self.tools_menu.addSeparator()
        self.tools_menu.addAction("About HoverNet", self._show_about_page)
        self.tools_menu.addAction("Settings", self._show_hovernet_settings)
        self.tools_btn.setMenu(self.tools_menu)
        self.tools_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        QShortcut(QKeySequence("Ctrl+N"), self, self._new_window)
        QShortcut(QKeySequence("Ctrl+P"), self, self._print_page)
        QShortcut(QKeySequence("F11"), self, self._toggle_fullscreen)
        QShortcut(QKeySequence("Ctrl+F"), self, self._act_find)
        QShortcut(QKeySequence("Ctrl+H"), self, self._show_browsing_history)
        QShortcut(QKeySequence("Ctrl+X"), self, self._act_cut)
        QShortcut(QKeySequence("Ctrl+C"), self, self._act_copy)
        QShortcut(QKeySequence("Ctrl+V"), self, self._act_paste)

        self.drag_handle = DragHandleLine(self)
        self.main_layout.addWidget(self.drag_handle)
        
        self.browser_area = QStackedWidget()
        self.main_layout.addWidget(self.browser_area)

        self.new_tab_btn = NewTabButton()
        self.new_tab_btn.clicked.connect(self.add_tab)
        
        self.island_widget = QWidget(central)
        self.island_widget.setObjectName("islandWidget")
        self.island_widget.setStyleSheet("""
            QWidget#islandWidget {
                background-color: rgba(30, 40, 60, 215);
                border-radius: 14px;
                border: none;
            }
        """)

        # Call setup dynamic layouts
        self.setup_island_layout()

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
        self.save_data_enabled = True
        self.save_download_history = True
        self.save_data_frequency = "Every 15 minutes"
        self._block_third_party_cookies = False
        
        self.apply_custom_title_bar_setting()
        
        # Apply accent highlight color globally on startup
        accent_rgb = self.get_accent_rgb()
        qcol = QColor(*accent_rgb)
        pal = self.palette()
        pal.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Highlight, qcol)
        pal.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Link, qcol)
        self.setPalette(pal)
        
        self.HOVERNET_VERSION = "2.35.00"
        self.HOVERNET_VARIANT = "py"
        self._update_bubble = UpdateBubble(self)
        self._update_nam = QNetworkAccessManager(self)
        QTimer.singleShot(3000, self._check_for_updates)
        self._download_bubble = DownloadBubble(self)
        self._download_bubble.set_anchor(self.tools_btn)
        self._download_hover_bubble = DownloadHoverBubble(self)
        self._printy_bubble = PrintyBubble(self)
        
        self._zoom_bubble = ZoomBubble(self)
        self._zoom_bubble.installEventFilter(self)

        self._find_bubble = FindBubble(self)
        self._find_bubble.installEventFilter(self)
        
        QApplication.instance().installEventFilter(self)
        self._island_ready = True
        self._island_transition_active = False

    def _make_pill_sep(self):
        s = QFrame()
        s.setFrameShape(QFrame.Shape.VLine)
        s.setFixedSize(1, 16)
        s.setStyleSheet("background: rgba(80,80,160,140); border: none;")
        return s

    def minimize_window(self): self.showMinimized()
    def maximize_window(self):
        import ctypes
        WM_SYSCOMMAND = 0x0112
        SC_RESTORE    = 0xF120
        SC_MAXIMIZE   = 0xF030
        hwnd = int(self.winId())
        if self.isMaximized():
            ctypes.windll.user32.SendMessageW(hwnd, WM_SYSCOMMAND, SC_RESTORE, 0)
            self.maximize_btn.set_maximized(False)
        else:
            ctypes.windll.user32.SendMessageW(hwnd, WM_SYSCOMMAND, SC_MAXIMIZE, 0)
            self.maximize_btn.set_maximized(True)
    def close_window(self): self.close()

    def set_ws_btn_visible(self, visible):
        self.show_ws_btn = visible
        self.ws_btn.setVisible(visible)
        self._sep_before_ws.setVisible(True)
        self._sep_after_ws.setVisible(visible)

    def set_data_saving_enabled(self, enabled):
        self.save_data_enabled = enabled

    def set_save_download_history(self, enabled):
        self.save_download_history = enabled

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
            self._rebuild_history_menu()
            return view
        if url == "hovernet://history":
            view = HistoryView(self)
            self.browser_area.addWidget(view)
            self.browser_area.setCurrentWidget(view)
            idx = self.tab_bar.addTab("History")
            self.tab_bar.setCurrentIndex(idx)
            self.url_bar.setText(url)
            self.new_tab_btn.trigger_animation()
            self._rebuild_history_menu()
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
        self._rebuild_history_menu()
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
        if url in ("hovernet://settings", "hovernet://history"): self.add_tab(url); return
        cur = self.browser_area.currentWidget()
        if isinstance(cur, BrowserView): cur.setUrl(QUrl(url))
        else: self.add_tab(url)

    def update_url(self, q, b):
        if b == self.browser_area.currentWidget():
            self.url_bar.setText(q.toString())
            self.update_nav_buttons()

    def switch_tab(self, idx):
        if 0 <= idx < self.browser_area.count():
            self.browser_area.setCurrentIndex(idx)
            cur = self.browser_area.currentWidget()
            if isinstance(cur, BrowserView):
                self.url_bar.setText(cur.url().toString())
            elif isinstance(cur, SettingsView):
                self.url_bar.setText("hovernet://settings")
            elif isinstance(cur, HistoryView):
                self.url_bar.setText("hovernet://history")
                cur.refresh()
            else:
                self.url_bar.setText("hovernet://settings")
            self.update_nav_buttons()
            self._rebuild_history_menu()

    def close_tab(self, idx):
        if self.tab_bar.count() > 1:
            w = self.browser_area.widget(idx)
            self.tab_bar.removeTab(idx)
            self.browser_area.removeWidget(w)
            w.deleteLater()
            self._on_tab_hovered(-1)
            self._rebuild_history_menu()

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

    def update_nav_buttons(self):
        cur = self.browser_area.currentWidget()
        if isinstance(cur, BrowserView):
            self.back_btn.setEnabled(cur.history().canGoBack())
            self.forward_btn.setEnabled(cur.history().canGoForward())
        else:
            self.back_btn.setEnabled(False)
            self.forward_btn.setEnabled(False)

    def whenthes_space(self):
        cur = self.browser_area.currentWidget()
        if isinstance(cur, BrowserView): cur.setUrl(QUrl("https://whenthesspace.vercel.app"))

    def _set_zoom(self, f):
        cur = self.browser_area.currentWidget()
        if isinstance(cur, BrowserView):
            cur.setZoomFactor(f)
            pct = int(round(f * 100))
            self.url_bar.zoom_indicator.setText(f"{pct}%")
            self._zoom_bubble.update_zoom(f)

    def _zoom(self, f):
        cur = self.browser_area.currentWidget()
        if isinstance(cur, BrowserView):
            new_f = cur.zoomFactor() * f
            self._set_zoom(new_f)

    def _zoom_reset(self):
        self._set_zoom(1.0)

    def _new_window(self):
        main = HoverNetPY()
        main.show()
        main.add_tab()

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            if hasattr(self, 'maximize_btn'):
                self.maximize_btn.set_maximized(self.isMaximized())
        else:
            self.showFullScreen()

    def _print_page(self):
        cur = self.browser_area.currentWidget()
        if isinstance(cur, BrowserView):
            cur.page().print(self._print_callback)

    def _print_callback(self, ok):
        if not ok:
            QMessageBox.warning(self, "Print", "Print failed or was cancelled.")

    def _act_find(self):
        cur = self.browser_area.currentWidget()
        if isinstance(cur, BrowserView):
            self._find_bubble.show_below(self.url_bar)
        else:
            QMessageBox.information(self, "Find", "Not available on this page.")

    def _act_cut(self):
        cur = self.browser_area.currentWidget()
        if isinstance(cur, BrowserView):
            cur.page().triggerAction(QWebEnginePage.Cut)
    def _act_copy(self):
        cur = self.browser_area.currentWidget()
        if isinstance(cur, BrowserView):
            cur.page().triggerAction(QWebEnginePage.Copy)
    def _act_paste(self):
        cur = self.browser_area.currentWidget()
        if isinstance(cur, BrowserView):
            cur.page().triggerAction(QWebEnginePage.Paste)
    def _show_browsing_history(self): self.add_tab("hovernet://history")
    def _show_hovernet_settings(self): self.add_tab("hovernet://settings")
    def _show_about_page(self):
        v = self.add_tab("hovernet://settings")
        if isinstance(v, SettingsView): v.sidebar.setCurrentRow(4)

    def _rebuild_history_menu(self):
        # Remove only dynamic entries (after the separator), keep Browsing history & Downloads
        actions = self._history_menu.actions()
        sep_idx = None
        for i, a in enumerate(actions):
            if a.isSeparator():
                sep_idx = i
                break
        if sep_idx is not None:
            for a in actions[sep_idx + 1:]:
                self._history_menu.removeAction(a)
        # Add recent tabs after the separator
        seen = []
        for idx in range(self.browser_area.count()):
            w = self.browser_area.widget(idx)
            if isinstance(w, BrowserView):
                t = w.title() or w.url().toString()
                u = w.url().toString()
                if u and u not in [s[1] for s in seen]:
                    seen.append((t, u))
                if len(seen) >= 10:
                    break
        for title, url in seen[:10]:
            label = title if len(title) < 40 else title[:37] + "..."
            act = self._history_menu.addAction(label, lambda checked=False, u=url: self.add_tab(u))
            act.setToolTip(url)

    def _on_download_requested(self, download):
        view = self._find_download_view(download)
        cs = getattr(self, 'cloud_storage', 'Local')
        if cs != "Local":
            import tempfile
            temp_dir = tempfile.mkdtemp(prefix="hovernet_")
            orig_name = download.downloadFileName()
            temp_path = os.path.join(temp_dir, orig_name)
            download.setDownloadDirectory(temp_dir)
            download.setDownloadFileName(orig_name)
            download.accept()
            entry = {"filename": orig_name, "status": "Uploading", "path": temp_path,
                     "item": download, "cloud": cs, "temp_dir": temp_dir,
                     "view": view, "minimized": False}
            self._downloads.append(entry)
            self._download_bubble.add_download(download, orig_name, view)
            # When download finishes, upload to cloud
            download.finished.connect(lambda: self._on_cloud_download_finished(download))
        else:
            path, _ = QFileDialog.getSaveFileName(self, "Save File",
                os.path.join(self._download_path, download.downloadFileName()))
            if not path: download.cancel(); return
            download.setDownloadDirectory(os.path.dirname(path))
            download.setDownloadFileName(os.path.basename(path))
            download.accept()
            entry = {"filename": os.path.basename(path), "status": "Downloading",
                     "path": path, "item": download, "view": view, "minimized": False}
            self._downloads.append(entry)
            self._download_bubble.add_download(download, entry["filename"], view)

        download.receivedBytesChanged.connect(lambda: self._refresh_tab_outlines())
        download.finished.connect(lambda: self._on_download_finished(download))

    def _find_download_view(self, download):
        """The tab that initiated the download. Matches by source URL first
        (downloads can start from background tabs), falling back to the
        currently active tab."""
        try:
            dl_url = download.url().toString()
        except Exception:
            dl_url = ""
        if dl_url:
            for i in range(self.browser_area.count()):
                w = self.browser_area.widget(i)
                if isinstance(w, BrowserView):
                    try:
                        if w.url().toString() == dl_url:
                            return w
                    except Exception:
                        pass
        return self.browser_area.currentWidget()

    def _find_download_entry(self, download):
        for e in self._downloads:
            if e.get("item") is download:
                return e
        return None

    def _find_active_download_for_view(self, view):
        for e in self._downloads:
            item = e.get("item")
            if item is not None and not e.get("done") and not item.isFinished() and e.get("view") is view:
                return e
        return None

    def _minimize_download(self, download):
        entry = self._find_download_entry(download)
        if entry:
            entry["minimized"] = True
        self._refresh_tab_outlines()

    def _refresh_tab_outlines(self):
        """Recompute every tab's download outline from the active minimized
        downloads (a tab's outline shows the slowest of its downloads)."""
        if not hasattr(self, 'tab_bar'):
            return
        progress_map = {}
        for e in self._downloads:
            item = e.get("item")
            if item is None or e.get("done") or item.isFinished():
                continue
            if not e.get("minimized"):
                continue
            view = e.get("view")
            if view is None:
                continue
            idx = self.browser_area.indexOf(view)
            if idx == -1:
                continue
            # Use the percentage already computed by the download bubble so
            # the outline always matches what the user sees in the bar.
            pct = e.get("pct", 0)
            cur = progress_map.get(idx)
            if cur is None or pct < cur:
                progress_map[idx] = pct
        if progress_map != self.tab_bar.download_progress_map():
            self.tab_bar.set_download_progress_map(progress_map)

    def _on_download_finished(self, download):
        entry = self._find_download_entry(download)
        if entry:
            entry["done"] = True
            if "cloud" not in entry:
                if getattr(download, 'isCanceled', lambda: False)():
                    entry["status"] = "Cancelled"
                else:
                    entry["status"] = "Completed"
        self._refresh_tab_outlines()
        if getattr(self, '_download_hover_bubble', None) is not None:
            self._download_hover_bubble._on_finished(download)

    def _on_tab_hovered(self, index):
        if not hasattr(self, '_download_hover_bubble'):
            return
        if index == -1 or index >= self.browser_area.count():
            # Moving from the tab onto the floating preview must not dismiss it,
            # otherwise its buttons would be unusable.
            if self._download_hover_bubble._cursor_over_self():
                return
            self._download_hover_bubble.hide_bubble()
            return
        view = self.browser_area.widget(index)
        entry = self._find_active_download_for_view(view)
        if entry is not None:
            self._download_hover_bubble.show_on_tab(index, entry["item"], entry["filename"])
        else:
            self._download_hover_bubble.hide_bubble()

    def _on_cloud_download_finished(self, download):
        entry = None
        for e in self._downloads:
            if e.get("item") is download:
                entry = e
                break
        if not entry:
            return
        entry["done"] = True
        temp_path = entry.get("path", "")
        filename = entry.get("filename", "file")
        cloud = entry.get("cloud", "")
        temp_dir = entry.get("temp_dir", "")

        result = None
        folder_cfg = getattr(self, 'cloud_folder', None) or {}
        folder = folder_cfg.get(cloud) or {}
        folder_id = folder.get('id') if isinstance(folder, dict) else None
        if cloud == "Google Drive":
            result = self.oauth_manager.upload_to_google_drive(temp_path, filename, folder_id)
        elif cloud == "OneDrive":
            result = self.oauth_manager.upload_to_onedrive(temp_path, filename, folder_id)

        # Clean up temp
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if temp_dir and os.path.exists(temp_dir):
                os.rmdir(temp_dir)
        except Exception:
            pass

        if result and result.get('success'):
            msg = f"Saved to {cloud}: {filename}"
        else:
            err = result.get('error', 'Unknown error') if result else 'Upload failed'
            msg = f"Cloud upload failed: {err} — saved to temp: {temp_path}"

        entry["status"] = msg
        QMessageBox.information(self, "Cloud Download", msg)

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
        for b in ['_download_bubble', '_update_bubble', '_printy_bubble', '_download_hover_bubble']:
            attr = getattr(self, b, None)
            if attr and attr.isVisible(): attr.reposition()

    def _install_topbar_drag_filters(self):
        self.bottom_bar.installEventFilter(self)
        self.app_title_text.installEventFilter(self)
        self.drag_handle.installEventFilter(self)
        for c in self.island_widget.findChildren(QWidget):
            if c is self.url_bar.zoom_indicator:
                continue
            if not isinstance(c, (QPushButton, QToolButton, QLineEdit)): c.installEventFilter(self)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QCursor

        # Guard: widgets may not be initialised yet during __init__
        if not hasattr(self, 'hover_trigger'):
            return super().eventFilter(obj, event)

        if hasattr(self, 'hover_trigger') and obj is self.hover_trigger and event.type() == QEvent.Type.Enter:
            if not self._island_visible:
                self.show_island()
                
        if obj is self.url_bar.zoom_indicator and event.type() == QEvent.Type.Enter:
            self._zoom_bubble.show_bubble(self.url_bar.zoom_indicator)
            
        if obj is self.url_bar.zoom_indicator and event.type() == QEvent.Type.Leave:
            QTimer.singleShot(100, self._zoom_bubble.hide_bubble)
            
        if obj is self.url_bar.zoom_indicator and event.type() == QEvent.Type.MouseButtonRelease:
            if not self._zoom_bubble.isVisible():
                self._zoom_bubble.show_bubble(self.url_bar.zoom_indicator)
            else:
                self._zoom_bubble.hide()
            
        if obj is getattr(self, '_zoom_bubble', None) and event.type() == QEvent.Type.Leave:
            self._zoom_bubble.hide_bubble()

        # Close FindBubble on Escape
        if hasattr(self, '_find_bubble') and self._find_bubble.isVisible() and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self._find_bubble._close_and_clear()
                return True

        elif obj is self.island_widget and event.type() == QEvent.Type.Leave:
            pos = self.island_widget.mapFromGlobal(QCursor.pos())
            if not self.island_widget.rect().contains(pos):
                trigger_pos = self.hover_trigger.mapFromGlobal(QCursor.pos())
                if not self.hover_trigger.rect().contains(trigger_pos):
                    # Keep the island visible while the URL bar is being edited
                    # or while any bubble is showing, so typing/hovering the
                    # floating UI never causes the island to collapse away.
                    if self._url_bar_active() or self._any_bubble_visible():
                        return True
                    self.hide_island()
        
        return super().eventFilter(obj, event)

    def _url_bar_active(self):
        fw = QApplication.focusWidget()
        if fw is None:
            return False
        if fw is self.url_bar:
            return True
        w = fw
        while w is not None:
            if w is self.url_bar:
                return True
            w = w.parentWidget()
        return False

    def _any_bubble_visible(self):
        for b in ('_download_bubble', '_download_hover_bubble', '_update_bubble',
                  '_printy_bubble', '_zoom_bubble', '_find_bubble'):
            attr = getattr(self, b, None)
            if attr is not None and attr.isVisible():
                return True
        return False

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
            BORDER  = 8   # px hit-test resize border

            # Extend client area to the full window rect (hides drawn title bar)
            if msg.message == WM_NCCALCSIZE and msg.wParam:
                return True, 0

            if msg.message == WM_NCHITTEST:
                # 1. Safely extract signed coordinates (Crucial for multi-monitor arrays)
                x = ctypes.c_short(msg.lParam & 0xFFFF).value
                y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                cursor = QPoint(x, y)

                # 2. Grab the REAL physical window bounds straight from the OS
                rect = ctypes.wintypes.RECT()
                ctypes.windll.user32.GetWindowRect(int(self.winId()), ctypes.byref(rect))

                # 3. Calculate hit states using pure Win32 physical coordinates
                on_left   = x < (rect.left + BORDER)
                on_right  = x >= (rect.right - BORDER)
                on_top    = y < (rect.top + BORDER)
                on_bottom = y >= (rect.bottom - BORDER)

                # ── Corners First (Highest Priority) ──────────────────────
                if on_top    and on_left:  return True, HTTOPLEFT
                if on_top    and on_right: return True, HTTOPRIGHT
                if on_bottom and on_left:  return True, HTBOTTOMLEFT
                if on_bottom and on_right: return True, HTBOTTOMRIGHT

                # ── Drag-handle zone overrides HTTOP for centre-top ───────
                dh = self.drag_handle
                if dh.isVisible():
                    # Note: mapToGlobal works in logical pixels, but because we are 
                    # comparing it to raw coordinates, we must map accurately.
                    # If this still offsets on your laptop screen, convert the 
                    # drag_handle rect boundaries using self.devicePixelRatioF()
                    dh_tl = dh.mapToGlobal(dh.rect().topLeft())
                    dh_br = dh.mapToGlobal(dh.rect().bottomRight())
                    
                    # Account for High-DPI scaling factor if needed
                    dpi = self.devicePixelRatioF()
                    if (dh_tl.x() * dpi) <= x <= (dh_br.x() * dpi) and (dh_tl.y() * dpi) <= y <= (dh_br.y() * dpi):
                        return True, HTCAPTION

                # ── Remaining Resize Edges ────────────────────────────────
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
                    dpi = self.devicePixelRatioF()
                    if (tl.x() * dpi) <= x <= (br.x() * dpi) and (tl.y() * dpi) <= y <= (br.y() * dpi):
                        # Convert raw screen back to logical for Qt child tracking
                        logical_cursor = QPoint(int(x / dpi), int(y / dpi))
                        local = widget.mapFromGlobal(logical_cursor)
                        child = widget.childAt(local)
                        
                        is_interactive = False
                        c = child
                        while c and c != widget:
                            if isinstance(c, (QPushButton, QToolButton, QLineEdit)) or c is self.url_bar.zoom_indicator or type(c).__name__ in ('CustomTabBar', 'QTabBar', 'CompactTabScrollArea', 'QScrollArea'):
                                is_interactive = True
                                break
                            c = c.parentWidget()
                            
                        if child is None or not is_interactive:
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

    def changeEvent(self, event):
        if event.type() == event.Type.WindowStateChange and hasattr(self, 'maximize_btn'):
            self.maximize_btn.set_maximized(self.isMaximized())
        super().changeEvent(event)

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
        if hasattr(self, 'layout_style') and self.layout_style == "compact":
            self.app_title_text.setVisible(False)
        else:
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

    def _show_site_info(self):
        if self.url_bar.text().startswith("hovernet://"):
            return
        dlg = SiteInfoDialog(self, self)
        dlg.exec()

    def _get_cookie_store(self):
        from PySide6.QtWebEngineCore import QWebEngineProfile
        return QWebEngineProfile.defaultProfile().cookieStore()

    def _cookie_filter(self, request):
        return not request.thirdParty

    def _get_bearer_token(self, provider):
        token_data = self.oauth_manager._load_token(provider)
        if token_data:
            return token_data.get('access_token', '')
        return ''

    def clear_layout(self, layout):
        core_widgets = (self.tab_bar, getattr(self, 'new_tab_btn', None), getattr(self, 'app_title_text', None), getattr(self, 'url_bar', None), getattr(self, 'back_btn', None), getattr(self, 'forward_btn', None), getattr(self, 'site_info_btn', None), getattr(self, 'refresh_btn', None), getattr(self, 'home_btn', None), getattr(self, 'ws_btn', None), getattr(self, 'printy_btn', None), getattr(self, 'tools_btn', None), getattr(self, 'minimize_btn', None), getattr(self, 'maximize_btn', None), getattr(self, 'close_btn', None), getattr(self, '_sep_before_ws', None), getattr(self, '_sep_after_ws', None), getattr(self, '_sep_before_tools', None), getattr(self, 'island_contents', None))
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    if widget not in core_widgets:
                        widget.setParent(None)
                        widget.deleteLater()
                else:
                    self.clear_layout(item.layout())

    def setup_island_layout(self):
        animate = getattr(self, '_island_ready', False) and self.isVisible()
        if animate and getattr(self, '_island_fade_effect', None) is not None:
            if getattr(self, '_island_transition_active', False):
                # A transition is already running; rebuild directly to avoid
                # stacking animations.
                if getattr(self, '_island_fade_out_anim', None) is not None:
                    try:
                        self._island_fade_out_anim.stop()
                    except RuntimeError:
                        pass
                    self._island_fade_out_anim = None
                self._island_fade_effect.setOpacity(0.0)
                self._do_setup_island_layout()
                return
            self._island_transition_active = True
            self._transition_old_h = self.island_widget.height()
            self._fade_island_contents_out(self._do_setup_island_layout)
            return
        self._do_setup_island_layout()

    def _fade_island_contents_out(self, on_finished):
        if getattr(self, '_island_fade_in_anim', None) is not None:
            try:
                self._island_fade_in_anim.stop()
            except RuntimeError:
                pass
            self._island_fade_in_anim = None
        self._island_fade_effect.setOpacity(1.0)
        anim = QPropertyAnimation(self._island_fade_effect, b"opacity", self.island_contents)
        anim.setDuration(100)
        anim.setEasingCurve(curve_linear_out())
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(on_finished)
        self._island_fade_out_anim = anim
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _fade_island_contents_in(self):
        self.island_contents.show()
        self._island_fade_effect.setOpacity(0.0)
        anim = QPropertyAnimation(self._island_fade_effect, b"opacity", self.island_contents)
        anim.setDuration(140)
        anim.setEasingCurve(curve_linear_out())
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        self._island_fade_in_anim = anim
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _start_island_resize(self, old_h, new_h):
        if getattr(self, '_island_resize_anim', None) is not None:
            try:
                self._island_resize_anim.stop()
            except RuntimeError:
                pass
        w = self.width() - 24
        y_old = self.height() - old_h - 12 if self._island_visible else self.height()
        y_new = self.height() - new_h - 12 if self._island_visible else self.height()
        anim = QPropertyAnimation(self.island_widget, b"geometry", self)
        anim.setDuration(160)
        anim.setEasingCurve(curve_linear_out())
        anim.setStartValue(QRect(12, y_old, w, old_h))
        anim.setEndValue(QRect(12, y_new, w, new_h))
        anim.finished.connect(self._finish_island_transition)
        self._island_resize_anim = anim
        anim.start()

    def _finish_island_transition(self):
        self._island_transition_active = False
        self.island_widget.adjustSize()
        self._fade_island_contents_in()

    def _do_setup_island_layout(self):
        # 1. Reparent all widgets to self.island_widget temporarily
        self.tab_bar.setParent(self.island_widget)
        self.new_tab_btn.setParent(self.island_widget)
        self.app_title_text.setParent(self.island_widget)
        self.url_bar.setParent(self.island_widget)
        self.back_btn.setParent(self.island_widget)
        self.forward_btn.setParent(self.island_widget)
        self.site_info_btn.setParent(self.island_widget)
        self.refresh_btn.setParent(self.island_widget)
        self.home_btn.setParent(self.island_widget)
        self.ws_btn.setParent(self.island_widget)
        self.printy_btn.setParent(self.island_widget)
        self.tools_btn.setParent(self.island_widget)
        self.minimize_btn.setParent(self.island_widget)
        self.maximize_btn.setParent(self.island_widget)
        self.close_btn.setParent(self.island_widget)
        
        if hasattr(self, '_sep_before_ws'): self._sep_before_ws.setParent(self.island_widget)
        if hasattr(self, '_sep_after_ws'): self._sep_after_ws.setParent(self.island_widget)
        if hasattr(self, '_sep_before_tools'): self._sep_before_tools.setParent(self.island_widget)
        
        # If we had a scroll area previously, hide/remove it
        if hasattr(self, 'compact_scroll_area') and self.compact_scroll_area:
            self.compact_scroll_area.setWidget(None)
            self.compact_scroll_area.deleteLater()
            self.compact_scroll_area = None

        # 2. Clear old layout of island_widget
        if self.island_widget.layout() is not None:
            old_layout = self.island_widget.layout()
            self.clear_layout(old_layout)
            QWidget().setLayout(old_layout)

        # Contents container: holds every fadable island control so the island
        # background can stay while the contents fade during layout changes.
        if getattr(self, 'island_contents', None) is None:
            self.island_contents = QWidget(self.island_widget)
            self.island_contents.setObjectName("islandContents")
            self._island_fade_effect = QGraphicsOpacityEffect(self.island_contents)
            self.island_contents.setGraphicsEffect(self._island_fade_effect)
            self._island_fade_effect.setOpacity(1.0)
        else:
            self.island_contents.setParent(self.island_widget)
            self.island_contents.setGraphicsEffect(self._island_fade_effect)
        if self.island_contents.layout() is not None:
            old_inner = self.island_contents.layout()
            self.clear_layout(old_inner)
            QWidget().setLayout(old_inner)

        island_layout = QVBoxLayout(self.island_widget)
        island_layout.setContentsMargins(0, 0, 0, 0)
        island_layout.setSpacing(0)
        island_layout.addWidget(self.island_contents)

        inner_layout = QVBoxLayout(self.island_contents)
        inner_layout.setContentsMargins(4, 4, 4, 4)
        inner_layout.setSpacing(0)

        # Get accent values
        accent_hex = self.get_accent_color_hex()
        accent_border = self.get_accent_border_color()
        accent_secondary = self.get_accent_secondary_color_hex()
        
        is_dark = getattr(self, 'is_dark_mode', True)
        r, g, b = self.get_accent_rgb()
        
        # Accent-derived dark background components
        dr, dg, db = max(r//6, 8), max(g//6, 8), max(b//6, 8)  # very dark tint
        mr, mg, mb = max(r//4, 14), max(g//4, 14), max(b//4, 14)  # mid dark tint
        
        bg_island = f"rgba({mr},{mg},{mb},215)" if is_dark else "rgba(250, 250, 252, 240)"
        self.island_widget.setStyleSheet(f"""
            QWidget#islandWidget {{
                background-color: {bg_island};
                border-radius: 14px;
                border: none;
            }}
        """)
        
        bg_url_tab = f"rgba({mr},{mg},{mb},215)" if is_dark else "rgba(250, 250, 252, 240)"
        bg_url_input = "transparent" if self.layout_style == "compact" else (f"rgba({dr},{dg},{db},160)" if is_dark else "rgba(230, 230, 235, 200)")
        bg_url_focus = f"rgba({mr},{mg},{mb},200)" if is_dark else "rgba(255, 255, 255, 255)"
        text_color = "#ffffff" if is_dark else "#000000"
        
        tab_unsel_color = "#A9B5CC" if is_dark else "#555566"
        tab_hover_bg = f"rgba({mr+20},{mg+20},{mb+20},122)" if is_dark else "rgba(200, 210, 230, 122)"
        
        sep_color = f"rgba({r},{g},{b},80)" if is_dark else f"rgba({r},{g},{b},120)"
        tab_border_color = f"rgba({dr},{dg},{db},255)" if is_dark else "#d0d0e0"

        if self.layout_style == "compact":
            self.tab_bar.compact_mode = True
            
            # Create a single row layout container
            row_widget = QWidget()
            row_widget.setStyleSheet("background: transparent;")
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(8, 2, 8, 2)
            row_layout.setSpacing(8)
            
            self.bottom_bar = row_widget  # For win32 title bar dragging
            self.app_title_text.hide()
            
            # Unified capsule: [Page Controls + URL Bar + Tab Scroll Area]
            self.unified_url_tab = QWidget()
            self.unified_url_tab.setObjectName("unifiedUrlTab")
            self.unified_url_tab.setStyleSheet(f"""
                QWidget#unifiedUrlTab {{
                    background-color: {bg_url_tab};
                    border: 2px solid {accent_border};
                    border-radius: 15px;
                }}
                QWidget#unifiedUrlTab:hover {{
                    border: 2px solid {accent_hex};
                }}
            """)
            ut_layout = QHBoxLayout(self.unified_url_tab)
            ut_layout.setContentsMargins(8, 2, 8, 2)
            ut_layout.setSpacing(6)
            
            # Add Page Controls to the left of Unified URL/Tab Bar
            btn_style = "QToolButton { background: transparent; border: none; }"
            self.back_btn.setStyleSheet(btn_style)
            self.forward_btn.setStyleSheet(btn_style)
            self.refresh_btn.setStyleSheet(btn_style)
            self.site_info_btn.setStyleSheet(btn_style)
            
            ut_layout.addWidget(self.back_btn)
            ut_layout.addWidget(self.forward_btn)
            ut_layout.addWidget(self.refresh_btn)
            
            # Zoom preview moves out of the URL bar into the page utilities,
            # sitting between the Reload and Site Info buttons.
            self.url_bar.zoom_indicator.setStyleSheet(f"""
                QLabel {{
                    color: {text_color};
                    font-size: 11px; font-weight: 600;
                    background: transparent;
                    border: none;
                    padding: 2px;
                }}
                QLabel:hover {{
                    color: {accent_hex};
                }}
            """)
            ut_layout.addWidget(self.url_bar.zoom_indicator)
            ut_layout.addWidget(self.site_info_btn)
            
            sep2 = QFrame()
            sep2.setFrameShape(QFrame.Shape.VLine)
            sep2.setFixedSize(1, 14)
            sep2.setStyleSheet(f"background: {sep_color}; border: none;")
            ut_layout.addWidget(sep2)
            
            # URL text input (middle)
            self.url_bar.setStyleSheet(f"""
                QLineEdit {{
                    background-color: {bg_url_input};
                    border: none;
                    padding: 4px 12px 4px 12px;
                    color: transparent;
                    font-size: 13px;
                    selection-background-color: {accent_hex};
                }}
                QLineEdit:focus {{
                    color: {text_color};
                }}
            """)
            ut_layout.addWidget(self.url_bar, stretch=1)
            # Compact Tab Scroll Area (right)
            from .core.tabs import CompactTabScrollArea
            self.compact_scroll_area = CompactTabScrollArea(self.tab_bar, self)
            self.tab_bar.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            ut_layout.addWidget(self.compact_scroll_area)
            
            # New Tab Button
            self.new_tab_btn.compact_mode = True
            ut_layout.addWidget(self.new_tab_btn)
            
            # Add to row layout
            row_layout.addWidget(self.unified_url_tab, stretch=1)
            
            # Tools Pill
            tools_pill = QWidget()
            tools_pill.setObjectName("toolsPill")
            tools_pill.setFixedHeight(28)
            tools_pill.setStyleSheet(f"QWidget#toolsPill {{ border: 2px solid {accent_border}; border-radius: 14px; background: transparent; }}")
            tp_layout = QHBoxLayout(tools_pill)
            tp_layout.setContentsMargins(4, 0, 4, 0)
            tp_layout.setSpacing(0)
            
            tp_layout.addWidget(self.home_btn)
            tp_layout.addWidget(self._sep_before_ws)
            tp_layout.addWidget(self.ws_btn)
            tp_layout.addWidget(self._sep_after_ws)
            tp_layout.addWidget(self.printy_btn)
            tp_layout.addWidget(self._sep_before_tools)
            tp_layout.addWidget(self.tools_btn)
            row_layout.addWidget(tools_pill)
            
            # Window controls
            row_layout.addWidget(self.minimize_btn)
            row_layout.addWidget(self.maximize_btn)
            row_layout.addWidget(self.close_btn)
            
            inner_layout.addWidget(row_widget)
            
            # Explicitly show new widgets
            row_widget.show()
            self.unified_url_tab.show()
            self.compact_scroll_area.show()
            tools_pill.show()
            sep2.show()
            
        else:
            self.tab_bar.compact_mode = False
            self.tab_bar.setExpanding(False)
            self.tab_bar.setExpanding(True)
            from PySide6.QtWidgets import QSizePolicy
            self.tab_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self.tab_bar.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self.app_title_text.show()
            
            # Standard layout: two rows
            tab_row = QWidget()
            tab_row.setStyleSheet("background: transparent;")
            tab_row_layout = QHBoxLayout(tab_row)
            tab_row_layout.setContentsMargins(4, 2, 8, 2)
            tab_row_layout.setSpacing(6)
            
            self.tab_bar.setStyleSheet(f"""
                QTabBar {{
                    background: transparent;
                    qproperty-drawBase: 0;
                }}
                QTabBar::tab {{
                    min-width: 60px; max-width: 9999px; min-height: 30px;
                    padding: 0 12px 0 8px; background: transparent; color: {tab_unsel_color};
                    border: none; font-size: 11px;
                }}
                QTabBar::tab:selected {{ background: transparent; color: {text_color}; font-weight: bold; }}
                QTabBar::tab:hover:!selected {{ background: transparent; color: {text_color}; }}
            """)
            tab_row_layout.addWidget(self.tab_bar, stretch=1)
            
            self.new_tab_btn.compact_mode = False
            tab_row_layout.addWidget(self.new_tab_btn, stretch=0)
            
            self.url_bar.setStyleSheet(f"""
                QLineEdit {{
                    background-color: {bg_url_input};
                    border: 2px solid {accent_border};
                    border-radius: 15px;
                    padding: 4px 70px 4px 12px;
                    color: transparent;
                    font-size: 13px;
                    selection-background-color: {accent_hex};
                }}
                UrlLineEdit:focus {{
                    border: 2px solid {accent_hex};
                    background-color: {bg_url_focus};
                    color: {text_color};
                }}
            """)
            
            # Bring the zoom preview back inside the URL bar's right side
            self.url_bar.zoom_indicator.setParent(self.url_bar)
            self.url_bar._layout.addWidget(self.url_bar.zoom_indicator)
            self.url_bar.zoom_indicator.setStyleSheet("color: #8994AB; font-size: 11px; font-weight: 600; background: transparent;")
            
            btn_style = "QToolButton { background: transparent; border: none; }"
            self.back_btn.setStyleSheet(btn_style)
            self.forward_btn.setStyleSheet(btn_style)
            self.refresh_btn.setStyleSheet(btn_style)
            self.site_info_btn.setStyleSheet(btn_style)
            
            nav_pill = QFrame()
            nav_pill.setFixedHeight(30)
            nav_pill.setObjectName("navPill")
            nav_pill.setStyleSheet(f"QFrame#navPill {{ background: transparent; border: 2px solid {accent_secondary}; border-radius: 15px; }}")
            np_layout = QHBoxLayout(nav_pill)
            np_layout.setContentsMargins(2, 0, 2, 0)
            np_layout.setSpacing(0)
            
            sep = QFrame()
            sep.setFixedSize(1, 14)
            sep.setStyleSheet(f"background-color: {accent_border};")
            
            np_layout.addWidget(self.back_btn)
            np_layout.addWidget(sep, 0, Qt.AlignmentFlag.AlignVCenter)
            np_layout.addWidget(self.forward_btn)
            
            nav_container = QFrame()
            nav_container.setStyleSheet("background: transparent;")
            nav_layout = QHBoxLayout(nav_container)
            nav_layout.setContentsMargins(0, 4, 0, 4)
            nav_layout.setSpacing(6)
            nav_layout.addWidget(nav_pill)
            nav_layout.addWidget(self.url_bar)
            nav_layout.addWidget(self.site_info_btn)
            nav_layout.addWidget(self.refresh_btn)
            
            tools_pill = QFrame()
            tools_pill.setObjectName("toolsPill")
            tools_pill.setFixedHeight(28)
            tools_pill.setStyleSheet(f"QFrame#toolsPill {{ border: 2px solid {accent_border}; border-radius: 14px; background: transparent; }}")
            tp_layout = QHBoxLayout(tools_pill)
            tp_layout.setContentsMargins(4, 0, 4, 0)
            tp_layout.setSpacing(0)
            
            tp_layout.addWidget(self.home_btn)
            tp_layout.addWidget(self._sep_before_ws, 0, Qt.AlignmentFlag.AlignVCenter)
            tp_layout.addWidget(self.ws_btn)
            tp_layout.addWidget(self._sep_after_ws, 0, Qt.AlignmentFlag.AlignVCenter)
            tp_layout.addWidget(self.printy_btn)
            tp_layout.addWidget(self._sep_before_tools, 0, Qt.AlignmentFlag.AlignVCenter)
            tp_layout.addWidget(self.tools_btn)
            
            bottom_bar = QFrame()
            bottom_bar.setStyleSheet("QFrame { background-color: transparent; }")
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
            
            inner_layout.addWidget(tab_row)
            inner_layout.addWidget(bottom_bar)
            
            # Explicitly show new widgets
            tab_row.show()
            bottom_bar.show()
            nav_pill.show()
            nav_container.show()
            tools_pill.show()
            sep.show()

        # Explicitly show all core widgets to ensure they remain visible after reparenting
        self.tab_bar.show()
        self.new_tab_btn.show()
        self.url_bar.show()
        self.back_btn.show()
        self.forward_btn.show()
        self.refresh_btn.show()
        self.site_info_btn.show()
        self.home_btn.show()
        self.ws_btn.show()
        self.printy_btn.show()
        self.tools_btn.show()
        self.minimize_btn.show()
        self.maximize_btn.show()
        self.close_btn.show()
        self.island_contents.show()
        
        self.set_ws_btn_visible(self.show_ws_btn)
            
        # Re-register event filters for drag support
        self._install_topbar_drag_filters()
        
        # Force QTabBar to recalculate layout for mode transitions
        self.tab_bar.hide()
        self.tab_bar.show()
        
        # Delay size adjustment and style polish until after layout engine has processed the new widgets
        def _delayed_adjust():
            if hasattr(self, 'url_bar'):
                self.url_bar.style().unpolish(self.url_bar)
                self.url_bar.style().polish(self.url_bar)
                self.url_bar.update()
                
            if self.island_widget.layout():
                self.island_widget.layout().activate()
                
            self.island_widget.adjustSize()

            if getattr(self, '_island_transition_active', False):
                new_h = self.island_widget.height()
                self._start_island_resize(getattr(self, '_transition_old_h', new_h), new_h)
            else:
                # Post-init geometry anchor pass
                if hasattr(self, 'resizeEvent'):
                    # Pass a dummy QResizeEvent or None
                    self.resizeEvent(None)
                
            self.island_widget.updateGeometry()
            
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, _delayed_adjust)

    def load_hovernet_settings(self):
        path = self.get_settings_file_path()
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    self.layout_style = data.get("layout_style", "standard")
                    self.accent_color_name = data.get("accent_color_name", "WS 3.5 Arc")
                    self.browser_theme = data.get("browser_theme", "System")
            except Exception:
                pass
                
    def save_hovernet_settings(self):
        path = self.get_settings_file_path()
        try:
            with open(path, 'w') as f:
                json.dump({
                    "layout_style": self.layout_style,
                    "accent_color_name": self.accent_color_name,
                    "browser_theme": getattr(self, 'browser_theme', "System")
                }, f)
        except Exception:
            pass
            
    def get_settings_file_path(self):
        base_path = os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), "HoverNet") # no fucking way i actually forgot this from the ie variant
        os.makedirs(base_path, exist_ok=True)
        return os.path.join(base_path, "HoverNetSettings.json")

    def get_accent_color_hex(self):
        return self.ACCENT_COLORS.get(self.accent_color_name, self.ACCENT_COLORS["WS 3.5 Arc"])["primary"]
        
    def get_accent_secondary_color_hex(self):
        return self.ACCENT_COLORS.get(self.accent_color_name, self.ACCENT_COLORS["WS 3.5 Arc"])["secondary"]
        
    def get_accent_border_color(self):
        return self.ACCENT_COLORS.get(self.accent_color_name, self.ACCENT_COLORS["WS 3.5 Arc"])["border"]
        
    def get_accent_rgb(self):
        return self.ACCENT_COLORS.get(self.accent_color_name, self.ACCENT_COLORS["WS 3.5 Arc"])["rgb"]
        
    def get_accent_hover_color_hex(self):
        hovers = {
            "WS 3.5 Arc": "#6699FF",
            "Neon Purple": "#C084FC",
            "Emerald Green": "#34D399",
            "Sunset Orange": "#FB923C",
            "Cyberpunk Pink": "#F472B6"
        }
        return hovers.get(self.accent_color_name, "#6699FF")
        
    def set_layout_style(self, style):
        if style in ("standard", "compact"):
            self.layout_style = style
            self.setup_island_layout()
            self.save_hovernet_settings()
            self.refresh_hovernet_pages()

    def set_accent_color(self, name):
        if name in self.ACCENT_COLORS:
            self.accent_color_name = name
            self.apply_browser_theme()
            self.setup_island_layout()
            self.save_hovernet_settings()
            self.refresh_hovernet_pages()

    def set_browser_theme(self, theme):
        if theme in ("Dark", "Light", "System"):
            self.browser_theme = theme
            self.apply_browser_theme()
            self.setup_island_layout()
            self.save_hovernet_settings()
            self.refresh_hovernet_pages()

    def refresh_hovernet_pages(self):
        """Re-apply theme styles to every open hovernet:// page (Settings and
        History views). This is the actual reload step that runs while the
        "Applying changes..." bubble is visible; without it the pages only
        partially switch because they never re-read the new theme."""
        for idx in range(self.browser_area.count()):
            widget = self.browser_area.widget(idx)
            if isinstance(widget, (SettingsView, HistoryView)):
                widget.apply_styles()

    def apply_browser_theme(self):
        theme = getattr(self, 'browser_theme', "System")
        app = QApplication.instance()
        
        from PySide6.QtGui import QPalette, QColor
        from PySide6.QtCore import Qt
        
        is_dark = True
        if theme == "Light":
            is_dark = False
        elif theme == "System":
            try:
                is_dark = app.styleHints().colorScheme() == Qt.ColorScheme.Dark
            except AttributeError:
                is_dark = True
        
        accent_rgb = self.get_accent_rgb()
        r, g, b = accent_rgb
        # Compute accent-tinted dark shades for palette
        dr, dg, db = max(r//6, 8), max(g//6, 8), max(b//6, 8)   # very dark
        mr, mg, mb = max(r//4, 14), max(g//4, 14), max(b//4, 14)  # mid dark
            
        pal = QPalette()
        if is_dark:
            pal.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Window, QColor(dr, dg, db))
            pal.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.WindowText, Qt.white)
            pal.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Base, QColor(mr, mg, mb))
            pal.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Text, Qt.white)
            pal.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Button, QColor(mr+10, mg+10, mb+10))
            pal.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.ButtonText, Qt.white)
        else:
            pal.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Window, QColor(240, 240, 245))
            pal.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.WindowText, Qt.black)
            pal.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Base, Qt.white)
            pal.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Text, Qt.black)
            pal.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Button, QColor(220, 220, 230))
            pal.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.ButtonText, Qt.black)
            pal.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.BrightText, QColor(255, 50, 50))
            
        qcol = QColor(*accent_rgb)
        pal.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Highlight, qcol)
        pal.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Link, qcol)
        pal.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.HighlightedText, Qt.white)
        app.setPalette(pal)
        
        self.is_dark_mode = is_dark
        
        # Enforce dark mode setting on WebEngine
        prof = QWebEngineProfile.defaultProfile()
        prof.settings().setAttribute(QWebEngineSettings.WebAttribute.ForceDarkMode, is_dark)
        
        # Enforce global QMenu styling for context menus (accent-derived)
        menu_bg = f"rgba({max(mr,20)},{max(mg,20)},{max(mb,20)},250)" if is_dark else "#ffffff"
        menu_fg = "#ffffff" if is_dark else "#000000"
        menu_sel = f"rgba({r}, {g}, {b}, 70)"
        menu_border = f"rgba({r//2},{g//2},{b//2},120)" if is_dark else "rgba(200, 200, 200, 100)"
        app.setStyleSheet(f"QMenu {{ background-color: {menu_bg}; color: {menu_fg}; border: 1px solid {menu_border}; border-radius: 6px; padding: 4px; font-size: 13px; }} QMenu::item {{ padding: 6px 20px; border-radius: 4px; }} QMenu::item:selected {{ background: {menu_sel}; }}")
        
        # Update autocomplete dropdown if it exists
        if hasattr(self, '_autocomplete') and self._autocomplete:
            self._autocomplete.update_style()
        
        # Update all open BrowserView page background colors
        from .core.browser import BrowserView
        page_bg = QColor(dr, dg, db) if is_dark else QColor(240, 240, 245)
        if hasattr(self, 'browser_area'):
            for idx in range(self.browser_area.count()):
                w = self.browser_area.widget(idx)
                if isinstance(w, BrowserView):
                    w.page().setBackgroundColor(page_bg)
