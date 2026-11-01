"""Real Qt/service integration checks against isolated temporary academy data."""

import csv
from datetime import date, timedelta
import os

# These checks exercise widgets without requiring a desktop/display server.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QFileDialog, QLabel, QMessageBox

from nexus.exports import export_challan, export_receipt
from nexus.services import AcademyService
from nexus.ui import admin, auth, common, fees, operations, shell, students


PASSWORD = "Offline test password 923!"


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    yield app
    app.closeAllWindows()


@pytest.fixture
def ui_messages(qapp, monkeypatch):
    """Unexpected modal errors fail a test instead of hanging the test runner."""
    errors = []
    for module in (admin, auth, common, fees, operations, shell, students):
        if hasattr(module, "show_error"):
            monkeypatch.setattr(module, "show_error", lambda _parent, error: errors.append(str(error)))
        if hasattr(module, "success"):
            monkeypatch.setattr(module, "success", lambda *_: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *_: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda _parent, _title, message, *_: errors.append(str(message)))
    monkeypatch.setattr(QMessageBox, "critical", lambda _parent, _title, message, *_: errors.append(str(message)))
    yield errors
    for widget in list(qapp.topLevelWidgets()):
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
    assert not errors, f"Unexpected desktop error dialog(s): {errors}"


@pytest.fixture
def academy(tmp_path, ui_messages):
    service = AcademyService(tmp_path / "academy")
    service.setup_academy(
        "Intellectual Nexus Academy", "Abbottabad", "03001234567",
        "Academy Owner", "owner", PASSWORD,
    )
    yield service
    service.close()


def _enroll(service, *, class_record=None, name="Ayesha Khan", fee="8000"):
    class_record = class_record or service.add_class("FSc Morning", "Mon–Fri 9am", fee)
    return service.admit_student(
        name, "Guardian Khan", "03001234567", class_record["id"],
        date.today().isoformat(), fee, "0", "0",
        (date.today() + timedelta(days=7)).isoformat(),
    )


def test_first_run_setup_and_subsequent_login(qapp, ui_messages, tmp_path, monkeypatch):
    service = AcademyService(tmp_path / "first-run")
    codes = []
    monkeypatch.setattr(
        auth.RecoveryCodeDialog, "exec",
        lambda dialog: codes.append(dialog.code_field.text()) or QDialog.DialogCode.Accepted,
    )
    try:
        window = auth.AuthWindow(service)
        assert window.pages.currentIndex() == 3
        authenticated = []
        window.authenticated.connect(lambda: authenticated.append(True))
        window.owner_name.setText("Academy Owner")
        window.owner_username.setText("owner")
        window.owner_password.setText(PASSWORD)
        window.owner_confirm.setText(PASSWORD)
        window._setup()
        assert authenticated == [True]
        assert not service.setup_required()
        assert service.user["role"] == "admin"
        assert len(codes) == 1 and len(codes[0]) >= 20
        assert not window.owner_password.text()

        service.logout()
        returning = auth.AuthWindow(service)
        assert returning.pages.currentIndex() == 0
        returning.authenticated.connect(lambda: authenticated.append(True))
        returning.login_username.setText("owner")
        returning.login_password.setText(PASSWORD)
        returning._login()
        assert authenticated == [True, True]
        assert service.user["username"] == "owner"
        assert not returning.login_password.text()
    finally:
        service.close()


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("admin", {"dashboard", "students", "fees", "attendance", "reports", "users", "settings"}),
        ("cashier", {"dashboard", "fees", "reports"}),
        ("receptionist", {"dashboard", "students", "fees"}),
        ("teacher", {"dashboard", "attendance"}),
    ],
)
def test_role_navigation_opens_only_authorized_pages(qapp, academy, role, expected):
    if role != "admin":
        academy.create_staff(role.title(), role, PASSWORD, role)
        academy.login(role, PASSWORD)
    window = shell.MainWindow(academy)
    window.show()
    qapp.processEvents()
    assert set(window.pages) == expected
    assert set(window.nav_buttons) == expected
    for name in expected:
        window.nav_buttons[name].click()
        qapp.processEvents()
        assert window.stack.currentWidget() is window.pages[name]
        assert window.nav_buttons[name].isChecked()
    if role == "receptionist":
        assert window.pages["fees"].receive.isHidden()
        assert window.pages["fees"].reverse.isHidden()
    elif role == "cashier":
        assert not window.pages["fees"].receive.isHidden()
        assert window.pages["fees"].reverse.isHidden()


