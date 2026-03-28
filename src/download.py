import os
import platform
import requests
import shutil
import src.globals as g
import zipfile
import tarfile
from PySide6.QtCore import QThread, Signal

FFMPEG_DL_WINDOWS = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
FFMPEG_DL_LINUX = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz"


def download_ffmpeg_func(progress_callback=None, log_callback=None):
    """
    Standalone function to download FFmpeg.
    :param progress_callback: Function taking an int (0-100)
    :param log_callback: Function taking a str message
    """
    if log_callback: log_callback("Downloading FFmpeg...")
    print("Downloading FFmpeg...")
    
    is_linux = platform.system() == "Linux"
    url = FFMPEG_DL_LINUX if is_linux else FFMPEG_DL_WINDOWS
    ext = ".tar.xz" if is_linux else ".zip"

    bin_path = g.bin_dir
    file_path = os.path.join(bin_path, f"ffmpeg{ext}")
    
    try:
        response = requests.get(url, stream=True)
        if not response.ok:
            error_msg = f"Download failed: {response.status_code}"
            if log_callback: log_callback(error_msg)
            print(error_msg)
            return False

        print(f"Source: {url}")
        total_size = response.headers.get("content-length")

        with open(file_path, "wb") as f:
            if total_size is None:
                f.write(response.content)
            else:
                downloaded = 0
                total_size = int(total_size)

                for chunk in response.iter_content(chunk_size=4096):
                    downloaded += len(chunk)
                    f.write(chunk)
                    percentage = (downloaded / total_size) * 100
                    downloaded_mb = downloaded / (1024 * 1024)
                    total_mb = total_size / (1024 * 1024)
                    message = f"Downloading FFmpeg...\n{downloaded_mb:.1f} MB / {total_mb:.1f} MB"
                    if log_callback: log_callback(message)
                    if progress_callback: progress_callback(int(percentage))
        return True
    except Exception as e:
        error_msg = f"Download error: {e}"
        if log_callback: log_callback(error_msg)
        print(error_msg)
        return False


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
