"""Admissions and teaching groups for the offline academy workspace."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from nexus.ui.common import (
    BasePage,
    fill_table,
    heading,
    money,
    selected_id,
    show_error,
    success,
    table,
)


def _amount(value=0):
    field = QDoubleSpinBox()
    field.setRange(0, 10_000_000)
    field.setDecimals(2)
    field.setSingleStep(500)
    field.setPrefix("Rs ")
    field.setGroupSeparatorShown(True)
    field.setValue(float(value or 0))
    return field


def _date(value=None):
    field = QDateEdit(value or QDate.currentDate())
    field.setCalendarPopup(True)
    field.setDisplayFormat("dd MMM yyyy")
    return field


def _note(text):
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName("muted")
    return label


def _field_group(title, fields):
    group = QGroupBox(title)
    grid = QGridLayout(group)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(18)
    grid.setVerticalSpacing(14)
    grid.setColumnStretch(0, 1)
    grid.setColumnStretch(1, 1)
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
        grid.addWidget(box, index // 2, index % 2)
    return group


def _register_columns(widget, flexible, amounts=()):
    """Keep identifiers and amounts readable while names use remaining space."""
    header = widget.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeToContents)
    for column in flexible:
        header.setSectionResizeMode(column, QHeaderView.Stretch)
    widget.set_flexible_columns(flexible)
    for column in amounts:
        widget.horizontalHeaderItem(column).setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        for row in range(widget.rowCount()):
            widget.item(row, column).setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)


def _restore_table_view(widget, record_id, vertical, horizontal):
    row = next((index for index in range(widget.rowCount()) if widget.item(index, 0).data(Qt.UserRole) == record_id), None) if record_id is not None else None
    if row is None:
        widget.clearSelection()
        widget.setCurrentCell(-1, -1)
    else:
        widget.selectRow(row)
    widget.verticalScrollBar().setValue(vertical)
    widget.horizontalScrollBar().setValue(horizontal)


class ClassDialog(QDialog):
    def __init__(self, service, parent=None, group=None):
        super().__init__(parent)
        self.service = service
        self.group = group
        self.setWindowTitle("Edit class or batch" if group else "Create a class or batch")
        self.setMinimumWidth(480)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(18)
        outer.addWidget(heading("Class amendment" if group else "Class registration", "Class particulars, teaching assignment and standard tuition fee."))
        form = QFormLayout()
        form.setSpacing(14)
        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. Grade 10 - Evening")
        self.name.setMaxLength(100)
        self.schedule = QLineEdit()
        self.schedule.setPlaceholderText("e.g. Mon–Fri, 4:00–6:00 PM")
        self.schedule.setMaxLength(200)
        self.fee = _amount()
        self.teacher = QComboBox()
        self.teacher.addItem("Not assigned", None)
        for teacher in service.list_teachers():
            self.teacher.addItem(teacher["full_name"], teacher["id"])
        if group:
            self.name.setText(group["name"])
            self.schedule.setText(group.get("schedule") or "")
            self.fee.setValue(float(group["monthly_fee"]))
            teacher_index = self.teacher.findData(group.get("teacher_id"))
            if teacher_index >= 0:
                self.teacher.setCurrentIndex(teacher_index)
        form.addRow("Class / batch name *", self.name)
        form.addRow("Schedule", self.schedule)
        form.addRow("Monthly tuition", self.fee)
        form.addRow("Teacher", self.teacher)
        outer.addLayout(form)
        outer.addWidget(_note("Only active, approved teachers may be assigned. Revised tuition applies to new admissions; existing student fees and issued challans are unaffected."))
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons = buttons
        buttons.button(QDialogButtonBox.Save).setText("Save changes" if group else "Create class")
        buttons.button(QDialogButtonBox.Save).setObjectName("primary")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        self.name.setFocus()

    def _save(self):
        if self.result() == QDialog.Accepted:
            return
        try:
            if not self.name.text().strip():
                raise ValueError("Enter a class or batch name.")
            values = dict(name=self.name.text().strip(), schedule=self.schedule.text().strip(), monthly_fee=str(self.fee.value()), teacher_id=self.teacher.currentData())
            self.buttons.button(QDialogButtonBox.Save).setEnabled(False)
            if self.group:
                self.service.update_class(self.group["id"], **values)
            else:
                self.service.add_class(**values)
            self.accept()
        except Exception as exc:
            self.buttons.button(QDialogButtonBox.Save).setEnabled(True)
            show_error(self, exc)


class AdmissionDialog(QDialog):
    def __init__(self, service, classes, parent=None):
        super().__init__(parent)
        self.service = service
        self.classes = classes
        self.result_record = None
        self.setWindowTitle("New student admission")
        self.resize(750, 760)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 26, 26, 22)
        outer.setSpacing(16)
        outer.addWidget(heading("Student admission form", "Registration particulars and initial fee assessment. Required fields are marked *."))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        form = QVBoxLayout(content)
        form.setContentsMargins(0, 0, 12, 0)
        form.setSpacing(10)
        self.name = QLineEdit()
        self.name.setMaxLength(150)
        self.name.setPlaceholderText("Student’s full name")
        self.guardian = QLineEdit()
        self.guardian.setMaxLength(150)
        self.guardian.setPlaceholderText("Parent or guardian’s full name")
        self.phone = QLineEdit()
        self.phone.setMaxLength(40)
        self.phone.setPlaceholderText("e.g. 03XX XXXXXXX")
        self.class_picker = QComboBox()
        for group in classes:
            self.class_picker.addItem(group["name"], group["id"])
        self.admitted_on = _date()
        self.monthly_fee = _amount(classes[0]["monthly_fee"] if classes else 0)
        self.admission_fee = _amount()
        self.discount = _amount()
        self.due_date = _date(QDate.currentDate().addDays(7))
        self.address = QTextEdit()
        self.address.setPlaceholderText("Home address (optional)")
        self.address.setMaximumHeight(76)
        self.notes = QTextEdit()
        self.notes.setPlaceholderText("Administrative remarks (optional)")
        self.notes.setMaximumHeight(76)
        self.total_label = QLabel()
        self.total_label.setObjectName("sectionTitle")
        form.addWidget(_field_group("01  Student particulars", [
            ("Student name *", self.name), ("Guardian name *", self.guardian),
            ("Contact number *", self.phone), ("Class / batch *", self.class_picker),
            ("Admission date", self.admitted_on),
        ]))
        fee_group = _field_group("02  Initial fee assessment", [
            ("Monthly tuition", self.monthly_fee), ("Admission fee", self.admission_fee),
            ("Initial discount", self.discount), ("Payment due date", self.due_date),
        ])
        self.fee_exempt = QCheckBox("Fee-exempt / no charges")
        self.fee_exempt.setToolTip("Select only when the assessed fee is intentionally zero. No payment or receipt will be recorded.")
        fee_group.layout().addWidget(self.fee_exempt, 2, 0, 1, 2)
        form.addWidget(fee_group)
        form.addWidget(_field_group("03  Additional information", [
            ("Residential address", self.address), ("Administrative remarks", self.notes),
        ]))
        scroll.setWidget(content)
        content.setAutoFillBackground(False)
        outer.addWidget(scroll, 1)
        assessment = QFrame()
        assessment.setObjectName("card")
        assessment_layout = QHBoxLayout(assessment)
        assessment_layout.setContentsMargins(14, 10, 14, 10)
        assessment_layout.addWidget(QLabel("Initial challan total"), 1)
        self.total_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        assessment_layout.addWidget(self.total_label)
        outer.addWidget(assessment)
        self.status_hint = _note("")
        outer.addWidget(self.status_hint)
        outer.addWidget(_note("The initial challan covers the month of admission. Any discount entered here applies only to this challan."))
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText("Confirm admission")
        self.buttons.button(QDialogButtonBox.Save).setObjectName("primary")
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)
        self.class_picker.currentIndexChanged.connect(self._class_changed)
        for field in (self.monthly_fee, self.admission_fee, self.discount):
            field.valueChanged.connect(self._update_total)
        self.fee_exempt.toggled.connect(self._update_total)
        self._update_total()

    def _class_changed(self, index):
        if 0 <= index < len(self.classes):
            self.monthly_fee.setValue(float(self.classes[index]["monthly_fee"]))

    def _update_total(self):
        value = self._net_total()
        self.total_label.setText(money(value))
        self.fee_exempt.setEnabled(value == 0)
        if value > 0:
            self.fee_exempt.setChecked(False)
            self.status_hint.setText("Unpaid — payment will be recorded separately.")
        elif value == 0 and self.fee_exempt.isChecked():
            self.status_hint.setText("No payment due — the student is fee-exempt; no payment is being recorded.")
        elif value == 0:
            self.status_hint.setText("Enter the fee amount, or select Fee-exempt / no charges to confirm an intentional zero-fee admission.")
        else:
            self.status_hint.setText("The discount cannot exceed the assessed charges.")

    def _net_total(self):
        return Decimal(str(self.monthly_fee.value())) + Decimal(str(self.admission_fee.value())) - Decimal(str(self.discount.value()))

    def _save(self):
        if self.result() == QDialog.Accepted:
            return
        try:
            if not all((self.name.text().strip(), self.guardian.text().strip(), self.phone.text().strip())):
                raise ValueError("Student name, guardian name and contact number are required.")
            if self.class_picker.currentData() is None:
                raise ValueError("Choose a class before saving the admission.")
            if self._net_total() < 0:
                raise ValueError("The discount cannot exceed the tuition and admission fee.")
            if self._net_total() == 0 and not self.fee_exempt.isChecked():
                raise ValueError("The initial challan has no charges. Enter the tuition/admission fee, or explicitly select Fee-exempt / no charges. A zero-fee admission does not record a payment.")
            self.buttons.button(QDialogButtonBox.Save).setEnabled(False)
            self.result_record = self.service.admit_student(
                full_name=self.name.text().strip(),
                guardian_name=self.guardian.text().strip(),
                phone=self.phone.text().strip(),
                class_id=self.class_picker.currentData(),
                admission_date=self.admitted_on.date().toString(Qt.ISODate),
                monthly_fee=str(self.monthly_fee.value()),
                admission_fee=str(self.admission_fee.value()),
                discount=str(self.discount.value()),
                due_date=self.due_date.date().toString(Qt.ISODate),
                address=self.address.toPlainText().strip(),
                notes=self.notes.toPlainText().strip(),
                fee_exempt=self.fee_exempt.isChecked(),
            )
            self.accept()
        except Exception as exc:
            self.buttons.button(QDialogButtonBox.Save).setEnabled(True)
            show_error(self, exc)


class EditStudentDialog(QDialog):
    """Correct a profile without creating another admission or fee record."""

    def __init__(self, service, student, classes, parent=None):
        super().__init__(parent)
        self.service = service
        self.student = student
        self.fee_changed = False
        self.setWindowTitle("Edit student profile")
        self.resize(700, 690)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 26, 26, 22)
        outer.setSpacing(16)
        outer.addWidget(heading("Student record amendment", f"Registration no. {student['student_number']}  |  Admission date: {student['admission_date']}"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        form = QVBoxLayout(content)
        form.setContentsMargins(0, 0, 12, 0)
        form.setSpacing(10)
        self.name = QLineEdit(student["full_name"])
        self.name.setMaxLength(150)
        self.guardian = QLineEdit(student["guardian_name"])
        self.guardian.setMaxLength(150)
        self.phone = QLineEdit(student["phone"])
        self.phone.setMaxLength(40)
        self.class_picker = QComboBox()
        for group in classes:
            self.class_picker.addItem(group["name"], group["id"])
        self.class_picker.setCurrentIndex(self.class_picker.findData(student["class_id"]))
        self.monthly_fee = _amount(student["monthly_fee"])
        self.status = QComboBox()
        self.status.addItem("Active", "active")
        self.status.addItem("Inactive", "inactive")
        self.status.setCurrentIndex(self.status.findData(student.get("status", "active")))
        self.address = QTextEdit()
        self.address.setPlainText(student.get("address") or "")
        self.address.setMaximumHeight(86)
        self.notes = QTextEdit()
        self.notes.setPlainText(student.get("notes") or "")
        self.notes.setMaximumHeight(86)
        form.addWidget(_field_group("01  Student particulars", [
            ("Student name *", self.name), ("Guardian name *", self.guardian),
            ("Contact number *", self.phone), ("Enrolment status", self.status),
        ]))
        form.addWidget(_field_group("02  Class and fee", [
            ("Class / batch *", self.class_picker), ("Monthly fee default", self.monthly_fee),
        ]))
        form.addWidget(_field_group("03  Additional information", [
            ("Residential address", self.address), ("Administrative remarks", self.notes),
        ]))
        scroll.setWidget(content)
        content.setAutoFillBackground(False)
        outer.addWidget(scroll, 1)
        outer.addWidget(_note("This monthly fee is the default for future challans. To correct an existing bill, select it in Fees & collections and choose Amend challan. Bills with any payment history cannot be amended. Inactive students retain their records but cannot receive new challans."))
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText("Save profile")
        self.buttons.button(QDialogButtonBox.Save).setObjectName("primary")
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)

    def _save(self):
        if self.result() == QDialog.Accepted:
            return
        try:
            if not all((self.name.text().strip(), self.guardian.text().strip(), self.phone.text().strip())):
                raise ValueError("Student name, guardian name and contact number are required.")
            if self.class_picker.currentData() is None:
                raise ValueError("Choose a class before saving the profile.")
            self.buttons.button(QDialogButtonBox.Save).setEnabled(False)
            self.service.update_student(
                student_id=self.student["id"],
                full_name=self.name.text().strip(),
                guardian_name=self.guardian.text().strip(),
                phone=self.phone.text().strip(),
                class_id=self.class_picker.currentData(),
                monthly_fee=str(self.monthly_fee.value()),
                address=self.address.toPlainText().strip(),
                notes=self.notes.toPlainText().strip(),
                status=self.status.currentData(),
            )
            self.fee_changed = Decimal(str(self.monthly_fee.value())) != Decimal(str(self.student["monthly_fee"]))
            self.accept()
        except Exception as exc:
            self.buttons.button(QDialogButtonBox.Save).setEnabled(True)
            show_error(self, exc)


class StudentsPage(BasePage):
    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        self.students = []
        self.classes = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(30, 28, 30, 28)
        outer.setSpacing(20)
        top = QHBoxLayout()
        top.addWidget(heading("Student register", "Admissions, enrolment records and class administration."), 1)
        self.admit_button = QPushButton("New admission")
        self.admit_button.setObjectName("primary")
        self.admit_button.clicked.connect(self._admit)
        top.addWidget(self.admit_button)
        outer.addLayout(top)
        self.tabs = QTabWidget()
        student_tab = QWidget()
        student_host = QVBoxLayout(student_tab)
        student_host.setContentsMargins(0, 12, 0, 0)
        student_panel = QFrame()
        student_panel.setObjectName("card")
        student_host.addWidget(student_panel)
        student_layout = QVBoxLayout(student_panel)
        student_layout.setContentsMargins(0, 0, 0, 0)
        student_layout.setSpacing(0)
        search_toolbar = QFrame()
        search_toolbar.setObjectName("registerToolbar")
        search_row = QHBoxLayout(search_toolbar)
        search_row.setContentsMargins(16, 14, 16, 14)
        search_row.setSpacing(12)
        search_label = QLabel("Search register")
        search_label.setObjectName("fieldLabel")
        search_row.addWidget(search_label)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Student name, registration number or contact number")
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip("Search the student register. Press Ctrl+F to focus this field; use the clear button to reset the search.")
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(self._load_students)
        self.search.textChanged.connect(lambda *_: self._search_timer.start())
        search_row.addWidget(self.search, 1)
        self.count = QLabel()
        self.count.setObjectName("countBadge")
        search_row.addWidget(self.count)
        student_layout.addWidget(search_toolbar)
        self.students_table = table(["REG. NO.", "STUDENT NAME", "CLASS / BATCH", "GUARDIAN", "CONTACT", "MONTHLY FEE", "STATUS"])
        self.students_table.setObjectName("registerTable")
        self.students_table.cellDoubleClicked.connect(self._student_details)
        student_layout.addWidget(self.students_table, 1)
        self.empty = _note("No admission records. Register a class before entering a new admission.")
        self.empty.setContentsMargins(16, 12, 16, 12)
        student_layout.addWidget(self.empty)
        action_bar = QFrame()
        action_bar.setObjectName("registerActions")
        bottom = QHBoxLayout(action_bar)
        bottom.setContentsMargins(16, 12, 16, 12)
        bottom.setSpacing(10)
        details = QPushButton("View profile")
        details.clicked.connect(self._student_details)
        self.edit_student_button = QPushButton("Edit student")
        self.edit_student_button.clicked.connect(self._edit_student)
        bottom.addWidget(details)
        bottom.addWidget(self.edit_student_button)
        bottom.addStretch()
        bottom.addWidget(_note("Select a row to view or amend the record."))
        student_layout.addWidget(action_bar)
        self.tabs.addTab(student_tab, "Admission register")
        class_tab = QWidget()
        class_host = QVBoxLayout(class_tab)
        class_host.setContentsMargins(0, 12, 0, 0)
        class_panel = QFrame()
        class_panel.setObjectName("card")
        class_host.addWidget(class_panel)
        class_layout = QVBoxLayout(class_panel)
        class_layout.setContentsMargins(0, 0, 0, 0)
        class_layout.setSpacing(0)
        class_toolbar = QFrame()
        class_toolbar.setObjectName("registerToolbar")
        class_top = QHBoxLayout(class_toolbar)
        class_top.setContentsMargins(16, 14, 16, 14)
        class_top.setSpacing(10)
        class_top.addWidget(_note("Class schedules, assigned teachers and standard tuition fees."), 1)
        self.class_button = QPushButton("Register class")
        self.class_button.setObjectName("primary")
        self.class_button.clicked.connect(self._add_class)
        self.edit_class_button = QPushButton("Edit selected class")
        self.edit_class_button.clicked.connect(self._edit_class)
        class_top.addWidget(self.edit_class_button)
        class_top.addWidget(self.class_button)
        class_layout.addWidget(class_toolbar)
        self.classes_table = table(["CLASS / BATCH", "SCHEDULE", "TEACHER", "MONTHLY TUITION"])
        self.classes_table.setObjectName("registerTable")
        self.classes_table.cellDoubleClicked.connect(self._edit_class)
        class_layout.addWidget(self.classes_table, 1)
        self.class_empty = _note("No classes registered. A class or batch is required for student admission.")
        self.class_empty.setContentsMargins(16, 12, 16, 12)
        class_layout.addWidget(self.class_empty)
        self.tabs.addTab(class_tab, "Classes && batches")
        outer.addWidget(self.tabs, 1)
        can_admit = service.user is not None and service.user["role"] in ("admin", "receptionist")
        self.admit_button.setVisible(can_admit)
        self.class_button.setVisible(can_admit)
        self.edit_class_button.setVisible(can_admit)
        self.edit_student_button.setVisible(can_admit)
        self.refresh()

    def refresh(self):
        try:
            class_id = selected_id(self.classes_table)
            vertical = self.classes_table.verticalScrollBar().value()
            horizontal = self.classes_table.horizontalScrollBar().value()
            self.classes = self.service.list_classes()
            fill_table(
                self.classes_table,
                [[group["name"], group.get("schedule") or "—", group.get("teacher_name") or "Unassigned", money(group["monthly_fee"])] for group in self.classes],
                [group["id"] for group in self.classes],
            )
            _register_columns(self.classes_table, (0, 1, 2), (3,))
            _restore_table_view(self.classes_table, class_id, vertical, horizontal)
            self.class_empty.setVisible(not self.classes)
            self._load_students()
        except Exception as exc:
            show_error(self, exc)

    def _load_students(self, *_):
        try:
            self._search_timer.stop()
            student_id = selected_id(self.students_table)
            vertical = self.students_table.verticalScrollBar().value()
            horizontal = self.students_table.horizontalScrollBar().value()
            self.students = self.service.list_students(self.search.text().strip())
            fill_table(
                self.students_table,
                [[s["student_number"], s["full_name"], s.get("class_name") or "—", s["guardian_name"], s["phone"], money(s["monthly_fee"]), str(s.get("status", "active")).title()] for s in self.students],
                [s["id"] for s in self.students],
            )
            _register_columns(self.students_table, (1, 2, 3), (5,))
            _restore_table_view(self.students_table, student_id, vertical, horizontal)
            self.count.setText(f"Records: {len(self.students):,}")
            self.empty.setVisible(not self.students)
            self.empty.setText("No records match the specified search criteria." if self.search.text().strip() else "No admission records. Register a class before entering a new admission.")
        except Exception as exc:
            show_error(self, exc)

    def focus_search(self):
        self.tabs.setCurrentIndex(0)
        self.search.setFocus()
        self.search.selectAll()

    def _add_class(self):
        try:
            dialog = ClassDialog(self.service, self)
            if dialog.exec() == QDialog.Accepted:
                self.refresh()
                self.changed.emit()
        except Exception as exc:
            show_error(self, exc)

    def _admit(self):
        try:
            self.classes = self.service.list_classes()
            if not self.classes:
                success(self, "Create a class or batch first so the student has a teaching group.")
                self.tabs.setCurrentIndex(1)
                self._add_class()
                return
            dialog = AdmissionDialog(self.service, self.classes, self)
            if dialog.exec() == QDialog.Accepted:
                self.refresh()
                self.changed.emit()
                result = dialog.result_record
                success(self, f"{result['student']['full_name']} is enrolled.\n\nStudent ID: {result['student']['student_number']}\nFirst challan: {result['challan']['number']}\nStatus: {result['challan']['status']}\n\nOpen Fees & collections to print the challan or record a payment.")
        except Exception as exc:
            show_error(self, exc)

    def _edit_class(self, *_):
        try:
            class_id = selected_id(self.classes_table)
            if class_id is None:
                raise ValueError("Select a class or batch first.")
            group = next((group for group in self.classes if group["id"] == class_id), None)
            if group is None:
                self.refresh()
                return
            dialog = ClassDialog(self.service, self, group=group)
            if dialog.exec() == QDialog.Accepted:
                self.refresh()
                self.changed.emit()
        except Exception as exc:
            show_error(self, exc)

    def _student_details(self, *_):
        try:
            student_id = selected_id(self.students_table)
            if student_id is None:
                raise ValueError("Select a student from the directory first.")
            student = next((s for s in self.students if s["id"] == student_id), None)
            if student is None:
                self.refresh()
                return
            dialog = QDialog(self)
            dialog.setWindowTitle("Student profile")
            dialog.setMinimumWidth(560)
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(28, 28, 28, 28)
            layout.setSpacing(20)
            layout.addWidget(heading(student["full_name"], f"{student['student_number']}  ·  {student.get('class_name') or 'No class'}"))
            form = QFormLayout()
            form.setSpacing(12)
            fields = [
                ("Guardian", student["guardian_name"]),
                ("Contact", student["phone"]),
                ("Admission date", student["admission_date"]),
                ("Monthly fee", money(student["monthly_fee"])),
                ("Status", str(student.get("status", "active")).title()),
                ("Address", student.get("address") or "—"),
                ("Notes", student.get("notes") or "—"),
            ]
            for label, value in fields:
                text = QLabel(str(value))
                text.setTextFormat(Qt.PlainText)
                text.setWordWrap(True)
                text.setTextInteractionFlags(Qt.TextSelectableByMouse)
                form.addRow(label, text)
            layout.addLayout(form)
            buttons = QDialogButtonBox(QDialogButtonBox.Close)
            if self.service.user and self.service.user["role"] in ("admin", "receptionist"):
                edit = buttons.addButton("Edit profile", QDialogButtonBox.ActionRole)
                edit.setObjectName("primary")
                edit.clicked.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if dialog.exec() == QDialog.Accepted:
                self._edit_student()
        except Exception as exc:
            show_error(self, exc)

    def _edit_student(self):
        try:
            student_id = selected_id(self.students_table)
            if student_id is None:
                raise ValueError("Select a student from the directory first.")
            student = next((s for s in self.students if s["id"] == student_id), None)
            if student is None:
                self.refresh()
                return
            dialog = EditStudentDialog(self.service, student, self.service.list_classes(), self)
            if dialog.exec() == QDialog.Accepted:
                self.refresh()
                self.changed.emit()
                if dialog.fee_changed:
                    success(self, "Student profile saved. The revised monthly fee applies to future challans.\n\nTo correct an existing unpaid or zero-fee bill, open Fees & collections, select the bill, and choose Amend challan. Bills with payment history remain unchanged.")
        except Exception as exc:
            show_error(self, exc)
