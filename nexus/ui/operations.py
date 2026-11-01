"""Offline class attendance and collection reports."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .common import BasePage, fill_table, heading, money, show_error, success, table


ATTENDANCE_STATUSES = ("Not marked", "Present", "Absent", "Late", "Excused")


def _card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(22, 18, 22, 18)
    layout.setSpacing(12)
    return frame, layout


def _panel_header(title, subtitle=""):
    header = QFrame()
    header.setObjectName("registerHeader")
    row = QHBoxLayout(header)
    row.setContentsMargins(22, 13, 22, 13)
    row.setSpacing(18)
    text = QVBoxLayout()
    text.setSpacing(5)
    label = QLabel(title)
    label.setObjectName("sectionTitle")
    text.addWidget(label)
    detail = QLabel(subtitle)
    detail.setObjectName("muted")
    detail.setWordWrap(True)
    text.addWidget(detail)
    row.addLayout(text, 1)
    return header, row, detail


class AttendancePage(BasePage):
    """Attendance is saved explicitly, scoped to the selected class and day."""

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        self._roster: list[dict] = []
        self._status_widgets: list[QComboBox] = []
        self._loaded_key: tuple[int, str] | None = None
        self._dirty = False
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(20)
        layout.addWidget(heading("Attendance register", "ACADEMIC OFFICE  /  DAILY CLASS ATTENDANCE"))

        filters, filters_layout = _card()
        controls = QHBoxLayout()
        controls.setSpacing(14)
        class_field = QVBoxLayout()
        class_field.addWidget(QLabel("Class / batch"))
        self.class_combo = QComboBox()
        self.class_combo.setMinimumWidth(220)
        class_field.addWidget(self.class_combo)
        controls.addLayout(class_field, 2)
        date_field = QVBoxLayout()
        date_field.addWidget(QLabel("Attendance date"))
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setKeyboardTracking(False)
        self.date_edit.setDisplayFormat("dd MMM yyyy")
        date_field.addWidget(self.date_edit)
        controls.addLayout(date_field, 1)
        self.load_button = QPushButton("Load roster")
        self.load_button.setObjectName("primary")
        self.load_button.setMinimumWidth(140)
        controls.addWidget(self.load_button, 0, Qt.AlignmentFlag.AlignBottom)
        filters_layout.addLayout(controls)
        self.filter_hint = QLabel("Select a class to load its students.")
        self.filter_hint.setObjectName("muted")
        self.filter_hint.setWordWrap(True)
        filters_layout.addWidget(self.filter_hint)
        layout.addWidget(filters)

        roster_card, roster_layout = _card()
        roster_layout.setContentsMargins(0, 0, 0, 0)
        roster_layout.setSpacing(0)
        register_header, row, self.roster_label = _panel_header(
            "Daily class attendance", "Load a class and date to open its attendance record."
        )
        self.present_button = QPushButton("Mark all present")
        self.present_button.setObjectName("quiet")
        row.addWidget(self.present_button)
        roster_layout.addWidget(register_header)
        body = QVBoxLayout()
        body.setContentsMargins(22, 14, 22, 14)
        body.setSpacing(16)
        self.save_button = QPushButton("Save attendance")
        self.save_button.setObjectName("primary")
        self.save_button.setMinimumWidth(170)
        self.roster_table = table(["REGISTRATION NO.", "STUDENT NAME", "ATTENDANCE STATUS"])
        roster_header = self.roster_table.horizontalHeader()
        roster_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        roster_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        roster_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.roster_table.setColumnWidth(2, 210)
        self.roster_table.setMinimumHeight(150)
        body.addWidget(self.roster_table, 1)
        self.summary = QLabel("No students loaded.")
        self.summary.setObjectName("muted")
        self.summary.setWordWrap(True)
        footer = QHBoxLayout()
        footer.setSpacing(18)
        footer.addWidget(self.summary, 1)
        footer.addWidget(self.save_button)
        body.addLayout(footer)
        roster_layout.addLayout(body, 1)
        layout.addWidget(roster_card, 1)

        self.load_button.clicked.connect(self._load_roster)
        self.present_button.clicked.connect(self._mark_present)
        self.save_button.clicked.connect(self._save)
        self.class_combo.currentIndexChanged.connect(self._selection_changed)
        self.date_edit.dateChanged.connect(self._selection_changed)
        self._set_editable(False)

    def _selection_key(self):
        class_id = self.class_combo.currentData()
        if class_id is None:
            return None
        return int(class_id), self.date_edit.date().toString("yyyy-MM-dd")

    def _set_editable(self, enabled):
        self.present_button.setEnabled(bool(enabled and self._roster))
        self.save_button.setEnabled(bool(enabled and self._roster))
        for widget in self._status_widgets:
            widget.setEnabled(enabled)

    def _selection_changed(self, *_):
        if self._loading:
            return
        if self._selection_key() == self._loaded_key and self._loaded_key:
            self._set_editable(True)
            self.filter_hint.setText(
                "Changes are saved only when you select Save attendance."
            )
            return
        self._load_roster()

    def _restore_loaded_selection(self):
        if self._loaded_key is None:
            return
        self._loading = True
        try:
            self.class_combo.setCurrentIndex(self.class_combo.findData(self._loaded_key[0]))
            self.date_edit.setDate(QDate.fromString(self._loaded_key[1], "yyyy-MM-dd"))
        finally:
            self._loading = False
        self._set_editable(True)
        self.filter_hint.setText("Unsaved attendance is preserved. Save the register before switching class or date.")

    def _can_replace(self):
        if not self._dirty:
            return True
        return QMessageBox.question(
            self,
            "Unsaved attendance",
            "Discard the unsaved attendance changes and load another roster?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        ) == QMessageBox.StandardButton.Discard

    def refresh(self):
        # Preserve edits when another page refreshes the shell after a mutation.
        if self._dirty:
            return
        try:
            classes = self.service.list_classes()
            previous_id = self.class_combo.currentData()
            self._loading = True
            self.class_combo.blockSignals(True)
            self.class_combo.clear()
            for item in classes:
                label = item["name"]
                if item.get("schedule"):
                    label += f" · {item['schedule']}"
                self.class_combo.addItem(label, item["id"])
            previous_index = self.class_combo.findData(previous_id)
            if previous_index >= 0:
                self.class_combo.setCurrentIndex(previous_index)
            self.class_combo.blockSignals(False)
            self._loading = False
            self.load_button.setEnabled(bool(classes))
            if not classes:
                self._roster = []
                self._status_widgets = []
                self._loaded_key = None
                fill_table(self.roster_table, [])
                self._set_editable(False)
                self.filter_hint.setText(
                    "No classes are available. An administrator can create a class "
                    "and assign its teacher from Students & classes."
                )
                self.roster_label.setText("No class is available for attendance recording.")
                self.summary.setText("No classes assigned yet.")
            else:
                self._load_roster()
        except Exception as exc:
            self.class_combo.blockSignals(False)
            self._loading = False
            self._set_editable(False)
            show_error(self, exc)

    def _load_roster(self):
        key = self._selection_key()
        if key is None:
            return
        if not self._can_replace():
            self._restore_loaded_selection()
            return
        try:
            roster = self.service.attendance_roster(*key)
            self._loading = True
            self._roster = roster
            self._loaded_key = key
            self._dirty = False
            self._status_widgets = []
            fill_table(
                self.roster_table,
                [[item["student_number"], item["full_name"], ""] for item in roster],
                [item["student_id"] for item in roster],
            )
            for index, item in enumerate(roster):
                status = QComboBox()
                status.addItems(ATTENDANCE_STATUSES)
                status.setCurrentText(item.get("status", "Not marked"))
                status.currentTextChanged.connect(self._mark_dirty)
                self.roster_table.setCellWidget(index, 2, status)
                self.roster_table.setRowHeight(index, 44)
                self._status_widgets.append(status)
            self.roster_label.setText(
                f"{self.class_combo.currentText()} · {self.date_edit.date().toString('dd MMM yyyy')}"
            )
            self._loading = False
            self._set_editable(True)
            self.filter_hint.setText(
                "Changes are saved only when you select Save attendance."
                if roster else "This class has no students yet. Add an admission to begin."
            )
            self._update_summary()
        except Exception as exc:
            self._loading = False
            if self._loaded_key is not None:
                self._restore_loaded_selection()
            else:
                self._set_editable(False)
            show_error(self, exc)

    def _mark_dirty(self, *_):
        if self._loading:
            return
        self._dirty = True
        self._update_summary()

    def _update_summary(self):
        counts = {status: 0 for status in ATTENDANCE_STATUSES}
        for widget in self._status_widgets:
            counts[widget.currentText()] += 1
        if not self._roster:
            self.summary.setText("No students in this class.")
            return
        parts = [f"{len(self._roster)} students"]
        parts.extend(f"{counts[status]} {status.lower()}" for status in ATTENDANCE_STATUSES if counts[status])
        if self._dirty:
            parts.append("Unsaved changes")
        self.summary.setText("  ·  ".join(parts))

    def _mark_present(self):
        if self._selection_key() != self._loaded_key:
            return
        for widget in self._status_widgets:
            widget.setCurrentText("Present")

    def _save(self):
        if not self._loaded_key or self._selection_key() != self._loaded_key:
            return
        try:
            records = [
                {"student_id": item["student_id"], "status": widget.currentText()}
                for item, widget in zip(self._roster, self._status_widgets)
            ]
            self.service.save_attendance(*self._loaded_key, records)
            self._dirty = False
            self._update_summary()
            self.changed.emit()
            success(self, "Attendance saved for the selected class and date.")
        except Exception as exc:
            show_error(self, exc)


def _safe_csv_cell(value):
    """Spreadsheet exports must treat names/reference text as literal cells."""
    text = "" if value is None else str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


class ReportsPage(BasePage):
    """Current collections and overdue balances from the local ledger."""

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        self._report: dict = {}
        self._filtered_defaulters = []
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(180)
        self._filter_timer.timeout.connect(self._render_defaulters)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(20)
        title_row = QHBoxLayout()
        title_row.addWidget(heading("Fee collection reports", "ACCOUNTS OFFICE  /  COLLECTIONS AND OUTSTANDING FEES"), 1)
        refresh_button = QPushButton("Refresh reports")
        refresh_button.setMinimumWidth(140)
        refresh_button.clicked.connect(self.refresh)
        title_row.addWidget(refresh_button)
        layout.addLayout(title_row)

        metrics = QHBoxLayout()
        metrics.setSpacing(14)
        self.metrics: dict[str, QLabel] = {}
        for key, title, note in (
            ("month_collected", "CURRENT MONTH COLLECTIONS", "Net receipts for the current calendar month"),
            ("outstanding", "TOTAL OUTSTANDING", "Balances payable against issued challans"),
            ("overdue_count", "OVERDUE CHALLANS", "Unsettled challans past their due date"),
        ):
            card, card_layout = _card()
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
            card_layout.setContentsMargins(20, 14, 20, 14)
            card_layout.setSpacing(6)
            label = QLabel(title)
            label.setObjectName("eyebrow")
            card_layout.addWidget(label)
            value = QLabel("—")
            value.setObjectName("metric")
            card_layout.addWidget(value)
            description = QLabel(note)
            description.setObjectName("muted")
            description.setWordWrap(True)
            card_layout.addWidget(description)
            self.metrics[key] = value
            metrics.addWidget(card, 1)
        layout.addLayout(metrics)

        reports_card, reports_layout = _card()
        reports_layout.setContentsMargins(0, 0, 0, 0)
        reports_layout.setSpacing(0)
        report_header, report_header_row, _ = _panel_header(
            "Collection statements", "Review payment collections and outstanding fee balances."
        )
        currency = QLabel("CURRENCY  ·  PKR")
        currency.setObjectName("eyebrow")
        report_header_row.addWidget(currency)
        reports_layout.addWidget(report_header)
        report_body = QVBoxLayout()
        report_body.setContentsMargins(22, 12, 22, 14)
        report_body.setSpacing(12)
        self.tabs = QTabWidget()
        overdue = QWidget()
        overdue_layout = QVBoxLayout(overdue)
        overdue_layout.setContentsMargins(0, 18, 0, 0)
        toolbar = QHBoxLayout()
        self.overdue_hint = QLabel("No report loaded.")
        self.overdue_hint.setObjectName("muted")
        toolbar.addWidget(self.overdue_hint, 1)
        self.export_overdue_button = QPushButton("Export overdue CSV")
        self.export_overdue_button.setObjectName("quiet")
        self.export_overdue_button.clicked.connect(self._export_overdue)
        toolbar.addWidget(self.export_overdue_button)
        overdue_layout.addLayout(toolbar)
        search_row = QHBoxLayout()
        search_row.setSpacing(10)
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setAccessibleName("Search overdue fees")
        self.search.setPlaceholderText("Search student, registration ID, class or challan number…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda *_: self._filter_timer.start())
        search_row.addWidget(self.search, 1)
        self.clear_filter = QPushButton("Clear search")
        self.clear_filter.clicked.connect(self._clear_filter)
        search_row.addWidget(self.clear_filter)
        overdue_layout.addLayout(search_row)
        self.overdue_table = table(["CHALLAN NO.", "STUDENT NAME", "CLASS / BATCH", "DUE DATE", "TOTAL (PKR)", "BALANCE (PKR)"])
        self.overdue_table.setMinimumHeight(130)
        overdue_layout.addWidget(self.overdue_table, 1)
        self.tabs.addTab(overdue, "Overdue fee register")

        monthly = QWidget()
        monthly_layout = QVBoxLayout(monthly)
        monthly_layout.setContentsMargins(0, 18, 0, 0)
        monthly_toolbar = QHBoxLayout()
        self.monthly_hint = QLabel("Collections grouped by payment month.")
        self.monthly_hint.setObjectName("muted")
        monthly_toolbar.addWidget(self.monthly_hint, 1)
        self.export_monthly_button = QPushButton("Export monthly CSV")
        self.export_monthly_button.setObjectName("quiet")
        self.export_monthly_button.clicked.connect(self._export_monthly)
        monthly_toolbar.addWidget(self.export_monthly_button)
        monthly_layout.addLayout(monthly_toolbar)
        self.monthly_table = table(["COLLECTION MONTH", "NET COLLECTIONS (PKR)"])
        self.monthly_table.setMinimumHeight(130)
        monthly_layout.addWidget(self.monthly_table, 1)
        self.tabs.addTab(monthly, "Monthly collection statement")
        report_body.addWidget(self.tabs, 1)
        note = QLabel(
            "Summary totals include all records. The overdue search filters the register and its CSV export. "
            "Amounts are in PKR; reversed entries are excluded from collections."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        report_body.addWidget(note)
        reports_layout.addLayout(report_body, 1)
        layout.addWidget(reports_card, 1)

    def refresh(self):
        try:
            report = self.service.reports()
            self._report = report
            self.metrics["month_collected"].setText(money(report["month_collected"]))
            self.metrics["outstanding"].setText(money(report["outstanding"]))
            self.metrics["overdue_count"].setText(str(report["overdue_count"]))
            self._filter_timer.stop()
            self._render_defaulters()
            months = report.get("monthly_collection", [])
            fill_table(self.monthly_table, [[item["month"], money(item["amount"])] for item in months])
            for row in range(self.monthly_table.rowCount()):
                self.monthly_table.item(row, 1).setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
            self.monthly_hint.setText(
                "Collections grouped by payment month, after reversals."
                if months else "No collections recorded yet."
            )
            self.export_monthly_button.setEnabled(bool(months))
        except Exception as exc:
            self.export_overdue_button.setEnabled(False)
            self.export_monthly_button.setEnabled(False)
            show_error(self, exc)

    def _clear_filter(self):
        self.search.clear()
        self._filter_timer.stop()
        self._render_defaulters()
        self.search.setFocus()

    def _matching_defaulters(self):
        tokens = self.search.text().strip().casefold().split()
        return [
            item for item in self._report.get("defaulters", [])
            if all(token in " ".join(str(item.get(key, "")) for key in (
                "number", "student_number", "student_name", "class_name", "due_date",
            )).casefold() for token in tokens)
        ]

    def _render_defaulters(self):
        try:
            defaulters = self._matching_defaulters()
            self._filtered_defaulters = defaulters
            fill_table(
                self.overdue_table,
                [[
                    item["number"], item["student_name"], item.get("class_name", "—"),
                    item["due_date"], money(item["total"]), money(item["balance"]),
                ] for item in defaulters],
                [item["id"] for item in defaulters],
            )
            for row in range(self.overdue_table.rowCount()):
                for column in (4, 5):
                    self.overdue_table.item(row, column).setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
            total = len(self._report.get("defaulters", []))
            if total:
                self.overdue_hint.setText(f"{len(defaulters)} of {total} overdue challans shown.")
                if not defaulters:
                    self.overdue_hint.setText("No overdue challans match this search. Clear the search to view all.")
            else:
                self.overdue_hint.setText("No overdue fees. New overdue challans will appear here.")
            self.clear_filter.setEnabled(bool(self.search.text()))
            self.export_overdue_button.setEnabled(bool(defaulters))
        except Exception as exc:
            self.export_overdue_button.setEnabled(False)
            show_error(self, exc)

    def _export(self, name, headers, rows):
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Export report",
            str(Path.home() / f"nexus-{name}-{date.today().isoformat()}.csv"),
            "CSV files (*.csv)",
        )
        if not destination:
            return
        path = Path(destination)
        if path.suffix.lower() != ".csv":
            path = path.with_suffix(".csv")
        try:
            with path.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(headers)
                writer.writerows([[_safe_csv_cell(cell) for cell in row] for row in rows])
            success(self, f"Report saved to:\n{path}")
        except Exception as exc:
            show_error(self, exc)

    def _export_overdue(self):
        # Re-authorize the request, so deactivated accounts cannot export stale data.
        try:
            self._report = self.service.reports()
            self._filter_timer.stop()
            self._render_defaulters()
            self._export(
                "overdue",
                ["Challan", "Student ID", "Student", "Class / batch", "Due date", "Total PKR", "Paid PKR", "Balance PKR"],
                [
                    [
                        item["number"], item["student_number"], item["student_name"],
                        item.get("class_name", ""), item["due_date"], item["total"], item["paid"], item["balance"],
                    ]
                    for item in self._filtered_defaulters
                ],
            )
        except Exception as exc:
            show_error(self, exc)

    def _export_monthly(self):
        try:
            self._report = self.service.reports()
            self._export(
                "monthly-collections",
                ["Payment month", "Collected PKR"],
                [[item["month"], item["amount"]] for item in self._report.get("monthly_collection", [])],
            )
        except Exception as exc:
            show_error(self, exc)
