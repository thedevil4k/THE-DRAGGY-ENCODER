import sys
import os
import subprocess

print("--- DIAGNOSTIC START ---", flush=True)

import src.globals as g
g.root_dir = os.path.dirname(os.path.abspath(__file__))
g.bin_dir = os.path.join(g.root_dir, "bin")
g.ffmpeg_path = os.path.join(g.bin_dir, "ffmpeg.exe")

print(f"FFmpeg path: {g.ffmpeg_path}", flush=True)
print(f"Exists: {os.path.exists(g.ffmpeg_path)}", flush=True)

print("Attempting to run ffmpeg -version...", flush=True)
try:
    # Use a simpler command and no creation flags
    res = subprocess.run([g.ffmpeg_path, "-version"], capture_output=True, text=True, timeout=10)
    print("FFmpeg output received!", flush=True)
    print(res.stdout[:100], flush=True)
except Exception as e:
    print(f"FFmpeg failed: {e}", flush=True)

print("--- DIAGNOSTIC END ---", flush=True)
