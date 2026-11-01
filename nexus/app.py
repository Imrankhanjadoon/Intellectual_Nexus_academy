"""Application lifecycle; no servers or Internet connection required."""
import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QLockFile, QObject, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from .services import AcademyService, default_data_dir
from . import __version__
from .ui.auth import AuthWindow
from .ui.shell import MainWindow
from .ui.theme import STYLE
from .ui.identity import seal_pixmap
from .ui.motion import LoadingOverlay, install_motion


class SessionController(QObject):
    def __init__(self, app, service, transition_ms=320):
        super().__init__(app)
        self.app = app
        self.service = service
        self.auth = None
        self.main = None
        self.loading = None
        self._opening = False
        self._transition_timer = QTimer(self)
        self._transition_timer.setSingleShot(True)
        self._transition_timer.setInterval(transition_ms)
        self._transition_timer.timeout.connect(self._finish_signin)
        self.idle = QTimer(self)
        self.idle.setSingleShot(True)
        self.idle.setInterval(15 * 60 * 1000)
        self.idle.timeout.connect(self.lock)
        app.installEventFilter(self)
        self.show_auth()

    def eventFilter(self, watched, event):
        if self.service.user and event.type() in (
            QEvent.Type.MouseButtonPress, QEvent.Type.KeyPress, QEvent.Type.Wheel,
        ):
            self.idle.start()
        return False

    def show_auth(self):
        self.auth = AuthWindow(self.service)
        self.auth.authenticated.connect(self.open_workspace)
        install_motion(self.auth)
        self.auth.showMaximized()

    def open_workspace(self):
        if self._opening or self.main is not None or self.service.user is None:
            return
        self._opening = True
        if self.auth is not None:
            self.loading = LoadingOverlay(self.auth.centralWidget())
        # Yield to the event loop so progress is visible during initialization.
        self._transition_timer.start()

    def _finish_signin(self):
        if not self._opening or self.service.user is None:
            return
        try:
            self.main = MainWindow(self.service)
            self.main.logout_requested.connect(self.request_signout)
            self.main.reauthentication_required.connect(self.lock)
            install_motion(self.main)
            self.main.showMaximized()
            if self.loading is not None:
                self.loading.hide()
                self.loading.deleteLater()
                self.loading = None
            if self.auth is not None:
                self.auth.close()
                self.auth.deleteLater()
                self.auth = None
            self._opening = False
            self.idle.start()
        except Exception as exc:
            self.lock()
            QMessageBox.warning(self.auth, "Unable to open workspace", str(exc))

    def request_signout(self):
        if self.main is None or self.service.user is None:
            return
        choice = QMessageBox.question(
            self.main, "Sign out of the academy?",
            "Sign out and return to the sign-in screen?\n\nAny unsaved form changes will be lost.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice == QMessageBox.StandardButton.Yes:
            self.lock()

    def lock(self):
        self.idle.stop()
        self._transition_timer.stop()
        self._opening = False
        if self.loading is not None:
            self.loading.hide()
            self.loading.deleteLater()
            self.loading = None
        # Close any open entry dialogs before disposing of authenticated pages.
        # A restored database also deliberately returns to fresh authentication.
        if self.main is not None:
            from PySide6.QtWidgets import QDialog
            for dialog in self.main.findChildren(QDialog):
                dialog.reject()
        previous_auth = self.auth
        self.service.logout()
        self.show_auth()
        if previous_auth is not None:
            previous_auth.close()
            previous_auth.deleteLater()
        if self.main is not None:
            self.main.close()
            self.main.deleteLater()
            self.main = None

    def shutdown(self):
        self.idle.stop()
        self._transition_timer.stop()
        self._opening = False
        if self.loading is not None:
            self.loading.hide()
            self.loading.deleteLater()
            self.loading = None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Intellectual Nexus Academy · offline desktop")
    parser.add_argument("--data-dir", type=Path, help="Use a separate local data folder (optional)")
    args = parser.parse_args(argv)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Intellectual Nexus Academy")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Intellectual Nexus")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setWindowIcon(QIcon(seal_pixmap()))
    app.setStyleSheet(STYLE)
    try:
        data_dir = (args.data_dir or default_data_dir()).expanduser().resolve()
        data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        instance_lock = QLockFile(str(data_dir / ".nexus.lock"))
        instance_lock.setStaleLockTime(0)
        if not instance_lock.tryLock(100):
            QMessageBox.warning(None, "Academy workspace already open", "An instance is already using this data folder. Close it before starting another app or restoring a backup.")
            return 1
        service = AcademyService(data_dir)
    except Exception as exc:
        QMessageBox.critical(None, "Unable to open academy records", str(exc))
        return 1
    controller = SessionController(app, service)
    app.aboutToQuit.connect(controller.shutdown)
    app.aboutToQuit.connect(service.close)
    app.aboutToQuit.connect(instance_lock.unlock)
    # Retain the controller for the entire Qt event loop.
    app.session_controller = controller
    return app.exec()
