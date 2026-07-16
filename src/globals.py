import os
import sys
import platform


VERSION = "1"
TITLE = f"DRAGGY ENCODER v{VERSION}"
READY_TEXT = f"Select your videos to get started."
DEFAULT_SETTINGS = {"target_size": 20.0, "codec": "libx264"}

ffmpeg_path = "ffmpeg"
ffprobe_path = "ffprobe"
realesrgan_path = ""
rife_path = ""
queue = []
completed = []
task_queue = []
task_id_counter = 0
active_task_id = None
root_dir = ""
install_dir = ""
bin_dir = ""
output_dir = ""
res_dir = ""
ffmpeg_installed = False
compressing = False
encoder_errors = {}


def _detect_install_and_root_dirs():
    """Return (install_dir, root_dir).

    install_dir: writable folder where the application lives (where bin/ is created).
    root_dir: folder containing bundled static assets (res/).
    """
    if getattr(sys, "frozen", False):
        # One-file/one-dir PyInstaller layout: the executable directory is writable;
        # _MEIPASS is the temporary extraction folder for bundled files.
        install_dir = os.path.dirname(sys.executable)
        root_dir = getattr(sys, "_MEIPASS", install_dir)
    else:
        install_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        root_dir = install_dir
    return install_dir, root_dir


def _is_dir_writable(path):
    """Check whether we can create files in *path* (create it if needed)."""
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_test")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return True
    except Exception:
        return False


def _fallback_data_dir():
    """Return a writable per-user data directory for binaries/outputs."""
    if platform.system() == "Windows":
        base = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "DraggyEncoder")
    else:
        base = os.path.expanduser("~/.draggy_encoder")
    os.makedirs(base, exist_ok=True)
    return base


def verify_directories():
    global root_dir, install_dir, bin_dir, output_dir, res_dir
    global ffmpeg_path, ffprobe_path, realesrgan_path, rife_path

    install_dir, root_dir = _detect_install_and_root_dirs()
    res_dir = os.path.join(root_dir, "res")

    # Try to keep binaries next to the application, but fall back to per-user
    # data directory if the install folder is read-only (e.g. Program Files).
    candidate_bin_dir = os.path.join(install_dir, "bin")
    if _is_dir_writable(candidate_bin_dir):
        bin_dir = candidate_bin_dir
    else:
        fallback = _fallback_data_dir()
        bin_dir = os.path.join(fallback, "bin")
        os.makedirs(bin_dir, exist_ok=True)

    # Outputs and user settings always live in the per-user data directory.
    base_data_dir = _fallback_data_dir()
    output_dir = os.path.join(base_data_dir, "output")
    os.makedirs(output_dir, exist_ok=True)

    if platform.system() == "Windows":
        ffmpeg_path = os.path.join(bin_dir, "ffmpeg.exe")
        ffprobe_path = os.path.join(bin_dir, "ffprobe.exe")
        realesrgan_path = os.path.join(bin_dir, "realesrgan-ncnn-vulkan.exe")
        rife_path = os.path.join(bin_dir, "rife-ncnn-vulkan.exe")
    else:
        ffmpeg_path = os.path.join(bin_dir, "ffmpeg")
        ffprobe_path = os.path.join(bin_dir, "ffprobe")
        realesrgan_path = os.path.join(bin_dir, "realesrgan-ncnn-vulkan")
        rife_path = os.path.join(bin_dir, "rife-ncnn-vulkan")
