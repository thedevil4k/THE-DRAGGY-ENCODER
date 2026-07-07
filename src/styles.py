# Window dimensions
from src.rect import Rect

# ──────────────────────────────────────────────
# New theme: Dark Cyan / Teal
# ──────────────────────────────────────────────

WINDOW = Rect(0, 0, 780, 720)
WINDOW_MIN = Rect(0, 0, 580, 520)
WINDOW_HALF = Rect(0, 0, WINDOW.w // 2, WINDOW.h // 2)

# Colors
BG_PRIMARY = "#0D1117"
BG_SECONDARY = "#161B22"
BG_TERTIARY = "#1C2128"
BORDER_DEFAULT = "#30363D"
BORDER_ACTIVE = "#00D4AA"
ACCENT_CYAN = "#00D4AA"
ACCENT_BLUE = "#58A6FF"
ACCENT_PURPLE = "#BC8CFF"
TEXT_PRIMARY = "#E6EDF3"
TEXT_SECONDARY = "#8B949E"
TEXT_MUTED = "#484F58"
STATUS_SUCCESS = "#00D4AA"
STATUS_WARNING = "#D29922"
STATUS_ERROR = "#F85149"

GLOBAL_STYLE = f"""
    QWidget {{
        background-color: {BG_PRIMARY};
        color: {TEXT_PRIMARY};
        font-family: 'Segoe UI', Inter, sans-serif;
        font-size: 13px;
    }}
"""

LABEL_STYLE = f"""
    QLabel {{
        qproperty-alignment: AlignCenter;
        color: {TEXT_SECONDARY};
        font-weight: bold;
    }}
"""

LABEL_LOG_STYLE = f"""
    QLabel {{
        qproperty-alignment: AlignLeft;
        background-color: {BG_SECONDARY};
        border: 1px solid {BORDER_DEFAULT};
        border-radius: 8px;
        padding: 8px;
        color: {TEXT_SECONDARY};
        font-size: 12px;
    }}
"""

ERROR_LABEL_STYLE = f"""
    QLabel {{
        background-color: #3D1214;
        color: {STATUS_ERROR};
        font-weight: bold;
        font-size: 13px;
        border: 1px solid {STATUS_ERROR};
        border-radius: 8px;
        qproperty-alignment: AlignCenter;
    }}
"""

# ── Buttons ──

BUTTON_DISABLED_STYLE = f"""
    QPushButton {{
        background-color: {BG_TERTIARY};
        color: {TEXT_MUTED};
        font-weight: bold;
        border: 1px solid {BORDER_DEFAULT};
        border-radius: 8px;
    }}
"""

BUTTON_SELECT_STYLE = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {ACCENT_BLUE}, stop:1 {ACCENT_CYAN});
        color: {BG_PRIMARY};
        font-weight: bold;
        font-size: 14px;
        border: none;
        border-radius: 8px;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #79C0FF, stop:1 #2EE8B5);
    }}
    QPushButton:pressed {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {ACCENT_BLUE}, stop:1 {ACCENT_CYAN});
        padding-top: 2px;
    }}
"""

BUTTON_COMPRESS_STYLE = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {ACCENT_CYAN}, stop:1 {ACCENT_BLUE});
        color: {BG_PRIMARY};
        font-weight: bold;
        font-size: 14px;
        border: none;
        border-radius: 8px;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #2EE8B5, stop:1 #79C0FF);
    }}
    QPushButton:pressed {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {ACCENT_CYAN}, stop:1 {ACCENT_BLUE});
        padding-top: 2px;
    }}
"""

BUTTON_ABORT_STYLE = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #F85149, stop:1 #FF6E6E);
        color: #FFFFFF;
        font-weight: bold;
        font-size: 13px;
        border: none;
        border-radius: 8px;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #FF6E6E, stop:1 #F85149);
    }}
    QPushButton:pressed {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #F85149, stop:1 #FF6E6E);
        padding-top: 2px;
    }}
"""

BUTTON_ADD_QUEUE_STYLE = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {ACCENT_CYAN}, stop:1 {ACCENT_BLUE});
        color: {BG_PRIMARY};
        font-weight: bold;
        font-size: 13px;
        border: none;
        border-radius: 8px;
        padding: 8px;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #2EE8B5, stop:1 #79C0FF);
    }}
    QPushButton:pressed {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {ACCENT_CYAN}, stop:1 {ACCENT_BLUE});
        padding-top: 2px;
    }}
"""

