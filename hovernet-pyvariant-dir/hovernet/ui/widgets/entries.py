from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QLineEdit, QStyle, QStyleOptionFrame
from PySide6.QtGui import QColor, QPainter

class UrlLineEdit(QLineEdit):
    """
    A custom QLineEdit that highlights the domain in white and grays out the rest
    (protocol and path) when not focused, for a premium browser look.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._gray_color = QColor("#8888aa")
        self._white_color = QColor("#ffffff")
        
        # Modern URL bar style
        self.setStyleSheet("""
            QLineEdit {
                background-color: rgba(30, 30, 60, 160);
                border: 2px solid #333366;
                border-radius: 14px;
                padding: 4px 12px;
                color: #ffffff;
                font-size: 13px;
                selection-background-color: #5566ff;
            }
            QLineEdit:focus {
                border: 2px solid #5566ff;
                background-color: rgba(40, 40, 80, 200);
            }
        """)

    def paintEvent(self, event):
        # When focused or selecting text, draw normally to show cursor/selection
        if self.hasFocus() or self.hasSelectedText():
            super().paintEvent(event)
            return

        # Initialize the style option to draw the background/border
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        option = QStyleOptionFrame()
        self.initStyleOption(option)
        
        # Draw the widget background and border using the current style
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_PanelLineEdit, option, painter, self)

        # Get the area where text is actually drawn
        rect = self.style().subElementRect(QStyle.SubElement.SE_LineEditContents, option, self)
        rect.adjust(2, 0, -2, 0) # slight horizontal padding
        
        text = self.text()
        if not text:
            # Handle placeholder text if empty
            if self.placeholderText():
                painter.setPen(QColor(100, 100, 140))
                painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.placeholderText())
            return

        # Split URL for highlighting
        prefix = ""
        domain = ""
        suffix = ""

        if "://" in text:
            idx = text.find("://") + 3
            prefix = text[:idx]
            rest = text[idx:]
        else:
            rest = text

        if "/" in rest:
            idx = rest.find("/")
            domain = rest[:idx]
            suffix = rest[idx:]
        else:
            domain = rest

        # Start drawing from the left
        metrics = painter.fontMetrics()
        x = rect.x()
        y = (self.height() + metrics.ascent() - metrics.descent()) // 2

        # Protocol (gray)
        if prefix:
            painter.setPen(self._gray_color)
            painter.drawText(x, y, prefix)
            x += metrics.horizontalAdvance(prefix)

        # Domain (white)
        painter.setPen(self._white_color)
        painter.drawText(x, y, domain)
        x += metrics.horizontalAdvance(domain)

        # Path/Query (gray)
        if suffix:
            painter.setPen(self._gray_color)
            # Use eliding if text is too long for the box
            painter.drawText(x, y, suffix)
