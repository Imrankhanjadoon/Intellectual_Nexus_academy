"""Session and animation regressions exercised through the real Qt event loop."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QElapsedTimer, QEvent, QPoint, QPointF, QTimer, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QMessageBox, QScrollArea, QWidget
from shiboken6 import isValid

from nexus.app import SessionController
from nexus.ui.motion import install_motion
from test_desktop import PASSWORD, academy, qapp, ui_messages


def _wait_until(predicate, timeout=2000):
    timer = QElapsedTimer()
    timer.start()
    while not predicate() and timer.elapsed() < timeout:
        QTest.qWait(10)
    assert predicate()


@pytest.fixture
def session(qapp, academy):
    academy.logout()
    controller = SessionController(qapp, academy, transition_ms=40)
    yield controller
    controller.shutdown()
    qapp.removeEventFilter(controller)
    for window in (controller.auth, controller.main):
        if window is not None and isValid(window):
            window.close()
            window.deleteLater()
    controller.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def _sign_in(controller):
    window = controller.auth
    window.login_username.setText("owner")
    window.login_password.setText(PASSWORD)
    window.login_button.click()


def _open_workspace(controller):
    _sign_in(controller)
    _wait_until(lambda: controller.main is not None)


def test_maximized_signin_shows_loading_before_maximized_workspace(session):
    assert session.auth.isVisible()
    assert session.auth.isMaximized()
    _sign_in(session)
    assert session.loading is not None and session.loading.isVisible()
    assert session.main is None
    assert not session.auth.login_button.isEnabled()
    overlay = session.loading
    session.open_workspace()
    assert session.loading is overlay
    _wait_until(lambda: session.main is not None)
    assert session.main.isVisible() and session.main.isMaximized()
    assert session.auth is None
    assert session.loading is None
    assert session.idle.isActive()
    main = session.main
    session.open_workspace()
    QTest.qWait(60)
    assert session.main is main


@pytest.mark.parametrize("choice", [QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes])
def test_signout_confirmation_preserves_or_ends_session(session, monkeypatch, choice):
    _open_workspace(session)
    original = session.main
    questions = []

    def answer(*args):
        questions.append(args)
        return choice

    monkeypatch.setattr(QMessageBox, "question", answer)
    original.logout_requested.emit()
    assert len(questions) == 1
    assert questions[0][0] is original
    assert questions[0][-1] == QMessageBox.StandardButton.No
    assert questions[0][-2] == QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    if choice == QMessageBox.StandardButton.No:
        assert session.main is original and original.isVisible()
        assert session.service.user["username"] == "owner"
        assert session.auth is None
    else:
        assert session.service.user is None
        assert session.main is None
        assert session.auth.isVisible() and session.auth.isMaximized()
        assert not session.idle.isActive()


def test_forced_lock_cancels_pending_signin_without_confirmation(session, monkeypatch):
    _sign_in(session)
    assert session.loading is not None
    old_auth = session.auth
    questions = []
    monkeypatch.setattr(QMessageBox, "question", lambda *_: questions.append(True))
    session.lock()
    assert session.service.user is None
    assert session.auth is not old_auth
    assert session.auth.isMaximized()
    assert session.loading is None
    QTest.qWait(100)
    assert session.main is None
    assert session.auth.isVisible()
    assert not questions


def test_forced_lock_dismisses_modal_child_and_returns_to_signin(session, monkeypatch):
    _open_workspace(session)
    dialog = QDialog(session.main)
    dialog.setModal(True)
    finished = []
    dialog.finished.connect(finished.append)
    questions = []
    monkeypatch.setattr(QMessageBox, "question", lambda *_: questions.append(True))
    QTimer.singleShot(0, session.lock)
    assert dialog.exec() == QDialog.DialogCode.Rejected
    assert finished == [QDialog.DialogCode.Rejected]
    assert session.service.user is None and session.main is None
    assert session.auth.isVisible() and session.auth.isMaximized()
    assert not questions


def test_lock_queued_during_auth_submit_cannot_reopen_authenticated_workspace(session):
    original = session.auth
    QTimer.singleShot(0, session.lock)
    _sign_in(session)
    # Painting submit feedback must not dispatch this lock inside the login action.
    assert session.auth is original
    assert session.service.user is not None
    _wait_until(lambda: session.auth is not original)
    QTest.qWait(100)
    assert session.service.user is None
    assert session.main is None
    assert session.loading is None
    assert session.auth.isVisible()


def test_shutdown_cancels_delayed_workspace_creation(session):
    _sign_in(session)
    session.shutdown()
    QTest.qWait(100)
    assert session.main is None
    assert session.loading is None
    assert not session._transition_timer.isActive()


def _wheel(area, *, angle=0, pixels=0):
    event = QWheelEvent(
        QPointF(20, 20), QPointF(20, 20), QPoint(0, pixels), QPoint(0, angle),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )
    QCoreApplication.sendEvent(area.viewport(), event)


def test_scroll_accumulates_wheel_target_clamps_pixels_and_cancels_on_deletion(qapp, ui_messages):
    area = QScrollArea()
    area.resize(250, 180)
    content = QWidget()
    content.resize(200, 1500)
    area.setWidget(content)
    install_motion(area)
    area.show()
    qapp.processEvents()
    bar = area.verticalScrollBar()
    bar.setValue(100)
    step = max(54, bar.singleStep() * 3)
    _wheel(area, angle=-120)
    _wheel(area, angle=-120)
    _wait_until(lambda: bar.value() == 100 + 2 * step)
    _wheel(area, pixels=-10000)
    assert bar.value() == bar.maximum()
    _wheel(area, pixels=10000)
    assert bar.value() == bar.minimum()
    _wheel(area, angle=-120)
    animation = area._smooth_scroll.animation
    area.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QTest.qWait(200)
    assert not isValid(area)
    assert not isValid(animation)
