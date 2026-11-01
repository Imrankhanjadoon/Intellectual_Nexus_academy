"""Regression coverage for admission intent, billing corrections and staff workflows."""

import csv
from datetime import date, timedelta
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QDate
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFileDialog, QMessageBox

from nexus.ui import admin, auth, fees, operations, students
from nexus.ui.common import selected_id

# Reuse the existing real-Qt fixtures and their unexpected-modal-error guard.
from test_desktop import PASSWORD, academy, qapp, ui_messages


@pytest.fixture(autouse=True)
def reduce_motion(qapp):
    previous = qapp.property("reduce_motion")
    qapp.setProperty("reduce_motion", True)
    yield
    qapp.setProperty("reduce_motion", previous)


def _save(dialog):
    dialog.buttons.button(QDialogButtonBox.StandardButton.Save).click()


def _admission_dialog(service, cls, name="Ayesha Khan"):
    dialog = students.AdmissionDialog(service, [cls])
    dialog.name.setText(name)
    dialog.guardian.setText("Guardian Khan")
    dialog.phone.setText("03001234567")
    return dialog


def _enroll(service, cls, name="Ayesha Khan", *, fee="8000", fee_exempt=False):
    return service.admit_student(
        name, "Guardian Khan", "03001234567", cls["id"],
        date.today().isoformat(), fee, "0", "0", date.today().isoformat(),
        fee_exempt=fee_exempt,
    )


def test_admission_rejects_accidental_zero_fee_without_creating_records(academy, monkeypatch):
    cls = academy.add_class("Unconfigured fee class", "9 am", "0")
    dialog = _admission_dialog(academy, cls)
    errors = []
    monkeypatch.setattr(students, "show_error", lambda _parent, error: errors.append(str(error)))
    _save(dialog)
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.buttons.button(QDialogButtonBox.StandardButton.Save).isEnabled()
    assert len(errors) == 1 and "Fee-exempt" in errors[0]
    assert academy.list_students() == []
    assert academy.list_challans() == []
    assert academy.list_payments() == []


def test_explicit_zero_fee_admission_is_not_paid_and_has_no_receipt(academy):
    cls = academy.add_class("Scholarship class", "9 am", "0")
    dialog = _admission_dialog(academy, cls)
    dialog.fee_exempt.setChecked(True)
    _save(dialog)
    assert dialog.result() == QDialog.DialogCode.Accepted
    challan = academy.challan_details(dialog.result_record["challan"]["id"])
    assert challan["status"] == "No payment due"
    assert challan["total"] == challan["paid"] == "0.00"
    assert challan["payments"] == []
    assert academy.list_payments() == []
    assert academy.list_challans(status="Paid") == []
    assert academy.dashboard()["month_collected"] == "0.00"


def test_positive_fee_admission_starts_unpaid_without_a_receipt(academy):
    cls = academy.add_class("FSc Pre-Medical", "9 am", "8000")
    dialog = _admission_dialog(academy, cls)
    dialog.admission_fee.setValue(1000)
    _save(dialog)
    assert dialog.result() == QDialog.DialogCode.Accepted
    challan = academy.challan_details(dialog.result_record["challan"]["id"])
    assert challan["status"] == "Unpaid"
    assert challan["total"] == challan["balance"] == "9000.00"
    assert challan["paid"] == "0.00" and challan["payments"] == []
    assert academy.list_payments() == []


def test_future_fee_profile_edit_does_not_rebill_zero_challan_but_amendment_does(academy, monkeypatch):
    cls = academy.add_class("FSc Morning", "9 am", "0")
    admission = _enroll(academy, cls, fee="0", fee_exempt=True)
    student, original_bill = admission["student"], admission["challan"]
    profile = students.EditStudentDialog(academy, student, [cls])
    profile.monthly_fee.setValue(8000)
    _save(profile)
    assert profile.result() == QDialog.DialogCode.Accepted
    assert academy.list_students()[0]["monthly_fee"] == "8000.00"
    unchanged = academy.challan_details(original_bill["id"])
    assert unchanged["status"] == "No payment due" and unchanged["total"] == "0.00"
    assert academy.list_payments() == []

    errors = []
    monkeypatch.setattr(fees, "show_error", lambda _parent, error: errors.append(str(error)))
    amendment = fees.AmendChallanDialog(academy, unchanged)
    amendment.tuition.setValue(8000)
    _save(amendment)
    assert amendment.result() != QDialog.DialogCode.Accepted
    assert len(errors) == 1 and "reason" in errors[0].lower()
    assert academy.challan_details(original_bill["id"])["total"] == "0.00"

    amendment.reason.setPlainText("Tuition was omitted from the admission assessment.")
    _save(amendment)
    assert amendment.result() == QDialog.DialogCode.Accepted
    corrected = academy.challan_details(original_bill["id"])
    assert corrected["status"] == "Unpaid" and corrected["total"] == "8000.00"
    assert len(academy.list_students()) == len(academy.list_challans()) == 1
    assert academy.list_payments() == []
    audit = [row for row in academy.list_audit() if row["action"] == "Challan amended"]
    assert audit and "Tuition was omitted" in audit[0]["details"]

    payment = fees.PaymentDialog(academy, corrected)
    payment.amount.setValue(5000)
    _save(payment)
    assert payment.result() == QDialog.DialogCode.Accepted
    for reverse_first in (False, True):
        if reverse_first:
            academy.reverse_payment(payment.payment["id"], "Payment was entered in error.")
        locked = fees.AmendChallanDialog(academy, academy.challan_details(original_bill["id"]))
        locked.tuition.setValue(9000)
        locked.reason.setPlainText("Attempt to rewrite a bill with payment history.")
        _save(locked)
        assert locked.result() != QDialog.DialogCode.Accepted
        assert "payment history" in errors[-1].lower()
        assert academy.challan_details(original_bill["id"])["total"] == "8000.00"
    assert len(errors) == 3


