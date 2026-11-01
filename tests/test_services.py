"""Domain tests use temporary real SQLite databases, never application data."""
from datetime import date, timedelta
from decimal import Decimal
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from nexus.services import AcademyService


PASSWORD = "A secure password 923!"


@pytest.fixture
def academy(tmp_path):
    service = AcademyService(tmp_path / "academy")
    result = service.setup_academy("Intellectual Nexus Academy", "Abbottabad", "03001234567", "Owner", "owner", PASSWORD)
    service._test_recovery = result["recovery_code"]
    yield service
    service.close()


def enroll(service, name="Test Student", fee="8000.00", admission="1000.00", discount="0.00", *, fee_exempt=False):
    classes = service.list_classes()
    cls = classes[0] if classes else service.add_class("FSc • Morning", "Mon–Fri 9am", fee)
    return service.admit_student(name, "Guardian", "03001234567", cls["id"], date.today().isoformat(), fee, admission, discount, (date.today() + timedelta(days=7)).isoformat(), fee_exempt=fee_exempt)


def staff(service, role, username=None):
    return service.create_staff(role.title(), username or role, PASSWORD, role)


def test_setup_once_and_credentials_hashed(academy):
    assert not academy.setup_required()
    owner = academy._db.execute("SELECT * FROM users").fetchone()
    assert owner["password_hash"].startswith("$argon2id$")
    assert owner["recovery_hash"].startswith("$argon2id$")
    assert PASSWORD not in str(tuple(owner))
    assert academy._test_recovery not in str(tuple(owner))
    with pytest.raises(RuntimeError, match="already complete"):
        academy.setup_academy("Other", "", "", "Other", "other", PASSWORD)
    assert academy.get_settings()["academy_name"] == "Intellectual Nexus Academy"


def test_pending_signup_approval_and_persistence(academy):
    academy.signup("Reception User", "reception", PASSWORD)
    pending = next(u for u in academy.list_users() if u["username"] == "reception")
    assert pending["status"] == "pending"
    with pytest.raises(PermissionError, match="approval"):
        academy.login("reception", PASSWORD)
    academy.login("owner", PASSWORD)
    academy.approve_user(pending["id"], "receptionist")
    assert academy.login("RECEPTION", PASSWORD)["role"] == "receptionist"
    assert academy.has_permission("students")
    assert not academy.has_permission("users")
    academy.close()
    restored = AcademyService(academy.data_dir)
    assert restored.user is None
    assert restored.login("reception", PASSWORD)["role"] == "receptionist"
    restored.close()


def test_password_policy_and_unique_username(academy):
    with pytest.raises(ValueError, match="10"):
        academy.signup("User", "user", "short")
    with pytest.raises(ValueError, match="Username"):
        academy.signup("User", "bad user!", PASSWORD)
    academy.signup("User", "user", PASSWORD)
    with pytest.raises(ValueError, match="already registered"):
        academy.signup("User", "USER", PASSWORD)
    with pytest.raises(ValueError, match="already registered"):
        academy.create_staff("Owner impersonation", "owner", PASSWORD, "teacher")


def test_owner_recovery_rotates_code(academy):
    old = academy._test_recovery
    academy.logout()
    new = academy.recover_owner("owner", old, "New password 456!")
    assert old != new
    assert academy.user is None
    with pytest.raises(PermissionError):
        academy.login("owner", PASSWORD)
    assert academy.login("owner", "New password 456!")["role"] == "admin"
    with pytest.raises(PermissionError):
        academy.recover_owner("owner", old, PASSWORD)
    academy.recover_owner("owner", new, PASSWORD)
    assert academy.login("owner", PASSWORD)["role"] == "admin"


def test_failed_logins_lock_account_temporarily(academy):
    for _ in range(5):
        with pytest.raises(PermissionError, match="Incorrect"):
            academy.login("owner", "incorrect")
    with pytest.raises(PermissionError, match="one minute"):
        academy.login("owner", PASSWORD)
    academy._db.execute("UPDATE users SET locked_until='2000-01-01T00:00:00+00:00'")
    academy.login("owner", PASSWORD)
    row = academy._db.execute("SELECT failed_attempts,locked_until FROM users").fetchone()
    assert tuple(row) == (0, None)


def test_owner_cannot_be_demoted_or_deactivated(academy):
    owner = academy.user["id"]
    with pytest.raises(ValueError):
        academy.set_user_active(owner, False)
    with pytest.raises(ValueError):
        academy.approve_user(owner, "teacher")
    with pytest.raises(ValueError):
        academy.create_staff("Other admin", "admin2", PASSWORD, "admin")


def test_session_rechecks_active_status(academy):
    cashier = staff(academy, "cashier")
    other = AcademyService(academy.data_dir)
    try:
        other.login("cashier", PASSWORD)
        academy.set_user_active(cashier["id"], False)
        with pytest.raises(PermissionError, match="no longer active"):
            other.dashboard()
        assert other.user is None
    finally:
        other.close()


