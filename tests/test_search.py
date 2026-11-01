"""Local search must open real records without exposing another role's data."""
from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from test_desktop import PASSWORD, academy, qapp, ui_messages
from nexus.ui.search import GlobalSearchDialog
from nexus.ui.shell import MainWindow


def enroll(service, name="Search Student", group=None):
    group = group or service.add_class("Search Class", "Monday 4pm", "5000")
    return service.admit_student(name, "Guardian", "03001234567", group["id"], date.today().isoformat(), "5000", "0", "0", (date.today()+timedelta(days=7)).isoformat())


def search(dialog, query):
    dialog.search.setText(query)
    QTest.qWait(230)
    return [(dialog.results.item(i).text(), tuple(dialog.results.item(i).data(Qt.ItemDataRole.UserRole))) for i in range(dialog.results.count())]


def test_admin_finds_real_student_bill_and_receipt(academy):
    admitted = enroll(academy)
    receipt = academy.record_payment(admitted["challan"]["id"], "2000", "Cash")
    dialog = GlobalSearchDialog(academy)
    results = search(dialog, admitted["student"]["student_number"])
    assert any(route == ("students", admitted["student"]["student_number"]) for _, route in results)
    assert any(route == ("fees", admitted["challan"]["number"]) for _, route in results)
    assert any(route == ("fees", receipt["number"]) for _, route in results)


def test_cashier_student_result_routes_to_allowed_fee_page(academy):
    admitted = enroll(academy)
    academy.create_staff("Cashier", "cashier", PASSWORD, "cashier")
    academy.login("cashier", PASSWORD)
    dialog = GlobalSearchDialog(academy)
    results = search(dialog, admitted["student"]["student_number"])
    assert results
    assert all(page == "fees" for _, (page, _) in results)
    assert any(query == admitted["student"]["student_number"] for _, (_, query) in results)


def test_teacher_sees_only_assigned_classes_and_no_finances(academy):
    teacher = academy.create_staff("Teacher", "teacher", PASSWORD, "teacher")
    own = academy.add_class("Visible Academy Class", "4pm", "5000", teacher["id"])
    hidden = academy.add_class("Hidden Academy Class", "5pm", "8000")
    enroll(academy, "Private Finance Student", own)
    enroll(academy, "Other Private Student", hidden)
    academy.login("teacher", PASSWORD)
    dialog = GlobalSearchDialog(academy)
    results = search(dialog, "Academy Class")
    assert any(text.startswith("Visible Academy Class") for text, _ in results)
    assert not any("Hidden Academy" in text or "Private" in text for text, _ in results)
    assert all(page == "attendance" for _, (page, _) in results)
    assert not search(dialog, "CH-")


def test_search_receipt_switches_to_receipts_and_bill_clears_old_status(academy):
    admitted = enroll(academy)
    receipt = academy.record_payment(admitted["challan"]["id"], "2000", "Cash")
    window = MainWindow(academy)
    page = window.pages["fees"]
    page.status.setCurrentText("Paid")
    window._search_result("fees", admitted["challan"]["number"])
    QTest.qWait(230)
    assert page.status.currentText() == "All"
    assert page.challan_table.rowCount() == 1
    window._search_result("fees", receipt["number"])
    QTest.qWait(230)
    assert page.tabs.currentIndex() == 1
    assert page.payment_table.rowCount() == 1
    assert page.payment_table.item(0, 0).text() == receipt["number"]


def test_selecting_result_emits_once_and_closed_dialog_cancels_search(academy, monkeypatch):
    admitted = enroll(academy)
    dialog = GlobalSearchDialog(academy)
    result = []
    dialog.navigate.connect(lambda page, query: result.append((page, query)))
    search(dialog, admitted["challan"]["number"])
    dialog._activate_current()
    dialog._activate_current()
    assert result == [("fees", admitted["challan"]["number"])]
    canceled = GlobalSearchDialog(academy)
    canceled.search.setText("Search Student")
    assert canceled._timer.isActive()
    canceled.reject()
    monkeypatch.setattr(academy, "list_challans", lambda *_: (_ for _ in ()).throw(AssertionError("Closed search ran")))
    QTest.qWait(230)
    assert not canceled._timer.isActive()
