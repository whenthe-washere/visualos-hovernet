from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QLineEdit, QStyle, QStyleOptionFrame, QHBoxLayout, QLabel
from PySide6.QtGui import QColor, QPainter

class UrlLineEdit(QLineEdit):
    """
    A custom QLineEdit that highlights the domain in white and grays out the rest
    (protocol and path) when not focused, for a premium browser look.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(28)
        
        # Internal layout for zoom indicator
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 12, 0) # Right padding inside URL bar
        self._layout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        self.zoom_indicator = QLabel("100%", self)
        self.zoom_indicator.setCursor(Qt.CursorShape.PointingHandCursor)
        self.zoom_indicator.setStyleSheet("color: #8994AB; font-size: 11px; font-weight: 600; background: transparent;")
        self.zoom_indicator.hide() # Hidden initially, shown if zoom != 100 or always shown depending on preference, but we'll show it always for now.
        self.zoom_indicator.show()
        
        self._layout.addWidget(self.zoom_indicator)
        
        # Minimal default style — will be fully overridden by setup_island_layout()
        self.setStyleSheet("""
            QLineEdit {
                background-color: rgba(30, 40, 60, 160);
                border: 2px solid #334466;
                border-radius: 14px;
                padding: 4px 70px 4px 12px; /* right padding for zoom indicator */
                color: #ffffff;
                font-size: 13px;
                selection-background-color: rgba(85, 142, 255, 180);
            }
            QLineEdit:focus {
                border: 2px solid rgba(85, 142, 255, 200);
                background-color: rgba(40, 40, 80, 200);
            }
        """)
        self.style().unpolish(self)
        self.style().polish(self)

    def showEvent(self, event):
        super().showEvent(event)
        self.style().unpolish(self)
        self.style().polish(self)

    def paintEvent(self, event):
        # Draw the standard QLineEdit (which perfectly handles the stylesheet border-radius and background).
        # When unfocused, the text color is transparent via stylesheet, so we can draw our custom text over it.
        super().paintEvent(event)

        if self.hasFocus() or self.hasSelectedText():
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        option = QStyleOptionFrame()
        self.initStyleOption(option)
        
        rect = self.style().subElementRect(QStyle.SubElement.SE_LineEditContents, option, self)
        rect.adjust(2, 0, -2, 0) # slight horizontal padding
        
        text = self.text()
        
        main_win = self.window()
        is_dark = getattr(main_win, 'is_dark_mode', True)
        gray_color = QColor("#8994AB") if is_dark else QColor("#555566")
        main_color = QColor("#ffffff") if is_dark else QColor("#000000")
        
        if not text:
            if self.placeholderText():
                painter.setPen(gray_color)
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
        y = (self.height() + metrics.ascent() - metrics.descent()) // 2

        def draw_segment(x, text, color):
            painter.setPen(color)
            avail = rect.right() - x
            if avail <= 0:
                return None
            if metrics.horizontalAdvance(text) <= avail:
                painter.drawText(x, y, text)
                return x + metrics.horizontalAdvance(text)
            painter.drawText(x, y, metrics.elidedText(text, Qt.TextElideMode.ElideRight, avail))
            return None

        x = draw_segment(rect.x(), prefix, gray_color)
        if x is None:
            return
        x = draw_segment(x, domain, main_color)
        if x is None:
            return
        draw_segment(x, suffix, gray_color)
