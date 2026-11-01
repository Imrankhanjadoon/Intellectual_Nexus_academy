"""European institutional palette, accessible type and paper-like records."""
from . import resources as _resources  # Register embedded Qt control icons.

STYLE = """
* { font-family: 'Segoe UI', 'DejaVu Sans', sans-serif; font-size: 13px; }
QMainWindow, QDialog { background: #f4f6f9; }
QWidget { color: #25354a; }
QWidget#documentPage, QWidget#dashboardPage, QStackedWidget { background: #f4f6f9; }
QWidget#navigationMenu { background: #ffffff; }
QLabel { background: transparent; }
QLabel#pageTitle { color: #173657; font-size: 26px; font-weight: 600; }
QLabel#muted { color: #68788b; font-size: 12px; }
QLabel#eyebrow, QLabel#fieldLabel { color: #536c88; font-size: 11px; font-weight: 600; }
QLabel#metric { color: #123766; font-size: 30px; font-weight: 600; }
QLabel#sectionTitle { color: #173657; font-size: 14px; font-weight: 600; }
QFrame#card, QWidget#card { background: #ffffff; border: 1px solid #dce4ee; border-radius: 4px; }
QFrame#summaryPanel { background: #ffffff; border: 1px solid #dce4ee; border-radius: 4px; }
QFrame#summaryCard { background: transparent; border: none; border-right: 1px solid #e4eaf2; border-radius: 0; }
QFrame#utilityBar { background: #123766; border: none; }
QFrame#utilityBar QLabel { color: #eaf0f8; font-size: 10px; }
QFrame#masthead { background: #ffffff; border: none; border-bottom: 1px solid #dce4ee; }
QLabel#academyTitle { font-family: Georgia, 'DejaVu Serif', serif; color: #123766; font-size: 27px; font-weight: 600; }
QLabel#mastheadSubtitle { color: #6a7a8e; font-size: 11px; }
QLabel#mastheadOffice { color: #536b88; font-size: 10px; font-weight: 600; }
QFrame#navigation { background: #ffffff; border: none; border-right: 1px solid #dce4ee; }
QLabel#navGroup { color: #8895a7; font-size: 10px; font-weight: 600; padding: 18px 17px 7px 17px; }
QLabel#navCaption { color: #173e75; font-size: 11px; font-weight: 600; }
QPushButton#nav { text-align: left; color: #53677f; background: transparent; border: none; border-left: 3px solid transparent; border-radius: 0; padding: 12px 14px; font-weight: 500; }
QPushButton#nav:hover { background: #f3f6fb; color: #173e75; }
QPushButton#nav:checked { background: #eaf0f9; color: #123766; border-left: 3px solid #255a9d; font-weight: 600; }
QPushButton#navQuiet { color: #53677f; background: #ffffff; text-align: left; border: 1px solid #dce4ee; border-radius: 3px; padding: 10px 14px; }
QPushButton#navQuiet:hover { background: #f3f6fb; }
QFrame#breadcrumbBar { background: #f4f6f9; border: none; border-bottom: 1px solid #e3e9f1; }
QFrame#breadcrumbBar QLabel { color: #73839a; font-size: 11px; }
QFrame#registerHeader { background: #f9fbfd; border: none; border-bottom: 1px solid #e0e7f0; }
QFrame#registerToolbar { background: #ffffff; border: none; border-bottom: 1px solid #e0e7f0; }
QFrame#registerActions { background: #fafbfd; border: none; border-top: 1px solid #e0e7f0; }
QLabel#countBadge { color: #26548b; background: #edf3fb; border: 1px solid #dae6f7; border-radius: 3px; padding: 6px 10px; font-size: 11px; }
QLabel#registerSummary { color: #677d96; font-size: 11px; padding: 4px 0; }
QFrame#notice { background: #f9fbff; border: 1px solid #dce6f2; border-left: 3px solid #c5a46d; border-radius: 3px; }
QFrame#footer { background: #ffffff; border: none; border-top: 1px solid #e0e7f0; }
QFrame#footer QLabel { color: #7c8a9c; font-size: 11px; }
QLabel#statusBadge { color: #2d5b81; background: #f0f5fb; border: 1px solid #dce6f1; border-radius: 3px; padding: 7px 10px; font-size: 10px; }
QPushButton { color: #34506f; background: #ffffff; border: 1px solid #cbd7e5; padding: 9px 16px; border-radius: 4px; font-weight: 600; min-height: 18px; }
QPushButton:hover { background: #f1f5fb; border-color: #91a9c7; }
QPushButton:pressed { background: #e5edf8; }
QPushButton:focus { outline: none; border: 1px solid #557eb5; }
QPushButton:disabled { color: #98a6b9; background: #f3f5f8; border-color: #e0e6ee; }
QPushButton#primary { color: #ffffff; background: #173e75; border-color: #173e75; }
QPushButton#primary:hover { background: #10325e; border-color: #10325e; }
QPushButton#primary:disabled { color: #f5f7fa; background: #a8b9cf; border-color: #a8b9cf; }
QPushButton#danger { color: #943c45; background: #fffafb; border-color: #dfc6cc; }
QPushButton#quiet { color: #265486; background: transparent; border: none; padding: 8px 10px; }
QPushButton#quiet:hover { background: #edf3fb; }
QPushButton#serviceLink { text-align: left; color: #234b7c; background: #ffffff; border: none; border-bottom: 1px solid #e6ebf3; border-radius: 0; padding: 14px 15px; font-size: 12px; font-weight: 500; }
QPushButton#serviceLink:hover { background: #f4f7fc; }
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox {
 color: #293c56; background: #ffffff; border: 1px solid #cbd6e5; border-radius: 3px;
 padding: 8px 10px; selection-background-color: #dce8f7; selection-color: #163c6e; min-height: 18px;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QDateEdit:focus, QDoubleSpinBox:focus { border: 1px solid #517db8; background: #ffffff; }
QLineEdit:disabled { background: #f2f5f9; color: #8f9eb0; }
QComboBox::drop-down, QDateEdit::drop-down { border: none; border-left: 1px solid #dce4ef; width: 27px; background: #f6f8fc; }
QComboBox::down-arrow, QDateEdit::down-arrow { image: url(:/nexus/arrow-down.svg); width: 13px; height: 13px; }
QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 22px; background: #f2f5fa; border-left: 1px solid #d5dfed; border-bottom: 1px solid #e1e7f1; }
QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 22px; background: #f2f5fa; border-left: 1px solid #d5dfed; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url(:/nexus/arrow-up.svg); width: 11px; height: 11px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url(:/nexus/arrow-down.svg); width: 11px; height: 11px; }
QComboBox QAbstractItemView { background: #ffffff; selection-background-color: #e7effb; selection-color: #173e75; padding: 4px; border: 1px solid #cbd6e5; }
QTableWidget { background: #ffffff; alternate-background-color: #fafbfd; border: 1px solid #dce4ee; border-radius: 2px; selection-background-color: #edf3fd; selection-color: #1b4273; }
QTableWidget#registerTable { border: none; border-radius: 0; }
QTableWidget::item { padding: 8px 11px; border-bottom: 1px solid #e9edf4; }
QTableWidget::item:selected { background: #edf3fd; color: #1b4273; }
QHeaderView::section { color: #6b7e98; background: #f4f7fb; padding: 12px 10px; border: none; border-bottom: 1px solid #dfe7f1; font-size: 10px; font-weight: 600; }
QTableCornerButton::section { background: #f4f7fb; border: none; }
QTabWidget::pane { border: none; background: transparent; padding-top: 12px; }
QTabBar::tab { color: #6e819b; background: transparent; padding: 12px 20px; border: none; border-bottom: 2px solid #dce4ef; font-weight: 500; }
QTabBar::tab:selected { color: #173e75; border-bottom: 2px solid #173e75; font-weight: 600; }
QTabBar::tab:hover:!selected { background: #eef3fb; }
QGroupBox { background: #ffffff; border: 1px solid #dce4ee; border-radius: 4px; margin-top: 14px; padding: 20px; padding-top: 24px; font-weight: 600; }
QGroupBox::title { color: #214c81; subcontrol-origin: margin; left: 18px; padding: 0 6px; }
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: #f1f4f8; width: 8px; border: none; }
QScrollBar::handle:vertical { background: #c6d2e2; border-radius: 3px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QStatusBar { color: #7d8b9e; background: #ffffff; border-top: 1px solid #dfe6ef; font-size: 10px; padding: 3px 10px; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QToolTip { color: #ffffff; background: #173e75; border: none; padding: 6px; }
"""
