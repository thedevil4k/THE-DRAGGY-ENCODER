import json
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
    QCheckBox,
    QProgressBar,
    QComboBox,
    QVBoxLayout,
    QHBoxLayout,
    QSpacerItem,
    QSizePolicy,
    QSystemTrayIcon,
    QMenu,
)
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import Qt, QEvent
import ctypes
from src.styles import (
    WINDOW,
    GLOBAL_STYLE,
    SELECT_BUTTON,
    OUTPUT_BUTTON,
    COMPRESS_BUTTON,
    ABORT_BUTTON,
    FILE_SIZE_LABEL,
    FILE_SIZE_ENTRY,
    DEVICE_LABEL,
    DEVICE_COMBOBOX,
    CODEC_LABEL,
    CODEC_COMBOBOX,
    EXPORT_LABEL,
    EXPORT_COMBOBOX,
    AUDIO_LABEL,
    AUDIO_COMBOBOX,
    LOG_AREA,
    INFO_PATH_LABEL,
    LABEL_STYLE,
    INFO_SIZE_LABEL,
    INFO_QUALITY_LABEL,
    ERROR_LABEL,
    ERROR_LABEL_STYLE,
    PROGRESS_BAR,
    BUTTON_DISABLED_STYLE,
    BUTTON_SELECT_STYLE,
    LINEEDIT_STYLE,
    COMBOBOX_STYLE,
    LABEL_LOG_STYLE,
    PROGRESS_BAR_STYLE,
    BUTTON_COMPRESS_STYLE,
    BUTTON_ABORT_STYLE
)

window = None


def load_settings() -> dict:
    # Try loading from writable AppData folder first
    base_data_dir = os.path.join(os.getenv("APPDATA", ""), "DraggyEncoder") if platform.system() == "Windows" else os.path.expanduser("~/.draggy_encoder")
    settings_path = Path(base_data_dir) / "settings.json"
    
    try:
        if settings_path.exists():
            return json.loads(settings_path.read_text())
        
        # Fallback to default settings in res_dir
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
        # Ensure base directory exists
        os.makedirs(base_data_dir, exist_ok=True)
        settings_path.write_text(json.dumps(settings, indent=4))
    except Exception as e:
        print(f"Error saving settings: {e}")


def kill_ffmpeg():
    if platform.system() == "Windows":
        # Fast kill using taskkill
        try:
            subprocess.run(["taskkill", "/F", "/IM", "ffmpeg.exe", "/T"], 
                           creationflags=0x08000000, 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL)
        except Exception:
            pass
    else:
        # Standard psutil fallback for Linux/other
        for proc in psutil.process_iter():
            try:
                if "ffmpeg" in proc.name().lower():
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue


def delete_bin():
    print("@@@@@@@@@@@@@@@@@@@@@@ DELETING BIN @@@@@@@@@@@@@@@@@@@@@@@")
    for root, dirs, files in os.walk(g.bin_dir, topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))


