"""Offline academy domain service.

All writes are transactional; money is stored as integer paisa. UI code never
needs direct database access. Database files contain personal/financial data:
keep the computer account and external backups protected.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import os
import json
import stat
import tempfile
from pathlib import Path
import re
import secrets
import sqlite3

from argon2 import PasswordHasher, extract_parameters
from argon2.exceptions import InvalidHashError, VerificationError


SCHEMA_VERSION = 1
STAFF_ROLES = {"receptionist", "cashier", "teacher"}
PERMISSIONS = {
    "admin": {"dashboard", "students", "fees", "attendance", "reports", "users", "settings"},
    "receptionist": {"dashboard", "students", "fees"},
    "cashier": {"dashboard", "fees", "reports"},
    "teacher": {"dashboard", "attendance"},
}
ATTENDANCE_STATUSES = {"Present", "Absent", "Late", "Excused", "Not marked"}
PAYMENT_METHODS = {"Cash", "Bank transfer", "Card", "Other"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
 key TEXT PRIMARY KEY, value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 full_name TEXT NOT NULL, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
 password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('admin','receptionist','cashier','teacher')),
 status TEXT NOT NULL CHECK(status IN ('pending','active','inactive')),
 is_owner INTEGER NOT NULL DEFAULT 0 CHECK(is_owner IN (0,1)),
 recovery_hash TEXT, failed_attempts INTEGER NOT NULL DEFAULT 0,
 locked_until TEXT, created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_owner ON users(is_owner) WHERE is_owner=1;
CREATE TABLE IF NOT EXISTS classes (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT NOT NULL UNIQUE COLLATE NOCASE, schedule TEXT NOT NULL DEFAULT '',
 monthly_fee INTEGER NOT NULL CHECK(monthly_fee>=0),
 teacher_id INTEGER REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS students (
 id INTEGER PRIMARY KEY AUTOINCREMENT, student_number TEXT UNIQUE,
 full_name TEXT NOT NULL, guardian_name TEXT NOT NULL, phone TEXT NOT NULL,
 class_id INTEGER NOT NULL REFERENCES classes(id), admission_date TEXT NOT NULL,
 monthly_fee INTEGER NOT NULL CHECK(monthly_fee>=0),
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','inactive')),
 address TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS challans (
 id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT UNIQUE,
 student_id INTEGER NOT NULL REFERENCES students(id), period TEXT NOT NULL,
 issued_on TEXT NOT NULL, due_date TEXT NOT NULL,
 tuition INTEGER NOT NULL CHECK(tuition>=0), other INTEGER NOT NULL CHECK(other>=0),
 discount INTEGER NOT NULL CHECK(discount>=0), total INTEGER NOT NULL CHECK(total>=0),
 created_by INTEGER NOT NULL REFERENCES users(id),
 UNIQUE(student_id,period), CHECK(total=tuition+other-discount)
);
CREATE TABLE IF NOT EXISTS payments (
 id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT UNIQUE,
 challan_id INTEGER NOT NULL REFERENCES challans(id),
 amount INTEGER NOT NULL CHECK(amount>0), method TEXT NOT NULL,
 reference TEXT NOT NULL DEFAULT '', paid_on TEXT NOT NULL,
 received_by INTEGER NOT NULL REFERENCES users(id), idempotency_key TEXT UNIQUE,
 reversed INTEGER NOT NULL DEFAULT 0 CHECK(reversed IN (0,1)),
 reversed_at TEXT, reversed_by INTEGER REFERENCES users(id), reversal_reason TEXT
);
CREATE TABLE IF NOT EXISTS attendance (
 student_id INTEGER NOT NULL REFERENCES students(id), day TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('Present','Absent','Late','Excused','Not marked')),
 marked_by INTEGER NOT NULL REFERENCES users(id), updated_at TEXT NOT NULL,
 PRIMARY KEY(student_id,day)
);
CREATE TABLE IF NOT EXISTS audit_log (
 id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
 actor_id INTEGER REFERENCES users(id), actor TEXT NOT NULL,
 action TEXT NOT NULL, details TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS student_class ON students(class_id);
CREATE INDEX IF NOT EXISTS payment_challan ON payments(challan_id);
CREATE INDEX IF NOT EXISTS challan_due ON challans(due_date);
"""


