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


def enroll(service, name="Test Student", fee="8000.00", admission="1000.00", discount="0.00"):
    classes = service.list_classes()
    cls = classes[0] if classes else service.add_class("FSc • Morning", "Mon–Fri 9am", fee)
    return service.admit_student(name, "Guardian", "03001234567", cls["id"], date.today().isoformat(), fee, admission, discount, (date.today() + timedelta(days=7)).isoformat())


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


def test_free_challan_is_paid_and_rejects_payment(academy):
    challan = enroll(academy, fee="500", admission="0", discount="500")["challan"]
    assert challan["status"] == "Paid"
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
