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


class DownloadThread(QThread):
    update_log = Signal(str)
    update_progress = Signal(int)
    installed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

    def download_ffmpeg(self):
        print("Downloading FFmpeg...")
        is_linux = platform.system() == "Linux"
        url = FFMPEG_DL_LINUX if is_linux else FFMPEG_DL_WINDOWS
        ext = ".tar.xz" if is_linux else ".zip"

        bin_path = g.bin_dir
        file_path = os.path.join(bin_path, f"ffmpeg{ext}")
        response = requests.get(url, stream=True)

        if not response.ok:
            print(f"Download failed: {response.status_code}\n{response.text}")
            return

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
                    self.update_log.emit(message)
                    self.update_progress.emit(int(percentage))

    def install_ffmpeg(self):
        print("Installing FFmpeg...")
        is_linux = platform.system() == "Linux"

        if is_linux:
            tar_path = os.path.join(g.bin_dir, "ffmpeg.tar.xz")
            with tarfile.open(tar_path, "r:xz") as tar:
                tar.extractall(g.bin_dir)
            os.remove(tar_path)
        else:
            zip_path = os.path.join(g.bin_dir, "ffmpeg.zip")
            with zipfile.ZipFile(zip_path, "r") as zip_file:
                zip_file.extractall(g.bin_dir)
            os.remove(zip_path)

        # Get extracted paths
        extracted_root = os.path.join(g.bin_dir, os.listdir(g.bin_dir)[0])
        extracted_bin = os.path.join(extracted_root, "bin")

        # Move binaries to target directory
        for file_name in os.listdir(extracted_bin):
            src = os.path.join(extracted_bin, file_name)
            dst = os.path.join(g.bin_dir, file_name)
            try:
                shutil.move(src, dst)
            except:
                print(f"Skipped {file_name} - file already exists")

        # Cleanup
        shutil.rmtree(extracted_root)

        # Remove ffplay (not needed)
        if is_linux:
            ffplay_path = os.path.join(g.bin_dir, "ffplay")
        else:
            ffplay_path = os.path.join(g.bin_dir, "ffplay.exe")
        
        if os.path.exists(ffplay_path):
            os.remove(ffplay_path)

        # Make executables on Linux
        if is_linux:
            for name in ["ffmpeg", "ffprobe"]:
                path = os.path.join(g.bin_dir, name)
                if os.path.exists(path):
                    os.chmod(path, 0o755)

    def run(self):
        self.download_ffmpeg()
        self.install_ffmpeg()
        self.installed.emit()