def test_teacher_saves_real_attendance_from_assigned_roster(qapp, academy):
    teacher = academy.create_staff("Teacher One", "teacher", PASSWORD, "teacher")
    assigned = academy.add_class("Assigned class", "4 pm", "8000", teacher["id"])
    other = academy.add_class("Other class", "5 pm", "8000")
    student = _enroll(academy, class_record=assigned)["student"]
    _enroll(academy, class_record=other, name="Other Student")
    academy.login("teacher", PASSWORD)
    window = shell.MainWindow(academy)
    window.navigate("attendance")
    page = window.pages["attendance"]
    assert page.class_combo.count() == 1
    assert page.class_combo.currentData() == assigned["id"]
    assert page.roster_table.rowCount() == 1
    assert page.roster_table.item(0, 1).text() == student["full_name"]
    assert page._status_widgets[0].currentText() == "Not marked"
    page._status_widgets[0].setCurrentText("Late")
    page.save_button.click()
    qapp.processEvents()
    persisted = academy.attendance_roster(assigned["id"], date.today().isoformat())
    assert persisted[0]["status"] == "Late"
    assert not page._dirty
    assert "1 late" in page.summary.text()


def _pdf_text(qapp, path):
    document = QPdfDocument()
    assert document.load(str(path)) == QPdfDocument.Error.None_
    assert document.status() == QPdfDocument.Status.Ready
    assert document.pageCount() >= 1
    text = "\n".join(document.getAllText(index).text() for index in range(document.pageCount()))
    document.close()
    return text


def test_exported_challans_and_receipts_are_readable_pdfs(qapp, academy, tmp_path):
    admission = _enroll(academy)
    challan = admission["challan"]
    unpaid = export_challan(academy, challan["id"], tmp_path / "unpaid.pdf")
    text = _pdf_text(qapp, unpaid)
    assert "FEE CHALLAN" in text
    assert "Ayesha Khan" in text
    assert challan["number"] in text
    assert "Unpaid" in text and "8,000.00" in text

    payment = academy.record_payment(challan["id"], "5000", "Cash")
    receipt = export_receipt(academy, payment["id"], tmp_path / "receipt.pdf")
    text = _pdf_text(qapp, receipt)
    assert "PAYMENT RECEIPT" in text
    assert payment["number"] in text
    assert "5,000.00" in text and "3,000.00" in text

    partial = export_challan(academy, challan["id"], tmp_path / "partial.pdf")
    assert "Partially paid" in _pdf_text(qapp, partial)
    academy.reverse_payment(payment["id"], "Test correction")
    reversed_receipt = export_receipt(academy, payment["id"], tmp_path / "reversed.pdf")
    assert "REVERSED" in _pdf_text(qapp, reversed_receipt)


def test_payment_dialog_updates_shell_ledger_and_metrics(qapp, academy):
    admission = _enroll(academy)
    window = shell.MainWindow(academy)
    window.navigate("fees")
    page = window.pages["fees"]
    assert page.challan_table.item(0, 7).text() == "Unpaid"

    dialog = fees.PaymentDialog(academy, admission["challan"], window)
    dialog.amount.setValue(5000)
    dialog.buttons.button(QDialogButtonBox.StandardButton.Save).click()
    qapp.processEvents()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.payment["amount"] == "5000.00"
    page.refresh()
    assert page.challan_table.item(0, 7).text() == "Partially paid"
    assert page.challan_table.item(0, 6).text() == "Rs 3,000"
    assert page.payment_table.rowCount() == 1

    window.navigate("dashboard")
    dashboard = window.pages["dashboard"]
    displayed_metrics = [
        label.text()
        for index in range(dashboard.metrics.count())
        for label in dashboard.metrics.itemAt(index).widget().findChildren(QLabel)
    ]
    assert "Rs 5,000" in displayed_metrics
    assert "Rs 3,000" in displayed_metrics
    assert dashboard.payments.item(0, 1).text() == "Ayesha Khan"
    assert dashboard.payments.item(0, 4).text() == "Rs 5,000"


def test_reports_export_real_overdue_data_with_spreadsheet_safe_names(academy, tmp_path, monkeypatch):
    admission = _enroll(academy, name="=2+2")
    previous_month = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    challan = academy.create_challan(
        admission["student"]["id"], previous_month, "8000", "0",
        (date.today() - timedelta(days=3)).isoformat(),
    )
    destination = tmp_path / "overdue.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_: (str(destination), "CSV files (*.csv)"))
    page = operations.ReportsPage(academy)
    page.refresh()
    assert page.overdue_table.rowCount() == 1
    page.export_overdue_button.click()
    with destination.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert len(rows) == 2
    assert rows[1][0] == challan["number"]
    assert rows[1][2] == "'=2+2"
    assert rows[1][-1] == "8000.00"
