"""Keyboard-friendly, permission-scoped search over local academy records."""
from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout,
)

from .common import heading, money
from .identity import line_icon
from .motion import install_motion


SERVICES = [
    ("dashboard", "Overview", "Enrollment and collection summary"),
    ("students", "Admissions", "Student register and classes"),
    ("fees", "Fee ledger", "Challans and payment receipts"),
    ("attendance", "Attendance", "Assigned class registers"),
    ("reports", "Reports", "Collections and overdue fees"),
    ("users", "Staff access", "Staff accounts and approval"),
    ("settings", "Administration", "Settings, backup and account security"),
]


class GlobalSearchDialog(QDialog):
    navigate = Signal(str, str)

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self._closed = False
        self.setWindowTitle("Search academy records")
        self.resize(730, 610)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 22)
        layout.setSpacing(16)
        layout.addWidget(heading("Search academy records", "Find records and office services available to your account."))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Name, student ID, challan number or service…")
        self.search.setClearButtonEnabled(True)
        self.search.setMaxLength(200)
        self.search.setMinimumHeight(36)
        layout.addWidget(self.search)
        self.status = QLabel("Choose an office service, or enter at least two characters.")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.results = QListWidget()
        self.results.setSpacing(2)
        self.results.setStyleSheet(
            "QListWidget { background: white; border: 1px solid #dce5f1; border-radius: 4px; }"
            "QListWidget::item { padding: 10px 13px; border-bottom: 1px solid #edf1f7; }"
            "QListWidget::item:selected { background: #eaf1fc; color: #1c457d; }"
        )
        layout.addWidget(self.results, 1)
        footer = QHBoxLayout()
        hint = QLabel("Enter to open  ·  Esc to close")
        hint.setObjectName("muted")
        footer.addWidget(hint, 1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        footer.addWidget(close)
        self.open_button = QPushButton("Open record")
        self.open_button.setObjectName("primary")
        self.open_button.clicked.connect(self._activate_current)
        footer.addWidget(self.open_button)
        layout.addLayout(footer)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self._run_search)
        self.search.textChanged.connect(self._queue_search)
        self.search.returnPressed.connect(self._activate_current)
        self.search.installEventFilter(self)
        self.results.itemActivated.connect(self._open_item)
        self.results.currentItemChanged.connect(lambda *_: self.open_button.setEnabled(self.results.currentItem() is not None))
        self.finished.connect(self._finish)
        install_motion(self)
        self._run_search()
        self.search.setFocus()

    def _finish(self, *_):
        self._closed = True
        self._timer.stop()

    def hideEvent(self, event):
        self._finish()
        super().hideEvent(event)

    def eventFilter(self, watched, event):
        if watched is self.search and event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Down:
            if self.results.count():
                self.results.setFocus()
            return True
        return super().eventFilter(watched, event)

    def _queue_search(self, *_):
        if not self._closed:
            self.status.setText("Searching local records…")
            self._timer.start()

    def _add(self, page, query, title, detail):
        if self.results.count() >= 40:
            return
        item = QListWidgetItem(line_icon(page), title + "\n" + detail)
        item.setSizeHint(QSize(0, 62))
        item.setData(Qt.ItemDataRole.UserRole, (page, query))
        self.results.addItem(item)

    def _run_search(self):
        if self._closed:
            return
        self.results.clear()
        query = self.search.text().strip()
        tokens = query.casefold().split()
        try:
            if self.service.user is None:
                self.status.setText("Your session has ended. Sign in to search again.")
                self.open_button.setEnabled(False)
                return
            allowed = {page for page, _, _ in SERVICES if self.service.has_permission(page)}
            for page, name, detail in SERVICES:
                if page in allowed and (not tokens or all(token in (name + " " + detail).casefold() for token in tokens)):
                    self._add(page, "", name, "SERVICE  ·  " + detail)
            if len(query) >= 2:
                if "students" in allowed or "fees" in allowed:
                    for student in self.service.list_students(query)[:10]:
                        route = "students" if "students" in allowed else "fees"
                        self._add(route, student["student_number"], student["full_name"], "STUDENT  ·  " + student["student_number"] + "  ·  " + student["class_name"])
                if "fees" in allowed:
                    for bill in self.service.list_challans(query)[:10]:
                        self._add("fees", bill["number"], bill["number"] + "  ·  " + bill["student_name"], "CHALLAN  ·  " + bill["status"] + "  ·  Balance " + money(bill["balance"]))
                    for payment in self.service.list_payments(query)[:10]:
                        self._add("fees", payment["number"], payment["number"] + "  ·  " + payment["student_name"], "RECEIPT  ·  " + money(payment["amount"]) + ("  ·  Reversed" if payment["reversed"] else ""))
                for group in self.service.list_classes():
                    text = (group["name"] + " " + group.get("schedule", "")).casefold()
                    if all(token in text for token in tokens):
                        if "attendance" in allowed:
                            self._add("attendance", group["name"], group["name"], "CLASS  ·  " + group.get("schedule", ""))
                        elif "students" in allowed:
                            self._add("students", "class:" + group["name"], group["name"], "CLASS  ·  " + group.get("schedule", ""))
                if "users" in allowed:
                    matches = [u for u in self.service.list_users() if all(token in " ".join(str(u[k]) for k in ("full_name", "username", "role", "status")).casefold() for token in tokens)]
                    for user in matches[:10]:
                        self._add("users", user["username"], user["full_name"], "STAFF  ·  " + user["username"] + "  ·  " + user["role"])
            count = self.results.count()
            self.status.setText(f"{count} result(s). Select a record to open it." if count else "No matching records. Try a student ID, name or record number.")
            if len(query) < 2:
                self.status.setText("Choose an office service, or enter at least two characters to search records.")
            self.open_button.setEnabled(bool(count))
            if count:
                self.results.setCurrentRow(0)
        except (ValueError, PermissionError, RuntimeError) as exc:
            self.results.clear()
            self.open_button.setEnabled(False)
            self.status.setText(str(exc))

    def _activate_current(self):
        if self._timer.isActive():
            self._timer.stop()
            self._run_search()
        self._open_item(self.results.currentItem())

    def _open_item(self, item):
        if item is None or self._closed:
            return
        page, query = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
        self.navigate.emit(page, query)
