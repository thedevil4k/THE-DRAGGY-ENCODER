import json
import re
import sys
import os
import platform
import subprocess
import psutil
from pathlib import Path
import src.globals as g
from notifypy import Notify
from src.thread import CompressionThread, get_video_metadata, human_readable_size
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
)
from PySide6.QtGui import QIcon, QAction, QFont, QPainter, QColor, QPolygon, QPixmap
from PySide6.QtCore import Qt, QEvent, Signal, QPoint
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

        title = QLabel("📦  Compression Settings")
        title.setStyleSheet(f"color: {ACCENT_CYAN}; font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        self.edit_size = QLineEdit("")
        layout.addLayout(create_setting_row("Size (MB)", self.edit_size))

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

        layout.addStretch()


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


# ──────────────────────────────────────────────
# Main Window
# ──────────────────────────────────────────────

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

        top_row.addWidget(self.button_select)
        top_row.addWidget(self.button_output)
        root.addLayout(top_row)

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

        btn_row.addWidget(self.button_compress)
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
        has_intel = any("Intel" in gpu for gpu in self.hw_info["gpus"])
        has_amd = any("AMD" in gpu or "Radeon" in gpu for gpu in self.hw_info["gpus"])
        has_nvidia = any("NVIDIA" in gpu for gpu in self.hw_info["gpus"])
        if has_intel: devices.append("iGPU (Intel)")
        if has_amd: devices.append("iGPU (AMD)")
        if has_nvidia or (has_amd and len(self.hw_info["gpus"]) > 1):
            devices.append("Dedicated GPU")
        devices = list(dict.fromkeys(devices))
        self.video_devices = devices
        panel.combo_device.addItems(devices)
        panel.combo_device.currentIndexChanged.connect(self._on_device_changed)

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

    def _on_device_changed(self):
        if self.is_audio_only:
            return
        panel = self.page_compress
        device = panel.combo_device.currentText()
        panel.combo_codec.blockSignals(True)
        panel.combo_codec.clear()
        match device:
            case "CPU":
                filtered = [e for e in self.all_encoders if not any(hw in e for hw in ["nvenc", "amf", "qsv"])]
            case d if "iGPU (Intel)" in d:
                filtered = [e for e in self.all_encoders if "qsv" in e or ("vaapi" in e and platform.system() == "Linux")]
            case d if "iGPU (AMD)" in d:
                filtered = [e for e in self.all_encoders if "amf" in e or ("vaapi" in e and platform.system() == "Linux")]
            case d if "Dedicated" in d:
                filtered = [e for e in self.all_encoders if "nvenc" in e or "amf" in e or ("vaapi" in e and platform.system() == "Linux")]
            case _:
                filtered = ["libx264"]
        if not filtered:
            filtered = ["libx264"]
        panel.combo_codec.addItems(filtered)
        panel.combo_codec.blockSignals(False)
        self._update_export_formats()

    def _update_codec_list(self):
        self._on_device_changed()

    def _update_export_formats(self):
        panel = self.page_compress
        codec_text = panel.combo_codec.currentText()
        if not codec_text:
            return
        pure_codec = codec_text.split(" ")[0]
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
        self.update_log(f"Selected {len(g.queue)} media file(s).")
        self._check_audio_only()

        last_video = g.queue[-1]
        metadata = get_video_metadata(last_video)
        file_size = os.path.getsize(last_video)

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

    def compress_videos(self):
        if not g.queue:
            return
        g.compressing = True
        self.label_error.hide()
        self.last_error_occured = False
        self._set_ui_enabled(False)

        panel = self.page_compress
        export_choice = panel.combo_export.currentText()
        export_format = "Original" if "Original" in export_choice else export_choice
        audio_codec = panel.audio_options.get(panel.combo_audio.currentText(), "copy")

        ai_config = self._get_ai_config()

        self.compress_thread = CompressionThread(
            float(panel.edit_size.text()),
            panel.combo_codec.currentText(),
            export_format,
            audio_codec,
            self.is_audio_only,
            panel.combo_resolution.currentText(),
            panel.edit_filename.text().strip(),
            ai_config=ai_config,
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
        else:
            self.button_compress.setEnabled(False)
            self.button_compress.setStyleSheet(BUTTON_DISABLED_STYLE)

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
        self.page_upscale.combo_model.setEnabled(enabled)
        self.page_upscale.combo_scale.setEnabled(enabled)
        self.page_upscale.combo_device.setEnabled(enabled)
        self.page_interpolate.combo_model.setEnabled(enabled)
        self.page_interpolate.combo_mult.setEnabled(enabled)
        self.page_interpolate.combo_device.setEnabled(enabled)
        self.page_colorize.combo_model.setEnabled(enabled)
        self.page_colorize.combo_device.setEnabled(enabled)

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
