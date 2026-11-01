"""Department navigation and a measured, institutional administrative workspace."""
from datetime import date
from decimal import Decimal

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QPushButton, QScrollArea, QStackedWidget,
    QVBoxLayout, QWidget,
)

from .common import BasePage, fill_table, heading, money, show_error, success, table
from .identity import AcademySeal, line_icon, seal_pixmap
from .visuals import SettlementChart


ROLE_NAMES = {
    "admin": "Administrator", "receptionist": "Reception office",
    "cashier": "Accounts office", "teacher": "Teaching staff",
}


def metric_card(label, value, note):
    frame = QFrame()
    frame.setObjectName("summaryCard")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(23, 18, 23, 19)
    layout.setSpacing(8)
    title = QLabel(label.upper())
    title.setObjectName("eyebrow")
    number = QLabel(str(value))
    number.setObjectName("metric")
    number.setWordWrap(True)
    sub = QLabel(note)
    sub.setObjectName("muted")
    sub.setWordWrap(True)
    layout.addWidget(title)
    layout.addWidget(number)
    layout.addWidget(sub)
    return frame


def section_header(title, suffix=""):
    frame = QFrame()
    frame.setObjectName("registerHeader")
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(20, 16, 20, 16)
    label = QLabel(title)
    label.setObjectName("sectionTitle")
    layout.addWidget(label)
    layout.addStretch()
    if suffix:
        detail = QLabel(suffix)
        detail.setObjectName("muted")
        layout.addWidget(detail)
    return frame


class PageStack(QStackedWidget):
    """Let the current document determine scrolling, rather than the tallest page."""
    def sizeHint(self):
        current = self.currentWidget()
        return current.sizeHint() if current else super().sizeHint()

    def minimumSizeHint(self):
        current = self.currentWidget()
        return current.minimumSizeHint() if current else super().minimumSizeHint()


