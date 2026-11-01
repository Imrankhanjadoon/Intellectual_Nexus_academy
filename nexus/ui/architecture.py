"""Original architectural linework for the academy's account portal."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget


class AcademicArchitecture(QWidget):
    """A decorative academic colonnade; it does not depict an actual campus."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(130)
        self.setMaximumHeight(170)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName("Decorative original academic architectural linework")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setViewport(self.rect())
        painter.setWindow(0, 0, 340, 165)
        pale = QColor("#b1c5dd")
        pale.setAlpha(105)
        faint = QColor("#b1c5dd")
        faint.setAlpha(35)
        gold = QColor("#c5a46d")
        gold.setAlpha(190)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(faint, 0.65))
        for x in range(16, 340, 22):
            painter.drawLine(x, 12, x, 156)
        for y in range(24, 160, 22):
            painter.drawLine(9, y, 330, y)
        painter.setPen(QPen(pale, 1.1))
        roof = QPainterPath()
        roof.moveTo(29, 59)
        roof.lineTo(170, 16)
        roof.lineTo(311, 59)
        roof.closeSubpath()
        painter.drawPath(roof)
        painter.drawLine(49, 54, 170, 25)
        painter.drawLine(170, 25, 291, 54)
        painter.drawRect(QRectF(27, 61, 286, 7))
        for x in (48, 91, 134, 177, 220, 263):
            painter.drawRect(QRectF(x, 74, 24, 4))
            painter.drawLine(x + 4, 79, x + 5, 126)
            painter.drawLine(x + 20, 79, x + 19, 126)
            painter.drawLine(x + 12, 80, x + 12, 125)
            painter.drawRect(QRectF(x, 127, 24, 4))
        painter.drawRect(QRectF(30, 135, 280, 5))
        painter.drawRect(QRectF(20, 143, 300, 4))
        painter.setPen(QPen(gold, 1.3))
        painter.drawLine(9, 154, 331, 154)
        painter.drawEllipse(QRectF(162, 40, 16, 12))
        painter.drawLine(QPointF(170, 39), QPointF(170, 53))
        painter.end()
