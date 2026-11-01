"""Staff administration, academy settings, and safe local backup tools."""
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QTabWidget, QVBoxLayout, QWidget,
)

from .common import BasePage, fill_table, heading, selected_id, show_error, success, table


ROLE_LABELS = {"receptionist": "Receptionist", "cashier": "Cashier / Accountant", "teacher": "Teacher"}


def _button(label, callback, primary=False, danger=False):
    widget = QPushButton(label)
    widget.setMinimumHeight(38)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.clicked.connect(callback)
    if primary:
        widget.setObjectName("primary")
    if danger:
        widget.setObjectName("danger")
    return widget


def _field(placeholder="", password=False):
    field = QLineEdit()
    field.setPlaceholderText(placeholder)
    field.setMinimumHeight(38)
    if password:
        field.setEchoMode(QLineEdit.EchoMode.Password)
    return field


def _roles():
    combo = QComboBox()
    for role, label in ROLE_LABELS.items():
        combo.addItem(label, role)
    return combo


def _dialog(title, parent):
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setMinimumWidth(450)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(18)
    return dialog, layout


def _section(title, description=""):
    """Compact section titles for administrative forms and registers."""
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    label = QLabel(title)
    label.setObjectName("sectionTitle")
    layout.addWidget(label)
    if description:
        note = QLabel(description)
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
    return widget


def _panel():
    panel = QFrame()
    panel.setObjectName("card")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(22, 20, 22, 20)
    layout.setSpacing(16)
    return panel, layout


def _panel_header(title, description=""):
    header = QFrame()
    header.setObjectName("registerHeader")
    row = QHBoxLayout(header)
    row.setContentsMargins(22, 16, 22, 16)
    row.setSpacing(18)
    row.addWidget(_section(title, description), 1)
    return header, row


