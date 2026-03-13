import sys
import math
import os
from urllib.parse import quote_plus
from PyQt5.QtCore import Qt, QUrl, QTimer, QSize, QStringListModel
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabBar, QToolButton, QLineEdit, QListView, QMenu, QStackedWidget,
    QAction, QMessageBox, QFileDialog, QDialog, QLabel, QTextEdit, QPushButton,
    QTabWidget, QCheckBox, QComboBox
)
from PyQt5.QtGui import QFont, QPainter, QColor
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebEngineWidgets import QWebEngineProfile, QWebEngineScript
from PyQt5.QtWebEngineWidgets import QWebEngineDownloadItem  # replacement for DownloadRequest

import subprocess


class CustomTabBar(QTabBar):
    def __init__(self, main_window=None):
        super().__init__(main_window)
        self.main_window = main_window
        self.setMovable(True)
        self.setTabsClosable(True)
        self.tabCloseRequested.connect(self.close_tab)

        # [+] button (square, IE11-like)
        self.plus_button = QToolButton(self)
        self.plus_button.setText("   ")
        self.plus_button.setFixedSize(20, 20)
        self.plus_button.setAutoRaise(False)
        self.plus_button.setStyleSheet("""
            QToolButton {
                border: 0.5px solid #9a9a9a;
                background: #ffffff;
                border-radius: 2px;
                padding: 0px;
            }
            QToolButton:hover { 
                background: #e8f0ff;
                border: 1px solid #6a9aff; 
            }
        """)
        self.plus_button.clicked.connect(self.new_tab_requested)

        # Keep button positioned next to rightmost tab when tabs change / resize
        self.tabMoved.connect(lambda *_: self.update_plus_position())
        self.tabCloseRequested.connect(lambda *_: self.update_plus_position())

        # initial placement
        self.update_plus_position()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_plus_position()

    # override tabInserted/tabRemoved to update plus-button position (these are methods, not signals)
    def tabInserted(self, index):
        try:
            super().tabInserted(index)
        except Exception:
            pass
        self.update_plus_position()

    def tabRemoved(self, index):
        try:
            super().tabRemoved(index)
        except Exception:
            pass
        self.update_plus_position()

    def update_plus_position(self):
        w = self.plus_button.width()
        h = self.plus_button.height()
        count = self.count()
        if count > 0:
            try:
                last_rect = self.tabRect(count - 1)
                x = last_rect.right() + 6
                y = (self.height() - h) // 2
                # ensure it doesn't go past widget bounds
                if x + w > self.width() - 4:
                    x = self.width() - w - 4
            except Exception:
                x = self.width() - w - 4
                y = (self.height() - h) // 2
        else:
            x = 4
            y = (self.height() - h) // 2
        self.plus_button.move(int(x), int(y))

    def new_tab_requested(self):
        if self.main_window:
            self.main_window.add_tab()
        # reposition after a new tab is created
        self.update_plus_position()

    def close_tab(self, index):
        if self.main_window:
            self.main_window.close_tab(index)
        # reposition after a tab is closed
        self.update_plus_position()


class LoadingOverlay(QWidget):
    def __init__(self, parent=None, text="Loading website, please wait..."):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        # block events while visible
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self._text = text
        self._progress = -1  # -1 = hidden, 0-100 otherwise
        self._timer = QTimer(self)
        self._timer.start(100)
        self.hide()

    def set_progress(self, percent):
        self._progress = int(percent) if percent is not None and percent >= 0 else -1
        if self._progress >= 0:
            self._text = f"Loading... {self._progress}%"
            self.show()
            self.raise_()
        else:
            self._text = "Loading website, please wait..."
            self.hide()
        self.update()

    def paintEvent(self, ev):
        # simplified overlay: faint backdrop and centered text (no spinner)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(255, 255, 255))
        painter.setPen(QColor(30, 30, 30))
        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)


