from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect, QRectF, QVariantAnimation, Property
from PySide6.QtWidgets import QToolButton, QCheckBox, QPushButton
from PySide6.QtGui import QColor, QPainter, QPen, QBrush

class NewTabButton(QToolButton):
    """A '+' button that expands into a 'New tab' capsule on hover with a graphical icon."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(26)
        self.setFixedWidth(28)
        self._collapsed_width = 28
        self._expanded_width = 100
        self._compact_mode = False
        
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._expand)

        self._leave_timer = QTimer(self)
        self._leave_timer.setSingleShot(True)
        self._leave_timer.timeout.connect(self._collapse)

        self._anim = QPropertyAnimation(self, b"minimumWidth")
        self._anim.setDuration(250)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._anim_max = QPropertyAnimation(self, b"maximumWidth")
        self._anim_max.setDuration(250)
        self._anim_max.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._expanded = False
        self._expanded = False

    @property
    def compact_mode(self):
        return getattr(self, '_compact_mode', False)

    @compact_mode.setter
    def compact_mode(self, value):
        self._compact_mode = value
        if value:
            self._collapsed_width = 24
            self._expanded_width = 24
            self.setMinimumWidth(24)
            self.setMaximumWidth(24)
            self.setFixedHeight(24)
        else:
            self._collapsed_width = 28
            self._expanded_width = 100
            self.setMinimumWidth(28)
            self.setMaximumWidth(9999)
            self.setFixedHeight(26)
        self.updateGeometry()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        is_hover = self.underMouse()
        is_pressed = self.isDown()
        
        # Colors
        bg_alpha = 0
        if is_hover: bg_alpha = 60
        if is_pressed: bg_alpha = 100
        
        accent_color = QColor("#558EFF")
        main_win = self.window()
        is_dark = getattr(main_win, 'is_dark_mode', True) if main_win else True
        if main_win and hasattr(main_win, 'get_accent_rgb'):
            accent_color = QColor(*main_win.get_accent_rgb())
            
        bg_color = QColor(accent_color.red(), accent_color.green(), accent_color.blue(), bg_alpha)
        r2, g2, b2 = accent_color.red(), accent_color.green(), accent_color.blue()
        border_color = accent_color if is_hover else (QColor(max(r2//3, 14), max(g2//3, 14), max(b2//3, 14)) if is_dark else QColor("#d0d0e0"))
        
        # When hovered in light mode, if the accent color is dark enough, white is fine. Otherwise, black.
        # But generally, white text on primary accent is standard, so we'll just keep white on hover.
        icon_color = QColor("#ffffff") if is_hover else (QColor("#A9B5CC") if is_dark else QColor("#555566"))
        
        # Background
        painter.setBrush(bg_color)
        painter.setPen(QPen(border_color, 2))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 13, 13)
        
        # Graphical + Icon: pinned to the collapsed-width center so it reads
        # left-aligned while the capsule expands, and back to centered when it
        # shrinks back down.
        painter.setPen(QPen(icon_color, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        cx = min(self.width() // 2, self._collapsed_width // 2)
        cy = 13
        s = 5
        painter.drawLine(cx - s, cy, cx + s, cy)
        painter.drawLine(cx, cy - s, cx, cy + s)
        
        # Text fade in based on width (only in standard mode)
        if not self.compact_mode and self.width() > 35:
            progress = (self.width() - self._collapsed_width) / (self._expanded_width - self._collapsed_width)
            alpha = int(max(0, min(255, progress * 255)))
            
            text_color = QColor(icon_color)
            text_color.setAlpha(alpha)
            painter.setPen(text_color)
            
            f = self.font()
            f.setPointSize(10)
            f.setBold(False)
            painter.setFont(f)
            
            painter.drawText(QRect(32, 0, self.width() - 35, self.height()), 
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, 
                             "New tab")

    def enterEvent(self, event):
        super().enterEvent(event)
        if self.compact_mode:
            return
        self._leave_timer.stop()
        self._hover_timer.start(200)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if self.compact_mode:
            return
        self._hover_timer.stop()
        if self._expanded:
            self._leave_timer.start(200)

    def _expand(self):
        if not self._expanded:
            self._expanded = True
            for anim in (self._anim, self._anim_max):
                anim.setStartValue(self.width())
                anim.setEndValue(self._expanded_width)
                anim.start()

    def _collapse(self):
        if self._expanded:
            self._expanded = False
            for anim in (self._anim, self._anim_max):
                anim.setStartValue(self.width())
                anim.setEndValue(self._collapsed_width)
                anim.start()

    def trigger_animation(self):
        if self.compact_mode:
            return
        if not self._expanded:
            self._expand()
            QTimer.singleShot(1200, lambda: self._collapse() if not self.underMouse() else None)

class SettingsToggle(QCheckBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._thumb_pos = 2.0
        self._anim = QPropertyAnimation(self, b"thumb_pos")
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.stateChanged.connect(self._on_state_changed)

    def _on_state_changed(self, state):
        target = 20.0 if self.isChecked() else 2.0
        self._anim.stop()
        self._anim.setEndValue(target)
        self._anim.start()

    @Property(float)
    def thumb_pos(self): return self._thumb_pos
    @thumb_pos.setter
    def thumb_pos(self, pos):
        self._thumb_pos = pos
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        is_on = self.isChecked()
        
        main_win = self.window()
        is_dark = getattr(main_win, 'is_dark_mode', True) if main_win else True
        accent_rgb = getattr(main_win, 'get_accent_rgb', lambda: (85, 142, 255))()
        
        r, g, b = accent_rgb
        dr, dg, db = max(r//4, 14), max(g//4, 14), max(b//4, 14)
        
        track_color = QColor(*accent_rgb) if is_on else (QColor(dr, dg, db) if is_dark else QColor("#e0e0e0"))
        if not self.isEnabled():
            track_color = QColor(max(dr-4, 4), max(dg-4, 4), max(db-4, 4)) if is_dark else QColor("#cccccc")
            
        painter.setBrush(track_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 11, 11)
        
        painter.setBrush(QColor(255, 255, 255))
        painter.drawEllipse(QRect(int(self._thumb_pos), 2, 18, 18))

class TitleBarButton(QPushButton):
    """Graphical window control buttons (Minimize, Maximize/Restore, Close)."""
    def __init__(self, btn_type, parent=None):
        super().__init__(parent)
        self.btn_type = btn_type # 'min', 'max', 'close'
        self.setFixedSize(36, 26)
        self._is_maximized = False # Only used for 'max' type
        self._anim = 0.0          # 0 = resting, 1 = hovered
        self._animator = QVariantAnimation(self)
        self._animator.setDuration(160)
        self._animator.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animator.valueChanged.connect(self._on_anim_value)
        self.setStyleSheet("background: transparent; border: none;") # Reset base style
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _on_anim_value(self, val):
        self._anim = float(val)
        self.update()

    def enterEvent(self, event):
        self._animator.stop()
        self._animator.setStartValue(self._anim)
        self._animator.setEndValue(1.0)
        self._animator.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animator.stop()
        self._animator.setStartValue(self._anim)
        self._animator.setEndValue(0.0)
        self._animator.start()
        super().leaveEvent(event)

    def set_maximized(self, is_max):
        self._is_maximized = is_max
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.btn_type == 'min':
            base_color = QColor("#EAB308")
        elif self.btn_type == 'max':
            base_color = QColor("#22C55E")
        else:
            base_color = QColor("#EF4444")

        # Crossfade resting -> hovered appearance (t = _anim)
        t = self._anim
        hue, sat, val, _ = base_color.getHsv()
        resting_sat = max(0, sat - 100)
        base_color.setHsv(hue, int(resting_sat + (sat - resting_sat) * t), val)
        base_color.setAlphaF(0.7 + 0.3 * t)

        w = 18 + 6 * t
        h = 2 + 1 * t
        r = 1.0 + 0.5 * t

        painter.setBrush(base_color)
        painter.setPen(Qt.PenStyle.NoPen)

        cx, cy = self.width() / 2, self.height() / 2
        painter.drawRoundedRect(QRectF(cx - w/2, cy - h/2, w, h), r, r)
