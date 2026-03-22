# Window dimensions
from src.rect import Rect


WINDOW = Rect(0, 0, 400, 680)
WINDOW_HALF = Rect(0, 0, WINDOW.w // 2, WINDOW.h // 2)

GLOBAL_STYLE = """
    QWidget {
        background-color: #1E1E2E;
        color: #CDD6F4;
        font-family: 'Segoe UI', Inter, sans-serif;
        font-size: 13px;
    }
"""

LABEL_STYLE = """
    QLabel {
        qproperty-alignment: AlignCenter;
        color: #A6ADC8;
        font-weight: bold;
    }
"""

LABEL_LOG_STYLE = """
    QLabel {
        qproperty-alignment: AlignCenter;
        background-color: #181825;
        border: 1px solid #313244;
        border-radius: 8px;
        padding: 5px;
        color: #BAC2DE;
    }
"""

ERROR_LABEL_STYLE = """
    QLabel {
        background-color: #451b23;
        color: #f38ba8;
        font-weight: bold;
        font-size: 13px;
        border: 1px solid #f38ba8;
        border-radius: 8px;
        qproperty-alignment: AlignCenter;
    }
"""

BUTTON_DISABLED_STYLE = """
    QPushButton {
        background-color: #313244;
        color: #585B70;
        font-weight: bold;
        border: none;
        border-radius: 8px;
    }
"""

BUTTON_SELECT_STYLE = """
    QPushButton {
        background-color: #89B4FA;
        color: #11111B;
        font-weight: bold;
        font-size: 14px;
        border: none;
        border-radius: 8px;
    }
    QPushButton:hover {
        background-color: #B4BEFE;
    }
    QPushButton:pressed {
        background-color: #89B4FA;
        padding-top: 2px;
    }
"""

BUTTON_COMPRESS_STYLE = """
    QPushButton {
        background-color: #A6E3A1;
        color: #11111B;
        font-weight: bold;
        font-size: 14px;
        border: none;
        border-radius: 8px;
    }
    QPushButton:hover {
        background-color: #94E2D5;
    }
    QPushButton:pressed {
        background-color: #A6E3A1;
        padding-top: 2px;
    }
"""

BUTTON_ABORT_STYLE = """
    QPushButton {
        background-color: #F38BA8;
        color: #11111B;
        font-weight: bold;
        font-size: 14px;
        border: none;
        border-radius: 8px;
    }
    QPushButton:hover {
        background-color: #EBA0AC;
    }
    QPushButton:pressed {
        background-color: #F38BA8;
        padding-top: 2px;
    }
"""

PROGRESS_BAR_STYLE = """
    QProgressBar {
        background-color: #181825;
        border: 1px solid #313244;
        border-radius: 8px;
        text-align: center;
        color: #CDD6F4;
        font-weight: bold;
    }
    QProgressBar::chunk {
        background-color: #A6E3A1;
        border-radius: 7px;
    }
"""

CHECKBOX_STYLE = """
    QCheckBox::indicator {
        width: 20px;
        height: 20px;
    }
"""

LINEEDIT_STYLE = """
    QLineEdit {
        background-color: #181825;
        border: 1px solid #313244;
        border-radius: 6px;
        padding: 4px;
        color: #CDD6F4;
        qproperty-alignment: AlignCenter;
    }
    QLineEdit:focus {
        border: 1px solid #89B4FA;
    }
"""

COMBOBOX_STYLE = """
    QComboBox {
        background-color: #181825;
        border: 1px solid #313244;
        border-radius: 6px;
        padding: 4px 8px;
        color: #CDD6F4;
    }
    QComboBox:hover {
        border: 1px solid #585B70;
    }
    QComboBox::drop-down {
        border: none;
        width: 20px;
    }
    QComboBox::down-arrow {
        image: none;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 5px solid #A6ADC8;
        margin-right: 8px;
    }
    QComboBox QAbstractItemView {
        background-color: #181825;
        border: 1px solid #313244;
        selection-background-color: #313244;
        color: #CDD6F4;
        outline: none;
    }
"""


# Gaps
H_GAP = 10  # Horizontal gap
V_GAP = 7   # Vertical gap

# Buttons and elements
SELECT_BUTTON = Rect(
    H_GAP,  # Start with H_GAP from left
    V_GAP,  # Start with V_GAP from top
    (WINDOW.w - (H_GAP * 3)) // 2,  # Half width
    50,
)

OUTPUT_BUTTON = Rect(
    SELECT_BUTTON.x + SELECT_BUTTON.w + H_GAP,
    V_GAP,
    SELECT_BUTTON.w,
    50,
)

COMPRESS_BUTTON = Rect(
    H_GAP,
    SELECT_BUTTON.y + SELECT_BUTTON.h + V_GAP,
    (WINDOW.w - (H_GAP * 3)) // 2,  # Half width minus gaps
    50,
)

ABORT_BUTTON = Rect(
    COMPRESS_BUTTON.x + COMPRESS_BUTTON.w + H_GAP,
    COMPRESS_BUTTON.y,
    COMPRESS_BUTTON.w,
    COMPRESS_BUTTON.h,
)

FILE_SIZE_LABEL = Rect(
    H_GAP,
    COMPRESS_BUTTON.y + COMPRESS_BUTTON.h + V_GAP,
    100,
    25,
)

FILE_SIZE_ENTRY = Rect(
    FILE_SIZE_LABEL.x + FILE_SIZE_LABEL.w + H_GAP,
    FILE_SIZE_LABEL.y,
    WINDOW.w - (FILE_SIZE_LABEL.x + FILE_SIZE_LABEL.w + H_GAP * 2),
    25,
)

DEVICE_LABEL = Rect(
    H_GAP,
    FILE_SIZE_LABEL.y + FILE_SIZE_LABEL.h + V_GAP,
    100,
    25,
)

DEVICE_COMBOBOX = Rect(
    DEVICE_LABEL.x + DEVICE_LABEL.w + H_GAP,
    DEVICE_LABEL.y,
    WINDOW.w - (DEVICE_LABEL.x + DEVICE_LABEL.w + H_GAP * 2),
    25,
)

CODEC_LABEL = Rect(
    H_GAP,
    DEVICE_LABEL.y + DEVICE_LABEL.h + V_GAP,
    100,
    25,
)

CODEC_COMBOBOX = Rect(
    CODEC_LABEL.x + CODEC_LABEL.w + H_GAP,
    CODEC_LABEL.y,
    WINDOW.w - (CODEC_LABEL.x + CODEC_LABEL.w + H_GAP * 2),
    25,
)

EXPORT_LABEL = Rect(
    H_GAP,
    CODEC_LABEL.y + CODEC_LABEL.h + V_GAP,
    100,
    25,
)

EXPORT_COMBOBOX = Rect(
    EXPORT_LABEL.x + EXPORT_LABEL.w + H_GAP,
    EXPORT_LABEL.y,
    WINDOW.w - (EXPORT_LABEL.x + EXPORT_LABEL.w + H_GAP * 2),
    25,
)

AUDIO_LABEL = Rect(
    H_GAP,
    EXPORT_LABEL.y + EXPORT_LABEL.h + V_GAP,
    100,
    25,
)

AUDIO_COMBOBOX = Rect(
    AUDIO_LABEL.x + AUDIO_LABEL.w + H_GAP,
    AUDIO_LABEL.y,
    WINDOW.w - (AUDIO_LABEL.x + AUDIO_LABEL.w + H_GAP * 2),
    25,
)

PROGRESS_BAR = Rect(
    H_GAP,
    WINDOW.h - V_GAP - 25,
    WINDOW.w - (H_GAP * 2),
    25,
)

LOG_AREA = Rect(
    H_GAP,
    PROGRESS_BAR.y - 80 - V_GAP,
    WINDOW.w - (H_GAP * 2),
    80,
)

ERROR_LABEL = Rect(
    H_GAP,
    LOG_AREA.y - 40 - V_GAP,
    WINDOW.w - (H_GAP * 2),
    40,
)

INFO_PATH_LABEL = Rect(
    H_GAP,
    AUDIO_LABEL.y + AUDIO_LABEL.h + V_GAP,
    WINDOW.w - (H_GAP * 2),
    60,
)

INFO_SIZE_LABEL = Rect(
    H_GAP,
    INFO_PATH_LABEL.y + INFO_PATH_LABEL.h + V_GAP,
    WINDOW.w - (H_GAP * 2),
    20,
)

INFO_QUALITY_LABEL = Rect(
    H_GAP,
    INFO_SIZE_LABEL.y + INFO_SIZE_LABEL.h + V_GAP,
    WINDOW.w - (H_GAP * 2),
    75,
)
