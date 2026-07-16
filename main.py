import json
import re
import sys
import os
import platform
import subprocess
import psutil
from pathlib import Path


# Force UTF-8 on stdout/stderr so non-ASCII ffmpeg output (or UI labels with
# emojis) never triggers a 'charmap' codec error inside this process.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


import src.globals as g
from notifypy import Notify
from src.thread import CompressionThread, PreviewThread, get_video_metadata, get_video_length, human_readable_size
from src.loader import LoadingWindow
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QPushButton,
    QFileDialog,
    QLabel,
    QLineEdit,
    QProgressBar,
    QComboBox,
    QVBoxLayout,
    QHBoxLayout,
    QSpacerItem,
    QSizePolicy,
    QSystemTrayIcon,
    QMenu,
    QFrame,
    QStackedWidget,
    QScrollArea,
    QCheckBox,
    QSlider,
    QTimeEdit,
)
from PySide6.QtWidgets import QDialog
from PySide6.QtGui import QIcon, QAction, QFont, QPainter, QColor, QPolygon, QPixmap
from PySide6.QtCore import Qt, QEvent, Signal, QPoint, QTimer, QRect, QTime
import ctypes
from src.styles import (
    WINDOW, WINDOW_MIN, GLOBAL_STYLE, BG_PRIMARY, BG_SECONDARY, BG_TERTIARY,
    BORDER_DEFAULT, ACCENT_CYAN, ACCENT_BLUE, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    BUTTON_SELECT_STYLE, BUTTON_COMPRESS_STYLE, BUTTON_ABORT_STYLE,
    BUTTON_DISABLED_STYLE, BUTTON_ADD_QUEUE_STYLE, BUTTON_START_STYLE,
    LINEEDIT_STYLE, COMBOBOX_STYLE, LABEL_STYLE, LABEL_LOG_STYLE,
    ERROR_LABEL_STYLE, PROGRESS_BAR_STYLE, AI_INFO_STYLE, AI_WARNING_STYLE,
    PIPELINE_CIRCLE_OFF, PIPELINE_CIRCLE_ON, PIPELINE_CIRCLE_ALWAYS_ON,
    PIPELINE_CIRCLE_DISABLED, PIPELINE_CIRCLE_PROCESSING, PIPELINE_CIRCLE_DONE,
    PIPELINE_ARROW, PIPELINE_ARROW_INACTIVE, PIPELINE_LABEL_ON, PIPELINE_LABEL_OFF,
    SETTINGS_PANEL, SETTINGS_ROW_LABEL, SCROLLBAR_STYLE,
)

window = None


def load_settings() -> dict:
    base_data_dir = os.path.join(os.getenv("APPDATA", ""), "DraggyEncoder") if platform.system() == "Windows" else os.path.expanduser("~/.draggy_encoder")
    settings_path = Path(base_data_dir) / "settings.json"
    try:
        if settings_path.exists():
            return json.loads(settings_path.read_text())
        default_settings_path = Path(g.res_dir) / "settings.json"
        if default_settings_path.exists():
            return json.loads(default_settings_path.read_text())
    except Exception as e:
        print(f"Error loading settings: {e}")
    return g.DEFAULT_SETTINGS


def save_settings(settings):
    base_data_dir = os.path.join(os.getenv("APPDATA", ""), "DraggyEncoder") if platform.system() == "Windows" else os.path.expanduser("~/.draggy_encoder")
    settings_path = Path(base_data_dir) / "settings.json"
    try:
        os.makedirs(base_data_dir, exist_ok=True)
        settings_path.write_text(json.dumps(settings, indent=4))
    except Exception as e:
        print(f"Error saving settings: {e}")


def format_seconds_to_mm_ss(s):
    if s is None or s == "":
        return ""
    try:
        s = max(0.0, float(s))
    except (ValueError, TypeError):
        return ""
    if s <= 0:
        return "00:00:00"
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(round(s - h * 3600 - m * 60))
    if h > 0:
        return f"{h:02d}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


def kill_ffmpeg():
    if platform.system() == "Windows":
        try:
            subprocess.run(["taskkill", "/F", "/IM", "ffmpeg.exe", "/T"],
                           creationflags=0x08000000,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    else:
        for proc in psutil.process_iter():
            try:
                if "ffmpeg" in proc.name().lower():
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue


def create_setting_row(label_text, widget):
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)
    label = QLabel(label_text)
    label.setFixedWidth(90)
    label.setStyleSheet(SETTINGS_ROW_LABEL)
    if isinstance(widget, QComboBox):
        widget.setStyleSheet(COMBOBOX_STYLE)
    elif isinstance(widget, QLineEdit):
        widget.setStyleSheet(LINEEDIT_STYLE)
    row.addWidget(label)
    row.addWidget(widget)
    return row


def _get_ai_device_options():
    """Return list of AI device options for combos."""
    options = ["Auto"]
    try:
        from src.ai_tools import detect_gpu_devices
        gpus = detect_gpu_devices()
        for gpu in gpus:
            label = f"GPU {gpu['id']} ({gpu['name']})"
            if gpu["type"] == "integrated":
                label += " [iGPU]"
            else:
                label += " [Dedicated]"
            options.append(label)
    except Exception:
        pass
    options.append("CPU")
    return options


def _parse_ai_device(device_text):
    """Parse AI device combo text to gpu_id or None/CPU string."""
    if not device_text or device_text == "Auto":
        return None  # let the tool auto-detect
    if device_text == "CPU":
        return -1  # for ncnn: -1 = CPU; for ONNX: "cpu"
    # e.g. "GPU 0 (NVIDIA GeForce...) [Dedicated]"
    import re
    m = re.match(r"GPU\s+(\d+)", device_text)
    if m:
        return int(m.group(1))
    return None


# ──────────────────────────────────────────────
# Pipeline Step Widget (Circle)
# ──────────────────────────────────────────────

def _load_step_icon(step_name):
    """Load and scale icon from src/assets/ for a pipeline step."""
    icon_map = {
        "import": "Import.png",
        "upscale": "AI Upscaling.png",
        "interpolate": "AI Interpolation.png",
        "colorize": "AI Colorize.png",
        "compress": "Export.png",
    }
    filename = icon_map.get(step_name)
    if not filename:
        return None
    path = Path(g.root_dir) / "src" / "assets" / filename
    if not path.exists():
        return None
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return None
    # Scale to 40x40 keeping aspect ratio, centered in 56x56 circle
    return pixmap.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)


class PipelineStep(QWidget):
    step_clicked = Signal(str)

    STEP_CONFIG = {
        "import":      {"label": "Import",    "always_on": True, "draggable": False},
        "upscale":     {"label": "Upscale",   "always_on": False, "draggable": True},
        "interpolate": {"label": "Interp",    "always_on": False, "draggable": True},
        "colorize":    {"label": "Colorize",  "always_on": False, "draggable": True},
        "compress":    {"label": "Compress",  "always_on": True, "draggable": False},
    }

    def __init__(self, step_name, parent=None):
        super().__init__(parent)
        self.step_name = step_name
        self._enabled = step_name in ("import", "compress")
        self._state = "done" if step_name in ("import", "compress") else "off"
        self.config = self.STEP_CONFIG[step_name]
        self.setFixedSize(64, 80)
        self.setCursor(Qt.PointingHandCursor if not self.config["draggable"] else Qt.OpenHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.circle = QWidget()
        self.circle.setFixedSize(56, 56)
        cl = QVBoxLayout(self.circle)
        cl.setContentsMargins(0, 0, 0, 0)

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent; border: none;")

        # Load and set icon from assets
        pixmap = _load_step_icon(step_name)
        if pixmap and not pixmap.isNull():
            self._using_pixmap = True
            self.icon_label.setPixmap(pixmap)
        else:
            self._using_pixmap = False
            fallback_icons = {"import": "▶", "upscale": "⬆", "interpolate": "🎞", "colorize": "🎨", "compress": "📦"}
            self.icon_label.setText(fallback_icons.get(step_name, "?"))
            font = QFont("Segoe UI", 18)
            self.icon_label.setFont(font)

        cl.addWidget(self.icon_label)

        self.text_label = QLabel(self.config["label"])
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setStyleSheet(PIPELINE_LABEL_OFF)
        self.text_label.setFixedHeight(16)

        layout.addWidget(self.circle, alignment=Qt.AlignCenter)
        layout.addWidget(self.text_label, alignment=Qt.AlignCenter)

        self._opacity_effect = None
        self._update_style()
        self._update_text()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self.config["always_on"]:
                if self._state == "off":
                    self._state = "on"
                    self._enabled = True
                else:
                    self._state = "off"
                    self._enabled = False
                self._update_style()
                self._update_text()
            self.step_clicked.emit(self.step_name)

    def _update_style(self):
        if self._state == "processing":
            style = PIPELINE_CIRCLE_PROCESSING
        elif self._state == "done":
            style = PIPELINE_CIRCLE_ALWAYS_ON
        elif self._state == "on":
            style = PIPELINE_CIRCLE_ON
        elif self.config["always_on"]:
            style = PIPELINE_CIRCLE_ALWAYS_ON
        else:
            style = PIPELINE_CIRCLE_OFF
        self.circle.setStyleSheet(style)

        is_active = self._state in ("on", "done", "processing") or self.config["always_on"]
        if self._using_pixmap:
            if is_active:
                if self._opacity_effect:
                    self.icon_label.setGraphicsEffect(None)
                    self._opacity_effect = None
            else:
                from PySide6.QtWidgets import QGraphicsOpacityEffect
                self._opacity_effect = QGraphicsOpacityEffect()
                self._opacity_effect.setOpacity(0.35)
                self.icon_label.setGraphicsEffect(self._opacity_effect)
        else:
            if is_active:
                self.icon_label.setStyleSheet(f"color: {ACCENT_CYAN}; background: transparent; border: none;")
            else:
                self.icon_label.setStyleSheet(f"color: {TEXT_MUTED}; background: transparent; border: none;")

    def _update_text(self):
        if self._state in ("on", "done", "processing") or self.config["always_on"]:
            self.text_label.setStyleSheet(PIPELINE_LABEL_ON)
        else:
            self.text_label.setStyleSheet(PIPELINE_LABEL_OFF)

    def is_enabled(self):
        return self._enabled

    def set_state(self, state):
        self._state = state
        self._enabled = state != "off"
        self._update_style()
        self._update_text()


class PipelineArrow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 56)
        self._active = False

    def set_active(self, active):
        self._active = active
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor(ACCENT_CYAN) if self._active else QColor(BORDER_DEFAULT)
        painter.setPen(color)
        painter.setBrush(color)
        w, h = self.width(), self.height()
        mid_y = h // 2
        painter.drawLine(4, mid_y, w - 12, mid_y)
        arrow = QPolygon([QPoint(w - 12, mid_y - 6), QPoint(w - 3, mid_y), QPoint(w - 12, mid_y + 6)])
        painter.drawPolygon(arrow)
        painter.end()


