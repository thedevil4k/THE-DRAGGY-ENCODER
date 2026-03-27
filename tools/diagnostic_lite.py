import sys
import os
import platform
import subprocess
import json

# Setup globals
import src.globals as g
g.root_dir = os.path.dirname(os.path.abspath(__file__))
g.bin_dir = os.path.join(g.root_dir, "bin")
if platform.system() == "Windows":
    g.ffmpeg_path = os.path.join(g.bin_dir, "ffmpeg.exe")
    g.ffprobe_path = os.path.join(g.bin_dir, "ffprobe.exe")

def is_encoder_supported_lite(encoder_name):
    print(f"Checking support for {encoder_name}...")
    try:
        cmd = [g.ffmpeg_path, "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=128x128", "-c:v", encoder_name, "-frames:v", "1", "-f", "null", "-"]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=5)
        return True
    except:
        return False

def get_available_encoders_lite():
    print("Getting available encoders...")
    try:
        cmd = [g.ffmpeg_path, "-hide_banner", "-encoders"]
        output = subprocess.check_output(cmd, universal_newlines=True)
        
        hardware_priority = ["h264_nvenc", "libx264"]
        all_video_encoders = []
        for line in output.splitlines():
            if line.startswith(" V"):
                parts = line.split()
                if len(parts) >= 2:
                    all_video_encoders.append(parts[1])
        
        encoders = []
        for name in hardware_priority:
            if name in all_video_encoders:
                if "nvenc" in name:
                    if is_encoder_supported_lite(name):
                        encoders.append(name)
                else:
                    encoders.append(name)
        return encoders
    except Exception as e:
        print(f"Error: {e}")
        return ["libx264"]

print("Starting Lite Diagnostic...")
encoders = get_available_encoders_lite()
print(f"Detected Encoders: {encoders}")
print("Done!")