def test_staff_search_filters_account_fields_and_clears_hidden_action_targets(academy):
    academy.create_staff("Teacher One", "teacher", PASSWORD, "teacher")
    academy.create_staff("Cashier One", "cashier", PASSWORD, "cashier")
    academy.signup("Pending Staff", "pending", PASSWORD)
    page = admin.UsersPage(academy)
    page.refresh()
    assert page.accounts.rowCount() == 4

    # Multiple tokens cover a role and account status; the timer applies the filter.
    page.search.setText("teacher active")
    QTest.qWait(220)
    assert page.accounts.rowCount() == 1
    assert page.accounts.item(0, 1).text() == "teacher"

    page.search.setText("accountant")
    QTest.qWait(220)
    assert page.accounts.rowCount() == 1
    assert page.accounts.item(0, 1).text() == "cashier"
    page.accounts.selectRow(0)
    assert page.reset_button.isEnabled()

    page.search.setText("owner")
    QTest.qWait(220)
    assert selected_id(page.accounts) is None
    assert not page.reset_button.isEnabled()
    page.search.setText("pending")
    QTest.qWait(220)
    page.accounts.selectRow(0)
    assert page.approve_button.isEnabled()
    assert "1 of 4" in page.summary.text()
    page.clear_filter.click()
    assert not page.search.text() and page.accounts.rowCount() == 4


def test_overdue_search_exports_only_current_matches_and_keeps_summary_totals(academy, tmp_path, monkeypatch):
    cls = academy.add_class("FSc Morning", "9 am", "8000")
    first = _enroll(academy, cls, "Ayesha Khan")
    second = _enroll(academy, cls, "Bilal Ali")
    previous_month = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    old_due = (date.today() - timedelta(days=5)).isoformat()
    late_a = academy.create_challan(first["student"]["id"], previous_month, "8000", "0", old_due)
    academy.create_challan(second["student"]["id"], previous_month, "8000", "0", old_due)
    academy.record_payment(late_a["id"], "500", "Cash")
    page = operations.ReportsPage(academy)
    page.refresh()
    assert page.overdue_table.rowCount() == 2
    summary_before = page.metrics["outstanding"].text()
    page.search.setText(first["student"]["student_number"])
    QTest.qWait(220)
    assert page.overdue_table.rowCount() == 1
    assert page.overdue_table.item(0, 1).text() == "Ayesha Khan"
    assert page.metrics["outstanding"].text() == summary_before

    destination = tmp_path / "filtered-overdue.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_: (str(destination), "CSV files (*.csv)"))
    page.export_overdue_button.click()
    with destination.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert len(rows) == 2
    assert rows[1][0] == late_a["number"] and rows[1][2] == "Ayesha Khan"
    assert rows[1][-1] == "7500.00"
    page.clear_filter.click()
    assert page.overdue_table.rowCount() == 2
    page.search.setText("no matching student")
    QTest.qWait(220)
    assert page.overdue_table.rowCount() == 0
    assert not page.export_overdue_button.isEnabled()


@pytest.mark.parametrize("selector", ["class", "date"])
def test_attendance_cancel_restores_selection_and_discard_never_saves_abandoned_edits(academy, monkeypatch, selector):
    first_class = academy.add_class("Class A", "9 am", "8000")
    second_class = academy.add_class("Class B", "11 am", "8000")
    _enroll(academy, first_class, "First Student")
    _enroll(academy, second_class, "Second Student")
    page = operations.AttendancePage(academy)
    page.refresh()
    initial = page._loaded_key
    page._status_widgets[0].setCurrentText("Late")

    def change_selection():
        if selector == "class":
            page.class_combo.setCurrentIndex(page.class_combo.findData(second_class["id"]))
        else:
            page.date_edit.setDate(QDate.currentDate().addDays(-1))

    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Cancel)
    change_selection()
    assert page._selection_key() == initial and page._loaded_key == initial
    assert page._dirty and page._status_widgets[0].currentText() == "Late"
    assert page.save_button.isEnabled()
    assert academy.attendance_roster(*initial)[0]["status"] == "Not marked"

    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Discard)
    change_selection()
    assert page._selection_key() != initial
    assert page._loaded_key == page._selection_key()
    assert not page._dirty and page._status_widgets[0].currentText() == "Not marked"
    expected_name = "Second Student" if selector == "class" else "First Student"
    assert page.roster_table.item(0, 1).text() == expected_name
    assert academy.attendance_roster(*initial)[0]["status"] == "Not marked"


def test_owner_resets_password_by_selecting_file_in_auth_ui(academy, tmp_path, monkeypatch):
    recovery_file = tmp_path / "owner-reset.nexus-key"
    academy.save_recovery_file(recovery_file, current_password=PASSWORD)
    academy.logout()
    window = auth.AuthWindow(academy)
    window._go(2)
    assert not hasattr(window, "recovery_code")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_: (str(recovery_file), "Academy recovery file (*.nexus-key)"))
    window._choose_recovery_file()
    assert window.recovery_file.text() == str(recovery_file)
    new_password = "New offline owner password 456!"
    window.recovery_password.setText(new_password)
    window.recovery_confirm.setText(new_password)
    window.recovery_button.click()
    assert academy.user is None
    assert window.pages.currentIndex() == 0
    assert not window.recovery_password.text() and not window.recovery_confirm.text()
    assert "Password reset" in window.login_message.text()
    signed_in = []
    window.authenticated.connect(lambda: signed_in.append(True))
    window.login_username.setText("owner")
    window.login_password.setText(new_password)
    window.login_button.click()
    assert signed_in == [True]
    assert academy.user["role"] == "admin"
