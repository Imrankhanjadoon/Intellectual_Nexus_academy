"""Original academic emblem, rendered locally at any display scale."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QLabel


def seal_pixmap(size=96):
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size * 2 / 200, size * 2 / 200)
    green, gold, ivory = QColor("#173e75"), QColor("#c5a46d"), QColor("#ffffff")
    painter.setPen(QPen(green, 2.2))
    painter.setBrush(ivory)
    painter.drawEllipse(QRectF(4, 4, 192, 192))
    painter.setPen(QPen(gold, 1))
    painter.drawEllipse(QRectF(10, 10, 180, 180))
    painter.setPen(QPen(green, 2))
    for side in (-1, 1):
        path = QPainterPath()
        path.moveTo(100 + side * 14, 166)
        path.cubicTo(100 + side * 60, 151, 100 + side * 72, 105, 100 + side * 48, 53)
        painter.drawPath(path)
        for x, y, angle in [(49, 65, 36), (56, 83, 15), (58, 102, -8), (53, 122, -29), (43, 140, -46), (27, 155, -62)]:
            painter.save()
            painter.translate(100 + side * x, y)
            painter.rotate(side * angle)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(green)
            painter.drawEllipse(QRectF(-4, -8, 8, 16))
            painter.restore()
    shield = QPainterPath()
    shield.moveTo(68, 57)
    shield.lineTo(132, 57)
    shield.lineTo(132, 112)
    shield.cubicTo(132, 134, 113, 146, 100, 153)
    shield.cubicTo(87, 146, 68, 134, 68, 112)
    shield.closeSubpath()
    painter.setBrush(green)
    painter.setPen(QPen(gold, 2))
    painter.drawPath(shield)
    painter.drawLine(84, 73, 116, 73)
    painter.drawLine(90, 78, 110, 78)
    book = QPainterPath()
    book.moveTo(100, 96)
    book.cubicTo(90, 89, 77, 89, 75, 92)
    book.lineTo(75, 119)
    book.cubicTo(85, 115, 94, 118, 100, 124)
    book.cubicTo(106, 118, 115, 115, 125, 119)
    book.lineTo(125, 92)
    book.cubicTo(119, 89, 109, 90, 100, 96)
    painter.setBrush(ivory)
    painter.setPen(QPen(gold, 1.5))
    painter.drawPath(book)
    painter.setPen(QPen(green, 1.4))
    painter.drawLine(100, 97, 100, 122)
    for offset in (0, 7, 14):
        painter.drawLine(80, 98 + offset, 94, 101 + offset)
        painter.drawLine(106, 101 + offset, 120, 98 + offset)
    painter.setBrush(gold)
    painter.setPen(Qt.PenStyle.NoPen)
    for x in (88, 100, 112):
        painter.drawEllipse(QRectF(x - 2, 27, 4, 4))
    painter.drawRect(QRectF(82, 170, 36, 2))
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return pixmap


class AcademySeal(QLabel):
    def __init__(self, size=84, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setPixmap(seal_pixmap(size))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAccessibleName("Academy emblem: open book and laurel")


def line_icon(name, color="#536b87", size=22):
    """Small original line icons; no operating-system icon/font dependency."""
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size * 2 / 24, size * 2 / 24)
    p.setPen(QPen(QColor(color), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if name == "dashboard":
        for x, y in ((3, 3), (14, 3), (3, 14), (14, 14)):
            p.drawRoundedRect(QRectF(x, y, 7, 7), 1, 1)
    elif name in ("students", "users"):
        p.drawEllipse(QRectF(5, 3, 7, 7))
        path = QPainterPath()
        path.moveTo(2, 21); path.lineTo(2, 18)
        path.cubicTo(2, 11, 15, 11, 15, 18); path.lineTo(15, 21)
        p.drawPath(path)
        path = QPainterPath(); path.moveTo(16, 4)
        path.cubicTo(22, 5, 22, 10, 17, 11)
        path.moveTo(18, 14); path.cubicTo(22, 15, 22, 18, 22, 21)
        p.drawPath(path)
    elif name == "fees":
        p.drawRoundedRect(QRectF(4, 2, 16, 20), 1.2, 1.2)
        p.drawLine(8, 7, 16, 7); p.drawLine(8, 11, 16, 11)
        p.drawLine(8, 17, 11, 17); p.drawEllipse(QRectF(13, 14, 4, 4))
    elif name == "attendance":
        p.drawRoundedRect(QRectF(4, 5, 16, 17), 1.4, 1.4)
        p.drawRoundedRect(QRectF(8, 2, 8, 5), 1, 1)
        path = QPainterPath(); path.moveTo(8, 14); path.lineTo(11, 17); path.lineTo(17, 11); p.drawPath(path)
    elif name == "reports":
        p.drawLine(3, 3, 3, 21); p.drawLine(3, 21, 22, 21)
        for x, y in ((7, 13), (12, 8), (17, 4)):
            p.drawRect(QRectF(x, y, 3, 20-y))
    elif name == "settings":
        p.drawEllipse(QRectF(4, 4, 16, 16)); p.drawEllipse(QRectF(9, 9, 6, 6))
        for a, b, c, d in ((12, 1, 12, 4), (12, 20, 12, 23), (1, 12, 4, 12), (20, 12, 23, 12), (4, 4, 6, 6), (18, 18, 20, 20), (4, 20, 6, 18), (18, 6, 20, 4)):
            p.drawLine(a, b, c, d)
    elif name == "logout":
        p.drawLine(11, 3, 4, 3); p.drawLine(4, 3, 4, 21); p.drawLine(4, 21, 11, 21)
        p.drawLine(10, 12, 22, 12); p.drawLine(18, 8, 22, 12); p.drawLine(18, 16, 22, 12)
    else:
        p.drawEllipse(QRectF(3, 3, 18, 18)); p.drawLine(12, 10, 12, 17); p.drawPoint(12, 7)
    p.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)
