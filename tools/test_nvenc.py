import subprocess
import os
import platform

# Hardcoded paths based on trace
ffmpeg_path = r"D:\video-compressor-3.1.2\video-compressor-3.1.2\bin\ffmpeg.exe"

print(f"Testing h264_nvenc support...")
cmd = [
    ffmpeg_path,
    "-v", "debug", # Use debug for more info
    "-f", "lavfi",
    "-i", "color=c=black:s=128x128",
    "-c:v", "h264_nvenc",
    "-frames:v", "1",
    "-f", "null", "-"
]

print(f"Running command: {' '.join(cmd)}")
try:
    # Run WITHOUT creationflags and WITHOUT output redirection to see everything
    res = subprocess.run(cmd, timeout=15)
    print(f"\nCommand finished with exit code: {res.returncode}")
except subprocess.TimeoutExpired:
    print("\nCommand TIMED OUT after 15 seconds!")
except Exception as e:
    print(f"\nCommand failed with error: {e}")

print("\nDone testing.")
