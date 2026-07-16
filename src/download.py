import os
import platform
import requests
import shutil
import src.globals as g
import zipfile
import tarfile
from PySide6.QtCore import QThread, Signal

# BtbN/FFmpeg-Builds latest requires NVENC API 13.1 (driver 610+).
# Many users have driver 581.57 which exposes NVENC API 13.0; using the
# August 2024 autobuild keeps NVENC SDK 12.x compatibility while still
# exposing h264_nvenc / hevc_nvenc 8-bit on those drivers.
FFMPEG_DL_WINDOWS = "https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2024-08-31-12-50/ffmpeg-N-116806-g4c0372281b-win64-gpl.zip"
FFMPEG_DL_LINUX = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz"

REALESRGAN_DL_WINDOWS = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip"
REALESRGAN_DL_LINUX = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-ubuntu.zip"

RIFE_DL_WINDOWS = "https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/rife-ncnn-vulkan-20221029-windows.zip"
RIFE_DL_LINUX = "https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/rife-ncnn-vulkan-20221029-linux.zip"


def _download_file(url, dest_path, progress_callback=None, log_callback=None, label="Downloading"):
    """Generic file downloader with progress reporting."""
    if log_callback:
        log_callback(f"{label}...")
    print(f"{label}: {url}")

    try:
        response = requests.get(url, stream=True, timeout=(15, None))
        response.raise_for_status()
        total_size = response.headers.get("content-length")

        with open(dest_path, "wb") as f:
            if total_size is None:
                f.write(response.content)
                if log_callback:
                    log_callback(f"{label} complete")
                return True

            total_size = int(total_size)
            downloaded = 0
            for chunk in response.iter_content(chunk_size=4096):
                if not chunk:
                    continue
                downloaded += len(chunk)
                f.write(chunk)
                percentage = (downloaded / total_size) * 100
                downloaded_mb = downloaded / (1024 * 1024)
                total_mb = total_size / (1024 * 1024)
                message = f"{label}...\n{downloaded_mb:.1f} MB / {total_mb:.1f} MB"
                if log_callback:
                    log_callback(message)
                if progress_callback:
                    progress_callback(int(percentage))
        return True
    except Exception as e:
        error_msg = f"{label} error: {e}"
        if log_callback:
            log_callback(error_msg)
        print(error_msg)
        return False


def download_ffmpeg_func(progress_callback=None, log_callback=None):
    """
    Standalone function to download FFmpeg.
    :param progress_callback: Function taking an int (0-100)
    :param log_callback: Function taking a str message
    """
    is_linux = platform.system() == "Linux"
    url = FFMPEG_DL_LINUX if is_linux else FFMPEG_DL_WINDOWS
    ext = ".tar.xz" if is_linux else ".zip"
    file_path = os.path.join(g.bin_dir, f"ffmpeg{ext}")

    return _download_file(url, file_path, progress_callback, log_callback, label="Downloading FFmpeg")


def install_ffmpeg_func(log_callback=None):
    """
    Standalone function to extract and install FFmpeg.
    :param log_callback: Function taking a str message
    """
    if log_callback: log_callback("Installing FFmpeg...")
    print("Installing FFmpeg...")
    
    is_linux = platform.system() == "Linux"
    ext = ".tar.xz" if is_linux else ".zip"
    archive_path = os.path.join(g.bin_dir, f"ffmpeg{ext}")
    
    if not os.path.exists(archive_path):
        if log_callback: log_callback("Archive not found!")
        return False

    try:
        if is_linux:
            with tarfile.open(archive_path, "r:xz") as tar:
                tar.extractall(g.bin_dir)
        else:
            with zipfile.ZipFile(archive_path, "r") as zip_file:
                zip_file.extractall(g.bin_dir)
        
        os.remove(archive_path)

        # Get extracted paths (usually the first directory in bin_dir after extraction)
        dir_list = [d for d in os.listdir(g.bin_dir) if os.path.isdir(os.path.join(g.bin_dir, d))]
        if not dir_list:
            return False
            
        extracted_root = os.path.join(g.bin_dir, dir_list[0])
        extracted_bin = os.path.join(extracted_root, "bin")

        # Move binaries to target directory
        if os.path.exists(extracted_bin):
            for file_name in os.listdir(extracted_bin):
                src = os.path.join(extracted_bin, file_name)
                dst = os.path.join(g.bin_dir, file_name)
                try:
                    if os.path.exists(dst):
                        os.remove(dst)
                    shutil.move(src, dst)
                except Exception as e:
                    print(f"Error moving {file_name}: {e}")

        # Cleanup extracted folder
        shutil.rmtree(extracted_root)

        # Remove ffplay (not needed)
        for name in ["ffplay", "ffplay.exe"]:
            path = os.path.join(g.bin_dir, name)
            if os.path.exists(path):
                os.remove(path)

        # Make executables on Linux
        if is_linux:
            for name in ["ffmpeg", "ffprobe"]:
                path = os.path.join(g.bin_dir, name)
                if os.path.exists(path):
                    os.chmod(path, 0o755)
        
        # Verify installation
        ffmpeg_exe = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
        if os.path.exists(os.path.join(g.bin_dir, ffmpeg_exe)):
            if log_callback: log_callback("FFmpeg installed successfully!")
            return True
        return False
    except Exception as e:
        error_msg = f"Installation error: {e}"
        if log_callback: log_callback(error_msg)
        print(error_msg)
        return False