class UsersPage(BasePage):
    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        self._users = []
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(180)
        self._filter_timer.timeout.connect(self._apply_filter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(18)
        layout.addWidget(heading("Staff access register", "ADMINISTRATION  /  STAFF ACCOUNTS AND PERMISSIONS"))
        register, register_layout = _panel()
        register_layout.setContentsMargins(0, 0, 0, 0)
        register_layout.setSpacing(0)
        header, bar = _panel_header("Staff directory", "Account approval and assigned access roles.")
        bar.addWidget(_button("Register staff member", self._create, True))
        register_layout.addWidget(header)
        body = QVBoxLayout()
        body.setContentsMargins(22, 18, 22, 18)
        body.setSpacing(16)
        search_row = QHBoxLayout()
        search_row.setSpacing(10)
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setAccessibleName("Search staff accounts")
        self.search.setPlaceholderText("Search name, username, role or account status…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda *_: self._filter_timer.start())
        search_row.addWidget(self.search, 1)
        self.clear_filter = _button("Clear search", self._clear_filter)
        search_row.addWidget(self.clear_filter)
        body.addLayout(search_row)
        self.summary = QLabel("No staff accounts yet")
        self.summary.setObjectName("muted")
        register_meta = QHBoxLayout()
        register_meta.addWidget(self.summary, 1)
        refresh = _button("Refresh register", self.refresh)
        refresh.setObjectName("quiet")
        register_meta.addWidget(refresh)
        body.addLayout(register_meta)
        self.accounts = table(["STAFF MEMBER", "USERNAME", "ACCESS ROLE", "ACCOUNT STATUS"])
        self.accounts.itemSelectionChanged.connect(self._selection_changed)
        body.addWidget(self.accounts, 1)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.approve_button = _button("Approve account…", self._approve, True)
        self.active_button = _button("Deactivate account", self._toggle_active)
        self.reset_button = _button("Reset password…", self._reset)
        actions.addWidget(self.approve_button)
        actions.addWidget(self.active_button)
        actions.addWidget(self.reset_button)
        actions.addStretch()
        body.addLayout(actions)
        note = QLabel("Account requests require administrator approval. Administrator privileges remain with the academy owner.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        body.addWidget(note)
        register_layout.addLayout(body, 1)
        layout.addWidget(register, 1)
        self._selection_changed()

    def refresh(self):
        try:
            self._users = self.service.list_users()
            self._filter_timer.stop()
            self._apply_filter()
        except Exception as exc:
            show_error(self, exc)

    def _clear_filter(self):
        self.search.clear()
        self._filter_timer.stop()
        self._apply_filter()
        self.search.setFocus()

    def _apply_filter(self):
        try:
            tokens = self.search.text().strip().casefold().split()
            previous = selected_id(self.accounts)
            previous_id = previous["id"] if previous else None
            users = [
                user for user in self._users
                if all(token in " ".join([
                    user["full_name"], user["username"], user["role"],
                    ROLE_LABELS.get(user["role"], "Owner Administrator"), user["status"],
                ]).casefold() for token in tokens)
            ]
            self.accounts.blockSignals(True)
            try:
                fill_table(self.accounts, [
                    [u["full_name"], u["username"], ROLE_LABELS.get(u["role"], "Owner / Administrator"), u["status"].title()]
                    for u in users
                ], users)
                self.accounts.clearSelection()
                self.accounts.setCurrentCell(-1, -1)
                for index, user in enumerate(users):
                    if user["id"] == previous_id:
                        self.accounts.selectRow(index)
                        break
            finally:
                self.accounts.blockSignals(False)
            pending = sum(u["status"].lower() == "pending" for u in self._users)
            active = sum(u["status"].lower() == "active" for u in self._users)
            self.summary.setText(
                f"{len(users)} of {len(self._users)} accounts shown  ·  {active} active in total  ·  {pending} awaiting approval"
            )
            if tokens and not users:
                self.summary.setText("No accounts match this search. Clear the search to view all staff.")
            self.clear_filter.setEnabled(bool(self.search.text()))
            self._selection_changed()
        except Exception as exc:
            show_error(self, exc)

    def _selected(self):
        user = selected_id(self.accounts)
        if not user:
            raise ValueError("Select a staff account first.")
        return user

    def _selection_changed(self):
        user = selected_id(self.accounts)
        pending = bool(user and user["status"].lower() == "pending")
        protected = bool(user and (user["role"] == "admin" or user["id"] == self.service.user["id"]))
        self.approve_button.setEnabled(pending)
        self.active_button.setEnabled(bool(user and not protected and not pending))
        self.reset_button.setEnabled(bool(user and not protected))
        self.active_button.setText("Reactivate account" if user and user["status"].lower() != "active" else "Deactivate account")

    def _create(self):
        dialog, layout = _dialog("Register staff member", self)
        layout.addWidget(heading("Staff account registration", "New accounts are active immediately. Provide the initial password to the staff member privately."))
        full_name = _field("Full name")
        username = _field("Unique username")
        password = _field("At least 10 characters", True)
        confirm = _field("Repeat password", True)
        role = _roles()
        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow("Full name", full_name)
        form.addRow("Username", username)
        form.addRow("Role", role)
        form.addRow("Password", password)
        form.addRow("Confirm", confirm)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        def save():
            try:
                if password.text() != confirm.text():
                    raise ValueError("The two passwords do not match.")
                self.service.create_staff(full_name.text().strip(), username.text().strip(), password.text(), role.currentData())
                password.clear()
                confirm.clear()
                dialog.accept()
                self.refresh()
                self.changed.emit()
            except Exception as exc:
                show_error(dialog, exc)

        buttons.accepted.connect(save)
        dialog.exec()

    def _approve(self):
        try:
            user = self._selected()
        except Exception as exc:
            show_error(self, exc)
            return
        dialog, layout = _dialog("Approve staff account", self)
        layout.addWidget(heading("Approve account", f"Assign a role for {user['full_name']} ({user['username']})."))
        role = _roles()
        form = QFormLayout()
        form.addRow("Access role", role)
        layout.addLayout(form)
        note = QLabel("Receptionist: admissions and challans\nCashier: fee collection and reports\nTeacher: assigned-class attendance")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Approve account")
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        def approve():
            try:
                self.service.approve_user(user["id"], role.currentData())
                dialog.accept()
                self.refresh()
                self.changed.emit()
            except Exception as exc:
                show_error(dialog, exc)

        buttons.accepted.connect(approve)
        dialog.exec()

    def _toggle_active(self):
        try:
            user = self._selected()
            active = user["status"].lower() != "active"
            verb = "Reactivate" if active else "Deactivate"
            if QMessageBox.question(self, f"{verb} account?", f"{verb} access for {user['full_name']}?" + (" They will no longer be able to use the academy workspace." if not active else "")) != QMessageBox.StandardButton.Yes:
                return
            self.service.set_user_active(user["id"], active)
            self.refresh()
            self.changed.emit()
        except Exception as exc:
            show_error(self, exc)

    def _reset(self):
        try:
            user = self._selected()
        except Exception as exc:
            show_error(self, exc)
            return
        dialog, layout = _dialog("Reset staff password", self)
        layout.addWidget(heading("Reset password", f"Set a new password for {user['full_name']}. Share it privately with this staff member."))
        password = _field("At least 10 characters", True)
        confirm = _field("Repeat password", True)
        form = QFormLayout()
        form.addRow("New password", password)
        form.addRow("Confirm", confirm)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        def save():
            try:
                if password.text() != confirm.text():
                    raise ValueError("The two passwords do not match.")
                self.service.reset_password(user["id"], password.text())
                password.clear()
                confirm.clear()
                dialog.accept()
                success(self, "Password updated. Share the new password privately with the staff member.")
                self.refresh()
            except Exception as exc:
                show_error(dialog, exc)

        buttons.accepted.connect(save)
        dialog.exec()


class SettingsPage(BasePage):
    auth_required = Signal()

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(18)
        layout.addWidget(heading("Academy administration", "ADMINISTRATION  /  INSTITUTION DETAILS AND DATABASE RECORDS"))
        tabs = QTabWidget()
        tabs.addTab(self._academy_tab(), "Institution details")
        tabs.addTab(self._data_tab(), "Database backup && restore")
        tabs.addTab(self._history_tab(), "Activity register")
        layout.addWidget(tabs, 1)

    def _academy_tab(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        details, details_layout = _panel()
        details_layout.setSpacing(20)
        details_layout.addWidget(_section("Institution particulars", "Official details used on fee challans and payment receipts."))
        self.academy_name = _field("Academy name")
        self.academy_address = _field("Campus address")
        self.academy_phone = _field("Contact number")
        form = QFormLayout()
        form.setVerticalSpacing(14)
        form.setHorizontalSpacing(20)
        form.addRow("Academy name", self.academy_name)
        form.addRow("Address", self.academy_address)
        form.addRow("Phone", self.academy_phone)
        currency = QLabel("PKR · Pakistani rupees")
        form.addRow("Currency", currency)
        details_layout.addLayout(form)
        details_layout.addSpacing(4)
        row = QHBoxLayout()
        row.addWidget(_button("Save academy details", self._save_settings, True))
        row.addStretch()
        details_layout.addLayout(row)
        details_layout.addStretch()
        security, security_layout = _panel()
        security_layout.addWidget(_section("Owner account", "Account credentials and recovery access."))
        security_note = QLabel("Keep a password reset file on a separate drive. Select it from Reset password if you forget the owner password.")
        security_note.setObjectName("muted")
        security_note.setWordWrap(True)
        security_layout.addWidget(security_note)
        security_layout.addSpacing(8)
        security_layout.addWidget(_button("Change my password…", self._change_password))
        self.save_reset_file = _button("Save password reset file…", self._save_reset_file)
        security_layout.addWidget(self.save_reset_file)
        self.reset_file_status = QLabel("Saving a new reset file replaces the previous one.")
        self.reset_file_status.setObjectName("muted")
        self.reset_file_status.setWordWrap(True)
        security_layout.addWidget(self.reset_file_status)
        security_layout.addStretch()
        layout.addWidget(details, 2)
        layout.addWidget(security, 1)
        return page

    def _data_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        panels = QHBoxLayout()
        panels.setSpacing(20)
        backup, backup_layout = _panel()
        backup_layout.addWidget(_section("Database backup", "Save a copy of the academy's current records."))
        backup_note = QLabel("A backup includes staff accounts, student information and financial history. Store backup files privately. The database file is not encrypted; protect your computer and backup drive with operating-system encryption.")
        backup_note.setWordWrap(True)
        backup_note.setObjectName("muted")
        backup_layout.addWidget(backup_note)
        backup_layout.addSpacing(8)
        backup_layout.addWidget(_button("Create database backup…", self._backup, True), 0, Qt.AlignmentFlag.AlignLeft)
        self.backup_status = QLabel("No backup created during this session.")
        self.backup_status.setWordWrap(True)
        self.backup_status.setObjectName("muted")
        backup_layout.addWidget(self.backup_status)
        backup_layout.addStretch()
        restore, restore_layout = _panel()
        restore_layout.addWidget(_section("Database restoration", "Replace current records with a verified academy backup."))
        restore_note = QLabel("Restoration replaces student, staff and financial records with the selected backup, then signs you out. A safety copy of the current database is saved first.")
        restore_note.setObjectName("muted")
        restore_note.setWordWrap(True)
        restore_layout.addWidget(restore_note)
        restore_layout.addSpacing(8)
        restore_layout.addWidget(_button("Restore database…", self._restore, danger=True), 0, Qt.AlignmentFlag.AlignLeft)
        restore_layout.addStretch()
        panels.addWidget(backup, 1)
        panels.addWidget(restore, 1)
        layout.addLayout(panels, 1)
        location, location_layout = _panel()
        self.data_location = QLabel("")
        self.data_location.setWordWrap(True)
        self.data_location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.data_location.setObjectName("muted")
        location_layout.addWidget(self.data_location)
        layout.addWidget(location)
        return page

    def _history_tab(self):
        page = QFrame()
        page.setObjectName("card")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        bar = QHBoxLayout()
        bar.addWidget(_section("Administrative activity register", "Recent account, admission and financial entries."))
        bar.addStretch()
        bar.addWidget(_button("Refresh history", self._refresh_audit))
        layout.addLayout(bar)
        self.audit_table = table(["DATE & TIME (UTC)", "STAFF MEMBER", "ACTION", "DETAILS"])
        audit_header = self.audit_table.horizontalHeader()
        for column, width in ((0, 205), (1, 150), (2, 180)):
            audit_header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            self.audit_table.setColumnWidth(column, width)
        audit_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.audit_table, 1)
        return page

    def refresh(self):
        try:
            settings = self.service.get_settings()
            self.academy_name.setText(settings.get("academy_name", ""))
            self.academy_address.setText(settings.get("address", ""))
            self.academy_phone.setText(settings.get("phone", ""))
            self.data_location.setText(f"Database location\n{getattr(self.service, 'db_path', 'Stored in your local application data folder')}")
            self._refresh_audit()
        except Exception as exc:
            show_error(self, exc)

    def _refresh_audit(self):
        try:
            history = self.service.list_audit(200)
            fill_table(self.audit_table, [[entry["created_at"], entry["actor"], entry["action"].replace("_", " ").title(), entry["details"]] for entry in history])
        except Exception as exc:
            show_error(self, exc)

    def _save_settings(self):
        try:
            self.service.update_settings(self.academy_name.text().strip(), self.academy_address.text().strip(), self.academy_phone.text().strip())
            self.changed.emit()
            self._refresh_audit()
            success(self, "Academy details saved. New challans and receipts will use these details.")
        except Exception as exc:
            show_error(self, exc)

    def _change_password(self):
        dialog, layout = _dialog("Change your password", self)
        layout.addWidget(heading("Change my password", "Choose a private password with at least 10 characters."))
        current = _field("Current password", True)
        new = _field("New password", True)
        confirm = _field("Repeat new password", True)
        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow("Current", current)
        form.addRow("New password", new)
        form.addRow("Confirm", confirm)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        def save():
            try:
                if new.text() != confirm.text():
                    raise ValueError("The two passwords do not match.")
                self.service.change_password(current.text(), new.text())
                current.clear()
                new.clear()
                confirm.clear()
                dialog.accept()
                self._refresh_audit()
                success(self, "Your password has been changed.")
            except Exception as exc:
                show_error(dialog, exc)

        buttons.accepted.connect(save)
        dialog.exec()

    def _save_reset_file(self):
        dialog, layout = _dialog("Save password reset file", self)
        layout.addWidget(heading(
            "Save password reset file",
            "Confirm your current password, then choose where to save the file. Keep it on a separate drive. A new file replaces the previous reset file.",
        ))
        password = _field("Current owner password", True)
        password.setObjectName("currentPassword")
        form = QFormLayout()
        form.addRow("Current password", password)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Choose save location…")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primary")
        buttons.button(QDialogButtonBox.StandardButton.Save).setDefault(True)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        def save():
            if not password.text():
                show_error(dialog, ValueError("Enter your current owner password."))
                password.setFocus()
                return
            destination, _ = QFileDialog.getSaveFileName(
                dialog, "Save password reset file", "academy-password-reset.nexus-key",
                "Academy password reset file (*.nexus-key)",
            )
            if not destination:
                return
            if not destination.lower().endswith(".nexus-key"):
                destination += ".nexus-key"
            try:
                path = self.service.save_recovery_file(destination, current_password=password.text())
                password.clear()
                self.reset_file_status.setText(f"Password reset file saved: {path}")
                self._refresh_audit()
                dialog.accept()
                success(self, "Password reset file saved. Keep it on a separate drive. Any older reset file has been replaced.")
            except Exception as exc:
                password.clear()
                show_error(dialog, exc)
                password.setFocus()

        buttons.accepted.connect(save)
        dialog.finished.connect(lambda *_: password.clear())
        dialog.exec()

    def _backup(self):
        destination, _ = QFileDialog.getSaveFileName(self, "Create academy backup", f"nexus-backup-{datetime.now():%Y-%m-%d-%H%M}.sqlite3", "SQLite backup (*.sqlite3)")
        if not destination:
            return
        try:
            path = self.service.backup(destination)
            self.backup_status.setText(f"Backup saved: {path}")
            self._refresh_audit()
            success(self, "Database backup created. Keep it on a separate drive for protection against computer failure.")
        except Exception as exc:
            show_error(self, exc)

    def _restore(self):
        source, _ = QFileDialog.getOpenFileName(self, "Choose academy backup", "", "SQLite backup (*.sqlite3 *.db);;All files (*)")
        if not source:
            return
        answer = QMessageBox.warning(self, "Replace current academy data?", f"Restore academy data from:\n{source}\n\nThis replaces the current students, accounts and payments with the backup contents. Changes made after that backup will no longer be in the active database. A safety copy will be saved first.\n\nYou will be signed out and must sign in with an account from the restored backup.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.restore(source)
            self.auth_required.emit()
        except Exception as exc:
            show_error(self, exc)
            if self.service.user is None:
                self.auth_required.emit()