def test_public_user_dict_cannot_escalate_role(academy):
    staff(academy, "teacher")
    academy.login("teacher", PASSWORD)
    academy.user["role"] = "admin"
    with pytest.raises(PermissionError):
        academy.list_users()
    assert academy.user["role"] == "teacher"


def test_admission_creates_challan_atomically(academy):
    result = enroll(academy, discount="500")
    student, challan = result["student"], result["challan"]
    assert student["student_number"] == "NX-00001"
    assert challan["total"] == "8500.00"
    assert challan["status"] == "Unpaid"
    assert challan["student_id"] == student["id"]
    assert academy.dashboard()["active_students"] == 1
    assert academy.dashboard()["outstanding"] == "8500.00"
    count = len(academy.list_students())
    with pytest.raises(ValueError, match="Discount"):
        enroll(academy, discount="100000")
    with pytest.raises(ValueError, match="existing class"):
        academy.admit_student("Other", "Guardian", "123", 999, date.today().isoformat(), "1", "0", "0", date.today().isoformat())
    assert len(academy.list_students()) == count


def test_admission_rolls_back_if_initial_challan_insert_fails(academy):
    original = academy._insert_challan
    def fail(*args, **kwargs):
        raise RuntimeError("simulated disk failure")
    academy._insert_challan = fail
    with pytest.raises(RuntimeError, match="disk failure"):
        enroll(academy)
    academy._insert_challan = original
    assert academy.list_students() == []
    assert academy.list_challans() == []


@pytest.mark.parametrize("invalid", ["-1", "NaN", "Infinity", "0.001", True, "100000001"])
def test_invalid_money_rejected(academy, invalid):
    with pytest.raises(ValueError):
        academy.add_class("Invalid fee", "", invalid)
    assert academy.list_classes() == []


def test_duplicate_month_challan_rejected(academy):
    result = enroll(academy)
    with pytest.raises(ValueError, match="already has a challan"):
        academy.create_challan(result["student"]["id"], date.today().strftime("%Y-%m"), "8000", "0", date.today().isoformat())
    assert len(academy.list_challans()) == 1
    next_month = (date.today().replace(day=1) + timedelta(days=32)).strftime("%Y-%m")
    new = academy.create_challan(result["student"]["id"], next_month, "8000", "1000", date.today().isoformat(), "200")
    assert new["total"] == "7200.00"


def test_exact_money_partial_paid_overpay_and_reversal(academy):
    challan = enroll(academy, fee="8000", admission="0")["challan"]
    first = academy.record_payment(challan["id"], "5000.10", "Cash", idempotency_key="unique-payment-1")
    after = academy.challan_details(challan["id"])
    assert after["status"] == "Partially paid"
    assert after["balance"] == "2999.90"
    with pytest.raises(ValueError, match="exceeds"):
        academy.record_payment(challan["id"], "3000", "Cash")
    second = academy.record_payment(challan["id"], "2999.90", "Bank transfer", "TXN-42")
    assert academy.challan_details(challan["id"])["status"] == "Paid"
    assert academy.dashboard()["month_collected"] == "8000.00"
    assert academy.dashboard()["outstanding"] == "0.00"
    academy.reverse_payment(first["id"], "Incorrect counter entry")
    after = academy.challan_details(challan["id"])
    assert after["status"] == "Partially paid"
    assert after["balance"] == "5000.10"
    assert academy.dashboard()["month_collected"] == "2999.90"
    assert academy.list_payments()[1]["reversed"] is True
    with pytest.raises(ValueError, match="already been reversed"):
        academy.reverse_payment(first["id"], "Again")
    assert second["number"] != first["number"]
    assert any(a["action"] == "Payment reversed" and "Incorrect counter entry" in a["details"] for a in academy.list_audit())


def test_payment_idempotence_and_mismatch(academy):
    challan = enroll(academy)["challan"]
    args = (challan["id"], "1000.20", "Cash")
    first = academy.record_payment(*args, idempotency_key="request-1")
    repeated = academy.record_payment(*args, idempotency_key="request-1")
    assert repeated == first
    assert len(academy.list_payments()) == 1
    assert academy.challan_details(challan["id"])["paid"] == "1000.20"
    with pytest.raises(ValueError, match="different details"):
        academy.record_payment(challan["id"], "2000", "Cash", idempotency_key="request-1")
    assert len(academy.list_payments()) == 1


def test_concurrent_payment_cannot_overpay(academy):
    challan_id = enroll(academy, fee="100", admission="0")["challan"]["id"]
    def pay(_):
        svc = AcademyService(academy.data_dir)
        try:
            svc.login("owner", PASSWORD)
            try:
                return svc.record_payment(challan_id, "100", "Cash")["id"]
            except ValueError:
                return None
        finally:
            svc.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(pay, range(2)))
    assert sum(r is not None for r in results) == 1
    assert academy.challan_details(challan_id)["paid"] == "100.00"
    assert len(academy.list_payments()) == 1


