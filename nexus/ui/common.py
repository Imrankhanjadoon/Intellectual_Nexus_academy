"""Shared accessible widgets and presentation helpers."""
from decimal import Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLabel, QMessageBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)


def money(value):
    amount = Decimal(str(value or 0))
    return f"Rs {amount:,.0f}" if amount == amount.to_integral_value() else f"Rs {amount:,.2f}"


def show_error(parent, exc):
    QMessageBox.warning(parent, "Please check", str(exc))


def success(parent, message):
    QMessageBox.information(parent, "Intellectual Nexus Academy", message)


def heading(title, subtitle=""):
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    label = QLabel(title)
    label.setObjectName("pageTitle")
    layout.addWidget(label)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setWordWrap(True)
        sub.setObjectName("muted")
        layout.addWidget(sub)
    return box


class RecordTable(QTableWidget):
    """Keep the name column legible; use horizontal scrolling on small screens."""
    def __init__(self, *args):
        super().__init__(*args)
        self._flexible_columns = ()
        self._flexible_minimum = 150
        self._adjusting_columns = False

    def set_flexible_column(self, column, minimum=150):
        self.set_flexible_columns((column,), minimum)

    def set_flexible_columns(self, columns, minimum=150):
        self._flexible_columns = tuple(columns)
        self._flexible_minimum = minimum
        self.adjust_columns()

    def adjust_columns(self):
        columns = tuple(column for column in self._flexible_columns if column < self.columnCount() and not self.isColumnHidden(column))
        if not columns or self._adjusting_columns:
            return
        self._adjusting_columns = True
        try:
            header = self.horizontalHeader()
            others = sum(self.columnWidth(index) for index in range(self.columnCount()) if index not in columns and not self.isColumnHidden(index))
            scroll = self.viewport().width() - others < self._flexible_minimum * len(columns)
            for column in columns:
                if scroll:
                    header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
                    self.setColumnWidth(column, self._flexible_minimum)
                else:
                    header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        finally:
            self._adjusting_columns = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adjust_columns()


def table(headers):
    widget = RecordTable(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.verticalHeader().setVisible(False)
    widget.verticalHeader().setDefaultSectionSize(44)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setAlternatingRowColors(True)
    widget.setShowGrid(False)
    widget.setWordWrap(False)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    widget.horizontalHeader().setMinimumSectionSize(80)
    widget.setMinimumHeight(160)
    widget.setSortingEnabled(False)
    widget.setAccessibleName("Records")
    return widget


def fill_table(widget, rows, data=None):
    widget.setUpdatesEnabled(False)
    widget.setRowCount(len(rows))
    for row_number, row in enumerate(rows):
        for column, value in enumerate(row):
            item = QTableWidgetItem(str(value if value is not None else "—"))
            item.setToolTip(item.text())
            if column == 0 and data is not None:
                item.setData(Qt.ItemDataRole.UserRole, data[row_number])
            if str(value) in ("Paid", "Present", "active", "Active"):
                from PySide6.QtGui import QColor
                item.setForeground(QColor("#245a42"))
            elif str(value) in ("Unpaid", "Absent", "pending", "Pending"):
                from PySide6.QtGui import QColor
                item.setForeground(QColor("#81672f"))
            widget.setItem(row_number, column, item)
    widget.setUpdatesEnabled(True)


def selected_id(widget):
    row = widget.currentRow()
    item = widget.item(row, 0) if row >= 0 else None
    return item.data(Qt.ItemDataRole.UserRole) if item else None


class BasePage(QWidget):
    changed = Signal()

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.setObjectName("documentPage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.service = service

    def refresh(self):
        pass
