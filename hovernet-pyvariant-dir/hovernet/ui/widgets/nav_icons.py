import math
from PySide6.QtWidgets import QToolButton
from PySide6.QtCore import QVariantAnimation, Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPainterPath, QPen, QBrush

def interpolate_color(c1, c2, progress):
    return QColor(
        int(c1.red() + (c2.red() - c1.red()) * progress),
        int(c1.green() + (c2.green() - c1.green()) * progress),
        int(c1.blue() + (c2.blue() - c1.blue()) * progress),
        int(c1.alpha() + (c2.alpha() - c1.alpha()) * progress)
    )

class AnimatedIconButton(QToolButton):
    def __init__(self, icon_type, parent=None):
        super().__init__(parent)
        self.icon_type = icon_type
        self.setFixedSize(30, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.hover_progress = 0.0
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(250)
        self.anim.valueChanged.connect(self.set_hover_progress)
        
    def set_hover_progress(self, val):
        self.hover_progress = val
        self.update()
        
    def enterEvent(self, e):
        self.anim.stop()
        self.anim.setStartValue(self.hover_progress)
        self.anim.setEndValue(1.0)
        self.anim.start()
        super().enterEvent(e)
        
    def leaveEvent(self, e):
        self.anim.stop()
        self.anim.setStartValue(self.hover_progress)
        self.anim.setEndValue(0.0)
        self.anim.start()
        super().leaveEvent(e)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w, h = self.width(), self.height()
        
        # Center the icon (assume 16x16 icon area)
        painter.translate((w - 16) / 2, (h - 16) / 2)
        
        base_color = QColor(255, 255, 255)
        
        if self.icon_type == 'home':
            target_color = QColor("#0050FF")
            color = interpolate_color(base_color, target_color, self.hover_progress)
            pen = QPen(color, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            
            # Draw outlined home
            path = QPainterPath()
            path.moveTo(8, 2)
            path.lineTo(2, 7)
            path.lineTo(2, 14)
            path.lineTo(14, 14)
            path.lineTo(14, 7)
            path.closeSubpath()
            painter.drawPath(path)
            
            # Door
            painter.drawRect(6, 10, 4, 4)
            
        elif self.icon_type == 'python':
            # Python logo (parallel curves)
            blue_target = QColor("#3776AB")
            yellow_target = QColor("#FFD43B")
            
            c_blue = interpolate_color(base_color, blue_target, self.hover_progress)
            c_yellow = interpolate_color(base_color, yellow_target, self.hover_progress)
            
            # Path 1 (Top/Left - Blue)
            pen_blue = QPen(c_blue, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen_blue)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            
            path1 = QPainterPath()
            path1.moveTo(2, 16)
            path1.lineTo(2, 11)
            path1.quadTo(2, 5, 8, 5)
            path1.lineTo(8, 5)
            path1.quadTo(10, 5, 10, 3)
            path1.lineTo(10, 0)
            painter.drawPath(path1)

            # Path 2 (Bottom/Right - Yellow)
            pen_yellow = QPen(c_yellow, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen_yellow)
            
            path2 = QPainterPath()
            path2.moveTo(6, 16)
            path2.lineTo(6, 11)
            path2.quadTo(6, 9, 8, 9)
            path2.lineTo(8, 9)
            path2.quadTo(14, 9, 14, 3)
            path2.lineTo(14, 0)
            painter.drawPath(path2)

        elif self.icon_type == 'ws':
            hex_target = QColor("#5c6bc0")
            tri_target = QColor("#4caf50")
            
            c_hex = interpolate_color(base_color, hex_target, self.hover_progress)
            c_tri = interpolate_color(base_color, tri_target, self.hover_progress)
            
            painter.setBrush(Qt.BrushStyle.NoBrush)
            
            # Hexagon
            pen_hex = QPen(c_hex, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen_hex)
            hex_path = QPainterPath()
            hex_path.moveTo(8, 0)
            hex_path.lineTo(15, 4)
            hex_path.lineTo(15, 12)
            hex_path.lineTo(8, 16)
            hex_path.lineTo(1, 12)
            hex_path.lineTo(1, 4)
            hex_path.closeSubpath()
            painter.drawPath(hex_path)
            
            # Inner square + triangle share the green pen
            pen_tri = QPen(c_tri, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen_tri)
            sq_path = QPainterPath()
            sq_path.addRect(3.5, 4.5, 9, 7)
            painter.drawPath(sq_path)
            
            # Inner triangle pointing up
            tri_path = QPainterPath()
            tri_path.moveTo(8, 5)
            tri_path.lineTo(11, 10.5)
            tri_path.lineTo(5, 10.5)
            tri_path.closeSubpath()
            painter.drawPath(tri_path)

        elif self.icon_type == 'tools':
            target_color = QColor("#1976D2")
            color = interpolate_color(base_color, target_color, self.hover_progress)
            
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            
            # Three horizontal dots
            painter.drawEllipse(2, 6, 3, 3)
            painter.drawEllipse(6.5, 6, 3, 3)
            painter.drawEllipse(11, 6, 3, 3)
