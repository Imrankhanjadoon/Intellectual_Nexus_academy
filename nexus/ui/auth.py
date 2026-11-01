"""First-run setup and offline authentication screens."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QBoxLayout, QDialog, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton,
    QMessageBox, QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from .common import show_error
from .architecture import AcademicArchitecture
from .identity import AcademySeal
from .motion import fade_in


AUTH_STYLE = """
QWidget#authRoot { background: #f4f6f8; }
QFrame#authUtility { background: #123766; }
QFrame#authUtility QLabel { color: #e0e7f0; font-size: 10px; letter-spacing: 1px; }
QFrame#authMasthead { background: #ffffff; border-bottom: 1px solid #dce2e9; }
QFrame#authNavigation { background: #ecf0f5; border-bottom: 1px solid #d6dee9; }
QFrame#authNavigation QLabel { color: #586a82; font-size: 11px; }
QFrame#authInformation { background: #173e75; border: none; }
QFrame#authInformation QLabel { color: #c8d6e8; background: transparent; }
QFrame#authInformation QPushButton { color: #e8eef6; background: transparent; border: none; border-bottom: 1px solid rgba(255, 255, 255, 32); border-radius: 0; text-align: left; padding: 10px 1px; font-size: 12px; font-weight: 500; }
QFrame#authInformation QPushButton:hover { color: #ffffff; background: #234d83; }
QFrame#authInformation QPushButton:checked { color: #ffffff; font-weight: 700; border-left: 2px solid #c5a46d; padding-left: 9px; }
QFrame#authInformation QPushButton:disabled { color: #9eb2cc; }
QWidget#authContent { background: #ffffff; }
QFrame#authDocument { background: #ffffff; border: none; border-radius: 0; }
QFrame#authDocument QLabel { background: transparent; color: #273b52; }
QFrame#authDocument QLineEdit { background: #ffffff; border: 1px solid #b9c5d2; border-radius: 3px; padding: 9px 12px; color: #203856; selection-background-color: #dce6f3; }
QFrame#authDocument QLineEdit:focus { border: 2px solid #315c91; padding: 8px 11px; }
QFrame#authDocument QPushButton, QDialog#recoveryDocument QPushButton { border-radius: 3px; border: 1px solid #c6cfda; color: #1c477e; background: #ffffff; padding: 10px 18px; }
QFrame#authDocument QPushButton:hover, QDialog#recoveryDocument QPushButton:hover { background: #edf2f8; }
QFrame#authDocument QPushButton#primary, QDialog#recoveryDocument QPushButton#primary { background: #173e75; color: white; border-color: #173e75; }
QFrame#authDocument QPushButton#primary:hover, QDialog#recoveryDocument QPushButton#primary:hover { background: #12315d; }
QFrame#authDocument QPushButton#authLink { background: transparent; border: none; color: #244c7f; text-decoration: underline; padding: 4px 0; font-weight: 500; }
QLabel#authSection { color: #697d96; font-size: 10px; font-weight: 700; letter-spacing: 1px; }
QLabel#authFooter { color: #79869a; font-size: 10px; }
QDialog#recoveryDocument { background: #ffffff; border-top: 4px solid #c5a46d; }
QScrollBar:vertical { background: #edf1f6; width: 7px; }
QScrollBar::handle:vertical { background: #aab8cb; border-radius: 0; min-height: 28px; }
"""


def _field(placeholder="", password=False):
    widget = QLineEdit()
    widget.setPlaceholderText(placeholder)
    widget.setMinimumHeight(40)
    if password:
        widget.setEchoMode(QLineEdit.EchoMode.Password)
    return widget


def _button(label, handler, primary=False):
    button = QPushButton(label)
    button.setMinimumHeight(42)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary:
        button.setObjectName("primary")
    button.clicked.connect(handler)
    return button


def _title(title, description):
    holder = QWidget()
    layout = QVBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 12)
    label = QLabel(title)
    label.setWordWrap(True)
    label.setStyleSheet("font-size: 28px; font-weight: 600; color: #173e75;")
    layout.addWidget(label)
    text = QLabel(description)
    text.setWordWrap(True)
    text.setStyleSheet("color: #6c7b8e; font-size: 13px;")
    layout.addWidget(text)
    return holder


class RecoveryFileDialog(QDialog):
    """Save a private recovery file without displaying its secret contents."""

    def __init__(self, service, recovery_code, parent=None):
        super().__init__(parent)
        self.service = service
        self._recovery_code = recovery_code
        self.setObjectName("recoveryDocument")
        self.setStyleSheet(AUTH_STYLE)
        self.setWindowTitle("Save your recovery file")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(20)
        section = QLabel("ACCOUNT PROTECTION")
        section.setObjectName("authSection")
        layout.addWidget(section)
        layout.addWidget(_title("Save your recovery file", "If you forget your password, choose this file on the Reset password screen to set a new one."))
        instructions = QLabel("Save the file to a private USB drive or another safe location. Anyone with this file can reset the academy administrator's password, so keep it separate from the academy database.")
        instructions.setWordWrap(True)
        instructions.setStyleSheet("color: #6c7b8e; font-size: 13px;")
        layout.addWidget(instructions)
        layout.addWidget(_button("Save recovery file…", self._save, True))
        later = _button("Save later", self.reject)
        later.setObjectName("quiet")
        layout.addWidget(later)

    def _save(self):
        destination, _ = QFileDialog.getSaveFileName(
            self, "Save recovery file", "academy-recovery.nexus-key",
            "Nexus recovery file (*.nexus-key)",
        )
        if not destination:
            return
        if not destination.lower().endswith(".nexus-key"):
            destination += ".nexus-key"
        try:
            self.service.save_recovery_file(destination, recovery_code=self._recovery_code)
            self._recovery_code = None
            self.accept()
        except Exception as exc:
            show_error(self, exc)


class AuthWindow(QMainWindow):
    authenticated = Signal()

    def __init__(self, service):
        super().__init__()
        self.service = service
        self._busy = False
        self._submit_button = None
        self._submit_text = ""
        self.setWindowTitle("Intellectual Nexus Academy | Administration Portal")
        self.resize(1280, 860)
        self.setMinimumSize(900, 720)
        container = QWidget()
        container.setObjectName("authRoot")
        self.setCentralWidget(container)
        self.setStyleSheet(AUTH_STYLE)
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        utility = QFrame()
        utility.setObjectName("authUtility")
        utility_layout = QHBoxLayout(utility)
        utility_layout.setContentsMargins(38, 8, 38, 8)
        utility_layout.addWidget(QLabel("INTELLECTUAL NEXUS ACADEMY"))
        utility_layout.addStretch()
        utility_layout.addWidget(QLabel("ADMINISTRATIVE SERVICES"))
        outer.addWidget(utility)
        outer.addWidget(self._brand())
        navigation = QFrame()
        navigation.setObjectName("authNavigation")
        navigation_layout = QHBoxLayout(navigation)
        navigation_layout.setContentsMargins(38, 11, 38, 11)
        navigation_layout.addWidget(QLabel("Academy services    /    Staff access"))
        navigation_layout.addStretch()
        navigation_layout.addWidget(QLabel("Local installation · Offline system"))
        outer.addWidget(navigation)
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(38, 30, 38, 14)
        body_layout.setSpacing(0)
        self.access_buttons = []
        body_layout.addWidget(self._information_panel(), 4)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._login_page())
        self.pages.addWidget(self._signup_page())
        self.pages.addWidget(self._recovery_page())
        self.pages.addWidget(self._setup_page())
        self.pages.currentChanged.connect(self._sync_access_nav)
        body_layout.addWidget(self.pages, 7)
        outer.addWidget(body, 1)
        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(38, 8, 38, 18)
        name = QLabel("INTELLECTUAL NEXUS ACADEMY  /  RECORDS ADMINISTRATION")
        name.setObjectName("authFooter")
        footer_layout.addWidget(name)
        footer_layout.addStretch()
        local = QLabel("Authorized staff access")
        local.setObjectName("authFooter")
        footer_layout.addWidget(local)
        outer.addWidget(footer)
        self.pages.setCurrentIndex(3 if self.service.setup_required() else 0)
        self._sync_access_nav(self.pages.currentIndex())

    def _brand(self):
        masthead = QFrame()
        masthead.setObjectName("authMasthead")
        layout = QHBoxLayout(masthead)
        layout.setContentsMargins(38, 19, 38, 19)
        layout.setSpacing(22)
        layout.addWidget(AcademySeal(78))
        titles = QVBoxLayout()
        titles.setSpacing(9)
        name = QLabel("Intellectual Nexus Academy")
        name.setWordWrap(True)
        name.setStyleSheet("font-family: Georgia, 'DejaVu Serif', serif; color: #123766; font-size: 29px; font-weight: 600;")
        titles.addWidget(name)
        subtitle = QLabel("ADMINISTRATION & STUDENT RECORDS")
        subtitle.setStyleSheet("color: #6c7b8e; font-size: 10px; font-weight: 600; letter-spacing: 2px;")
        titles.addWidget(subtitle)
        layout.addLayout(titles, 1)
        designation = QLabel("ACADEMY PORTAL\nAdmissions · Accounts · Academic records")
        designation.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        designation.setStyleSheet("color: #6d7d92; font-size: 11px;")
        layout.addWidget(designation)
        return masthead

    def _information_panel(self):
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(248)
        scroll.setMaximumWidth(360)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        panel = QFrame()
        panel.setObjectName("authInformation")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(30, 28, 30, 26)
        layout.setSpacing(14)
        caption = QLabel("ACADEMY ADMINISTRATION")
        caption.setStyleSheet("color: #c5a46d; font-size: 10px; font-weight: 600; letter-spacing: 1px;")
        layout.addWidget(caption)
        title = QLabel("Staff services")
        title.setWordWrap(True)
        title.setStyleSheet("font-family: Georgia, 'DejaVu Serif', serif; font-size: 27px; color: #ffffff;")
        layout.addWidget(title)
        description = QLabel("Staff access to admissions, fee administration and academic records.")
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 13px; color: #c8d6e8;")
        layout.addWidget(description)
        layout.addSpacing(4)
        for index, label in enumerate(("01   Staff sign in", "02   Staff registration", "03   Reset password")):
            button = QPushButton(label)
            button.setMinimumHeight(38)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, target=index: self._go(target))
            button.setEnabled(not self.service.setup_required())
            layout.addWidget(button)
            self.access_buttons.append(button)
        layout.addStretch(1)
        layout.addWidget(AcademicArchitecture())
        support_title = QLabel("ACCOUNT ASSISTANCE")
        support_title.setStyleSheet("color: #c5a46d; font-size: 10px; font-weight: 600; letter-spacing: 1px;")
        layout.addWidget(support_title)
        support = QLabel("Staff permissions and password resets are managed by the academy administrator.")
        support.setWordWrap(True)
        support.setStyleSheet("color: #b5c8df; font-size: 12px;")
        layout.addWidget(support)
        scroll.setWidget(panel)
        return scroll

    def _sync_access_nav(self, index):
        for position, button in enumerate(self.access_buttons):
            button.setChecked(position == index)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "setup_columns"):
            self.setup_columns.setDirection(
                QBoxLayout.Direction.TopToBottom
                if self.width() < 1060 else QBoxLayout.Direction.LeftToRight
            )

    def _page(self, title, subtitle, section="STAFF SERVICES", width=640):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("authContent")
        outer = QVBoxLayout(content)
        outer.setContentsMargins(38, 28, 38, 28)
        outer.setSpacing(0)
        card = QFrame()
        card.setObjectName("authDocument")
        card.setMaximumWidth(width)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(18)
        section_label = QLabel(section)
        section_label.setObjectName("authSection")
        section_label.setWordWrap(True)
        card_layout.addWidget(section_label)
        card_layout.addWidget(_title(title, subtitle))
        outer.addWidget(card)
        outer.addStretch(1)
        scroll.setWidget(content)
        return scroll, card_layout

    @staticmethod
    def _link(label, callback):
        button = _button(label, callback)
        button.setObjectName("authLink")
        button.setMinimumHeight(28)
        return button

    def _go(self, index):
        if self._busy:
            return
        self.login_password.clear()
        self.signup_password.clear()
        self.signup_confirm.clear()
        self.recovery_password.clear()
        self.recovery_confirm.clear()
        self.recovery_file.clear()
        self.pages.setCurrentIndex(index)
        fade_in(self.pages.currentWidget())

    def _login_page(self):
        page, layout = self._page("Staff sign in", "Enter your assigned account details to access academy records.", "ACCOUNT ACCESS")
        self.login_username = _field("Enter username")
        self.login_password = _field("Enter password", True)
        form = QFormLayout()
        form.setVerticalSpacing(14)
        form.addRow("Username", self.login_username)
        form.addRow("Password", self.login_password)
        layout.addLayout(form)
        self.login_password.returnPressed.connect(self._login)
        self.login_button = _button("Sign in", self._login, True)
        layout.addWidget(self.login_button)
        self.login_message = QLabel("")
        self.login_message.setWordWrap(True)
        self.login_message.setStyleSheet("color: #244c7f; font-size: 12px;")
        layout.addWidget(self.login_message)
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #dce2ea;")
        layout.addWidget(divider)
        links = QHBoxLayout()
        links.addWidget(self._link("Staff account registration", lambda: self._go(1)))
        links.addStretch()
        links.addWidget(self._link("Forgot password?", lambda: self._go(2)))
        layout.addLayout(links)
        notice = QLabel("New staff registrations require approval by the academy administrator.")
        notice.setWordWrap(True)
        notice.setStyleSheet("color: #6c7b8e; font-size: 12px;")
        layout.addWidget(notice)
        return page

    def _signup_page(self):
        page, layout = self._page("Staff account registration", "Submit your details for administrator approval. Account permissions are assigned by the academy.", "ACCOUNT SERVICES / REGISTRATION")
        self.signup_name = _field("Your full name")
        self.signup_username = _field("Choose a unique username")
        self.signup_password = _field("At least 10 characters", True)
        self.signup_confirm = _field("Repeat password", True)
        form = QFormLayout()
        form.setVerticalSpacing(14)
        form.addRow("Full name", self.signup_name)
        form.addRow("Username", self.signup_username)
        form.addRow("Password", self.signup_password)
        form.addRow("Confirm", self.signup_confirm)
        layout.addLayout(form)
        self.signup_button = _button("Submit registration request", self._signup, True)
        layout.addWidget(self.signup_button)
        layout.addWidget(self._link("Return to sign in", lambda: self._go(0)))
        return page

    def _recovery_page(self):
        page, layout = self._page(
            "Reset password", "Choose your saved recovery file and enter a new password.",
            "ACCOUNT SERVICES / PASSWORD RESET",
        )
        self.recovery_file = _field("Choose your saved .nexus-key file")
        self.recovery_file.setReadOnly(True)
        picker = QWidget()
        picker_layout = QHBoxLayout(picker)
        picker_layout.setContentsMargins(0, 0, 0, 0)
        picker_layout.setSpacing(10)
        picker_layout.addWidget(self.recovery_file, 1)
        picker_layout.addWidget(_button("Choose file…", self._choose_recovery_file))
        self.recovery_password = _field("At least 10 characters", True)
        self.recovery_confirm = _field("Repeat new password", True)
        form = QFormLayout()
        form.setVerticalSpacing(14)
        form.addRow("Recovery file", picker)
        form.addRow("New password", self.recovery_password)
        form.addRow("Confirm", self.recovery_confirm)
        layout.addLayout(form)
        self.recovery_button = _button("Reset password", self._recover, True)
        layout.addWidget(self.recovery_button)
        note = QLabel("Staff members: ask your academy administrator to reset your password. The administrator's recovery file is saved during setup or from Administration.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #6c7b8e; font-size: 12px;")
        layout.addWidget(note)
        layout.addWidget(self._link("Return to sign in", lambda: self._go(0)))
        return page

    def _choose_recovery_file(self):
        if self._busy:
            return
        source, _ = QFileDialog.getOpenFileName(
            self, "Choose recovery file", "", "Nexus recovery file (*.nexus-key)",
        )
        if source:
            self.recovery_file.setText(source)
            self.recovery_file.setToolTip(source)

    def _setup_page(self):
        page, layout = self._page("Initial academy setup", "Complete the academy particulars and create the owner account for this local installation.", "GETTING STARTED / LOCAL INSTALLATION", 700)
        self.academy_name = _field("Academy name")
        self.academy_name.setText("Intellectual Nexus Academy")
        self.academy_name.setCursorPosition(0)
        self.academy_address = _field("Campus address")
        self.academy_phone = _field("Contact number")
        self.owner_name = _field("Owner's full name")
        self.owner_username = _field("Choose an owner username")
        self.owner_password = _field("At least 10 characters", True)
        self.owner_confirm = _field("Repeat password", True)
        columns = QHBoxLayout()
        self.setup_columns = columns
        columns.setSpacing(28)
        for title, fields in [
            ("01   ACADEMY PARTICULARS", [("Academy name", self.academy_name), ("Address", self.academy_address), ("Contact number", self.academy_phone)]),
            ("02   OWNER ACCOUNT", [("Full name", self.owner_name), ("Username", self.owner_username), ("Password", self.owner_password), ("Confirm password", self.owner_confirm)]),
        ]:
            column = QVBoxLayout()
            column.setSpacing(8)
            section = QLabel(title)
            section.setObjectName("authSection")
            column.addWidget(section)
            column.addSpacing(5)
            for label, field in fields:
                column.addWidget(QLabel(label))
                column.addWidget(field)
            column.addStretch()
            columns.addLayout(column, 1)
        layout.addLayout(columns)
        note = QLabel("After setup, save a recovery file to a private USB drive or another safe location. You can use it to reset a forgotten password without internet.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #6c7b8e; font-size: 12px;")
        layout.addWidget(note)
        self.setup_button = _button("Complete initial setup", self._setup, True)
        layout.addWidget(self.setup_button)
        return page

    def _begin_submit(self, button, message):
        if self._busy:
            return False
        self._busy = True
        self._submit_button = button
        self._submit_text = button.text()
        button.setText(message)
        button.setEnabled(False)
        button.setCursor(Qt.CursorShape.WaitCursor)
        # Paint feedback without dispatching a lock/shutdown inside this action.
        button.repaint()
        return True

    def _finish_submit(self):
        if self._submit_button is not None:
            self._submit_button.setText(self._submit_text)
            self._submit_button.setEnabled(True)
            self._submit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._submit_button = None
        self._busy = False

    def offer_recovery_file(self, recovery_code):
        saved = RecoveryFileDialog(self.service, recovery_code, self).exec() == QDialog.DialogCode.Accepted
        if not saved:
            QMessageBox.information(
                self, "Save a recovery file later",
                "Your academy account has been created. You can save a recovery file later from Administration. Until then, keep your password safe.",
            )
        return saved

    def _login(self):
        if not self._begin_submit(self.login_button, "Signing in…"):
            return
        try:
            self.service.login(self.login_username.text().strip(), self.login_password.text())
        except Exception as exc:
            self.login_password.clear()
            self._finish_submit()
            show_error(self, exc)
            return
        self.login_password.clear()
        self.login_button.setText("Opening workspace…")
        self.authenticated.emit()

    def _signup(self):
        if not self._begin_submit(self.signup_button, "Submitting request…"):
            return
        try:
            if self.signup_password.text() != self.signup_confirm.text():
                raise ValueError("The two passwords do not match.")
            self.service.signup(self.signup_name.text().strip(), self.signup_username.text().strip(), self.signup_password.text())
        except Exception as exc:
            self._finish_submit()
            show_error(self, exc)
            return
        self.login_username.setText(self.signup_username.text().strip())
        self.signup_name.clear()
        self.signup_username.clear()
        self._finish_submit()
        self._go(0)
        self.login_message.setText("Account request received. Ask the academy administrator to approve your access before signing in.")

    def _recover(self):
        if not self._begin_submit(self.recovery_button, "Resetting password…"):
            return
        try:
            if not self.recovery_file.text().strip():
                raise ValueError("Choose your saved recovery file first.")
            if self.recovery_password.text() != self.recovery_confirm.text():
                raise ValueError("The two passwords do not match.")
            self.service.reset_password_with_file(self.recovery_file.text().strip(), self.recovery_password.text())
        except Exception as exc:
            self._finish_submit()
            show_error(self, exc)
            return
        self._finish_submit()
        self._go(0)
        self.login_message.setText("Password reset. Sign in with your new password.")
        if self.login_username.text().strip():
            self.login_password.setFocus()
        else:
            self.login_username.setFocus()

    def _setup(self):
        if not self._begin_submit(self.setup_button, "Creating academy…"):
            return
        try:
            if self.owner_password.text() != self.owner_confirm.text():
                raise ValueError("The two passwords do not match.")
            result = self.service.setup_academy(
                self.academy_name.text().strip(), self.academy_address.text().strip(),
                self.academy_phone.text().strip(), self.owner_name.text().strip(),
                self.owner_username.text().strip(), self.owner_password.text(),
            )
        except Exception as exc:
            self._finish_submit()
            show_error(self, exc)
            return
        self.owner_password.clear()
        self.owner_confirm.clear()
        self.setup_button.setText("Preparing account…")
        try:
            self.offer_recovery_file(result["recovery_code"])
        except Exception:
            QMessageBox.information(
                self, "Academy account created",
                "Your academy account was created. Save a recovery file later from Administration to protect access if you forget your password.",
            )
        self.authenticated.emit()