def test_free_challan_has_no_payment_due_and_rejects_payment(academy):
    challan = enroll(academy, fee="500", admission="0", discount="500", fee_exempt=True)["challan"]
    assert challan["status"] == "No payment due"
    with pytest.raises(ValueError, match="exceeds"):
        academy.record_payment(challan["id"], "1", "Cash")


def test_receptionist_cannot_receive_payments_or_read_reports(academy):
    staff(academy, "receptionist")
    academy.login("receptionist", PASSWORD)
    challan = enroll(academy)["challan"]
    assert academy.list_challans()[0]["id"] == challan["id"]
    for action in [lambda: academy.record_payment(challan["id"], "1", "Cash"), academy.reports, academy.list_users, lambda: academy.backup(academy.data_dir / "secret.sqlite3")]:
        with pytest.raises(PermissionError):
            action()


def test_cashier_can_collect_but_not_admit_or_reverse(academy):
    challan = enroll(academy)["challan"]
    staff(academy, "cashier")
    academy.login("cashier", PASSWORD)
    payment = academy.record_payment(challan["id"], "100", "Cash")
    assert academy.reports()["month_collected"] == "100.00"
    with pytest.raises(PermissionError):
        enroll(academy)
    with pytest.raises(PermissionError):
        academy.reverse_payment(payment["id"], "No access")


def test_teacher_classes_students_attendance_are_scoped(academy):
    teacher = staff(academy, "teacher")
    other = academy.create_staff("Other Teacher", "otherteacher", PASSWORD, "teacher")
    cls = academy.add_class("Own class", "9am", "100", teacher["id"])
    another = academy.add_class("Other class", "10am", "100", other["id"])
    student = academy.admit_student("Assigned", "Parent", "123", cls["id"], date.today().isoformat(), "100", "0", "0", date.today().isoformat())["student"]
    foreign = academy.admit_student("Not assigned", "Parent", "123", another["id"], date.today().isoformat(), "100", "0", "0", date.today().isoformat())["student"]
    academy.login("teacher", PASSWORD)
    assert [c["id"] for c in academy.list_classes()] == [cls["id"]]
    assert [s["id"] for s in academy.list_students()] == [student["id"]]
    roster = academy.attendance_roster(cls["id"], date.today().isoformat())
    assert roster[0]["status"] == "Not marked"
    academy.save_attendance(cls["id"], date.today().isoformat(), [{"student_id": student["id"], "status": "Present"}])
    assert academy.attendance_roster(cls["id"], date.today().isoformat())[0]["status"] == "Present"
    with pytest.raises(PermissionError):
        academy.attendance_roster(another["id"], date.today().isoformat())
    with pytest.raises(ValueError):
        academy.save_attendance(cls["id"], date.today().isoformat(), [{"student_id": foreign["id"], "status": "Present"}])
    with pytest.raises(PermissionError):
        academy.list_challans()
    assert academy.dashboard()["month_collected"] == "0.00"
    assert academy.dashboard()["active_students"] == 1


def test_invalid_attendance_is_atomic_and_not_marked_clears(academy):
    result = enroll(academy)
    student_id, class_id = result["student"]["id"], result["student"]["class_id"]
    day = date.today().isoformat()
    academy.save_attendance(class_id, day, [{"student_id": student_id, "status": "Present"}])
    with pytest.raises(ValueError):
        academy.save_attendance(class_id, day, [{"student_id": student_id, "status": "Absent"}, {"student_id": 999, "status": "Late"}])
    assert academy.attendance_roster(class_id, day)[0]["status"] == "Present"
    academy.save_attendance(class_id, day, [{"student_id": student_id, "status": "Not marked"}])
    assert academy.attendance_roster(class_id, day)[0]["status"] == "Not marked"


def test_reports_exclude_reversals_and_only_overdue_defaulters(academy):
    result = enroll(academy)
    old_month = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    late = academy.create_challan(result["student"]["id"], old_month, "2500", "0", (date.today() - timedelta(days=5)).isoformat())
    receipt = academy.record_payment(late["id"], "500", "Cash")
    report = academy.reports()
    assert report["overdue_count"] == 1
    assert report["defaulters"][0]["id"] == late["id"]
    assert report["defaulters"][0]["balance"] == "2000.00"
    assert report["monthly_collection"][0]["amount"] == "500.00"
    academy.reverse_payment(receipt["id"], "Wrong entry")
    assert academy.reports()["monthly_collection"] == []