class DownloadThread(QThread):
    update_log = Signal(str)
    update_progress = Signal(int)
    installed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        if download_ffmpeg_func(self.update_progress.emit, self.update_log.emit):
            if install_ffmpeg_func(self.update_log.emit):
                self.installed.emit()


# ──────────────────────────────────────────────
# Real-ESRGAN download / install
# ──────────────────────────────────────────────

def download_realesrgan_func(progress_callback=None, log_callback=None):
    """Download Real-ESRGAN ncnn-vulkan."""
    is_linux = platform.system() == "Linux"
    url = REALESRGAN_DL_LINUX if is_linux else REALESRGAN_DL_WINDOWS
    ext = ".tar.xz" if is_linux else ".zip"
    file_path = os.path.join(g.bin_dir, f"realesrgan{ext}")

    return _download_file(url, file_path, progress_callback, log_callback, label="Downloading Real-ESRGAN")


def install_realesrgan_func(log_callback=None):
    """Extract and install Real-ESRGAN ncnn-vulkan."""
    if log_callback:
        log_callback("Installing Real-ESRGAN...")
    print("Installing Real-ESRGAN...")

    is_linux = platform.system() == "Linux"
    ext = ".tar.xz" if is_linux else ".zip"
    archive_path = os.path.join(g.bin_dir, f"realesrgan{ext}")

    if not os.path.exists(archive_path):
        if log_callback:
            log_callback("Real-ESRGAN archive not found!")
        return False

    try:
        if is_linux:
            with tarfile.open(archive_path, "r:xz") as tar:
                tar.extractall(g.bin_dir)
        else:
            with zipfile.ZipFile(archive_path, "r") as zip_file:
                zip_file.extractall(g.bin_dir)

        os.remove(archive_path)

        # Find extracted directory
        dir_list = [d for d in os.listdir(g.bin_dir) if os.path.isdir(os.path.join(g.bin_dir, d))]
        if not dir_list:
            return False

        extracted_root = os.path.join(g.bin_dir, dir_list[0])

        # Move binary to bin_dir
        bin_name = "realesrgan-ncnn-vulkan.exe" if platform.system() == "Windows" else "realesrgan-ncnn-vulkan"
        src_bin = os.path.join(extracted_root, bin_name)
        dst_bin = os.path.join(g.bin_dir, bin_name)
        if os.path.exists(src_bin):
            if os.path.exists(dst_bin):
                os.remove(dst_bin)
            shutil.move(src_bin, dst_bin)

        # Move models directory
        src_models = os.path.join(extracted_root, "models")
        dst_models = os.path.join(g.bin_dir, "models")
        if os.path.exists(src_models):
            if os.path.exists(dst_models):
                shutil.rmtree(dst_models)
            shutil.move(src_models, dst_models)

        # Cleanup extracted folder
        shutil.rmtree(extracted_root, ignore_errors=True)

        # Make executable on Linux
        if is_linux and os.path.exists(dst_bin):
            os.chmod(dst_bin, 0o755)

        if os.path.exists(dst_bin):
            if log_callback:
                log_callback("Real-ESRGAN installed successfully!")
            return True
        return False
    except Exception as e:
        error_msg = f"Real-ESRGAN install error: {e}"
        if log_callback:
            log_callback(error_msg)
        print(error_msg)
        return False