def default_data_dir() -> Path:
    """Follow OS conventions without creating application data in the checkout."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    elif __import__("sys").platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return base / "IntellectualNexusAcademy"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _money(paisa: int) -> str:
    return f"{Decimal(paisa) / 100:.2f}"


def _amount(value, label="Amount", positive=False) -> int:
    try:
        if isinstance(value, bool):
            raise ValueError
        amount = Decimal(str(value))
        if not amount.is_finite() or amount != amount.quantize(Decimal("0.01")):
            raise ValueError
        paisa = int(amount * 100)
        if paisa < 0 or (positive and paisa == 0) or paisa > 10_000_000_000:
            raise ValueError
        return paisa
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        raise ValueError(f"{label} must be {'greater than zero' if positive else 'zero or greater'}, with at most two decimal places (maximum Rs 100,000,000).") from None


def _text(value, label, maximum=200, required=True) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text.")
    value = value.strip()
    if (required and not value) or len(value) > maximum or "\x00" in value:
        raise ValueError(f"{label} is required and must be at most {maximum} characters." if required else f"{label} must be at most {maximum} characters.")
    return value


def _day(value, label="Date") -> str:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError
        return value
    except (ValueError, TypeError):
        raise ValueError(f"{label} must use YYYY-MM-DD.") from None


def _username(value) -> str:
    value = _text(value, "Username", 40).lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,39}", value):
        raise ValueError("Username must be 3–40 letters/numbers, dots, underscores or hyphens.")
    return value


def _password(value) -> str:
    if not isinstance(value, str) or len(value) < 10 or len(value) > 1024 or not value.strip():
        raise ValueError("Use a password of 10–1,024 characters.")
    return value


def _identifier(value) -> int:
    if isinstance(value, bool):
        raise ValueError("Invalid record selection.")
    try:
        result = int(value)
        if str(result) != str(value) or result < 1:
            raise ValueError
        return result
    except (ValueError, TypeError):
        raise ValueError("Select a valid record.") from None


class AcademyService:
    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db_path = self.data_dir / "academy.sqlite3"
        self.user = None
        self._session_id = None
        self._hasher = PasswordHasher()
        self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(24))
        self._connect()
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            self.close()
            raise RuntimeError("This database belongs to a newer app version. Install the matching version before opening it.")
        self._db.executescript(SCHEMA)
        self._db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        try:
            self.db_path.chmod(0o600)
        except OSError:
            pass

    def _connect(self):
        self._db = sqlite3.connect(self.db_path, isolation_level=None, timeout=10)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")

    @contextmanager
    def _transaction(self):
        self._db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self._db.commit()
        except BaseException:
            self._db.rollback()
            raise

    def _public_user(self, row):
        return {key: row[key] for key in ("id", "full_name", "username", "role", "status")}

    def _require(self, *roles):
        if self._session_id is None:
            raise PermissionError("Please sign in to continue.")
        row = self._db.execute("SELECT * FROM users WHERE id=?", (self._session_id,)).fetchone()
        if not row or row["status"] != "active":
            self.logout()
            raise PermissionError("Your account is no longer active. Contact the owner.")
        self.user = self._public_user(row)
        if roles and row["role"] not in roles:
            raise PermissionError("Your role does not have permission for this action.")
        return row

    def _audit(self, action, details="", actor=None):
        actor = actor or self.user
        self._db.execute("INSERT INTO audit_log(created_at,actor_id,actor,action,details) VALUES(?,?,?,?,?)", (_now(), actor["id"] if actor else None, actor["full_name"] if actor else "System", action, str(details)))

    def setup_required(self):
        return not bool(self._db.execute("SELECT 1 FROM users WHERE is_owner=1").fetchone())

    def setup_academy(self, academy_name, address, phone, owner_name, username, password):
        name = _text(academy_name, "Academy name")
        address = _text(address, "Address", 1000, False)
        phone = _text(phone, "Phone", 50, False)
        full_name = _text(owner_name, "Owner name")
        username = _username(username)
        password_hash = self._hasher.hash(_password(password))
        code = self._recovery_code()
        recovery_hash = self._hasher.hash(code)
        with self._transaction():
            if not self.setup_required():
                raise RuntimeError("Academy setup is already complete. Sign in instead.")
            self._db.executemany("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", [("academy_name", name), ("address", address), ("phone", phone), ("currency", "PKR")])
            cursor = self._db.execute("INSERT INTO users(full_name,username,password_hash,role,status,is_owner,recovery_hash,created_at) VALUES(?,?,?,'admin','active',1,?,?)", (full_name, username, password_hash, recovery_hash, _now()))
            row = self._db.execute("SELECT * FROM users WHERE id=?", (cursor.lastrowid,)).fetchone()
            user = self._public_user(row)
            self._audit("Academy setup", name, actor=user)
        self._session_id = user["id"]
        self.user = user
        return {"user": dict(user), "recovery_code": code}

    @staticmethod
    def _recovery_code():
        raw = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
        return "-".join(raw[i:i + 4] for i in range(0, len(raw), 4))

    @staticmethod
    def _valid_password_hash(value):
        if not isinstance(value, str) or not re.fullmatch(r"\$argon2id\$v=19\$m=\d+,t=\d+,p=\d+\$[A-Za-z0-9+/]+\$[A-Za-z0-9+/]+", value):
            return False
        try:
            params = extract_parameters(value)
            salt_text, hash_text = value.rsplit("$", 2)[1:]
            salt = base64.b64decode(salt_text + "=" * (-len(salt_text) % 4), validate=True)
            digest = base64.b64decode(hash_text + "=" * (-len(hash_text) % 4), validate=True)
            return (1 <= params.time_cost <= 5 and 8192 <= params.memory_cost <= 131072
                    and 1 <= params.parallelism <= 8 and 16 <= len(salt) <= 64
                    and 16 <= len(digest) <= 64)
        except (InvalidHashError, ValueError):
            return False

    def _verify(self, password_hash, password):
        if not self._valid_password_hash(password_hash):
            return False
        try:
            return self._hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError, TypeError):
            return False

    def _failed_login(self, row):
        if row:
            failures = row["failed_attempts"] + 1
            locked = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat(timespec="seconds") if failures >= 5 else None
            with self._transaction():
                self._db.execute("UPDATE users SET failed_attempts=?,locked_until=? WHERE id=?", (failures, locked, row["id"]))

    def login(self, username, password):
        self.logout()
        username = _username(username)
        if not isinstance(password, str) or len(password) > 1024:
            raise PermissionError("Incorrect username or password.")
        row = self._db.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (username,)).fetchone()
        if row and row["locked_until"] and row["locked_until"] > _now():
            raise PermissionError("Too many attempts. Wait one minute and try again.")
        correct = self._verify(row["password_hash"] if row else self._dummy_hash, password)
        if not correct or not row:
            self._failed_login(row)
            raise PermissionError("Incorrect username or password.")
        if row["status"] != "active":
            raise PermissionError("Your account is awaiting approval or is inactive. Contact the owner.")
        with self._transaction():
            self._db.execute("UPDATE users SET failed_attempts=0,locked_until=NULL WHERE id=?", (row["id"],))
            if self._hasher.check_needs_rehash(row["password_hash"]):
                self._db.execute("UPDATE users SET password_hash=? WHERE id=?", (self._hasher.hash(password), row["id"]))
            self._audit("Signed in", actor=self._public_user(row))
        self.user = self._public_user(row)
        self._session_id = row["id"]
        return dict(self.user)

    def signup(self, full_name, username, password):
        if self.setup_required():
            raise RuntimeError("The owner must set up the academy first.")
        full_name, username = _text(full_name, "Full name"), _username(username)
        hashed = self._hasher.hash(_password(password))
        try:
            with self._transaction():
                cursor = self._db.execute("INSERT INTO users(full_name,username,password_hash,role,status,created_at) VALUES(?,?,?,'receptionist','pending',?)", (full_name, username, hashed, _now()))
                self._audit("Staff signup pending", f"Username: {username}; user #{cursor.lastrowid}", actor={"id": cursor.lastrowid, "full_name": full_name})
        except sqlite3.IntegrityError:
            raise ValueError("This username is already registered.") from None

    def logout(self):
        self.user = None
        self._session_id = None

    def _verified_recovery_owner(self, username, recovery_code):
        username = _username(username)
        row = self._db.execute("SELECT * FROM users WHERE username=? AND is_owner=1", (username,)).fetchone()
        if row and row["locked_until"] and row["locked_until"] > _now():
            raise PermissionError("Too many attempts. Wait one minute and try again.")
        code = str(recovery_code).strip().upper()
        if len(code) > 200 or not self._verify(row["recovery_hash"] if row else self._dummy_hash, code) or not row:
            self._failed_login(row)
            raise PermissionError("This recovery key does not match the academy owner account.")
        return row

    def recover_owner(self, username, recovery_code, new_password):
        """Legacy typed-code recovery; new desktop flows use a recovery file."""
        _password(new_password)
        row = self._verified_recovery_owner(username, recovery_code)
        new_code = self._recovery_code()
        with self._transaction():
            self._db.execute("UPDATE users SET password_hash=?,recovery_hash=?,failed_attempts=0,locked_until=NULL WHERE id=?", (self._hasher.hash(new_password), self._hasher.hash(new_code), row["id"]))
            self._audit("Owner account recovered", "Recovery code rotated", actor=self._public_user(row))
        self.logout()
        return new_code

    @staticmethod
    def _write_recovery_file(target, payload):
        """Install a private, fully written key without replacing any file.

        POSIX hard-link installation and Windows rename both offer atomic
        no-overwrite semantics. The staged file is fsynced before installation.
        """
        temporary = None
        installed = False
        try:
            descriptor, temporary_name = tempfile.mkstemp(prefix=".nexus-key-", suffix=".tmp", dir=target.parent)
            temporary = Path(temporary_name)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
                json.dump(payload, output, ensure_ascii=True, indent=2)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            if os.name == "nt":
                os.rename(temporary, target)  # Windows refuses an existing target.
            else:
                os.link(temporary, target)  # Atomic O_EXCL-style installation.
            installed = True
            if os.name != "nt":
                directory_fd = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        except BaseException:
            if installed:
                target.unlink(missing_ok=True)
            raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def save_recovery_file(self, destination, recovery_code=None, current_password=None):
        """Save the first-run key, or create a replacement after password proof.

        A replacement invalidates older recovery files only after the new file
        has been written durably. Failed saves leave the previous key usable.
        """
        owner = self._require("admin")
        if not owner["is_owner"]:
            raise PermissionError("Only the academy owner can save an owner recovery file.")
        if (recovery_code is None) == (current_password is None):
            raise ValueError("Provide either the first-setup recovery key or your current password.")
        try:
            target = Path(destination).expanduser().absolute()
        except (TypeError, ValueError):
            raise ValueError("Choose a valid recovery-file destination.") from None
        if target.resolve() == self.db_path.resolve():
            raise ValueError("A recovery file cannot replace the academy database.")
        if os.path.lexists(target):
            raise ValueError("A file already exists there. Choose a new recovery filename.")
        if not target.parent.is_dir():
            raise ValueError("The recovery-file folder does not exist.")
        if owner["locked_until"] and owner["locked_until"] > _now():
            raise PermissionError("Too many attempts. Wait one minute and try again.")
        rotate = current_password is not None
        if rotate:
            if not isinstance(current_password, str) or len(current_password) > 1024 or not self._verify(owner["password_hash"], current_password):
                self._failed_login(owner)
                raise PermissionError("The current owner password is incorrect.")
            code = self._recovery_code()
        else:
            code = str(recovery_code).strip().upper()
            if len(code) > 200 or not self._verify(owner["recovery_hash"], code):
                self._failed_login(owner)
                raise PermissionError("The first-setup recovery key is no longer valid. Use your current password to save a replacement file.")
        new_hash = self._hasher.hash(code) if rotate else owner["recovery_hash"]
        payload = {"format": "nexus-recovery-v1", "username": owner["username"], "recovery_code": code}
        created = False
        try:
            with self._transaction():
                current = self._db.execute("SELECT * FROM users WHERE id=?", (owner["id"],)).fetchone()
                if not current or current["status"] != "active" or current["password_hash"] != owner["password_hash"] or current["recovery_hash"] != owner["recovery_hash"]:
                    raise PermissionError("The owner account changed. Sign in again before saving a recovery file.")
                self._write_recovery_file(target, payload)
                created = True
                self._db.execute("UPDATE users SET recovery_hash=?,failed_attempts=0,locked_until=NULL WHERE id=?", (new_hash, owner["id"]))
                self._audit("Owner recovery file saved", "Replacement key activated; older recovery files invalidated" if rotate else "Initial owner recovery file saved")
        except BaseException:
            if created:
                target.unlink(missing_ok=True)
            raise
        return str(target)

    @staticmethod
    def _read_recovery_file(source):
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate recovery-file fields.")
                result[key] = value
            return result
        try:
            descriptor = os.open(Path(source).expanduser(), os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
            with os.fdopen(descriptor, "rb") as incoming:
                info = os.fstat(incoming.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > 8192:
                    raise ValueError("Invalid recovery file size or type.")
                raw = incoming.read(8193)
                if len(raw) > 8192:
                    raise ValueError("Recovery file is too large.")
            payload = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
            if not isinstance(payload, dict) or set(payload) != {"format", "username", "recovery_code"} or payload["format"] != "nexus-recovery-v1":
                raise ValueError("Unsupported recovery-file format.")
            username = _username(payload["username"])
            code = payload["recovery_code"]
            if username != payload["username"] or not isinstance(code, str) or not re.fullmatch(r"[A-Z2-7]{4}(?:-[A-Z2-7]{4}){7}", code):
                raise ValueError("Invalid recovery-file fields.")
            return username, code
        except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
            raise ValueError("Choose a valid academy recovery file (.nexus-key). The file may be missing, damaged or for another format.") from None

    def reset_password_with_file(self, source, new_password):
        """Reset the owner password while retaining the selected reusable key."""
        _password(new_password)
        username, code = self._read_recovery_file(source)
        owner = self._verified_recovery_owner(username, code)
        hashed = self._hasher.hash(new_password)
        with self._transaction():
            current = self._db.execute("SELECT recovery_hash FROM users WHERE id=? AND is_owner=1", (owner["id"],)).fetchone()
            if not current or current["recovery_hash"] != owner["recovery_hash"]:
                raise PermissionError("This recovery file was replaced. Choose the latest owner recovery file.")
            self._db.execute("UPDATE users SET password_hash=?,failed_attempts=0,locked_until=NULL WHERE id=?", (hashed, owner["id"]))
            self._audit("Owner password reset using recovery file", "Owner recovery file verified and retained", actor=self._public_user(owner))
        self.logout()

    def has_permission(self, area):
        try:
            actor = self._require()
        except PermissionError:
            return False
        return area in PERMISSIONS.get(actor["role"], set())

    def get_settings(self):
        if not self.setup_required():
            self._require()
        result = {"academy_name": "Intellectual Nexus Academy", "address": "", "phone": "", "currency": "PKR"}
        result.update(dict(self._db.execute("SELECT key,value FROM settings").fetchall()))
        return result

    def update_settings(self, academy_name, address, phone):
        self._require("admin")
        values = [("academy_name", _text(academy_name, "Academy name")), ("address", _text(address, "Address", 1000, False)), ("phone", _text(phone, "Phone", 50, False))]
        with self._transaction():
            self._db.executemany("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", values)
            self._audit("Academy settings updated")

    def list_users(self):
        self._require("admin")
        return [dict(self._public_user(row), is_owner=bool(row["is_owner"])) for row in self._db.execute("SELECT * FROM users ORDER BY is_owner DESC,full_name")]

    def create_staff(self, full_name, username, password, role):
        self._require("admin")
        if role not in STAFF_ROLES:
            raise ValueError("Choose Receptionist, Cashier or Teacher. The owner remains the only administrator.")
        full_name, username = _text(full_name, "Full name"), _username(username)
        hashed = self._hasher.hash(_password(password))
        try:
            with self._transaction():
                cursor = self._db.execute("INSERT INTO users(full_name,username,password_hash,role,status,created_at) VALUES(?,?,?,?,'active',?)", (full_name, username, hashed, role, _now()))
                self._audit("Staff account created", f"{username}; {role}")
                result = self._public_user(self._db.execute("SELECT * FROM users WHERE id=?", (cursor.lastrowid,)).fetchone())
            return result
        except sqlite3.IntegrityError:
            raise ValueError("This username is already registered.") from None

    def approve_user(self, user_id, role):
        self._require("admin")
        if role not in STAFF_ROLES:
            raise ValueError("Choose a staff role. Signup cannot grant administrator access.")
        user_id = _identifier(user_id)
        row = self._db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not row or row["is_owner"]:
            raise ValueError("Select a staff account.")
        with self._transaction():
            self._db.execute("UPDATE users SET role=?,status='active' WHERE id=?", (role, user_id))
            self._audit("Staff account approved", f"{row['username']}; {role}")

    def set_user_active(self, user_id, active):
        self._require("admin")
        row = self._db.execute("SELECT * FROM users WHERE id=?", (_identifier(user_id),)).fetchone()
        if not row or row["is_owner"] or row["id"] == self._session_id:
            raise ValueError("The owner cannot be deactivated. Select a staff account.")
        status = "active" if active else "inactive"
        with self._transaction():
            self._db.execute("UPDATE users SET status=? WHERE id=?", (status, row["id"]))
            self._audit("Staff status changed", f"{row['username']}; {status}")

    def reset_password(self, user_id, new_password):
        self._require("admin")
        row = self._db.execute("SELECT * FROM users WHERE id=?", (_identifier(user_id),)).fetchone()
        if not row:
            raise ValueError("Account not found.")
        with self._transaction():
            self._db.execute("UPDATE users SET password_hash=?,failed_attempts=0,locked_until=NULL WHERE id=?", (self._hasher.hash(_password(new_password)), row["id"]))
            self._audit("Staff password reset", row["username"])

    def change_password(self, current_password, new_password):
        row = self._require()
        if not self._verify(row["password_hash"], current_password):
            raise PermissionError("The current password is incorrect.")
        with self._transaction():
            self._db.execute("UPDATE users SET password_hash=?,failed_attempts=0,locked_until=NULL WHERE id=?", (self._hasher.hash(_password(new_password)), row["id"]))
            self._audit("Password changed")

    def list_teachers(self):
        self._require("admin", "receptionist")
        return [dict(row) for row in self._db.execute("SELECT id,full_name FROM users WHERE role='teacher' AND status='active' ORDER BY full_name")]

    def list_classes(self):
        actor = self._require()
        query = "SELECT c.*,u.full_name AS teacher_name FROM classes c LEFT JOIN users u ON u.id=c.teacher_id"
        params = ()
        if actor["role"] == "teacher":
            query += " WHERE c.teacher_id=?"
            params = (actor["id"],)
        return [dict(row, monthly_fee=_money(row["monthly_fee"])) for row in self._db.execute(query + " ORDER BY c.name", params)]

    def add_class(self, name, schedule, monthly_fee, teacher_id=None):
        self._require("admin", "receptionist")
        name, schedule = _text(name, "Class/batch name"), _text(schedule, "Schedule", 200, False)
        monthly_fee = _amount(monthly_fee, "Monthly fee")
        if teacher_id is not None:
            teacher_id = _identifier(teacher_id)
            if not self._db.execute("SELECT 1 FROM users WHERE id=? AND role='teacher' AND status='active'", (teacher_id,)).fetchone():
                raise ValueError("Select an active teacher.")
        try:
            with self._transaction():
                cursor = self._db.execute("INSERT INTO classes(name,schedule,monthly_fee,teacher_id) VALUES(?,?,?,?)", (name, schedule, monthly_fee, teacher_id))
                self._audit("Class created", name)
            return next(c for c in self.list_classes() if c["id"] == cursor.lastrowid)
        except sqlite3.IntegrityError:
            raise ValueError("A class with this name already exists.") from None

    def update_class(self, class_id, name, schedule, monthly_fee, teacher_id=None):
        self._require("admin", "receptionist")
        class_id = _identifier(class_id)
        name, schedule = _text(name, "Class/batch name"), _text(schedule, "Schedule", 200, False)
        monthly_fee = _amount(monthly_fee, "Monthly fee")
        if teacher_id is not None:
            teacher_id = _identifier(teacher_id)
            if not self._db.execute("SELECT 1 FROM users WHERE id=? AND role='teacher' AND status='active'", (teacher_id,)).fetchone():
                raise ValueError("Select an active teacher.")
        try:
            with self._transaction():
                if not self._db.execute("SELECT 1 FROM classes WHERE id=?", (class_id,)).fetchone():
                    raise ValueError("Class not found.")
                self._db.execute("UPDATE classes SET name=?,schedule=?,monthly_fee=?,teacher_id=? WHERE id=?", (name, schedule, monthly_fee, teacher_id, class_id))
                self._audit("Class updated", f"Class #{class_id}; {name}; teacher #{teacher_id or 'unassigned'}")
            return next(c for c in self.list_classes() if c["id"] == class_id)
        except sqlite3.IntegrityError:
            raise ValueError("A class with this name already exists.") from None

    def list_students(self, search=""):
        actor = self._require()
        search = _text(search, "Search", 200, False)
        query = "SELECT s.*,c.name AS class_name FROM students s JOIN classes c ON c.id=s.class_id WHERE 1=1"
        params = []
        if actor["role"] == "teacher":
            query += " AND c.teacher_id=?"
            params.append(actor["id"])
        if search:
            query += " AND (s.full_name LIKE ? OR s.student_number LIKE ? OR s.phone LIKE ? OR c.name LIKE ?)"
            params.extend([f"%{search}%"] * 4)
        return [dict(row, monthly_fee=_money(row["monthly_fee"])) for row in self._db.execute(query + " ORDER BY s.id DESC", params)]

    def admit_student(self, full_name, guardian_name, phone, class_id, admission_date, monthly_fee, admission_fee, discount, due_date, address="", notes="", *, fee_exempt=False):
        self._require("admin", "receptionist")
        full_name = _text(full_name, "Student name")
        guardian_name = _text(guardian_name, "Guardian name")
        phone = _text(phone, "Guardian phone", 50)
        class_id = _identifier(class_id)
        admission_date, due_date = _day(admission_date, "Admission date"), _day(due_date, "Due date")
        tuition, other, reduction = _amount(monthly_fee, "Monthly fee"), _amount(admission_fee, "Admission fee"), _amount(discount, "Discount")
        self._validate_fee_total(tuition, other, reduction, fee_exempt)
        address, notes = _text(address, "Address", 1000, False), _text(notes, "Notes", 3000, False)
        with self._transaction():
            if not self._db.execute("SELECT 1 FROM classes WHERE id=?", (class_id,)).fetchone():
                raise ValueError("Select an existing class.")
            cursor = self._db.execute("INSERT INTO students(full_name,guardian_name,phone,class_id,admission_date,monthly_fee,address,notes) VALUES(?,?,?,?,?,?,?,?)", (full_name, guardian_name, phone, class_id, admission_date, tuition, address, notes))
            student_id = cursor.lastrowid
            number = f"NX-{student_id:05d}"
            self._db.execute("UPDATE students SET student_number=? WHERE id=?", (number, student_id))
            challan_id = self._insert_challan(student_id, admission_date[:7], tuition, other, reduction, due_date)
            self._audit("Student admitted", f"{number}; {full_name}; initial challan #{challan_id}" + ("; fee-exempt: no payment due" if tuition + other == reduction else ""))
        student = next(s for s in self.list_students() if s["id"] == student_id)
        return {"student": student, "challan": self.challan_details(challan_id)}

    def update_student(self, student_id, full_name, guardian_name, phone, class_id, monthly_fee, address="", notes="", status="active"):
        self._require("admin", "receptionist")
        student_id, class_id = _identifier(student_id), _identifier(class_id)
        full_name, guardian_name = _text(full_name, "Student name"), _text(guardian_name, "Guardian name")
        phone = _text(phone, "Guardian phone", 50)
        monthly_fee = _amount(monthly_fee, "Monthly fee")
        address, notes = _text(address, "Address", 1000, False), _text(notes, "Notes", 3000, False)
        if status not in {"active", "inactive"}:
            raise ValueError("Student status must be active or inactive.")
        with self._transaction():
            original = self._db.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()
            if not original:
                raise ValueError("Student not found.")
            if not self._db.execute("SELECT 1 FROM classes WHERE id=?", (class_id,)).fetchone():
                raise ValueError("Select an existing class.")
            self._db.execute("UPDATE students SET full_name=?,guardian_name=?,phone=?,class_id=?,monthly_fee=?,address=?,notes=?,status=? WHERE id=?", (full_name, guardian_name, phone, class_id, monthly_fee, address, notes, status, student_id))
            changed = [key for key, value in {"full_name": full_name, "guardian_name": guardian_name, "phone": phone, "class_id": class_id, "monthly_fee": monthly_fee, "address": address, "notes": notes, "status": status}.items() if original[key] != value]
            self._audit("Student updated", f"{original['student_number']}; changed: {', '.join(changed) or 'no fields'}; existing fee history retained")
        return next(s for s in self.list_students() if s["id"] == student_id)

    def _insert_challan(self, student_id, period, tuition, other, discount, due_date):
        issued = date.today().isoformat()
        cursor = self._db.execute("INSERT INTO challans(student_id,period,issued_on,due_date,tuition,other,discount,total,created_by) VALUES(?,?,?,?,?,?,?,?,?)", (student_id, period, issued, due_date, tuition, other, discount, tuition + other - discount, self._session_id))
        challan_id = cursor.lastrowid
        number = f"CH-{date.today().year}-{challan_id:05d}"
        self._db.execute("UPDATE challans SET number=? WHERE id=?", (number, challan_id))
        return challan_id

    def create_challan(self, student_id, period, tuition, discount, due_date, other=0, *, fee_exempt=False):
        self._require("admin", "receptionist", "cashier")
        student_id = _identifier(student_id)
        if not isinstance(period, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period) or period.startswith("0000"):
            raise ValueError("Fee period must use YYYY-MM, for example 2026-11.")
        tuition, other, discount = _amount(tuition, "Tuition"), _amount(other, "Other fees"), _amount(discount, "Discount")
        due_date = _day(due_date, "Due date")
        self._validate_fee_total(tuition, other, discount, fee_exempt)
        try:
            with self._transaction():
                if not self._db.execute("SELECT 1 FROM students WHERE id=? AND status='active'", (student_id,)).fetchone():
                    raise ValueError("Select an active student.")
                challan_id = self._insert_challan(student_id, period, tuition, other, discount, due_date)
                self._audit("Challan created", f"Challan #{challan_id}; period {period}" + ("; fee-exempt: no payment due" if tuition + other == discount else ""))
            return self.challan_details(challan_id)
        except sqlite3.IntegrityError:
            raise ValueError("This student already has a challan for that month.") from None

    @staticmethod
    def _validate_fee_total(tuition, other, discount, fee_exempt):
        if not isinstance(fee_exempt, bool):
            raise ValueError("Fee exemption must be explicitly selected.")
        if discount > tuition + other:
            raise ValueError("Discount cannot exceed the total fee.")
        if tuition + other == discount and not fee_exempt:
            raise ValueError("Enter the actual fee, or explicitly select fee-exempt / no payment due for a zero-total bill.")

    def amend_challan(self, challan_id, tuition, other, discount, due_date, reason, *, fee_exempt=False):
        """Correct an uncollected bill without changing financial history.

        Even reversed payments make a challan immutable. Student fee defaults
        are independent, and must be changed through update_student instead.
        """
        self._require("admin", "receptionist", "cashier")
        challan_id = _identifier(challan_id)
        tuition, other, discount = _amount(tuition, "Tuition"), _amount(other, "Other fees"), _amount(discount, "Discount")
        self._validate_fee_total(tuition, other, discount, fee_exempt)
        due_date, reason = _day(due_date, "Due date"), _text(reason, "Amendment reason", 1000)
        with self._transaction():
            original = self._db.execute("SELECT * FROM challans WHERE id=?", (challan_id,)).fetchone()
            if not original:
                raise ValueError("Challan not found.")
            if self._db.execute("SELECT 1 FROM payments WHERE challan_id=? LIMIT 1", (challan_id,)).fetchone():
                raise ValueError("This bill has payment history and cannot be amended, including after a reversal. Keep the original financial record.")
            total = tuition + other - discount
            self._db.execute("UPDATE challans SET tuition=?,other=?,discount=?,total=?,due_date=? WHERE id=?", (tuition, other, discount, total, due_date, challan_id))
            before = f"tuition {_money(original['tuition'])}, other {_money(original['other'])}, discount {_money(original['discount'])}, total {_money(original['total'])}, due {original['due_date']}"
            after = f"tuition {_money(tuition)}, other {_money(other)}, discount {_money(discount)}, total {_money(total)}, due {due_date}"
            self._audit("Challan amended", f"{original['number']}; before: {before}; after: {after}; reason: {reason}" + ("; fee-exempt: no payment due" if total == 0 else ""))
        return self.challan_details(challan_id)

    @staticmethod
    def _challan_query():
        return """SELECT c.*,s.full_name AS student_name,s.student_number,s.guardian_name,s.phone,
        cl.name AS class_name,COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.challan_id=c.id AND p.reversed=0),0) AS paid
        FROM challans c JOIN students s ON s.id=c.student_id JOIN classes cl ON cl.id=s.class_id"""

    @staticmethod
    def _challan(row):
        result = dict(row)
        balance = row["total"] - row["paid"]
        result["status"] = "No payment due" if row["total"] == 0 else "Paid" if balance == 0 and row["paid"] > 0 else "Partially paid" if row["paid"] else "Unpaid"
        result["balance"] = _money(balance)
        for key in ("tuition", "other", "discount", "total", "paid"):
            result[key] = _money(row[key])
        result.pop("created_by", None)
        return result

    def list_challans(self, search="", status="All"):
        self._require("admin", "receptionist", "cashier")
        search = _text(search, "Search", 200, False)
        if status not in {"All", "Unpaid", "Partially paid", "Paid", "No payment due", "Overdue"}:
            raise ValueError("Unknown challan status.")
        query, params = self._challan_query(), []
        if search:
            query += " WHERE (c.number LIKE ? OR s.full_name LIKE ? OR s.student_number LIKE ? OR cl.name LIKE ?)"
            params = [f"%{search}%"] * 4
        rows = [self._challan(row) for row in self._db.execute(query + " ORDER BY c.id DESC", params)]
        if status == "Overdue":
            return [r for r in rows if Decimal(r["balance"]) > 0 and r["due_date"] < date.today().isoformat()]
        return rows if status == "All" else [r for r in rows if r["status"] == status]

    def challan_details(self, challan_id):
        self._require("admin", "receptionist", "cashier")
        row = self._db.execute(self._challan_query() + " WHERE c.id=?", (_identifier(challan_id),)).fetchone()
        if not row:
            raise ValueError("Challan not found.")
        result = self._challan(row)
        result["payments"] = [self._payment(r) for r in self._db.execute(self._payment_query() + " WHERE p.challan_id=? ORDER BY p.id DESC", (row["id"],))]
        return result

    @staticmethod
    def _payment_query():
        return """SELECT p.*,c.number AS challan_number,s.full_name AS student_name,s.student_number,
        u.full_name AS received_by_name FROM payments p JOIN challans c ON c.id=p.challan_id
        JOIN students s ON s.id=c.student_id JOIN users u ON u.id=p.received_by"""

    @staticmethod
    def _payment(row):
        result = dict(row)
        result["amount"] = _money(row["amount"])
        result["received_by"] = row["received_by_name"]
        result["reversed"] = bool(row["reversed"])
        result.pop("received_by_name", None)
        result.pop("idempotency_key", None)
        return result

    def list_payments(self, search=""):
        self._require("admin", "receptionist", "cashier")
        search = _text(search, "Search", 200, False)
        query, params = self._payment_query(), []
        if search:
            query += " WHERE (p.number LIKE ? OR c.number LIKE ? OR s.full_name LIKE ? OR s.student_number LIKE ?)"
            params = [f"%{search}%"] * 4
        return [self._payment(row) for row in self._db.execute(query + " ORDER BY p.id DESC", params)]

    def record_payment(self, challan_id, amount, method, reference="", idempotency_key=None):
        self._require("admin", "cashier")
        challan_id, amount = _identifier(challan_id), _amount(amount, "Payment", positive=True)
        if method not in PAYMENT_METHODS:
            raise ValueError("Choose Cash, Bank transfer, Card or Other.")
        reference = _text(reference, "Reference", 200, False)
        key = _text(idempotency_key, "Payment request ID", 200) if idempotency_key is not None else None
        with self._transaction():
            if key:
                previous = self._db.execute("SELECT * FROM payments WHERE idempotency_key=?", (key,)).fetchone()
                if previous:
                    if (previous["challan_id"], previous["amount"], previous["method"], previous["reference"]) != (challan_id, amount, method, reference):
                        raise ValueError("That payment request ID was already used with different details.")
                    return self._payment(self._db.execute(self._payment_query() + " WHERE p.id=?", (previous["id"],)).fetchone())
            row = self._db.execute(self._challan_query() + " WHERE c.id=?", (challan_id,)).fetchone()
            if not row:
                raise ValueError("Challan not found.")
            if amount > row["total"] - row["paid"]:
                raise ValueError("Payment exceeds the outstanding balance.")
            cursor = self._db.execute("INSERT INTO payments(challan_id,amount,method,reference,paid_on,received_by,idempotency_key) VALUES(?,?,?,?,?,?,?)", (challan_id, amount, method, reference, _now(), self._session_id, key))
            number = f"RC-{date.today().year}-{cursor.lastrowid:05d}"
            self._db.execute("UPDATE payments SET number=? WHERE id=?", (number, cursor.lastrowid))
            self._audit("Payment received", f"{number}; challan {row['number']}; Rs {_money(amount)}; {method}")
            result = self._payment(self._db.execute(self._payment_query() + " WHERE p.id=?", (cursor.lastrowid,)).fetchone())
        return result

    def reverse_payment(self, payment_id, reason):
        self._require("admin")
        payment_id, reason = _identifier(payment_id), _text(reason, "Reversal reason", 1000)
        with self._transaction():
            payment = self._db.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
            if not payment:
                raise ValueError("Payment not found.")
            if payment["reversed"]:
                raise ValueError("This payment has already been reversed.")
            self._db.execute("UPDATE payments SET reversed=1,reversed_at=?,reversed_by=?,reversal_reason=? WHERE id=?", (_now(), self._session_id, reason, payment_id))
            self._audit("Payment reversed", f"{payment['number']}; Rs {_money(payment['amount'])}; reason: {reason}")

    def _class_for_attendance(self, class_id):
        actor = self._require("admin", "teacher")
        class_id = _identifier(class_id)
        cls = self._db.execute("SELECT * FROM classes WHERE id=?", (class_id,)).fetchone()
        if not cls:
            raise ValueError("Class not found.")
        if actor["role"] == "teacher" and cls["teacher_id"] != actor["id"]:
            raise PermissionError("You can mark attendance only for classes assigned to you.")
        return class_id

    def attendance_roster(self, class_id, date):
        class_id = self._class_for_attendance(class_id)
        day = _day(date)
        query = """SELECT s.id AS student_id,s.student_number,s.full_name,COALESCE(a.status,'Not marked') AS status
          FROM students s LEFT JOIN attendance a ON a.student_id=s.id AND a.day=?
          WHERE s.class_id=? AND s.status='active' ORDER BY s.full_name"""
        return [dict(row) for row in self._db.execute(query, (day, class_id))]

    def save_attendance(self, class_id, date, records):
        class_id = self._class_for_attendance(class_id)
        day = _day(date)
        if not isinstance(records, (list, tuple)):
            raise ValueError("Attendance must be a list of student records.")
        active_ids = {r["student_id"] for r in self.attendance_roster(class_id, day)}
        validated, seen = [], set()
        for record in records:
            if not isinstance(record, dict):
                raise ValueError("Invalid attendance record.")
            student_id = _identifier(record.get("student_id"))
            status = record.get("status")
            if student_id not in active_ids or status not in ATTENDANCE_STATUSES or student_id in seen:
                raise ValueError("Attendance contains an invalid, duplicate or unassigned student/status.")
            seen.add(student_id)
            validated.append((student_id, day, status, self._session_id, _now()))
        with self._transaction():
            self._db.executemany("INSERT INTO attendance(student_id,day,status,marked_by,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(student_id,day) DO UPDATE SET status=excluded.status,marked_by=excluded.marked_by,updated_at=excluded.updated_at", validated)
            self._audit("Attendance saved", f"Class #{class_id}; {day}; {len(validated)} records")

    def _financial_summary(self):
        month = date.today().strftime("%Y-%m")
        collected = self._db.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE reversed=0 AND strftime('%Y-%m',paid_on,'localtime')=?", (month,)).fetchone()[0]
        rows = [self._challan(r) for r in self._db.execute(self._challan_query() + " ORDER BY c.due_date,c.id")]
        unpaid = [r for r in rows if Decimal(r["balance"]) > 0]
        outstanding = sum((int(Decimal(r["balance"]) * 100) for r in unpaid), 0)
        overdue = [r for r in unpaid if r["due_date"] < date.today().isoformat()]
        return collected, outstanding, overdue, unpaid

    def dashboard(self):
        actor = self._require()
        if actor["role"] == "teacher":
            rows = self.list_students()
            return {"total_students": len(rows), "active_students": sum(r["status"] == "active" for r in rows), "month_collected": "0.00", "outstanding": "0.00", "overdue_count": 0, "recent_payments": []}
        collected, outstanding, overdue, _ = self._financial_summary()
        total, active = self._db.execute("SELECT COUNT(*),COALESCE(SUM(status='active'),0) FROM students").fetchone()
        recent = [self._payment(r) for r in self._db.execute(self._payment_query() + " WHERE p.reversed=0 ORDER BY p.id DESC LIMIT 8")]
        return {"total_students": total, "active_students": active, "month_collected": _money(collected), "outstanding": _money(outstanding), "overdue_count": len(overdue), "recent_payments": recent}

    def reports(self):
        self._require("admin", "cashier")
        collected, outstanding, overdue, unpaid = self._financial_summary()
        active = self._db.execute("SELECT COUNT(*) FROM students WHERE status='active'").fetchone()[0]
        months = [dict(month=r["month"], amount=_money(r["amount"])) for r in self._db.execute("SELECT strftime('%Y-%m',paid_on,'localtime') AS month,SUM(amount) AS amount FROM payments WHERE reversed=0 GROUP BY month ORDER BY month DESC LIMIT 12")]
        return {"month_collected": _money(collected), "outstanding": _money(outstanding), "overdue_count": len(overdue), "active_students": active, "defaulters": overdue, "monthly_collection": months}

    def list_audit(self, limit=100):
        self._require("admin")
        try:
            limit = max(1, min(int(limit), 1000))
        except (ValueError, TypeError):
            raise ValueError("Audit limit must be a number.") from None
        return [dict(r) for r in self._db.execute("SELECT created_at,actor,action,details FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))]

    def backup(self, destination):
        self._require("admin")
        target = Path(destination).expanduser().absolute()
        if target.resolve() == self.db_path.resolve():
            raise ValueError("Choose a backup location different from the active database.")
        if target.exists():
            raise ValueError("A file already exists there. Choose a new backup filename.")
        if not target.parent.is_dir():
            raise ValueError("The backup folder does not exist.")
        try:
            with sqlite3.connect(target) as output:
                self._db.backup(output)
                if output.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Backup verification failed.")
            try:
                target.chmod(0o600)
            except OSError:
                pass
        except (sqlite3.Error, OSError) as exc:
            target.unlink(missing_ok=True)
            raise ValueError(f"Could not create backup: {exc}") from None
        with self._transaction():
            self._audit("Database backup created", target.name)
        return str(target)

    @staticmethod
    def _validate_backup(source):
        required = {"settings", "users", "classes", "students", "challans", "payments", "attendance", "audit_log"}
        try:
            connection = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            try:
                if connection.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                    raise ValueError("Backup schema version is not supported.")
                if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Backup integrity check failed.")
                if connection.execute("PRAGMA foreign_key_check").fetchone():
                    raise ValueError("Backup contains broken record references.")
                tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not required.issubset(tables):
                    raise ValueError("This is not an academy backup.")
                # Query all required columns, and reject views/triggers masquerading as data.
                for table in required:
                    if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                        raise ValueError("Invalid backup table layout.")
                if connection.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view')").fetchone():
                    raise ValueError("Unexpected executable objects in the backup.")
                expected = sqlite3.connect(":memory:")
                try:
                    expected.executescript(SCHEMA)
                    # table_info omits CHECK/UNIQUE/FK constraints and indexes. Compare
                    # canonical definitions too so modified constraints cannot validate.
                    def definitions(db):
                        return {(r[0], r[1]): r[2].strip()
                                for r in db.execute("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'")}
                    if definitions(connection) != definitions(expected):
                        raise ValueError("Backup table structure or constraints do not match this app version.")
                    for table in required:
                        actual_cols = [tuple(r) for r in connection.execute(f"PRAGMA table_info({table})")]
                        expected_cols = [tuple(r) for r in expected.execute(f"PRAGMA table_info({table})")]
                        if actual_cols != expected_cols:
                            raise ValueError("Backup table structure does not match this app version.")
                finally:
                    expected.close()
                owners = connection.execute("SELECT * FROM users WHERE is_owner=1").fetchall()
                if len(owners) != 1 or owners[0]["role"] != "admin" or owners[0]["status"] != "active":
                    raise ValueError("Backup must contain one active academy owner.")
                for account in connection.execute("SELECT * FROM users"):
                    if not AcademyService._valid_password_hash(account["password_hash"]):
                        raise ValueError("Backup account credentials are invalid or use unsupported hashing parameters.")
                    if account["is_owner"] and not AcademyService._valid_password_hash(account["recovery_hash"]):
                        raise ValueError("Backup owner recovery credentials are invalid.")
                    _username(account["username"])
                    _text(account["full_name"], "Backup account name")
                for student in connection.execute("SELECT * FROM students"):
                    _day(student["admission_date"], "Backup admission date")
                    if not student["student_number"] or not re.fullmatch(r"NX-\d{5,}", student["student_number"]):
                        raise ValueError("Backup student numbers are invalid.")
                for challan in connection.execute("SELECT * FROM challans"):
                    _day(challan["issued_on"], "Backup challan date")
                    _day(challan["due_date"], "Backup due date")
                    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", challan["period"]):
                        raise ValueError("Backup fee periods are invalid.")
                    if not challan["number"] or not re.fullmatch(r"CH-\d{4}-\d{5,}", challan["number"]):
                        raise ValueError("Backup challan numbers are invalid.")
                for payment in connection.execute("SELECT * FROM payments"):
                    if payment["method"] not in PAYMENT_METHODS:
                        raise ValueError("Backup payment methods are invalid.")
                    if not payment["number"] or not re.fullmatch(r"RC-\d{4}-\d{5,}", payment["number"]):
                        raise ValueError("Backup receipt numbers are invalid.")
                    try:
                        datetime.fromisoformat(payment["paid_on"])
                    except (ValueError, TypeError):
                        raise ValueError("Backup payment dates are invalid.") from None
                for attendance in connection.execute("SELECT day FROM attendance"):
                    _day(attendance["day"], "Backup attendance date")
                if not connection.execute("SELECT 1 FROM settings WHERE key='academy_name' AND length(value)>0").fetchone():
                    raise ValueError("Backup academy settings are missing.")
                invalid = connection.execute("""SELECT 1 FROM challans c WHERE c.total<0 OR c.total!=c.tuition+c.other-c.discount
                  OR c.total<(SELECT COALESCE(SUM(p.amount),0) FROM payments p WHERE p.challan_id=c.id AND p.reversed=0) LIMIT 1""").fetchone()
                if invalid:
                    raise ValueError("Backup contains inconsistent fee balances.")
            finally:
                connection.close()
        except sqlite3.Error:
            raise ValueError("The selected file is not a valid academy SQLite backup.") from None

    def restore(self, source):
        actor = dict(self._public_user(self._require("admin")))
        source = Path(source).expanduser().resolve()
        if source == self.db_path.resolve():
            raise ValueError("Select an external backup, not the active database.")
        if not source.is_file():
            raise ValueError("Backup file does not exist.")
        self._validate_backup(source)
        backups = self.data_dir / "pre_restore_backups"
        backups.mkdir(exist_ok=True, mode=0o700)
        safety = backups / f"academy-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}.sqlite3"
        self.backup(safety)
        # Stage using SQLite's backup API, which includes committed WAL contents.
        staging = self.data_dir / f".restore-{secrets.token_hex(8)}.sqlite3"
        try:
            with sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True) as incoming:
                with sqlite3.connect(staging) as output:
                    incoming.backup(output)
            self._validate_backup(staging)
            self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self._db.close()
            self._db = None
            os.replace(staging, self.db_path)
            # Old connection is closed/checkpointed; no stale WAL may survive replace.
            Path(str(self.db_path) + "-wal").unlink(missing_ok=True)
            Path(str(self.db_path) + "-shm").unlink(missing_ok=True)
            self._connect()
            try:
                self.db_path.chmod(0o600)
            except OSError:
                pass
            with self._transaction():
                # Restored backup may not contain the current actor; audit by name only.
                self._db.execute("INSERT INTO audit_log(created_at,actor_id,actor,action,details) VALUES(?,NULL,?,'Database restored',?)", (_now(), actor["full_name"], f"Source: {source.name}; pre-restore backup: {safety.name}"))
        except (OSError, sqlite3.Error) as exc:
            if self._db is None:
                self._connect()
            raise RuntimeError(f"Restore could not complete. A safety backup is at {safety}. {exc}") from None
        finally:
            staging.unlink(missing_ok=True)
            self.logout()

    def close(self):
        self.logout()
        if getattr(self, "_db", None) is not None:
            self._db.close()
            self._db = None
