import os
import tempfile
from PySide6.QtCore import Qt, QThread, Signal, QRectF, QTimer
from PySide6.QtGui import QPainter, QPen, QColor, QImage, QPainterPath
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QStackedWidget, QScrollArea, QLabel, QFrame, QLineEdit, QComboBox,
    QPushButton, QMessageBox, QFileDialog, QApplication, QDialog,
    QStyledItemDelegate, QStyle, QGraphicsOpacityEffect
)
from ..ui.widgets.layout import SettingsRow
from ..ui.widgets.buttons import SettingsToggle
from ..ui.components.bubbles import ApplyBubble
from ..utils.oauth import OAuthManager
from ..utils.easing import linear_out, smoothstep

_arrow_cache = {}

def _combo_arrow_path(color_hex):
    """Generate (once) a small down-chevron PNG for the QComboBox drop-down."""
    if color_hex in _arrow_cache:
        return _arrow_cache[color_hex]
    w, h = 10, 6
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(color_hex), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    path.moveTo(1, 0.6)
    path.lineTo(5, 4.6)
    path.lineTo(9, 0.6)
    p.drawPath(path)
    p.end()
    f = os.path.join(tempfile.gettempdir(), f"hn_combo_chevron_{color_hex.lstrip('#')}.png").replace("\\", "/")
    img.save(f)
    _arrow_cache[color_hex] = f
    return f

class UserInfoWorker(QThread):
    finished = Signal(dict, str)

    def __init__(self, manager, provider):
        super().__init__()
        self.manager = manager
        self.provider = provider

    def run(self):
        if self.provider == 'google':
            info = self.manager.get_google_user_info()
        else:
            info = self.manager.get_microsoft_user_info()
        self.finished.emit(info or {}, self.provider)

class FolderListWorker(QThread):
    finished = Signal(dict)

    def __init__(self, manager, provider, parent_id):
        super().__init__()
        self.manager = manager
        self.provider = provider
        self.parent_id = parent_id

    def run(self):
        if self.provider == 'google':
            result = self.manager.list_google_drive_folders(self.parent_id)
        else:
            result = self.manager.list_onedrive_folders(self.parent_id)
        self.finished.emit(result)