def test_backup_restore_validates_and_preserves_safety_copy(academy, tmp_path):
    first = enroll(academy)
    academy.record_payment(first["challan"]["id"], "500", "Cash")
    backup = tmp_path / "academy-backup.sqlite3"
    academy.backup(backup)
    second = enroll(academy, name="Second Student")
    assert len(academy.list_students()) == 2
    academy.restore(backup)
    assert academy.user is None
    with pytest.raises(PermissionError):
        academy.dashboard()
    academy.login("owner", PASSWORD)
    assert len(academy.list_students()) == 1
    assert academy.challan_details(first["challan"]["id"])["paid"] == "500.00"
    safety = list((academy.data_dir / "pre_restore_backups").glob("*.sqlite3"))
    assert len(safety) == 1
    with sqlite3.connect(safety[0]) as db:
        assert db.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 2
    assert academy.list_audit()[0]["action"] == "Signed in"
    assert any(a["action"] == "Database restored" for a in academy.list_audit())


def test_corrupt_restore_does_not_damage_active_data(academy, tmp_path):
    enroll(academy)
    bad = tmp_path / "corrupt.sqlite3"
    bad.write_bytes(b"not a database")
    with pytest.raises(ValueError, match="not a valid"):
        academy.restore(bad)
    assert academy.user is not None
    assert len(academy.list_students()) == 1
    wrong = tmp_path / "unrelated.sqlite3"
    with sqlite3.connect(wrong) as db:
        db.execute("CREATE TABLE irrelevant (x)")
    with pytest.raises(ValueError):
        academy.restore(wrong)
    assert len(academy.list_students()) == 1


def test_backup_refuses_active_database_and_existing_file(academy, tmp_path):
    with pytest.raises(ValueError, match="different"):
        academy.backup(academy.db_path)
    existing = tmp_path / "important.txt"
    existing.write_text("Keep this")
    with pytest.raises(ValueError, match="already exists"):
        academy.backup(existing)
    assert existing.read_text() == "Keep this"


def test_changed_password_and_staff_reset(academy):
    user = staff(academy, "teacher")
    academy.reset_password(user["id"], "Reset password 123!")
    academy.login("teacher", "Reset password 123!")
    with pytest.raises(PermissionError):
        academy.change_password("Wrong password", "Final password 123!")
    academy.change_password("Reset password 123!", "Final password 123!")
    assert academy.login("teacher", "Final password 123!")["username"] == "teacher"


def test_unauthenticated_access_denied(tmp_path):
    svc = AcademyService(tmp_path / "empty")
    try:
        assert svc.setup_required()
        assert svc.get_settings()["currency"] == "PKR"
        for action in [svc.list_classes, svc.list_students, svc.list_users, svc.dashboard, svc.reports, svc.list_audit]:
            with pytest.raises(PermissionError):
                action()
    finally:
        svc.close()


def test_large_valid_fee_total_does_not_break_summary(academy):
    challan = enroll(academy, fee="100000000", admission="100000000")["challan"]
    assert challan["total"] == "200000000.00"
    assert academy.dashboard()["outstanding"] == "200000000.00"
    assert academy.reports()["outstanding"] == "200000000.00"


def test_update_class_assigns_teacher_and_preserves_default_fees(academy):
    cls = academy.add_class("Before", "9am", "8000")
    teacher = staff(academy, "teacher")
    changed = academy.update_class(cls["id"], "After", "11am", "8500", teacher["id"])
    assert changed["teacher_id"] == teacher["id"]
    assert changed["name"] == "After"
    assert changed["monthly_fee"] == "8500.00"
    with pytest.raises(ValueError, match="active teacher"):
        academy.update_class(cls["id"], "After", "", "0", academy.user["id"])
    academy.login("teacher", PASSWORD)
    assert academy.list_classes()[0]["id"] == cls["id"]
    with pytest.raises(PermissionError):
        academy.update_class(cls["id"], "Escalate", "", "0")


def test_update_student_changes_profile_not_historic_fees(academy):
    result = enroll(academy)
    student, challan = result["student"], result["challan"]
    payment = academy.record_payment(challan["id"], "500", "Cash")
    attendance = [{"student_id": student["id"], "status": "Present"}]
    academy.save_attendance(student["class_id"], date.today().isoformat(), attendance)
    changed = academy.update_student(student["id"], "Corrected name", "New Guardian", "03000000000", student["class_id"], "9500", "Address", "Notes", "inactive")
    assert changed["student_number"] == student["student_number"]
    assert changed["full_name"] == "Corrected name"
    assert changed["monthly_fee"] == "9500.00"
    assert changed["status"] == "inactive"
    assert academy.challan_details(challan["id"])["total"] == "9000.00"
    assert academy.challan_details(challan["id"])["paid"] == "500.00"
    assert academy.list_payments()[0]["id"] == payment["id"]
    assert academy._db.execute("SELECT status FROM attendance WHERE student_id=?", (student["id"],)).fetchone()[0] == "Present"
    with pytest.raises(ValueError, match="active student"):
        academy.create_challan(student["id"], "2099-01", "1", "0", date.today().isoformat())
    assert academy.dashboard()["active_students"] == 0


