"""Restrained input feedback and cancellable transitions for the desktop UI."""
from PySide6.QtCore import (
    QAbstractAnimation, QEasingCurve, QEvent, QObject, QPointF,
    QPropertyAnimation, Qt, QVariantAnimation,
)
from PySide6.QtGui import QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractScrollArea, QApplication, QFrame,
    QGraphicsOpacityEffect, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)


def enabled():
    app = QApplication.instance()
    return bool(app) and not bool(app.property("reduce_motion"))


class ButtonFeedback(QWidget):
    """A moving hover accent and a short press ripple, without moving the layout."""
    def __init__(self, button):
        super().__init__(button)
        self.button = button
        self.hover = 0.0
        self.press = 1.0
        self.origin = QPointF()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setGeometry(button.rect())
        self.hover_animation = QVariantAnimation(self)
        self.hover_animation.setDuration(140)
        self.hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.hover_animation.valueChanged.connect(self._hover_frame)
        self.press_animation = QVariantAnimation(self)
        self.press_animation.setDuration(240)
        self.press_animation.setStartValue(0.0)
        self.press_animation.setEndValue(1.0)
        self.press_animation.valueChanged.connect(self._press_frame)
        button.installEventFilter(self)
        self.show()

    def _hover_frame(self, value):
        self.hover = float(value)
        self.update()

    def _press_frame(self, value):
        self.press = float(value)
        self.update()

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind == QEvent.Type.Resize:
            self.setGeometry(self.button.rect())
        elif kind in (QEvent.Type.Enter, QEvent.Type.Leave):
            self.hover_animation.stop()
            if enabled() and self.button.isEnabled():
                self.hover_animation.setStartValue(self.hover)
                self.hover_animation.setEndValue(1.0 if kind == QEvent.Type.Enter else 0.0)
                self.hover_animation.start()
            else:
                self.hover = 0.0
                self.update()
        elif kind == QEvent.Type.MouseButtonPress and enabled() and self.button.isEnabled():
            self.origin = event.position()
            self.press_animation.stop()
            self.press_animation.start()
        elif kind in (QEvent.Type.Hide, QEvent.Type.EnabledChange):
            self.hover_animation.stop()
            self.press_animation.stop()
            self.hover, self.press = 0.0, 1.0
            self.update()
        return False

    def paintEvent(self, event):
        if not enabled() or not self.button.isEnabled():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        ink = self.button.palette().color(QPalette.ColorRole.ButtonText)
        if ink.lightness() < 80:
            ink = QColor("#315e99")
        if self.hover > 0.01:
            color = QColor(ink)
            color.setAlphaF(0.60 * self.hover)
            painter.setPen(QPen(color, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            span = max(0, (self.width() - 22) * self.hover)
            painter.drawLine(QPointF((self.width()-span)/2, self.height()-3), QPointF((self.width()+span)/2, self.height()-3))
        if self.press < 0.99:
            color = QColor(ink)
            color.setAlphaF(0.10 * (1-self.press))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            radius = max(self.width(), self.height()) * self.press
            painter.drawEllipse(self.origin, radius, radius)
        painter.end()


class SmoothScroll(QObject):
    def __init__(self, area):
        super().__init__(area)
        self.area = area
        self.animation = QPropertyAnimation(area.verticalScrollBar(), b"value", self)
        self.animation.setDuration(160)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        area.viewport().installEventFilter(self)
        if isinstance(area, QAbstractItemView):
            area.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Hide:
            self.animation.stop()
        if event.type() != QEvent.Type.Wheel or not enabled() or event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            return False
        bar = self.area.verticalScrollBar()
        delta = event.pixelDelta().y() or event.angleDelta().y()
        if not delta or bar.maximum() <= bar.minimum():
            return False
        start = bar.value()
        previous = int(self.animation.endValue()) if self.animation.state() == QAbstractAnimation.State.Running else start
        if event.pixelDelta().y():
            movement = event.pixelDelta().y()
        else:
            movement = int(event.angleDelta().y() / 120 * max(54, bar.singleStep() * 3))
        target = max(bar.minimum(), min(bar.maximum(), previous - movement))
        if target == start and target == previous:
            return False  # Nested documents can continue scrolling their parent.
        self.animation.stop()
        if event.pixelDelta().y():
            bar.setValue(target)
        else:
            self.animation.setStartValue(start)
            self.animation.setEndValue(target)
            self.animation.start()
        event.accept()
        return True


class MotionManager(QObject):
    def __init__(self, app):
        super().__init__(app)
        app.installEventFilter(self)

    def enhance(self, widget):
        if isinstance(widget, QPushButton) and not hasattr(widget, "_motion_feedback"):
            widget._motion_feedback = ButtonFeedback(widget)
        if isinstance(widget, QAbstractScrollArea) and not hasattr(widget, "_smooth_scroll"):
            widget._smooth_scroll = SmoothScroll(widget)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Show and isinstance(watched, QWidget):
            self.enhance(watched)
        return False


def install_motion(root):
    app = QApplication.instance()
    if app is None:
        return
    manager = getattr(app, "_nexus_motion_manager", None)
    if manager is None:
        manager = app._nexus_motion_manager = MotionManager(app)
    manager.enhance(root)
    for child in root.findChildren(QWidget):
        manager.enhance(child)


def fade_in(widget, duration=180):
    if not enabled():
        return
    previous = getattr(widget, "_fade_animation", None)
    if previous:
        previous.stop()
        previous.deleteLater()
    widget.setGraphicsEffect(None)
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    widget._fade_animation = animation
    animation.setStartValue(0.45)
    animation.setEndValue(1.0)
    animation.setDuration(duration)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def finished():
        if getattr(widget, "_fade_animation", None) is animation:
            widget.setGraphicsEffect(None)
            widget._fade_animation = None
        animation.deleteLater()

    animation.finished.connect(finished)
    animation.start()


class LoadingOverlay(QFrame):
    """Indeterminate progress while the authenticated workspace is prepared."""
    def __init__(self, parent, message="Opening your workspace", detail="Loading academy records and office services…"):
        super().__init__(parent)
        self.setObjectName("loadingOverlay")
        self.setStyleSheet("QFrame#loadingOverlay { background: #f4f7fc; }")
        self.setGeometry(parent.rect())
        parent.installEventFilter(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.addStretch()
        card = QFrame()
        card.setObjectName("card")
        card.setFixedWidth(500)
        content = QVBoxLayout(card)
        content.setContentsMargins(34, 32, 34, 32)
        content.setSpacing(16)
        title = QLabel(message)
        title.setObjectName("pageTitle")
        title.setWordWrap(True)
        content.addWidget(title)
        text = QLabel(detail)
        text.setObjectName("muted")
        text.setWordWrap(True)
        content.addWidget(text)
        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.setFixedHeight(5)
        progress.setTextVisible(False)
        content.addWidget(progress)
        layout.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()
        self.show()
        self.raise_()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize:
            self.setGeometry(watched.rect())
        return False