BUTTON_START_STYLE = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {ACCENT_CYAN}, stop:1 {ACCENT_BLUE});
        color: {BG_PRIMARY};
        font-weight: bold;
        font-size: 14px;
        border: none;
        border-radius: 8px;
        padding: 8px 20px;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #2EE8B5, stop:1 #79C0FF);
    }}
    QPushButton:pressed {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {ACCENT_CYAN}, stop:1 {ACCENT_BLUE});
        padding-top: 2px;
    }}
    QPushButton:disabled {{
        background-color: {BG_TERTIARY};
        color: {TEXT_MUTED};
        border: 1px solid {BORDER_DEFAULT};
    }}
"""

BUTTON_CLEAR_STYLE = f"""
    QPushButton {{
        background-color: transparent;
        color: {TEXT_SECONDARY};
        font-weight: bold;
        font-size: 12px;
        border: 1px solid {BORDER_DEFAULT};
        border-radius: 8px;
        padding: 8px 16px;
    }}
    QPushButton:hover {{
        border-color: {STATUS_ERROR};
        color: {STATUS_ERROR};
    }}
"""

# ── Progress Bar ──

PROGRESS_BAR_STYLE = f"""
    QProgressBar {{
        background-color: {BG_SECONDARY};
        border: 1px solid {BORDER_DEFAULT};
        border-radius: 8px;
        text-align: center;
        color: {TEXT_PRIMARY};
        font-weight: bold;
        font-size: 12px;
    }}
    QProgressBar::chunk {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {ACCENT_CYAN}, stop:1 {ACCENT_BLUE});
        border-radius: 7px;
    }}
"""

# ── Inputs ──

LINEEDIT_STYLE = f"""
    QLineEdit {{
        background-color: {BG_SECONDARY};
        border: 1px solid {BORDER_DEFAULT};
        border-radius: 6px;
        padding: 6px 8px;
        color: {TEXT_PRIMARY};
        qproperty-alignment: AlignCenter;
    }}
    QLineEdit:focus {{
        border: 1px solid {ACCENT_CYAN};
    }}