@pytest.mark.parametrize("field,value", [("password_hash", "$argon2id$invalid"), ("recovery_hash", "invalid"), ("password_hash", "$argon2id$v=19$m=999999999,t=3,p=4$1234567890123456789012$1234567890123456789012345678901234567890123")])
def test_restore_rejects_invalid_or_excessive_hashes(academy, tmp_path, field, value):
    target = tmp_path / "bad-hash.sqlite3"
    academy.backup(target)
    with sqlite3.connect(target) as db:
        db.execute(f"UPDATE users SET {field}=? WHERE is_owner=1", (value,))
    with pytest.raises(ValueError, match="credentials"):
        academy.restore(target)
    assert academy.user is not None
    assert academy.login("owner", PASSWORD)["role"] == "admin"


def test_restore_rejects_schema_with_removed_constraints(academy, tmp_path):
    from nexus.services import SCHEMA
    backup = tmp_path / "changed-schema.sqlite3"
    with sqlite3.connect(backup) as db:
        db.executescript(SCHEMA.replace("amount INTEGER NOT NULL CHECK(amount>0)", "amount INTEGER NOT NULL"))
        db.execute("PRAGMA user_version=1")
    with pytest.raises(ValueError, match="structure or constraints"):
        academy.restore(backup)
    assert academy.user is not None


def test_collection_month_uses_computer_local_timezone(academy, monkeypatch):
    import os
    import time
    from datetime import datetime, time as clock_time, timezone
    if not hasattr(time, "tzset"):
        pytest.skip("POSIX timezone switch is unavailable on this platform")
    previous = os.environ.get("TZ")
    try:
        monkeypatch.setenv("TZ", "Asia/Karachi")
        time.tzset()
        challan = enroll(academy)["challan"]
        receipt = academy.record_payment(challan["id"], "500", "Cash")
        local_first = datetime.combine(date.today().replace(day=1), clock_time(0, 30), tzinfo=timezone(timedelta(hours=5)))
        utc_time = local_first.astimezone(timezone.utc).isoformat()
        academy._db.execute("UPDATE payments SET paid_on=? WHERE id=?", (utc_time, receipt["id"]))
        assert academy.reports()["month_collected"] == "500.00"
        assert academy.reports()["monthly_collection"][0]["month"] == local_first.strftime("%Y-%m")
    finally:
        if previous is None:
            monkeypatch.delenv("TZ", raising=False)
        else:
            monkeypatch.setenv("TZ", previous)
        time.tzset()


def test_zero_fee_admission_requires_explicit_exemption_and_never_says_paid(academy):
    with pytest.raises(ValueError, match="explicitly select fee-exempt"):
        enroll(academy, fee="0", admission="0")
    assert academy.list_students() == []
    assert academy.list_challans() == []
    result = enroll(academy, fee="0", admission="0", fee_exempt=True)
    assert result["challan"]["status"] == "No payment due"
    assert result["challan"]["payments"] == []
    assert academy.list_challans(status="Paid") == []
    assert academy.list_challans(status="Unpaid") == []
    assert academy.list_challans(status="No payment due")[0]["id"] == result["challan"]["id"]
    assert academy.dashboard()["outstanding"] == "0.00"
    assert academy.dashboard()["month_collected"] == "0.00"


def test_fully_discounted_new_challan_requires_explicit_exemption(academy):
    result = enroll(academy)
    future = (date.today().replace(day=1) + timedelta(days=32)).strftime("%Y-%m")
    with pytest.raises(ValueError, match="fee-exempt"):
        academy.create_challan(result["student"]["id"], future, "8000", "8000", date.today().isoformat())
    assert len(academy.list_challans()) == 1
    exempt = academy.create_challan(result["student"]["id"], future, "8000", "8000", date.today().isoformat(), fee_exempt=True)
    assert exempt["status"] == "No payment due"
    assert exempt["total"] == "0.00"


