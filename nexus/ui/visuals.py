"""Small, local financial graphics for the academy overview."""
from decimal import Decimal, InvalidOperation, ROUND_DOWN

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget


class SettlementChart(QWidget):
    """An accurate collected/outstanding ring, including a true empty state.

    The surrounding card supplies the title, monetary totals and legend. No
    student or transaction data is retained by this presentation component.
    """

    COLLECTED = QColor("#173e75")
    OUTSTANDING = QColor("#c5a46d")
    TRACK = QColor("#e7edf4")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.paid = Decimal("0")
        self.outstanding = Decimal("0")
        self.percentage = None
        self.setMinimumWidth(200)
        self.setFixedHeight(170)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.set_totals(0, 0)

    def sizeHint(self):
        return QSize(240, 170)

    @staticmethod
    def _nonnegative(value):
        try:
            amount = Decimal(str(value))
            return amount if amount.is_finite() and amount > 0 else Decimal("0")
        except (InvalidOperation, ValueError, TypeError):
            return Decimal("0")

    def set_totals(self, paid, outstanding):
        self.paid = self._nonnegative(paid)
        self.outstanding = self._nonnegative(outstanding)
        total = self.paid + self.outstanding
        self.percentage = self.paid / total * 100 if total else None
        description = (
            "Fee settlement: no fees recorded."
            if self.percentage is None
            else (
                f"Fee settlement: Rs {self.paid:,.2f} collected; "
                f"Rs {self.outstanding:,.2f} outstanding; "
                f"{self.percentage:.2f} percent collected."
            )
        )
        self.setAccessibleName(description)
        self.setToolTip(description)
        self.update()

    def _percentage_text(self):
        if self.percentage is None:
            return "—"
        if self.paid and self.percentage < 1:
            return "<1%"
        # Flooring prevents a positive outstanding balance being labelled 100%.
        value = self.percentage.quantize(Decimal("0.1"), rounding=ROUND_DOWN)
        return f"{value:f}".rstrip("0").rstrip(".") + "%" if value % 1 else f"{value:.0f}%"

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))

        diameter = min(138.0, self.width() - 28.0, self.height() - 28.0)
        thickness = max(11.0, diameter * 0.10)
        bounds = QRectF(
            (self.width() - diameter) / 2 + thickness / 2,
            (self.height() - diameter) / 2 + thickness / 2,
            diameter - thickness,
            diameter - thickness,
        )
        pen = QPen(self.TRACK, thickness, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(bounds)

        if self.percentage is not None:
            # Qt arcs are in sixteenths of a degree; negative sweeps run clockwise.
            collected_sweep = round(float(self.percentage) * 360 * 16 / 100)
            outstanding_sweep = 360 * 16 - collected_sweep
            if outstanding_sweep:
                pen.setColor(self.OUTSTANDING)
                painter.setPen(pen)
                painter.drawArc(bounds, 90 * 16 - collected_sweep, -outstanding_sweep)
            if collected_sweep:
                pen.setColor(self.COLLECTED)
                painter.setPen(pen)
                painter.drawArc(bounds, 90 * 16, -collected_sweep)

        center = bounds.center()
        number = QFont(self.font())
        number.setPixelSize(28 if diameter >= 120 else 24)
        number.setWeight(QFont.Weight.DemiBold)
        inner_width = diameter - 2 * thickness - 12
        while QFontMetricsF(number).horizontalAdvance(self._percentage_text()) > inner_width and number.pixelSize() > 14:
            number.setPixelSize(number.pixelSize() - 1)
        painter.setFont(number)
        painter.setPen(self.COLLECTED)
        painter.drawText(
            QRectF(center.x() - diameter / 2, center.y() - 29, diameter, 39),
            Qt.AlignmentFlag.AlignCenter,
            self._percentage_text(),
        )
        caption = QFont(self.font())
        caption.setPointSizeF(8)
        caption.setWeight(QFont.Weight.Medium)
        caption.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.9)
        painter.setFont(caption)
        painter.setPen(QColor("#62738a"))
        painter.drawText(
            QRectF(center.x() - diameter / 2, center.y() + 13, diameter, 18),
            Qt.AlignmentFlag.AlignCenter,
            "COLLECTED" if self.percentage is not None else "NO FEES YET",
        )
        painter.end()