"""

COMBOBOX_STYLE = f"""
    QComboBox {{
        background-color: {BG_SECONDARY};
        border: 1px solid {BORDER_DEFAULT};
        border-radius: 6px;
        padding: 6px 8px;
        color: {TEXT_PRIMARY};
    }}
    QComboBox:hover {{
        border: 1px solid {TEXT_MUTED};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox::down-arrow {{
        image: none;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 5px solid {TEXT_SECONDARY};
        margin-right: 8px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {BG_SECONDARY};
        border: 1px solid {BORDER_DEFAULT};
        selection-background-color: {BG_TERTIARY};
        selection-color: {ACCENT_CYAN};
        color: {TEXT_PRIMARY};
        outline: none;
        padding: 4px;
    }}
"""

CHECKBOX_STYLE = """
    QCheckBox::indicator {
        width: 20px;
        height: 20px;
    }
"""

# ── Pipeline Steps ──

PIPELINE_STEP_STYLE = f"""
    QWidget {{
        background-color: transparent;
    }}
"""

PIPELINE_CIRCLE_OFF = f"""
    QWidget {{
        background-color: {BG_SECONDARY};
        border: 2px solid {BORDER_DEFAULT};
        border-radius: 30px;
    }}
    QWidget:hover {{
        border-color: {TEXT_MUTED};
    }}
"""

PIPELINE_CIRCLE_ON = f"""
    QWidget {{
        background-color: rgba(0, 212, 170, 0.15);
        border: 2px solid {ACCENT_CYAN};
        border-radius: 30px;
    }}
"""

PIPELINE_CIRCLE_PROCESSING = f"""
    QWidget {{
        background-color: rgba(88, 166, 255, 0.15);
        border: 2px solid {ACCENT_BLUE};
        border-radius: 30px;
    }}
"""

PIPELINE_CIRCLE_DONE = f"""
    QWidget {{
        background-color: rgba(0, 212, 170, 0.2);
        border: 2px solid {ACCENT_CYAN};
        border-radius: 30px;
    }}
"""

PIPELINE_CIRCLE_DISABLED = f"""
    QWidget {{
        background-color: {BG_TERTIARY};
        border: 2px solid {BORDER_DEFAULT};
        border-radius: 30px;
        opacity: 0.5;
    }}
"""

PIPELINE_CIRCLE_ALWAYS_ON = f"""
    QWidget {{
        background-color: rgba(0, 212, 170, 0.1);
        border: 2px solid {ACCENT_CYAN};
        border-radius: 30px;
    }}
"""

PIPELINE_ARROW = f"""
    QLabel {{
        color: {ACCENT_CYAN};
        font-size: 18px;
        font-weight: bold;
        qproperty-alignment: AlignCenter;
    }}
"""

PIPELINE_ARROW_INACTIVE = f"""
    QLabel {{
        color: {BORDER_DEFAULT};
        font-size: 18px;
        font-weight: bold;
        qproperty-alignment: AlignCenter;
    }}
"""

PIPELINE_LABEL_ON = f"""
    QLabel {{
        color: {ACCENT_CYAN};
        font-size: 10px;
        font-weight: bold;
        qproperty-alignment: AlignCenter;
    }}
"""

PIPELINE_LABEL_OFF = f"""
    QLabel {{
        color: {TEXT_MUTED};
        font-size: 10px;
        qproperty-alignment: AlignCenter;
    }}
"""

PIPELINE_STEP_TITLE = f"""
    QLabel {{
        color: {TEXT_PRIMARY};
        font-size: 12px;
        font-weight: bold;
    }}
"""

# ── Settings Panel ──

SETTINGS_PANEL = f"""
    QWidget {{
        background-color: {BG_SECONDARY};
        border: 1px solid {BORDER_DEFAULT};
        border-radius: 10px;
        padding: 12px;
    }}
"""

SETTINGS_ROW_LABEL = f"""
    QLabel {{
        color: {TEXT_SECONDARY};
        font-size: 12px;
        font-weight: bold;
    }}
"""

# ── Info Cards ──

AI_INFO_STYLE = f"""
    QLabel {{
        background-color: {BG_TERTIARY};
        border: 1px solid {BORDER_DEFAULT};
        border-radius: 8px;
        padding: 8px;
        color: {TEXT_SECONDARY};
        font-size: 11px;
    }}
"""

AI_WARNING_STYLE = f"""
    QLabel {{
        color: {STATUS_WARNING};
        font-style: italic;
        font-size: 11px;
        qproperty-alignment: AlignCenter;
    }}
"""

AI_SECTION_TITLE = f"""
    QLabel {{
        color: {ACCENT_CYAN};
        font-weight: bold;
        font-size: 13px;
        qproperty-alignment: AlignCenter;
    }}
"""

AI_SEPARATOR_STYLE = f"""
    QFrame {{
        background-color: {BORDER_DEFAULT};
        max-height: 1px;
        border: none;
    }}
"""

# ── Queue Items ──

QUEUE_ITEM_STYLE = f"""
    QFrame {{
        background-color: {BG_TERTIARY};
        border: 1px solid {BORDER_DEFAULT};
        border-radius: 8px;
        padding: 4px;
    }}
    QFrame:hover {{
        border-color: {TEXT_MUTED};
    }}
"""

QUEUE_ITEM_ACTIVE_STYLE = f"""
    QFrame {{
        background-color: rgba(0, 212, 170, 0.05);
        border: 1px solid {ACCENT_CYAN};
        border-radius: 8px;
        padding: 4px;
    }}
"""

QUEUE_ITEM_DONE_STYLE = f"""
    QFrame {{
        background-color: rgba(0, 212, 170, 0.08);
        border: 1px solid rgba(0, 212, 170, 0.3);
        border-radius: 8px;
        padding: 4px;
    }}
"""

QUEUE_TITLE_STYLE = f"""
    QLabel {{
        color: {TEXT_PRIMARY};
        font-weight: bold;
        font-size: 12px;
    }}
"""

QUEUE_SUMMARY_STYLE = f"""
    QLabel {{
        color: {TEXT_SECONDARY};
        font-size: 11px;
    }}
"""

QUEUE_REMOVE_BTN = f"""
    QPushButton {{
        background-color: transparent;
        color: {TEXT_MUTED};
        border: none;
        font-size: 14px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        color: {STATUS_ERROR};
    }}
"""

QUEUE_EMPTY_STYLE = f"""
    QLabel {{
        color: {TEXT_MUTED};
        font-style: italic;
        font-size: 12px;
        qproperty-alignment: AlignCenter;
    }}
"""

# ── Section Headers ──

SECTION_HEADER_STYLE = f"""
    QLabel {{
        color: {ACCENT_CYAN};
        font-weight: bold;
        font-size: 14px;
        padding: 4px 0px;
    }}
"""

# ── Scrollbar ──

SCROLLBAR_STYLE = f"""
    QScrollBar:vertical {{
        background-color: {BG_PRIMARY};
        width: 8px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background-color: {BORDER_DEFAULT};
        min-height: 30px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {TEXT_MUTED};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}
"""

# ── Gaps ──
H_GAP = 10
V_GAP = 7