def test_existing_zero_bill_is_preserved_and_can_be_explicitly_amended(academy):
    result = enroll(academy)
    student, challan = result["student"], result["challan"]
    # Reproduce a pre-fix database: no new schema flag/migration is required.
    academy._db.execute("UPDATE students SET monthly_fee=0 WHERE id=?", (student["id"],))
    academy._db.execute("UPDATE challans SET tuition=0,other=0,discount=0,total=0 WHERE id=?", (challan["id"],))
    schema_before = list(academy._db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name"))
    recovery_hash = academy._db.execute("SELECT recovery_hash FROM users WHERE is_owner=1").fetchone()[0]
    academy.close()
    reopened = AcademyService(academy.data_dir)
    try:
        reopened.login("owner", PASSWORD)
        assert reopened.challan_details(challan["id"])["status"] == "No payment due"
        reopened.update_student(student["id"], student["full_name"], student["guardian_name"], student["phone"], student["class_id"], "5000")
        assert reopened.challan_details(challan["id"])["total"] == "0.00"
        assert reopened.list_students()[0]["monthly_fee"] == "5000.00"
        fixed = reopened.amend_challan(challan["id"], "5000", "1000", "500", date.today().isoformat(), "Correct accidental zero fee from admission")
        assert fixed["id"] == challan["id"]
        assert fixed["number"] == challan["number"]
        assert fixed["total"] == "5500.00"
        assert fixed["status"] == "Unpaid"
        assert fixed["paid"] == "0.00"
        assert reopened.dashboard()["outstanding"] == "5500.00"
        assert reopened._db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert list(reopened._db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name")) == schema_before
        assert reopened._db.execute("SELECT recovery_hash FROM users WHERE is_owner=1").fetchone()[0] == recovery_hash
        audit = next(a for a in reopened.list_audit() if a["action"] == "Challan amended")
        assert "before: tuition 0.00" in audit["details"]
        assert "after: tuition 5000.00" in audit["details"]
        assert "total 5500.00" in audit["details"]
        assert "Correct accidental zero fee" in audit["details"]
    finally:
        reopened.close()


@pytest.mark.parametrize("reverse", [False, True])
def test_amendment_rejects_any_payment_history_including_reversals(academy, reverse):
    challan = enroll(academy)["challan"]
    payment = academy.record_payment(challan["id"], "100", "Cash")
    if reverse:
        academy.reverse_payment(payment["id"], "Counter correction")
    before = academy.challan_details(challan["id"])
    with pytest.raises(ValueError, match="payment history"):
        academy.amend_challan(challan["id"], "15000", "0", "0", date.today().isoformat(), "Not permitted")
    assert academy.challan_details(challan["id"]) == before


def test_amendment_requires_reason_valid_amounts_and_explicit_zero_intent(academy):
    challan = enroll(academy)["challan"]
    before = academy.challan_details(challan["id"])
    with pytest.raises(ValueError, match="reason"):
        academy.amend_challan(challan["id"], "5000", "0", "0", date.today().isoformat(), "")
    with pytest.raises(ValueError, match="Discount"):
        academy.amend_challan(challan["id"], "1", "0", "2", date.today().isoformat(), "Invalid discount")
    with pytest.raises(ValueError, match="fee-exempt"):
        academy.amend_challan(challan["id"], "0", "0", "0", date.today().isoformat(), "Waive fees")
    assert academy.challan_details(challan["id"]) == before
    waived = academy.amend_challan(challan["id"], "0", "0", "0", date.today().isoformat(), "Full scholarship approved", fee_exempt=True)
    assert waived["status"] == "No payment due"
    assert waived["total"] == "0.00"


@pytest.mark.parametrize("role", ["receptionist", "cashier"])
def test_amendment_permitted_for_billing_staff(academy, role):
    challan = enroll(academy)["challan"]
    staff(academy, role)
    academy.login(role, PASSWORD)
    updated = academy.amend_challan(challan["id"], "7000", "500", "1000", date.today().isoformat(), "Agreed fee package")
    assert updated["total"] == "6500.00"
    assert updated["status"] == "Unpaid"


def test_teacher_cannot_amend_bills(academy):
    challan = enroll(academy)["challan"]
    staff(academy, "teacher")
    academy.login("teacher", PASSWORD)
    with pytest.raises(PermissionError):
        academy.amend_challan(challan["id"], "1", "0", "0", date.today().isoformat(), "Forbidden")


def _owner_recovery_hash(academy):
    return academy._db.execute("SELECT recovery_hash FROM users WHERE is_owner=1").fetchone()[0]


def test_initial_recovery_file_is_private_and_reusable_without_code_rotation(academy, tmp_path):
    import json
    import os
    import stat
    key = tmp_path / "owner.nexus-key"
    original_hash = _owner_recovery_hash(academy)
    result = academy.save_recovery_file(key, recovery_code=academy._test_recovery)
    assert result == str(key)
    payload = json.loads(key.read_text())
    assert payload == {"format": "nexus-recovery-v1", "username": "owner", "recovery_code": academy._test_recovery}
    assert _owner_recovery_hash(academy) == original_hash
    if os.name != "nt":
        assert stat.S_IMODE(key.stat().st_mode) == 0o600
    assert academy._test_recovery not in str(academy.list_audit())
    academy.logout()
    academy.reset_password_with_file(key, "Replacement password 123!")
    assert academy.user is None
    academy.login("owner", "Replacement password 123!")
    academy.logout()
    academy.reset_password_with_file(key, "Another replacement 456!")
    assert academy.login("owner", "Another replacement 456!")["role"] == "admin"
    assert key.read_text() == __import__("json").dumps(payload, ensure_ascii=True, indent=2) + "\n"
    assert _owner_recovery_hash(academy) == original_hash


def test_current_password_export_rotates_key_only_after_success(academy, tmp_path):
    old = tmp_path / "old.nexus-key"
    academy.save_recovery_file(old, recovery_code=academy._test_recovery)
    original_hash = _owner_recovery_hash(academy)
    replacement = tmp_path / "replacement.nexus-key"
    academy.save_recovery_file(replacement, current_password=PASSWORD)
    assert _owner_recovery_hash(academy) != original_hash
    assert old.exists() and replacement.exists()
    academy.logout()
    with pytest.raises(PermissionError, match="does not match"):
        academy.reset_password_with_file(old, "Changed password 123!")
    academy.reset_password_with_file(replacement, "Changed password 123!")
    assert academy.login("owner", "Changed password 123!")["role"] == "admin"


def test_recovery_export_never_overwrites_or_rotates_on_existing_path(academy, tmp_path):
    target = tmp_path / "important.nexus-key"
    target.write_text("Keep this user file")
    original = _owner_recovery_hash(academy)
    with pytest.raises(ValueError, match="already exists"):
        academy.save_recovery_file(target, current_password=PASSWORD)
    assert target.read_text() == "Keep this user file"
    assert _owner_recovery_hash(academy) == original
    with pytest.raises(ValueError, match="database"):
        academy.save_recovery_file(academy.db_path, current_password=PASSWORD)
    assert _owner_recovery_hash(academy) == original


def test_recovery_export_rejects_dangling_symlink(academy, tmp_path):
    target = tmp_path / "dangling.nexus-key"
    try:
        target.symlink_to(tmp_path / "missing-key")
    except OSError:
        pytest.skip("Symlink creation is unavailable")
    original = _owner_recovery_hash(academy)
    with pytest.raises(ValueError, match="already exists"):
        academy.save_recovery_file(target, current_password=PASSWORD)
    assert target.is_symlink()
    assert not (tmp_path / "missing-key").exists()
    assert _owner_recovery_hash(academy) == original


def test_recovery_export_write_failure_preserves_old_recovery_access(academy, tmp_path, monkeypatch):
    original = _owner_recovery_hash(academy)
    def fail(*_):
        raise OSError("Simulated unavailable drive")
    monkeypatch.setattr(academy, "_write_recovery_file", fail)
    target = tmp_path / "failed.nexus-key"
    with pytest.raises(OSError, match="unavailable drive"):
        academy.save_recovery_file(target, current_password=PASSWORD)
    assert not target.exists()
    assert _owner_recovery_hash(academy) == original
    academy.recover_owner("owner", academy._test_recovery, "Changed password 123!")
    assert academy.login("owner", "Changed password 123!")["role"] == "admin"


def test_recovery_export_database_failure_removes_unactivated_file(academy, tmp_path, monkeypatch):
    original = _owner_recovery_hash(academy)
    original_audit = academy._audit
    def fail(action, *args, **kwargs):
        if action == "Owner recovery file saved":
            raise RuntimeError("Simulated commit failure")
        return original_audit(action, *args, **kwargs)
    monkeypatch.setattr(academy, "_audit", fail)
    target = tmp_path / "failed.nexus-key"
    with pytest.raises(RuntimeError, match="commit failure"):
        academy.save_recovery_file(target, current_password=PASSWORD)
    assert not target.exists()
    assert list(tmp_path.glob(".nexus-key-*.tmp")) == []
    assert _owner_recovery_hash(academy) == original
    assert academy.login("owner", PASSWORD)["role"] == "admin"


def test_recovery_export_fsync_failure_leaves_no_file_or_rotated_hash(academy, tmp_path, monkeypatch):
    import os
    original = _owner_recovery_hash(academy)
    def fail(_):
        raise OSError("Simulated fsync failure")
    monkeypatch.setattr(os, "fsync", fail)
    target = tmp_path / "failed.nexus-key"
    with pytest.raises(OSError, match="fsync failure"):
        academy.save_recovery_file(target, current_password=PASSWORD)
    assert not target.exists()
    assert list(tmp_path.glob(".nexus-key-*.tmp")) == []
    assert _owner_recovery_hash(academy) == original


def test_staff_and_signed_out_sessions_cannot_export_owner_file(academy, tmp_path):
    staff(academy, "teacher")
    academy.login("teacher", PASSWORD)
    with pytest.raises(PermissionError):
        academy.save_recovery_file(tmp_path / "forbidden.nexus-key", current_password=PASSWORD)
    academy.logout()
    with pytest.raises(PermissionError):
        academy.save_recovery_file(tmp_path / "forbidden.nexus-key", recovery_code=academy._test_recovery)
    assert not (tmp_path / "forbidden.nexus-key").exists()


def test_wrong_owner_password_export_is_throttled_and_does_not_rotate(academy, tmp_path):
    original = _owner_recovery_hash(academy)
    for _ in range(5):
        with pytest.raises(PermissionError, match="incorrect"):
            academy.save_recovery_file(tmp_path / "wrong.nexus-key", current_password="Wrong password 123!")
    with pytest.raises(PermissionError, match="one minute"):
        academy.save_recovery_file(tmp_path / "wrong.nexus-key", current_password=PASSWORD)
    assert not (tmp_path / "wrong.nexus-key").exists()
    assert _owner_recovery_hash(academy) == original


def test_wrong_recovery_file_is_throttled_and_valid_key_cannot_bypass_lock(academy, tmp_path):
    import json
    key = tmp_path / "valid.nexus-key"
    academy.save_recovery_file(key, recovery_code=academy._test_recovery)
    wrong = tmp_path / "wrong.nexus-key"
    wrong.write_text(json.dumps({"format": "nexus-recovery-v1", "username": "owner", "recovery_code": "AAAA-AAAA-AAAA-AAAA-AAAA-AAAA-AAAA-AAAA"}))
    original_password = academy._db.execute("SELECT password_hash FROM users WHERE is_owner=1").fetchone()[0]
    academy.logout()
    for _ in range(5):
        with pytest.raises(PermissionError, match="does not match"):
            academy.reset_password_with_file(wrong, "Changed password 123!")
    with pytest.raises(PermissionError, match="one minute"):
        academy.reset_password_with_file(key, "Changed password 123!")
    assert academy._db.execute("SELECT password_hash FROM users WHERE is_owner=1").fetchone()[0] == original_password
    academy._db.execute("UPDATE users SET locked_until='2000-01-01T00:00:00+00:00'")
    academy.reset_password_with_file(key, "Changed password 123!")
    assert academy.login("owner", "Changed password 123!")["role"] == "admin"


def test_recovery_key_for_another_academy_does_not_reset_this_owner(academy, tmp_path):
    other = AcademyService(tmp_path / "other-academy")
    try:
        result = other.setup_academy("Other academy", "", "", "Other owner", "owner", PASSWORD)
        key = tmp_path / "other.nexus-key"
        other.save_recovery_file(key, recovery_code=result["recovery_code"])
        with pytest.raises(PermissionError, match="does not match"):
            academy.reset_password_with_file(key, "Wrong academy password 123!")
        assert academy.login("owner", PASSWORD)["role"] == "admin"
    finally:
        other.close()


@pytest.mark.parametrize("content", [b"not JSON", b"[]", b"{}", b"\xff\x00", b"x" * 8193,
    b'{"format":"nexus-recovery-v0","username":"owner","recovery_code":"invalid"}',
    b'{"format":"nexus-recovery-v1","username":"owner","recovery_code":"invalid"}',
    b'{"format":"nexus-recovery-v1","format":"nexus-recovery-v1","username":"owner","recovery_code":"invalid"}'])
def test_malformed_recovery_files_fail_without_password_change(academy, tmp_path, content):
    target = tmp_path / "bad.nexus-key"
    target.write_bytes(content)
    original = academy._db.execute("SELECT password_hash FROM users WHERE is_owner=1").fetchone()[0]
    with pytest.raises(ValueError, match="valid academy recovery file"):
        academy.reset_password_with_file(target, "Changed password 123!")
    assert academy._db.execute("SELECT password_hash FROM users WHERE is_owner=1").fetchone()[0] == original
    assert academy.login("owner", PASSWORD)["role"] == "admin"


def test_recovery_files_require_password_policy_before_reset(academy, tmp_path):
    key = tmp_path / "valid.nexus-key"
    academy.save_recovery_file(key, recovery_code=academy._test_recovery)
    with pytest.raises(ValueError, match="10"):
        academy.reset_password_with_file(key, "short")
    assert academy.login("owner", PASSWORD)["role"] == "admin"


def test_atomic_recovery_install_refuses_a_destination_created_during_save(academy, tmp_path, monkeypatch):
    import os
    if os.name == "nt":
        pytest.skip("POSIX atomic link installation branch")
    target = tmp_path / "race.nexus-key"
    original = _owner_recovery_hash(academy)
    real_link = os.link
    def race(source, destination):
        target.write_text("Another process created this file")
        return real_link(source, destination)
    monkeypatch.setattr(os, "link", race)
    with pytest.raises(FileExistsError):
        academy.save_recovery_file(target, current_password=PASSWORD)
    assert target.read_text() == "Another process created this file"
    assert _owner_recovery_hash(academy) == original
    assert list(tmp_path.glob(".nexus-key-*.tmp")) == []


def test_deeply_nested_recovery_json_is_rejected_as_invalid_file(academy, tmp_path):
    target = tmp_path / "nested.nexus-key"
    target.write_text("[" * 2000 + "0" + "]" * 2000)
    with pytest.raises(ValueError, match="valid academy recovery file"):
        academy.reset_password_with_file(target, "Changed password 123!")
    assert academy.login("owner", PASSWORD)["role"] == "admin"
