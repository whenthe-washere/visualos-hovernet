import random
import subprocess
from PySide6.QtCore import Qt, QPoint, QTimer, QRectF
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QToolButton, QProgressBar
from PySide6.QtGui import QPainter, QColor
from ...utils.helpers import format_size

class DownloadBubble(QWidget):
    """Floating bubble anchored to the Tools button showing active download progress."""
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._entries = {}  # download item -> {widgets}
        self._anchor = None

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 10, 14, 10)
        self._layout.setSpacing(8)

        self._no_downloads = QLabel("No active downloads")
        self._no_downloads.setStyleSheet("color: #7777aa; font-size: 11px; background: transparent;")
        self._no_downloads.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._no_downloads)

    def add_download(self, download, filename):
        if download in self._entries:
            return

        row = QWidget()
        row.setStyleSheet("background: transparent;")
        rl = QVBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(2)

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
        cancel_btn.setStyleSheet("color: #ff5555; background: transparent; border: none; font-weight: bold;")
        cancel_btn.clicked.connect(lambda: self._cancel_download(download))

        trl.addWidget(name_lbl, 1)
        trl.addWidget(cancel_btn)

        bar = QProgressBar()
        bar.setFixedHeight(6)
        bar.setTextVisible(False)
        bar.setStyleSheet("""
            QProgressBar {
                background: #1a1a3a;
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
        try: download.cancel()
        except: pass
        self._on_finished(download)

    def _on_progress(self, download):
        entry = self._entries.get(download)
        if not entry: return
        received = download.receivedBytes()
        total = download.totalBytes()
        pct = int(received / total * 100) if total > 0 else 0
        entry["bar"].setValue(pct)
        entry["info"].setText(f"{pct}% — {format_size(received)} / {format_size(total)}")
        self.adjustSize()

    def _on_finished(self, download):
        entry = self._entries.pop(download, None)
        if entry: entry["row"].deleteLater()
        if not self._entries:
            self._no_downloads.setVisible(True)
            QTimer.singleShot(2000, self.hide)
        self.adjustSize()

    def _reposition(self):
        if not self._anchor: return
        global_pos = self._anchor.mapToGlobal(QPoint(self._anchor.width() // 2, self._anchor.height()))
        self.adjustSize()
        x = global_pos.x() - self.width() // 2
        y = global_pos.y() + 6
        self.move(x, y)

    def set_anchor(self, widget):
        self._anchor = widget

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(QColor(28, 28, 58, 240))
        painter.setPen(QColor(80, 80, 160, 200))
        painter.drawRoundedRect(QRectF(rect), 10, 10)

class UpdateBubble(QWidget):
    RELEASES_PAGE = "https://github.com/whenthe-washere/visualos-hovernet/releases"
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._anchor = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(280)
        self._label.setStyleSheet("color: #e0e0ff; font-family: Consolas, monospace; font-size: 11px; background: transparent;")
        layout.addWidget(self._label)

        self._btn = QPushButton("View on GitHub →")
        self._btn.setStyleSheet("""
            QPushButton {
                background: #2e2e60; color: #aaaaff; border: 1px solid #5555aa;
                border-radius: 4px; font-size: 10px; padding: 3px 10px;
            }
            QPushButton:hover { background: #3a3a80; color: #ffffff; }
        """)
        self._btn.clicked.connect(self._open_releases)
        layout.addWidget(self._btn)

    def _open_releases(self):
        try: subprocess.Popen(["start", "", self.RELEASES_PAGE], shell=True)
        except: pass

    def show_update(self, latest_tag, anchor_widget):
        self._anchor = anchor_widget
        self._label.setText(f'update("{latest_tag} is available!")')
        self.reposition()
        self.show()
        self.raise_()

    def reposition(self):
        if not self._anchor: return
        global_pos = self._anchor.mapToGlobal(QPoint(self._anchor.width() // 2, self._anchor.height()))
        self.adjustSize()
        x = global_pos.x() - self.width() // 2
        y = global_pos.y() + 6
        self.move(x, y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(QColor(28, 28, 58, 240))
        painter.setPen(QColor(80, 80, 160, 200))
        painter.drawRoundedRect(QRectF(rect), 10, 10)

class PrintyBubble(QWidget):
    _SENTENCES = [
        "Have you tried turning it off and on again?",
        "The mitochondria is the powerhouse of the cell.",
        "I am a banana.",
        "Do you ever just stare at code until it makes sense? No? Just me?",
        "All your base are belong to us.",
        "I heard whenthe_washere was working on replacing Google Sites websites with actual websites.",
        "Error 404: I forgot what the fuck was I supposed to say.",
        "Touch grass. Or don't. I'm a browser, not your mum.",
        "Certified HoverNet moment.",
        "Today's forecast: partly cloudy with a chance of unhandled exceptions.",
        "you are valid. also please clear your cache.",
        "nuh uh",
        "im bored and i now require cat images."
    ]
    _WORDS = ["miku", "teto", "neru", "serendipity", "quokka", "void", "amogus", "skibidi", "gigachad", "BSOD"]

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._mode = "Random"
        self._text = ""
        self._anchor = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(340)
        self._label.setStyleSheet("color: #e0e0ff; font-family: Consolas, monospace; font-size: 11px; background: transparent;")
        layout.addWidget(self._label)

    def _pick(self):
        if self._mode == "Sentence": return random.choice(self._SENTENCES)
        elif self._mode == "Word": return random.choice(self._WORDS)
        else: return random.choice(self._SENTENCES if random.random() < 0.5 else self._WORDS)

    def regenerate(self):
        self._text = self._pick()
        self._label.setText(f'print("{self._text}")')
        self.adjustSize()

    def show_below(self, anchor_widget):
        self._anchor = anchor_widget
        self.regenerate()
        self.reposition()
        self.show()
        self.raise_()

    def reposition(self):
        if not self._anchor: return
        global_pos = self._anchor.mapToGlobal(QPoint(self._anchor.width() // 2, self._anchor.height()))
        self.adjustSize()
        x = global_pos.x() - self.width() // 2
        y = global_pos.y() + 6
        self.move(x, y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(QColor(28, 28, 58, 240))
        painter.setPen(QColor(80, 80, 160, 200))
        painter.drawRoundedRect(QRectF(rect), 10, 10)
