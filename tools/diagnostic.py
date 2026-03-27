import sys
import os
import platform
import subprocess
import json

# Mock globals for the test
class G:
    def __init__(self):
        self.root_dir = os.path.dirname(os.path.abspath(__file__))
        self.bin_dir = os.path.join(self.root_dir, "bin")
        if platform.system() == "Windows":
            self.ffmpeg_path = os.path.join(self.bin_dir, "ffmpeg.exe")
            self.ffprobe_path = os.path.join(self.bin_dir, "ffprobe.exe")
        else:
            self.ffmpeg_path = os.path.join(self.bin_dir, "ffmpeg")
            self.ffprobe_path = os.path.join(self.bin_dir, "ffprobe")

import src.globals as g
g.root_dir = os.path.dirname(os.path.abspath(__file__))
g.bin_dir = os.path.join(g.root_dir, "bin")
if platform.system() == "Windows":
    g.ffmpeg_path = os.path.join(g.bin_dir, "ffmpeg.exe")
    g.ffprobe_path = os.path.join(g.bin_dir, "ffprobe.exe")
else:
    g.ffmpeg_path = os.path.join(g.bin_dir, "ffmpeg")
    g.ffprobe_path = os.path.join(g.bin_dir, "ffprobe")

from src.thread import get_hardware_info, get_available_encoders

print("Testing hardware info detection...")
try:
    hw = get_hardware_info()
    print(f"Hardware info: {hw}")
except Exception as e:
    print(f"Hardware info detection failed: {e}")

print("\nTesting encoder detection...")
try:
    encoders = get_available_encoders()
    print(f"Available encoders: {encoders}")
except Exception as e:
    print(f"Encoder detection failed: {e}")

print("\nSuccess!")