# ──────────────────────────────────────────────
# RIFE download / install
# ──────────────────────────────────────────────

def download_rife_func(progress_callback=None, log_callback=None):
    """Download RIFE ncnn-vulkan."""
    is_linux = platform.system() == "Linux"
    url = RIFE_DL_LINUX if is_linux else RIFE_DL_WINDOWS
    ext = ".tar.xz" if is_linux else ".zip"
    file_path = os.path.join(g.bin_dir, f"rife{ext}")

    return _download_file(url, file_path, progress_callback, log_callback, label="Downloading RIFE")


def install_rife_func(log_callback=None):
    """Extract and install RIFE ncnn-vulkan."""
    if log_callback:
        log_callback("Installing RIFE...")
    print("Installing RIFE...")

    is_linux = platform.system() == "Linux"
    ext = ".tar.xz" if is_linux else ".zip"
    archive_path = os.path.join(g.bin_dir, f"rife{ext}")

    if not os.path.exists(archive_path):
        if log_callback:
            log_callback("RIFE archive not found!")
        return False

    try:
        if is_linux:
            with tarfile.open(archive_path, "r:xz") as tar:
                tar.extractall(g.bin_dir)
        else:
            with zipfile.ZipFile(archive_path, "r") as zip_file:
                zip_file.extractall(g.bin_dir)

        os.remove(archive_path)

        # Find extracted directory
        dir_list = [d for d in os.listdir(g.bin_dir) if os.path.isdir(os.path.join(g.bin_dir, d))]
        if not dir_list:
            return False

        extracted_root = os.path.join(g.bin_dir, dir_list[0])

        # Move binary to bin_dir
        bin_name = "rife-ncnn-vulkan.exe" if platform.system() == "Windows" else "rife-ncnn-vulkan"
        src_bin = os.path.join(extracted_root, bin_name)
        dst_bin = os.path.join(g.bin_dir, bin_name)
        if os.path.exists(src_bin):
            if os.path.exists(dst_bin):
                os.remove(dst_bin)
            shutil.move(src_bin, dst_bin)

        # Move models directory (if present)
        src_models = os.path.join(extracted_root, "models")
        dst_models = os.path.join(g.bin_dir, "models")
        if os.path.exists(src_models):
            if os.path.exists(dst_models):
                # Merge: copy individual model subdirectories
                for item in os.listdir(src_models):
                    s = os.path.join(src_models, item)
                    d = os.path.join(dst_models, item)
                    if os.path.isdir(s):
                        if os.path.exists(d):
                            shutil.rmtree(d)
                        shutil.move(s, d)
                    else:
                        shutil.move(s, d)
            else:
                shutil.move(src_models, dst_models)

        # Cleanup extracted folder
        shutil.rmtree(extracted_root, ignore_errors=True)

        # Make executable on Linux
        if is_linux and os.path.exists(dst_bin):
            os.chmod(dst_bin, 0o755)

        if os.path.exists(dst_bin):
            if log_callback:
                log_callback("RIFE installed successfully!")
            return True
        return False
    except Exception as e:
        error_msg = f"RIFE install error: {e}"
        if log_callback:
            log_callback(error_msg)
        print(error_msg)
        return False


# ──────────────────────────────────────────────
# DeOldify model download
# ──────────────────────────────────────────────

def download_deoldify_model(progress_callback=None, log_callback=None, model_key=None):
    """Download DeOldify ONNX model(s).

    If model_key is None, downloads all colorize models.
    If model_key is specified, downloads only that model.
    """
    from src.ai_tools import COLORIZE_MODELS

    if model_key:
        models_to_download = {model_key: COLORIZE_MODELS[model_key]}
    else:
        models_to_download = COLORIZE_MODELS

    models_dir = os.path.join(g.bin_dir, "models")
    os.makedirs(models_dir, exist_ok=True)

    all_ok = True
    for key, model_info in models_to_download.items():
        file_path = os.path.join(models_dir, model_info["model_filename"])
        if os.path.exists(file_path):
            if log_callback:
                log_callback(f"{model_info['name']} already downloaded.")
            continue

        ok = _download_file(
            model_info["model_url"],
            file_path,
            progress_callback,
            log_callback,
            label=f"Downloading {model_info['name']}",
        )
        if ok:
            if log_callback:
                log_callback(f"{model_info['name']} downloaded successfully!")
        else:
            all_ok = False

    return all_ok
