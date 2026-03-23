import json
import sys
import os
import platform
import subprocess
import psutil
import src.globals as g
from notifypy import Notify
from src.download import DownloadThread
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
)
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt
from src.styles import *

window = None


def load_settings():
    try:
        with open(os.path.join(g.res_dir, "settings.json"), "r") as f:
            return json.load(f)
    except:
        return g.DEFAULT_SETTINGS


def save_settings(settings):
    with open(os.path.join(g.res_dir, "settings.json"), "w") as f:
        json.dump(settings, f)


def kill_ffmpeg():
    for proc in psutil.process_iter():
        if "ffmpeg" in proc.name():
            proc.kill()


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
        self.is_audio_only = False
        print("Loading settings...")
        self.settings = load_settings()
        
        # Use provided hardware data or fallback
        if hw_data:
            self.hw_info = hw_data.get("hw_info", {"cpu": "Unknown", "gpus": []})
            self.all_encoders = hw_data.get("encoders", ["libx264"])
        else:
            from src.thread import get_hardware_info, get_available_encoders
            self.hw_info = get_hardware_info()
            self.all_encoders = get_available_encoders()

        print("Setting window properties...")
        self.setFixedSize(WINDOW.w, WINDOW.h)
        self.setWindowTitle(g.TITLE)
        icon_path = os.path.join(g.res_dir, "icon.ico")
        print(f"Setting window icon: {icon_path}")
        self.setWindowIcon(QIcon(icon_path))
        self.setAcceptDrops(True)
        print("Setting styles...")
        self.setStyleSheet(GLOBAL_STYLE)

        # Select Button
        self.button_select = QPushButton("Select Videos", self)
        self.button_select.resize(SELECT_BUTTON.w, SELECT_BUTTON.h)
        self.button_select.move(SELECT_BUTTON.x, SELECT_BUTTON.y)
        self.button_select.clicked.connect(self.select_videos)
        self.button_select.setEnabled(False)

        # Output Button
        self.button_output = QPushButton("📂 Output Folder", self)
        self.button_output.resize(OUTPUT_BUTTON.w, OUTPUT_BUTTON.h)
        self.button_output.move(OUTPUT_BUTTON.x, OUTPUT_BUTTON.y)
        self.button_output.clicked.connect(self.select_output_dir)

        # Compress Button
        self.button_compress = QPushButton("Compress", self)
        self.button_compress.resize(COMPRESS_BUTTON.w, COMPRESS_BUTTON.h)
        self.button_compress.move(COMPRESS_BUTTON.x, COMPRESS_BUTTON.y)
        self.button_compress.clicked.connect(self.compress_videos)
        self.button_compress.setEnabled(False)

        # Abort Button
        self.button_abort = QPushButton("Abort", self)
        self.button_abort.resize(ABORT_BUTTON.w, ABORT_BUTTON.h)
        self.button_abort.move(ABORT_BUTTON.x, ABORT_BUTTON.y)
        self.button_abort.clicked.connect(self.abort_compression)
        self.button_abort.setEnabled(False)

        # File Size Label
        self.label_size = QLabel("Size (MB)", self)
        self.label_size.resize(FILE_SIZE_LABEL.w, FILE_SIZE_LABEL.h)
        self.label_size.move(FILE_SIZE_LABEL.x, FILE_SIZE_LABEL.y)

        # File Size Entry
        self.edit_size = QLineEdit(str(self.settings["target_size"]), self)
        self.edit_size.resize(FILE_SIZE_ENTRY.w, FILE_SIZE_ENTRY.h)
        self.edit_size.move(FILE_SIZE_ENTRY.x, FILE_SIZE_ENTRY.y)
        self.edit_size.setEnabled(True)

        # Device Label
        self.label_device = QLabel("Device", self)
        self.label_device.resize(DEVICE_LABEL.w, DEVICE_LABEL.h)
        self.label_device.move(DEVICE_LABEL.x, DEVICE_LABEL.y)

        # Device Dropdown
        self.combo_device = QComboBox(self)
        self.combo_device.resize(DEVICE_COMBOBOX.w, DEVICE_COMBOBOX.h)
        self.combo_device.move(DEVICE_COMBOBOX.x, DEVICE_COMBOBOX.y)
        
        # Determine available devices
        devices = ["CPU"]
        
        has_intel = any("Intel" in gpu for gpu in self.hw_info["gpus"])
        has_amd = any("AMD" in gpu or "Radeon" in gpu for gpu in self.hw_info["gpus"])
        has_nvidia = any("NVIDIA" in gpu for gpu in self.hw_info["gpus"])

        if has_intel:
            devices.append("iGPU (Intel)")
        if has_amd:
            devices.append("iGPU (AMD)")
        if has_nvidia or (has_amd and len(self.hw_info["gpus"]) > 1):
            devices.append("Dedicated GPU")
        
        # Ensure unique devices in case of duplicate detection
        devices = list(dict.fromkeys(devices))
        self.combo_device.addItems(devices)
        self.combo_device.currentIndexChanged.connect(self.update_codec_list)

        # Codec Label
        self.label_codec = QLabel("Codec", self)
        self.label_codec.resize(CODEC_LABEL.w, CODEC_LABEL.h)
        self.label_codec.move(CODEC_LABEL.x, CODEC_LABEL.y)

        # Codec Dropdown
        self.combo_codec = QComboBox(self)
        self.combo_codec.resize(CODEC_COMBOBOX.w, CODEC_COMBOBOX.h)
        self.combo_codec.move(CODEC_COMBOBOX.x, CODEC_COMBOBOX.y)
        
        # Store all verified encoders and update list
        self.update_codec_list()
        
        # Select saved codec/device if available
        saved_device = self.settings.get("device", "CPU")
        dev_index = self.combo_device.findText(saved_device)
        if dev_index >= 0:
            self.combo_device.setCurrentIndex(dev_index)
            
        saved_codec = self.settings.get("codec", "libx264")
        codec_index = self.combo_codec.findText(saved_codec)
        if codec_index >= 0:
            self.combo_codec.setCurrentIndex(codec_index)

        # Export Label
        self.label_export = QLabel("Export", self)
        self.label_export.resize(EXPORT_LABEL.w, EXPORT_LABEL.h)
        self.label_export.move(EXPORT_LABEL.x, EXPORT_LABEL.y)

        # Export Dropdown
        self.combo_export = QComboBox(self)
        self.combo_export.resize(EXPORT_COMBOBOX.w, EXPORT_COMBOBOX.h)
        self.combo_export.move(EXPORT_COMBOBOX.x, EXPORT_COMBOBOX.y)
        
        self.video_exports = ["Original", "mp4", "mkv", "avi", "mov", "webm", "flv", "m4v"]
        self.audio_exports = ["Original", "mp3", "flac", "wav", "m4a", "ogg", "wma"]
        self.audio_codecs = [
            "MP3 128kbps", "MP3 192kbps", "MP3 320kbps", 
            "AAC 128kbps", "AAC 192kbps", "AAC 256kbps", 
            "FLAC (Lossless)", "WAV (Uncompressed)", "Copy (Original)"
        ]
        self.combo_export.addItems(self.video_exports)
        self.video_devices = devices

        # Audio Label
        self.label_audio = QLabel("Audio", self)
        self.label_audio.resize(AUDIO_LABEL.w, AUDIO_LABEL.h)
        self.label_audio.move(AUDIO_LABEL.x, AUDIO_LABEL.y)

        # Audio Dropdown
        self.combo_audio = QComboBox(self)
        self.combo_audio.resize(AUDIO_COMBOBOX.w, AUDIO_COMBOBOX.h)
        self.combo_audio.move(AUDIO_COMBOBOX.x, AUDIO_COMBOBOX.y)
        audio_options = {
            "Copy (original)": "copy",
            "AAC (192k)": "aac",
            "MP3 - LAME (192k)": "mp3",
            "Opus (128k)": "opus",
            "FLAC (lossless)": "flac",
            "No Audio": "none",
        }
        self.audio_options = audio_options
        self.combo_audio.addItems(audio_options.keys())
        
        # Restore saved audio preference
        saved_audio = self.settings.get("audio", "Copy (original)")
        audio_index = self.combo_audio.findText(saved_audio)
        if audio_index >= 0:
            self.combo_audio.setCurrentIndex(audio_index)

        # Log Label
        self.label_log = QLabel(g.READY_TEXT, self)
        self.label_log.setEnabled(True)
        self.label_log.resize(LOG_AREA.w, LOG_AREA.h)
        self.label_log.move(LOG_AREA.x, LOG_AREA.y)
        self.label_log.setWordWrap(True)

        # Info Labels
        self.label_path = QLabel("", self)
        self.label_path.resize(INFO_PATH_LABEL.w, INFO_PATH_LABEL.h)
        self.label_path.move(INFO_PATH_LABEL.x, INFO_PATH_LABEL.y)
        self.label_path.setWordWrap(True)
        self.label_path.setStyleSheet(LABEL_STYLE)
        self.label_path.setAlignment(Qt.AlignCenter)

        self.label_info_size = QLabel("", self)
        self.label_info_size.resize(INFO_SIZE_LABEL.w, INFO_SIZE_LABEL.h)
        self.label_info_size.move(INFO_SIZE_LABEL.x, INFO_SIZE_LABEL.y)
        self.label_info_size.setStyleSheet(LABEL_STYLE)
        self.label_info_size.setAlignment(Qt.AlignCenter)

        self.label_quality = QLabel("", self)
        self.label_quality.resize(INFO_QUALITY_LABEL.w, INFO_QUALITY_LABEL.h)
        self.label_quality.move(INFO_QUALITY_LABEL.x, INFO_QUALITY_LABEL.y)
        self.label_quality.setWordWrap(True)
        self.label_quality.setStyleSheet(LABEL_STYLE)
        self.label_quality.setAlignment(Qt.AlignCenter)

        # Error Label (Modern Red Message)
        self.label_error = QLabel("", self)
        self.label_error.resize(ERROR_LABEL.w, ERROR_LABEL.h)
        self.label_error.move(ERROR_LABEL.x, ERROR_LABEL.y)
        self.label_error.setStyleSheet(ERROR_LABEL_STYLE)
        self.label_error.hide()

        # Progress Bar
        self.progress_bar = QProgressBar(self)
        self.progress_bar.resize(PROGRESS_BAR.w, PROGRESS_BAR.h)
        self.progress_bar.move(PROGRESS_BAR.x, PROGRESS_BAR.y)
        self.progress_bar.setRange(0, 100)

        self.download_thread = None
        self.compress_thread = None

        self.button_select.setStyleSheet(BUTTON_DISABLED_STYLE)
        self.button_compress.setStyleSheet(BUTTON_DISABLED_STYLE)
        self.button_abort.setStyleSheet(BUTTON_DISABLED_STYLE)
        self.button_output.setStyleSheet(BUTTON_SELECT_STYLE)
        self.label_size.setStyleSheet(LABEL_STYLE)
        self.edit_size.setStyleSheet(LINEEDIT_STYLE)
        self.label_device.setStyleSheet(LABEL_STYLE)
        self.combo_device.setStyleSheet(COMBOBOX_STYLE)
        self.label_codec.setStyleSheet(LABEL_STYLE)
        self.combo_codec.setStyleSheet(COMBOBOX_STYLE)
        self.label_export.setStyleSheet(LABEL_STYLE)
        self.combo_export.setStyleSheet(COMBOBOX_STYLE)
        self.label_audio.setStyleSheet(LABEL_STYLE)
        self.combo_audio.setStyleSheet(COMBOBOX_STYLE)
        self.label_log.setStyleSheet(LABEL_LOG_STYLE)
        self.progress_bar.setStyleSheet(PROGRESS_BAR_STYLE)

        self.verify_ffmpeg()

    def closeEvent(self, event):
        # Save settings when closing
        self.settings["target_size"] = float(self.edit_size.text())
        self.settings["device"] = self.combo_device.currentText()
        self.settings["codec"] = self.combo_codec.currentText()
        self.settings["audio"] = self.combo_audio.currentText()
        save_settings(self.settings)
        kill_ffmpeg()

        if os.path.exists(os.path.join(g.root_dir, "TEMP")):
            os.remove(os.path.join(g.root_dir, "TEMP"))

        event.accept()

    def reset(self):
        g.compressing = False
        g.queue = []
        self.button_select.setEnabled(True)
        self.button_select.setStyleSheet(BUTTON_SELECT_STYLE)
        self.button_select.setFocus()
        
        self.button_output.setEnabled(True)
        self.button_output.setStyleSheet(BUTTON_SELECT_STYLE)
        
        self.button_compress.setEnabled(False)
        self.button_compress.setStyleSheet(BUTTON_DISABLED_STYLE)
        self.button_abort.setEnabled(False)
        self.button_abort.setStyleSheet(BUTTON_DISABLED_STYLE)
        self.edit_size.setEnabled(True)
        self.combo_codec.setEnabled(True)
        self.update_log(g.READY_TEXT)
        self.update_progress(0)


    def verify_ffmpeg(self):
        if os.path.exists(g.ffmpeg_path) and os.path.exists(g.ffprobe_path):
            g.ffmpeg_installed = True
            self.reset()
        else:
            self.download_thread = DownloadThread()
            self.download_thread.installed.connect(self.installed)
            self.download_thread.update_log.connect(self.update_log)
            self.download_thread.update_progress.connect(self.update_progress)
            self.download_thread.start()

        # Show detected system and hardware
        os_info = f"{platform.system()} {platform.release()}"
        hw = self.hw_info
        gpus_str = "\n".join([f"- {gpu}" for gpu in hw["gpus"]])
        msg = f"System: {os_info}\nCPU: {hw['cpu']}\nGPUs Detected:\n{gpus_str}\n\n{g.READY_TEXT}"
        self.update_log(msg)

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
            self.combo_audio.setEnabled(False)
        else:
            self.combo_device.addItems(self.video_devices)
            self.combo_export.addItems(self.video_exports)
            # Re-enable elements
            self.edit_size.setEnabled(True)
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
        self.button_select.setStyleSheet(BUTTON_DISABLED_STYLE)
        self.button_output.setStyleSheet(BUTTON_DISABLED_STYLE)
        self.button_compress.setStyleSheet(BUTTON_DISABLED_STYLE)
        self.button_abort.setEnabled(True)
        self.button_abort.setStyleSheet(BUTTON_ABORT_STYLE)
        self.button_select.setEnabled(False)
        self.button_output.setEnabled(False)
        self.button_compress.setEnabled(False)
        self.edit_size.setEnabled(False)
        self.combo_codec.setEnabled(False)
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
            self.is_audio_only
        )
        self.compress_thread.completed.connect(self.completed)
        self.compress_thread.update_log.connect(self.update_log)
        self.compress_thread.update_progress.connect(self.update_progress)
        self.compress_thread.error_msg.connect(self.show_error)
        self.compress_thread.start()

    def show_error(self, message):
        self.label_error.setText(message)
        self.label_error.show()

    def abort_compression(self):
        kill_ffmpeg()
        self.completed(True)

    def update_codec_list(self):
        if self.is_audio_only:
            return
            
        device = self.combo_device.currentText()
        self.combo_codec.clear()
        
        filtered = []
        if device == "CPU":
            # Show only software encoders
            filtered = [e for e in self.all_encoders if not any(hw in e for hw in ["nvenc", "amf", "qsv"])]
        elif "iGPU (Intel)" in device:
            # Show Intel QSV encoders and VAAPI (on Linux)
            filtered = [e for e in self.all_encoders if "qsv" in e or ("vaapi" in e and platform.system() == "Linux")]
        elif "iGPU (AMD)" in device:
            # Show AMD AMF encoders and VAAPI (on Linux)
            filtered = [e for e in self.all_encoders if "amf" in e or ("vaapi" in e and platform.system() == "Linux")]
        elif "Dedicated" in device:
            # Show NVENC, AMF or VAAPI (on Linux)
            filtered = [e for e in self.all_encoders if "nvenc" in e or "amf" in e or ("vaapi" in e and platform.system() == "Linux")]
            
        if not filtered:
            # Fallback to libx264 if no compatible encoder found
            filtered = ["libx264"]
            
        self.combo_codec.addItems(filtered)

    def update_log(self, text):
        self.label_log.setText(text)

    def update_progress(self, progress_percentage):
        self.progress_bar.setValue(progress_percentage)

    def installed(self):
        g.ffmpeg_installed = True
        if platform.system() == "Windows":
            g.ffmpeg_path = os.path.join(g.bin_dir, "ffmpeg.exe")
            g.ffprobe_path = os.path.join(g.bin_dir, "ffprobe.exe")
        else:
            g.ffmpeg_path = os.path.join(g.bin_dir, "ffmpeg")
            g.ffprobe_path = os.path.join(g.bin_dir, "ffprobe")
        self.reset()
        n = Notify()
        n.title = "FFmpeg installed!"
        n.message = "You can now compress your videos."
        n.icon = os.path.join(g.res_dir, "icon.ico")
        n.send()

    def completed(self, aborted=False):
        g.compressing = False
        self.compress_thread.terminate()
        self.reset()
        n = Notify()
        n.title = "Done!" if not aborted else "Aborted!"
        n.message = (
            "Your videos are ready." if not aborted else "Your videos are cooked!"
        )
        n.icon = os.path.join(g.res_dir, "icon.ico")
        n.send()

        if not aborted:
            # os.startfile is Windows-only
            if platform.system() == "Windows":
                os.startfile(g.output_dir)
            else:
                subprocess.Popen(["xdg-open", g.output_dir])


def start_main_window(hw_data):
    global window
    window = Window(hw_data)
    window.show()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Initialize directories and paths FIRST
    g.verify_directories()
    
    loader = LoadingWindow()
    loader.finished.connect(start_main_window)
    loader.show()
    
    sys.exit(app.exec())