class DashboardPage(BasePage):
    navigate = Signal(str)

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        self.setObjectName("dashboardPage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(22)
        title_row = QHBoxLayout()
        title_row.addWidget(heading("Administrative overview", "Student records, fee collection and daily office services"), 1)
        self.shortcut = QPushButton("New admission")
        self.shortcut.setObjectName("primary")
        self.shortcut.setIcon(line_icon("students", "#ffffff", 18))
        self.shortcut.clicked.connect(lambda: self.navigate.emit("students"))
        title_row.addWidget(self.shortcut, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(title_row)

        summary = QFrame()
        summary.setObjectName("summaryPanel")
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(0)
        summary_header = QFrame()
        summary_header.setObjectName("registerHeader")
        summary_heading = QHBoxLayout(summary_header)
        summary_heading.setContentsMargins(21, 11, 21, 11)
        stamp = QLabel("INSTITUTIONAL RECORDS")
        stamp.setObjectName("eyebrow")
        summary_heading.addWidget(stamp)
        summary_heading.addStretch()
        self.overdue = QLabel()
        self.overdue.setObjectName("muted")
        summary_heading.addWidget(self.overdue)
        summary_layout.addWidget(summary_header)
        self.metrics = QHBoxLayout()
        self.metrics.setSpacing(0)
        summary_layout.addLayout(self.metrics)
        layout.addWidget(summary)

        details = QHBoxLayout()
        details.setSpacing(22)
        self.register = QFrame()
        self.register.setObjectName("card")
        register_layout = QVBoxLayout(self.register)
        register_layout.setContentsMargins(0, 0, 0, 0)
        register_layout.setSpacing(0)
        self.collection_header = section_header("Recent payment receipts", "LATEST 8 ENTRIES")
        self.collections_title = self.collection_header.findChild(QLabel)
        register_layout.addWidget(self.collection_header)
        self.payments = table(["RECEIPT NO.", "STUDENT NAME", "DATE", "METHOD", "AMOUNT"])
        self.payments.setObjectName("registerTable")
        register_layout.addWidget(self.payments, 1)
        self.empty = QLabel("No receipts recorded. Confirmed fee payments will appear in this register.")
        self.empty.setObjectName("muted")
        self.empty.setWordWrap(True)
        self.empty.setContentsMargins(20, 20, 20, 20)
        register_layout.addWidget(self.empty)
        register_footer = QFrame()
        register_footer.setObjectName("registerActions")
        footer = QHBoxLayout(register_footer)
        footer.setContentsMargins(14, 10, 14, 10)
        self.receipt_note = QLabel("Reversed payments are excluded.")
        self.receipt_note.setObjectName("muted")
        self.receipt_note.setWordWrap(True)
        footer.addWidget(self.receipt_note, 1)
        self.view_fees = QPushButton("View fee register")
        self.view_fees.setObjectName("quiet")
        self.view_fees.clicked.connect(lambda: self.navigate.emit("fees"))
        footer.addWidget(self.view_fees)
        register_layout.addWidget(register_footer)
        details.addWidget(self.register, 7)

        self.finance_panel = QFrame()
        self.finance_panel.setObjectName("card")
        self.finance_panel.setMinimumWidth(246)
        self.finance_panel.setMaximumWidth(300)
        finance = QVBoxLayout(self.finance_panel)
        finance.setContentsMargins(0, 0, 0, 0)
        finance.setSpacing(0)
        finance.addWidget(section_header("Fee settlement"))
        scope = QLabel("ALL ISSUED CHALLANS")
        scope.setObjectName("eyebrow")
        scope.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scope.setContentsMargins(0, 18, 0, 0)
        finance.addWidget(scope)
        self.settlement = SettlementChart()
        finance.addWidget(self.settlement)
        legend = QWidget()
        legend_layout = QVBoxLayout(legend)
        legend_layout.setContentsMargins(20, 0, 20, 18)
        legend_layout.setSpacing(12)
        self.paid_amount = QLabel()
        self.balance_amount = QLabel()
        for color, name, value in (("#173e75", "Received", self.paid_amount), ("#c5a46d", "Outstanding", self.balance_amount)):
            row = QHBoxLayout()
            mark = QLabel()
            mark.setFixedSize(8, 8)
            mark.setStyleSheet("background: " + color + "; border-radius: 2px;")
            row.addWidget(mark)
            title = QLabel(name)
            title.setObjectName("muted")
            row.addWidget(title)
            row.addStretch()
            row.addWidget(value)
            legend_layout.addLayout(row)
        finance.addWidget(legend)
        chart_note = QLabel("Live balances across student accounts. Reversed entries are excluded.")
        chart_note.setObjectName("muted")
        chart_note.setWordWrap(True)
        chart_note.setContentsMargins(20, 0, 20, 20)
        finance.addWidget(chart_note)
        finance.addStretch()
        details.addWidget(self.finance_panel, 3)
        layout.addLayout(details, 1)

        self.services = QHBoxLayout()
        self.services.setSpacing(14)
        for key, title, subtitle in [("students", "Admissions office", "Student register and class allocation"), ("attendance", "Academic records", "Daily class attendance"), ("reports", "Accounts statements", "Collections and overdue balances")]:
            if not service.has_permission(key):
                continue
            item = QFrame()
            item.setObjectName("card")
            item_layout = QHBoxLayout(item)
            item_layout.setContentsMargins(17, 14, 17, 14)
            icon = QLabel()
            icon.setPixmap(line_icon(key, "#315b90", 24).pixmap(24, 24))
            item_layout.addWidget(icon)
            copy = QVBoxLayout()
            copy.setSpacing(4)
            link = QPushButton(title)
            link.setObjectName("quiet")
            link.setStyleSheet("text-align: left; padding: 0;")
            link.clicked.connect(lambda checked=False, name=key: self.navigate.emit(name))
            copy.addWidget(link)
            caption = QLabel(subtitle)
            caption.setObjectName("muted")
            caption.setWordWrap(True)
            copy.addWidget(caption)
            item_layout.addLayout(copy, 1)
            self.services.addWidget(item)
        layout.addLayout(self.services)

    def refresh(self):
        data = self.service.dashboard()
        user = self.service.user
        financial = user["role"] != "teacher"
        self.shortcut.setVisible(user["role"] in ("admin", "receptionist"))
        self.view_fees.setVisible(self.service.has_permission("fees"))
        self.finance_panel.setVisible(financial)
        while self.metrics.count():
            old_card = self.metrics.takeAt(0).widget()
            if old_card:
                old_card.hide(); old_card.setParent(None); old_card.deleteLater()
        self.metrics.addWidget(metric_card("Active enrollments", data["active_students"], "Student admission register"))
        if financial:
            self.metrics.addWidget(metric_card("Collected this month", money(data["month_collected"]), date.today().strftime("%B %Y") + " · confirmed receipts"))
            self.metrics.addWidget(metric_card("Outstanding fees", money(data["outstanding"]), "Current unpaid fee balances"))
            self.overdue.setText(f"{data['overdue_count']} overdue challan(s)")
            self.payments.setColumnCount(5)
            self.payments.setHorizontalHeaderLabels(["RECEIPT NO.", "STUDENT NAME", "DATE", "METHOD", "AMOUNT"])
            self.collections_title.setText("Recent payment receipts")
            rows = data.get("recent_payments", [])
            fill_table(self.payments, [[p["number"], p["student_name"], p["paid_on"][:10], p["method"], money(p["amount"])] for p in rows])
            self.empty.setVisible(not rows)
            challans = self.service.list_challans()
            paid = sum((Decimal(c["paid"]) for c in challans), Decimal(0))
            balance = sum((Decimal(c["balance"]) for c in challans), Decimal(0))
            self.settlement.set_totals(paid, balance)
            self.paid_amount.setText(money(paid))
            self.balance_amount.setText(money(balance))
            self.receipt_note.setText("Reversed payments are excluded.")
        else:
            self.metrics.addWidget(metric_card("Assigned classes", len(self.service.list_classes()), "Current teaching assignments"))
            self.overdue.setText("Academic office")
            self.payments.setColumnCount(3)
            self.payments.setHorizontalHeaderLabels(["CLASS / BATCH", "SCHEDULE", "TEACHER"])
            self.collections_title.setText("Assigned class register")
            classes = self.service.list_classes()
            fill_table(self.payments, [[c["name"], c["schedule"], c.get("teacher_name", "")] for c in classes])
            self.empty.setVisible(not classes)
            self.empty.setText("No teaching assignments are available. Contact the academy administrator.")
            self.receipt_note.setText("Attendance is available for your assigned classes.")
        header = self.payments.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        widths = ((0, 145), (2, 120), (3, 95), (4, 115)) if financial else ((0, 210), (2, 170))
        for index, width in widths:
            header.setSectionResizeMode(index, QHeaderView.ResizeMode.Interactive)
            self.payments.setColumnWidth(index, width)
        self.payments.set_flexible_column(1, 150)
        if financial:
            for row in range(self.payments.rowCount()):
                self.payments.item(row, 4).setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)


class MainWindow(QMainWindow):
    logout_requested = Signal()

    def __init__(self, service):
        super().__init__()
        from .admin import SettingsPage, UsersPage
        from .fees import FeesPage
        from .operations import AttendancePage, ReportsPage
        from .students import StudentsPage

        self.service = service
        self.setWindowTitle("Intellectual Nexus Academy | Administration")
        self.setWindowIcon(QIcon(seal_pixmap()))
        self.resize(1440, 940)
        self.setMinimumSize(1080, 740)
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)
        user = service.user

        utility = QFrame()
        utility.setObjectName("utilityBar")
        utility.setFixedHeight(29)
        utility_layout = QHBoxLayout(utility)
        utility_layout.setContentsMargins(28, 0, 28, 0)
        utility_layout.addWidget(QLabel("INTELLECTUAL NEXUS ACADEMY    /    STAFF ADMINISTRATION"))
        utility_layout.addStretch()
        utility_layout.addWidget(QLabel(date.today().strftime("%A, %d %B %Y")))
        root_layout.addWidget(utility)

        masthead = QFrame()
        masthead.setObjectName("masthead")
        masthead_layout = QHBoxLayout(masthead)
        masthead_layout.setContentsMargins(26, 15, 28, 16)
        masthead_layout.setSpacing(17)
        masthead_layout.addWidget(AcademySeal(65))
        academy = QVBoxLayout()
        academy.setSpacing(5)
        self.academy_label = QLabel(service.get_settings()["academy_name"])
        self.academy_label.setTextFormat(Qt.TextFormat.PlainText)
        self.academy_label.setObjectName("academyTitle")
        self.academy_label.setWordWrap(True)
        academy.addWidget(self.academy_label)
        subtitle = QLabel("STUDENT SERVICES  /  ACADEMIC RECORDS  /  ACCOUNTS")
        subtitle.setObjectName("mastheadSubtitle")
        academy.addWidget(subtitle)
        masthead_layout.addLayout(academy, 1)
        session = QLabel("LOCAL STAFF PORTAL")
        session.setObjectName("statusBadge")
        session.setFixedHeight(29)
        masthead_layout.addWidget(session, 0, Qt.AlignmentFlag.AlignVCenter)
        masthead_layout.addSpacing(17)
        profile = QVBoxLayout()
        profile.setSpacing(2)
        office = QLabel(ROLE_NAMES.get(user["role"], "Staff").upper())
        office.setObjectName("mastheadOffice")
        office.setAlignment(Qt.AlignmentFlag.AlignRight)
        profile.addWidget(office)
        self.account = QPushButton(user["full_name"].replace("&", "&&"))
        self.account.setObjectName("quiet")
        self.account.setToolTip("Change your account password")
        self.account.clicked.connect(self.change_password)
        profile.addWidget(self.account)
        masthead_layout.addLayout(profile)
        root_layout.addWidget(masthead)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("navigation")
        sidebar.setFixedWidth(224)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 22, 0, 18)
        side.setSpacing(0)
        caption = QLabel("   ACADEMY SERVICES")
        caption.setContentsMargins(18, 0, 0, 13)
        caption.setObjectName("navCaption")
        side.addWidget(caption)
        menu = QWidget()
        menu.setObjectName("navigationMenu")
        nav = QVBoxLayout(menu)
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(2)
        self.stack = PageStack()
        self.pages = {}
        self.nav_buttons = {}
        self.page_titles = {}
        page_types = [
            ("dashboard", "Overview", DashboardPage, ""),
            ("students", "Admissions", StudentsPage, "ACADEMIC SERVICES"),
            ("attendance", "Attendance", AttendancePage, "ACADEMIC SERVICES"),
            ("fees", "Fee ledger", FeesPage, "FINANCIAL RECORDS"),
            ("reports", "Reports", ReportsPage, "FINANCIAL RECORDS"),
            ("users", "Staff access", UsersPage, "ADMINISTRATION"),
            ("settings", "Administration", SettingsPage, "ADMINISTRATION"),
        ]
        last_group = ""
        for key, title, page_type, group in page_types:
            if not service.has_permission(key):
                continue
            if group and group != last_group:
                label = QLabel(group)
                label.setObjectName("navGroup")
                nav.addWidget(label)
            last_group = group
            page = page_type(service)
            page.changed.connect(self.refresh_current)
            self.pages[key] = page
            self.page_titles[key] = title
            self.stack.addWidget(page)
            button = QPushButton(title)
            button.setObjectName("nav")
            button.setIcon(line_icon(key))
            button.setIconSize(QSize(19, 19))
            button.setMinimumHeight(42)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, name=key: self.navigate(name))
            self.nav_buttons[key] = button
            nav.addWidget(button)
        nav.addStretch()
        menu_scroll = QScrollArea()
        menu_scroll.setWidgetResizable(True)
        menu_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        menu_scroll.setWidget(menu)
        side.addWidget(menu_scroll, 1)
        security = QFrame()
        security.setObjectName("notice")
        security_layout = QVBoxLayout(security)
        security_layout.setContentsMargins(14, 12, 14, 12)
        security_layout.setSpacing(5)
        security_title = QLabel("ACCOUNT SECURITY")
        security_title.setObjectName("eyebrow")
        security_layout.addWidget(security_title)
        security_copy = QLabel("Your session locks after 15 minutes of inactivity.")
        security_copy.setObjectName("muted")
        security_copy.setWordWrap(True)
        security_layout.addWidget(security_copy)
        side.addSpacing(12)
        side.addWidget(security)
        side.addSpacing(12)
        logout = QPushButton("Sign out")
        logout.setObjectName("navQuiet")
        logout.setIcon(line_icon("logout"))
        logout.clicked.connect(self.logout_requested)
        side.addWidget(logout)
        body.addWidget(sidebar)

        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        breadcrumb_bar = QFrame()
        breadcrumb_bar.setObjectName("breadcrumbBar")
        breadcrumb_layout = QHBoxLayout(breadcrumb_bar)
        breadcrumb_layout.setContentsMargins(30, 11, 30, 11)
        self.breadcrumb = QLabel()
        breadcrumb_layout.addWidget(self.breadcrumb)
        breadcrumb_layout.addStretch()
        breadcrumb_layout.addWidget(QLabel("ACADEMY MANAGEMENT SYSTEM"))
        content.addWidget(breadcrumb_bar)
        self.page_scroll = QScrollArea()
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setWidget(self.stack)
        content.addWidget(self.page_scroll, 1)
        body.addLayout(content, 1)
        root_layout.addLayout(body, 1)
        self.pages["dashboard"].navigate.connect(self.navigate)
        if "settings" in self.pages:
            self.pages["settings"].auth_required.connect(self.logout_requested)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().showMessage("Intellectual Nexus Academy   /   Internal administration")
        status = QLabel("Local records  ·  Offline workspace")
        status.setContentsMargins(0, 0, 16, 0)
        self.statusBar().addPermanentWidget(status)
        self.navigate("dashboard")

    def navigate(self, key):
        if key not in self.pages:
            return
        try:
            self.pages[key].refresh()
            self.stack.setCurrentWidget(self.pages[key])
            self.stack.updateGeometry()
            self.page_scroll.verticalScrollBar().setValue(0)
            self.breadcrumb.setText("Academy portal   /   " + self.page_titles[key])
            for name, button in self.nav_buttons.items():
                button.setChecked(name == key)
                button.setIcon(line_icon(name, "#173e75" if name == key else "#73859b"))
        except (ValueError, PermissionError, RuntimeError) as exc:
            show_error(self, exc)

    def refresh_current(self):
        try:
            if self.service.user is None:
                return
            self.stack.currentWidget().refresh()
            self.academy_label.setText(self.service.get_settings()["academy_name"])
        except (ValueError, PermissionError, RuntimeError) as exc:
            show_error(self, exc)

    def change_password(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Change your password")
        dialog.setMinimumWidth(420)
        layout = QFormLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        current = QLineEdit()
        new = QLineEdit()
        confirm = QLineEdit()
        for entry in (current, new, confirm):
            entry.setEchoMode(QLineEdit.EchoMode.Password)
        new.setPlaceholderText("At least 10 characters")
        layout.addRow("Current password", current)
        layout.addRow("New password", new)
        layout.addRow("Confirm password", confirm)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        layout.addRow(buttons)
        buttons.rejected.connect(dialog.reject)

        def save():
            try:
                if new.text() != confirm.text():
                    raise ValueError("The new passwords do not match.")
                self.service.change_password(current.text(), new.text())
                dialog.accept()
                success(self, "Your password has been changed.")
            except (ValueError, PermissionError, RuntimeError) as exc:
                show_error(dialog, exc)

        buttons.accepted.connect(save)
        dialog.exec()