class ReorderButton(QPushButton):
    """Small arrow button for reordering pipeline steps."""
    def __init__(self, direction, parent=None):
        super().__init__(parent)
        self.direction = direction
        text = "◂" if direction == "left" else "▸"
        self.setText(text)
        self.setFixedSize(18, 18)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {BG_TERTIARY};
                color: {TEXT_MUTED};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: 9px;
                font-size: 10px;
                font-weight: bold;
                padding: 0;
            }}
            QPushButton:hover {{
                color: {ACCENT_CYAN};
                border-color: {ACCENT_CYAN};
            }}
        """)


class PipelineWidget(QWidget):
    order_changed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.steps = {}
        self.arrows = []
        self.reorder_buttons = []
        self.step_names = ["import", "upscale", "interpolate", "colorize", "compress"]

        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(20, 8, 20, 8)
        self.main_layout.addStretch()
        self.main_layout.addStretch()

    def _init_steps(self):
        """Create step widgets and build layout. Called once after __init__."""
        for name in self.step_names:
            step = PipelineStep(name)
            step.step_clicked.connect(self._on_step_clicked)
            self.steps[name] = step
        self._build_pipeline()

    def _build_pipeline(self):
        """Build the pipeline layout from current step_names order."""
        if not self.steps:
            return
        # Remove all widgets from layout
        self.reorder_buttons.clear()
        while self.main_layout.count():
            item = self.main_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
        for arrow in self.arrows:
            arrow.deleteLater()
        self.arrows.clear()

        self.main_layout.addStretch()

        for i, name in enumerate(self.step_names):
            is_ai = name in ("upscale", "interpolate", "colorize")

            if is_ai:
                btn_left = ReorderButton("left")
                btn_left.clicked.connect(lambda checked, n=name: self._move_step(n, -1))
                self.reorder_buttons.append(btn_left)
                self.main_layout.addWidget(btn_left, alignment=Qt.AlignCenter)

            self.main_layout.addWidget(self.steps[name], alignment=Qt.AlignCenter)

            if is_ai:
                btn_right = ReorderButton("right")
                btn_right.clicked.connect(lambda checked, n=name: self._move_step(n, 1))
                self.reorder_buttons.append(btn_right)
                self.main_layout.addWidget(btn_right, alignment=Qt.AlignCenter)

            if i < len(self.step_names) - 1:
                arrow = PipelineArrow()
                self.arrows.append(arrow)
                self.main_layout.addWidget(arrow, alignment=Qt.AlignCenter)

        self.main_layout.addStretch()
        self._update_arrows()

    def _move_step(self, step_name, direction):
        """Move an AI step left (-1) or right (+1)."""
        ai_steps = ["upscale", "interpolate", "colorize"]
        if step_name not in ai_steps:
            return
        idx = self.step_names.index(step_name)
        new_idx = idx + direction
        if new_idx < 1 or new_idx >= len(self.step_names) - 1:
            return
        if self.step_names[new_idx] not in ai_steps:
            return
        self.step_names[idx], self.step_names[new_idx] = self.step_names[new_idx], self.step_names[idx]
        self._build_pipeline()
        self._on_step_clicked(step_name)
        self.order_changed.emit(self.get_ai_order())

    def get_ai_order(self):
        """Return the current order of AI steps."""
        ai_steps = ["upscale", "interpolate", "colorize"]
        return [s for s in self.step_names if s in ai_steps]

    def _on_step_clicked(self, step_name):
        self._update_arrows()

    def _update_arrows(self):
        for i, name in enumerate(self.step_names):
            if i < len(self.arrows):
                self.arrows[i].set_active(
                    self.steps[name].is_enabled() and self.steps[self.step_names[i + 1]].is_enabled()
                )

    def set_step_state(self, step_name, state):
        if step_name in self.steps:
            self.steps[step_name].set_state(state)
            self._update_arrows()


# ──────────────────────────────────────────────
# Compress Settings Page (full, with all controls)
# ──────────────────────────────────────────────

class CompressSettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._trim_enabled = False

        title = QLabel("📦  Compression Settings")
        title.setStyleSheet(f"color: {ACCENT_CYAN}; font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        self.combo_compression = QComboBox()
        self.combo_compression.addItems(["Target Size (MB)", "Target Bitrate (kbps)"])
        self.combo_compression.currentIndexChanged.connect(self._on_compression_mode_changed)
        layout.addLayout(create_setting_row("Mode", self.combo_compression))

        self.edit_size = QLineEdit("")
        self._size_row = create_setting_row("Size (MB)", self.edit_size)
        layout.addLayout(self._size_row)

        self.edit_bitrate = QLineEdit("")
        self.edit_bitrate.setPlaceholderText("e.g. 5000")
        self._bitrate_row = create_setting_row("Bitrate (kbps)", self.edit_bitrate)
        self._bitrate_row_widgets = [self._bitrate_row.itemAt(0).widget() if self._bitrate_row.itemAt(0) else None, self.edit_bitrate]
        layout.addLayout(self._bitrate_row)
        self.edit_bitrate.hide()
        for i in range(self._bitrate_row.count()):
            w = self._bitrate_row.itemAt(i).widget()
            if w and w != self.edit_bitrate:
                w.hide()

        self.label_orig_bitrate = QLabel("")
        self.label_orig_bitrate.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        self._orig_bitrate_row = QHBoxLayout()
        self._orig_bitrate_row.setContentsMargins(0, 0, 0, 0)
        spacer = QLabel("")
        spacer.setFixedWidth(90)
        self._orig_bitrate_row.addWidget(spacer)
        self._orig_bitrate_row.addWidget(self.label_orig_bitrate)
        layout.addLayout(self._orig_bitrate_row)

        self.edit_filename = QLineEdit("")
        self.edit_filename.setPlaceholderText("Leave empty for original name")
        layout.addLayout(create_setting_row("Output Name", self.edit_filename))

        self.combo_resolution = QComboBox()
        self.combo_resolution.addItems(["Original", "4K (2160p)", "1440p (QHD)", "1080p (FHD)", "720p (HD)", "480p (SD)", "360p"])
        layout.addLayout(create_setting_row("Resolution", self.combo_resolution))

        self.combo_device = QComboBox()
        layout.addLayout(create_setting_row("Device", self.combo_device))

        self.combo_codec = QComboBox()
        layout.addLayout(create_setting_row("Codec", self.combo_codec))

        self.combo_export = QComboBox()
        layout.addLayout(create_setting_row("Export", self.combo_export))

        self.combo_audio = QComboBox()
        self.audio_options = {
            "Copy (original)": "copy",
            "AAC (192k)": "aac",
            "MP3 - LAME (192k)": "mp3",
            "Opus (128k)": "opus",
            "FLAC (lossless)": "flac",
            "No Audio": "none",
        }
        self.combo_audio.addItems(self.audio_options.keys())
        layout.addLayout(create_setting_row("Audio", self.combo_audio))

        self.check_audio_boost = QCheckBox("Audio Boost (normalize volume)")
        self._audio_boost_text_active = "Audio Boost (normalize volume)"
        self._audio_boost_text_disabled = "Audio Boost (unavailable with Copy / No Audio)"
        self.check_audio_boost.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        self.check_audio_boost.setToolTip("Apply EBU R128 loudness normalization to maximize volume without clipping while preserving dynamic range.")
        boost_row = QHBoxLayout()
        boost_row.setContentsMargins(0, 0, 0, 0)
        boost_row.setSpacing(8)
        boost_label = QLabel("")
        boost_label.setFixedWidth(90)
        boost_row.addWidget(boost_label)
        boost_row.addWidget(self.check_audio_boost)
        layout.addLayout(boost_row)

        self.label_audio_boost_info = QLabel("Disabled when Audio is set to 'Copy (original)' or 'No Audio'.")
        self.label_audio_boost_info.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; font-style: italic;")
        info_row = QHBoxLayout()
        info_row.setContentsMargins(0, 0, 0, 0)
        info_row.setSpacing(8)
        info_label = QLabel("")
        info_label.setFixedWidth(90)
        info_row.addWidget(info_label)
        info_row.addWidget(self.label_audio_boost_info)
        layout.addLayout(info_row)

        # ── Trim ────────────────────────────────────────────────────────────
        self.check_trim = QCheckBox("Trim (only export a portion of the video)")
        self.check_trim.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px;")
        self.check_trim.toggled.connect(self._on_trim_toggled)
        trim_title_row = QHBoxLayout()
        trim_title_row.setContentsMargins(0, 0, 0, 0)
        trim_title_row.setSpacing(8)
        trim_spacer = QLabel("")
        trim_spacer.setFixedWidth(90)
        trim_title_row.addWidget(trim_spacer)
        trim_title_row.addWidget(self.check_trim)
        layout.addLayout(trim_title_row)

        self.edit_trim_start = QTimeEdit()
        self.edit_trim_start.setDisplayFormat("hh:mm:ss")
        self.edit_trim_start.setTimeRange(
            QTime(0, 0, 0), QTime(23, 59, 59))
        self.edit_trim_start.setToolTip("Where the exported segment begins.")
        self._trim_start_row = create_setting_row("Start", self.edit_trim_start)
        layout.addLayout(self._trim_start_row)

        self.edit_trim_end = QTimeEdit()
        self.edit_trim_end.setDisplayFormat("hh:mm:ss")
        self.edit_trim_end.setTimeRange(
            QTime(0, 0, 0), QTime(23, 59, 59))
        self.edit_trim_end.setToolTip(
            "Where the exported segment ends. Set to 00:00:00 to use the natural end.")
        self._trim_end_row = create_setting_row("End", self.edit_trim_end)
        layout.addLayout(self._trim_end_row)

        self.label_trim_info = QLabel("")
        self.label_trim_info.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; font-style: italic;")
        trim_info_row = QHBoxLayout()
        trim_info_row.setContentsMargins(0, 0, 0, 0)
        trim_info_row.setSpacing(8)
        trim_info_spacer = QLabel("")
        trim_info_spacer.setFixedWidth(90)
        trim_info_row.addWidget(trim_info_spacer)
        trim_info_row.addWidget(self.label_trim_info)
        layout.addLayout(trim_info_row)

        for w in [self.edit_trim_start, self.edit_trim_end,
                  self.label_trim_info]:
            w.hide()
        self._trim_enabled = False

        layout.addStretch()

    def _on_compression_mode_changed(self):
        is_bitrate = self.combo_compression.currentText() == "Target Bitrate (kbps)"
        self.edit_size.setVisible(not is_bitrate)
        self.edit_bitrate.setVisible(is_bitrate)
        for i in range(self._size_row.count()):
            w = self._size_row.itemAt(i).widget()
            if w and w != self.edit_size:
                w.setVisible(not is_bitrate)
        for i in range(self._bitrate_row.count()):
            w = self._bitrate_row.itemAt(i).widget()
            if w and w != self.edit_bitrate:
                w.setVisible(is_bitrate)
        self.label_orig_bitrate.setVisible(is_bitrate)

    def _on_trim_toggled(self, checked):
        self._trim_enabled = bool(checked)
        visible = bool(checked)
        for w in (self.edit_trim_start, self.edit_trim_end,
                  self.label_trim_info):
            w.setVisible(visible)
        for row_layout in (getattr(self, "_trim_start_row", None),
                           getattr(self, "_trim_end_row", None)):
            if row_layout is None:
                continue
            for i in range(row_layout.count()):
                it = row_layout.itemAt(i)
                if it and it.widget():
                    it.widget().setVisible(visible)

    def trim_state(self):
        """Returns (enabled: bool, start_seconds: float, end_seconds: float_or_None)
        end_seconds is None if 00:00 = "until end".
        """
        enabled = self._trim_enabled
        start_s = self.edit_trim_start.time().hour() * 3600 + \
                  self.edit_trim_start.time().minute() * 60 + \
                  self.edit_trim_start.time().second()
        end_time = self.edit_trim_end.time()
        if end_time.hour() == 0 and end_time.minute() == 0 and end_time.second() == 0:
            end_s = None
        else:
            end_s = end_time.hour() * 3600 + \
                    end_time.minute() * 60 + \
                    end_time.second()
        if start_s < 0:
            start_s = 0.0
        return enabled, float(start_s), end_s

    def set_trim_info(self, msg):
        try:
            self.label_trim_info.setText(msg)
        except Exception:
            pass


# ──────────────────────────────────────────────
# Time parsing helper — exposed at module scope
# ──────────────────────────────────────────────

def parse_time_to_seconds(text: str, allow_empty_end: bool = False):
    """Parse 'ss' / 'mm:ss' / 'hh:mm:ss' / 'hh:mm:ss.ff' into seconds (float).

    Returns:
        - > 0  : a valid timestamp.
        -  -1  : empty/invalid (caller treats end specially).

    Robust to leading/trailing whitespace; sums partial units.
    """
    if text is None:
        return -1
    s = str(text).strip()
    if not s:
        return -1 if allow_empty_end else 0
    parts = s.split(":")
    try:
        nums = [float(p) for p in parts]
    except Exception:
        return -1
    if any(n < 0 for n in nums):
        return -1
    total = 0.0
    for n in nums:
        total = total * 60 + n
    return total


# ──────────────────────────────────────────────
# AI Settings Page
# ──────────────────────────────────────────────

class UpscaleSettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title = QLabel("⬆  AI Upscale")
        title.setStyleSheet(f"color: {ACCENT_CYAN}; font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        from src.ai_tools import UPSCALE_MODELS, detect_gpu_devices
        self.combo_model = QComboBox()
        self.model_keys = list(UPSCALE_MODELS.keys())
        for key in self.model_keys:
            info = UPSCALE_MODELS[key]
            self.combo_model.addItem(f"{info['name']} - {info['best_for']}", key)
        layout.addLayout(create_setting_row("Model", self.combo_model))

        self.combo_scale = QComboBox()
        self.combo_scale.addItems(["2x", "3x", "4x"])
        layout.addLayout(create_setting_row("Scale", self.combo_scale))

        self.combo_device = QComboBox()
        self.combo_device.addItems(_get_ai_device_options())
        layout.addLayout(create_setting_row("AI Device", self.combo_device))

        self.label_info = QLabel("")
        self.label_info.setStyleSheet(AI_INFO_STYLE)
        self.label_info.setWordWrap(True)
        self.label_info.setMinimumHeight(50)
        layout.addWidget(self.label_info)
        layout.addStretch()

        self.combo_model.currentIndexChanged.connect(self._update_info)
        self.combo_scale.currentIndexChanged.connect(self._update_info)
        self._update_info()

    def _update_info(self):
        try:
            from src.ai_tools import UPSCALE_MODELS, get_gpu_vram_mb, classify_vram, stars_rating
            key = self.combo_model.currentData()
            if not key:
                return
            model = UPSCALE_MODELS.get(key, {})
            scale = self.combo_scale.currentText()
            vram = model.get("vram_mb", 0)
            if "3x" in scale: vram = int(vram * 1.3)
            elif "4x" in scale: vram = int(vram * 1.8)
            gpu_vram = get_gpu_vram_mb()
            _, status_text = classify_vram(gpu_vram, vram)
            self.label_info.setText(
                f"VRAM: ~{vram}MB | Speed: {model.get('speed', 'N/A')}\n"
                f"Quality: {stars_rating(model.get('quality', 0))} | {model.get('best_for', '')}\n"
                f"GPU: {status_text}"
            )
        except Exception as e:
            print(f"upscale info error: {e}")


class InterpolateSettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title = QLabel("🎞  AI Frame Interpolation")
        title.setStyleSheet(f"color: {ACCENT_CYAN}; font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        from src.ai_tools import INTERPOLATION_MODELS
        self.combo_model = QComboBox()
        self.model_keys = list(INTERPOLATION_MODELS.keys())
        for key in self.model_keys:
            info = INTERPOLATION_MODELS[key]
            self.combo_model.addItem(f"{info['name']} - {info['best_for']}", key)
        layout.addLayout(create_setting_row("Model", self.combo_model))

        self.combo_mult = QComboBox()
        self.combo_mult.addItems(["2x", "3x", "4x"])
        layout.addLayout(create_setting_row("Multiplier", self.combo_mult))

        self.combo_device = QComboBox()
        self.combo_device.addItems(_get_ai_device_options())
        layout.addLayout(create_setting_row("AI Device", self.combo_device))

        self.label_info = QLabel("")
        self.label_info.setStyleSheet(AI_INFO_STYLE)
        self.label_info.setWordWrap(True)
        self.label_info.setMinimumHeight(50)
        layout.addWidget(self.label_info)
        layout.addStretch()

        self.combo_model.currentIndexChanged.connect(self._update_info)
        self._update_info()

    def _update_info(self):
        try:
            from src.ai_tools import INTERPOLATION_MODELS, get_gpu_vram_mb, classify_vram, stars_rating
            key = self.combo_model.currentData()
            if not key:
                return
            model = INTERPOLATION_MODELS.get(key, {})
            gpu_vram = get_gpu_vram_mb()
            vram = model.get("vram_mb", 0)
            _, status_text = classify_vram(gpu_vram, vram)
            self.label_info.setText(
                f"VRAM: ~{vram}MB | Speed: {model.get('speed', 'N/A')}\n"
                f"Quality: {stars_rating(model.get('quality', 0))} | {model.get('best_for', '')}\n"
                f"GPU: {status_text}"
            )
        except Exception as e:
            print(f"interp info error: {e}")


class ColorizeSettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title = QLabel("🎨  AI Colorize")
        title.setStyleSheet(f"color: {ACCENT_CYAN}; font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        from src.ai_tools import COLORIZE_MODELS
        self.combo_model = QComboBox()
        self.model_keys = list(COLORIZE_MODELS.keys())
        for key in self.model_keys:
            info = COLORIZE_MODELS[key]
            self.combo_model.addItem(f"{info['name']} - {info['best_for']}", key)
        layout.addLayout(create_setting_row("Model", self.combo_model))

        self.combo_device = QComboBox()
        self.combo_device.addItems(_get_ai_device_options())
        layout.addLayout(create_setting_row("AI Device", self.combo_device))

        self.label_info = QLabel("")
        self.label_info.setStyleSheet(AI_INFO_STYLE)
        self.label_info.setWordWrap(True)
        self.label_info.setMinimumHeight(50)
        layout.addWidget(self.label_info)
        layout.addStretch()

        self.combo_model.currentIndexChanged.connect(self._update_info)
        self._update_info()

    def _update_info(self):
        try:
            from src.ai_tools import COLORIZE_MODELS, get_gpu_vram_mb, classify_vram, stars_rating, check_onnx_available
            key = self.combo_model.currentData()
            if not key:
                return
            model = COLORIZE_MODELS.get(key, {})
            gpu_vram = get_gpu_vram_mb()
            vram = model.get("vram_mb", 0)
            _, status_text = classify_vram(gpu_vram, vram)
            onnx_ok, has_cuda, _ = check_onnx_available()
            backend = "CUDA" if has_cuda else ("CPU" if onnx_ok else "Not installed")
            self.label_info.setText(
                f"VRAM: ~{vram}MB | Speed: {model.get('speed', 'N/A')}\n"
                f"Quality: {stars_rating(model.get('quality', 0))} | {model.get('best_for', '')}\n"
                f"ONNX: {backend} | GPU: {status_text}"
            )
        except Exception as e:
            print(f"colorize info error: {e}")


class ImportInfoPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title = QLabel("▶  Video Info")
        title.setStyleSheet(f"color: {ACCENT_CYAN}; font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        self.label_path = QLabel("No video selected.")
        self.label_path.setWordWrap(True)
        self.label_path.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px;")
        layout.addWidget(self.label_path)

        self.label_size = QLabel("")
        self.label_size.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(self.label_size)

        self.label_quality = QLabel("")
        self.label_quality.setWordWrap(True)
        self.label_quality.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(self.label_quality)

        layout.addStretch()


class HardwareInfoDialog(QDialog):
    def __init__(self, hw_info, parent=None):
        super().__init__(parent)
        self.setWindowTitle("System Hardware Diagnostic")
        self.setFixedSize(500, 480)
        self.setStyleSheet(GLOBAL_STYLE)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Title
        title = QLabel("🖥️ System Hardware & Codec Report")
        title.setStyleSheet(f"color: {ACCENT_CYAN}; font-size: 16px; font-weight: bold; background: transparent; border: none;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Info Box
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)
        
        # CPU
        cpu_box = QFrame()
        cpu_box.setStyleSheet(f"background-color: {BG_SECONDARY}; border: 1px solid {BORDER_DEFAULT}; border-radius: 8px;")
        cpu_layout = QVBoxLayout(cpu_box)
        cpu_layout.setContentsMargins(12, 10, 12, 10)
        cpu_title = QLabel("Processor (CPU)")
        cpu_title.setStyleSheet(f"color: {ACCENT_BLUE}; font-weight: bold; font-size: 13px; background: transparent; border: none;")
        cpu_val = QLabel(hw_info.get("cpu", "Unknown CPU"))
        cpu_val.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; background: transparent; border: none;")
        cpu_val.setWordWrap(True)
        cpu_layout.addWidget(cpu_title)
        cpu_layout.addWidget(cpu_val)
        content_layout.addWidget(cpu_box)
        
        # GPUs
        gpu_details = hw_info.get("gpu_details", [])
        if not gpu_details:
            no_gpu_box = QFrame()
            no_gpu_box.setStyleSheet(f"background-color: {BG_SECONDARY}; border: 1px solid {BORDER_DEFAULT}; border-radius: 8px;")
            no_gpu_layout = QVBoxLayout(no_gpu_box)
            no_gpu_layout.setContentsMargins(12, 10, 12, 10)
            no_gpu_title = QLabel("Graphics Processor (GPU)")
            no_gpu_title.setStyleSheet(f"color: {ACCENT_BLUE}; font-weight: bold; background: transparent; border: none;")
            no_gpu_val = QLabel("No discrete or integrated GPU detected (using CPU software fallback).")
            no_gpu_val.setStyleSheet("color: #F85149; font-size: 12px; background: transparent; border: none;")
            no_gpu_layout.addWidget(no_gpu_title)
            no_gpu_layout.addWidget(no_gpu_val)
            content_layout.addWidget(no_gpu_box)
        else:
            for i, gpu in enumerate(gpu_details):
                gpu_box = QFrame()
                gpu_box.setStyleSheet(f"background-color: {BG_SECONDARY}; border: 1px solid {BORDER_DEFAULT}; border-radius: 8px;")
                gpu_layout = QVBoxLayout(gpu_box)
                gpu_layout.setContentsMargins(12, 10, 12, 10)
                
                type_lbl = "Dedicated" if gpu.get("type") == "dedicated" else "Integrated"
                vram_val = gpu.get("vram_mb", 0)
                vram_lbl = f"{round(vram_val / 1024, 1)} GB" if vram_val > 0 else "Unknown / Shared"
                
                gpu_title = QLabel(f"GPU {gpu.get('id', i)}: {gpu.get('name', 'Unknown')}")
                gpu_title.setStyleSheet(f"color: {ACCENT_BLUE}; font-weight: bold; font-size: 13px; background: transparent; border: none;")
                gpu_title.setWordWrap(True)
                
                details_lbl = QLabel(f"• Type: {type_lbl} | Vendor: {gpu.get('vendor', 'Other')} | VRAM: {vram_lbl}")
                details_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; background: transparent; border: none;")
                
                gpu_layout.addWidget(gpu_title)
                gpu_layout.addWidget(details_lbl)
                
                # Codecs
                codecs = gpu.get("supported_codecs", [])
                if codecs:
                    codecs_title = QLabel("• Natively Supported Hardware Codecs:")
                    codecs_title.setStyleSheet(f"color: {TEXT_SECONDARY}; font-weight: bold; font-size: 11px; margin-top: 5px; background: transparent; border: none;")
                    gpu_layout.addWidget(codecs_title)
                    
                    for c in codecs:
                        prof_str = ", ".join(c.get("profiles", []))
                        codec_lbl = QLabel(f"   - {c.get('name')} ({prof_str})")
                        codec_lbl.setStyleSheet("color: #00D4AA; font-size: 11px; background: transparent; border: none;")
                        gpu_layout.addWidget(codec_lbl)
                else:
                    codecs_lbl = QLabel("• No native hardware video codecs detected for this card.")
                    codecs_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")
                    gpu_layout.addWidget(codecs_lbl)
                    
                content_layout.addWidget(gpu_box)
                
        # AI Backend & Models
        ai_box = QFrame()
        ai_box.setStyleSheet(f"background-color: {BG_SECONDARY}; border: 1px solid {BORDER_DEFAULT}; border-radius: 8px;")
        ai_layout = QVBoxLayout(ai_box)
        ai_layout.setContentsMargins(12, 10, 12, 10)
        ai_title = QLabel("AI System & Frame Interpolation")
        ai_title.setStyleSheet(f"color: {ACCENT_BLUE}; font-weight: bold; font-size: 13px; background: transparent; border: none;")
        ai_layout.addWidget(ai_title)
        
        from src.ai_tools import check_onnx_available
        onnx_ok, has_cuda, _ = check_onnx_available()
        backend_str = "ONNX Runtime: CUDA (GPU Accelerated)" if has_cuda else ("ONNX Runtime: CPU Only" if onnx_ok else "ONNX Runtime: Not Installed")
        backend_color = "#00D4AA" if has_cuda else ("#D29922" if onnx_ok else "#F85149")
        
        backend_lbl = QLabel(f"• AI Backend: {backend_str}")
        backend_lbl.setStyleSheet(f"color: {backend_color}; font-size: 12px; background: transparent; border: none;")
        ai_layout.addWidget(backend_lbl)
        
        content_layout.addWidget(ai_box)
        
        scroll.setWidget(content)
        layout.addWidget(scroll)
        
        # OK Button
        btn_ok = QPushButton("Dismiss")
        btn_ok.setStyleSheet(BUTTON_SELECT_STYLE)
        btn_ok.setFixedHeight(36)
        btn_ok.clicked.connect(self.accept)
        layout.addWidget(btn_ok)


class ClickableFrameLabel(QLabel):
    """QLabel that emits clicked when user clicks it (only when a pixmap is set)."""
    clicked = Signal()

    def __init__(self, subtitle, parent=None):
        super().__init__(parent)
        self._subtitle = subtitle
        self._has_pixmap = False
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(360, 220)
        self._reset_style()
        self.setCursor(Qt.ArrowCursor)
        self.setText(f"{subtitle}\n(waiting…)")

    def _reset_style(self):
        self.setStyleSheet(
            f"background-color: {BG_TERTIARY}; border: 1px solid {BORDER_DEFAULT}; "
            f"border-radius: 8px; color: {TEXT_MUTED}; font-size: 13px;")

    def set_subtitle_text(self, placeholder):
        self.setText(f"{self._subtitle}\n({placeholder})")
        self._reset_style()
        self._has_pixmap = False
        self.setCursor(Qt.ArrowCursor)

    def set_pixmap_marks(self, pix):
        scaled = pix.scaledToWidth(
            self.width() - 24, Qt.SmoothTransformation
        )
        self.setPixmap(scaled)
        self._has_pixmap = True
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            f"background-color: {BG_SECONDARY}; border: 1px solid {ACCENT_CYAN}; "
            "border-radius: 8px;")

    def mousePressEvent(self, event):
        if self._has_pixmap and event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ZoomableFrameView(QLabel):
    """Scroll-area-friendly viewer for a single full-resolution frame.
    Supports scroll-wheel zoom (Ctrl+wheel anywhere) and drag to pan."""

    def __init__(self, pix, parent=None):
        super().__init__(parent)
        self._full = pix
        self._zoom = 1.0
        self._min_zoom = 0.1
        self._max_zoom = 8.0
        self._drag_pos = None
        self._zoom_callback = None
        self.setAlignment(Qt.AlignCenter)
        self._refresh()

    def set_zoom_callback(self, cb):
        self._zoom_callback = cb

    def _refresh(self):
        if self._full.isNull():
            return
        w = max(1, int(round(self._full.width() * self._zoom)))
        h = max(1, int(round(self._full.height() * self._zoom)))
        scaled = self._full.scaled(
            w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(scaled)

    def set_zoom(self, z):
        self._zoom = max(self._min_zoom, min(self._max_zoom, z))
        self._refresh()
        if self._zoom_callback is not None:
            self._zoom_callback(self._zoom)

    def zoom_factor(self):
        return self._zoom

    def reset_zoom_fit(self, view_w, view_h):
        if self._full.isNull() or view_w <= 1 or view_h <= 1:
            return
        z = min(view_w / self._full.width(),
                view_h / self._full.height())
        self.set_zoom(z)

    def reset_zoom_100(self):
        self.set_zoom(1.0)

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            factor = 1.25 if delta > 0 else 1.0 / 1.25
            self.set_zoom(self._zoom * factor)
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = None
            self.setCursor(Qt.ArrowCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class SliderCompareLabel(QWidget):
    """Side-by-side A/B frame comparator with a draggable vertical slider.
    Original is shown to the LEFT of the slider; Compressed on the RIGHT.
    Architecture:
        +-------------------------------------------------------+
        | _image_label (full-area, paintEvent draws both         |
        |   images with vertical split)                          |
        |                                                       |
        |   +---+                                               |
        |   | O |   ← center of QSlider handle = divider X       |
        |   +---+                                               |
        |                                                       |
        |   [Original]                  [Compressed]            |
        |                                                       |
        |                 [Zoom bar 100%]                        |
        +-------------------------------------------------------+
    Wheel zooms the view (anchored to cursor). Mid-button pans when
    zoom > 1×. Left-click on the slider groove/handle jumps the
    divider to that x (standard QSlider behaviour). Double-clicking
    on the image emits side_clicked("left"/"right") for full-resolution
    zoom.
    """

    side_clicked = Signal(str)
    zoom_changed = Signal(float)

    _SLIDER_RANGE = 1000

    class _ImageCanvas(QLabel):
        """QLabel subclass that paints both halves of the A/B comparison
        and the divider. Owns no state — all values come from the parent."""

        def __init__(self, owner, parent=None):
            super().__init__(parent)
            self._owner = owner

        def paintEvent(self, event):
            owner = self._owner
            if owner is None:
                return
            painter = QPainter(self)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            bg_rect = self.rect()
            painter.fillRect(bg_rect, QColor(BG_TERTIARY))

            if owner._orig_pix.isNull():
                painter.setPen(QColor(TEXT_MUTED))
                font = painter.font()
                font.setPointSize(13)
                painter.setFont(font)
                painter.drawText(bg_rect, Qt.AlignCenter,
                                 "Preparing frames…")
                return

            rect = owner._display_rect()
            if rect is None:
                return

            ww = self.width()
            wh = self.height()

            if not owner._orig_pix.isNull():
                scaled = owner._orig_pix.scaled(
                    rect.size(), Qt.KeepAspectRatio,
                    Qt.SmoothTransformation)
                sx = rect.x() + (rect.width() - scaled.width()) // 2
                sy = rect.y() + (rect.height() - scaled.height()) // 2
                dest = QRect(sx, sy, scaled.width(), scaled.height())
                visible = dest.intersected(QRect(0, 0, ww, wh))
                painter.drawPixmap(
                    visible, scaled,
                    QRect(visible.x() - sx, visible.y() - sy,
                          visible.width(), visible.height()))

            slider_x = owner._slider_x_in_widget()
            clip_right = max(0, slider_x - rect.x())

            if not owner._comp_pix.isNull():
                scaled = owner._comp_pix.scaled(
                    rect.size(), Qt.KeepAspectRatio,
                    Qt.SmoothTransformation)
                sx = rect.x() + (rect.width() - scaled.width()) // 2
                sy = rect.y() + (rect.height() - scaled.height()) // 2
                dest = QRect(sx, sy, scaled.width(), scaled.height())
                painter.save()
                clip = QRect(rect.x(), rect.y(), clip_right, rect.height())
                painter.setClipRect(
                    clip.intersected(QRect(0, 0, ww, wh)),
                    Qt.ReplaceClip)
                visible = dest.intersected(QRect(0, 0, ww, wh))
                painter.drawPixmap(
                    visible, scaled,
                    QRect(visible.x() - sx, visible.y() - sy,
                          visible.width(), visible.height()))
                painter.restore()

            painter.setPen(QColor("#FFFFFF"))
            painter.drawLine(slider_x - 1, rect.y(),
                             slider_x - 1, rect.y() + rect.height())
            painter.drawLine(slider_x + 1, rect.y(),
                             slider_x + 1, rect.y() + rect.height())
            painter.setPen(QColor(ACCENT_CYAN))
            painter.drawLine(slider_x, rect.y(),
                             slider_x, rect.y() + rect.height())

            painter.setPen(QColor(TEXT_MUTED))
            font = painter.font()
            font.setPointSize(10)
            font.setBold(True)
            painter.setFont(font)
            if rect.x() + 8 + 80 < ww:
                painter.drawText(rect.x() + 8, rect.y() + 18, "ORIGINAL")
            if rect.x() + rect.width() - 8 - 100 >= 0:
                right_pos = rect.x() + rect.width() - 8 - 100
                painter.drawText(right_pos, rect.y() + 18, "COMPRESSED")

            bar_w = 110
            bar_h = 18
            bx = (ww - bar_w) // 2
            by = wh - bar_h - 6
            bar_bg = QRect(bx, by, bar_w, bar_h)
            painter.setBrush(QColor(0, 0, 0, 180))
            painter.setPen(QColor(BORDER_DEFAULT))
            painter.drawRoundedRect(bar_bg, 9, 9)
            pct = int(round(owner._zoom * 100))
            pct = max(25, min(800, pct))
            fill_w = int(round(
                (pct - 25) / (800 - 25) * (bar_w - 4)))
            fill_rect = QRect(bx + 2, by + 2, fill_w, bar_h - 4)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(ACCENT_CYAN))
            painter.drawRoundedRect(fill_rect, 7, 7)
            pct_text = f"{pct}%"
            painter.setPen(QColor(TEXT_PRIMARY))
            font = painter.font()
            font.setPointSize(9)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(bar_bg, Qt.AlignCenter, pct_text)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._orig_pix = QPixmap()
        self._comp_pix = QPixmap()
        self._orig_png = None
        self._comp_png = None
        self._zoom = 1.0
        self._min_zoom = 0.25
        self._max_zoom = 8.0
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._panning = False
        self._pan_start = QPoint()

        self._image_label = self._ImageCanvas(self, self)
        self._image_label.setMouseTracking(True)
        self._image_label.setStyleSheet(
            f"background-color: {BG_TERTIARY};")
        self._image_label.mousePressEvent = self._on_image_mouse_press
        self._image_label.mouseMoveEvent = self._on_image_mouse_move
        self._image_label.mouseReleaseEvent = self._on_image_mouse_release
        self._image_label.wheelEvent = self._on_image_wheel
        self._image_label.mouseDoubleClickEvent = (
            self._on_image_double_click)

        self._slider = QSlider(Qt.Horizontal, self)
        self._slider.setRange(0, self._SLIDER_RANGE)
        self._slider.setValue(self._SLIDER_RANGE // 2)
        self._slider.setPageStep(50)
        self._slider.setSingleStep(10)
        self._slider.setCursor(Qt.SplitHCursor)
        self._slider.wheelEvent = lambda e: None
        self._slider.valueChanged.connect(self._on_slider_value_changed)
        self._slider.sliderPressed.connect(self._on_slider_pressed)
        self._slider.sliderReleased.connect(self._on_slider_released)

        self.setMinimumSize(360, 220)
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)

    # ───────────────── public API ─────────────────
    def set_original(self, png_bytes):
        self._orig_png = png_bytes
        pix = QPixmap()
        if png_bytes:
            pix.loadFromData(png_bytes, "PNG")
        self._orig_pix = pix
        self._reset_zoom_state()
        self._image_label.update()

    def set_compressed(self, png_bytes):
        self._comp_png = png_bytes
        pix = QPixmap()
        if png_bytes:
            pix.loadFromData(png_bytes, "PNG")
        self._comp_pix = pix
        self._reset_zoom_state()
        self._image_label.update()

    def has_frames(self):
        return (not self._orig_pix.isNull()) and (not self._comp_pix.isNull())

    def orig_png_bytes(self):
        return self._orig_png

    def comp_png_bytes(self):
        return self._comp_png

    def zoom_factor(self):
        return self._zoom

    def zoom_in(self):
        self._apply_zoom(self._zoom * 1.25)

    def zoom_out(self):
        self._apply_zoom(self._zoom / 1.25)

    def zoom_fit(self):
        self._zoom = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0
        self.zoom_changed.emit(self._zoom)
        self._image_label.update()

    def zoom_100(self):
        ref = next((p for p in (self._orig_pix, self._comp_pix)
                    if not p.isNull()), QPixmap())
        fit = self._fit_rect()
        if ref.isNull() or fit is None:
            return
        z = min(fit.width() / ref.width(),
                fit.height() / ref.height())
        target_z = 1.0 / z
        self._apply_zoom(target_z)

    # ───────────────── zoom constants ─────────────────
    @property
    def _slider_ratio(self):
        return self._slider.value() / self._SLIDER_RANGE

    def _reset_zoom_state(self):
        self._zoom = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0
        self.zoom_changed.emit(self._zoom)

    def _fit_rect(self):
        w = self.width()
        h = self.height()
        if w < 2 or h < 2:
            return None
        ref = None
        for pix in (self._orig_pix, self._comp_pix):
            if not pix.isNull():
                ref = pix
                break
        if ref is None or ref.isNull() or ref.width() < 1 or ref.height() < 1:
            return None
        ratio = ref.width() / ref.height()
        target_w = w
        target_h = int(round(w / ratio))
        if target_h > h:
            target_h = h
            target_w = int(round(h * ratio))
        x = (w - target_w) // 2
        y = (h - target_h) // 2
        return QRect(x, y, target_w, target_h)

    def _display_rect(self):
        fit = self._fit_rect()
        if fit is None:
            return None
        if (abs(self._zoom - 1.0) < 1e-3
                and self._offset_x == 0.0
                and self._offset_y == 0.0):
            return fit
        new_w = max(1, int(round(fit.width() * self._zoom)))
        new_h = max(1, int(round(fit.height() * self._zoom)))
        x = int(round(self._offset_x))
        y = int(round(self._offset_y))
        return QRect(x, y, new_w, new_h)

    def _clamp_offset(self):
        rect = self._display_rect()
        ww = self.width()
        wh = self.height()
        if rect is None:
            return
        if rect.width() <= ww:
            self._offset_x = 0.0
        else:
            self._offset_x = max(ww - rect.width(),
                                 min(0, self._offset_x))
        if rect.height() <= wh:
            self._offset_y = 0.0
        else:
            self._offset_y = max(wh - rect.height(),
                                 min(0, self._offset_y))

    def _apply_zoom(self, new_zoom, anchor_widget_pos=None):
        old_zoom = self._zoom
        self._zoom = max(self._min_zoom, min(self._max_zoom, new_zoom))
        if abs(self._zoom - old_zoom) < 1e-4:
            return
        fit = self._fit_rect()
        if fit is None:
            return
        anchor = anchor_widget_pos or QPoint(self.width() // 2,
                                            self.height() // 2)
        old_w = max(1, fit.width() * old_zoom)
        old_h = max(1, fit.height() * old_zoom)
        if abs(old_zoom - 1.0) < 1e-3:
            old_x = (self.width() - old_w) // 2
            old_y = (self.height() - old_h) // 2
        else:
            old_x = self._offset_x
            old_y = self._offset_y
        rel_x = (anchor.x() - old_x) / old_w
        rel_y = (anchor.y() - old_y) / old_h
        new_w = fit.width() * self._zoom
        new_h = fit.height() * self._zoom
        self._offset_x = anchor.x() - rel_x * new_w
        self._offset_y = anchor.y() - rel_y * new_h
        self._clamp_offset()
        self.zoom_changed.emit(self._zoom)
        self._image_label.update()

    # ───────────────── geometry ─────────────────
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._image_label.setGeometry(0, 0, self.width(), self.height())
        self._slider.setGeometry(0, 0, self.width(), self.height())
        self._install_slider_style()
        self._image_label.update()
        self._slider.raise_()

    def _install_slider_style(self):
        h = self.height()
        if h < 8:
            return
        neg = max(8, h)
        self._slider.setStyleSheet(
            "QSlider { background: transparent; }"
            "QSlider::groove:horizontal {"
            " background: transparent;"
            " height: 6px;"
            "}"
            "QSlider::sub-page:horizontal { background: transparent; }"
            "QSlider::add-page:horizontal { background: transparent; }"
            f"QSlider::handle:horizontal {{"
            f" background: {BG_PRIMARY};"
            f" border: 2px solid {ACCENT_CYAN};"
            f" width: 16px;"
            f" margin-top: -{neg}px;"
            f" margin-bottom: -{neg}px;"
            f" margin-left: -7px;"
            f" margin-right: -7px;"
            " border-radius: 4px;"
            "}"
        )

    # ───────────────── image rendering ─────────────────
    def wheelEvent(self, event):
        self._on_image_wheel(event)

    def _slider_x_in_widget(self):
        fit = self._fit_rect()
        if fit is None or fit.width() < 1:
            return self.width() // 2
        return int(round(fit.x() + self._slider_ratio * fit.width()))

    # ───────────────── slider signal handlers ─────────────────
    def _on_slider_value_changed(self, value):
        self._image_label.update()

    def _on_slider_pressed(self):
        self.setCursor(Qt.SplitHCursor)

    def _on_slider_released(self):
        self.setCursor(Qt.ArrowCursor)

    # ───────────────── drag & zoom on the image_label ─────────────────
    def _on_image_mouse_press(self, event):
        if event.button() == Qt.MidButton:
            self._panning = True
            self._pan_start = event.globalPosition().toPoint()
            self._image_label.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        if event.button() != Qt.LeftButton:
            return
        fit = self._fit_rect()
        if fit is None or fit.width() < 1:
            return
        pos_x = int(event.position().toPoint().x())
        if pos_x < fit.x() or pos_x > fit.x() + fit.width():
            return
        new_ratio = (pos_x - fit.x()) / fit.width()
        new_ratio = max(0.0, min(1.0, new_ratio))
        self._slider.setValue(int(round(new_ratio * self._SLIDER_RANGE)))

    def _on_image_mouse_move(self, event):
        if self._panning:
            cur = event.globalPosition().toPoint()
            delta = cur - self._pan_start
            self._pan_start = cur
            self._offset_x += delta.x()
            self._offset_y += delta.y()
            self._clamp_offset()
            self._image_label.update()
            return
        fit = self._fit_rect()
        if fit is None or fit.width() < 1:
            return
        if not (event.buttons() & Qt.LeftButton):
            return
        pos_x = int(event.position().toPoint().x())
        if pos_x < fit.x() or pos_x > fit.x() + fit.width():
            return
        new_ratio = (pos_x - fit.x()) / fit.width()
        new_ratio = max(0.0, min(1.0, new_ratio))
        self._slider.setValue(int(round(new_ratio * self._SLIDER_RANGE)))

    def _on_image_mouse_release(self, event):
        if event.button() == Qt.MiddleButton and self._panning:
            self._panning = False
            self._image_label.setCursor(Qt.ArrowCursor)
            return

    def _on_image_wheel(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.25 if delta > 0 else 1.0 / 1.25
        self._apply_zoom(self._zoom * factor,
                         event.position().toPoint())

    def _on_image_double_click(self, event):
        if event.button() != Qt.LeftButton:
            return
        fit = self._fit_rect()
        if fit is None or fit.width() < 1:
            return
        side = "left" if self._slider.value() < self._SLIDER_RANGE // 2 else "right"
        self.side_clicked.emit(side)

    def showEvent(self, event):
        super().showEvent(event)
        pass

    # ───────────────── outer's events: forward wheel correctly ─────────────────
    def wheelEvent(self, event):
        self._on_image_wheel(event)


class ZoomDialog(QDialog):
    """Full-size single frame viewer with zoom controls & drag-to-pan
    wrapped inside a QScrollArea."""

    def __init__(self, subtitle, png_bytes, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Frame Zoom — {subtitle}")
        self.setStyleSheet(GLOBAL_STYLE)
        self.resize(960, 720)
        self._png_bytes = png_bytes
        self._full = QPixmap()
        self._full.loadFromData(png_bytes, "PNG")
        self._zoom_view = None
        self._scroll = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel(subtitle)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"color: {ACCENT_CYAN}; font-size: 14px; font-weight: bold; "
            "background: transparent; border: none;")
        layout.addWidget(title)

        if self._full.isNull():
            err = QLabel("Frame unavailable.")
            err.setAlignment(Qt.AlignCenter)
            err.setStyleSheet("color: #F85149; font-size: 13px;")
            layout.addWidget(err, 1)
        else:
            self._scroll = QScrollArea()
            self._scroll.setWidgetResizable(False)
            self._scroll.setStyleSheet("background-color: #000; border: none;")
            self._zoom_view = ZoomableFrameView(self._full, self._scroll)
            self._zoom_view.setMinimumSize(self._full.size())
            self._scroll.setWidget(self._zoom_view)
            layout.addWidget(self._scroll, 1)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        def make_btn(text, slot):
            b = QPushButton(text)
            b.setFixedHeight(32)
            b.setStyleSheet(BUTTON_SELECT_STYLE)
            b.clicked.connect(slot)
            return b

        toolbar.addWidget(make_btn("Fit", self._on_fit))
        toolbar.addWidget(make_btn("100%", self._on_100))
        toolbar.addWidget(make_btn("−", self._on_zoom_out))
        toolbar.addWidget(make_btn("+", self._on_zoom_in))

        self.zoom_label = QLabel("100%")
        self.zoom_label.setFixedWidth(64)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.zoom_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 12px; background: transparent; "
            "border: none;")
        toolbar.addWidget(self.zoom_label)

        toolbar.addStretch(1)

        save_btn = make_btn("Save PNG…", self._on_save)
        toolbar.addWidget(save_btn)

        close_btn = make_btn("Close", self.accept)
        toolbar.addWidget(close_btn)

        layout.addLayout(toolbar)

        if self._zoom_view is not None:
            self._zoom_view.set_zoom_callback(self._sync_zoom_label)
            QTimer.singleShot(0, self._on_fit)

    def _sync_zoom_label(self, _=None):
        if self._zoom_view is not None:
            self.zoom_label.setText(f"{int(round(self._zoom_view.zoom_factor() * 100))}%")

    def _on_fit(self):
        if self._zoom_view is None or self._scroll is None:
            return
        self._zoom_view.reset_zoom_fit(
            self._scroll.viewport().width() - 4,
            self._scroll.viewport().height() - 4)
        self._sync_zoom_label()

    def _on_100(self):
        if self._zoom_view is None:
            return
        self._zoom_view.reset_zoom_100()
        self._sync_zoom_label()

    def _on_zoom_in(self):
        if self._zoom_view is None:
            return
        self._zoom_view.set_zoom(self._zoom_view.zoom_factor() * 1.25)
        self._sync_zoom_label()

    def _on_zoom_out(self):
        if self._zoom_view is None:
            return
        self._zoom_view.set_zoom(self._zoom_view.zoom_factor() / 1.25)
        self._sync_zoom_label()

    def _on_save(self):
        from PySide6.QtWidgets import QFileDialog
        suggested = "draggy_preview_frame.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save frame", suggested, "PNG Image (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        try:
            with open(path, "wb") as f:
                f.write(self._png_bytes)
            self.zoom_label.setText("Saved ✓")
        except Exception as e:
            self.zoom_label.setText(f"Save failed: {e}")


class PreviewDialog(QDialog):
    """Non-modal preview window showing original vs compressed frames
    plus predicted size/bitrate/algorithm info. Frames are clickable to
    open a full-resolution zoom view."""

    def __init__(self, file_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Compression Preview — {file_name}")
        self.setMinimumSize(760, 560)
        self.setStyleSheet(GLOBAL_STYLE)
        self._preview_thread = None
        self._orig_png = None
        self._comp_png = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Compression Preview")
        title.setStyleSheet(
            f"color: {ACCENT_CYAN}; font-size: 15px; font-weight: bold; "
            "background: transparent; border: none;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(16)
        self.progress.setStyleSheet(PROGRESS_BAR_STYLE)
        layout.addWidget(self.progress)

        self.frame_row = QHBoxLayout()
        self.frame_row.setSpacing(10)

        self.compare = SliderCompareLabel()
        self.compare.setStyleSheet(
            f"background-color: {BG_TERTIARY}; border: 1px solid {BORDER_DEFAULT}; "
            "border-radius: 8px;")
        self.compare.side_clicked.connect(self._on_compare_side_clicked)
        self.frame_row.addWidget(self.compare, 1)
        layout.addLayout(self.frame_row, 1)

        self.zoom_hint = QLabel(
            "Arrastrá la barra central para revelar Original (izq.) vs Compressed (der.). "
            "Rueda del ratón = zoom (anclado al cursor). "
            "Doble-click sobre cualquier lado para ampliarlo. "
            "Botón central del ratón = paneo.")
        self.zoom_hint.setAlignment(Qt.AlignCenter)
        self.zoom_hint.setWordWrap(True)
        self.zoom_hint.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")
        layout.addWidget(self.zoom_hint)

        self.info_label = QLabel("Preparing preview…")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet(
            f"background-color: {BG_SECONDARY}; border: 1px solid {BORDER_DEFAULT}; "
            f"border-radius: 8px; color: {TEXT_PRIMARY}; font-size: 12px; padding: 10px;")
        layout.addWidget(self.info_label)

        btn_row = QHBoxLayout()

        def _add_btn(text, slot, enabled=True, style=BUTTON_SELECT_STYLE):
            b = QPushButton(text)
            b.setFixedHeight(32)
            b.setStyleSheet(style if enabled else BUTTON_DISABLED_STYLE)
            b.setEnabled(enabled)
            b.clicked.connect(slot)
            btn_row.addWidget(b)
            return b

        _add_btn("Zoom −", lambda: self.compare.zoom_out())
        _add_btn("Fit", lambda: self.compare.zoom_fit())
        _add_btn("100%", lambda: self.compare.zoom_100())
        _add_btn("Zoom +", lambda: self.compare.zoom_in())

        self.btn_save_orig = QPushButton("Save Original")
        self.btn_save_orig.setFixedHeight(34)
        self.btn_save_orig.setStyleSheet(BUTTON_DISABLED_STYLE)
        self.btn_save_orig.setEnabled(False)
        self.btn_save_orig.clicked.connect(lambda: self._save_frame("orig"))
        btn_row.addWidget(self.btn_save_orig)

        self.btn_zoom_orig = QPushButton("Zoom Original")
        self.btn_zoom_orig.setFixedHeight(34)
        self.btn_zoom_orig.setStyleSheet(BUTTON_DISABLED_STYLE)
        self.btn_zoom_orig.setEnabled(False)
        self.btn_zoom_orig.clicked.connect(self._zoom_original)
        btn_row.addWidget(self.btn_zoom_orig)

        self.btn_save_comp = QPushButton("Save Compressed")
        self.btn_save_comp.setFixedHeight(34)
        self.btn_save_comp.setStyleSheet(BUTTON_DISABLED_STYLE)
        self.btn_save_comp.setEnabled(False)
        self.btn_save_comp.clicked.connect(lambda: self._save_frame("comp"))
        btn_row.addWidget(self.btn_save_comp)

        self.btn_zoom_comp = QPushButton("Zoom Compressed")
        self.btn_zoom_comp.setFixedHeight(34)
        self.btn_zoom_comp.setStyleSheet(BUTTON_DISABLED_STYLE)
        self.btn_zoom_comp.setEnabled(False)
        self.btn_zoom_comp.clicked.connect(self._zoom_compressed)
        btn_row.addWidget(self.btn_zoom_comp)

        btn_close = QPushButton("Close")
        btn_close.setFixedHeight(34)
        btn_close.setStyleSheet(BUTTON_SELECT_STYLE)
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)

    def set_original_frame(self, png_bytes):
        self._orig_png = png_bytes
        self.compare.set_original(png_bytes)
        self.btn_save_orig.setEnabled(bool(png_bytes))
        if bool(png_bytes):
            self.btn_save_orig.setStyleSheet(BUTTON_SELECT_STYLE)
        ready = (self._orig_png and self._comp_png)
        if ready:
            for b in (self.btn_zoom_orig, self.btn_zoom_comp):
                b.setEnabled(True)
                b.setStyleSheet(BUTTON_SELECT_STYLE)

    def set_compressed_frame(self, png_bytes):
        self._comp_png = png_bytes
        self.compare.set_compressed(png_bytes)
        self.btn_save_comp.setEnabled(bool(png_bytes))
        if bool(png_bytes):
            self.btn_save_comp.setStyleSheet(BUTTON_SELECT_STYLE)
        ready = (self._orig_png and self._comp_png)
        if ready:
            for b in (self.btn_zoom_orig, self.btn_zoom_comp):
                b.setEnabled(True)
                b.setStyleSheet(BUTTON_SELECT_STYLE)

    def _on_compare_side_clicked(self, side):
        if side == "left":
            self._zoom_original()
        else:
            self._zoom_compressed()

    def _zoom_original(self):
        png = self.compare.orig_png_bytes() or self._orig_png
        if png:
            ZoomDialog("Original Frame", png, self).exec()

    def _zoom_compressed(self):
        png = self.compare.comp_png_bytes() or self._comp_png
        if png:
            ZoomDialog("Compressed Frame", png, self).exec()

    def _save_frame(self, which):
        png = self._orig_png if which == "orig" else self._comp_png
        if not png:
            return
        suggested = (
            f"draggy_preview_{which}_original.png"
            if which == "orig"
            else f"draggy_preview_{which}_compressed.png")
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Save frame", suggested, "PNG Image (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        try:
            with open(path, "wb") as f:
                f.write(png)
            self.info_label.setText(
                self.info_label.text() + f"\n✓ Saved: {path}")
        except Exception as e:
            self.info_label.setText(
                self.info_label.text() + f"\n✗ Save failed: {e}")

    def set_info(self, info):
        src_size_mb = info.get("source_size_bytes", 0) / (1024 * 1024)
        est = info.get("estimated_size_mb", 0)
        ratio = (est / src_size_mb * 100) if src_size_mb > 0 else 0
        warnings_text = "\n".join(info.get("warnings", []))
        if warnings_text:
            warnings_text = f"\n\n{warnings_text}"

        text = (
            f"Algorithm: {info.get('algorithm', 'Unknown')}\n"
            f"Codec: {info.get('codec', 'Unknown')}    "
            f"Resolution: {info.get('output_resolution', 'Original')}\n"
            f"Video bitrate: {info.get('video_bitrate_kbps', 0)} kbps    "
            f"Audio: {info.get('audio_codec', 'copy')}"
            f" ({info.get('audio_bitrate_kbps', 0)} kbps)"
            f"{' + Boost' if info.get('audio_boost') else ''}\n"
            f"Source size: {src_size_mb:.1f} MB    "
            f"Estimated output: {est:.1f} MB    "
            f"({ratio:.0f}% of source)"
            f"{warnings_text}"
        )
        self.info_label.setText(text)

    def set_progress(self, pct):
        self.progress.setValue(pct)

    def set_failed(self, msg):
        self.progress.setValue(0)
        self.info_label.setText(f"Preview failed:\n{msg}")
        self.info_label.setStyleSheet(
            f"background-color: {BG_SECONDARY}; border: 1px solid #F85149; "
            "border-radius: 8px; color: #F85149; font-size: 12px; padding: 10px;")

    def closeEvent(self, event):
        if self._preview_thread is not None:
            self._preview_thread.cancel()
            self._preview_thread.cleanup_tempfiles()
        super().closeEvent(event)


class Window(QWidget):
    def __init__(self, hw_data=None) -> None:
        super().__init__()
        self._force_close = False
        self.is_audio_only = False
        self.label_log = None
        self.progress_bar = None
        self.settings: dict = load_settings()

        if hw_data:
            self.hw_info = hw_data.get("hw_info", {"cpu": "Unknown", "gpus": []})
            self.all_encoders = hw_data.get("encoders", ["libx264"])
        else:
            from src.thread import get_hardware_info, get_available_encoders
            self.hw_info = get_hardware_info()
            self.all_encoders = get_available_encoders()

        self.setMinimumSize(WINDOW_MIN.w, WINDOW_MIN.h)
        self.setWindowTitle(g.TITLE)
        icon_path = Path(g.res_dir) / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setAcceptDrops(True)
        self.setStyleSheet(GLOBAL_STYLE)

        self.setup_ui()
        self.setup_tray_icon()
        self._init_device_codec_export()
        self._restore_settings()

    # ── Tray ──

    def setup_tray_icon(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon_path = Path(g.res_dir) / "icon.ico"
        if not icon_path.exists():
            return
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon(str(icon_path)))
        self.tray_icon.setToolTip(g.TITLE)
        self.tray_menu = QMenu()
        restore_action = QAction("Mostrar", self)
        restore_action.triggered.connect(self.restore_window)
        quit_action = QAction("Salir", self)
        quit_action.triggered.connect(self.quit_application)
        self.tray_menu.addAction(restore_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.show()

    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.restore_window()

    def restore_window(self):
        self.show()
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def quit_application(self):
        self._force_close = True
        self.close()
        QApplication.quit()

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            if self.isMinimized():
                self.hide()
                event.accept()
        super().changeEvent(event)

    # ── UI Setup ──

    def setup_ui(self):
        self.label_log = QLabel(g.READY_TEXT)
        self.progress_bar = QProgressBar()

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        # ── Top buttons ──
        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        self.button_select = QPushButton("Select Videos")
        self.button_select.setFixedHeight(44)
        self.button_select.setStyleSheet(BUTTON_SELECT_STYLE)
        self.button_select.clicked.connect(self.select_videos)

        self.button_output = QPushButton("Output Folder")
        self.button_output.setFixedHeight(44)
        self.button_output.setStyleSheet(BUTTON_SELECT_STYLE)
        self.button_output.clicked.connect(self.select_output_dir)

        self.button_hardware = QPushButton("Hardware Info")
        self.button_hardware.setFixedHeight(44)
        self.button_hardware.setStyleSheet(BUTTON_SELECT_STYLE)
        self.button_hardware.clicked.connect(self.show_hardware_info)

        top_row.addWidget(self.button_select)
        top_row.addWidget(self.button_output)
        top_row.addWidget(self.button_hardware)
        root.addLayout(top_row)

        # ── GPU info bar ──
        self.gpu_info_label = QLabel("")
        self.gpu_info_label.setStyleSheet(f"color: {ACCENT_CYAN}; font-size: 12px; font-weight: bold; padding: 2px 8px;")
        gpu_info_frame = QFrame()
        gpu_info_frame.setStyleSheet(f"QFrame {{ background-color: {BG_TERTIARY}; border: 1px solid {BORDER_DEFAULT}; border-radius: 6px; }}")
        gpu_info_layout = QHBoxLayout(gpu_info_frame)
        gpu_info_layout.setContentsMargins(8, 4, 8, 4)
        gpu_info_layout.setSpacing(6)
        gpu_icon = QLabel("GPU")
        gpu_icon.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-weight: bold;")
        gpu_info_layout.addWidget(gpu_icon)
        gpu_info_layout.addWidget(self.gpu_info_label)
        gpu_info_layout.addStretch()
        root.addWidget(gpu_info_frame)

        # ── Pipeline visual ──
        self.pipeline = PipelineWidget()
        self.pipeline._init_steps()
        self.pipeline.steps["import"].step_clicked.connect(lambda: self._show_step("import"))
        self.pipeline.steps["upscale"].step_clicked.connect(lambda: self._show_step("upscale"))
        self.pipeline.steps["interpolate"].step_clicked.connect(lambda: self._show_step("interpolate"))
        self.pipeline.steps["colorize"].step_clicked.connect(lambda: self._show_step("colorize"))
        self.pipeline.steps["compress"].step_clicked.connect(lambda: self._show_step("compress"))

        pipe_frame = QFrame()
        pipe_frame.setStyleSheet(f"QFrame {{ background-color: {BG_SECONDARY}; border: 1px solid {BORDER_DEFAULT}; border-radius: 10px; }}")
        pipe_layout = QVBoxLayout(pipe_frame)
        pipe_layout.setContentsMargins(0, 0, 0, 0)
        pipe_layout.addWidget(self.pipeline)
        root.addWidget(pipe_frame)

        # ── Settings stack (fills available space) ──
        self.settings_stack = QStackedWidget()
        self.settings_stack.setStyleSheet(f"""
            QStackedWidget {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: 10px;
            }}
        """)

        self.page_import = ImportInfoPage()
        self.page_upscale = UpscaleSettingsPage()
        self.page_interpolate = InterpolateSettingsPage()
        self.page_colorize = ColorizeSettingsPage()
        self.page_compress = CompressSettingsPage()

        self.settings_stack.addWidget(self.page_import)
        self.settings_stack.addWidget(self.page_upscale)
        self.settings_stack.addWidget(self.page_interpolate)
        self.settings_stack.addWidget(self.page_colorize)
        self.settings_stack.addWidget(self.page_compress)
        self.settings_stack.setCurrentIndex(0)

        root.addWidget(self.settings_stack, 1)  # stretch=1, fills space

        # ── Action buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.button_compress = QPushButton("Compress")
        self.button_compress.setFixedHeight(44)
        self.button_compress.setEnabled(False)
        self.button_compress.setStyleSheet(BUTTON_DISABLED_STYLE)
        self.button_compress.clicked.connect(self.compress_videos)

        self.button_abort = QPushButton("Abort")
        self.button_abort.setFixedHeight(44)
        self.button_abort.setEnabled(False)
        self.button_abort.setStyleSheet(BUTTON_DISABLED_STYLE)
        self.button_abort.clicked.connect(self.abort_compression)

        self.button_preview = QPushButton("Preview")
        self.button_preview.setFixedHeight(44)
        self.button_preview.setEnabled(False)
        self.button_preview.setStyleSheet(BUTTON_DISABLED_STYLE)
        self.button_preview.clicked.connect(self._show_preview)

        btn_row.addWidget(self.button_compress)
        btn_row.addWidget(self.button_preview)
        btn_row.addWidget(self.button_abort)
        root.addLayout(btn_row)

        # ── Log + Progress ──
        self.label_log.setWordWrap(True)
        self.label_log.setStyleSheet(LABEL_LOG_STYLE)
        self.label_log.setMinimumHeight(40)
        self.label_log.setMaximumHeight(60)
        root.addWidget(self.label_log)

        self.progress_bar.setRange(0, 100)
        self.progress_bar.setStyleSheet(PROGRESS_BAR_STYLE)
        self.progress_bar.setFixedHeight(20)
        root.addWidget(self.progress_bar)

        # ── Error ──
        self.label_error = QLabel("")
        self.label_error.setStyleSheet(ERROR_LABEL_STYLE)
        self.label_error.setMinimumHeight(28)
        self.label_error.hide()
        root.addWidget(self.label_error)

    def _show_step(self, step_name):
        page_map = {"import": 0, "upscale": 1, "interpolate": 2, "colorize": 3, "compress": 4}
        if step_name in page_map:
            self.settings_stack.setCurrentIndex(page_map[step_name])

    # ── Device / Codec / Export ──

    def _init_device_codec_export(self):
        panel = self.page_compress
        devices = ["CPU"]
        gpu_names_lower = [g.lower() for g in self.hw_info["gpus"]]
        has_intel = any("intel" in g for g in gpu_names_lower)
        has_amd = any("amd" in g or "radeon" in g for g in gpu_names_lower)
        has_nvidia = any("nvidia" in g for g in gpu_names_lower)
        if has_intel: devices.append("iGPU (Intel)")
        if has_amd: devices.append("iGPU (AMD)")
        if has_nvidia: devices.append("NVIDIA GPU")
        if has_amd: devices.append("AMD GPU")
        devices = list(dict.fromkeys(devices))
        self.video_devices = devices
        panel.combo_device.addItems(devices)
        panel.combo_device.currentIndexChanged.connect(self._on_device_changed)

        # Update GPU info label with model + VRAM
        try:
            from src.ai_tools import get_gpu_vram_display
            model, vram_gb, display_text = get_gpu_vram_display()
            if model and model != "Unknown GPU":
                self.gpu_info_label.setText(display_text)
            else:
                self.gpu_info_label.setText("No GPU detected")
        except Exception:
            self.gpu_info_label.setText("GPU info unavailable")

        # Show encoder errors (e.g. NVIDIA driver too old)
        import src.globals as g
        encoder_errors = getattr(g, "encoder_errors", {})
        if encoder_errors:
            has_nvenc_driver_issue = False
            for enc_name, value in encoder_errors.items():
                if "nvenc" not in enc_name:
                    continue
                reason = value[1] if isinstance(value, tuple) else value
                if isinstance(reason, str) and "driver" in reason.lower():
                    has_nvenc_driver_issue = True
                    break
            if has_nvenc_driver_issue:
                warning_msg = "⚠ NVIDIA driver too old for NVENC (H264/H265/AV1). Use CPU codecs or update driver to 610+. See libx264/libx265 as fallback."
                if self.label_log:
                    self.label_log.setText(warning_msg)
                else:
                    print(warning_msg)

        # If no NVENC encoders but NVIDIA GPU detected, add software fallbacks
        if has_nvidia and not any("nvenc" in e.lower() for e in self.all_encoders):
            self.all_encoders.extend(["libx264", "libx265"])

        self.all_video_exports = ["Original", "mp4", "mkv", "avi", "mov", "webm", "flv", "m4v"]
        self.audio_exports = ["Original", "mp3", "flac", "wav", "m4a", "ogg", "wma"]
        self.audio_codecs = [
            "MP3 128kbps", "MP3 192kbps", "MP3 320kbps",
            "AAC 128kbps", "AAC 192kbps", "AAC 256kbps",
            "FLAC (Lossless)", "WAV (Uncompressed)", "Copy (Original)"
        ]
        self.codec_format_map = {
            "h264_nvenc": ["mp4", "mkv", "avi", "mov", "flv", "m4v"],
            "hevc_nvenc": ["mp4", "mkv", "mov", "m4v"],
            "av1_nvenc":  ["mp4", "mkv", "webm"],
            "h264_amf":   ["mp4", "mkv", "avi", "mov", "flv", "m4v"],
            "hevc_amf":   ["mp4", "mkv", "mov", "m4v"],
            "av1_amf":    ["mp4", "mkv", "webm"],
            "h264_qsv":   ["mp4", "mkv", "avi", "mov", "flv", "m4v"],
            "hevc_qsv":   ["mp4", "mkv", "mov", "m4v"],
            "av1_qsv":    ["mp4", "mkv", "webm"],
            "h264_vaapi":  ["mp4", "mkv", "avi", "mov", "flv", "m4v"],
            "hevc_vaapi":  ["mp4", "mkv", "mov", "m4v"],
            "av1_vaapi":   ["mp4", "mkv", "webm"],
            "libx264":     ["mp4", "mkv", "avi", "mov", "flv", "m4v"],
            "libx265":     ["mp4", "mkv", "mov", "m4v"],
            "libsvtav1":   ["mp4", "mkv", "webm"],
            "libaom-av1":  ["mp4", "mkv", "webm"],
            "libvvenc":    ["mp4", "mkv"],
            "ffv1":        ["mkv", "avi"],
        }
        self._update_codec_list()
        panel.combo_codec.currentIndexChanged.connect(self._update_export_formats)
        panel.combo_codec.currentIndexChanged.connect(self._on_codec_changed)
        panel.combo_audio.currentIndexChanged.connect(self._on_audio_changed)

    def _on_device_changed(self):
        if self.is_audio_only:
            return
        panel = self.page_compress
        device = panel.combo_device.currentText()

        hw_families = {
            "CPU": [],
            "iGPU (Intel)": ["qsv"],
            "iGPU (AMD)": ["amf"],
            "NVIDIA GPU": ["nvenc"],
            "AMD GPU": ["amf"],
        }
        selected_family = hw_families.get(device, [])
        hw_names = ("nvenc", "amf", "qsv", "vaapi")

        # When a hardware device is picked, show only its hardware codecs so
        # the user does not accidentally pick a slow software fallback. If no
        # HW codec for that family is detected, fall back to every codec with
        # a hint in the log label so the user is never stuck.
        import src.globals as g
        encoder_errors = getattr(g, "encoder_errors", {})

        if selected_family:
            matching_hw = []
            for enc in self.all_encoders:
                base = enc.split(" ")[0]
                if any(fam in base for fam in selected_family):
                    matching_hw.append(enc)
            def _sort_key(name):
                return (1, name) if "⚠" in name else (0, name)
            filtered = sorted(set(matching_hw), key=_sort_key)
            if not filtered:
                shown = ", ".join(selected_family).upper()
                self.label_log.setText(
                    f"{device} selected, but no compatible {shown} codec "
                    "was detected. Showing all available codecs below."
                )
                filtered = list(self.all_encoders)
        else:
            # CPU: hide hardware codecs to keep the list clean
            filtered = [
                e for e in self.all_encoders
                if not any(hw in e.split(" ")[0] for hw in hw_names)
            ]

        if not filtered:
            filtered = ["libx264"]

        panel.combo_codec.blockSignals(True)
        panel.combo_codec.clear()
        panel.combo_codec.addItems(filtered)
        panel.combo_codec.blockSignals(False)
        self._update_export_formats()

    def _update_codec_list(self):
        self._on_device_changed()
        if not self.is_audio_only:
            panel = self.page_compress
            if panel.combo_codec.findText("Copy (Remux)") < 0:
                panel.combo_codec.insertItem(0, "Copy (Remux)")

    def _update_export_formats(self):
        panel = self.page_compress
        codec_text = panel.combo_codec.currentText()
        if not codec_text:
            return
        pure_codec = codec_text.split(" ")[0]
        if pure_codec == "Copy":
            compatible = self.all_video_exports
        else:
            compatible = self.codec_format_map.get(pure_codec, ["mp4", "mkv", "avi", "mov", "webm", "flv", "m4v"])
        current_export = panel.combo_export.currentText()
        panel.combo_export.blockSignals(True)
        panel.combo_export.clear()
        panel.combo_export.addItem("Original")
        panel.combo_export.addItems(compatible)
        panel.combo_export.blockSignals(False)
        idx = panel.combo_export.findText(current_export)
        if idx >= 0:
            panel.combo_export.setCurrentIndex(idx)

    def _on_codec_changed(self):
        panel = self.page_compress
        codec_text = panel.combo_codec.currentText()
        is_remux = codec_text == "Copy (Remux)"
        panel.edit_size.setEnabled(not is_remux and not self.is_audio_only)
        panel.combo_resolution.setEnabled(not is_remux and not self.is_audio_only)
        panel.combo_device.setEnabled(not is_remux and not self.is_audio_only)
        if is_remux:
            panel.edit_size.setStyleSheet(LINEEDIT_STYLE.replace("border: 1px solid #444;", "border: 1px solid #333; color: #666;"))
            panel.combo_resolution.setStyleSheet(COMBOBOX_STYLE.replace("border: 1px solid #444;", "border: 1px solid #333; color: #666;"))
            panel.combo_device.setStyleSheet(COMBOBOX_STYLE.replace("border: 1px solid #444;", "border: 1px solid #333; color: #666;"))
        else:
            panel.edit_size.setStyleSheet(LINEEDIT_STYLE)
            panel.combo_resolution.setStyleSheet(COMBOBOX_STYLE)
            panel.combo_device.setStyleSheet(COMBOBOX_STYLE)
        self._on_audio_changed()

    def _on_audio_changed(self):
        panel = self.page_compress
        audio_text = panel.combo_audio.currentText()
        can_boost = audio_text not in ("Copy (original)", "No Audio")
        panel.check_audio_boost.setEnabled(can_boost)
        if can_boost:
            panel.check_audio_boost.setText(self._audio_boost_text_active)
            panel.check_audio_boost.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: 11px;"
            )
            panel.label_audio_boost_info.setText(
                "EBU R128 loudnorm will be applied during encoding."
            )
            panel.label_audio_boost_info.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: 9px; font-style: italic;"
            )
        else:
            panel.check_audio_boost.setChecked(False)
            panel.check_audio_boost.setText(self._audio_boost_text_disabled)
            panel.check_audio_boost.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: 11px;"
            )
            reason = (
                "Audio is set to 'Copy (original)', which streams audio "
                "directly without re-encoding, so no filter can be applied."
                if audio_text == "Copy (original)"
                else "No audio stream is being produced."
            )
            panel.label_audio_boost_info.setText(reason)
            panel.label_audio_boost_info.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: 9px; font-style: italic;"
            )

    def show_hardware_info(self):
        diag = HardwareInfoDialog(self.hw_info, self)
        diag.exec()

    # ── Video Selection ──

    def select_videos(self):
        self.label_error.hide()
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Media Files", "",
            "Media Files (*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.m4v *.mp3 *.wav *.flac *.m4a *.aac *.wma *.ogg);;All Files (*.*)",
        )
        if file_paths:
            self.add_videos(file_paths)

    def select_output_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", g.output_dir)
        if folder:
            g.output_dir = folder
            self.button_output.setText(f"Output: ...{os.sep}{os.path.basename(folder)}")
            self.button_output.setToolTip(folder)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        self.label_error.hide()
        files = [url.toLocalFile() for url in event.mimeData().urls()]
        media_extensions = ('.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v',
                            '.mp3', '.wav', '.flac', '.m4a', '.aac', '.wma', '.ogg')
        media_files = [f for f in files if f.lower().endswith(media_extensions)]
        if media_files:
            self.add_videos(media_files)

    def add_videos(self, file_paths):
        for path in file_paths:
            if path in g.queue:
                continue
            g.queue.append(path)

        self.button_compress.setEnabled(True)
        self.button_compress.setStyleSheet(BUTTON_COMPRESS_STYLE)
        self.button_preview.setEnabled(True)
        self.button_preview.setStyleSheet(BUTTON_SELECT_STYLE)
        self.update_log(f"Selected {len(g.queue)} media file(s).")
        self._check_audio_only()

        last_video = g.queue[-1]
        metadata = get_video_metadata(last_video)
        file_size = os.path.getsize(last_video)
        duration = get_video_length(last_video)
        if duration > 0:
            try:
                panel = self.page_compress
                panel.set_trim_info(f"Full duration: {format_seconds_to_mm_ss(duration)}.")
            except Exception:
                pass

        page = self.page_import
        page.label_path.setText(f"{last_video}")
        page.label_size.setText(f"Size: {human_readable_size(file_size)}")
        page.label_quality.setText(
            f"Video: {metadata.get('codec')} | {metadata.get('depth')} | {metadata.get('bitrate')}\n"
            f"Audio: {metadata.get('audio_codec')} | {metadata.get('audio_bitrate')}\n"
            f"Res: {metadata.get('resolution')}"
        )

        panel = self.page_compress
        _, ext = os.path.basename(last_video).rsplit(".", 1)
        panel.combo_export.setItemText(0, f"Original (.{ext})")
        panel.combo_export.setCurrentIndex(0)

        orig_bitrate = metadata.get("bitrate", "Unknown")
        if orig_bitrate != "Unknown":
            panel.label_orig_bitrate.setText(f"Original video bitrate: {orig_bitrate}")
        else:
            panel.label_orig_bitrate.setText("")
        panel._on_compression_mode_changed()

    def _check_audio_only(self):
        audio_extensions = ('.mp3', '.wav', '.flac', '.m4a', '.aac', '.wma', '.ogg')
        if not g.queue:
            return
        self.is_audio_only = all(f.lower().endswith(audio_extensions) for f in g.queue)
        panel = self.page_compress
        panel.combo_device.blockSignals(True)
        panel.combo_export.blockSignals(True)
        panel.combo_device.clear()
        panel.combo_export.clear()
        if self.is_audio_only:
            panel.combo_device.addItems(["CPU"])
            panel.combo_export.addItems(self.audio_exports)
            panel.combo_codec.clear()
            panel.combo_codec.addItems(self.audio_codecs)
        else:
            panel.combo_device.addItems(self.video_devices)
            self._update_export_formats()
            self._update_codec_list()
        panel.combo_device.blockSignals(False)
        panel.combo_export.blockSignals(False)

    # ── Settings Restore / Save ──

    def _restore_settings(self):
        p = self.page_compress
        p.edit_size.setText(str(self.settings.get("target_size", 20.0)))

        idx = p.combo_device.findText(self.settings.get("device", "CPU"))
        if idx >= 0: p.combo_device.setCurrentIndex(idx)
        idx = p.combo_codec.findText(self.settings.get("codec", "libx264"))
        if idx >= 0: p.combo_codec.setCurrentIndex(idx)
        idx = p.combo_resolution.findText(self.settings.get("resolution", "Original"))
        if idx >= 0: p.combo_resolution.setCurrentIndex(idx)
        idx = p.combo_audio.findText(self.settings.get("audio", "Copy (original)"))
        if idx >= 0: p.combo_audio.setCurrentIndex(idx)
        p.check_audio_boost.setChecked(self.settings.get("audio_boost", False))

        # Trim
        trim_enabled = bool(self.settings.get("trim_enabled", False))
        p.check_trim.setChecked(trim_enabled)
        if trim_enabled:
            ts = self.settings.get("trim_start_s")
            te = self.settings.get("trim_end_s")
            try:
                if ts is not None:
                    t = QTime(0, 0).addSecs(int(round(ts)))
                    p.edit_trim_start.setTime(t)
            except Exception:
                pass
            if te is not None:
                try:
                    t = QTime(0, 0).addSecs(int(round(te)))
                    p.edit_trim_end.setTime(t)
                except Exception:
                    p.edit_trim_end.setTime(QTime(0, 0))

        # AI settings
        up = self.page_upscale
        saved = self.settings.get("upscale_model", "")
        if saved:
            idx = up.combo_model.findData(saved)
            if idx >= 0: up.combo_model.setCurrentIndex(idx)
        idx = up.combo_scale.findText(self.settings.get("ai_scale", "4x"))
        if idx >= 0: up.combo_scale.setCurrentIndex(idx)
        idx = up.combo_device.findText(self.settings.get("ai_device_upscale", "Auto"))
        if idx >= 0: up.combo_device.setCurrentIndex(idx)

        ip = self.page_interpolate
        saved = self.settings.get("interp_model", "")
        if saved:
            idx = ip.combo_model.findData(saved)
            if idx >= 0: ip.combo_model.setCurrentIndex(idx)
        idx = ip.combo_mult.findText(self.settings.get("fps_multiplier", "2x"))
        if idx >= 0: ip.combo_mult.setCurrentIndex(idx)
        idx = ip.combo_device.findText(self.settings.get("ai_device_interpolate", "Auto"))
        if idx >= 0: ip.combo_device.setCurrentIndex(idx)

        co = self.page_colorize
        saved = self.settings.get("colorize_model", "")
        if saved:
            idx = co.combo_model.findData(saved)
            if idx >= 0: co.combo_model.setCurrentIndex(idx)
        idx = co.combo_device.findText(self.settings.get("ai_device_colorize", "Auto"))
        if idx >= 0: co.combo_device.setCurrentIndex(idx)

        # Restore pipeline order and steps
        saved_order = self.settings.get("ai_order", ["upscale", "interpolate", "colorize"])
        if saved_order:
            ai_steps = ["upscale", "interpolate", "colorize"]
            valid_order = [s for s in saved_order if s in ai_steps]
            for s in ai_steps:
                if s not in valid_order:
                    valid_order.append(s)
            self.pipeline.step_names = ["import"] + valid_order + ["compress"]
            self.pipeline._build_pipeline()

        for step in ["upscale", "interpolate", "colorize"]:
            if self.settings.get(f"step_{step}", False):
                self.pipeline.set_step_state(step, "on")

        # Show compress page by default
        self._show_step("compress")

    def _save_current_settings(self):
        try:
            p = self.page_compress
            self.settings["target_size"] = float(p.edit_size.text())
            self.settings["resolution"] = p.combo_resolution.currentText()
            self.settings["device"] = p.combo_device.currentText()
            self.settings["codec"] = p.combo_codec.currentText()
            self.settings["audio"] = p.combo_audio.currentText()
            self.settings["audio_boost"] = p.check_audio_boost.isChecked()
            trim_enabled, trim_start, trim_end = p.trim_state()
            self.settings["trim_enabled"] = trim_enabled
            if trim_enabled:
                self.settings["trim_start_s"] = trim_start
                self.settings["trim_end_s"] = (""
                                               if trim_end is None
                                               else trim_end)
            else:
                self.settings["trim_start_s"] = ""
                self.settings["trim_end_s"] = ""

            up = self.page_upscale
            if up.combo_model.currentData():
                self.settings["upscale_model"] = up.combo_model.currentData()
            self.settings["ai_scale"] = up.combo_scale.currentText()
            self.settings["ai_device_upscale"] = up.combo_device.currentText()

            ip = self.page_interpolate
            if ip.combo_model.currentData():
                self.settings["interp_model"] = ip.combo_model.currentData()
            self.settings["fps_multiplier"] = ip.combo_mult.currentText()
            self.settings["ai_device_interpolate"] = ip.combo_device.currentText()

            co = self.page_colorize
            if co.combo_model.currentData():
                self.settings["colorize_model"] = co.combo_model.currentData()
            self.settings["ai_device_colorize"] = co.combo_device.currentText()

            self.settings["ai_order"] = self.pipeline.get_ai_order()

            for step in ["upscale", "interpolate", "colorize"]:
                self.settings[f"step_{step}"] = self.pipeline.steps[step].is_enabled()

            save_settings(self.settings)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def closeEvent(self, event):
        if not self._force_close:
            self._save_current_settings()
            self.hide()
            event.ignore()
            return
        self._save_current_settings()
        kill_ffmpeg()
        if os.path.exists(os.path.join(g.root_dir, "TEMP")):
            os.remove(os.path.join(g.root_dir, "TEMP"))
        event.accept()

    # ── Compression ──

    def _show_preview(self):
        if not g.queue:
            return
        file_path = g.queue[0]
        panel = self.page_compress
        compression_mode = "bitrate" if panel.combo_compression.currentText() == "Target Bitrate (kbps)" else "size"
        audio_codec = panel.audio_options.get(panel.combo_audio.currentText(), "copy")
        try:
            target_size = float(panel.edit_size.text()) if panel.edit_size.text() else 20.0
        except ValueError:
            target_size = 20.0
        try:
            target_bitrate = int(panel.edit_bitrate.text()) if panel.edit_bitrate.text() else 5000
        except ValueError:
            target_bitrate = 5000
        trim_enabled, trim_start, trim_end = panel.trim_state()

        from os.path import basename
        dlg = PreviewDialog(basename(str(file_path)), self)
        thread = PreviewThread(
            file_path,
            compression_mode,
            target_size,
            target_bitrate,
            panel.combo_codec.currentText(),
            audio_codec,
            panel.combo_resolution.currentText(),
            panel.check_audio_boost.isChecked(),
            trim_enabled=trim_enabled,
            trim_start_s=trim_start,
            trim_end_s=trim_end,
        )
        thread.info_ready.connect(dlg.set_info)
        thread.original_frame_ready.connect(dlg.set_original_frame)
        thread.compressed_frame_ready.connect(dlg.set_compressed_frame)
        thread.progress.connect(dlg.set_progress)
        thread.failed.connect(dlg.set_failed)
        thread.finished_ok.connect(lambda info: dlg.progress.setValue(100))
        dlg._preview_thread = thread
        thread.start()
        dlg.show()

    def compress_videos(self):
        if not g.queue:
            return
        g.compressing = True
        self.label_error.hide()
        self.last_error_occured = False
        self._set_ui_enabled(False)

        panel = self.page_compress
        compression_mode = "bitrate" if panel.combo_compression.currentText() == "Target Bitrate (kbps)" else "size"
        export_choice = panel.combo_export.currentText()
        export_format = "Original" if "Original" in export_choice else export_choice
        audio_codec = panel.audio_options.get(panel.combo_audio.currentText(), "copy")
        trim_enabled, trim_start, trim_end = panel.trim_state()

        ai_config = self._get_ai_config()

        try:
            target_size = float(panel.edit_size.text()) if panel.edit_size.text() else 20.0
        except ValueError:
            target_size = 20.0
        try:
            target_bitrate = int(panel.edit_bitrate.text()) if panel.edit_bitrate.text() else 5000
        except ValueError:
            target_bitrate = 5000

        self.compress_thread = CompressionThread(
            target_size,
            panel.combo_codec.currentText(),
            export_format,
            audio_codec,
            self.is_audio_only,
            panel.combo_resolution.currentText(),
            panel.edit_filename.text().strip(),
            ai_config=ai_config,
            audio_boost=panel.check_audio_boost.isChecked(),
            compression_mode=compression_mode,
            target_bitrate_kbps=target_bitrate,
            trim_enabled=trim_enabled,
            trim_start_s=trim_start,
            trim_end_s=trim_end,
        )
        if self.compress_thread:
            self.compress_thread.completed.connect(self._on_completed)
            self.compress_thread.update_log.connect(self.update_log)
            self.compress_thread.update_progress.connect(self.update_progress)
            self.compress_thread.error_msg.connect(self.show_error)
            self.compress_thread.start()

    def _get_ai_config(self):
        steps = self.pipeline.steps
        ai_order = self.pipeline.get_ai_order()

        active = []
        for step_name in ai_order:
            if steps[step_name].is_enabled():
                active.append(step_name)

        if not active:
            return None

        mode_label = {"upscale": "Upscale", "interpolate": "Interpolation", "colorize": "Colorize"}
        config = {"mode": " + ".join(mode_label.get(s, s) for s in active)}
        config["ai_order"] = list(active)

        if steps["colorize"].is_enabled():
            config["colorize_enabled"] = True
            config["colorize_model"] = self.page_colorize.combo_model.currentData() or "deoldify-artistic"
            config["colorize_render_factor"] = 256
            config["colorize_device"] = _parse_ai_device(self.page_colorize.combo_device.currentText())

        if steps["upscale"].is_enabled():
            config["upscale_model"] = self.page_upscale.combo_model.currentData() or "realesrgan-x4plus"
            config["upscale_scale"] = int(self.page_upscale.combo_scale.currentText().replace("x", ""))
            config["upscale_device"] = _parse_ai_device(self.page_upscale.combo_device.currentText())

        if steps["interpolate"].is_enabled():
            config["interp_model"] = self.page_interpolate.combo_model.currentData() or "rife-v4.6"
            config["interp_multiplier"] = int(self.page_interpolate.combo_mult.currentText().replace("x", ""))
            config["interp_device"] = _parse_ai_device(self.page_interpolate.combo_device.currentText())

        return config

    def _set_ui_enabled(self, enabled):
        style = BUTTON_SELECT_STYLE if enabled else BUTTON_DISABLED_STYLE
        self.button_select.setEnabled(enabled)
        self.button_select.setStyleSheet(style)
        self.button_output.setEnabled(enabled)
        self.button_output.setStyleSheet(style)

        if g.queue and enabled:
            self.button_compress.setEnabled(True)
            self.button_compress.setStyleSheet(BUTTON_COMPRESS_STYLE)
            self.button_preview.setEnabled(True)
            self.button_preview.setStyleSheet(BUTTON_SELECT_STYLE)
        else:
            self.button_compress.setEnabled(False)
            self.button_compress.setStyleSheet(BUTTON_DISABLED_STYLE)
            self.button_preview.setEnabled(False)
            self.button_preview.setStyleSheet(BUTTON_DISABLED_STYLE)

        self.button_abort.setEnabled(not enabled)
        self.button_abort.setStyleSheet(BUTTON_ABORT_STYLE if not enabled else BUTTON_DISABLED_STYLE)

        p = self.page_compress
        p.edit_size.setEnabled(enabled)
        p.edit_filename.setEnabled(enabled)
        p.combo_resolution.setEnabled(enabled)
        p.combo_device.setEnabled(enabled)
        p.combo_codec.setEnabled(enabled)
        p.combo_export.setEnabled(enabled)
        p.combo_audio.setEnabled(enabled)
        p.check_audio_boost.setEnabled(enabled)
        p.check_trim.setEnabled(enabled)
        p.edit_trim_start.setEnabled(enabled)
        p.edit_trim_end.setEnabled(enabled)
        self.page_upscale.combo_model.setEnabled(enabled)
        self.page_upscale.combo_scale.setEnabled(enabled)
        self.page_upscale.combo_device.setEnabled(enabled)
        self.page_interpolate.combo_model.setEnabled(enabled)
        self.page_interpolate.combo_mult.setEnabled(enabled)
        self.page_interpolate.combo_device.setEnabled(enabled)
        self.page_colorize.combo_model.setEnabled(enabled)
        self.page_colorize.combo_device.setEnabled(enabled)
        if enabled:
            self._on_codec_changed()

    def abort_compression(self):
        kill_ffmpeg()
        self._on_completed(True)

    def _on_completed(self, aborted=False):
        g.compressing = False
        if self.compress_thread:
            self.compress_thread.terminate()
        self._set_ui_enabled(True)

        was_error = getattr(self, 'last_error_occured', False)
        n = Notify()
        if was_error:
            n.title = "Error!"
            n.message = "There was an error during compression."
        else:
            n.title = "Done!" if not aborted else "Aborted!"
            n.message = "Your videos are ready." if not aborted else "Processing cancelled."
        n.icon = os.path.join(g.res_dir, "icon.ico")
        n.send()

        if not aborted and not was_error and hasattr(os, "startfile"):
            os.startfile(g.output_dir)

    # ── Utils ──

    def update_log(self, text):
        if self.label_log:
            self.label_log.setText(text)
        print(text)

    def update_progress(self, value):
        if self.progress_bar:
            self.progress_bar.setValue(value)

    def show_error(self, message):
        self.label_error.setText(message)
        self.label_error.show()
        self.last_error_occured = True


def start_main_window(hw_data):
    global window
    window = Window(hw_data)
    window.show()


if __name__ == "__main__":
    if platform.system() == "Windows":
        myappid = u"thedevil4k.draggyencoder.v1"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    g.verify_directories()

    icon_path = Path(g.res_dir) / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    loader = LoadingWindow()
    loader.finished.connect(start_main_window)
    loader.show()

    sys.exit(app.exec())
