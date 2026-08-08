import random
import subprocess
import json
from PySide6.QtCore import Qt, QPoint, QTimer, QRectF, QRect, QPropertyAnimation
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QToolButton, QProgressBar, QLineEdit, QApplication
from PySide6.QtGui import QPainter, QColor, QTextCharFormat, QCursor
from ...utils.helpers import format_size
from ...utils.easing import curve_linear_out, curve_linear_in

def _build_download_row(color_source, download, filename, on_cancel, on_minimize):
    """Shared row UI (name, minimize, cancel, progress bar, info) used by both
    the anchored DownloadBubble and the per-tab DownloadHoverBubble."""
    r, g, b = color_source._get_accent_rgb()
    accent = f"#{r:02x}{g:02x}{b:02x}"
    bar_bg = f"rgba({r//3},{g//3},{b//3},180)"
    info_col = f"rgba({r},{g},{b},160)"

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
    name_lbl.setStyleSheet("color: #ffffff; font-size: 11px; font-family: Consolas, monospace; background: transparent;")
    name_lbl.setMaximumWidth(220)
    name_lbl.setToolTip(filename)

    minimize_btn = QToolButton()
    minimize_btn.setText("\u2013")
    minimize_btn.setStyleSheet("color: #c9d3e5; background: transparent; border: none; font-weight: bold;")
    minimize_btn.setToolTip("Minimize download")
    minimize_btn.clicked.connect(lambda: on_minimize(download))

    cancel_btn = QToolButton()
    cancel_btn.setText("\u2715")
    cancel_btn.setStyleSheet("color: #ff5555; background: transparent; border: none; font-weight: bold;")
    cancel_btn.setToolTip("Cancel download")
    cancel_btn.clicked.connect(lambda: on_cancel(download))

    trl.addWidget(name_lbl, 1)
    trl.addWidget(minimize_btn)
    trl.addWidget(cancel_btn)

    bar = QProgressBar()
    bar.setFixedHeight(6)
    bar.setTextVisible(False)
    bar.setStyleSheet(f"""
        QProgressBar {{
            background: {bar_bg};
            border: none;
            border-radius: 3px;
        }}
        QProgressBar::chunk {{
            background: {accent};
            border-radius: 3px;
        }}
    """)

    info_lbl = QLabel("0% — ? / ?")
    info_lbl.setStyleSheet(f"color: {info_col}; font-size: 10px; font-family: Consolas, monospace; background: transparent;")

    rl.addWidget(top_row)
    rl.addWidget(bar)
    rl.addWidget(info_lbl)

    return {"row": row, "bar": bar, "info": info_lbl, "cancel_btn": cancel_btn, "minimize_btn": minimize_btn}


