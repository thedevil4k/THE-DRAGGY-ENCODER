import os
import sys
import platform


VERSION = "1"
TITLE = f"DRAGGY ENCODER v{VERSION}"
READY_TEXT = f"Select your videos to get started."
DEFAULT_SETTINGS = {"target_size": 20.0, "codec": "libx264"}

ffmpeg_path = "ffmpeg"
ffprobe_path = "ffprobe"
queue = []
completed = []
root_dir = ""
bin_dir = ""
output_dir = ""
res_dir = ""
ffmpeg_installed = False
compressing = False


def verify_directories():
    global root_dir, bin_dir, output_dir, res_dir, ffmpeg_path, ffprobe_path
    
    if getattr(sys, "frozen", False):
        root_dir = os.path.dirname(sys.executable)
    else:
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    bin_dir = os.path.join(root_dir, "bin")
    if not os.path.exists(bin_dir):
        os.mkdir(bin_dir)

    output_dir = os.path.join(root_dir, "output")
    if not os.path.exists(output_dir):
        os.mkdir(output_dir)

    res_dir = os.path.join(root_dir, "res")
    
    if platform.system() == "Windows":
        ffmpeg_path = os.path.join(bin_dir, "ffmpeg.exe")
        ffprobe_path = os.path.join(bin_dir, "ffprobe.exe")
    else:
        ffmpeg_path = os.path.join(bin_dir, "ffmpeg")
        ffprobe_path = os.path.join(bin_dir, "ffprobe")