class CloudFolderDialog(QDialog):
    """Browse and select a folder inside a connected cloud storage account."""

    def __init__(self, oauth_manager, provider, parent=None):
        super().__init__(parent)
        self.oauth_manager = oauth_manager
        self.provider = provider
        self.selected_id = None
        self.selected_name = None
        self._path = [(("My Drive" if provider == "google" else "OneDrive"), None)]
        self._loading = False

        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setFixedSize(420, 420)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        mw = getattr(parent, 'main_window', None) or parent if parent else None
        is_dark = getattr(mw, 'is_dark_mode', True) if mw else True
        accent = mw.get_accent_color_hex() if mw and hasattr(mw, 'get_accent_color_hex') else "#558EFF"
        hover_accent = mw.get_accent_hover_color_hex() if mw and hasattr(mw, 'get_accent_hover_color_hex') else "#6697FF"
        r, g, b = mw.get_accent_rgb() if mw and hasattr(mw, 'get_accent_rgb') else (85, 142, 255)

        dr, dg, db = max(r // 6, 8), max(g // 6, 8), max(b // 6, 8)
        bg = f"rgb({dr},{dg},{db})" if is_dark else "#f0f0f5"
        text = "#ffffff" if is_dark else "#000000"
        muted = "#888E99" if is_dark else "#676D78"
        border = f"rgba({r // 3},{g // 3},{b // 3},180)" if is_dark else "#c8c8d0"

        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        panel = QFrame()
        panel.setObjectName("cloudPanel")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(20, 18, 20, 18)
        pl.setSpacing(12)

        head = QHBoxLayout()
        ttl = QLabel(f"Select folder in {('Google Drive' if provider == 'google' else 'OneDrive')}")
        ttl.setObjectName("cloudTitle")
        head.addWidget(ttl, 1)
        close_x = QPushButton("\u2715")
        close_x.setObjectName("cloudClose")
        close_x.setCursor(Qt.CursorShape.PointingHandCursor)
        close_x.setFixedSize(22, 22)
        close_x.clicked.connect(self.reject)
        head.addWidget(close_x)
        pl.addLayout(head)

        self.path_label = QLabel()
        self.path_label.setObjectName("cloudPath")
        self.path_label.setWordWrap(True)
        pl.addWidget(self.path_label)

        self.folder_list = QListWidget()
        self.folder_list.setObjectName("cloudList")
        self.folder_list.itemActivated.connect(lambda item: self._enter_folder(item))
        pl.addWidget(self.folder_list, 1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("cloudStatus")
        pl.addWidget(self.status_label)

        btns = QHBoxLayout()
        btns.setSpacing(10)
        up_btn = QPushButton("\u2191  Up")
        up_btn.setObjectName("cloudUp")
        up_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        up_btn.clicked.connect(self._go_up)
        btns.addWidget(up_btn)
        btns.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cloudCancel")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        select_btn = QPushButton("Select this folder")
        select_btn.setObjectName("cloudSelect")
        select_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        select_btn.clicked.connect(self._accept_current)
        btns.addWidget(cancel_btn)
        btns.addWidget(select_btn)
        pl.addLayout(btns)

        root.addWidget(panel)

        self.setStyleSheet(f"""
            QFrame#cloudPanel {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 14px;
            }}
            QLabel#cloudTitle {{ color: {text}; font-size: 15px; font-weight: 700; background: transparent; }}
            QLabel#cloudPath {{ color: {accent}; font-size: 12px; background: transparent; }}
            QLabel#cloudStatus {{ color: {muted}; font-size: 12px; background: transparent; }}
            QPushButton#cloudClose {{
                background: transparent; color: {muted}; border: none;
                font-size: 11px; border-radius: 6px;
            }}
            QPushButton#cloudClose:hover {{
                background: {"rgba(255,255,255,10)" if is_dark else "rgba(0,0,0,8)"};
                color: {text};
            }}
            QListWidget#cloudList {{
                background: {bg}; border: 1px solid {border}; border-radius: 10px;
                color: {text}; font-size: 13px; padding: 6px; outline: none;
            }}
            QListWidget#cloudList::item {{ padding: 9px 10px; border-radius: 6px; }}
            QListWidget#cloudList::item:hover {{ background: {"rgba(255,255,255,8)" if is_dark else "rgba(0,0,0,6)"}; }}
            QListWidget#cloudList::item:selected {{ background: {accent}; color: #ffffff; }}
            QPushButton#cloudUp {{
                background: transparent; color: {muted}; border: 1px solid {border};
                border-radius: 8px; padding: 8px 16px; font-weight: 600; font-size: 12px;
            }}
            QPushButton#cloudUp:hover {{ color: {text}; border-color: {accent}; }}
            QPushButton#cloudCancel {{
                background: transparent; color: {muted}; border: 1px solid {border};
                border-radius: 8px; padding: 8px 18px; font-weight: 600; font-size: 12px;
            }}
            QPushButton#cloudCancel:hover {{ color: {text}; }}
            QPushButton#cloudSelect {{
                background: {accent}; color: #ffffff; border: none;
                border-radius: 8px; padding: 9px 18px; font-weight: 700; font-size: 12px;
            }}
            QPushButton#cloudSelect:hover {{ background: {hover_accent}; }}
        """)

        self._refresh_path()
        self._load_folders()

    def _refresh_path(self):
        names = [n for n, _ in self._path]
        self.path_label.setText("  /  ".join(names))

    def _set_loading(self, loading):
        self._loading = loading
        self.folder_list.setEnabled(not loading)
        if loading:
            self.status_label.setText("Loading folders\u2026")
        else:
            self.status_label.setText("Double-click a folder to enter it, then confirm.")

    def _load_folders(self):
        self._set_loading(True)
        self.folder_list.clear()
        current_id = self._path[-1][1]
        self._worker = FolderListWorker(self.oauth_manager, self.provider, current_id)
        self._worker.finished.connect(self._on_folders_loaded)
        self._worker.start()

    def _on_folders_loaded(self, result):
        self._set_loading(False)
        if result.get('error'):
            self.status_label.setText(f"Error: {result['error']}")
            return
        self.folder_list.clear()
        for f in result.get('folders', []):
            item = QListWidgetItem(f"\U0001F4C1  {f['name']}")
            item.setData(Qt.ItemDataRole.UserRole, f['id'])
            self.folder_list.addItem(item)

    def _enter_folder(self, item):
        if self._loading:
            return
        folder_id = item.data(Qt.ItemDataRole.UserRole)
        name = item.text().split("  ", 1)[1]
        self._path.append((name, folder_id))
        self._refresh_path()
        self._load_folders()

    def _go_up(self):
        if self._loading or len(self._path) <= 1:
            return
        self._path.pop()
        self._refresh_path()
        self._load_folders()

    def _accept_current(self):
        if self._loading:
            return
        self.selected_id = self._path[-1][1]
        self.selected_name = self._path[-1][0]
        self.accept()

class AppearancePreview(QWidget):
    """Miniature HoverNet chrome reflecting the pending appearance settings.

    Only draws what the style settings actually affect: the floating island,
    tabs, nav/url row, tools pill, title-bar strip, and the settings page +
    sidebar it floats over.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(240, 150)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._accent = (85, 142, 255)
        self._is_dark = True
        self._custom_title_bar = True
        self._layout_style = "standard"
        self._ws_btn = True
        self._preview_effect = None
        self._crossfade_pixmap = None
        self._crossfade_opacity = 0.0
        self._crossfade_timer = QTimer(self)
        self._crossfade_timer.timeout.connect(self._crossfade_step)
        self._crossfade_timer.setInterval(16)
        self._crossfade_step_size = 1.0 / 10.0

    def set_state(self, accent=None, is_dark=None, custom_title_bar=None,
                  layout_style=None, ws_btn=None):
        if self.isVisible() and self._preview_effect is None:
            self._preview_effect = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(self._preview_effect)
            self._preview_effect.setOpacity(1.0)

        new = {}
        if accent is not None and accent != self._accent:
            new['_accent'] = accent
        if is_dark is not None and is_dark != self._is_dark:
            new['_is_dark'] = is_dark
        if custom_title_bar is not None and custom_title_bar != self._custom_title_bar:
            new['_custom_title_bar'] = custom_title_bar
        if layout_style is not None and layout_style != self._layout_style:
            new['_layout_style'] = layout_style
        if ws_btn is not None and ws_btn != self._ws_btn:
            new['_ws_btn'] = ws_btn

        if not new:
            self.update()
            return

        if not self.isVisible() or self._preview_effect is None:
            # First paint / popup preview: apply instantly.
            for k, v in new.items():
                setattr(self, k, v)
            if self._preview_effect is not None:
                self._preview_effect.setOpacity(1.0)
            self.update()
            return

        # Animated change: true crossfade. Snapshot the current look, apply the
        # new state underneath, then fade the old snapshot out on top so the two
        # looks blend instead of the preview dipping fully transparent.
        self._crossfade_pixmap = self.grab()
        self._crossfade_opacity = 1.0
        for k, v in new.items():
            setattr(self, k, v)
        self.update()
        if not self._crossfade_timer.isActive():
            self._crossfade_timer.start()

    def _crossfade_step(self):
        self._crossfade_opacity -= self._crossfade_step_size
        if self._crossfade_opacity <= 0.0:
            self._crossfade_opacity = 0.0
            self._crossfade_pixmap = None
            self._crossfade_timer.stop()
        self.update()

    def _rrect(self, p, x, y, w, h, rad, color, pen=None):
        p.setPen(pen or Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(QRectF(x, y, w, h), rad, rad)

    @staticmethod
    def _bar_path(x, y, w, h, tl, tr, bl, br):
        path = QPainterPath()
        path.moveTo(x + tl, y)
        path.lineTo(x + w - tr, y)
        path.arcTo(x + w - 2 * tr, y, 2 * tr, 2 * tr, 90.0, -90.0)
        path.lineTo(x + w, y + h - br)
        path.arcTo(x + w - 2 * br, y + h - 2 * br, 2 * br, 2 * br, 0.0, -90.0)
        path.lineTo(x + bl, y + h)
        path.arcTo(x, y + h - 2 * bl, 2 * bl, 2 * bl, -90.0, -90.0)
        path.lineTo(x, y + tl)
        path.arcTo(x, y, 2 * tl, 2 * tl, 180.0, -90.0)
        path.closeSubpath()
        return path

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        r, g, b = self._accent
        W, H = float(self.width()), float(self.height())
        dark = self._is_dark

        accent = QColor(r, g, b)
        accent_border = QColor(max(r // 3, 14), max(g // 3, 14), max(b // 3, 14))
        text_hi = QColor("#ffffff") if dark else QColor("#111122")
        muted = QColor("#8E99AD") if dark else QColor("#7A8090")

        win_bg = QColor(max(r // 7, 8), max(g // 7, 8), max(b // 7, 8)) if dark else QColor("#f1f1f6")
        island_bg = QColor(max(r // 4, 14), max(g // 4, 14), max(b // 4, 14)) if dark else QColor("#f8f8fb")
        side_bg = QColor(max(r // 5, 10), max(g // 5, 10), max(b // 5, 10)) if dark else QColor("#e7e7ef")
        card_bg = QColor(max(r // 4 + 10, 20), max(g // 4 + 10, 20), max(b // 4 + 10, 20)) if dark else QColor("#ffffff")
        chrome = accent if self._custom_title_bar else (QColor(58, 58, 70) if dark else QColor(210, 210, 218))

        # Window frame + background (theme/accent)
        self._rrect(p, 1.5, 1.5, W - 3, H - 3, 12, win_bg, QPen(accent, 2))

        # Chrome strip (custom vs native title bar) — a full-width rectangle
        # clipped to the rounded window mask so it stays inside the frame.
        p.save()
        mask = QPainterPath()
        mask.addRoundedRect(QRectF(1.5, 1.5, W - 3, H - 3), 12, 12)
        p.setClipPath(mask)
        p.fillRect(QRectF(0, 0, W, 10), chrome)
        p.restore()

        # Floating island — anchored at the bottom, like the real window
        ix, iw = 8.0, W - 16.0
        ibottom = H - 8.0
        iheight = 40.0 if self._layout_style == "standard" else 22.0
        itop = ibottom - iheight
        self._rrect(p, ix, itop, iw, iheight, 8, island_bg)
        p.setPen(QPen(accent_border, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(ix, itop, iw, iheight), 8, 8)

        if self._layout_style == "standard":
            # ── Tab row: connected bars (adaptive roundness) + new-tab ──
            ty = itop + 3
            bh = 13.0
            fill_a = QColor(accent)
            fill_a.setAlpha(45)
            p.setPen(QPen(accent, 1))
            p.setBrush(fill_a)
            p.drawPath(self._bar_path(11, ty + 1, 60, bh, 6.5, 4.0, 6.5, 4.0))  # active (neighbor right)
            fill_m = QColor(muted)
            fill_m.setAlpha(40)
            p.setPen(QPen(muted, 1))
            p.setBrush(fill_m)
            p.drawPath(self._bar_path(71, ty + 1, 60, bh, 4.0, 6.5, 4.0, 6.5))  # inactive (rightmost)
            p.setPen(QPen(muted, 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(W - 22, ty + 1.5, 12, 12))                     # new-tab (circle)

            # ── Bottom row: nav pill · url · buttons (right side) ──
            by = itop + 21
            p.setPen(QPen(accent, 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(11, by + 1, 24, 12), 6, 6)            # nav pill
            p.setBrush(text_hi)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(16, by + 5, 3.5, 3.5), 1.5, 1.5)       # back
            p.drawRoundedRect(QRectF(25, by + 5, 3.5, 3.5), 1.5, 1.5)       # forward

            p.setPen(QPen(accent_border, 1))
            p.setBrush(island_bg.lighter(108))
            p.drawRoundedRect(QRectF(38, by, 110, 14), 7, 7)                # url capsule
            p.setBrush(accent)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(44, by + 5, 4, 4), 2, 2)               # favicon

            p.setBrush(muted)                                               # site info + refresh
            p.drawRoundedRect(QRectF(154, by + 5, 3.5, 3.5), 1.5, 1.5)
            p.drawRoundedRect(QRectF(161, by + 5, 3.5, 3.5), 1.5, 1.5)

            p.setPen(QPen(accent_border, 1))                                # tools pill
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(168, by + 1, 36, 12), 6, 6)
            p.setBrush(text_hi)
            p.setPen(Qt.PenStyle.NoPen)
            tp_x = 173
            p.drawRoundedRect(QRectF(tp_x, by + 5, 3.5, 3.5), 1.5, 1.5)     # home
            if self._ws_btn:
                p.drawRoundedRect(QRectF(tp_x + 7, by + 5, 3.5, 3.5), 1.5, 1.5)   # ws
            p.drawRoundedRect(QRectF(tp_x + 14, by + 5, 3.5, 3.5), 1.5, 1.5)      # printy
            p.drawRoundedRect(QRectF(tp_x + 21, by + 5, 3.5, 3.5), 1.5, 1.5)      # tools
        else:
            # ── Compact: unified capsule + tools ──
            cy = itop + 3
            p.setPen(QPen(accent_border, 1))
            p.setBrush(island_bg.lighter(108))
            p.drawRoundedRect(QRectF(11, cy, 150, 15), 7.5, 7.5)            # unified capsule

            p.setBrush(text_hi)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(17, cy + 5.5, 3.5, 3.5), 1.5, 1.5)      # back
            p.drawRoundedRect(QRectF(24, cy + 5.5, 3.5, 3.5), 1.5, 1.5)      # forward
            p.setBrush(muted)
            p.drawRoundedRect(QRectF(31, cy + 3, 1, 9), 0.5, 0.5)            # sep

            # connected bars (adaptive roundness) + new-tab
            fill_a = QColor(accent)
            fill_a.setAlpha(45)
            p.setPen(QPen(accent, 1))
            p.setBrush(fill_a)
            p.drawPath(self._bar_path(40, cy + 2.5, 26, 10, 5.0, 3.0, 5.0, 3.0))  # active chip (neighbor right)
            fill_m = QColor(muted)
            fill_m.setAlpha(40)
            p.setPen(QPen(muted, 1))
            p.setBrush(fill_m)
            p.drawPath(self._bar_path(66, cy + 2.5, 18, 10, 3.0, 5.0, 3.0, 5.0))  # inactive chip (rightmost)
            p.setPen(QPen(muted, 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(92, cy + 4, 8, 8))                               # new-tab (circle)

            p.setPen(QPen(accent_border, 1))                                 # tools pill
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(165, cy + 1, 30, 13), 6.5, 6.5)
            p.setBrush(text_hi)
            p.setPen(Qt.PenStyle.NoPen)
            tp_x = 170
            p.drawRoundedRect(QRectF(tp_x, cy + 5.5, 3.5, 3.5), 1.5, 1.5)
            if self._ws_btn:
                p.drawRoundedRect(QRectF(tp_x + 6, cy + 5.5, 3.5, 3.5), 1.5, 1.5)
            p.drawRoundedRect(QRectF(tp_x + 12, cy + 5.5, 3.5, 3.5), 1.5, 1.5)
            p.drawRoundedRect(QRectF(tp_x + 18, cy + 5.5, 3.5, 3.5), 1.5, 1.5)

        # ── Settings page content: sidebar + card backgrounds (no text) ──
        cy = 13.0
        ch = max(itop - 6 - cy, 20.0)

        self._rrect(p, 11, cy, 44, ch, 6, side_bg)                            # sidebar
        self._rrect(p, 16, cy + 6, 34, 8, 4, accent)                          # active item
        p.setBrush(muted)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(3):
            p.drawRoundedRect(QRectF(16, cy + 19 + i * 9, 26, 5), 2, 2)       # other items

        self._rrect(p, 61, cy, W - 72, ch, 6, card_bg)                        # content card
        self._rrect(p, 69, cy + 7, 64, 7, 3, accent)                          # heading block
        p.setPen(QPen(accent_border, 1))                                       # combo row
        p.setBrush(card_bg.darker(104) if dark else card_bg)
        p.drawRoundedRect(QRectF(69, cy + 22, 66, 10), 5, 5)
        p.setBrush(accent)
        p.setPen(Qt.PenStyle.NoPen)
        chev = QPainterPath()                                                 # dropdown chevron (linear)
        chev.moveTo(121, cy + 24.5)
        chev.lineTo(123.5, cy + 27.5)
        chev.lineTo(126, cy + 24.5)
        p.setPen(QPen(accent, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(chev)
        self._rrect(p, 69, cy + 40, 15, 7, 3.5, accent)                        # toggle on
        p.setBrush(QColor("#ffffff") if dark else QColor("#e9e9f0"))
        p.drawEllipse(QRectF(78, cy + 40.5, 6, 6))                            # knob right

        # Crossfade: old look fading out over the newly-painted state.
        if self._crossfade_pixmap is not None and self._crossfade_opacity > 0.0:
            p.save()
            p.setOpacity(self._crossfade_opacity)
            p.drawPixmap(0, 0, self._crossfade_pixmap)
            p.restore()


class UnsavedChangesPopup(QDialog):
    """Custom popup warning about unsaved appearance changes.

    Offers Apply / Discard / Keep editing, alongside a small window preview.
    """
    RESULT_APPLY = 1
    RESULT_DISCARD = 2
    RESULT_KEEP = 3

    def __init__(self, settings_view):
        super().__init__(settings_view)
        self._view = settings_view
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setFixedSize(360, 330)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        mw = settings_view.main_window
        r, g, b = mw.get_accent_rgb()
        is_dark = getattr(mw, 'is_dark_mode', True)
        accent = mw.get_accent_color_hex()
        hover_accent = mw.get_accent_hover_color_hex()

        dr, dg, db = max(r // 6, 8), max(g // 6, 8), max(b // 6, 8)
        bg = f"rgb({dr},{dg},{db})" if is_dark else "#f0f0f5"
        text = "#ffffff" if is_dark else "#000000"
        muted = "#888E99" if is_dark else "#676D78"
        border = f"rgba({r // 3},{g // 3},{b // 3},180)" if is_dark else "#c8c8d0"

        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        panel = QFrame()
        panel.setObjectName("popupPanel")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(18, 16, 18, 18)
        pl.setSpacing(12)

        head = QHBoxLayout()
        ttl = QLabel("Unsaved changes")
        ttl.setObjectName("popupTitle")
        head.addWidget(ttl, 1)
        close_x = QPushButton("\u2715")
        close_x.setObjectName("popupClose")
        close_x.setCursor(Qt.CursorShape.PointingHandCursor)
        close_x.setFixedSize(22, 22)
        close_x.clicked.connect(lambda: self.done(self.RESULT_KEEP))
        head.addWidget(close_x)
        pl.addLayout(head)

        msg = QLabel("You have unsaved appearance changes.\n"
                     "Apply them, or discard and keep the current look?")
        msg.setObjectName("popupText")
        msg.setWordWrap(True)
        pl.addWidget(msg)

        preview = AppearancePreview()
        preview.set_state(
            accent=settings_view._preview_accent_rgb(),
            is_dark=settings_view._preview_is_dark(),
            custom_title_bar=settings_view._preview_custom_title_bar(),
            layout_style=settings_view._preview_layout_style(),
            ws_btn=settings_view._preview_ws_btn(),
        )
        pwrap = QHBoxLayout()
        pwrap.addStretch(1)
        pwrap.addWidget(preview)
        pwrap.addStretch(1)
        pl.addLayout(pwrap)

        btns = QHBoxLayout()
        btns.setSpacing(10)
        discard = QPushButton("Discard")
        discard.setObjectName("popupDiscard")
        discard.setCursor(Qt.CursorShape.PointingHandCursor)
        discard.clicked.connect(lambda: self.done(self.RESULT_DISCARD))
        apply_btn = QPushButton("Apply changes")
        apply_btn.setObjectName("popupApply")
        apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_btn.clicked.connect(lambda: self.done(self.RESULT_APPLY))
        btns.addWidget(discard, 1)
        btns.addWidget(apply_btn, 1)
        pl.addLayout(btns)

        root.addWidget(panel)

        self.setStyleSheet(f"""
            QFrame#popupPanel {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 14px;
            }}
            QLabel#popupTitle {{ color: {text}; font-size: 15px; font-weight: 700; background: transparent; }}
            QLabel#popupText {{ color: {muted}; font-size: 12px; background: transparent; }}
            QPushButton#popupClose {{
                background: transparent; color: {muted}; border: none;
                font-size: 11px; border-radius: 6px;
            }}
            QPushButton#popupClose:hover {{
                background: {"rgba(255,255,255,10)" if is_dark else "rgba(0,0,0,8)"};
                color: {text};
            }}
            QPushButton#popupApply {{
                background: {accent}; color: #ffffff; border: none;
                border-radius: 8px; padding: 9px 14px; font-weight: 700; font-size: 12px;
            }}
            QPushButton#popupApply:hover {{ background: {hover_accent}; }}
            QPushButton#popupDiscard {{
                background: {"rgba(120,120,140,40)" if is_dark else "#e4e4ec"};
                color: {text}; border: none; border-radius: 8px;
                padding: 9px 14px; font-weight: 600; font-size: 12px;
            }}
            QPushButton#popupDiscard:hover {{
                background: {"rgba(239,68,68,60)" if is_dark else "#fbdada"};
                color: {"#ff6b6b" if is_dark else "#c0392b"};
            }}
        """)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.done(self.RESULT_KEEP)
        else:
            super().keyPressEvent(event)

class AnimatedSidebarDelegate(QStyledItemDelegate):
    """Delegate that paints the settings sidebar items so the active page
    highlight can animate. The active background eases in/out smoothly
    (smoothstep), while the active text uses linear + ease-out."""

    def paint(self, painter, option, index):
        sidebar = self.parent()
        cur = sidebar.currentRow()
        prev = getattr(sidebar, '_anim_prev_row', cur)
        progress = getattr(sidebar, '_anim_progress', 1.0)
        row = index.row()

        accent = sidebar._sidebar_accent
        text_base = sidebar._sidebar_text
        hover_text = sidebar._sidebar_hover_text
        is_dark = sidebar._sidebar_is_dark

        rect = option.rect.adjusted(15, 3, -15, -3)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        transitioning = (prev != cur)
        if row == cur:
            sel_p = smoothstep(progress) if transitioning else 1.0
        elif row == prev and transitioning:
            sel_p = 1.0 - smoothstep(progress)
        else:
            sel_p = 0.0

        if row == cur:
            text_p = linear_out(progress) if transitioning else 1.0
        else:
            text_p = 0.0

        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver) and sel_p < 0.5 and row != cur

        if sel_p > 0.001:
            bg = QColor(accent)
            bg.setAlphaF(0.08 * sel_p)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(QRectF(rect), 10, 10)
        elif hovered:
            bg = QColor(255, 255, 255, 5) if is_dark else QColor(0, 0, 0, 8)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(QRectF(rect), 10, 10)

        text_rect = rect.adjusted(3, 0, -3, 0)
        f = option.font
        f.setBold(sel_p > 0.5)
        painter.setFont(f)

        c_base = QColor(text_base)
        c_accent = QColor(accent)
        color = QColor(
            int(c_base.red() + (c_accent.red() - c_base.red()) * text_p),
            int(c_base.green() + (c_accent.green() - c_base.green()) * text_p),
            int(c_base.blue() + (c_accent.blue() - c_base.blue()) * text_p),
        )
        painter.setPen(color)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         index.data())
        painter.restore()


class AnimatedSettingsSidebar(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._anim_prev_row = 0
        self._anim_progress = 1.0
        self._anim_step = 1.0 / 14.0
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._step_anim)
        self._anim_timer.setInterval(16)
        self._sidebar_accent = QColor(85, 142, 255)
        self._sidebar_text = QColor("#8791AA")
        self._sidebar_hover_text = QColor("#ffffff")
        self._sidebar_is_dark = True
        self.viewport().setMouseTracking(True)

    def begin_selection_transition(self, from_row, to_row):
        if to_row == from_row:
            return
        self._anim_prev_row = from_row if from_row != -1 else to_row
        self._anim_progress = 0.0
        self._anim_timer.start()
        self.viewport().update()

    def _step_anim(self):
        self._anim_progress += self._anim_step
        if self._anim_progress >= 1.0:
            self._anim_progress = 1.0
            self._anim_timer.stop()
        self.viewport().update()


class SettingsView(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setObjectName("settingsPage")
        self._cards = []  # track all card frames for direct style updates
        self._current_section = 0
        self._appearance = {}  # staged appearance changes (applied only on Apply)
        self._apply_bubble = ApplyBubble(main_window)
        
        # Main layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Sidebar
        self.sidebar = AnimatedSettingsSidebar()
        self.sidebar.setFixedWidth(240)
        self.sidebar.setObjectName("settingsSidebar")
        self._sidebar_delegate = AnimatedSidebarDelegate(self.sidebar)
        self.sidebar.setItemDelegate(self._sidebar_delegate)
        self.sidebar.entered.connect(lambda idx: self.sidebar.viewport().update())
        
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
            
        self.sidebar.currentRowChanged.connect(self._on_sidebar_row_changed)
        
        # Content Area (Stacked widget containing scroll areas)
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("settingsContent")
        
        self.setup_pages()
        
        layout.addWidget(self.sidebar)
        layout.addWidget(self.content_stack)
        
        self.sidebar.setCurrentRow(0)
        self.apply_styles()

    def apply_styles(self):
        accent = self.main_window.get_accent_color_hex() if hasattr(self.main_window, 'get_accent_color_hex') else "#558EFF"
        hover_accent = self.main_window.get_accent_hover_color_hex() if hasattr(self.main_window, 'get_accent_hover_color_hex') else "#6697FF"
        combo_arrow = _combo_arrow_path(accent)
        r, g, b = (85, 142, 255)
        if hasattr(self.main_window, 'get_accent_rgb'):
            r, g, b = self.main_window.get_accent_rgb()

        is_dark = getattr(self.main_window, 'is_dark_mode', True)
        
        # Compute accent-derived dark shades
        dr, dg, db = max(r//6, 8), max(g//6, 8), max(b//6, 8)    # very dark tint
        mr, mg, mb = max(r//4, 14), max(g//4, 14), max(b//4, 14)  # mid dark tint
        
        bg_page = f"rgb({dr},{dg},{db})" if is_dark else "#f0f0f5"
        bg_sidebar = f"rgb({mr},{mg},{mb})" if is_dark else "#e0e0e8"
        border_sidebar = f"rgba({r//3},{g//3},{b//3},200)" if is_dark else "#d0d0d8"
        text_sidebar = "#8791AA" if is_dark else "#676D78"
        text_sidebar_hover = "#ffffff" if is_dark else "#000000"

        # Feed the animated sidebar its colors (the delegate paints items now)
        self.sidebar._sidebar_accent = QColor(accent)
        self.sidebar._sidebar_text = QColor(text_sidebar)
        self.sidebar._sidebar_hover_text = QColor(text_sidebar_hover)
        self.sidebar._sidebar_is_dark = is_dark
        
        bg_card = f"rgba({max(mr+8,20)},{max(mg+8,20)},{max(mb+8,20)},255)" if is_dark else "rgba(255, 255, 255, 255)"
        text_title = "#ffffff" if is_dark else "#000000"
        text_normal = "#ffffff" if is_dark else "#111122"
        
        bg_input = f"rgba({dr},{dg},{db},200)" if is_dark else "rgba(245, 245, 250, 200)"
        bg_input_focus = f"rgba({mr},{mg},{mb},255)" if is_dark else "rgba(255, 255, 255, 255)"
        
        bg_scroll_stop0 = f"rgb({dr},{dg},{db})" if is_dark else "#f0f0f5"
        
        rel_notes_color = "#99ABBB" if is_dark else "#445566"
        rel_notes_bg = "rgba(0, 0, 0, 40)" if is_dark else "rgba(0, 0, 0, 10)"

        self.setStyleSheet(f"""
            QWidget#settingsPage {{
                background-color: {bg_page};
            }}
            QListWidget#settingsSidebar {{
                background-color: {bg_sidebar};
                border: none;
                border-right: 1px solid {border_sidebar};
                padding: 40px 15px;
                color: {text_sidebar};
                font-size: 14px;
                outline: none;
            }}
            
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QWidget#scrollContainer {{
                background: qlineargradient(
                    x1:0, y1:0, x0:0, y1:1,
                    stop:0 {bg_scroll_stop0},
                    stop:1 {"rgba(" + str(r) + "," + str(g) + "," + str(b) + ",18)" if is_dark else "#e8e8f0"}
                );
            }}
            
            /* Section Card Styling */
            QFrame[class="settingsCard"] {{
                background-color: {bg_card};
                border-radius: 16px;
            }}
            QLabel[class="cardTitle"] {{
                color: {text_title};
                font-size: 28px;
                font-weight: 800;
                padding-bottom: 15px;
                background: transparent;
            }}
            
            QLabel[class="rowTitle"] {{
                color: {text_title};
                font-size: 14px;
                font-weight: 600;
                background: transparent;
            }}
            
            QLabel[class="rowDesc"] {{
                color: {text_sidebar};
                font-size: 12px;
                background: transparent;
            }}
            
            QWidget#settingsPage QLineEdit {{
                background-color: {bg_input};
                border: none;
                border-radius: 8px;
                padding: 10px 14px;
                color: {text_normal};
                font-size: 13px;
                min-width: 280px;
            }}
            QWidget#settingsPage QLineEdit:focus {{
                background-color: {bg_input_focus};
            }}

            QWidget#settingsPage QComboBox {{
                background-color: {bg_input};
                border: 1px solid {border_sidebar};
                border-radius: 8px;
                padding: 8px 14px;
                color: {text_normal};
                font-size: 13px;
                min-width: 280px;
            }}
            QWidget#settingsPage QComboBox:hover {{ background-color: {bg_input_focus}; }}
            QWidget#settingsPage QComboBox::drop-down {{
                border: none;
                width: 26px;
                subcontrol-origin: padding;
                subcontrol-position: center right;
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
            }}
            QWidget#settingsPage QComboBox::down-arrow {{
                image: url({combo_arrow});
                width: 10px;
                height: 6px;
            }}
            QWidget#settingsPage QComboBox QAbstractItemView {{
                background-color: {bg_input_focus};
                border: 1px solid {border_sidebar};
                border-radius: 8px;
                padding: 4px;
                color: {text_normal};
                selection-background-color: {accent};
                selection-color: #ffffff;
                outline: none;
            }}
            QWidget#settingsPage QComboBox QAbstractItemView::item {{
                padding: 7px 10px;
                border-radius: 4px;
            }}
            QWidget#settingsPage QComboBox QAbstractItemView::item:hover {{
                background: {"rgba(255,255,255,8)" if is_dark else "rgba(0,0,0,6)"};
            }}
            
            QPushButton.actionButton {{
                background: {accent};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: 700;
                font-size: 13px;
            }}
            QPushButton.actionButton:hover {{
                background: {hover_accent};
            }}
            QPushButton.actionButton:pressed {{
                background: {accent};
            }}
            
            QLabel#relNotes {{
                color: {rel_notes_color};
                font-family: 'Consolas', monospace;
                font-size: 12px;
                background: {rel_notes_bg};
                padding: 20px;
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 10);
            }}
            
            QFrame#appearanceBar {{
                background: {rel_notes_bg};
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 10);
            }}
            QLabel#appearanceHint {{
                color: {text_sidebar}; font-size: 12px; background: transparent;
            }}
            QLabel#cloudFolderVal {{
                color: {text_normal}; font-size: 13px; background: transparent;
            }}
            QPushButton#barApply {{
                background: {accent}; color: #ffffff; border: none;
                border-radius: 8px; padding: 8px 22px; font-weight: 700; font-size: 12px;
            }}
            QPushButton#barApply:hover {{ background: {hover_accent}; }}
            QPushButton#barDiscard {{
                background: transparent; color: {text_sidebar};
                border: 1px solid {border_sidebar}; border-radius: 8px;
                padding: 8px 18px; font-weight: 600; font-size: 12px;
            }}
            QPushButton#barDiscard:hover {{
                color: #ff6b6b; border-color: rgba(239, 68, 68, 180);
                background: rgba(239, 68, 68, 30);
            }}
        """)
        
        # Directly style all tracked cards (QFrame[class=] selector is not always reliable)
        card_style = f"background-color: {bg_card}; border-radius: 16px;"
        for card in self._cards:
            card.setStyleSheet(f"QFrame {{ {card_style} }}")
        
        # Force styles to reapply to all instantiated child widgets instantly
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
        for child in self.findChildren(QWidget):
            child.style().unpolish(child)
            child.style().polish(child)
            child.update()

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
        self._cards.append(card)
        return card, layout

    def setup_pages(self):
        # 1. Appearance
        pg_app, l_app = self._make_page("Appearance")
        card, cl = self._make_card()

        # Live preview of the pending appearance
        preview_row = QHBoxLayout()
        preview_row.setSpacing(12)
        self.appearance_preview = AppearancePreview()
        self._update_preview()
        preview_row.addWidget(self.appearance_preview)
        cl.addLayout(preview_row)

        self._sw_title = SettingsToggle()
        self._sw_title.setChecked(self.main_window.use_custom_title_bar)
        self._sw_title.toggled.connect(lambda c: self._stage_appearance('custom_title_bar', c))
        cl.addWidget(SettingsRow("Custom Title Bar", "Uses the custom HoverNet title bar, which is still experimental.", self._sw_title))
        
        self._sw_ws = SettingsToggle()
        self._sw_ws.setChecked(self.main_window.show_ws_btn)
        self._sw_ws.toggled.connect(lambda c: self._stage_appearance('ws_btn', c))
        cl.addWidget(SettingsRow("Show WS Button", "Display the WS/whenthe's space redirect button in the navigation toolbar.", self._sw_ws))
        
        # Browser Theme
        self.browser_theme_cb = QComboBox()
        self.browser_theme_cb.addItems(["Dark", "Light", "System"])
        current_theme = getattr(self.main_window, 'browser_theme', "System")
        self.browser_theme_cb.setCurrentText(current_theme)
        self.browser_theme_cb.currentTextChanged.connect(lambda t: self._stage_appearance('browser_theme', t))
        cl.addWidget(SettingsRow("Browser Theme", "Choose the color theme for the browser interface.", self.browser_theme_cb))
        
        # Layout Style
        self.layout_style_cb = QComboBox()
        self.layout_style_cb.addItems(["Standard", "Compact"])
        current_style = getattr(self.main_window, 'layout_style', "standard")
        self.layout_style_cb.setCurrentText(current_style.capitalize())
        self.layout_style_cb.currentTextChanged.connect(lambda s: self._stage_appearance('layout_style', s.lower()))
        cl.addWidget(SettingsRow("Layout Style", "Switch between Standard (two-row) and Compact (unified single-row) layout styles.", self.layout_style_cb))
        
        # Color Accent
        self.accent_cb = QComboBox()
        self.accent_cb.addItems(["WS 3.5 Arc", "Neon Purple", "Emerald Green", "Sunset Orange", "Cyberpunk Pink"])
        current_accent = getattr(self.main_window, 'accent_color_name', "WS 3.5 Arc")
        self.accent_cb.setCurrentText(current_accent)
        self.accent_cb.currentTextChanged.connect(lambda a: self._stage_appearance('accent', a))
        cl.addWidget(SettingsRow("Color Accent", "Select a dynamic accent color for borders, highlights, and backgrounds.", self.accent_cb))
        
        l_app.addWidget(card)

        # Apply / Discard bar (hidden until appearance is dirty)
        bar = QFrame()
        bar.setObjectName("appearanceBar")
        bar.setVisible(False)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(14, 10, 14, 10)
        hint = QLabel("Appearance changes are not applied yet")
        hint.setObjectName("appearanceHint")
        bl.addWidget(hint)
        bl.addStretch(1)
        discard_btn = QPushButton("Discard")
        discard_btn.setObjectName("barDiscard")
        discard_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        discard_btn.clicked.connect(self._discard_appearance)
        apply_btn = QPushButton("Apply")
        apply_btn.setObjectName("barApply")
        apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_btn.clicked.connect(self._apply_appearance)
        bl.addWidget(discard_btn)
        bl.addWidget(apply_btn)
        l_app.addWidget(bar)
        self.appearance_bar = bar

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
        
        save_data_toggle = SettingsToggle()
        save_data_toggle.setChecked(getattr(self.main_window, 'save_data_enabled', True))
        save_data_toggle.toggled.connect(self.main_window.set_data_saving_enabled)
        cl.addWidget(SettingsRow("Save browsing data", "Automatically preserve browsing and download metadata for recovery.", save_data_toggle))

        save_history_toggle = SettingsToggle()
        save_history_toggle.setChecked(getattr(self.main_window, 'save_download_history', True))
        save_history_toggle.toggled.connect(self.main_window.set_save_download_history)
        cl.addWidget(SettingsRow("Save download history", "Keep a local record of recent downloads in the download manager.", save_history_toggle))

        save_freq = QComboBox()
        save_freq.addItems(["Every 5 minutes", "Every 15 minutes", "Every 30 minutes", "Hourly", "On exit"])
        if getattr(self.main_window, 'save_data_frequency', None) in [save_freq.itemText(i) for i in range(save_freq.count())]:
            save_freq.setCurrentText(self.main_window.save_data_frequency)
        save_freq.currentTextChanged.connect(self._update_data_saving_frequency)
        cl.addWidget(SettingsRow("Auto-save frequency", "Choose how often HoverNet writes saved data to disk.", save_freq))

        cl.addWidget(SettingsRow("Download Location", "The folder where files will be saved by default.", dl_path))
        cl.addWidget(btn_browse, 0, Qt.AlignmentFlag.AlignRight)

        cloud_combo = QComboBox()
        cloud_items = ["Local", "Google Drive", "OneDrive"]
        cloud_combo.addItems(cloud_items)
        cloud_combo.setToolTip("Upload completed downloads to cloud storage (requires OAuth authentication)")
        current_cs = getattr(self.main_window, 'cloud_storage', 'Local')
        if current_cs in cloud_items:
            cloud_combo.setCurrentText(current_cs)
        cloud_combo.currentTextChanged.connect(self._update_cloud_storage)
        cl.addWidget(SettingsRow("Cloud Storage", "Save downloads to cloud instead of local disk.", cloud_combo))

        # Cloud folder selection (inside the connected storage)
        self.cloud_folder_label = QLabel()
        self.cloud_folder_label.setObjectName("cloudFolderVal")
        self.cloud_folder_label.setWordWrap(True)
        browse_folder_btn = QPushButton("Change\u2026")
        browse_folder_btn.setProperty("class", "actionButton")
        browse_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_folder_btn.clicked.connect(self._browse_cloud_folder)
        folder_row = QWidget()
        folder_row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        fr = QHBoxLayout(folder_row)
        fr.setContentsMargins(0, 0, 0, 0)
        fr.setSpacing(10)
        fr.addWidget(self.cloud_folder_label, 1)
        fr.addWidget(browse_folder_btn, 0)
        self.cloud_folder_row = SettingsRow("Cloud Folder", "Choose the destination folder inside your cloud storage (optional).", folder_row)
        cl.addWidget(self.cloud_folder_row)
        self._update_cloud_folder_row()

        l_dl.addWidget(card)
        self.content_stack.addWidget(pg_dl)

        # 4. Account
        pg_acc, l_acc = self._make_page("Account")
        card, cl = self._make_card()
        
        self.oauth_manager = OAuthManager()
        
        # Google Account Section
        google_label = QLabel()
        google_label.setObjectName("accountStatus")
        self._update_google_label(google_label)
        
        btn_gmail = QPushButton()
        btn_gmail.setProperty("class", "actionButton")
        self._update_gmail_button(btn_gmail, google_label)
        btn_gmail.clicked.connect(lambda: self._handle_google_login(btn_gmail, google_label))
        
        google_row = QHBoxLayout()
        google_row.addWidget(google_label, 1)
        google_row.addWidget(btn_gmail, 0)
        
        google_container = QWidget()
        google_container.setLayout(google_row)
        cl.addWidget(SettingsRow("Google Account", "Sign in with your Google account.", google_container))
        
        # Microsoft Account Section
        microsoft_label = QLabel()
        microsoft_label.setObjectName("accountStatus")
        self._update_microsoft_label(microsoft_label)
        
        btn_ms = QPushButton()
        btn_ms.setProperty("class", "actionButton")
        self._update_microsoft_button(btn_ms, microsoft_label)
        btn_ms.clicked.connect(lambda: self._handle_microsoft_login(btn_ms, microsoft_label))
        
        microsoft_row = QHBoxLayout()
        microsoft_row.addWidget(microsoft_label, 1)
        microsoft_row.addWidget(btn_ms, 0)
        
        microsoft_container = QWidget()
        microsoft_container.setLayout(microsoft_row)
        cl.addWidget(SettingsRow("Microsoft Account", "Sign in with your Microsoft account.", microsoft_container))
        
        l_acc.addWidget(card)
        self.content_stack.addWidget(pg_acc)

        # 5. About
        pg_about, l_about = self._make_page("About HoverNet")
        card, cl = self._make_card()
        
        logo = QLabel("visualOS HoverNet")
        accent = self.main_window.get_accent_color_hex() if hasattr(self.main_window, 'get_accent_color_hex') else "#558EFF"
        logo.setStyleSheet(f"font-size: 32px; font-weight: 700; color: {accent}; background: transparent;")
        cl.addWidget(logo)
        
        cl.addWidget(QLabel(f"App Version: {getattr(self.main_window, 'HOVERNET_VERSION', '2.35')}-py.QR0"))
        cl.addWidget(QLabel("visualOS HoverNet by whenthe's space."))
        
        notes = QLabel("What changed in Quality Release Pack 0(compared to v2.30):\n"
                      "(Because of so many features, bug fixes etc. being added, I, the only developer behind HoverNet + the other WS stuff, simply cannot list them all because of just how long it's been since I started working on the update.)\n\n"
                      "• Various layout and interface additions, improvements etc.\n"
                      "• Uncountably lots of reworks/advancements to existing features, new features and more\n"
                      "• OAuth services for Google and Microsoft now available under Settings > Accounts, allows for downloading directly onto your cloud storage\n"
                      "• New accents, a whole new layout mode to the Browsing Island, accessible under Settings > Appearance\n"
                      "• (Most probably) a lot of bug fixes\n"
                      )
        notes.setObjectName("relNotes")
        notes.setWordWrap(True)
        cl.addWidget(notes)
        
        l_about.addWidget(card)
        self.content_stack.addWidget(pg_about)

    def switch_section(self, index):
        self.content_stack.setCurrentIndex(index)

    # ── Appearance staging (apply/discard) ────────────────────────────────
    def _preview_is_dark(self):
        theme = self._appearance.get('browser_theme',
                                     getattr(self.main_window, 'browser_theme', "System"))
        if theme == "Light":
            return False
        if theme == "Dark":
            return True
        return bool(getattr(self.main_window, 'is_dark_mode', True))

    def _preview_accent_rgb(self):
        name = self._appearance.get('accent',
                                    getattr(self.main_window, 'accent_color_name', "WS 3.5 Arc"))
        colors = getattr(self.main_window, 'ACCENT_COLORS', None)
        if colors and name in colors:
            return tuple(colors[name]['rgb'])
        return (85, 142, 255)

    def _preview_custom_title_bar(self):
        return self._appearance.get('custom_title_bar',
                                    getattr(self.main_window, 'use_custom_title_bar', True))

    def _preview_layout_style(self):
        return self._appearance.get('layout_style',
                                    getattr(self.main_window, 'layout_style', 'standard'))

    def _preview_ws_btn(self):
        return self._appearance.get('ws_btn',
                                    getattr(self.main_window, 'show_ws_btn', True))

    def _update_preview(self):
        if hasattr(self, 'appearance_preview'):
            self.appearance_preview.set_state(
                accent=self._preview_accent_rgb(),
                is_dark=self._preview_is_dark(),
                custom_title_bar=self._preview_custom_title_bar(),
                layout_style=self._preview_layout_style(),
                ws_btn=self._preview_ws_btn(),
            )

    def _stage_appearance(self, key, value):
        self._appearance[key] = value
        dirty = bool(self._appearance)
        if hasattr(self, 'appearance_bar'):
            self.appearance_bar.setVisible(dirty)
        self._update_preview()

    def _sync_controls_from_applied(self):
        self._sw_title.blockSignals(True)
        self._sw_title.setChecked(self.main_window.use_custom_title_bar)
        self._sw_title.blockSignals(False)
        self._sw_ws.blockSignals(True)
        self._sw_ws.setChecked(self.main_window.show_ws_btn)
        self._sw_ws.blockSignals(False)
        self.browser_theme_cb.blockSignals(True)
        self.browser_theme_cb.setCurrentText(getattr(self.main_window, 'browser_theme', "System"))
        self.browser_theme_cb.blockSignals(False)
        self.layout_style_cb.blockSignals(True)
        self.layout_style_cb.setCurrentText(getattr(self.main_window, 'layout_style', "standard").capitalize())
        self.layout_style_cb.blockSignals(False)
        self.accent_cb.blockSignals(True)
        self.accent_cb.setCurrentText(getattr(self.main_window, 'accent_color_name', "WS 3.5 Arc"))
        self.accent_cb.blockSignals(False)

    def _apply_appearance(self, complete_switch=None):
        mw = self.main_window
        a = self._appearance

        steps = []
        if 'custom_title_bar' in a:
            steps.append(lambda: mw.set_custom_title_bar_enabled(a['custom_title_bar']))
        if 'ws_btn' in a:
            steps.append(lambda: mw.set_ws_btn_visible(a['ws_btn']))
        if 'browser_theme' in a:
            steps.append(lambda: mw.set_browser_theme(a['browser_theme']))
        if 'layout_style' in a:
            steps.append(lambda: mw.set_layout_style(a['layout_style']))
        if 'accent' in a:
            steps.append(lambda: mw.set_accent_color(a['accent']))

        if steps:
            total = len(steps) + 1  # +1 reload step, which also counts
            self._apply_bubble.start(total, self)
            done = 0
            for fn in steps:
                QApplication.processEvents()
                try:
                    fn()
                    done += 1
                except Exception:
                    pass
                self._apply_bubble.set_progress(done, total)
                QApplication.processEvents()
            # Reload step: re-sync the controls and repaint so the change fully
            # completes, and reload every open hovernet:// page (Settings,
            # History) so the new theme fully applies.
            QApplication.processEvents()
            self._appearance.clear()
            self._sync_controls_from_applied()
            self._refresh_appearance()
            if complete_switch is not None:
                self._switch_to(complete_switch)
            if hasattr(mw, 'refresh_hovernet_pages'):
                mw.refresh_hovernet_pages()
            if hasattr(mw, 'update'):
                mw.update()
            done += 1
            self._apply_bubble.set_progress(done, total)
            QApplication.processEvents()
            self._apply_bubble.finish()
            return

        self._appearance.clear()
        self._sync_controls_from_applied()
        self._refresh_appearance()
        if complete_switch is not None:
            self._switch_to(complete_switch)

    def _discard_appearance(self, complete_switch=None):
        self._appearance.clear()
        self._sync_controls_from_applied()
        self._refresh_appearance()
        if complete_switch is not None:
            self._switch_to(complete_switch)

    def _refresh_appearance(self):
        if hasattr(self, 'appearance_bar'):
            self.appearance_bar.setVisible(bool(self._appearance))
        self._update_preview()

    def _on_sidebar_row_changed(self, index):
        if index == self._current_section:
            return
        if self._appearance:
            self.sidebar.blockSignals(True)
            self.sidebar.setCurrentRow(self._current_section)
            self.sidebar.blockSignals(False)
            popup = UnsavedChangesPopup(self)
            res = popup.exec()
            if res == UnsavedChangesPopup.RESULT_APPLY:
                self._apply_appearance(complete_switch=index)
            elif res == UnsavedChangesPopup.RESULT_DISCARD:
                self._discard_appearance(complete_switch=index)
        else:
            self._switch_to(index)

    def _switch_to(self, index):
        prev = self._current_section
        self._current_section = index
        self.sidebar.blockSignals(True)
        self.sidebar.setCurrentRow(index)
        self.sidebar.blockSignals(False)
        self.sidebar.begin_selection_transition(prev, index)
        self.switch_section(index)

    def _update_newtab_url(self, text):
        if hasattr(self.main_window, 'edit_newtab_url'):
            if hasattr(self.main_window.edit_newtab_url, 'setText'):
                self.main_window.edit_newtab_url.setText(text)
            else:
                self.main_window.edit_newtab_url = text

    def _update_download_path(self, text):
        self.main_window._download_path = text

    def _update_data_saving_frequency(self, text):
        self.main_window.save_data_frequency = text

    def _browse_dl_path(self, line_edit):
        path = QFileDialog.getExistingDirectory(self, "Select Download Folder", line_edit.text())
        if path:
            line_edit.setText(path)
            self.main_window._download_path = path

    def _update_cloud_storage(self, text):
        self.main_window.cloud_storage = text
        self._update_cloud_folder_row()

    def _update_cloud_folder_row(self):
        if not hasattr(self, 'cloud_folder_row'):
            return
        cs = getattr(self.main_window, 'cloud_storage', 'Local')
        enabled = cs in ("Google Drive", "OneDrive")
        self.cloud_folder_row.setEnabled(enabled)
        folder_cfg = getattr(self.main_window, 'cloud_folder', None) or {}
        folder = folder_cfg.get(cs) if cs in folder_cfg else None
        if isinstance(folder, dict) and folder.get('name'):
            self.cloud_folder_label.setText(folder['name'])
        else:
            self.cloud_folder_label.setText("Top level (root)")

    def _browse_cloud_folder(self):
        cs = getattr(self.main_window, 'cloud_storage', 'Local')
        if cs == "Google Drive":
            provider = 'google'
            display = "Google Drive"
        elif cs == "OneDrive":
            provider = 'onedrive'
            display = "OneDrive"
        else:
            return
        authed = (self.oauth_manager.is_google_authenticated()
                  if provider == 'google' else self.oauth_manager.is_microsoft_authenticated())
        if not authed:
            QMessageBox.information(self, "Not signed in",
                                    f"Sign in with {display} on the Account page first, "
                                    "then you can pick a destination folder.")
            return
        dlg = CloudFolderDialog(self.oauth_manager, provider, parent=self)
        res = dlg.exec()
        if res == QDialog.DialogCode.Accepted:
            if dlg.selected_id is not None:
                self.main_window.cloud_folder[cs] = {'id': dlg.selected_id, 'name': dlg.selected_name}
            else:
                self.main_window.cloud_folder[cs] = None
            self._update_cloud_folder_row()

    def _update_google_label(self, label):
        """Update Google account status label."""
        if self.oauth_manager.is_google_authenticated():
            label.setText("✓ Authenticated (loading...)")
            label.setStyleSheet("color: #00DD88; font-size: 12px; background: transparent; font-weight: 600;")
            self.google_worker = UserInfoWorker(self.oauth_manager, 'google')
            self.google_worker.finished.connect(lambda info, p: self._on_user_info_loaded(label, info, p))
            self.google_worker.start()
        else:
            label.setText("Not logged in")
            label.setStyleSheet("color: #8994AB; font-size: 12px; background: transparent;")

    def _update_gmail_button(self, button, label):
        """Update Gmail button text based on auth status."""
        if self.oauth_manager.is_google_authenticated():
            button.setText("Logout")
        else:
            button.setText("Connect Google")

    def _update_microsoft_label(self, label):
        """Update Microsoft account status label."""
        if self.oauth_manager.is_microsoft_authenticated():
            label.setText("✓ Authenticated (loading...)")
            label.setStyleSheet("color: #00DD88; font-size: 12px; background: transparent; font-weight: 600;")
            self.ms_worker = UserInfoWorker(self.oauth_manager, 'microsoft')
            self.ms_worker.finished.connect(lambda info, p: self._on_user_info_loaded(label, info, p))
            self.ms_worker.start()
        else:
            label.setText("Not logged in")
            label.setStyleSheet("color: #8994AB; font-size: 12px; background: transparent;")

    def _on_user_info_loaded(self, label, info, provider):
        if provider == 'google':
            email = info.get('email', 'Unknown')
        else:
            email = info.get('mail') or info.get('userPrincipalName', 'Unknown')
            
        if info:
            label.setText(f"✓ Logged in as {email}")
        else:
            label.setText("✓ Authenticated (user info unavailable)")

    def _update_microsoft_button(self, button, label):
        """Update Microsoft button text based on auth status."""
        if self.oauth_manager.is_microsoft_authenticated():
            button.setText("Logout")
        else:
            button.setText("Connect Microsoft")

    def _handle_google_login(self, button, label):
        """Handle Google login/logout."""
        if self.oauth_manager.is_google_authenticated():
            self.oauth_manager.logout_google()
            self._update_google_label(label)
            self._update_gmail_button(button, label)
            QMessageBox.information(self, "Logged Out", "You have been signed out from Google.")
        else:
            try:
                # Use default OAuth credentials for demonstration
                # In production, these should be securely stored/configured
                client_id = "" # The Google OAuth Client ID and secrets for visualOS HoverNet have been removed from the source code to protect the security of this app. You will need to make your own OAuth 2.0 credentials to get this feature to work.
                client_secret = ""
                
                result = self.oauth_manager.authenticate_google(client_id, client_secret, process_events=QApplication.processEvents)
                
                if 'error' in result:
                    if 'access_denied' in str(result['error']).lower():
                        QMessageBox.warning(self, "Access Denied",
                                            "Google denied the request.\n\n"
                                            "Common reasons:\n"
                                            "• The app is unverified and uses sensitive scopes (drive.file)\n"
                                            "• The Google Cloud project has an issue (OAuth consent screen not published)\n"
                                            "• API (Drive API) is not enabled in the Google Cloud project")
                    else:
                        QMessageBox.warning(self, "Sign In Failed", f"Authentication failed: {result['error']}")
                else:
                    self._update_google_label(label)
                    self._update_gmail_button(button, label)
                    QMessageBox.information(self, "Sign In Successful", "You have successfully signed in with Google.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"An error occurred during Google login: {str(e)}")

    def _handle_microsoft_login(self, button, label):
        """Handle Microsoft login/logout."""
        if self.oauth_manager.is_microsoft_authenticated():
            self.oauth_manager.logout_microsoft()
            self._update_microsoft_label(label)
            self._update_microsoft_button(button, label)
            QMessageBox.information(self, "Logged Out", "You have been signed out from Microsoft.")
        else:
            try:
                # These are the Microsoft OAuth credentials.
                # If you registered this as a public desktop client(which HoverNet's OAuth was registered as), leave client_secret blank.
                client_id = "" # The Microsoft OAuth Client ID for visualOS HoverNet have been removed from the source code to protect the security of this app. You will need to make your own OAuth 2.0 credentials to get this feature to work.
                client_secret = ""
                
                result = self.oauth_manager.authenticate_microsoft(client_id, client_secret, process_events=QApplication.processEvents)
                
                if 'error' in result:
                    QMessageBox.warning(self, "Sign In Failed", f"Microsoft authentication failed: {result['error']}")
                else:
                    self._update_microsoft_label(label)
                    self._update_microsoft_button(button, label)
                    QMessageBox.information(self, "Sign In Successful", "You have successfully signed in with Microsoft.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"An error occurred during Microsoft login: {str(e)}")

    def _change_layout_style(self, style):
        if hasattr(self.main_window, 'set_layout_style'):
            self.main_window.set_layout_style(style.lower())

    def _change_browser_theme(self, theme):
        if hasattr(self.main_window, 'set_browser_theme'):
            self.main_window.set_browser_theme(theme)

    def _change_accent_color(self, accent_name):
        if hasattr(self.main_window, 'set_accent_color'):
            self.main_window.set_accent_color(accent_name)
            self.apply_styles()