class DownloadBubble(QWidget):
    """Floating bubble anchored to the Tools button showing active download progress.

    Downloads can be minimized (manually via each row's minimize button, or
    automatically after three seconds). While a download is minimized, its
    progress is shown as an outline around the tab it belongs to, and hovering
    that tab shows a full per-tab preview (see DownloadHoverBubble)."""
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._main_window = parent
        self._entries = {}
        self._anchor = None
        self._cached_bg = None
        self._cached_border = None

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 10, 14, 10)
        self._layout.setSpacing(8)

        self._no_downloads = QLabel("No active downloads")
        self._apply_no_downloads_style()
        self._no_downloads.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._no_downloads)

        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self._auto_minimize)

    def _get_accent_rgb(self):
        win = self.window()
        if win and hasattr(win, 'get_accent_rgb'):
            return win.get_accent_rgb()
        return (85, 142, 255)

    def _get_is_dark(self):
        win = self.window()
        if win and hasattr(win, 'is_dark_mode'):
            return win.is_dark_mode
        return True

    def _apply_no_downloads_style(self):
        r, g, b = self._get_accent_rgb()
        muted = f"rgba({r},{g},{b},140)"
        self._no_downloads.setStyleSheet(f"color: {muted}; font-size: 11px; background: transparent;")

    def _recalc_colors(self):
        r, g, b = self._get_accent_rgb()
        if self._get_is_dark():
            self._cached_bg = QColor(max(r//3, 10), max(g//3, 10), max(b//3, 10), 240)
            self._cached_border = QColor(min(r//2+30, 255), min(g//2+30, 255), min(b//2+30, 255), 200)
        else:
            self._cached_bg = QColor(min(r+100, 255), min(g+100, 255), min(b+100, 255), 240)
            self._cached_border = QColor(r, g, b, 200)

    def add_download(self, download, filename, view=None):
        if download in self._entries:
            return

        ui = _build_download_row(self, download, filename,
                                 on_cancel=self._cancel_download,
                                 on_minimize=self._minimize)
        self._entries[download] = dict(ui, minimized=False, pct=0)
        self._no_downloads.setVisible(False)
        self._layout.addWidget(ui["row"])

        download.receivedBytesChanged.connect(lambda: self._on_progress(download))
        download.stateChanged.connect(lambda state, d=download: self._on_finished(d) if d.isFinished() else None)

        self._reposition()
        self.adjustSize()
        self.show()
        self.raise_()
        self._auto_timer.start(3000)

    def _cancel_download(self, download):
        try: download.cancel()
        except: pass
        self._on_finished(download)

    def _minimize(self, download):
        entry = self._entries.get(download)
        if not entry or entry.get("minimized"):
            return
        entry["minimized"] = True
        entry["row"].hide()
        mw = self._main_window
        if mw is not None and hasattr(mw, '_minimize_download'):
            mw._minimize_download(download)
        if not any(e["row"].isVisible() for e in self._entries.values()):
            self._auto_timer.stop()
            self.hide()

    def _auto_minimize(self):
        for download in list(self._entries):
            self._minimize(download)

    def _on_progress(self, download):
        entry = self._entries.get(download)
        if not entry: return
        received = download.receivedBytes()
        total = download.totalBytes()
        pct = int(received / total * 100) if total > 0 else 0
        entry["bar"].setValue(pct)
        entry["info"].setText(f"{pct}% — {format_size(received)} / {format_size(total)}")
        self.adjustSize()
        # Store the percentage on the canonical app-level entry so the tab
        # outline draws using exactly the same value the bar displays.
        mw = self._main_window
        if mw is not None and hasattr(mw, '_find_download_entry'):
            app_entry = mw._find_download_entry(download)
            if app_entry is not None:
                app_entry["pct"] = pct

    def _on_finished(self, download):
        entry = self._entries.pop(download, None)
        if entry: entry["row"].deleteLater()
        if not self._entries:
            self._no_downloads.setVisible(True)
            self._auto_timer.stop()
            QTimer.singleShot(2000, self.hide)
        self.adjustSize()

    def _reposition(self):
        if not self._anchor: return
        global_pos = self._anchor.mapToGlobal(QPoint(self._anchor.width() // 2, 0))
        self.adjustSize()
        x = global_pos.x() - self.width() // 2
        y = global_pos.y() - self.height() - 6
        self.move(x, y)

    def set_anchor(self, widget):
        self._anchor = widget

    def paintEvent(self, event):
        if self._cached_bg is None:
            self._recalc_colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(self._cached_bg)
        painter.setPen(self._cached_border)
        painter.drawRoundedRect(QRectF(rect), 10, 10)


class DownloadHoverBubble(QWidget):
    """Per-tab download preview shown on top of a tab while it is hovered and a
    download is still in progress. Fades in (linear + ease-out) and out
    (ease-in + linear, same duration), and is horizontally centered on the tab."""
    def __init__(self, main_window, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._main_window = main_window
        self._cached_bg = None
        self._cached_border = None
        self._current = None
        self._ui = None
        self._tab_index = -1

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 8, 12, 8)
        self._layout.setSpacing(6)

        self._fade_in = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_in.setDuration(170)
        self._fade_in.setEasingCurve(curve_linear_out())
        self._fade_in.finished.connect(lambda: self.setWindowOpacity(1.0))
        self._fade_out = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_out.setDuration(170)
        self._fade_out.setEasingCurve(curve_linear_in())
        self._fade_out.finished.connect(self._fade_out_done)

    def _get_accent_rgb(self):
        win = self.window()
        if win and hasattr(win, 'get_accent_rgb'):
            return win.get_accent_rgb()
        return (85, 142, 255)

    def _get_is_dark(self):
        win = self.window()
        if win and hasattr(win, 'is_dark_mode'):
            return win.is_dark_mode
        return True

    def _recalc_colors(self):
        r, g, b = self._get_accent_rgb()
        if self._get_is_dark():
            self._cached_bg = QColor(max(r//3, 10), max(g//3, 10), max(b//3, 10), 240)
            self._cached_border = QColor(min(r//2+30, 255), min(g//2+30, 255), min(b//2+30, 255), 200)
        else:
            self._cached_bg = QColor(min(r+100, 255), min(g+100, 255), min(b+100, 255), 240)
            self._cached_border = QColor(r, g, b, 200)

    def _fade_out_done(self):
        self.hide()
        self.setWindowOpacity(1.0)

    def _clear_row(self):
        if self._ui is not None:
            self._layout.removeWidget(self._ui["row"])
            self._ui["row"].deleteLater()
            self._ui = None
        self._current = None

    def show_on_tab(self, index, download, filename):
        if not hasattr(self._main_window, 'tab_bar'):
            return
        if self._current is not None and self._current[0] is download:
            pass
        else:
            self._clear_row()
            ui = _build_download_row(self, download, filename,
                                     on_cancel=self._cancel,
                                     on_minimize=self._minimize)
            self._ui = ui
            self._layout.addWidget(ui["row"])
            self._current = (download, filename)
            download.receivedBytesChanged.connect(lambda: self._on_progress(download))
            download.stateChanged.connect(lambda state, d=download: self._on_finished(d) if d.isFinished() else None)
        self._tab_index = index
        self._reposition()
        self._fade_out.stop()
        if not self.isVisible():
            self.setWindowOpacity(0.0)
            self.show()
            self.raise_()
        # Re-run once the window is mapped so centering uses the final width.
        self._reposition()
        self._fade_in.setStartValue(self.windowOpacity())
        self._fade_in.setEndValue(1.0)
        self._fade_in.start()

    def _cancel(self, download):
        try: download.cancel()
        except: pass
        self._on_finished(download)

    def _minimize(self, download):
        mw = self._main_window
        if mw is not None and hasattr(mw, '_minimize_download'):
            mw._minimize_download(download)
        self.hide_bubble()

    def _on_progress(self, download):
        if self._current is None or self._current[0] is not download:
            return
        received = download.receivedBytes()
        total = download.totalBytes()
        pct = int(received / total * 100) if total > 0 else 0
        self._ui["bar"].setValue(pct)
        self._ui["info"].setText(f"{pct}% — {format_size(received)} / {format_size(total)}")
        self.adjustSize()

    def _on_finished(self, download):
        if self._current is not None and self._current[0] is download:
            self._clear_row()
            self.hide_bubble()

    def is_showing(self, download):
        return self.isVisible() and self._current is not None and self._current[0] is download

    def _cursor_over_self(self):
        return self.isVisible() and self.rect().contains(self.mapFromGlobal(QCursor.pos()))

    def enterEvent(self, event):
        super().enterEvent(event)
        if self.isVisible():
            self._fade_out.stop()
            self.setWindowOpacity(1.0)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if not self.isVisible():
            return
        tb = self._main_window.tab_bar
        pos = tb.mapFromGlobal(QCursor.pos())
        if tb.rect().contains(pos) and tb.tabAt(pos) == self._tab_index:
            return
        self.hide_bubble()

    def hide_bubble(self):
        if not self.isVisible():
            self._fade_out.stop()
            self.setWindowOpacity(1.0)
            return
        self._fade_in.stop()
        self._fade_out.setStartValue(self.windowOpacity())
        self._fade_out.setEndValue(0.0)
        self._fade_out.start()

    def _reposition(self):
        if self._tab_index < 0:
            return
        tb = self._main_window.tab_bar
        if self._tab_index >= tb.count():
            return
        rect = tb.tabRect(self._tab_index)
        if rect.width() <= 0 or rect.height() <= 0:
            return
        sh = self.sizeHint()
        w = sh.width() if sh.width() > 0 else self.width()
        h = sh.height() if sh.height() > 0 else self.height()
        g = tb.mapToGlobal(QPoint(rect.center().x(), rect.top()))
        x = g.x() - w // 2
        y = g.y() - h - 8
        scr = QApplication.primaryScreen().availableGeometry() if QApplication.primaryScreen() else None
        if scr is not None:
            x = max(scr.left() + 4, min(x, scr.right() - w - 4))
            y = max(scr.top() + 4, y)
        self.setGeometry(x, y, w, h)

    def reposition(self):
        if self.isVisible() and self._current is not None:
            self._reposition()

    def paintEvent(self, event):
        if self._cached_bg is None:
            self._recalc_colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(self._cached_bg)
        painter.setPen(self._cached_border)
        painter.drawRoundedRect(QRectF(rect), 10, 10)

class ApplyBubble(QWidget):
    """Floating bubble shown while settings are being applied, with a progress bar
    that reflects successful changes / total changes (the final reload counts too)."""
    def __init__(self, main_window, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._main_window = main_window
        self._anchor = None
        self._cached_bg = None
        self._cached_border = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        self._label = QLabel("Applying settings…")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label)

        self._bar = QProgressBar()
        self._bar.setFixedWidth(200)
        self._bar.setFixedHeight(8)
        self._bar.setTextVisible(False)
        self._bar.setRange(0, 1)
        layout.addWidget(self._bar)

        self._pct = QLabel("0%")
        self._pct.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._pct)

        self._apply_style()

    def _apply_style(self):
        win = self._main_window
        r, g, b = (85, 142, 255)
        if win and hasattr(win, 'get_accent_rgb'):
            r, g, b = win.get_accent_rgb()
        is_dark = True
        if win and hasattr(win, 'is_dark_mode'):
            is_dark = win.is_dark_mode
        accent = f"#{r:02x}{g:02x}{b:02x}"
        if is_dark:
            self._cached_bg = QColor(max(r//3, 10), max(g//3, 10), max(b//3, 10), 240)
            self._cached_border = QColor(min(r//2+30, 255), min(g//2+30, 255), min(b//2+30, 255), 200)
            bar_bg = f"rgba({r//4},{g//4},{b//4},180)"
        else:
            self._cached_bg = QColor(min(r+100, 255), min(g+100, 255), min(b+100, 255), 240)
            self._cached_border = QColor(r, g, b, 200)
            bar_bg = f"rgba({r},{g},{b},40)"
        text = "#ffffff" if is_dark else "#000000"
        self._label.setStyleSheet(f"color: {text}; font-family: Consolas, monospace; font-size: 12px; background: transparent;")
        self._pct.setStyleSheet(f"color: {accent}; font-family: Consolas, monospace; font-size: 10px; background: transparent;")
        self._bar.setStyleSheet(f"""
            QProgressBar {{
                background: {bar_bg}; border: none; border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background: {accent}; border-radius: 4px;
            }}
        """)

    def start(self, total, anchor_widget):
        self._anchor = anchor_widget
        self._bar.setRange(0, max(1, total))
        self._bar.setValue(0)
        self._pct.setText("0%")
        self._apply_style()
        self.reposition()
        self.show()
        self.raise_()

    def set_progress(self, done, total):
        self._bar.setRange(0, max(1, total))
        self._bar.setValue(done)
        pct = int(done / total * 100) if total > 0 else 0
        self._pct.setText(f"{pct}%")

    def finish(self):
        QTimer.singleShot(800, self.hide)

    def reposition(self):
        if not self._anchor:
            return
        self.adjustSize()
        ar = self._anchor.rect()
        global_bottom = self._anchor.mapToGlobal(QPoint(ar.width() // 2, ar.height()))
        x = global_bottom.x() - self.width() // 2
        y = global_bottom.y() - self.height() - 16
        self.move(x, y)

    def paintEvent(self, event):
        if self._cached_bg is None:
            self._apply_style()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(self._cached_bg)
        painter.setPen(self._cached_border)
        painter.drawRoundedRect(QRectF(rect), 10, 10)


class UpdateBubble(QWidget):
    RELEASES_PAGE = "https://github.com/whenthe-washere/visualos-hovernet/releases"
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._anchor = None
        self._cached_bg = None
        self._cached_border = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(280)
        layout.addWidget(self._label)

        self._btn = QPushButton("View on GitHub →")
        self._btn.clicked.connect(self._open_releases)
        layout.addWidget(self._btn)

        self._apply_style()

    def _get_accent_rgb(self):
        win = self.window()
        if win and hasattr(win, 'get_accent_rgb'):
            return win.get_accent_rgb()
        return (85, 142, 255)

    def _get_is_dark(self):
        win = self.window()
        if win and hasattr(win, 'is_dark_mode'):
            return win.is_dark_mode
        return True

    def _apply_style(self):
        r, g, b = self._get_accent_rgb()
        is_dark = self._get_is_dark()
        if is_dark:
            self._cached_bg = QColor(max(r//3, 10), max(g//3, 10), max(b//3, 10), 240)
            self._cached_border = QColor(min(r//2+30, 255), min(g//2+30, 255), min(b//2+30, 255), 200)
            btn_bg = f"rgba({r//2},{g//2},{b//2},160)"
            btn_border = f"rgba({r},{g},{b},140)"
            btn_hover = f"rgba({r},{g},{b},40)"
        else:
            self._cached_bg = QColor(min(r+100, 255), min(g+100, 255), min(b+100, 255), 240)
            self._cached_border = QColor(r, g, b, 200)
            btn_bg = f"rgba({r},{g},{b},50)"
            btn_border = f"rgba({r},{g},{b},80)"
            btn_hover = f"rgba({r},{g},{b},30)"
        text = "#ffffff" if is_dark else "#000000"
        self._label.setStyleSheet(f"color: {text}; font-family: Consolas, monospace; font-size: 11px; background: transparent;")
        self._btn.setStyleSheet(f"""
            QPushButton {{
                background: {btn_bg}; color: {text}; border: 1px solid {btn_border};
                border-radius: 4px; font-size: 10px; padding: 3px 10px;
            }}
            QPushButton:hover {{ background: {btn_hover}; color: {text}; }}
        """)

    def _open_releases(self):
        try: subprocess.Popen(["start", "", self.RELEASES_PAGE], shell=True)
        except: pass

    def show_update(self, latest_tag, anchor_widget):
        self._anchor = anchor_widget
        self._label.setText(f'update("{latest_tag} is available!")')
        self._apply_style()
        self.reposition()
        self.show()
        self.raise_()

    def reposition(self):
        if not self._anchor: return
        global_pos = self._anchor.mapToGlobal(QPoint(self._anchor.width() // 2, 0))
        self.adjustSize()
        x = global_pos.x() - self.width() // 2
        y = global_pos.y() - self.height() - 6
        self.move(x, y)

    def paintEvent(self, event):
        if self._cached_bg is None:
            self._apply_style()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(self._cached_bg)
        painter.setPen(self._cached_border)
        painter.drawRoundedRect(QRectF(rect), 10, 10)

class PrintyBubble(QWidget):
    _SENTENCES = [
        "Have you tried turning it off and on again?\nSeriously, have you?",
        "Contributors, assemble.",
        "I am a banana. A nano banana, if you may.",
        "Do you ever just stare at code until it makes sense? No? Just me? Alright then.",
        "All your base are belong to us.",
        "This is a bubble text placeholder meant to test the current state of Printy's bubble is something I would've said, except we're past the testing point already.",
        "Error 403: Access denied... to what again?",
        "I would say things like \"Touch grass. Or don't, I'm not your mum.\" right now, but that joke's getting boring at this point.",
        "Non-certified HoverNet moment, cause I don't wanna verify my OAuth to Google.",
        "Today's forecast: partly crashy with a chance of unhandled exceptions.",
        "You may be valid. But you haven't cleared your AppData, therefore your argument is false.",
        "Sometimes I just look. Then I look. Then I proceed to get sent straight to the void 'cause SmartScreen is being SmartScreen.",
        "I can't have feelings, yeah, but at the same time.. What would a living being be if it also didn't have feelings?... I dunno man, maybe I'm just overthinking things right now.",
        "Error 0: Something happened, but I can't tell what."
    ]
    _WORDS = ["miku", "teto", "neru", "serendipity", "quokka", "void", "amogus", "skibidi", "gigachad", "BSOD"]

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._mode = "Random"
        self._text = ""
        self._anchor = None
        self._cached_bg = None
        self._cached_border = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)

        self._label = QLabel()
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(340)
        layout.addWidget(self._label)

        self._apply_style()

    def _get_accent_rgb(self):
        win = self.window()
        if win and hasattr(win, 'get_accent_rgb'):
            return win.get_accent_rgb()
        return (85, 142, 255)

    def _get_is_dark(self):
        win = self.window()
        if win and hasattr(win, 'is_dark_mode'):
            return win.is_dark_mode
        return True

    def _apply_style(self):
        r, g, b = self._get_accent_rgb()
        is_dark = self._get_is_dark()
        if is_dark:
            self._cached_bg = QColor(max(r//3, 10), max(g//3, 10), max(b//3, 10), 240)
            self._cached_border = QColor(min(r//2+30, 255), min(g//2+30, 255), min(b//2+30, 255), 200)
        else:
            self._cached_bg = QColor(min(r+100, 255), min(g+100, 255), min(b+100, 255), 240)
            self._cached_border = QColor(r, g, b, 200)
        text = "#ffffff" if is_dark else "#000000"
        self._label.setStyleSheet(f"color: {text}; font-family: Consolas, monospace; font-size: 11px; background: transparent;")

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
        self._apply_style()
        self.regenerate()
        self.reposition()
        self.show()
        self.raise_()

    def mousePressEvent(self, event):
        self.hide()

    def reposition(self):
        if not self._anchor: return
        global_pos = self._anchor.mapToGlobal(QPoint(self._anchor.width() // 2, 0))
        self.adjustSize()
        x = global_pos.x() - self.width() // 2
        y = global_pos.y() - self.height() - 6
        self.move(x, y)

    def paintEvent(self, event):
        if self._cached_bg is None:
            self._apply_style()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(self._cached_bg)
        painter.setPen(self._cached_border)
        painter.drawRoundedRect(QRectF(rect), 10, 10)

class ZoomBubble(QWidget):
    """Compact zoom controls bubble: [+ % -] [Reset]"""
    def __init__(self, main_window, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._anchor = None
        self._main_window = main_window
        self._cached_bg = None
        self._cached_border = None

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(4)

        self._btn_in = QToolButton()
        self._btn_in.setText("+")
        self._btn_in.setFixedSize(28, 26)
        self._btn_in.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_in.clicked.connect(lambda: main_window._zoom(1.1))
        row.addWidget(self._btn_in)

        self._pct = QLineEdit("100%")
        self._pct.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pct.setFixedSize(52, 26)
        self._pct.setMaxLength(5)
        self._pct.returnPressed.connect(self._apply_custom_zoom)
        row.addWidget(self._pct)

        self._btn_out = QToolButton()
        self._btn_out.setText("-")
        self._btn_out.setFixedSize(28, 26)
        self._btn_out.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_out.clicked.connect(lambda: main_window._zoom(1/1.1))
        row.addWidget(self._btn_out)

        self._btn_reset = QToolButton()
        self._btn_reset.setText("Reset")
        self._btn_reset.setFixedHeight(26)
        self._btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_reset.clicked.connect(main_window._zoom_reset)
        row.addWidget(self._btn_reset)

        self._apply_style()

    def _apply_custom_zoom(self):
        raw = self._pct.text().strip().replace("%", "")
        try:
            val = int(raw)
        except ValueError:
            self.update_zoom(self._main_window.browser_area.currentWidget().zoomFactor()
                             if hasattr(self._main_window, 'browser_area') and
                             hasattr(self._main_window.browser_area.currentWidget(), 'zoomFactor') else 1.0)
            return
        val = max(10, min(500, val))
        cur = self._main_window.browser_area.currentWidget()
        if hasattr(cur, 'setZoomFactor'):
            cur.setZoomFactor(val / 100.0)
        if hasattr(self._main_window, '_zoom_bubble'):
            self._main_window._zoom_bubble.update_zoom(val / 100.0)
        if hasattr(self._main_window, '_zoom_trigger'):
            self._main_window._zoom_trigger.setText(f"{val}%")

    def _apply_style(self):
        win = self._main_window
        r, g, b = win.get_accent_rgb()
        is_dark = getattr(win, 'is_dark_mode', True)
        mr, mg, mb = max(r//4, 14), max(g//4, 14), max(b//4, 14)
        text = "#ffffff" if is_dark else "#000000"
        muted = f"rgba({r},{g},{b},140)" if is_dark else f"rgba({r},{g},{b},100)"
        hover_bg = f"rgba({r},{g},{b},40)" if is_dark else f"rgba({r},{g},{b},20)"
        btn_bg = f"rgba({mr+6},{mg+6},{mb+6},180)" if is_dark else "rgba(230,230,235,200)"
        input_bg = f"rgba({mr},{mg},{mb},120)" if is_dark else "rgba(235,235,240,200)"
        if is_dark:
            self._cached_bg = QColor(max(r//3, 10), max(g//3, 10), max(b//3, 10), 240)
            self._cached_border = QColor(min(r//2+30, 255), min(g//2+30, 255), min(b//2+30, 255), 200)
        else:
            self._cached_bg = QColor(min(r+100, 255), min(g+100, 255), min(b+100, 255), 240)
            self._cached_border = QColor(r, g, b, 200)
        self.setStyleSheet(f"""
            ZoomBubble QToolButton {{
                background: {btn_bg}; color: {text}; border: none;
                border-radius: 6px; font-size: 14px; font-weight: 700;
            }}
            ZoomBubble QToolButton:hover {{ background: {hover_bg}; }}
            ZoomBubble QToolButton:pressed {{ background: rgba({r},{g},{b},60); }}
            ZoomBubble QLineEdit {{
                color: {text}; font-size: 12px; font-weight: 600;
                background: {input_bg}; border: 1px solid transparent;
                border-radius: 4px; font-family: Consolas, monospace;
                padding: 0; text-align: center;
            }}
            ZoomBubble QLineEdit:focus {{
                border: 1px solid rgba({r},{g},{b},120);
                background: {btn_bg};
            }}
        """)

    def update_zoom(self, factor):
        pct = int(round(factor * 100))
        if not self._pct.hasFocus():
            self._pct.setText(f"{pct}%")
        self._apply_style()

    def show_bubble(self, anchor_widget):
            self._anchor = anchor_widget
            self.reposition()
            self.show()
            self.raise_()
    
    def hide_bubble(self):
        if not self.rect().contains(self.mapFromGlobal(self.cursor().pos())):
            self.hide()

    def reposition(self):
        if not self._anchor: return
        # In compact mode the zoom preview sits in the page utilities between
        # the Reload and Site Info buttons, so always anchor the bubble to the
        # indicator widget itself (the URL bar right-side special-case no longer
        # applies).
        global_pos = self._anchor.mapToGlobal(QPoint(self._anchor.width() // 2, 0))
        self.adjustSize()
        x = global_pos.x() - self.width() // 2
        y = global_pos.y() - self.height() - 6
        self.move(x, y)

    def paintEvent(self, event):
        if self._cached_bg is None:
            self._apply_style()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(self._cached_bg)
        painter.setPen(self._cached_border)
        painter.drawRoundedRect(QRectF(rect), 10, 10)


class FindBubble(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._main_window = main_window
        self._match_count = 0
        self._current_match = 0
        self._search_text = ""
        self._cached_bg = None
        self._cached_border = None

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(4)

        self._counter = QLabel("0/0")
        self._counter.setFixedWidth(38)
        self._counter.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Find on page")
        self._input.setFixedWidth(160)
        self._input.textChanged.connect(self._on_text_changed)
        self._input.returnPressed.connect(self._find_next)

        self._prev_btn = QToolButton()
        self._prev_btn.setText("\u25b2")
        self._prev_btn.setFixedSize(26, 26)
        self._prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prev_btn.clicked.connect(self._find_prev)

        self._next_btn = QToolButton()
        self._next_btn.setText("\u25bc")
        self._next_btn.setFixedSize(26, 26)
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.clicked.connect(self._find_next)

        self._close_btn = QToolButton()
        self._close_btn.setText("\u2715")
        self._close_btn.setFixedSize(26, 26)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.clicked.connect(self._close_and_clear)

        row.addWidget(self._counter)
        row.addWidget(self._input)
        row.addWidget(self._prev_btn)
        row.addWidget(self._next_btn)
        row.addWidget(self._close_btn)

        self._init_js()
        self._apply_style()

    def _init_js(self):
        page = self._get_page()
        if not page:
            return
        from PySide6.QtWebEngineCore import QWebEngineScript
        script = QWebEngineScript()
        script.setName("_hn_find_init")
        script.setSourceCode(
            "(function(){"
            "if(!document.getElementById('_hn_find_style')){"
            "var s=document.createElement('style');s.id='_hn_find_style';"
            "s.textContent='::highlight(_hn_find){background:#ffff00;color:#000;}::highlight(_hn_find_active){background:#ff8800;color:#000;}';"
            "document.head.appendChild(s);"
            "}"
            "window._hnRanges=window._hnRanges||[];window._hnIdx=window._hnIdx||-1;"
            "})()"
        )
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        script.setRunsOnSubFrames(True)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        try:
            page.scripts().add(script)
        except:
            pass

    def _get_page(self):
        cur = self._main_window.browser_area.currentWidget()
        if hasattr(cur, 'page'):
            return cur.page()
        return None

    def _on_text_changed(self, text):
        self._search_text = text
        self._do_search(text)

    def _do_search(self, text):
        page = self._get_page()
        if not page:
            self._update_counter(0, 0)
            return
        safe = json.dumps(text)
        js = (
            "(function(t){"
            "if(window.CSS&&CSS.highlights){CSS.highlights.delete('_hn_find');CSS.highlights.delete('_hn_find_active');}"
            "window._hnRanges=[];window._hnIdx=-1;"
            "if(!t)return JSON.stringify({c:0,i:0});"
            "var rgs=[],w=document.createTreeWalker(document.body,4,null,false),ns=[],n;"
            "while(n=w.nextNode())ns.push(n);"
            "var lt=t.toLowerCase();"
            "for(var i=0;i<ns.length;i++){"
            "var node=ns[i],l=node.textContent.toLowerCase(),idx=0;"
            "while((idx=l.indexOf(lt,idx))!==-1){"
            "try{var rg=new Range();rg.setStart(node,idx);rg.setEnd(node,idx+t.length);rgs.push(rg);}catch(e){}"
            "idx+=t.length;"
            "}"
            "}"
            "if(rgs.length&&window.CSS&&CSS.highlights){"
            "var hl=new Highlight();"
            "for(var j=0;j<rgs.length;j++){hl.add(rgs[j]);window._hnRanges.push(rgs[j]);}"
            "CSS.highlights.set('_hn_find',hl);"
            "window._hnIdx=0;"
            "var ar=rgs[0];"
            "var el=ar.startContainer;"
            "if(el.nodeType===3)el=el.parentElement;"
            "if(el)el.scrollIntoView({block:'center'});"
            "}"
            "return JSON.stringify({c:rgs.length,i:window._hnIdx+1});"
            "})(" + safe + ")"
        )
        page.runJavaScript(js, self._on_search_result)

    def _on_search_result(self, result):
        try:
            import json
            data = json.loads(result) if isinstance(result, str) else result
            self._match_count = data["c"]
            self._current_match = data["i"]
        except:
            self._match_count = 0
            self._current_match = 0
        self._update_counter(self._current_match, self._match_count)

    def _find_next(self):
        if not self._search_text:
            return
        self._navigate("n")

    def _find_prev(self):
        if not self._search_text:
            return
        self._navigate("p")

    def _navigate(self, direction):
        page = self._get_page()
        if not page:
            return
        js = (
            "(function(d){"
            "var rgs=window._hnRanges;"
            "if(!rgs||!rgs.length||!window.CSS||!CSS.highlights)return JSON.stringify({c:0,i:0});"
            "CSS.highlights.delete('_hn_find_active');"
            "var t=rgs.length,idx=window._hnIdx;"
            "if(d==='n')idx=(idx+1)%t;else idx=(idx-1+t)%t;"
            "window._hnIdx=idx;"
            "var ar=rgs[idx];"
            "var ahl=new Highlight();ahl.add(ar);CSS.highlights.set('_hn_find_active',ahl);"
            "var el=ar.startContainer;if(el.nodeType===3)el=el.parentElement;"
            "if(el)el.scrollIntoView({block:'center'});"
            "return JSON.stringify({c:t,i:idx+1});"
            "})('" + direction + "')"
        )
        page.runJavaScript(js, self._on_nav_result)

    def _on_nav_result(self, result):
        try:
            import json
            data = json.loads(result) if isinstance(result, str) else result
            self._match_count = data["c"]
            self._current_match = data["i"]
        except:
            pass
        self._update_counter(self._current_match, self._match_count)

    def _update_counter(self, current, total):
        if total == 0:
            self._counter.setText("0/0")
        else:
            self._counter.setText(f"{current}/{total}")

    def _clear_marks(self):
        page = self._get_page()
        if page:
            page.runJavaScript(
                "(function(){"
                "if(window.CSS&&CSS.highlights){CSS.highlights.delete('_hn_find');CSS.highlights.delete('_hn_find_active');}"
                "window._hnRanges=[];window._hnIdx=-1;"
                "})()"
            )

    def _close_and_clear(self):
        self._clear_marks()
        self._search_text = ""
        self.hide()

    def show_below(self, anchor_widget):
        self._match_count = 0
        self._current_match = 0
        self._search_text = ""
        self._counter.setText("0/0")
        self._input.clear()
        self._input.setFocus()
        self.adjustSize()
        global_pos = anchor_widget.mapToGlobal(QPoint(anchor_widget.width() // 2, 0))
        x = global_pos.x() - self.width() // 2
        y = global_pos.y() - self.height() - 6
        self.move(x, y)
        self.show()
        self.raise_()

    def reposition(self):
        if not self.isVisible():
            return
        anchor = self._main_window.url_bar
        if anchor:
            global_pos = anchor.mapToGlobal(QPoint(anchor.width() // 2, 0))
            self.adjustSize()
            x = global_pos.x() - self.width() // 2
            y = global_pos.y() - self.height() - 6
            self.move(x, y)

    def _apply_style(self):
        win = self._main_window
        r, g, b = win.get_accent_rgb()
        is_dark = getattr(win, 'is_dark_mode', True)
        mr, mg, mb = max(r//4, 14), max(g//4, 14), max(b//4, 14)
        text = "#ffffff" if is_dark else "#000000"
        muted = f"rgba({r},{g},{b},140)" if is_dark else f"rgba({r},{g},{b},100)"
        hover_bg = f"rgba({r},{g},{b},40)" if is_dark else f"rgba({r},{g},{b},20)"
        btn_bg = f"rgba({mr+6},{mg+6},{mb+6},180)" if is_dark else "rgba(230,230,235,200)"
        input_bg = f"rgba({mr},{mg},{mb},120)" if is_dark else "rgba(235,235,240,200)"
        if is_dark:
            self._cached_bg = QColor(max(r//3, 10), max(g//3, 10), max(b//3, 10), 240)
            self._cached_border = QColor(min(r//2+30, 255), min(g//2+30, 255), min(b//2+30, 255), 200)
        else:
            self._cached_bg = QColor(min(r+100, 255), min(g+100, 255), min(b+100, 255), 240)
            self._cached_border = QColor(r, g, b, 200)
        self.setStyleSheet(f"""
            FindBubble QLabel {{
                color: {muted}; font-size: 11px; font-weight: 600;
                background: {input_bg}; border-radius: 4px; padding: 0 4px;
                font-family: Consolas, monospace; min-height: 24px; line-height: 24px;
            }}
            FindBubble QLineEdit {{
                color: {text}; font-size: 12px;
                background: {input_bg}; border: 1px solid transparent;
                border-radius: 4px; padding: 0 6px; min-height: 24px;
            }}
            FindBubble QLineEdit:focus {{
                border: 1px solid rgba({r},{g},{b},120);
                background: {btn_bg};
            }}
            FindBubble QLineEdit::placeholder {{
                color: {muted};
            }}
            FindBubble QToolButton {{
                background: {btn_bg}; color: {text}; border: none;
                border-radius: 5px; font-size: 12px; font-weight: 600;
            }}
            FindBubble QToolButton:hover {{ background: {hover_bg}; }}
            FindBubble QToolButton:pressed {{ background: rgba({r},{g},{b},60); }}
        """)

    def paintEvent(self, event):
        if self._cached_bg is None:
            self._apply_style()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(self._cached_bg)
        painter.setPen(self._cached_border)
        painter.drawRoundedRect(QRectF(rect), 10, 10)