class Window(QWidget):
    def __init__(self, hw_data=None) -> None:
        print("Window __init__ starting...")
        super().__init__()
        self._force_close = False
        self.is_audio_only = False
        self.label_log = None
        self.progress_bar = None
        print("Loading settings...")
        self.settings: dict = load_settings()
        
        # Use provided hardware data or fallback
        if hw_data:
            self.hw_info = hw_data.get("hw_info", {"cpu": "Unknown", "gpus": []})
            self.all_encoders = hw_data.get("encoders", ["libx264"])
        else:
            from src.thread import get_hardware_info, get_available_encoders
            self.hw_info = get_hardware_info()
            self.all_encoders = get_available_encoders()

        print("Setting window properties...")
        # We can still keep a minimum/fixed size if desired, but layouts will manage the inside.
        self.setMinimumSize(WINDOW.w, WINDOW.h)
        self.setWindowTitle(g.TITLE)
        icon_path = Path(g.res_dir) / "icon.ico"
        if icon_path.exists():
            print(f"Setting window icon: {icon_path}")
            self.setWindowIcon(QIcon(str(icon_path)))
        
        self.setAcceptDrops(True)
        print("Setting styles...")
        self.setStyleSheet(GLOBAL_STYLE)

        self.setup_ui()
        self.setup_tray_icon()

    def setup_tray_icon(self):
        """Setup the system tray icon and its context menu."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("System tray is not available on this system.")
            return

        icon_path = Path(g.res_dir) / "icon.ico"
        if not icon_path.exists():
            print(f"Tray icon not found at: {icon_path}")
            return

        print(f"Initializing tray icon with: {icon_path}")
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon(str(icon_path)))
        self.tray_icon.setToolTip(g.TITLE)

        # Create tray menu
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
        """Handle tray icon click activation."""
        if reason == QSystemTrayIcon.Trigger:  # Single click
            self.restore_window()

    def restore_window(self):
        """Restore window from tray."""
        self.show()
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def quit_application(self):
        """Force quit the application immediately."""
        self._force_close = True
        self.close()
        QApplication.quit() # Ensure the event loop stops

    def changeEvent(self, event):
        """Override changeEvent to detect minimization and hide to tray."""
        if event.type() == QEvent.WindowStateChange:
            if self.isMinimized():
                # On Windows, we hide the window so it doesn't stay in the taskbar
                self.hide()
                event.accept()
        super().changeEvent(event)

    def setup_ui(self):
        # Initialize log and progress first to avoid AttributeErrors if methods call them during setup
        self.label_log = QLabel(g.READY_TEXT)
        self.progress_bar = QProgressBar()

        # Main Layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(15, 15, 15, 15)
        self.main_layout.setSpacing(10)

        # Top Buttons (Select / Output)
        self.layout_top_buttons = QHBoxLayout()
        self.button_select = QPushButton("Select Videos")
        self.button_select.clicked.connect(self.select_videos)
        self.button_select.setEnabled(True)
        self.button_select.setFixedHeight(50)
        self.button_select.setStyleSheet(BUTTON_SELECT_STYLE)

        self.button_output = QPushButton("📂 Output Folder")
        self.button_output.clicked.connect(self.select_output_dir)
        self.button_output.setFixedHeight(50)
        self.button_output.setStyleSheet(BUTTON_SELECT_STYLE)

        self.layout_top_buttons.addWidget(self.button_select)
        self.layout_top_buttons.addWidget(self.button_output)
        self.main_layout.addLayout(self.layout_top_buttons)

        # Compress / Abort Buttons
        self.layout_action_buttons = QHBoxLayout()
        self.button_compress = QPushButton("Compress")
        self.button_compress.clicked.connect(self.compress_videos)
        self.button_compress.setEnabled(False)
        self.button_compress.setFixedHeight(50)
        self.button_compress.setStyleSheet(BUTTON_DISABLED_STYLE)

        self.button_abort = QPushButton("Abort")
        self.button_abort.clicked.connect(self.abort_compression)
        self.button_abort.setEnabled(False)
        self.button_abort.setFixedHeight(50)
        self.button_abort.setStyleSheet(BUTTON_DISABLED_STYLE)

        self.layout_action_buttons.addWidget(self.button_compress)
        self.layout_action_buttons.addWidget(self.button_abort)
        self.main_layout.addLayout(self.layout_action_buttons)

        # Settings Grid (Size, Device, Codec, Export, Audio)
        self.layout_settings = QVBoxLayout()
        
        def create_setting_row(label_text, widget):
            row = QHBoxLayout()
            label = QLabel(label_text)
            label.setFixedWidth(100)
            label.setStyleSheet(LABEL_STYLE)
            widget.setStyleSheet(COMBOBOX_STYLE if isinstance(widget, QComboBox) else LINEEDIT_STYLE)
            row.addWidget(label)
            row.addWidget(widget)
            return row

        # File Size
        self.edit_size = QLineEdit(str(self.settings.get("target_size", 20.0)))
        self.main_layout.addLayout(create_setting_row("Size (MB)", self.edit_size))

        # Custom Filename
        self.edit_filename = QLineEdit("")
        self.edit_filename.setPlaceholderText("Dejar vacio para usar nombre original")
        self.main_layout.addLayout(create_setting_row("Output Name", self.edit_filename))

        # Resolution
        self.combo_resolution = QComboBox()
        self.resolutions = [
            "Original",
            "4K (2160p)",
            "1440p (QHD)",
            "1080p (FHD)",
            "720p (HD)",
            "480p (SD)",
            "360p"
        ]
        self.combo_resolution.addItems(self.resolutions)
        self.main_layout.addLayout(create_setting_row("Resolution", self.combo_resolution))

        # Device
        self.combo_device = QComboBox()
        devices = ["CPU"]
        has_intel = any("Intel" in gpu for gpu in self.hw_info["gpus"])
        has_amd = any("AMD" in gpu or "Radeon" in gpu for gpu in self.hw_info["gpus"])
        has_nvidia = any("NVIDIA" in gpu for gpu in self.hw_info["gpus"])

        if has_intel: devices.append("iGPU (Intel)")
        if has_amd: devices.append("iGPU (AMD)")
        if has_nvidia or (has_amd and len(self.hw_info["gpus"]) > 1):
            devices.append("Dedicated GPU")
        
        devices = list(dict.fromkeys(devices))
        self.combo_device.addItems(devices)
        self.combo_device.currentIndexChanged.connect(self.update_codec_list)
        self.main_layout.addLayout(create_setting_row("Device", self.combo_device))

        # Export (must be initialized before Codec, because codec changes update export formats)
        self.combo_export = QComboBox()
        self.all_video_exports = ["Original", "mp4", "mkv", "avi", "mov", "webm", "flv", "m4v"]
        self.audio_exports = ["Original", "mp3", "flac", "wav", "m4a", "ogg", "wma"]
        self.audio_codecs = [
            "MP3 128kbps", "MP3 192kbps", "MP3 320kbps", 
            "AAC 128kbps", "AAC 192kbps", "AAC 256kbps", 
            "FLAC (Lossless)", "WAV (Uncompressed)", "Copy (Original)"
        ]
        
        # Codec → compatible container formats
        self.codec_format_map = {
            # NVENC
            "h264_nvenc": ["mp4", "mkv", "avi", "mov", "flv", "m4v"],
            "hevc_nvenc": ["mp4", "mkv", "mov", "m4v"],
            "av1_nvenc":  ["mp4", "mkv", "webm"],
            # AMF
            "h264_amf":   ["mp4", "mkv", "avi", "mov", "flv", "m4v"],
            "hevc_amf":   ["mp4", "mkv", "mov", "m4v"],
            "av1_amf":    ["mp4", "mkv", "webm"],
            # QSV
            "h264_qsv":   ["mp4", "mkv", "avi", "mov", "flv", "m4v"],
            "hevc_qsv":   ["mp4", "mkv", "mov", "m4v"],
            "av1_qsv":    ["mp4", "mkv", "webm"],
            # VAAPI
            "h264_vaapi":  ["mp4", "mkv", "avi", "mov", "flv", "m4v"],
            "hevc_vaapi":  ["mp4", "mkv", "mov", "m4v"],
            "av1_vaapi":   ["mp4", "mkv", "webm"],
            # Software
            "libx264":     ["mp4", "mkv", "avi", "mov", "flv", "m4v"],
            "libx265":     ["mp4", "mkv", "mov", "m4v"],
            "libsvtav1":   ["mp4", "mkv", "webm"],
            "libaom-av1":  ["mp4", "mkv", "webm"],
            "libvvenc":    ["mp4", "mkv"],
            # Lossless
            "ffv1":        ["mkv", "avi"],
        }

        # Codec (update_codec_list will also call update_export_formats)
        self.combo_codec = QComboBox()
        self.update_codec_list()
        self.combo_codec.currentIndexChanged.connect(self.update_export_formats)
        self.main_layout.addLayout(create_setting_row("Codec", self.combo_codec))

        # Export row (widget already created above)
        self.video_devices = devices
        self.main_layout.addLayout(create_setting_row("Export", self.combo_export))

        # Audio
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
        self.main_layout.addLayout(create_setting_row("Audio", self.combo_audio))

        # Restore saved preferences
        self.restore_settings()

        # Info Labels Group
        self.layout_info = QVBoxLayout()
        self.layout_info.setSpacing(5)

        self.label_path = QLabel("")
        self.label_path.setWordWrap(True)
        self.label_path.setStyleSheet(LABEL_STYLE)
        self.label_path.setAlignment(Qt.AlignCenter)
        self.label_path.setMinimumHeight(40)

        self.label_info_size = QLabel("")
        self.label_info_size.setStyleSheet(LABEL_STYLE)
        self.label_info_size.setAlignment(Qt.AlignCenter)

        self.label_quality = QLabel("")
        self.label_quality.setWordWrap(True)
        self.label_quality.setStyleSheet(LABEL_STYLE)
        self.label_quality.setAlignment(Qt.AlignCenter)
        self.label_quality.setMinimumHeight(60)

        self.layout_info.addWidget(self.label_path)
        self.layout_info.addWidget(self.label_info_size)
        self.layout_info.addWidget(self.label_quality)
        self.main_layout.addLayout(self.layout_info)

        # Spacer to push progress/log to bottom
        self.main_layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))

        # Error Label
        self.label_error = QLabel("")
        self.label_error.setStyleSheet(ERROR_LABEL_STYLE)
        self.label_error.setMinimumHeight(40)
        self.label_error.hide()
        self.main_layout.addWidget(self.label_error)

        # Log Area
        self.label_log.setWordWrap(True)
        self.label_log.setStyleSheet(LABEL_LOG_STYLE)
        self.label_log.setMinimumHeight(80)
        self.main_layout.addWidget(self.label_log)

        # Progress Bar
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setStyleSheet(PROGRESS_BAR_STYLE)
        self.progress_bar.setFixedHeight(25)
        self.main_layout.addWidget(self.progress_bar)

    def restore_settings(self):
        saved_device = self.settings.get("device", "CPU")
        dev_index = self.combo_device.findText(saved_device)
        if dev_index >= 0:
            self.combo_device.setCurrentIndex(dev_index)
            
        saved_codec = self.settings.get("codec", "libx264")
        codec_index = self.combo_codec.findText(saved_codec)
        if codec_index >= 0:
            self.combo_codec.setCurrentIndex(codec_index)

        saved_res = self.settings.get("resolution", "Original")
        res_index = self.combo_resolution.findText(saved_res)
        if res_index >= 0:
            self.combo_resolution.setCurrentIndex(res_index)

        saved_audio = self.settings.get("audio", "Copy (original)")
        audio_index = self.combo_audio.findText(saved_audio)
        if audio_index >= 0:
            self.combo_audio.setCurrentIndex(audio_index)

    def closeEvent(self, event):
        """Override closeEvent to minimize to tray instead of quitting."""
        if not self._force_close:
            # Save settings even when minimizing to tray (just in case)
            self.save_current_settings()
            
            self.hide()
            event.ignore()
            return
            
        # Actual cleanup when quitting
        self.save_current_settings()
        kill_ffmpeg()

        if os.path.exists(os.path.join(g.root_dir, "TEMP")):
            os.remove(os.path.join(g.root_dir, "TEMP"))

        event.accept()

    def save_current_settings(self):
        """Save settings to the config file."""
        try:
            self.settings["target_size"] = float(self.edit_size.text())
            self.settings["resolution"] = self.combo_resolution.currentText()
            self.settings["device"] = self.combo_device.currentText()
            self.settings["codec"] = self.combo_codec.currentText()
            self.settings["audio"] = self.combo_audio.currentText()
            save_settings(self.settings)
        except Exception as e:
            print(f"Error while saving settings: {e}")

    def reset(self, preserve_queue=False):
        g.compressing = False
        if not preserve_queue:
            g.queue = []
            
        self.button_select.setEnabled(True)
        self.button_select.setStyleSheet(BUTTON_SELECT_STYLE)
        self.button_select.setFocus()
        
        self.button_output.setEnabled(True)
        self.button_output.setStyleSheet(BUTTON_SELECT_STYLE)
        
        if g.queue:
            self.button_compress.setEnabled(True)
            self.button_compress.setStyleSheet(BUTTON_COMPRESS_STYLE)
        else:
            self.button_compress.setEnabled(False)
            self.button_compress.setStyleSheet(BUTTON_DISABLED_STYLE)
            
        self.button_abort.setEnabled(False)
        self.button_abort.setStyleSheet(BUTTON_DISABLED_STYLE)
        
        self.edit_size.setEnabled(True)
        self.combo_resolution.setEnabled(True)
        self.combo_codec.setEnabled(True)
        self.combo_device.setEnabled(True)
        self.combo_export.setEnabled(True)
        self.combo_audio.setEnabled(True)
        self.edit_filename.setEnabled(True)
        
        self.update_log(g.READY_TEXT)
        self.update_progress(0)



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

    def select_output_dir(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Output Folder", g.output_dir
        )
        if folder:
            g.output_dir = folder
            self.button_output.setText(f"📂 ...{os.sep}{os.path.basename(folder)}")
            self.button_output.setToolTip(folder)

    def select_videos(self):
        self.label_error.hide()
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Media Files",
            "",
            "Media Files (*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.m4v *.mp3 *.wav *.flac *.m4a *.aac *.wma *.ogg);;All Files (*.*)",
        )

        if len(file_paths) > 0:
            self.add_videos(file_paths)

    def check_audio_only(self):
        audio_extensions = ('.mp3', '.wav', '.flac', '.m4a', '.aac', '.wma', '.ogg')
        if not g.queue:
            return
            
        self.is_audio_only = all(f.lower().endswith(audio_extensions) for f in g.queue)
        
        # Block signals to prevent redundant logic execution
        self.combo_device.blockSignals(True)
        self.combo_export.blockSignals(True)
        
        self.combo_device.clear()
        self.combo_export.clear()
        
        if self.is_audio_only:
            self.combo_device.addItems(["CPU"])
            self.combo_export.addItems(self.audio_exports)
            self.combo_codec.clear()
            self.combo_codec.addItems(self.audio_codecs)
            # Disable irrelevant UI elements
            self.edit_size.setEnabled(False)
            self.combo_resolution.setEnabled(False)
            self.combo_audio.setEnabled(False)
        else:
            self.combo_device.addItems(self.video_devices)
            self.update_export_formats()
            # Re-enable elements
            self.edit_size.setEnabled(True)
            self.combo_resolution.setEnabled(True)
            self.combo_audio.setEnabled(True)
            self.update_codec_list()
            
        self.combo_device.blockSignals(False)
        self.combo_export.blockSignals(False)

    def add_videos(self, file_paths):
        for PATH in file_paths:
            if PATH in g.queue:
                continue

            g.queue.append(PATH)

            self.button_compress.setEnabled(True)
            self.button_compress.setStyleSheet(BUTTON_COMPRESS_STYLE)
            print(f"Selected: {g.queue}")
            msg = f"Selected {len(g.queue)} media file(s)."
            self.update_log(msg)

            self.check_audio_only()

            # Update Video Info for the last selected video
            last_video = g.queue[-1]
            metadata = get_video_metadata(last_video)
            file_size = os.path.getsize(last_video)
            
            # Update Export dropdown default
            _, ext = os.path.basename(last_video).rsplit(".", 1)
            self.combo_export.setItemText(0, f"Original (.{ext})")
            self.combo_export.setCurrentIndex(0)
            
            self.label_path.setText(f"Path: {last_video}")
            self.label_info_size.setText(f"Size: {human_readable_size(file_size)}")
            self.label_quality.setText(
                f"Video: {metadata.get('codec')} | {metadata.get('depth')} | {metadata.get('bitrate')}\n"
                f"Audio: {metadata.get('audio_codec')} | {metadata.get('audio_bitrate')}\n"
                f"Res: {metadata.get('resolution')}"
            )

    def compress_videos(self):
        g.compressing = True
        self.label_error.hide()
        self.last_error_occured = False
        self.button_select.setStyleSheet(BUTTON_DISABLED_STYLE)
        self.button_output.setStyleSheet(BUTTON_DISABLED_STYLE)
        self.button_compress.setStyleSheet(BUTTON_DISABLED_STYLE)
        self.button_abort.setEnabled(True)
        self.button_abort.setStyleSheet(BUTTON_ABORT_STYLE)
        self.button_select.setEnabled(False)
        self.button_output.setEnabled(False)
        self.button_compress.setEnabled(False)
        self.edit_size.setEnabled(False)
        self.combo_resolution.setEnabled(False)
        self.combo_codec.setEnabled(False)
        self.combo_device.setEnabled(False)
        self.combo_export.setEnabled(False)
        self.combo_audio.setEnabled(False)
        self.edit_filename.setEnabled(False)
        
        export_choice = self.combo_export.currentText()
        export_format = "Original" if "Original" in export_choice else export_choice
        
        # Get selected audio codec internal value
        audio_display = self.combo_audio.currentText()
        audio_codec = self.audio_options.get(audio_display, "copy")
        
        self.compress_thread = CompressionThread(
            float(self.edit_size.text()), 
            self.combo_codec.currentText(),
            export_format,
            audio_codec,
            self.is_audio_only,
            self.combo_resolution.currentText(),
            self.edit_filename.text().strip()
        )
        if self.compress_thread:
            self.compress_thread.completed.connect(self.completed)
            self.compress_thread.update_log.connect(self.update_log)
            self.compress_thread.update_progress.connect(self.update_progress)
            self.compress_thread.error_msg.connect(self.show_error)
            self.compress_thread.start()

    def show_error(self, message):
        self.label_error.setText(message)
        self.label_error.show()
        self.last_error_occured = True

    def abort_compression(self):
        kill_ffmpeg()
        self.completed(True)

    def update_codec_list(self):
        if self.is_audio_only:
            return
            
        device = self.combo_device.currentText()
        self.combo_codec.blockSignals(True)
        self.combo_codec.clear()
        
        match device:
            case "CPU":
                # Show only software encoders
                filtered = [e for e in self.all_encoders if not any(hw in e for hw in ["nvenc", "amf", "qsv"])]
            case d if "iGPU (Intel)" in d:
                # Show Intel QSV encoders and VAAPI (on Linux)
                filtered = [e for e in self.all_encoders if "qsv" in e or ("vaapi" in e and platform.system() == "Linux")]
            case d if "iGPU (AMD)" in d:
                # Show AMD AMF encoders and VAAPI (on Linux)
                filtered = [e for e in self.all_encoders if "amf" in e or ("vaapi" in e and platform.system() == "Linux")]
            case d if "Dedicated" in d:
                # Show NVENC, AMF or VAAPI (on Linux)
                filtered = [e for e in self.all_encoders if "nvenc" in e or "amf" in e or ("vaapi" in e and platform.system() == "Linux")]
            case _:
                filtered = ["libx264"]
            
        if not filtered:
            filtered = ["libx264"]
            
        self.combo_codec.addItems(filtered)
        self.combo_codec.blockSignals(False)
        
        # Update export formats for the new codec
        self.update_export_formats()

    def update_export_formats(self):
        """Update the export format dropdown based on the currently selected codec."""
        if hasattr(self, 'label_error'):
            self.label_error.hide()
        if self.is_audio_only:
            return
        
        codec_text = self.combo_codec.currentText()
        if not codec_text:
            return
        
        # Extract the pure codec name (remove suffixes like " (Standard 8-bit)")
        pure_codec = codec_text.split(" ")[0]
        
        # Look up compatible formats
        compatible = self.codec_format_map.get(pure_codec, None)
        
        if compatible is None:
            # Unknown codec, show all formats
            compatible = ["mp4", "mkv", "avi", "mov", "webm", "flv", "m4v"]
        
        # Save currently selected format to restore if still valid
        current_export = self.combo_export.currentText()
        
        self.combo_export.blockSignals(True)
        self.combo_export.clear()
        self.combo_export.addItem("Original")
        self.combo_export.addItems(compatible)
        self.combo_export.blockSignals(False)
        
        # Restore previous selection if it's still available
        restore_index = self.combo_export.findText(current_export)
        if restore_index >= 0:
            self.combo_export.setCurrentIndex(restore_index)

    def update_log(self, text):
        if self.label_log:
            self.label_log.setText(text)
        print(text)

    def update_progress(self, progress_percentage):
        if self.progress_bar:
            self.progress_bar.setValue(progress_percentage)


    def completed(self, aborted=False):
        g.compressing = False
        if self.compress_thread:
            self.compress_thread.terminate()
            
        was_error = getattr(self, 'last_error_occured', False)
        self.reset(preserve_queue=True) # Always preserve queue to allow re-compression
        
        n = Notify()
        if was_error:
            n.title = "Error!"
            n.message = "There was an error during compression."
        else:
            n.title = "Done!" if not aborted else "Aborted!"
            n.message = "Your videos are ready." if not aborted else "Your videos are cooked!"
            
        n.icon = os.path.join(g.res_dir, "icon.ico")
        n.send()

        if not aborted and not was_error:
            # os.startfile is Windows-only
            if hasattr(os, "startfile"):
                os.startfile(g.output_dir)
            elif platform.system() == "Linux":
                subprocess.Popen(["xdg-open", g.output_dir])


def start_main_window(hw_data):
    global window
    window = Window(hw_data)
    window.show()

if __name__ == "__main__":
    if platform.system() == "Windows":
        # Fix for taskbar icon: Set a unique AppUserModelID
        myappid = u"thedevil4k.draggyencoder.v1" 
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    # Initialize directories and paths FIRST
    g.verify_directories()
    
    icon_path = Path(g.res_dir) / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
        print(f"Application icon set from: {icon_path}")
    else:
        print(f"Warning: Icon file not found at {icon_path}")
    
    loader = LoadingWindow()
    loader.finished.connect(start_main_window)
    loader.show()
    
    sys.exit(app.exec())
