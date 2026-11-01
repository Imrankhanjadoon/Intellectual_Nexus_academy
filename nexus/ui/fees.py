"""Challans, collections and printable records with role-aware actions."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QDate, QStandardPaths, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from nexus.exports import export_challan, export_receipt
from nexus.ui.common import BasePage, fill_table, heading, money, selected_id, show_error, success, table


def _amount(value=0):
    field = QDoubleSpinBox()
    field.setRange(0, 10_000_000)
    field.setDecimals(2)
    field.setSingleStep(500)
    field.setPrefix("Rs ")
    field.setGroupSeparatorShown(True)
    field.setValue(float(value or 0))
    return field


def _note(text):
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName("muted")
    return label


def _field_group(title, fields, columns=2):
    group = QGroupBox(title)
    grid = QGridLayout(group)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(18)
    grid.setVerticalSpacing(14)
    for column in range(columns):
        grid.setColumnStretch(column, 1)
    for index, (caption, field) in enumerate(fields):
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = QLabel(caption)
        label.setObjectName("fieldLabel")
        label.setBuddy(field)
        layout.addWidget(label)
        layout.addWidget(field)
        grid.addWidget(box, index // columns, index % columns)
    return group


def _pdf_path(parent, title, filename):
    folder = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or str(Path.home())
    path, _ = QFileDialog.getSaveFileName(parent, title, str(Path(folder) / filename), "PDF document (*.pdf)")
    if path and not path.lower().endswith(".pdf"):
        path += ".pdf"
    return path


def _tint_status(widget, rows, column):
    colors = {"Paid": "#245a42", "Partially paid": "#81672f", "Unpaid": "#8a3b32", "Reversed": "#81672f", "Received": "#245a42"}
    for row, values in enumerate(rows):
        item = widget.item(row, column)
        if item:
            item.setForeground(QColor(colors.get(str(values[column]), "#29394c")))
            item.setTextAlignment(Qt.AlignCenter)
            font = item.font()
            font.setWeight(QFont.Weight.DemiBold)
            item.setFont(font)


def _ledger_columns(widget, flexible, amounts=()):
    header = widget.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeToContents)
    for column in flexible:
        header.setSectionResizeMode(column, QHeaderView.Stretch)
    widget.set_flexible_columns(flexible)
    for column in amounts:
        widget.horizontalHeaderItem(column).setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        for row in range(widget.rowCount()):
            widget.item(row, column).setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)


class ChallanDialog(QDialog):
    def __init__(self, service, students, parent=None):
        super().__init__(parent)
        self.service = service
        self.students = students
        self.result_record = None
        self.setWindowTitle("Create fee challan")
        self.setMinimumWidth(650)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(18)
        outer.addWidget(heading("Fee challan preparation", "Student account, billing month and fee assessment."))
        self.student = QComboBox()
        self.student.setMinimumContentsLength(28)
        for student in students:
            self.student.addItem(f"{student['full_name']} · {student['student_number']}", student["id"])
        self.period = QDateEdit(QDate.currentDate())
        self.period.setCalendarPopup(True)
        self.period.setDisplayFormat("MMMM yyyy")
        self.tuition = _amount(students[0]["monthly_fee"] if students else 0)
        self.other = _amount()
        self.discount = _amount()
        self.due = QDateEdit(QDate.currentDate().addDays(7))
        self.due.setCalendarPopup(True)
        self.due.setDisplayFormat("dd MMM yyyy")
        self.total = QLabel()
        self.total.setObjectName("sectionTitle")
        outer.addWidget(_field_group("01  Student account", [("Student *", self.student)], columns=1))
        outer.addWidget(_field_group("02  Billing details", [("Fee month", self.period), ("Due date", self.due)]))
        outer.addWidget(_field_group("03  Fee assessment", [("Tuition", self.tuition), ("Other charges", self.other), ("Discount", self.discount)], columns=3))
        assessment = QFrame()
        assessment.setObjectName("card")
        assessment_layout = QHBoxLayout(assessment)
        assessment_layout.setContentsMargins(16, 12, 16, 12)
        assessment_layout.addWidget(QLabel("Challan total"), 1)
        self.total.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        assessment_layout.addWidget(self.total)
        outer.addWidget(assessment)
        outer.addWidget(_note("One challan is permitted per student per month. The admission challan covers the month of admission."))
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText("Create challan")
        self.buttons.button(QDialogButtonBox.Save).setObjectName("primary")
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)
        self.student.currentIndexChanged.connect(self._student_changed)
        for field in (self.tuition, self.other, self.discount):
            field.valueChanged.connect(self._update_total)
        self._update_total()

    def _student_changed(self, index):
        if 0 <= index < len(self.students):
            self.tuition.setValue(float(self.students[index]["monthly_fee"]))

    def _update_total(self):
        self.total.setText(money(self.tuition.value() + self.other.value() - self.discount.value()))

    def _save(self):
        try:
            if self.student.currentData() is None:
                raise ValueError("Choose a student first.")
            if self.discount.value() > self.tuition.value() + self.other.value():
                raise ValueError("The discount cannot exceed the charges.")
            self.buttons.button(QDialogButtonBox.Save).setEnabled(False)
            self.result_record = self.service.create_challan(
                student_id=self.student.currentData(),
                period=self.period.date().toString("yyyy-MM"),
                tuition=str(self.tuition.value()),
                discount=str(self.discount.value()),
                due_date=self.due.date().toString(Qt.ISODate),
                other=str(self.other.value()),
            )
            self.accept()
        except Exception as exc:
            self.buttons.button(QDialogButtonBox.Save).setEnabled(True)
            show_error(self, exc)


class PaymentDialog(QDialog):
    def __init__(self, service, challan, parent=None):
        super().__init__(parent)
        self.service = service
        self.challan = challan
        self.payment = None
        self.request_key = str(uuid4())
        self.setWindowTitle("Receive payment")
        self.setMinimumWidth(510)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(18)
        outer.addWidget(heading("Payment entry", f"Student: {challan['student_name']}  |  Challan: {challan['number']}"))
        summary = QFrame()
        summary.setObjectName("card")
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(18, 16, 18, 16)
        summary_layout.addWidget(_note("Outstanding balance"), 1)
        balance = QLabel(money(challan["balance"]))
        balance.setObjectName("sectionTitle")
        summary_layout.addWidget(balance)
        outer.addWidget(summary)
        self.amount = _amount(challan["balance"])
        self.amount.setMaximum(float(challan["balance"]))
        self.method = QComboBox()
        self.method.addItems(["Cash", "Bank transfer", "Card", "Other"])
        self.reference = QLineEdit()
        self.reference.setPlaceholderText("Transaction reference or note (optional)")
        self.reference.setMaxLength(200)
        outer.addWidget(_field_group("Payment particulars", [("Amount received *", self.amount), ("Payment method", self.method)]))
        reference_box = QVBoxLayout()
        reference_box.setSpacing(6)
        reference_label = QLabel("Transaction reference / remarks")
        reference_label.setObjectName("fieldLabel")
        reference_label.setBuddy(self.reference)
        reference_box.addWidget(reference_label)
        reference_box.addWidget(self.reference)
        outer.addLayout(reference_box)
        outer.addWidget(_note("Confirm receipt or verification of funds before posting this entry. The account balance and challan status will be updated."))
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText("Confirm payment")
        self.buttons.button(QDialogButtonBox.Save).setObjectName("primary")
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)

    def _save(self):
        try:
            if self.amount.value() <= 0:
                raise ValueError("Enter a payment amount greater than zero.")
            self.buttons.button(QDialogButtonBox.Save).setEnabled(False)
            self.payment = self.service.record_payment(
                challan_id=self.challan["id"],
                amount=str(self.amount.value()),
                method=self.method.currentText(),
                reference=self.reference.text().strip(),
                idempotency_key=self.request_key,
            )
            self.accept()
        except Exception as exc:
            self.buttons.button(QDialogButtonBox.Save).setEnabled(True)
            show_error(self, exc)


class FeesPage(BasePage):
    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        self.challans = []
        self.payments = []
        role = service.user["role"] if service.user else ""
        self.can_receive = role in ("admin", "cashier")
        self.can_reverse = role == "admin"
        outer = QVBoxLayout(self)
        outer.setContentsMargins(30, 28, 30, 28)
        outer.setSpacing(18)
        top = QHBoxLayout()
        top.addWidget(heading("Fee and collection register", "Monthly challans, payment entries and receipt records."), 1)
        self.new_challan = QPushButton("Prepare challan")
        self.new_challan.setObjectName("primary")
        self.new_challan.clicked.connect(self._create_challan)
        top.addWidget(self.new_challan)
        outer.addLayout(top)
        self.tabs = QTabWidget()
        challan_tab = QWidget()
        challan_host = QVBoxLayout(challan_tab)
        challan_host.setContentsMargins(0, 12, 0, 0)
        challan_panel = QFrame()
        challan_panel.setObjectName("card")
        challan_host.addWidget(challan_panel)
        challan_layout = QVBoxLayout(challan_panel)
        challan_layout.setContentsMargins(0, 0, 0, 0)
        challan_layout.setSpacing(0)
        filter_bar = QFrame()
        filter_bar.setObjectName("registerToolbar")
        filters = QHBoxLayout(filter_bar)
        filters.setContentsMargins(16, 14, 16, 14)
        filters.setSpacing(12)
        search_label = QLabel("Search register")
        search_label.setObjectName("fieldLabel")
        filters.addWidget(search_label)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Student name, challan number or registration number")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._load_challans)
        self.status = QComboBox()
        self.status.addItems(["All", "Unpaid", "Partially paid", "Paid", "Overdue"])
        self.status.setMinimumWidth(155)
        self.status.currentTextChanged.connect(self._load_challans)
        filters.addWidget(self.search, 1)
        status_label = QLabel("Status")
        status_label.setObjectName("fieldLabel")
        filters.addWidget(status_label)
        filters.addWidget(self.status)
        challan_layout.addWidget(filter_bar)
        self.summary = _note("")
        self.summary.setObjectName("registerSummary")
        self.summary.setContentsMargins(16, 10, 16, 10)
        challan_layout.addWidget(self.summary)
        self.challan_table = table(["CHALLAN NO.", "STUDENT NAME", "FEE MONTH", "DUE DATE", "TOTAL", "PAID", "BALANCE", "STATUS"])
        self.challan_table.setObjectName("registerTable")
        self.challan_table.cellDoubleClicked.connect(self._view_challan)
        self.challan_table.itemSelectionChanged.connect(self._selection_changed)
        challan_layout.addWidget(self.challan_table, 1)
        self.challan_empty = _note("No challans recorded. The initial challan is generated upon student admission.")
        self.challan_empty.setContentsMargins(16, 12, 16, 12)
        challan_layout.addWidget(self.challan_empty)
        action_bar = QFrame()
        action_bar.setObjectName("registerActions")
        actions = QHBoxLayout(action_bar)
        actions.setContentsMargins(16, 12, 16, 12)
        actions.setSpacing(10)
        view = QPushButton("View breakdown")
        view.clicked.connect(self._view_challan)
        export = QPushButton("Save challan PDF")
        export.clicked.connect(self._export_selected_challan)
        self.receive = QPushButton("Receive payment")
        self.receive.setObjectName("primary")
        self.receive.setVisible(self.can_receive)
        self.receive.clicked.connect(self._receive_selected)
        actions.addWidget(view)
        actions.addWidget(export)
        actions.addStretch()
        actions.addWidget(self.receive)
        challan_layout.addWidget(action_bar)
        self.tabs.addTab(challan_tab, "Challan register")
        payment_tab = QWidget()
        payment_host = QVBoxLayout(payment_tab)
        payment_host.setContentsMargins(0, 12, 0, 0)
        payment_panel = QFrame()
        payment_panel.setObjectName("card")
        payment_host.addWidget(payment_panel)
        payment_layout = QVBoxLayout(payment_panel)
        payment_layout.setContentsMargins(0, 0, 0, 0)
        payment_layout.setSpacing(0)
        payment_toolbar = QFrame()
        payment_toolbar.setObjectName("registerToolbar")
        payment_filters = QHBoxLayout(payment_toolbar)
        payment_filters.setContentsMargins(16, 14, 16, 14)
        payment_filters.setSpacing(12)
        payment_search_label = QLabel("Search receipts")
        payment_search_label.setObjectName("fieldLabel")
        payment_filters.addWidget(payment_search_label)
        self.payment_search = QLineEdit()
        self.payment_search.setPlaceholderText("Student name, receipt number or challan number")
        self.payment_search.setClearButtonEnabled(True)
        self.payment_search.textChanged.connect(self._load_payments)
        payment_filters.addWidget(self.payment_search, 1)
        payment_layout.addWidget(payment_toolbar)
        self.payment_table = table(["RECEIPT NO.", "STUDENT NAME", "CHALLAN NO.", "DATE", "AMOUNT", "METHOD", "RECEIVED BY", "STATUS"])
        self.payment_table.setObjectName("registerTable")
        self.payment_table.cellDoubleClicked.connect(self._view_payment)
        payment_layout.addWidget(self.payment_table, 1)
        self.payment_empty = _note("No payment entries recorded. A receipt is generated for each confirmed payment.")
        self.payment_empty.setContentsMargins(16, 12, 16, 12)
        payment_layout.addWidget(self.payment_empty)
        payment_action_bar = QFrame()
        payment_action_bar.setObjectName("registerActions")
        payment_actions = QHBoxLayout(payment_action_bar)
        payment_actions.setContentsMargins(16, 12, 16, 12)
        payment_actions.setSpacing(10)
        payment_details = QPushButton("View payment details")
        payment_details.clicked.connect(self._view_payment)
        payment_actions.addWidget(payment_details)
        self.reverse = QPushButton("Reverse payment")
        self.reverse.setObjectName("danger")
        self.reverse.setVisible(self.can_reverse)
        self.reverse.clicked.connect(self._reverse_payment)
        receipt = QPushButton("Save receipt PDF")
        receipt.clicked.connect(self._export_selected_receipt)
        payment_actions.addWidget(receipt)
        payment_actions.addStretch()
        payment_actions.addWidget(self.reverse)
        payment_layout.addWidget(payment_action_bar)
        self.tabs.addTab(payment_tab, "Collection register")
        outer.addWidget(self.tabs, 1)
        outer.addWidget(_note("Payment entries require authorised staff access. Use Save PDF to retain or print the official challan or receipt."))
        self.refresh()

    def refresh(self):
        self._load_challans()
        self._load_payments()

    def _load_challans(self, *_):
        try:
            self.challans = self.service.list_challans(self.search.text().strip(), self.status.currentText())
            rows = [[c["number"], c["student_name"], c["period"], c["due_date"], money(c["total"]), money(c["paid"]), money(c["balance"]), c["status"]] for c in self.challans]
            fill_table(self.challan_table, rows, [c["id"] for c in self.challans])
            _tint_status(self.challan_table, rows, 7)
            _ledger_columns(self.challan_table, (1,), (4, 5, 6))
            total_balance = sum((Decimal(str(c["balance"])) for c in self.challans), Decimal(0))
            self.summary.setText(f"Records: {len(self.challans):,}    |    Outstanding balance for displayed records: {money(total_balance)}")
            self.challan_empty.setVisible(not self.challans)
            filtered = bool(self.search.text().strip()) or self.status.currentText() != "All"
            self.challan_empty.setText("No challans match the specified search and status criteria." if filtered else "No challans recorded. The initial challan is generated upon student admission.")
            self._selection_changed()
        except Exception as exc:
            show_error(self, exc)

    def _load_payments(self, *_):
        try:
            self.payments = self.service.list_payments(self.payment_search.text().strip())
            rows = [[p["number"], p["student_name"], p["challan_number"], p["paid_on"][:10], money(p["amount"]), p["method"], p["received_by"], "Reversed" if p["reversed"] else "Received"] for p in self.payments]
            fill_table(self.payment_table, rows, [p["id"] for p in self.payments])
            _tint_status(self.payment_table, rows, 7)
            _ledger_columns(self.payment_table, (1, 6), (4,))
            for row, payment in enumerate(self.payments):
                self.payment_table.item(row, 3).setToolTip(payment["paid_on"])
            self.payment_empty.setVisible(not self.payments)
            self.payment_empty.setText("No receipts match the specified search criteria." if self.payment_search.text().strip() else "No payment entries recorded. A receipt is generated for each confirmed payment.")
        except Exception as exc:
            show_error(self, exc)

    def _selection_changed(self):
        challan_id = selected_id(self.challan_table)
        challan = next((c for c in self.challans if c["id"] == challan_id), None)
        self.receive.setEnabled(bool(challan and Decimal(str(challan["balance"])) > 0))

    def _selected_challan(self):
        challan_id = selected_id(self.challan_table)
        if challan_id is None:
            raise ValueError("Select a challan from the list first.")
        return self.service.challan_details(challan_id)

    def _create_challan(self):
        try:
            students = [s for s in self.service.list_students() if str(s.get("status", "active")).lower() == "active"]
            if not students:
                raise ValueError("Admit a student first. Their initial challan will be created automatically.")
            dialog = ChallanDialog(self.service, students, self)
            if dialog.exec() == QDialog.Accepted:
                self.refresh()
                self.changed.emit()
                success(self, f"Challan {dialog.result_record['number']} has been created. You can now save its PDF or receive a payment.")
        except Exception as exc:
            show_error(self, exc)

    def _receive_selected(self):
        try:
            self._receive_payment(self._selected_challan())
        except Exception as exc:
            show_error(self, exc)

    def _receive_payment(self, challan):
        if not self.can_receive:
            raise PermissionError("Only an administrator or cashier can receive payments.")
        if Decimal(str(challan["balance"])) <= 0:
            raise ValueError("This challan is already paid in full.")
        dialog = PaymentDialog(self.service, challan, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            self.changed.emit()
            payment = dialog.payment
            answer = QMessageBox.question(
                self,
                "Payment received",
                f"{money(payment['amount'])} recorded successfully.\nReceipt: {payment['number']}\n\nSave the receipt as a PDF now?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer == QMessageBox.Yes:
                self._export_receipt(payment)

    def _view_challan(self, *_):
        try:
            c = self._selected_challan()
            dialog = QDialog(self)
            dialog.setWindowTitle(f"Challan {c['number']}")
            dialog.resize(730, 620)
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(28, 28, 28, 28)
            layout.setSpacing(16)
            layout.addWidget(heading(c["student_name"], f"{c['number']}  ·  {c['student_number']}  ·  {c['period']}"))
            form = QFormLayout()
            form.setSpacing(10)
            values = [
                ("Class / batch", c.get("class_name") or "—"),
                ("Guardian / contact", f"{c.get('guardian_name', '')} · {c.get('phone', '')}"),
                ("Due date", c["due_date"]),
                ("Tuition", money(c.get("tuition", 0))),
                ("Other / admission charges", money(c.get("other", 0))),
                ("Discount", money(c.get("discount", 0))),
                ("Total", money(c["total"])),
                ("Received", money(c["paid"])),
                ("Balance", f"{money(c['balance'])} · {c['status']}"),
            ]
            for label, value in values:
                text = QLabel(str(value))
                text.setTextFormat(Qt.PlainText)
                text.setTextInteractionFlags(Qt.TextSelectableByMouse)
                form.addRow(label, text)
            layout.addLayout(form)
            layout.addWidget(_note("Payment entries against this challan"))
            trail = table(["RECEIPT", "DATE", "AMOUNT", "METHOD", "STATUS"])
            trail.setMinimumHeight(145)
            payments = c.get("payments", [])
            fill_table(trail, [[p["number"], p["paid_on"], money(p["amount"]), p["method"], "Reversed" if p.get("reversed") else "Received"] for p in payments])
            _ledger_columns(trail, (1,), (2,))
            layout.addWidget(trail, 1)
            if not payments:
                layout.addWidget(_note("No payments have been recorded for this challan."))
            actions = QHBoxLayout()
            export = QPushButton("Save challan PDF")
            export.clicked.connect(lambda: self._export_challan(c))
            actions.addWidget(export)
            actions.addStretch()
            if self.can_receive and Decimal(str(c["balance"])) > 0:
                receive = QPushButton("Receive payment")
                receive.setObjectName("primary")
                receive.clicked.connect(dialog.accept)
                actions.addWidget(receive)
            close = QPushButton("Close")
            close.clicked.connect(dialog.reject)
            actions.addWidget(close)
            layout.addLayout(actions)
            if dialog.exec() == QDialog.Accepted:
                self._receive_payment(c)
        except Exception as exc:
            show_error(self, exc)

    def _export_selected_challan(self):
        try:
            self._export_challan(self._selected_challan())
        except Exception as exc:
            show_error(self, exc)

    def _export_challan(self, challan):
        try:
            path = _pdf_path(self, "Save fee challan", f"{challan['number']}.pdf")
            if path:
                export_challan(self.service, challan["id"], path)
                success(self, f"Challan PDF saved to:\n{path}\n\nOpen the file in a PDF reader to print it.")
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception as exc:
            show_error(self, exc)

    def _export_selected_receipt(self):
        try:
            payment_id = selected_id(self.payment_table)
            if payment_id is None:
                raise ValueError("Select a payment from the history first.")
            payment = next((p for p in self.payments if p["id"] == payment_id), None)
            if payment is None:
                raise ValueError("The payment is no longer in this view. Refresh and select it again.")
            self._export_receipt(payment)
        except Exception as exc:
            show_error(self, exc)

    def _view_payment(self, *_):
        try:
            payment_id = selected_id(self.payment_table)
            if payment_id is None:
                raise ValueError("Select a payment from the history first.")
            payment = next((p for p in self.payments if p["id"] == payment_id), None)
            if payment is None:
                self.refresh()
                return
            dialog = QDialog(self)
            dialog.setWindowTitle("Payment details")
            dialog.setMinimumWidth(540)
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(28, 28, 28, 28)
            layout.setSpacing(18)
            layout.addWidget(heading(payment["number"], f"{payment['student_name']}  ·  {payment['challan_number']}"))
            form = QFormLayout()
            form.setSpacing(12)
            fields = [
                ("Amount", money(payment["amount"])),
                ("Received on", payment["paid_on"]),
                ("Payment method", payment["method"]),
                ("Received by", payment["received_by"]),
                ("Reference", payment.get("reference") or "—"),
                ("Status", "Reversed" if payment["reversed"] else "Received"),
            ]
            if payment["reversed"]:
                fields.extend([("Reversed on", payment.get("reversed_at") or "—"), ("Reason", payment.get("reversal_reason") or "—")])
            for name, value in fields:
                label = QLabel(str(value))
                label.setTextFormat(Qt.PlainText)
                label.setWordWrap(True)
                label.setTextInteractionFlags(Qt.TextSelectableByMouse)
                form.addRow(name, label)
            layout.addLayout(form)
            buttons = QHBoxLayout()
            export = QPushButton("Save receipt PDF")
            export.setObjectName("primary")
            export.clicked.connect(lambda: self._export_receipt(payment))
            buttons.addWidget(export)
            buttons.addStretch()
            close = QPushButton("Close")
            close.clicked.connect(dialog.reject)
            buttons.addWidget(close)
            layout.addLayout(buttons)
            dialog.exec()
        except Exception as exc:
            show_error(self, exc)

    def _export_receipt(self, payment):
        try:
            path = _pdf_path(self, "Save payment receipt", f"{payment['number']}.pdf")
            if path:
                export_receipt(self.service, payment["id"], path)
                success(self, f"Receipt PDF saved to:\n{path}\n\nOpen the file in a PDF reader to print it.")
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception as exc:
            show_error(self, exc)

    def _reverse_payment(self):
        try:
            payment_id = selected_id(self.payment_table)
            if payment_id is None:
                raise ValueError("Select a payment to reverse first.")
            payment = next((p for p in self.payments if p["id"] == payment_id), None)
            if payment is None:
                raise ValueError("Select a payment from the current view.")
            if payment["reversed"]:
                raise ValueError("This payment has already been reversed.")
            reason, accepted = QInputDialog.getMultiLineText(
                self,
                "Reverse payment",
                f"Reverse receipt {payment['number']} for {money(payment['amount'])}?\n\nThe challan balance will increase. The original receipt and your reason remain in the audit history. Enter a reason:",
            )
            if not accepted:
                return
            if not reason.strip():
                raise ValueError("A reason is required to reverse a payment.")
            self.service.reverse_payment(payment_id, reason.strip())
            self.refresh()
            self.changed.emit()
            success(self, "Payment reversed. The challan balance and collection reports have been updated.")
        except Exception as exc:
            show_error(self, exc)
