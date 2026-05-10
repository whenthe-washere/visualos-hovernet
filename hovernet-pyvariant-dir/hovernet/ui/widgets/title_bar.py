from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect, QPoint
from PySide6.QtWidgets import QLabel, QFrame
from PySide6.QtGui import QColor, QPainter

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
        if getattr(self.parent_window, 'use_expandable_title', False):
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

class DragHandleLine(QFrame):
    """
    A horizontal line that appears at the top of the window when hovering
    for a while, indicating the draggable area.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(4) # Hit area height
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setStyleSheet("background-color: transparent; border: none;")
        
        # Inner line widget for cleaner animation
        self.line = QFrame(self)
        # Position at the center with 0 width initially
        self.line.setStyleSheet("background-color: #5566ff; border-radius: 1px;")
        
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._expand)
        
        self._leave_timer = QTimer(self)
        self._leave_timer.setSingleShot(True)
        self._leave_timer.timeout.connect(self._collapse)
        
        self._anim = QPropertyAnimation(self.line, b"geometry")
        self._anim.setDuration(400)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._expanded = False

    def resizeEvent(self, event):
        if not self._expanded:
            self.line.setGeometry(self.width() // 2, 1, 0, 2)
        else:
            self.line.setGeometry(20, 1, self.width() - 40, 2)
        super().resizeEvent(event)

    def enterEvent(self, event):
        self._leave_timer.stop()
        self._hover_timer.start(600) # Lingering duration
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_timer.stop()
        self._leave_timer.start(300)
        super().leaveEvent(event)

    def _expand(self):
        if not self._expanded:
            self._expanded = True
            self._anim.stop()
            self._anim.setStartValue(self.line.geometry())
            self._anim.setEndValue(QRect(20, 1, self.width() - 40, 2))
            self._anim.start()

    def _collapse(self):
        if self._expanded:
            self._expanded = False
            self._anim.stop()
            self._anim.setStartValue(self.line.geometry())
            self._anim.setEndValue(QRect(self.width() // 2, 1, 0, 2))
            self._anim.start()
