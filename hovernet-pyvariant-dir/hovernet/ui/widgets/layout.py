from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QCheckBox
from .buttons import SettingsToggle

class SettingsRow(QWidget):
    """A standardized row for settings with a title, description, and control widget."""
    def __init__(self, title, description="", control=None, parent=None):
        super().__init__(parent)
        self.control = control
        self.setCursor(Qt.CursorShape.PointingHandCursor if isinstance(control, SettingsToggle) else Qt.CursorShape.ArrowCursor)
        
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(20)
        
        text_container = QWidget()
        text_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        text_container.setStyleSheet("background: transparent;")
        tv = QVBoxLayout(text_container)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(2)
        
        t_lbl = QLabel(title)
        t_lbl.setProperty("class", "rowTitle")
        tv.addWidget(t_lbl)
        
        if description:
            d_lbl = QLabel(description)
            d_lbl.setProperty("class", "rowDesc")
            d_lbl.setWordWrap(True)
            tv.addWidget(d_lbl)
        
        layout.addWidget(text_container, 3)
        if control:
            layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if isinstance(self.control, SettingsToggle):
                self.control.setChecked(not self.control.isChecked())
            elif isinstance(self.control, QCheckBox):
                self.control.toggle()
        super().mousePressEvent(event)
