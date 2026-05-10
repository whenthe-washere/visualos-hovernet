from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect, Property
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
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        is_hover = self.underMouse()
        is_pressed = self.isDown()
        
        # Colors
        bg_alpha = 0
        if is_hover: bg_alpha = 60
        if is_pressed: bg_alpha = 100
        
        bg_color = QColor(85, 102, 255, bg_alpha)
        border_color = QColor("#5566ff") if is_hover else QColor("#4a4a80")
        icon_color = QColor("#ffffff") if is_hover else QColor("#aaaacc")
        
        # Background
        painter.setBrush(bg_color)
        painter.setPen(QPen(border_color, 2))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 13, 13)
        
        # Graphical + Icon
        painter.setPen(QPen(icon_color, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        cx, cy = 14, 13
        s = 5
        painter.drawLine(cx - s, cy, cx + s, cy)
        painter.drawLine(cx, cy - s, cx, cy + s)
        
        # Text fade in based on width
        if self.width() > 35:
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
        self._leave_timer.stop()
        self._hover_timer.start(200)

    def leaveEvent(self, event):
        super().leaveEvent(event)
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
        
        track_color = QColor("#5566ff") if is_on else QColor("#2a2a4a")
        if not self.isEnabled():
            track_color = QColor("#1a1a3a")
            
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
        self.setStyleSheet("background: transparent; border: none;") # Reset base style
        
    def set_maximized(self, is_max):
        self._is_maximized = is_max
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        is_hover = self.underMouse()
        is_pressed = self.isDown()
        
        # Background
        if is_hover:
            bg_color = QColor(255, 50, 50) if self.btn_type == 'close' else QColor(255, 255, 255, 30)
            if is_pressed:
                bg_color = QColor(200, 40, 40) if self.btn_type == 'close' else QColor(255, 255, 255, 50)
            painter.setBrush(bg_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(self.rect())
            
        # Icon
        pen_color = QColor(255, 255, 255)
        painter.setPen(QPen(pen_color, 1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap, Qt.PenJoinStyle.MiterJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        cx, cy = 18, 13
        
        if self.btn_type == 'min':
            painter.drawLine(cx - 5, cy, cx + 5, cy)
        elif self.btn_type == 'max':
            if not self._is_maximized:
                # Square
                painter.drawRect(cx - 5, cy - 5, 10, 10)
            else:
                # Overlapping squares (Restore)
                painter.drawRect(cx - 3, cy - 5, 8, 8)
                # Draw a small background-colored square to mask the intersection
                painter.setBrush(QColor(30, 30, 60)) 
                painter.drawRect(cx - 5, cy - 3, 8, 8)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(cx - 5, cy - 3, 8, 8)
        elif self.btn_type == 'close':
            painter.drawLine(cx - 5, cy - 5, cx + 5, cy + 5)
            painter.drawLine(cx - 5, cy + 5, cx + 5, cy - 5)