class BrowserView(QWebEngineView):
    """QWebEngineView subclass that owns a LoadingOverlay and keeps it sized."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._overlay = LoadingOverlay(self)
        self._overlay.hide()
        # store current load progress for the URL-bar background when switching tabs
        self._load_progress = -1
        # Inject lightweight polyfills (structuredClone + String.replaceAll) at document creation.
        # These are fallbacks for older Chromium builds used by PyQt5; they are limited
        # (structuredClone fallback uses JSON round-trip and won't support functions/circular refs).
        try:
            profile = self.page().profile()
            poly_js = r"""
                (function(){
                if(!window.structuredClone){
                    window.structuredClone = function(obj){
                    try{ return JSON.parse(JSON.stringify(obj)); }catch(e){ return null; }
                    };
                }
                if(!String.prototype.replaceAll){
                    String.prototype.replaceAll = function(search, replace){
                    if(search instanceof RegExp) return this.replace(search, replace);
                    return this.split(String(search)).join(replace);
                    };
                }
                })();
                """
            script = QWebEngineScript()
            script.setName("ie12_polyfills")
            script.setSourceCode(poly_js)
            script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
            script.setRunsOnSubFrames(True)
            # MainWorld makes the polyfills available to page scripts
            script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            profile.scripts().insert(script)
        except Exception:
            # fail silently if the platform/version doesn't support script injection APIs
            pass

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        # ensure overlay covers the whole view
        self._overlay.setGeometry(0, 0, self.width(), self.height())

    def overlay(self):
        return self._overlay


class IEBrowser(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("visualOS Hovernet vIE.12")
        self.resize(1200, 800)

        # Use Calibri font
        app_font = QFont("Calibri", 10)
        self.setFont(app_font)

        # Security / persistence tweaks to reduce fingerprinting and keep cookies/cache
        # (best-effort: sets a modern user-agent, enables disk cache & persistent cookies,
        #  and stores profile data under %APPDATA%/IE12Profile so cookies, localStorage and cache
        #  survive across runs which helps avoid repeated bot/challenge checks)
        try:
            prof = QWebEngineProfile.defaultProfile()
            # Use a generic modern UA string (keeps "QtWebEngine" out of the UA)
            prof.setHttpUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
            # Persist cookies and storage to disk
            prof.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
            base_path = os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), "IE12Profile")
            os.makedirs(base_path, exist_ok=True)
            try:
                prof.setPersistentStoragePath(base_path)
            except Exception:
                pass
            try:
                prof.setCachePath(os.path.join(base_path, "Cache"))
                prof.setHttpCacheType(QWebEngineProfile.DiskHttpCache)
            except Exception:
                pass
        except Exception:
            # non-fatal; continue without profile tweaks
            pass

        # --- Main layout ---
        central = QWidget()
        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.setCentralWidget(central)

        # --- Top bar ---
        top_bar = QWidget()
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(4, 2, 4, 2)
        top_layout.setSpacing(4)

        # Tabs (QTabBar only, no QTabWidget)
        self.tab_bar = CustomTabBar(self)
        self.tab_bar.setFont(app_font)
        self.tab_bar.currentChanged.connect(self.switch_tab)
        self.tab_bar.tabMoved.connect(self.on_tab_moved)
        # Keep tabs at a fixed size and enable scroll buttons when overflowed
        self.tab_bar.setExpanding(False)
        self.tab_bar.setUsesScrollButtons(False)
        self.tab_bar.setElideMode(Qt.TextElideMode.ElideRight)
        # Fixed visual width for each tab so new tabs don't shrink others
        self.tab_bar.setStyleSheet("QTabBar::tab { min-width: 120px; max-width: 120px; }")

        # URL/Search bar
        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("Search or enter web address")
        self.url_bar.returnPressed.connect(self.load_url)
        self.url_bar.setFont(app_font)

        # Navigation buttons: Back (larger) and Forward (smaller)
        self.back_btn = QToolButton()
        self.back_btn.setText("↩")
        self.back_btn.setAutoRaise(True)
        self.back_btn.setEnabled(False)
        # larger circular style for Back
        self.back_btn.setFixedSize(QSize(30, 30))
        self.back_btn.setStyleSheet("""
            QToolButton {
            border: 1px solid #9a9a9a;
            border-radius: 15px;
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 rgba(0,125,255,255), stop:1 rgba(0,75,255,255));
            font-size: 20px;
            font-weight: bold;
            color: white;
            }
            QToolButton:pressed { background: rgba(180,210,255,255); }
            QToolButton:disabled {
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #e0e0e0, stop:1 #bdbdbd);
            color: #a0a0a0;
            }
        """)
        self.back_btn.clicked.connect(self.go_back)

        self.forward_btn = QToolButton()
        self.forward_btn.setText("↪")
        self.forward_btn.setAutoRaise(True)
        self.forward_btn.setEnabled(False)
        # smaller circular style for Forward
        self.forward_btn.setFixedSize(QSize(24, 24))
        self.forward_btn.setStyleSheet("""
            QToolButton {
            border: 1px solid #9a9a9a;
            border-radius: 12px;
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 rgba(0,125,255,255), stop:1 rgba(0,75,255,255));
            font-size: 20px;
            font-weight: bold;
            color: white;
            }
            QToolButton:pressed { background: rgba(200,220,255,255); }
            QToolButton:disabled {
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #e0e0e0, stop:1 #bdbdbd);
            color: #a0a0a0;
            }
        """)
        self.forward_btn.clicked.connect(self.go_forward)

        # Site info button (Certificate status + Cookies)
        self.site_info_btn = QToolButton()
        self.site_info_btn.setText("⇋")
        self.site_info_btn.setAutoRaise(True)
        self.site_info_btn.setFixedSize(QSize(20, 20))
        self.site_info_btn.setStyleSheet("""
            QToolButton {
                border: 1px solid #9a9a9a;
                border-radius: 10px;
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 rgba(235,245,255,255), stop:1 rgba(210,230,255,255));
            }
            QToolButton:pressed { background: rgba(190,215,255,255); }
        """)
        if self._show_site_info:
            self.site_info_btn.setStyleSheet("""
                QToolButton {
                    border: 1px solid #9a9a9a;
                    border-radius: 10px;
                    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 rgba(235,245,255,255), stop:1 rgba(128,255,128,255));
                }
                QToolButton:pressed { background: rgba(122,204,184,255); }
            """)
        if self._show_site_info is None:
            self.site_info_btn.setStyleSheet("""
                QToolButton {
                    border: 1px solid #9a9a9a;
                    border-radius: 10px;
                    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 rgba(235,245,255,255), stop:1 rgba(255,128,128,255));
                }
                QToolButton:pressed { background: rgba(204,102,104,255); }
            """)
        self.site_info_btn.clicked.connect(self._show_site_info)

        # Refresh button (placed in the URL/nav container)
        self.refresh_btn = QToolButton()
        self.refresh_btn.setText("⟳")
        self.refresh_btn.setAutoRaise(True)
        self.refresh_btn.setFixedSize(QSize(26, 26))
        self.refresh_btn.setStyleSheet("""
            QToolButton {
                border: 1px solid #9a9a9a;
                border-radius: 13px;
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 rgba(245,250,255,255), stop:1 rgba(220,235,255,255));
                font-size: 14px;
            }
            QToolButton:pressed { background: rgba(200,220,255,255); }
        """)
        self.refresh_btn.clicked.connect(self.go_refresh)

        # Put nav buttons next to the URL bar so they feel integrated
        # Create a small container for url + nav so layout spacing stays correct
        nav_container = QWidget()
        nav_layout = QHBoxLayout(nav_container)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(6)
        nav_layout.addWidget(self.back_btn)
        nav_layout.addWidget(self.forward_btn)
        nav_layout.addWidget(self.url_bar)
        nav_layout.addWidget(self.site_info_btn)
        nav_layout.addWidget(self.refresh_btn)

        # Right-side buttons
        self.home_btn = QToolButton()
        self.home_btn.setText("Home")
        self.home_btn.clicked.connect(self.go_home)
        self.home_btn.setStyleSheet("""
            QToolButton { background: transparent; border: none; color: black; }
            QToolButton:hover { color: #e53935; font-weight: bold; }
        """)

        self.fav_btn = QToolButton()
        self.fav_btn.setText("Fav")
        self.fav_btn.setStyleSheet("""
            QToolButton { background: transparent; border: none; color: black; }
            QToolButton:hover { color: #FFAB27; font-weight: bold; }
        """)

        self.ws_btn = QToolButton()
        self.ws_btn.setText("WS")
        self.ws_btn.clicked.connect(self.whenthes_space)
        self.ws_btn.setStyleSheet("""
            QToolButton { background: transparent; border: none; color: black; }
            QToolButton:hover { color: #004BFF; font-weight: bold; }
        """)

        self.tools_btn = QToolButton()
        self.tools_btn.setText("Tools    ")
        self.tools_btn.setStyleSheet("""
            QToolButton { background: transparent; border: none; color: black; }
            QToolButton:hover { color: #1976d2; font-weight: bold; }
        """)


        # Build the expanded Extras/Tools menu
        self.tools_menu = QMenu()

        # File submenu (placeholder: Open File)
        act_file = QAction("File", self)
        act_file.triggered.connect(self._act_file)
        self.tools_menu.addAction(act_file)

        # Print
        act_print = QAction("Print...", self)
        act_print.triggered.connect(self._act_print)
        self.tools_menu.addAction(act_print)

        # Zoom submenu
        zoom_menu = QMenu("Zoom", self)
        act_zoom_in = QAction("Zoom In", self)
        act_zoom_in.setShortcut("Ctrl++")
        act_zoom_in.triggered.connect(lambda: self._zoom(1.1))
        zoom_menu.addAction(act_zoom_in)
        act_zoom_out = QAction("Zoom Out", self)
        act_zoom_out.setShortcut("Ctrl+-")
        act_zoom_out.triggered.connect(lambda: self._zoom(1/1.1))
        zoom_menu.addAction(act_zoom_out)
        act_zoom_reset = QAction("Reset Zoom", self)
        act_zoom_reset.setShortcut("Ctrl+0")
        act_zoom_reset.triggered.connect(lambda: self._zoom_reset())
        zoom_menu.addAction(act_zoom_reset)
        self.tools_menu.addMenu(zoom_menu)

        # Safety submenu (placeholder actions)
        safety_menu = QMenu("Safety", self)
        act_delete_history = QAction("Delete browsing history", self)
        act_delete_history.triggered.connect(self._show_delete_history_dialog)
        safety_menu.addAction(act_delete_history)
        self.act_activex_filtering = QAction("ActiveX Filtering", self)
        self.act_activex_filtering.setCheckable(True)
        self.act_activex_filtering.setChecked(False)
        self.act_activex_filtering.triggered.connect(self._toggle_activex_filtering)
        safety_menu.addAction(self.act_activex_filtering)
        self.tools_menu.addMenu(safety_menu)

        # Add site to start menu
        act_pin = QAction("Add site to Start menu", self)
        act_pin.triggered.connect(lambda: QMessageBox.information(self, "Pin site", "This feature is not implemented yet."))
        self.tools_menu.addAction(act_pin)

        # View downloads
        act_downloads = QAction("View downloads", self)
        act_downloads.triggered.connect(self._show_downloads_dialog)
        self.tools_menu.addAction(act_downloads)

        # Manage add-ons
        act_addons = QAction("Manage add-ons", self)
        act_addons.triggered.connect(lambda: QMessageBox.information(self, "Manage add-ons", "This feature is not implemented yet."))
        self.tools_menu.addAction(act_addons)

        # Developer Tools (open DevTools window)
        act_devtools = QAction("Developer Tools", self)
        act_devtools.setShortcut("F12")
        act_devtools.triggered.connect(self._open_devtools_for_current)
        self.tools_menu.addAction(act_devtools)

        # Go to pinned sites
        act_pinned = QAction("Go to pinned sites", self)
        act_pinned.triggered.connect(lambda: QMessageBox.information(self, "Pinned Sites", "This feature is not implemented yet."))
        self.tools_menu.addAction(act_pinned)

        # Separator before settings-ish items
        self.tools_menu.addSeparator()

        # Report website problems (grayed/disabled)
        act_report = QAction("Report website problems", self)
        act_report.setDisabled(True)
        self.tools_menu.addAction(act_report)

        # Internet Options / Settings (already present previously) — keep as final entries
        internet_opts_menu = QMenu("Internet Options", self)
        act_ie_options = QAction("IE Internet Options", self)
        act_ie_options.triggered.connect(self._launch_ie_internet_options)
        internet_opts_menu.addAction(act_ie_options)
        act_hovernet_settings = QAction("HoverNet Settings", self)
        act_hovernet_settings.triggered.connect(self._show_hovernet_settings)
        internet_opts_menu.addAction(act_hovernet_settings)
        self.tools_menu.addMenu(internet_opts_menu)
        act_about = QAction("About HoverNet", self)
        act_about.triggered.connect(lambda: QMessageBox.information(
            self,
            "visualOS HoverNet",
            '<span style="font-size:16px; color:#0078d7;">visualOS HoverNet(wb redesign/IE12)</span>'
            '<br><span style="font-size:12px; color:#000000;">whenthe\'s browser, recreated.</span>'
            '<br><span style="font-size:12px; color:#000000;">HoverNet version IE.12(Internet Explorer 12 fanmade creation)</span>'
            '<br><span style="font-size:12px; color:#000000;">Py3.12.9, Imports: PyQt5(Core, Widgets, Gui, WebEngineWidgets), sys, os, urllib</span>'
        ))
        self.tools_menu.addAction(act_about)

        self.tools_btn.setMenu(self.tools_menu)
        self.tools_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        # Assemble top bar: nav + address bar to the left of tabs
        top_layout.addWidget(nav_container, stretch=2)
        top_layout.addWidget(self.tab_bar, stretch=3)
        top_layout.addWidget(self.home_btn)
        top_layout.addWidget(self.ws_btn)
        top_layout.addWidget(self.fav_btn)
        top_layout.addWidget(self.tools_btn)

        self.main_layout.addWidget(top_bar)

        # --- Browser content area ---
        self.browser_area = QStackedWidget()
        self.main_layout.addWidget(self.browser_area)

        # Start with one tab
        self.add_tab("https://www.google.com")

        # --- Download tracking ---
        self._downloads = []  # List of (filename, status, path)
        QWebEngineProfile.defaultProfile().downloadRequested.connect(self._on_download_requested)
        self._download_path = os.path.expanduser('~')

    def normalize_input(self, text):
        text = (text or "").strip()
        if not text:
            return "https://www.google.com"
        # If contains spaces -> treat as search
        if " " in text:
            return "https://www.google.com/search?q=" + quote_plus(text)
        # If looks like a bare domain or starts with www.
        if text.startswith("www.") or ("." in text and " " not in text):
            if not text.startswith(("http://", "https://")):
                return "http://" + text
            return text
        # Otherwise treat as search
        return "https://www.google.com/search?q=" + quote_plus(text)

    def add_tab(self, url="https://www.google.com"):
        url = self.normalize_input(url)
        browser = BrowserView()
        browser.setUrl(QUrl(url))
        stack_index = self.browser_area.addWidget(browser)
        self.browser_area.setCurrentIndex(stack_index)

        tab_index = self.tab_bar.addTab("New Tab")
        self.tab_bar.setCurrentIndex(tab_index)

        # Keep title and URL in sync with the tab and address bar
        browser.titleChanged.connect(lambda title, browser=browser: self.update_title(title, browser))
        browser.urlChanged.connect(lambda qurl, browser=browser: self.update_url(qurl, browser))
        # loading signals -> update overlay and tab text
        browser.loadStarted.connect(lambda b=browser: self.on_load_started(b))
        browser.loadProgress.connect(lambda p, b=browser: self.on_load_progress(b, p))
        browser.loadFinished.connect(lambda ok, b=browser: self.on_load_finished(b, ok))
        # Keep navigation buttons in sync with this view's history
        try:
            browser.history().canGoBackChanged.connect(lambda enabled, b=browser: self._update_nav_buttons_for(b))
            browser.history().canGoForwardChanged.connect(lambda enabled, b=browser: self._update_nav_buttons_for(b))
        except Exception:
            # older PyQt versions may not expose these signals; fall back to updating on load events
            browser.urlChanged.connect(lambda *_: self._update_nav_buttons_for(browser))
            browser.loadFinished.connect(lambda *_: self._update_nav_buttons_for(browser))

        # If this is the active tab, update the URL bar immediately
        if browser == self.browser_area.currentWidget():
            self.url_bar.setText(browser.url().toString())


    # Loading helpers ----------------------------------------------------
    def on_load_started(self, browser):
        ov = getattr(browser, "overlay", lambda: None)()
        if ov:
            ov.set_progress(0)
            ov.show()
        browser._load_progress = 0
        self.set_urlbar_progress(0)
        idx = self.browser_area.indexOf(browser)
        if idx != -1:
            self.tab_bar.setTabText(idx, "Loading... 0%")

    def on_load_progress(self, browser, percent):
        ov = getattr(browser, "overlay", lambda: None)()
        if ov:
            ov.set_progress(percent)
        browser._load_progress = percent
        # update the URL bar background only if this tab is current
        if browser == self.browser_area.currentWidget():
            self.set_urlbar_progress(percent)
        idx = self.browser_area.indexOf(browser)
        if idx != -1:
            self.tab_bar.setTabText(idx, f"Loading... {percent}%")

    def on_load_finished(self, browser, ok):
        ov = getattr(browser, "overlay", lambda: None)()
        if ov:
            ov.set_progress(-1)
            ov.hide()
        browser._load_progress = -1
        # clear URL bar background if this is the current tab
        if browser == self.browser_area.currentWidget():
            self.set_urlbar_progress(-1)
        idx = self.browser_area.indexOf(browser)
        if idx != -1:
            title = browser.title() or "New Tab"
            self.tab_bar.setTabText(idx, title)

    def set_urlbar_progress(self, percent):
        if percent is None or percent < 0:
            self.url_bar.setStyleSheet("")
            return
        frac = max(0.0, min(1.0, percent / 100.0))
        stop = f"{frac:.3f}"
        self.url_bar.setStyleSheet(f"""
QLineEdit {{
  padding: 3px;
  border: 1px solid #9a9a9a;
  background: qlineargradient(x0:0, y2:0, x2:1, y2:0,
     stop:0 rgba(0,128,0,255),
     stop:{stop} rgba(0,128,0,255),
     stop:{stop} rgba(255,255,255,255),
     stop:1 rgba(255,255,255,255));
}}
""")

    def load_url(self):
        raw = self.url_bar.text()
        url = self.normalize_input(raw)
        cur = self.browser_area.currentWidget()
        if cur:
            cur.setUrl(QUrl(url))

    def update_url(self, q, browser=None):
        if browser == self.browser_area.currentWidget():
            self.url_bar.setText(q.toString())

    def update_title(self, title, browser=None):
        idx = self.browser_area.indexOf(browser)
        if idx != -1:
            self.tab_bar.setTabText(idx, title)

    def close_tab(self, index):
        if self.tab_bar.count() > 1:
            # Remove tab from tab bar
            self.tab_bar.removeTab(index)
            # Remove corresponding widget from stacked widget
            widget = self.browser_area.widget(index)
            self.browser_area.removeWidget(widget)
            widget.deleteLater()
            # Ensure the stacked widget current index follows tab bar current index
            cur = self.tab_bar.currentIndex()
            if cur >= 0:
                self.browser_area.setCurrentIndex(cur)
                self.url_bar.setText(self.browser_area.currentWidget().url().toString())

    def go_home(self):
        cur = self.browser_area.currentWidget()
        if cur:
            cur.setUrl(QUrl("https://www.google.com"))

    def whenthes_space(self):
        cur = self.browser_area.currentWidget()
        if cur:
            cur.setUrl(QUrl("https://www.sites.google.com/view/whenthesspace"))

    def switch_tab(self, index):
        if index >= 0 and index < self.browser_area.count():
            self.browser_area.setCurrentIndex(index)
            cur = self.browser_area.currentWidget()
            if cur:
                self.url_bar.setText(cur.url().toString())
                # restore URL-bar progress visual for the newly selected tab
                prog = getattr(cur, "_load_progress", -1)
                self.set_urlbar_progress(prog)

    def on_tab_moved(self, from_index, to_index):
        # Keep stacked widget in sync with tab bar order
        widget = self.browser_area.widget(from_index)
        if widget is None:
            return
        # Remove and re-insert at new position
        self.browser_area.removeWidget(widget)
        self.browser_area.insertWidget(to_index, widget)
        # Keep the same current tab selected
        cur = self.tab_bar.currentIndex()
        if cur >= 0:
            self.browser_area.setCurrentIndex(cur)

        # update nav buttons whenever the tab order or selection changes
        curw = self.browser_area.currentWidget()
        if curw:
            self._update_nav_buttons_for(curw)

    # navigation helpers ------------------------------------------------
    def _update_nav_buttons_for(self, browser):
        """Enable/disable nav buttons based on the given browser's history.
        Only updates buttons if the browser is the current view."""
        cur = self.browser_area.currentWidget()
        if browser is None or browser != cur:
            return
        try:
            hb = browser.history().canGoBack()
            hf = browser.history().canGoForward()
        except Exception:
            # fallback: assume both disabled if we can't query
            hb = False
            hf = False
        self.back_btn.setEnabled(bool(hb))
        self.forward_btn.setEnabled(bool(hf))

    def go_back(self):
        cur = self.browser_area.currentWidget()
        if cur and cur.history().canGoBack():
            cur.back()

    def go_forward(self):
        cur = self.browser_area.currentWidget()
        if cur and cur.history().canGoForward():
            cur.forward()

    def go_refresh(self):
        cur = self.browser_area.currentWidget()
        if cur:
            cur.reload()

    # helpers for the Tools/Extras menu (were referenced but missing)
    def current_view(self):
        return self.browser_area.currentWidget() if self.browser_area.count() else None

    def _act_file(self):
        QMessageBox.information(self, "File", "File menu: not implemented")

    def _act_print(self):
        cur = self.current_view()
        if not cur:
            QMessageBox.information(self, "Print", "No page to print")
            return
        fn, _ = QFileDialog.getSaveFileName(self, "Print to PDF", "", "PDF files (*.pdf)")
        if not fn:
            return
        try:
            cur.page().printToPdf(fn)
            QMessageBox.information(self, "Print", f"Saved PDF to: {fn}")
        except Exception:
            QMessageBox.information(self, "Print", "Print/Save to PDF not supported on this platform/version")

    def _zoom(self, factor):
        cur = self.current_view()
        if cur:
            cur.setZoomFactor(cur.zoomFactor() * factor)

    def _zoom_reset(self):
        cur = self.current_view()
        if cur:
            cur.setZoomFactor(1.0)

    def _open_devtools_for_current(self):
        cur = self.current_view()
        if not cur:
            QMessageBox.information(self, "Developer Tools", "No active page")
            return
        dev = QWebEngineView()
        dev.setWindowTitle("Developer Tools")
        dev.resize(900, 600)
        try:
            cur.page().setDevToolsPage(dev.page())
            dev.show()
        except Exception:
            QMessageBox.information(self, "Developer Tools", "Unable to open DevTools on this platform/version")
        if not hasattr(self, "_devtools_windows"):
            self._devtools_windows = []
        self._devtools_windows.append(dev)
        dev.destroyed.connect(lambda: self._devtools_windows.remove(dev) if dev in getattr(self, "_devtools_windows", []) else None)

    def _show_site_info(self):
        cur = self.current_view()
        if not cur:
            QMessageBox.information(self, "Site info", "No active page")
            return

        url = cur.url()
        host = url.host() or url.toString()
        scheme = url.scheme().lower()
        secure = (scheme == "https")

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Site information — {host}")
        layout = QVBoxLayout(dlg)

        lbl = QLabel(f"URL: {url.toString()}<br>Connection: {'Secure (HTTPS)' if secure else 'Not secure'}")
        lbl.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(lbl)

        cert_lbl = QLabel("Certificate: " + ("Present (details not available in this build)" if secure else "None"))
        layout.addWidget(cert_lbl)

        layout.addWidget(QLabel("Cookies:"))
        cookies_view = QTextEdit()
        cookies_view.setReadOnly(True)
        cookies_view.setPlainText("Loading...")
        layout.addWidget(cookies_view)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dlg.accept)
        layout.addWidget(btn_close)

        # Try to read cookies via document.cookie (works for same-origin pages)
        try:
            cur.page().runJavaScript("document.cookie", lambda result: _fill_cookies(result, cookies_view))
        except Exception:
            cookies_view.setPlainText("(Unable to retrieve cookies)")

        def _fill_cookies(result, widget):
            if result is None:
                widget.setPlainText("(no cookies or access denied)")
                return
            if isinstance(result, str):
                if not result.strip():
                    widget.setPlainText("(no cookies)")
                    return
                lines = [c.strip() for c in result.split(";") if c.strip()]
                widget.setPlainText("\n".join(lines))
                return
            widget.setPlainText(str(result))

        dlg.setModal(True)
        dlg.resize(420, 300)
        dlg.exec()

    def _launch_ie_internet_options(self):
        # Launch the real Internet Options dialog (inetcpl.cpl)
        try:
            import subprocess
            subprocess.Popen(["control.exe", "/name", "Microsoft.InternetOptions"])
        except Exception:
            QMessageBox.information(self, "Internet Options", "Unable to launch Internet Options dialog.")

    def _show_hovernet_settings(self):
        dlg = HoverNetSettingsDialog(self)
        dlg.exec()

    def _show_delete_history_dialog(self):
        dlg = DeleteHistoryDialog(self)
        dlg.exec()

    def _toggle_activex_filtering(self):
        enabled = self.act_activex_filtering.isChecked()
        msg = "ActiveX Filtering is now {}.".format("enabled" if enabled else "disabled")
        QMessageBox.information(self, "ActiveX Filtering", msg)

    def _on_download_requested(self, download: QWebEngineDownloadItem):
        # Ask user where to save the file, default to _download_path
        suggested = download.downloadFileName() or download.url().fileName() or "downloaded_file"
        default_dir = self._download_path if hasattr(self, '_download_path') else os.path.expanduser('~')
        path, _ = QFileDialog.getSaveFileName(self, "Save File", os.path.join(default_dir, suggested))
        if not path:
            download.cancel()
            return
        folder = os.path.dirname(path)
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)
        filename = os.path.basename(path)
        download.setDownloadDirectory(folder)
        download.setDownloadFileName(filename)
        download.accept()
        entry = {"filename": os.path.basename(path), "status": "Downloading", "path": path, "item": download}
        self._downloads.append(entry)
        download.finished.connect(lambda: self._on_download_finished(entry))
    def _on_download_finished(self, entry):
        entry["status"] = "Completed" if entry["item"].state() == QWebEngineDownloadItem.DownloadState.DownloadCompleted else "Failed"

    def _show_downloads_dialog(self):
        dlg = ViewDownloadsDialog(self._downloads, self)
        dlg.exec()


class HoverNetSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(400, 250)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs)

        tab_themes = QWidget()
        v_themes = QVBoxLayout(tab_themes)
        lbl_warn = QLabel("This setting does not work.")
        lbl_warn.setWordWrap(True)
        v_themes.addWidget(lbl_warn)
        self.chk_night = QCheckBox("Night Mode")
        v_themes.addWidget(self.chk_night)
        v_themes.addStretch(1)
        self.tabs.addTab(tab_themes, "Theme")

        # Account Tab
        tab_account = QWidget()
        v_account = QVBoxLayout(tab_account)
        btn_gmail = QPushButton("G-Mail")
        btn_ms = QPushButton("Microsoft Account")
        v_account.addWidget(btn_gmail)
        v_account.addWidget(btn_ms)
        lbl_acc = QLabel("This setting does not work.")
        lbl_acc.setWordWrap(True)
        v_account.addWidget(lbl_acc)
        v_account.addStretch(1)
        self.tabs.addTab(tab_account, "Account")

        # Tabs Tab
        tab_tabs = QWidget()
        v_tabs = QVBoxLayout(tab_tabs)
        lbl_newtab = QLabel("When a new tab is opened, open")
        v_tabs.addWidget(lbl_newtab)
        self.edit_newtab_url = QLineEdit("https://www.google.com")
        v_tabs.addWidget(self.edit_newtab_url)
        lbl_startup = QLabel("On startup,")
        v_tabs.addWidget(lbl_startup)
        self.combo_startup = QComboBox()
        self.combo_startup.addItems(["Open a new tab", "Continue from last session", "Show a blank page"])  # Add more options if needed
        v_tabs.addWidget(self.combo_startup)
        btn_save = QPushButton("Save Settings(Unavaiable)")
        btn_save.setEnabled(False)
        v_tabs.addWidget(btn_save)
        v_tabs.addStretch(1)
        self.tabs.addTab(tab_tabs, "Tabs")

        tab_wb = QWidget()
        v_wb = QVBoxLayout(tab_wb)
        btn_notes = QPushButton("Release Notes")
        btn_notes.clicked.connect(self.show_release_notes)
        v_wb.addWidget(btn_notes)
        v_wb.addStretch(1)
        self.tabs.addTab(tab_wb, "HoverNet")

        # Downloads Tab
        tab_downloads = QWidget()
        v_downloads = QVBoxLayout(tab_downloads)
        v_downloads.addWidget(QLabel("Default download path:"))
        self.edit_download_path = QLineEdit(getattr(parent, '_download_path', os.path.expanduser('~')))
        btn_browse = QPushButton("Browse...")
        v_downloads.addWidget(self.edit_download_path)
        v_downloads.addWidget(btn_browse)
        v_downloads.addStretch(1)
        self.tabs.addTab(tab_downloads, "Downloads")
        def browse_path():
            path = QFileDialog.getExistingDirectory(self, "Select Download Folder", self.edit_download_path.text())
            if path:
                self.edit_download_path.setText(path)
        btn_browse.clicked.connect(browse_path)
        # Save path on close
        def save_path():
            path = self.edit_download_path.text()
            if path and not os.path.exists(path):
                os.makedirs(path, exist_ok=True)
            if parent is not None:
                parent._download_path = path
        self.accepted.connect(save_path)

    def show_release_notes(self):
        notes = (
            "visualOS HoverNet (WB 2 Release 2, IE Variant)\n"
            "Welcome to the new, redesigned WB, aka HoverNet!\n"
            "i dont have anything new to put here :<"
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("Release Notes")
        layout = QVBoxLayout(dlg)
        lbl = QLabel(notes)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
        btn_close = QPushButton("Close", dlg)
        btn_close.clicked.connect(dlg.accept)
        layout.addWidget(btn_close)
        dlg.setModal(True)
        dlg.resize(400, 300)
        dlg.exec()


class DeleteHistoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Delete Browsing History")
        self.resize(400, 300)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select the items you want to delete:", self))
        self.chk_history = QCheckBox("History")
        self.chk_cookies = QCheckBox("Cookies and website data")
        self.chk_cache = QCheckBox("Cached images and files")
        self.chk_passwords = QCheckBox("Saved passwords")
        self.chk_form = QCheckBox("Form data")
        self.chk_downloads = QCheckBox("Download history")
        for chk in [self.chk_history, self.chk_cookies, self.chk_cache, self.chk_passwords, self.chk_form, self.chk_downloads]:
            layout.addWidget(chk)
        layout.addStretch(1)
        btns = QHBoxLayout()
        btn_delete = QPushButton("Delete")
        btn_cancel = QPushButton("Cancel")
        btn_delete.clicked.connect(self.do_delete)
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_delete)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)
    def do_delete(self):
        # Placeholder: just show a confirmation
        QMessageBox.information(self, "Delete Browsing History", "Selected items deleted (placeholder)")
        self.accept()


class ViewDownloadsDialog(QDialog):
    def __init__(self, downloads, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Downloads")
        self.resize(600, 350)
        self.downloads = downloads
        layout = QVBoxLayout(self)
        self.list = QListView(self)
        self.model = QStringListModel()
        self.update_list()
        self.list.setModel(self.model)
        layout.addWidget(self.list)
        btns = QHBoxLayout()
        self.btn_open = QPushButton("Open File")
        self.btn_folder = QPushButton("Open Folder")
        self.btn_clear = QPushButton("Clear List")
        btns.addWidget(self.btn_open)
        btns.addWidget(self.btn_folder)
        btns.addWidget(self.btn_clear)
        layout.addLayout(btns)
        self.btn_open.clicked.connect(self.open_file)
        self.btn_folder.clicked.connect(self.open_folder)
        self.btn_clear.clicked.connect(self.clear_list)
    def update_list(self):
        items = [f"{d['filename']} - {d['status']}" for d in self.downloads]
        self.model.setStringList(items)
    def open_file(self):
        idx = self.list.currentIndex().row()
        if 0 <= idx < len(self.downloads):
            path = self.downloads[idx]['path']
            if os.path.exists(path):
                os.startfile(path)
            else:
                QMessageBox.warning(self, "Open File", "File does not exist.")
    def open_folder(self):
        idx = self.list.currentIndex().row()
        if 0 <= idx < len(self.downloads):
            path = self.downloads[idx]['path']
            folder = os.path.dirname(path)
            if os.path.exists(folder):
                subprocess.Popen(f'explorer "{folder}"')
            else:
                QMessageBox.warning(self, "Open Folder", "Folder does not exist.")
    def clear_list(self):
        self.downloads.clear()
        self.update_list()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = IEBrowser()
    window.show()
    sys.exit(app.exec())