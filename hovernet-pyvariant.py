import sys
import os
import shutil
import random
import json
from urllib.parse import quote_plus
from PyQt6.QtCore import QStringListModel, Qt, QUrl, QTimer, QSize, QPropertyAnimation, QEasingCurve, QPoint
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt6.QtWidgets import (
    QApplication, QListView, QMainWindow, QTabBar, QToolButton,
    QLineEdit, QHBoxLayout, QWidget, QVBoxLayout, QMenu, QStackedWidget, QMessageBox, QFileDialog, QDialog, QLabel, QTextEdit, QPushButton,
    QTabWidget, QCheckBox, QComboBox, QFrame, QListWidget, QListWidgetItem, QProgressBar
)
from PyQt6.QtGui import QFont, QPainter, QColor, QAction, QIcon
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineScript, QWebEngineProfile, QWebEngineDownloadRequest
import subprocess


class ExpandableAppTitle(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        
        # Title texts
        self.short_text = "HoverNet"
        self.full_text = "visualOS HoverNet - PY Variant"
        
        # Set initial state
        self.setText(self.short_text)
        self.setFixedHeight(24)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setStyleSheet("""
            QLabel {
                background-color: transparent;
                border: none;
                font-size: 12px;
                color: #ffffff;
                padding: 0px;
                margin: 0px;
                font-weight: bold;
            }
        """)
        
        # Animation and timer setup
        self.setFixedWidth(60)  # Start with short width
        self.target_width = 60
        self.is_expanded = False
        self.hover_timer = QTimer()
        self.hover_timer.setSingleShot(True)
        self.hover_timer.timeout.connect(self.expand_title)
        
        self.leave_timer = QTimer()
        self.leave_timer.setSingleShot(True)
        self.leave_timer.timeout.connect(self.contract_title)
        
        # Animation
        self.animation = QPropertyAnimation(self, b"minimumWidth")
        self.animation.setDuration(200)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        # Enable mouse tracking for hover detection
        self.setMouseTracking(True)
    
    def enterEvent(self, event):
        super().enterEvent(event)
        self.hover_timer.start(500)
    
    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.hover_timer.stop()
        if self.is_expanded:
            self.leave_timer.start(500)
    
    def expand_title(self):
        if not self.is_expanded:
            self.is_expanded = True
            self.setText(self.full_text)
            self.animation.setStartValue(60)
            self.animation.setEndValue(180)
            self.animation.start()
    
    def contract_title(self):
        if self.is_expanded:
            self.is_expanded = False
            self.setText(self.short_text)
            self.animation.setStartValue(180)
            self.animation.setEndValue(60)
            self.animation.start()


class NewTabButton(QToolButton):
    """A '+' button that expands into a 'New tab' capsule on hover."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText("+")
        self.setFixedHeight(26)
        self.setFixedWidth(28)
        self._collapsed_width = 28
        self._expanded_width = 90
        self.setAutoRaise(True)
        self._base_style = """
            QToolButton {{
                border: 2px solid #4a4a80;
                border-radius: {r}px;
                padding: 0px 6px;
                color: #aaaacc;
                font-size: 16px;
                font-weight: bold;
                background: transparent;
            }}
            QToolButton:hover {{
                border: 2px solid #7777cc;
                background: #2e2e5a;
                color: #ffffff;
                font-size: 12px;
                font-weight: normal;
            }}
            QToolButton:pressed {{
                background: #3d3d7a;
                color: #ffffff;
            }}
        """
        self._apply_style(collapsed=True)

        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._expand)

        self._leave_timer = QTimer(self)
        self._leave_timer.setSingleShot(True)
        self._leave_timer.timeout.connect(self._collapse)

        self._anim = QPropertyAnimation(self, b"minimumWidth")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._anim_max = QPropertyAnimation(self, b"maximumWidth")
        self._anim_max.setDuration(180)
        self._anim_max.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._expanded = False

    def _apply_style(self, collapsed=True):
        r = 13 if collapsed else 13
        self.setStyleSheet(self._base_style.format(r=r))

    def enterEvent(self, event):
        super().enterEvent(event)
        self._leave_timer.stop()
        self._hover_timer.start(300)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._hover_timer.stop()
        if self._expanded:
            self._leave_timer.start(250)

    def _expand(self):
        if not self._expanded:
            self._expanded = True
            self.setText("+ New tab")
            for anim, prop in ((self._anim, b"minimumWidth"), (self._anim_max, b"maximumWidth")):
                anim.setStartValue(self.width())
                anim.setEndValue(self._expanded_width)
                anim.start()

    def _collapse(self):
        if self._expanded:
            self._expanded = False
            self.setText("+")
            for anim, prop in ((self._anim, b"minimumWidth"), (self._anim_max, b"maximumWidth")):
                anim.setStartValue(self.width())
                anim.setEndValue(self._collapsed_width)
                anim.start()


class CustomTabBar(QTabBar):
    def __init__(self, main_window=None):
        super().__init__(main_window)
        self.main_window = main_window
        self.setMovable(True)
        self.setTabsClosable(True)
        self.tabCloseRequested.connect(self.close_tab)

    def _load_icon(self, name, theme="dark"):
        """Load themed icons with alt fallback.
        name = base name (e.g. 'close', 'maximize', 'minimize')
        theme = 'dark' or 'light'
        """
        if not self._assets_root:
            return None
        root = os.path.join(self._assets_root, "icons")

        candidates = [
            f"{name}-{theme}.png",
            f"{name}-alt-{theme}.png",
            f"{name}-{('light' if theme=='dark' else 'dark')}.png",
            f"{name}-alt-{('light' if theme=='dark' else 'dark')}.png",
        ]
        for fn in candidates:
            path = os.path.join(root, fn)
            if os.path.exists(path):
                return QIcon(path)
        return None

    def new_tab_requested(self):
        if self.main_window:
            self.main_window.add_tab()

    def close_tab(self, index):
        if self.main_window:
            self.main_window.close_tab(index)


class BrowserView(QWebEngineView):
    """QWebEngineView subclass that tracks load progress for the URL bar."""
    def __init__(self, parent=None):
        super().__init__(parent)
        # store current load progress for the URL-bar background when switching tabs
        self._load_progress = -1

        # Match the app's dark background so blank/loading pages aren't a white void
        self.page().setBackgroundColor(QColor("#1E1E3C"))
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


class AutocompleteDropdown(QListWidget):
    """Floating suggestion list that appears below the URL bar."""

    def __init__(self, url_bar, parent_window):
        super().__init__(parent_window, )
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.url_bar = url_bar
        self.parent_window = parent_window

        self.setStyleSheet("""
            QListWidget {
                background: #1a1a3a;
                border: 1px solid #333366;
                border-radius: 6px;
                color: #ddddff;
                font-size: 12px;
                outline: none;
            }
            QListWidget::item {
                padding: 5px 10px;
                border: none;
            }
            QListWidget::item:selected {
                background: #2e2e60;
                color: #ffffff;
            }
            QListWidget::item:hover {
                background: #252550;
            }
        """)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.itemClicked.connect(self._on_item_clicked)

        self._nam = QNetworkAccessManager(self)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(200)
        self._debounce.timeout.connect(self._fetch)
        self._current_reply = None

        # Watch url_bar text changes
        self.url_bar.textEdited.connect(self._on_text_edited)
        self.url_bar.installEventFilter(self)

    def _on_text_edited(self, text):
        text = text.strip()
        if not text or text.startswith(("http://", "https://", "about:", "file://")):
            self.hide()
            return
        self._debounce.start()

    def _fetch(self):
        query = self.url_bar.text().strip()
        if not query:
            self.hide()
            return
        # Google suggest — client=firefox returns a clean JSON array, no auth needed
        url = QUrl(f"https://suggestqueries.google.com/complete/search?client=firefox&q={QUrl.toPercentEncoding(query).data().decode()}")
        req = QNetworkRequest(url)
        req.setRawHeader(b"User-Agent", b"Mozilla/5.0")
        if self._current_reply:
            try:
                self._current_reply.abort()
            except Exception:
                pass
        self._current_reply = self._nam.get(req)
        self._current_reply.finished.connect(self._on_reply)

    def _on_reply(self):
        reply = self._current_reply
        if not reply:
            return
        try:
            raw = bytes(reply.readAll())
            data = json.loads(raw.decode("utf-8"))
            suggestions = data[1] if len(data) > 1 else []
        except Exception:
            suggestions = []
        finally:
            reply.deleteLater()
            self._current_reply = None

        self.clear()
        for s in suggestions[:8]:
            self.addItem(QListWidgetItem(s))

        if self.count() == 0:
            self.hide()
            return

        self._reposition()
        self.show()
        self.raise_()

    def _reposition(self):
        bar = self.url_bar
        pos = bar.mapToGlobal(QPoint(0, bar.height()))
        self.move(pos)
        self.setFixedWidth(bar.width())
        row_h = self.sizeHintForRow(0) if self.count() > 0 else 28
        self.setFixedHeight(min(self.count(), 8) * (row_h + 2) + 6)

    def _on_item_clicked(self, item):
        self.url_bar.setText(item.text())
        self.hide()
        self.parent_window.load_url()

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if not hasattr(self, 'url_bar'):
            return super().eventFilter(obj, event)
        if obj is self.url_bar:
            if event.type() == QEvent.Type.FocusOut:
                # Delay hide so click on item registers first
                QTimer.singleShot(150, self._maybe_hide)
            elif event.type() == QEvent.Type.KeyPress:
                key = event.key()
                if key == Qt.Key.Key_Down and self.count():
                    cur = self.currentRow()
                    self.setCurrentRow(min(cur + 1, self.count() - 1))
                    return True
                elif key == Qt.Key.Key_Up and self.count():
                    cur = self.currentRow()
                    self.setCurrentRow(max(cur - 1, 0))
                    return True
                elif key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
                    if self.isVisible() and self.currentItem():
                        self._on_item_clicked(self.currentItem())
                        return True
                elif key == Qt.Key.Key_Escape:
                    self.hide()
                    return True
        return super().eventFilter(obj, event)

    def _maybe_hide(self):
        if not self.underMouse():
            self.hide()


class DownloadBubble(QWidget):
    """Floating bubble anchored to the Tools button showing active download progress."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._entries = {}  # download item -> {widgets}

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 10, 14, 10)
        self._layout.setSpacing(8)

        self._no_downloads = QLabel("No active downloads")
        self._no_downloads.setStyleSheet("color: #7777aa; font-size: 11px; background: transparent;")
        self._no_downloads.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._no_downloads)

    def _fmt_size(self, bytes_val):
        if bytes_val <= 0:
            return "?"
        for unit in ("B", "KB", "MB", "GB"):
            if bytes_val < 1024:
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= 1024
        return f"{bytes_val:.1f} GB"

    def add_download(self, download, filename):
        """Register a new download and wire up its progress signals."""
        if download in self._entries:
            return

        row = QWidget()
        row.setStyleSheet("background: transparent;")
        rl = QVBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(2)

        # Top row: filename + X cancel button
        top_row = QWidget()
        top_row.setStyleSheet("background: transparent;")
        trl = QHBoxLayout(top_row)
        trl.setContentsMargins(0, 0, 0, 0)
        trl.setSpacing(4)

        name_lbl = QLabel(filename)
        name_lbl.setStyleSheet("color: #ddddff; font-size: 11px; font-family: Consolas, monospace; background: transparent;")
        name_lbl.setMaximumWidth(220)

        cancel_btn = QToolButton()
        cancel_btn.setText("✕")
        cancel_btn.setFixedSize(16, 16)
        cancel_btn.setStyleSheet("""
            QToolButton {
                background: transparent;
                border: none;
                color: #6666aa;
                font-size: 10px;
            }
            QToolButton:hover { color: #ff5555; }
        """)
        cancel_btn.clicked.connect(lambda: self._cancel_download(download))

        trl.addWidget(name_lbl)
        trl.addStretch(1)
        trl.addWidget(cancel_btn)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(6)
        bar.setStyleSheet("""
            QProgressBar {
                background: #2a2a50;
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background: #5566ff;
                border-radius: 3px;
            }
        """)

        info_lbl = QLabel("0% — ? / ?")
        info_lbl.setStyleSheet("color: #8888bb; font-size: 10px; font-family: Consolas, monospace; background: transparent;")

        rl.addWidget(top_row)
        rl.addWidget(bar)
        rl.addWidget(info_lbl)

        self._entries[download] = {"row": row, "bar": bar, "info": info_lbl, "cancel_btn": cancel_btn}
        self._no_downloads.setVisible(False)
        self._layout.insertWidget(self._layout.count(), row)

        download.receivedBytesChanged.connect(lambda: self._on_progress(download))
        download.stateChanged.connect(lambda state, d=download: self._on_finished(d) if d.isFinished() else None)

        self._reposition()
        self.adjustSize()
        self.show()
        self.raise_()

    def _cancel_download(self, download):
        try:
            download.cancel()
        except Exception:
            pass
        self._on_finished(download)

    def _on_progress(self, download):
        entry = self._entries.get(download)
        if not entry:
            return
        received = download.receivedBytes()
        total = download.totalBytes()
        pct = int(received / total * 100) if total > 0 else 0
        entry["bar"].setValue(pct)
        entry["info"].setText(f"{pct}% — {self._fmt_size(received)} / {self._fmt_size(total)}")
        self.adjustSize()

    def _on_finished(self, download):
        entry = self._entries.pop(download, None)
        if entry:
            entry["row"].deleteLater()
        if not self._entries:
            self._no_downloads.setVisible(True)
            # Auto-hide 2s after last download finishes
            QTimer.singleShot(2000, self.hide)
        self.adjustSize()

    def _reposition(self):
        anchor = getattr(self, '_anchor', None)
        if not anchor:
            return
        global_pos = anchor.mapToGlobal(QPoint(anchor.width() // 2, anchor.height()))
        self.adjustSize()
        x = global_pos.x() - self.width() // 2
        y = global_pos.y() + 6
        self.move(x, y)

    def set_anchor(self, widget):
        self._anchor = widget

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        from PyQt6.QtCore import QRectF
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(QColor(28, 28, 58, 240))
        painter.setPen(QColor(80, 80, 160, 200))
        painter.drawRoundedRect(QRectF(rect), 10, 10)


class UpdateBubble(QWidget):
    """Floating bubble that appears below the P button announcing a new PY release."""

    RELEASES_URL = "https://api.github.com/repos/whenthe-washere/visualos-hovernet/releases"
    RELEASES_PAGE = "https://github.com/whenthe-washere/visualos-hovernet/releases"

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(280)
        self._label.setStyleSheet("""
            QLabel {
                color: #e0e0ff;
                font-family: Consolas, monospace;
                font-size: 11px;
                background: transparent;
            }
        """)
        layout.addWidget(self._label)

        self._btn = QPushButton("View on GitHub →")
        self._btn.setStyleSheet("""
            QPushButton {
                background: #2e2e60;
                color: #aaaaff;
                border: 1px solid #5555aa;
                border-radius: 4px;
                font-size: 10px;
                padding: 3px 10px;
            }
            QPushButton:hover { background: #3a3a80; color: #ffffff; }
            QPushButton:pressed { background: #222244; }
        """)
        self._btn.clicked.connect(self._open_releases)
        layout.addWidget(self._btn)

    def _open_releases(self):
        import subprocess
        try:
            subprocess.Popen(["start", "", self.RELEASES_PAGE], shell=True)
        except Exception:
            pass

    def show_update(self, latest_tag, anchor_widget):
        self._label.setText(f'update("{latest_tag} is available!")')
        self.adjustSize()
        global_pos = anchor_widget.mapToGlobal(QPoint(anchor_widget.width() // 2, anchor_widget.height()))
        x = global_pos.x() - self.width() // 2
        y = global_pos.y() + 6
        self.move(x, y)
        self.show()
        self.raise_()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        from PyQt6.QtCore import QRectF
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(QColor(28, 28, 58, 240))
        painter.setPen(QColor(80, 80, 160, 200))
        painter.drawRoundedRect(QRectF(rect), 10, 10)


class PrintyBubble(QWidget):
    """Floating bubble that appears below the P button showing print("of the day!")."""

    _SENTENCES = [
        "Have you tried turning it off and on again?",
        "The mitochondria is the powerhouse of the cell.",
        "I am a banana.",
        "Do you ever just stare at code until it makes sense? No? Just me?",
        "All your base are belong to us.",
        "The FitnessGram™ Pacer Test is a multistage aerobic capacity test that progressively gets more difficult as it continues. The 20 meter pacer test will begin in 30 seconds. Line up at the start. The running speed starts slowly, but gets faster each minute after you hear this signal. [BEEP] A single lap should be completed each time you hear this sound. Remember to run in a straight line, and run as long as possible. The second time you fail to complete a lap before the sound, your test is over. The test will begin on the word start. On your mark, get ready, start. [BEEP]",
        "Error 404: I forgot what the fuck was I supposed to say.",
        "Why do they call it oven when you of in the cold food of out hot eat the food?",
        "Touch grass. Or don't. I'm a browser, not your mum.",
        "Certified HoverNet moment.",
        "This sentence is definitely not filler content.",
        "Loading personality... please wait... just kidding, I have plenty.",
        "визуалОС HoverNet — сейчас в твоём браузере. (dev note: i have no idea why this is one of the generateable dialogues)",
        "fun fact: this message was generated by an AI inside a browser inside a computer. layers.",
        "you are valid. also please clear your cache.",
        "Today's forecast: partly cloudy with a chance of unhandled exceptions.",
        "Imagine if browsers loaded this fast in 2003.",
        "Some people use bookmarks. However, this browser doesn't give that option for the sole purpose of torturing you.",
        "me when I hover on the net\nnet: dude what the fuck\nme: what dude im js hovering on you",
        "nuh uh",
        "me when i uhhhhhhhhhhhhhh <insert joke here>",
        "for legal reasons I cannot say this line."
    ]

    _WORDS = [
        "miku",
        "teto",
        "neru",
        "serendipity",
        "quokka",
        "mewheni_handshakewiththetcp",
        "void",
        "amogus",
        "Goku",
        "ligma",
        "gus",
        "mogus",
        "HoverNet",
        "NullPointerException",
        "Minecraft",
        "existentialism",
        "gigachad",
        "bureaucracy",
        "skibidi",
        "RAM",
        "404",
        "touchgrass.exe",
        "bomboclat",
    ]

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._mode = "Random"
        self._text = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(340)
        self._label.setStyleSheet("""
            QLabel {
                color: #e0e0ff;
                font-family: Consolas, monospace;
                font-size: 11px;
                background: transparent;
            }
        """)
        layout.addWidget(self._label)

    def _pick(self):
        mode = self._mode
        if mode == "Sentence":
            return random.choice(self._SENTENCES)
        elif mode == "Word":
            return random.choice(self._WORDS)
        else:
            return random.choice(self._SENTENCES if random.random() < 0.5 else self._WORDS)

    def regenerate(self):
        self._text = self._pick()
        self._label.setText(f'print("{self._text}")')
        self.adjustSize()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        # Shadow-ish dark fill
        painter.setBrush(QColor(28, 28, 58, 240))
        painter.setPen(QColor(80, 80, 160, 200))
        from PyQt6.QtCore import QRectF
        painter.drawRoundedRect(QRectF(rect), 10, 10)

    def show_below(self, anchor_widget):
        """Position bubble below the anchor widget and show it."""
        self.regenerate()
        global_pos = anchor_widget.mapToGlobal(
            QPoint(anchor_widget.width() // 2, anchor_widget.height())
        )
        self.adjustSize()
        x = global_pos.x() - self.width() // 2
        y = global_pos.y() + 6
        self.move(x, y)
        self.show()
        self.raise_()


class HoverNetPY(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("visualOS HoverNet - PY Variant")
        self.resize(1200, 800)
        
        self.use_custom_title_bar = False
        app_font = QFont("Segoe UI", 10)
        self.setFont(app_font)

        # Security / persistence tweaks to reduce fingerprinting and keep cookies/cache
        # (best-effort: sets a modern user-agent, enables disk cache & persistent cookies,
        #  and stores profile data under %APPDATA%/IE12Profile so cookies, localStorage and cache
        #  survive across runs which helps avoid repeated bot/challenge checks)
        try:
            prof = QWebEngineProfile.defaultProfile()
            # Use a generic modern UA string (keeps "QtWebEngine" out of the UA)
            prof.setHttpUserAgent(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36"
            )
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

        # --- Top bar (includes title bar elements) ---
        top_bar = QWidget()
        top_bar.setStyleSheet("""
            QWidget {
                background-color: #1E1E3C;
            }
        """)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(8, 4, 8, 4)
        top_layout.setSpacing(8)
        self.top_bar = top_bar
        
        # App title (left side) - expandable on hover
        self.app_title_text = ExpandableAppTitle(self)
        
        # Window buttons (right side)
        self.minimize_btn = QPushButton("–")
        self.minimize_btn.setFixedSize(36, 26)
        self.minimize_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                font-size: 24px;
            }
            QPushButton:hover {
                color: #00CC52;
                border-radius: 3px;
            }
            QPushButton:pressed {
                color: #00993D;
                font-weight: bold;
            }
        """)
        self.minimize_btn.clicked.connect(self.minimize_window)
        
        self.maximize_btn = QPushButton("<>")
        self.maximize_btn.setFixedSize(36, 26)
        self.maximize_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                font-size: 16px;
            }
            QPushButton:hover {
                color: #3374FF;
                border-radius: 3px;
            }
            QPushButton:pressed {
                color: #6696FF;
                font-weight: bold;
            }
        """)
        self.maximize_btn.clicked.connect(self.maximize_window)
        
        self.close_btn = QPushButton("X")
        self.close_btn.setFixedSize(36, 26)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                font-size: 16px;
            }
            QPushButton:hover {
                color: #FF3333;
                border-radius: 3px;
            }
            QPushButton:pressed {
                color: #FF6666;
                font-weight: bold;
            }
        """)
        self.close_btn.clicked.connect(self.close_window)

        # Tabs (QTabBar only, no QTabWidget) — Safari-style full-width expanding tabs
        self.tab_bar = CustomTabBar(self)
        self.tab_bar.setFont(app_font)
        self.tab_bar.currentChanged.connect(self.switch_tab)
        self.tab_bar.tabMoved.connect(self.on_tab_moved)
        # Expanding=True makes all tabs share available width equally (Safari behaviour)
        self.tab_bar.setExpanding(True)
        self.tab_bar.setUsesScrollButtons(False)
        self.tab_bar.setElideMode(Qt.TextElideMode.ElideRight)
        self.tab_bar.setIconSize(QSize(16, 16))
        # Only enforce a minimum height; width is distributed automatically
        self.tab_bar.setStyleSheet("""
            QTabBar::tab {
                min-width: 60px;
                max-width: 9999px;
                min-height: 30px;
                padding: 0 12px 0 8px;
                background: #2a2a50;
                color: #aaaacc;
                border: none;
                border-right: 1px solid #1a1a38;
                border-radius: 0px;
                font-size: 11px;
            }
            QTabBar::tab:selected {
                background: #1E1E3C;
                color: #ffffff;
                font-weight: bold;
                border-bottom: 2px solid #5566ff;
            }
            QTabBar::tab:hover:!selected {
                background: #33335a;
                color: #ddddff;
            }
            QTabBar::close-button {
                subcontrol-position: right;
            }
        """)

        # URL/Search bar
        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("Search or enter web address")
        self.url_bar.returnPressed.connect(self.load_url)
        self.url_bar.setFont(app_font)
        # Autocomplete dropdown — attached after window is fully built
        self._autocomplete = None  # initialised below after layout is ready

        # Navigation buttons: merged into a single pill/capsule
        BTN_H = 30
        nav_pill = QWidget()
        nav_pill.setFixedHeight(BTN_H)
        nav_pill.setStyleSheet("""
            QWidget#navPill {
                background: transparent;
                border: 2px solid #0050FF;
                border-radius: 15px;
            }
        """)
        nav_pill.setObjectName("navPill")

        _pill_layout = QHBoxLayout(nav_pill)
        _pill_layout.setContentsMargins(2, 0, 2, 0)
        _pill_layout.setSpacing(0)

        _btn_style = """
            QToolButton {{
                background: transparent;
                border: none;
                border-radius: 0px;
                font-size: {fs}px;
                font-weight: bold;
                color: {col};
                padding: 0 6px;
                min-width: {mw}px;
            }}
            QToolButton:pressed  {{ color: #ffffff; }}
            QToolButton:disabled {{ color: #444466; }}
        """

        self.back_btn = QToolButton()
        self.back_btn.setText("↩")
        self.back_btn.setAutoRaise(True)
        self.back_btn.setEnabled(False)
        self.back_btn.setFixedHeight(BTN_H - 4)
        self.back_btn.setStyleSheet(_btn_style.format(fs=18, col="#0050FF", mw=28))
        self.back_btn.clicked.connect(self.go_back)

        # Semi-transparent separator painted as a thin QFrame
        _sep = QFrame()
        _sep.setFrameShape(QFrame.Shape.VLine)
        _sep.setFixedWidth(1)
        _sep.setFixedHeight(BTN_H - 10)
        _sep.setStyleSheet("QFrame { background: rgba(100,120,255,120); border: none; }")

        self.forward_btn = QToolButton()
        self.forward_btn.setText("↪")
        self.forward_btn.setAutoRaise(True)
        self.forward_btn.setEnabled(False)
        self.forward_btn.setFixedHeight(BTN_H - 4)
        self.forward_btn.setStyleSheet(_btn_style.format(fs=16, col="#0050FF", mw=24))
        self.forward_btn.clicked.connect(self.go_forward)

        _pill_layout.addWidget(self.back_btn)
        _pill_layout.addWidget(_sep, 0, Qt.AlignmentFlag.AlignVCenter)
        _pill_layout.addWidget(self.forward_btn)

        # Site info button (Certificate status + Cookies)
        self.site_info_btn = QToolButton()
        self.site_info_btn.setText("⇋")
        self.site_info_btn.setAutoRaise(True)
        self.site_info_btn.setFixedSize(QSize(24, 24))
        self.site_info_btn.setStyleSheet("""
            QToolButton {
                border: 2px solid #9a9a9a;
                border-radius: 12px;
            }
            QToolButton:pressed { background: rgba(190,215,255,255); }
        """)
        if self._show_site_info:
            self.site_info_btn.setText("⇌")
            self.site_info_btn.setStyleSheet("""
                QToolButton {
                    border: 2px solid #3C993C;
                    border-radius: 12px;
                    color: #3C993C;
                }
                QToolButton:pressed { border: 2px solid #ffffff; color: white; }
            """)
        if self._show_site_info is None:
            self.site_info_btn.setText("✕")
            self.site_info_btn.setStyleSheet("""
                QToolButton {
                    border: 2px solid #9a9a9a;
                    border-radius: 12px;
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
            color: #0050FF; 
            border: 2px solid #0050FF; 
            border-radius: 13px;
            }
            QToolButton:pressed { 
            color: #FFFFFF; 
            border: 2px solid #FFFFFF; 
            }
        """)
        self.refresh_btn.clicked.connect(self.go_refresh)

        # Put nav buttons next to the URL bar so they feel integrated
        # Create a small container for url + nav so layout spacing stays correct
        nav_container = QWidget()
        nav_layout = QHBoxLayout(nav_container)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(6)
        nav_layout.addWidget(nav_pill)
        nav_layout.addWidget(self.url_bar)
        nav_layout.addWidget(self.site_info_btn)
        nav_layout.addWidget(self.refresh_btn)
        self.nav_container = nav_container

        # --- Tools pill: Home | WS | Tools ▾ ---
        # WS button visibility is driven by self.show_ws_btn (default True)
        self.show_ws_btn = True

        tools_pill = QWidget()
        tools_pill.setObjectName("toolsPill")
        tools_pill.setFixedHeight(28)
        tools_pill.setStyleSheet("""
            QWidget#toolsPill {
                border: 2px solid #333366;
                border-radius: 14px;
                background: transparent;
            }
        """)
        _tpill_layout = QHBoxLayout(tools_pill)
        _tpill_layout.setContentsMargins(4, 0, 4, 0)
        _tpill_layout.setSpacing(0)

        _pill_btn_style = """
            QToolButton {{
                background: transparent;
                border: none;
                color: {col};
                font-size: 11px;
                padding: 0 7px;
                min-height: 24px;
            }}
            QToolButton:hover {{ color: {hover}; font-weight: bold; }}
            QToolButton:pressed {{ color: #ffffff; }}
            QToolButton::menu-indicator {{ width: 0; height: 0; image: none; }}
        """
        _pill_sep_style = "QFrame { background: rgba(80,80,160,140); border: none; }"

        def _make_pill_sep():
            s = QFrame()
            s.setFrameShape(QFrame.Shape.VLine)
            s.setFixedWidth(1)
            s.setFixedHeight(16)
            s.setStyleSheet(_pill_sep_style)
            return s

        self.home_btn = QToolButton()
        self.home_btn.setText("Home")
        self.home_btn.clicked.connect(self.go_home)
        self.home_btn.setStyleSheet(_pill_btn_style.format(col="#ccccee", hover="#e53935"))

        self.ws_btn = QToolButton()
        self.ws_btn.setText("WS")
        self.ws_btn.clicked.connect(self.whenthes_space)
        self.ws_btn.setStyleSheet(_pill_btn_style.format(col="#ccccee", hover="#4488ff"))

        self.tools_btn = QToolButton()
        self.tools_btn.setText("Tools")
        self.tools_btn.setStyleSheet(_pill_btn_style.format(col="#ccccee", hover="#1976d2") + """
            QToolButton::menu-indicator { image: none; width: 0; }
        """)
        self.tools_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)

        self._sep_before_ws   = _make_pill_sep()
        self._sep_after_ws    = _make_pill_sep()
        self._sep_before_p    = _make_pill_sep()
        self._sep_before_tools = _make_pill_sep()

        self.printy_btn = QToolButton()
        self.printy_btn.setText("P")
        self.printy_btn.setStyleSheet(_pill_btn_style.format(col="#ccccee", hover="#cc88ff"))
        self.printy_btn.clicked.connect(self._toggle_printy_bubble)

        _tpill_layout.addWidget(self.home_btn)
        _tpill_layout.addWidget(self._sep_before_ws, 0, Qt.AlignmentFlag.AlignVCenter)
        _tpill_layout.addWidget(self.ws_btn)
        _tpill_layout.addWidget(self._sep_after_ws, 0, Qt.AlignmentFlag.AlignVCenter)
        _tpill_layout.addWidget(self.printy_btn)
        _tpill_layout.addWidget(self._sep_before_tools, 0, Qt.AlignmentFlag.AlignVCenter)
        _tpill_layout.addWidget(self.tools_btn)

        self._tools_pill = tools_pill
        self._printy_bubble = PrintyBubble(self)
        self._printy_bubble.hide()


        # Build the expanded Extras/Tools menu
        self.tools_menu = QMenu()

        # File submenu (placeholder: Open File)
        act_file = QAction("File", self)
        act_file.triggered.connect(self._act_file)
        self.tools_menu.addAction(act_file)

        # Zoom submenu
        zoom_menu = QMenu("Zoom", self)
        act_zoom_in = QAction("Zoom In", self)
        act_zoom_in.setShortcut("[Ctrl] + [+]")
        act_zoom_in.triggered.connect(lambda: self._zoom(1.1))
        zoom_menu.addAction(act_zoom_in)
        act_zoom_out = QAction("Zoom Out", self)
        act_zoom_out.setShortcut("[Ctrl] + [-]")
        act_zoom_out.triggered.connect(lambda: self._zoom(1/1.1))
        zoom_menu.addAction(act_zoom_out)
        act_zoom_reset = QAction("Reset Zoom", self)
        act_zoom_reset.setShortcut("[Ctrl] + [0]")
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


        act_downloads = QAction("Download History", self)
        act_downloads.triggered.connect(self._show_downloads_dialog)
        self.tools_menu.addAction(act_downloads)

        act_addons = QAction("Extensions", self)
        act_addons.setDisabled(True)
        act_addons.triggered.connect(lambda: QMessageBox.information(self, "Manage add-ons", "This feature is not implemented yet."))
        self.tools_menu.addAction(act_addons)

        # Developer Tools (open DevTools window)
        act_devtools = QAction("Developer Tools", self)
        act_devtools.setShortcut("F12")
        act_devtools.triggered.connect(self._open_devtools_for_current)
        self.tools_menu.addAction(act_devtools)

        # Separator before settings-ish items
        self.tools_menu.addSeparator()

        # Internet Options / Settings (already present previously) — keep as final entries
        act_hovernet_settings = QAction("HoverNet Settings", self)
        act_hovernet_settings.triggered.connect(self._show_hovernet_settings)
        self.tools_menu.addAction(act_hovernet_settings)

        act_about = QAction("About HoverNet", self)
        act_about.triggered.connect(lambda: QMessageBox.information(
            self,
            "visualOS HoverNet",
            '<span style="font-size:16px; color:#0078d7;">visualOS HoverNet(wb redesign/PY)</span>'
            '<br><span style="font-size:12px;">whenthe\'s browser, recreated.</span>'
            '<br><span style="font-size:12px;">Version: 2(PY: Python Variant)</span>'
            '<br><span style="font-size:12px;">Python Version: 3.12.9</span>'
            '<br><span style="font-size:12px;">Browser made with PyQt6(This upgrade will not come to the IE variant)</span>'
            '<br><span style="font-size:12px;">Release Notes are located in "HoverNet Settings/HoverNet/Release Notes". </span>'
        ))
        self.tools_menu.addAction(act_about)

        self.tools_btn.setMenu(self.tools_menu)
        self.tools_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        # Assemble top bar: app title, nav + address bar, tools pill, and window buttons
        top_layout.addWidget(self.app_title_text)
        top_layout.addWidget(nav_container, stretch=1)
        top_layout.addWidget(self._tools_pill)
        top_layout.addWidget(self.minimize_btn)
        top_layout.addWidget(self.maximize_btn)
        top_layout.addWidget(self.close_btn)

        self.main_layout.addWidget(top_bar)

        # --- Tab bar row (Safari-style: full-width, tabs share space equally) ---
        tab_row = QWidget()
        tab_row.setStyleSheet("QWidget { background-color: #1E1E3C; }")
        tab_row_layout = QHBoxLayout(tab_row)
        tab_row_layout.setContentsMargins(4, 2, 8, 2)
        tab_row_layout.setSpacing(6)
        tab_row_layout.addWidget(self.tab_bar, stretch=1)

        # New Tab button — lives in the tab row, right of all tabs
        self.new_tab_btn = NewTabButton()
        self.new_tab_btn.clicked.connect(self.add_tab)
        tab_row_layout.addWidget(self.new_tab_btn, stretch=0)

        self.main_layout.addWidget(tab_row)

        # --- Browser content area ---
        self.browser_area = QStackedWidget()
        self.main_layout.addWidget(self.browser_area)

        # Start with one tab
        self.add_tab("https://www.google.com")

        # Autocomplete — needs window to exist first so it can parent correctly
        self._autocomplete = AutocompleteDropdown(self.url_bar, self)

        # --- Download tracking ---
        self._downloads = []  # List of (filename, status, path)
        QWebEngineProfile.defaultProfile().downloadRequested.connect(self._on_download_requested)
        self._download_path = os.path.expanduser('~')
        
        # Apply custom title bar setting
        self.apply_custom_title_bar_setting()

        # Ensure external assets (icons/images) are installed when running as frozen EXE
        try:
            self._assets_root = self._ensure_installed_assets()
        except Exception:
            self._assets_root = None

        # Drag state for custom title bar
        self._drag_active = False
        self._drag_pending = False
        self._drag_start_pos = QPoint(0, 0)
        self._drag_maximized = False
        self._drag_ratio_x = 0.5
        self._drag_window_offset = QPoint(0, 0)
        self._press_pos_in_topbar = QPoint(0, 0)
        self._press_window_offset = QPoint(0, 0)
        # Install event filters on the top bar and all of its children to enable dragging everywhere
        self._install_topbar_drag_filters()

        # Dismiss Printy bubble when clicking anywhere outside it
        QApplication.instance().installEventFilter(self)

        # --- Version info ---
        self.HOVERNET_VERSION = "2.10.00"
        self.HOVERNET_VARIANT = "py"  # "py" | "ie" | "def"

        # --- Update checker ---
        self._update_bubble = UpdateBubble(self)
        self._update_bubble.hide()
        self._update_nam = QNetworkAccessManager(self)
        QTimer.singleShot(3000, self._check_for_updates)  # check 3s after launch

        # --- Download bubble ---
        self._download_bubble = DownloadBubble(self)
        self._download_bubble.hide()
        self._download_bubble.set_anchor(self.tools_btn)

    def _check_for_updates(self):
        try:
            from PyQt6.QtNetwork import QNetworkRequest
            req = QNetworkRequest(QUrl(UpdateBubble.RELEASES_URL))
            req.setRawHeader(b"User-Agent", b"HoverNet-PY-UpdateChecker")
            req.setRawHeader(b"Accept", b"application/vnd.github+json")
            reply = self._update_nam.get(req)
            reply.finished.connect(lambda: self._on_update_reply(reply))
        except Exception:
            pass

    def _on_update_reply(self, reply):
        try:
            import json as _json
            raw = bytes(reply.readAll())
            releases = _json.loads(raw.decode("utf-8"))
            reply.deleteLater()

            suffix = f"-{self.HOVERNET_VARIANT}"  # e.g. "-py"

            # Filter to only releases matching this variant's tag suffix
            variant_releases = [
                r for r in releases
                if isinstance(r.get("tag_name"), str)
                and r["tag_name"].lower().endswith(suffix)
                and not r.get("draft", False)
                and not r.get("prerelease", False)
            ]

            if not variant_releases:
                return

            latest_tag = variant_releases[0]["tag_name"]  # already sorted newest-first by GitHub

            # Strip suffix to get bare version for comparison
            latest_ver = latest_tag[:-len(suffix)].lstrip("vV")

            # Simple version comparison: split on dots and compare numerically
            def ver_tuple(v):
                try:
                    return tuple(int(x) for x in v.split("."))
                except Exception:
                    return (0,)

            if ver_tuple(latest_ver) > ver_tuple(self.HOVERNET_VERSION):
                self._update_bubble.show_update(latest_tag, self.printy_btn)
        except Exception:
            pass

    # --- Custom title bar drag handling ---
    def _is_frozen(self):
        try:
            return getattr(sys, 'frozen', False) is True
        except Exception:
            return False

    def _ensure_installed_assets(self):
        if self._is_frozen():
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        internal_root = os.path.join(base_dir, "_internal")
        source_dir = os.path.join(internal_root, "HoverNet")

        program_files = os.environ.get("ProgramFiles") or os.path.join(os.path.expanduser("~"), "AppData", "Local", "Programs")
        dest_dir = os.path.join(program_files, "HoverNet")

        def _sync_dir(src, dst):
            os.makedirs(dst, exist_ok=True)
            for root, dirs, files in os.walk(src):
                rel = os.path.relpath(root, src)
                target_root = os.path.join(dst, rel) if rel != "." else dst
                os.makedirs(target_root, exist_ok=True)
                for f in files:
                    src_f = os.path.join(root, f)
                    dst_f = os.path.join(target_root, f)
                    try:
                        # Copy if new, missing, or modified
                        if not os.path.exists(dst_f) or os.path.getmtime(src_f) > os.path.getmtime(dst_f):
                            shutil.copy2(src_f, dst_f)
                    except Exception:
                        continue

        if os.path.isdir(dest_dir):
            if os.path.isdir(source_dir):
                _sync_dir(source_dir, dest_dir)  # update missing/outdated files
            return dest_dir

        if os.path.isdir(source_dir):
            try:
                _sync_dir(source_dir, dest_dir)
                return dest_dir
            except PermissionError:
                appdata = os.getenv("APPDATA") or os.path.expanduser("~")
                dest_dir2 = os.path.join(appdata, "HoverNet")
                _sync_dir(source_dir, dest_dir2)
                return dest_dir2

        return None

    def _install_topbar_drag_filters(self):
        try:
            from PyQt6.QtWidgets import QWidget as _QWidget
        except Exception:
            _QWidget = None
        try:
            if getattr(self, 'top_bar', None) is None:
                return
            # Watch the window as well to keep receiving events while grabbing
            self.installEventFilter(self)
            self.top_bar.installEventFilter(self)
            if _QWidget is not None:
                for w in self.top_bar.findChildren(_QWidget):
                    try:
                        w.installEventFilter(self)
                    except Exception:
                        continue
        except Exception:
            pass

    def _is_topbar_object(self, obj):
        tb = getattr(self, 'top_bar', None)
        if tb is None or obj is None:
            return False
        if obj is tb:
            return True
        try:
            p = getattr(obj, 'parentWidget', lambda: None)()
            while p is not None:
                if p is tb:
                    return True
                p = p.parentWidget()
        except Exception:
            return False
        return False

    def _is_in_drag_region(self, pos_in_top_bar):
        """Return True if mouse is in the custom title bar region suitable for dragging.
        We allow the entire top bar to initiate drag to increase usable area."""
        if not self.use_custom_title_bar:
            return False
        if not hasattr(self, 'top_bar'):
            return False
        # Allow anywhere on the top bar. Clicks will still work because we only
        # activate dragging once the mouse has moved beyond a threshold.
        return True

    def eventFilter(self, obj, event):
        try:
            from PyQt6.QtCore import QEvent
        except Exception:
            QEvent = None

        # Dismiss Printy/Update bubble on any mouse press outside them
        if QEvent is not None and event.type() == QEvent.Type.MouseButtonPress:
            bubble = getattr(self, '_printy_bubble', None)
            if bubble and bubble.isVisible():
                if obj is not bubble and obj is not self.printy_btn:
                    bubble.hide()
            upd = getattr(self, '_update_bubble', None)
            if upd and upd.isVisible():
                if obj is not upd and obj is not self.printy_btn:
                    upd.hide()

        if QEvent is not None and (self._is_topbar_object(obj) or obj is self):
            et = event.type()
            # Mouse press: initiate potential drag
            if et == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                # Always compute position relative to the top bar using global coordinates
                pos_in_top_bar = self.top_bar.mapFromGlobal(event.globalPosition().toPoint())
                if self._is_in_drag_region(pos_in_top_bar):
                    self._drag_pending = True
                    self._press_pos_in_topbar = QPoint(pos_in_top_bar.x(), pos_in_top_bar.y())
                    self._drag_start_pos = event.globalPosition().toPoint()
                    self._drag_maximized = self.isMaximized()
                    # Capture the press offset in window coordinates to preserve exact anchor on restore
                    self._press_window_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                    # Ratio of cursor across the window width, used when restoring from maximized
                    w = max(1, self.width())
                    self._drag_ratio_x = max(0.0, min(1.0, pos_in_top_bar.x() / float(w)))
                    # Offset used for normal-size dragging (will be refined when drag activates)
                    self._drag_window_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                    return False
            # Mouse move: perform drag
            if et == QEvent.Type.MouseMove and self._drag_active:
                global_pos = event.globalPosition().toPoint()
                if self._drag_maximized:
                    # Restore to normal size and position window such that:
                    # - the middle of the top bar is directly under the cursor
                    self.showNormal()
                    new_width = max(1, self.width())
                    # Compute vertical center of the top bar relative to the window
                    topbar_center_y = int(getattr(self, 'top_bar').y() + getattr(self, 'top_bar').height() / 2)
                    # Offset from window top-left to the top bar center point horizontally/vertically
                    anchor_offset = QPoint(int(new_width / 2), topbar_center_y)
                    # Place window so that anchor_offset maps to the cursor position
                    target_middle = global_pos - anchor_offset
                    self.move(target_middle)
                    # Maintain this anchor during continued dragging
                    self._drag_window_offset = QPoint(anchor_offset.x(), anchor_offset.y())
                    self._drag_maximized = False
                else:
                    # Normal drag: move window keeping the press offset
                    top_left = global_pos - self._drag_window_offset
                    self.move(top_left)
                return True
            if et == QEvent.Type.MouseMove and self._drag_pending and not self._drag_active:
                # Activate drag only after exceeding threshold so clicks still work
                from PyQt6.QtWidgets import QApplication as _QtApp
                global_pos = event.globalPosition().toPoint()
                threshold = getattr(_QtApp.instance(), 'startDragDistance', lambda: 10)()
                dx = abs(global_pos.x() - self._drag_start_pos.x())
                dy = abs(global_pos.y() - self._drag_start_pos.y())
                if dx >= threshold or dy >= threshold:
                    self._drag_active = True
                    try:
                        self.grabMouse()
                    except Exception:
                        pass
                    # Update offset now that we are dragging
                    self._drag_window_offset = global_pos - self.frameGeometry().topLeft()
                    return True
            # Mouse release: end drag
            if et == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                if self._drag_active:
                    try:
                        self.releaseMouse()
                    except Exception:
                        pass
                self._drag_active = False
                self._drag_pending = False
                self._drag_maximized = False
                return False
        return super().eventFilter(obj, event)
    
    def apply_custom_title_bar_setting(self):
        """Apply the custom title bar setting"""
        if self.use_custom_title_bar:
            # Hide the default window title bar and show custom elements
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
            self.app_title_text.show()
            self.minimize_btn.show()
            self.maximize_btn.show()
            self.close_btn.show()
        else:
            # Show the default window title bar and hide custom elements
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.FramelessWindowHint)
            self.app_title_text.hide()
            self.minimize_btn.hide()
            self.maximize_btn.hide()
            self.close_btn.hide()
        self.show()  # Refresh the window to apply changes
    
    def set_custom_title_bar_enabled(self, enabled):
        """Enable or disable custom title bar"""
        self.use_custom_title_bar = enabled
        self.apply_custom_title_bar_setting()

    
    def minimize_window(self):
        self.showMinimized()
    
    def maximize_window(self):
        if self.isMaximized():
            self.showNormal()
            self.maximize_btn.setText("<>")
        else:
            self.showMaximized()
            self.maximize_btn.setText("><")
    
    def close_window(self):
        self.close()

    def set_ws_btn_visible(self, visible: bool):
        """Show or hide the WS button inside the tools pill."""
        self.show_ws_btn = visible
        self.ws_btn.setVisible(visible)
        self._sep_before_ws.setVisible(True)   # always keep separator between Home and P
        self._sep_after_ws.setVisible(visible)  # only needed when WS is present

    def _toggle_printy_bubble(self):
        """Show bubble on first click, regenerate on subsequent clicks."""
        if self._printy_bubble.isVisible():
            self._printy_bubble.regenerate()
            self._printy_bubble.show_below(self.printy_btn)
        else:
            self._printy_bubble.show_below(self.printy_btn)

    def normalize_input(self, text):
        text = (text or "").strip()
        if not text:
            return "https://www.google.com"

        # Already a fully qualified URL — pass straight through
        if text.startswith(("http://", "https://", "file://", "ftp://")):
            return text

        # Internal browser URIs — never search these
        if text.startswith(("about:", "chrome:", "edge:", "data:")):
            return text

        # localhost or local IPs (with optional port/path)
        import re
        if re.match(r'^localhost(:\d+)?(/.*)?$', text) or \
           re.match(r'^127\.\d+\.\d+\.\d+(:\d+)?(/.*)?$', text) or \
           re.match(r'^192\.168\.\d+\.\d+(:\d+)?(/.*)?$', text):
            return "http://" + text

        # Has spaces → definitely a search query
        if " " in text:
            return "https://www.google.com/search?q=" + quote_plus(text)

        # Looks like a domain: has a dot, no spaces, and a valid-ish TLD
        # e.g. google.com, www.github.com, sub.domain.co.uk
        if re.match(r'^(www\.)?[a-zA-Z0-9\-]+(\.[a-zA-Z]{2,})+(/.*)?$', text):
            return "https://" + text

        # Everything else → search
        return "https://www.google.com/search?q=" + quote_plus(text)

    def add_tab(self, url="https://www.google.com"):
        url = self.normalize_input(url)
        browser = BrowserView()
        browser.setUrl(QUrl(url))
        stack_index = self.browser_area.addWidget(browser)
        self.browser_area.setCurrentIndex(stack_index)

        tab_index = self.tab_bar.addTab("New Tab")
        self.tab_bar.setCurrentIndex(tab_index)

        browser.urlChanged.connect(lambda qurl, browser=browser: self.update_url(qurl, browser))
        # loading signals -> update tab text
        browser.loadStarted.connect(lambda b=browser: self.on_load_started(b))
        browser.loadProgress.connect(lambda p, b=browser: self.on_load_progress(b, p))
        browser.loadFinished.connect(lambda ok, b=browser: self.on_load_finished(b, ok))
        # Favicon: update tab icon whenever the page icon changes
        browser.iconChanged.connect(lambda icon, b=browser: self._on_favicon_changed(icon, b))
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
        browser._load_progress = 0
        idx = self.browser_area.indexOf(browser)
        if idx != -1:
            self.tab_bar.setTabText(idx, "Loading...")

    def on_load_progress(self, browser, percent):
        browser._load_progress = percent
        idx = self.browser_area.indexOf(browser)
        if idx != -1:
            self.tab_bar.setTabText(idx, f"{percent}%")

    def on_load_finished(self, browser, ok):
        browser._load_progress = -1
        idx = self.browser_area.indexOf(browser)
        if idx != -1:
            title = browser.title() or "New Tab"
            self.tab_bar.setTabText(idx, title)

    def _on_favicon_changed(self, icon, browser):
        """Update the tab icon when the page favicon changes."""
        idx = self.browser_area.indexOf(browser)
        if idx == -1:
            return
        if icon and not icon.isNull():
            # Scale to 16×16 to keep tab height consistent
            self.tab_bar.setTabIcon(idx, icon)
        else:
            self.tab_bar.setTabIcon(idx, QIcon())

    def load_url(self):
        raw = self.url_bar.text()
        url = self.normalize_input(raw)
        cur = self.browser_area.currentWidget()
        if cur:
            cur.setUrl(QUrl(url))

    def update_url(self, q, browser=None):
        if browser == self.browser_area.currentWidget():
            self.url_bar.setText(q.toString())

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

    def _on_download_requested(self, download: QWebEngineDownloadRequest):
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
        download.stateChanged.connect(lambda state, e=entry, d=download: self._on_download_finished(e) if d.isFinished() else None)
        # Show progress bubble
        self._download_bubble._reposition()
        self._download_bubble.add_download(download, os.path.basename(path))
    def _on_download_finished(self, entry):
        entry["status"] = "Completed" if entry["item"].state() == QWebEngineDownloadRequest.DownloadState.DownloadCompleted else "Failed"

    def _show_downloads_dialog(self):
        dlg = ViewDownloadsDialog(self._downloads, self)
        dlg.exec()


class HoverNetSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.resize(400, 420)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs)
        QMessageBox.warning(self, "Warning", "Most of the settings in here currently does not function.\nTheir functions will be implemented in the future.")

        def make_sep():
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Sunken)
            return line

        # ── Elements tab ─────────────────────────────────────────────────
        tab_elements = QWidget()
        v = QVBoxLayout(tab_elements)
        v.setSpacing(4)
        v.setContentsMargins(8, 8, 8, 8)

        # — Appearance —
        self.chk_custom_title_bar = QCheckBox("Use HoverNet title bar (Early access)")
        self.chk_custom_title_bar.setChecked(getattr(parent, 'use_custom_title_bar', True))
        self.chk_custom_title_bar.stateChanged.connect(self.on_custom_title_bar_changed)
        v.addWidget(self.chk_custom_title_bar)
        self.chk_show_ws = QCheckBox("Show \"WS\" in toolbar")
        self.chk_show_ws.setChecked(getattr(parent, 'show_ws_btn', True))
        self.chk_show_ws.stateChanged.connect(
            lambda state: parent.set_ws_btn_visible(state == Qt.CheckState.Checked.value)
            if parent and hasattr(parent, 'set_ws_btn_visible') else None
        )
        v.addWidget(self.chk_show_ws)

        v.addWidget(make_sep())

        # — Tabs —
        v.addWidget(QLabel("When a new tab is opened, open"))
        self.edit_newtab_url = QLineEdit("https://www.google.com")
        v.addWidget(self.edit_newtab_url)
        v.addWidget(QLabel("On startup,"))
        self.combo_startup = QComboBox()
        self.combo_startup.addItems(["Open a new tab", "Continue from last session", "Show a blank page"])
        v.addWidget(self.combo_startup)

        v.addWidget(make_sep())

        # — Downloads —
        v.addWidget(QLabel("Default download path:"))
        self.edit_download_path = QLineEdit(getattr(parent, '_download_path', os.path.expanduser('~')))
        v.addWidget(self.edit_download_path)
        btn_browse = QPushButton("Browse...")
        v.addWidget(btn_browse)
        def browse_path():
            path = QFileDialog.getExistingDirectory(self, "Select Download Folder", self.edit_download_path.text())
            if path:
                self.edit_download_path.setText(path)
        btn_browse.clicked.connect(browse_path)
        v.addStretch(1)
        self.tabs.addTab(tab_elements, "Elements")

        def save_path():
            path = self.edit_download_path.text()
            if path and not os.path.exists(path):
                os.makedirs(path, exist_ok=True)
            if parent is not None:
                parent._download_path = path
        self.accepted.connect(save_path)

        # ── Printy tab ────────────────────────────────────────────────────
        tab_printy = QWidget()
        vp = QVBoxLayout(tab_printy)
        vp.setContentsMargins(8, 8, 8, 8)
        vp.setSpacing(6)
        vp.addWidget(QLabel("Default mode for print(\"of the day!\"):"))
        self.combo_printy_mode = QComboBox()
        self.combo_printy_mode.addItems(["Random", "Sentence", "Word"])
        if parent and hasattr(parent, '_printy_bubble'):
            idx = self.combo_printy_mode.findText(parent._printy_bubble._mode)
            if idx >= 0:
                self.combo_printy_mode.setCurrentIndex(idx)
        self.combo_printy_mode.currentTextChanged.connect(
            lambda text: setattr(parent._printy_bubble, '_mode', text)
            if parent and hasattr(parent, '_printy_bubble') else None
        )
        vp.addWidget(self.combo_printy_mode)
        vp.addStretch(1)
        self.tabs.addTab(tab_printy, "Printy")

        # ── Account tab ───────────────────────────────────────────────────
        tab_account = QWidget()
        v_account = QVBoxLayout(tab_account)
        btn_gmail = QPushButton("G-Mail")
        btn_gmail.clicked.connect(lambda: QMessageBox.information(self, "Account", "Account management is not implemented yet."))
        btn_ms = QPushButton("Microsoft Account")
        btn_ms.clicked.connect(lambda: QMessageBox.information(self, "Account", "Account management is not implemented yet."))
        v_account.addWidget(btn_gmail)
        v_account.addWidget(btn_ms)
        v_account.addStretch(1)
        self.tabs.addTab(tab_account, "Account")

        # ── Release Notes tab ─────────────────────────────────────────────
        tab_relnotes = QWidget()
        v_relnotes = QVBoxLayout(tab_relnotes)
        notes = QLabel("visualOS HoverNet 2.1-PY\n"
            "Welcome back, Printy!\n"
            "Added favicons to tabs\n"
            "Added a toggle to set the WS button visible or invisible\n"
            "Added a custom background to blank and non-loaded pages\n"
            "Added autocomplete into the address bar\n"
            "Changed the app style from IE-like to pill-shaped\n"
            "Changed the position of tabs and the New tab button to a dedicated container\n"
            "Changed tab styles, this new style was inspired by Safari\n"
            "Replaced Appearance, Tabs and Downloads with Elements\n"
            "Fixed some minor bugs\n"
            "There were more features planned to come with v2.1, however those have been delayed for now.\n"
            )
        notes.setWordWrap(True)
        v_relnotes.addWidget(notes)
        self.tabs.addTab(tab_relnotes, "Release Notes")

    def on_custom_title_bar_changed(self, state):
        enabled = state == Qt.CheckState.Checked.value
        if self.parent() and hasattr(self.parent(), 'set_custom_title_bar_enabled'):
            self.parent().set_custom_title_bar_enabled(enabled)

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
        self.btn_cancel_dl = QPushButton("Cancel Download")
        self.btn_clear = QPushButton("Clear List")
        btns.addWidget(self.btn_open)
        btns.addWidget(self.btn_folder)
        btns.addWidget(self.btn_cancel_dl)
        btns.addWidget(self.btn_clear)
        layout.addLayout(btns)
        self.btn_open.clicked.connect(self.open_file)
        self.btn_folder.clicked.connect(self.open_folder)
        self.btn_cancel_dl.clicked.connect(self.cancel_download)
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
    def cancel_download(self):
        idx = self.list.currentIndex().row()
        if 0 <= idx < len(self.downloads):
            entry = self.downloads[idx]
            if entry.get('status') == 'Downloading':
                try:
                    entry['item'].cancel()
                    entry['status'] = 'Cancelled'
                    self.update_list()
                except Exception:
                    pass
            else:
                QMessageBox.information(self, "Cancel Download", "This download is not active.")
    def clear_list(self):
        self.downloads.clear()
        self.update_list()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = HoverNetPY()
    window.show()
    sys.exit(app.exec())