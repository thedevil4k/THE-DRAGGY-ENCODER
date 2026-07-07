import os
import sys
import platform
import subprocess
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QFrame, QScrollArea
)
from PySide6.QtCore import Qt, QThread, Signal, QPropertyAnimation, QEasingCurve
from src.styles import GLOBAL_STYLE, PROGRESS_BAR_STYLE
from PySide6.QtGui import QIcon
from pathlib import Path
import src.globals as g

class Tag(QFrame):
    def __init__(self, text, color="#89B4FA", parent=None):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(8, 4, 8, 4)
        
        self.label = QLabel(text)
        self.label.setStyleSheet(f"color: {color}; font-weight: bold; border: none; background: transparent;")
        self.layout.addWidget(self.label)
        
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {color}22;
                border: 1px solid {color};
                border-radius: 12px;
            }}
        """)

class LoadingThread(QThread):
    progress = Signal(int)
    status = Signal(str)
    tag_added = Signal(str, str) # text, color
    finished_data = Signal(dict)

    def run(self):
        from src.thread import is_encoder_supported
        from src.download import (
            download_ffmpeg_func, install_ffmpeg_func,
            download_realesrgan_func, install_realesrgan_func,
            download_rife_func, install_rife_func,
            download_deoldify_model,
        )
        
        # 0. Check for FFmpeg installation
        if not os.path.exists(g.ffmpeg_path) or not os.path.exists(g.ffprobe_path):
            self.status.emit("FFmpeg not found. Downloading...")
            self.tag_added.emit("FFmpeg: Downloading...", "#FAB387")
            
            # Use standalone functions with signals as callbacks
            if download_ffmpeg_func(self.progress.emit, self.status.emit):
                if install_ffmpeg_func(self.status.emit):
                    self.tag_added.emit("FFmpeg: Installed", "#A6E3A1")
                    g.ffmpeg_installed = True
                    # Re-verify paths just in case
                    if platform.system() == "Windows":
                        g.ffmpeg_path = os.path.join(g.bin_dir, "ffmpeg.exe")
                        g.ffprobe_path = os.path.join(g.bin_dir, "ffprobe.exe")
                    else:
                        g.ffmpeg_path = os.path.join(g.bin_dir, "ffmpeg")
                        g.ffprobe_path = os.path.join(g.bin_dir, "ffprobe")
                else:
                    self.tag_added.emit("FFmpeg: Install Failed", "#F38BA8")
            else:
                self.tag_added.emit("FFmpeg: Download Failed", "#F38BA8")

        # 0b. Download AI tools if missing
        if not os.path.exists(g.realesrgan_path):
            self.status.emit("Downloading Real-ESRGAN...")
            self.tag_added.emit("Real-ESRGAN: Downloading...", "#FAB387")
            if download_realesrgan_func(self.progress.emit, self.status.emit):
                if install_realesrgan_func(self.status.emit):
                    self.tag_added.emit("Real-ESRGAN: Installed", "#A6E3A1")
                else:
                    self.tag_added.emit("Real-ESRGAN: Install Failed", "#F38BA8")
            else:
                self.tag_added.emit("Real-ESRGAN: Download Failed", "#F38BA8")

        if not os.path.exists(g.rife_path):
            self.status.emit("Downloading RIFE...")
            self.tag_added.emit("RIFE: Downloading...", "#FAB387")
            if download_rife_func(self.progress.emit, self.status.emit):
                if install_rife_func(self.status.emit):
                    self.tag_added.emit("RIFE: Installed", "#A6E3A1")
                else:
                    self.tag_added.emit("RIFE: Install Failed", "#F38BA8")
            else:
                self.tag_added.emit("RIFE: Download Failed", "#F38BA8")

        # 0c. Download DeOldify models if missing
        from src.ai_tools import get_deoldify_model_path, COLORIZE_MODELS
        for model_key in COLORIZE_MODELS:
            if not get_deoldify_model_path(model_key):
                model_name = COLORIZE_MODELS[model_key]["name"]
                self.status.emit(f"Downloading {model_name}...")
                self.tag_added.emit(f"{model_name}: Downloading...", "#FAB387")
                if download_deoldify_model(self.progress.emit, self.status.emit, model_key=model_key):
                    self.tag_added.emit(f"{model_name}: Ready", "#A6E3A1")
                else:
                    self.tag_added.emit(f"{model_name}: Download Failed", "#F38BA8")

        # Explicit initialization to help linter
        hw_info_data = {"cpu": "Unknown", "gpus": []}
        detected_encoders = []
        
        results = {
            "hw_info": hw_info_data,
            "encoders": detected_encoders
        }
        
        # 1. Detect Hardware info (CPU/GPU)
        self.status.emit("Detecting hardware...")
        self.progress.emit(10)
        
        try:
            if platform.system() == "Windows":
                creation_flags = 0x08000000
                cpu_cmd = ["powershell", "-Command", "Get-CimInstance Win32_Processor | Select-Object -ExpandProperty Name"]
                cpu_output = subprocess.check_output(cpu_cmd, universal_newlines=True, creationflags=creation_flags).strip()
                hw_info_data["cpu"] = cpu_output
                cpu_tag = str(cpu_output)[:25]
                self.tag_added.emit(f"CPU: {cpu_tag}", "#A6E3A1")
                
                gpu_cmd = ["powershell", "-Command", "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"]
                gpu_output = subprocess.check_output(gpu_cmd, universal_newlines=True, creationflags=creation_flags).strip()
                if gpu_output:
                    gpus = [line.strip() for line in gpu_output.splitlines() if line.strip()]
                    hw_info_data["gpus"] = gpus
                    for gpu in gpus:
                        gpu_tag = str(gpu)[:25]
                        self.tag_added.emit(f"GPU: {gpu_tag}", "#FAB387")
            else:
                hw_info_data["cpu"] = "Linux CPU"
                self.tag_added.emit("CPU: Linux Detected", "#A6E3A1")
        except Exception as e:
            print(f"HW Detection Error: {e}")
            
        self.progress.emit(25)
        
        # 2. Get encoders from binary
        all_video_encoders = []
        if not os.path.exists(g.ffmpeg_path):
            self.status.emit("FFmpeg still missing. skipping tests...")
            self.tag_added.emit("FFmpeg: MISSING", "#F38BA8")
            self.progress.emit(35)
        else:
            self.status.emit("Reading FFmpeg capabilities...")
            try:
                cmd = [g.ffmpeg_path, "-hide_banner", "-encoders"]
                if platform.system() == "Windows":
                    output = subprocess.check_output(cmd, universal_newlines=True, creationflags=0x08000000)
                else:
                    output = subprocess.check_output(cmd, universal_newlines=True)
                
                start_parsing = False
                for line in output.splitlines():
                    if "-----" in line:
                        start_parsing = True
                        continue
                    if not start_parsing:
                        continue
                    if line.startswith(" V"):
                        parts = line.split()
                        if len(parts) >= 2:
                            all_video_encoders.append(parts[1])
            except Exception as e:
                print(f"FFmpeg binary error: {e}")
                
            self.progress.emit(35)
        
        # 3. Detect Encoders
        self.status.emit("Testing codec compatibility...")
        if all_video_encoders:
            self.tag_added.emit(f"FFmpeg: {len(all_video_encoders)} encoders available", "#CDD6F4")
        
        hardware_priority = [
            "h264_nvenc", "hevc_nvenc", "av1_nvenc",
            "h264_amf", "hevc_amf", "av1_amf",
            "h264_qsv", "hevc_qsv", "av1_qsv",
            "h264_vaapi", "hevc_vaapi", "av1_vaapi",
            "libx264", "libx265", "libsvtav1", "libaom-av1", "libvvenc", "ffv1"
        ]
        
        total = len(hardware_priority)
        for i, name in enumerate(hardware_priority):
            self.status.emit(f"Testing {name}...")
            
            # Only test if the binary actually has it
            if name in all_video_encoders:
                # For hardware encoders, run quality-based capability test
                if any(hw in name for hw in ["nvenc", "amf", "qsv", "vaapi"]):
                    if is_encoder_supported(name):
                        if is_encoder_supported(name, "p010le"):
                            detected_encoders.append(f"{name} (Modern 10-bit)")
                            self.tag_added.emit(f"Codec: {name} (10-bit)", "#CBA6F7")
                        detected_encoders.append(f"{name} (Standard 8-bit)")
                        self.tag_added.emit(f"Codec: {name} (8-bit)", "#89B4FA")
                    else:
                        self.tag_added.emit(f"Codec: {name} (failed test)", "#F38BA8")
                else:
                    # Software encoders are usually safe if present in binary
                    detected_encoders.append(name)
                    self.tag_added.emit(f"Codec: {name}", "#89B4FA")
            
            prog = 35 + int((i / total) * 55)
            self.progress.emit(prog)
            
        if not detected_encoders:
            detected_encoders.append("libx264")
            
        self.status.emit("Initialization complete!")
        self.progress.emit(100)
        self.msleep(300)

        # Detect AI tools
        from src.ai_tools import get_gpu_vram_mb, get_gpu_name, check_onnx_available, get_deoldify_model_path
        gpu_name = get_gpu_name()
        gpu_vram = get_gpu_vram_mb()

        if os.path.exists(g.realesrgan_path) and os.path.exists(g.rife_path):
            self.tag_added.emit("AI Tools: Real-ESRGAN + RIFE", "#A6E3A1")
        elif os.path.exists(g.realesrgan_path):
            self.tag_added.emit("AI Tools: Real-ESRGAN only", "#FAB387")
        elif os.path.exists(g.rife_path):
            self.tag_added.emit("AI Tools: RIFE only", "#FAB387")
        else:
            self.tag_added.emit("AI Tools: Not installed", "#F38BA8")

        # ONNX Runtime status
        onnx_ok, has_cuda, _ = check_onnx_available()
        if onnx_ok:
            backend = "CUDA" if has_cuda else "CPU"
            self.tag_added.emit(f"ONNX Runtime: {backend}", "#A6E3A1" if has_cuda else "#FAB387")
        else:
            self.tag_added.emit("ONNX Runtime: Not installed", "#F38BA8")

        # DeOldify model status
        from src.ai_tools import COLORIZE_MODELS as _CM
        for mk in _CM:
            if get_deoldify_model_path(mk):
                self.tag_added.emit(f"{_CM[mk]['name']}: Ready", "#A6E3A1")
            else:
                self.tag_added.emit(f"{_CM[mk]['name']}: Not found", "#F38BA8")

        if gpu_vram > 0:
            self.tag_added.emit(f"GPU VRAM: {gpu_vram} MB ({gpu_name[:30]})", "#A6E3A1")
        else:
            self.tag_added.emit(f"GPU: {gpu_name[:30]} (VRAM unknown)", "#FAB387")

        self.finished_data.emit(results)

class LoadingWindow(QWidget):
    finished = Signal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedSize(350, 450)
        self.setStyleSheet(GLOBAL_STYLE)
        
        # Icon
        icon_path = Path(g.res_dir) / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)
        
        # Title
        self.title = QLabel("THE DRAGGY ENCODER")
        self.title.setStyleSheet("font-size: 18px; font-weight: bold; color: #89B4FA;")
        self.title.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.title)
        
        self.subtitle = QLabel("Initializing engine...")
        self.subtitle.setStyleSheet("color: #A6ADC8; font-size: 12px;")
        self.subtitle.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.subtitle)
        
        # Tags Area (Scrollable or just a container)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("background: transparent;")
        
        self.tag_container = QWidget()
        self.tag_container.setStyleSheet("background: transparent;")
        self.tag_layout = QVBoxLayout(self.tag_container)
        self.tag_layout.setAlignment(Qt.AlignTop)
        self.tag_layout.setSpacing(8)
        self.scroll.setWidget(self.tag_container)
        self.layout.addWidget(self.scroll)
        
        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(PROGRESS_BAR_STYLE)
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Starting up...")
        self.status_label.setStyleSheet("color: #6C7086; font-size: 11px;")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.status_label)
        
        # Thread
        self.thread = LoadingThread()
        self.thread.progress.connect(self.progress_bar.setValue)
        self.thread.status.connect(self.status_label.setText)
        self.thread.tag_added.connect(self.add_tag)
        self.thread.finished_data.connect(self.on_finished)
        
    def showEvent(self, event):
        super().showEvent(event)
        self.thread.start()
        
    def add_tag(self, text, color):
        tag = Tag(text, color)
        self.tag_layout.insertWidget(0, tag) # New tags at the top
        
    def on_finished(self, data):
        self.finished.emit(data)
        self.close()

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    w = LoadingWindow()
    w.show()
    sys.exit(app.exec())
