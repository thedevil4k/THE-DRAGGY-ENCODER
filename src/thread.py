import json
import subprocess
import os
import platform
import src.globals as g
from math import ceil, floor
from PySide6.QtCore import QThread, Signal


def get_video_length(file_path):
    cmd = [
        g.ffprobe_path,
        "-v",
        "quiet",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        file_path,
    ]

    output = subprocess.check_output(cmd)
    data = json.loads(output)

    if "format" in data:
        duration = data["format"].get("duration")
        return float(duration) if duration else 0

    return 0


def get_video_metadata(file_path):
    """Returns a dictionary with video and audio metadata."""
    try:
        # Video stream info
        cmd_video = [
            g.ffprobe_path, "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,codec_name,bit_rate,pix_fmt",
            "-of", "json", file_path,
        ]
        output = subprocess.check_output(cmd_video)
        data = json.loads(output)

        width, height, codec, bitrate, pix_fmt = None, None, None, None, "Unknown"
        if "streams" in data and len(data["streams"]) > 0:
            stream = data["streams"][0]
            width = stream.get("width")
            height = stream.get("height")
            codec = stream.get("codec_name")
            bitrate = stream.get("bit_rate")
            pix_fmt = stream.get("pix_fmt", "Unknown")

        # Overall bitrate fallback
        if not bitrate:
            cmd_fmt = [
                g.ffprobe_path, "-v", "quiet",
                "-show_entries", "format=bit_rate",
                "-of", "json", file_path,
            ]
            output_fmt = subprocess.check_output(cmd_fmt)
            data_fmt = json.loads(output_fmt)
            bitrate = data_fmt.get("format", {}).get("bit_rate")

        # Audio stream info
        audio_codec = "No Audio"
        audio_bitrate = "N/A"
        try:
            cmd_audio = [
                g.ffprobe_path, "-v", "quiet",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_name,bit_rate",
                "-of", "json", file_path,
            ]
            audio_output = subprocess.check_output(cmd_audio)
            audio_data = json.loads(audio_output)
            if "streams" in audio_data and len(audio_data["streams"]) > 0:
                a_stream = audio_data["streams"][0]
                audio_codec = a_stream.get("codec_name", "Unknown")
                a_br = a_stream.get("bit_rate")
                if a_br:
                    audio_bitrate = f"{round(float(a_br) / 1000)} kbps"
        except:
            pass

        res_str = f"{width}x{height}" if width and height else "Unknown"
        codec_str = codec if codec else "Unknown"
        bitrate_str = f"{round(float(bitrate) / 1000)} kbps" if bitrate else "Unknown"
        depth = "10-bit" if "10" in pix_fmt else "12-bit" if "12" in pix_fmt else "8-bit"
        
        return {
            "resolution": res_str,
            "codec": codec_str,
            "bitrate": bitrate_str,
            "pix_fmt": pix_fmt,
            "depth": depth,
            "audio_codec": audio_codec,
            "audio_bitrate": audio_bitrate,
        }
    except Exception as e:
        print(f"Error getting metadata: {e}")

    return {"resolution": "Unknown", "codec": "Unknown", "bitrate": "Unknown", "pix_fmt": "Unknown", "depth": "Unknown", "audio_codec": "Unknown", "audio_bitrate": "Unknown"}



def human_readable_size(size_bytes):
    import math
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"


def get_audio_bitrate(video_path):
    cmd = [
        g.ffprobe_path,
        "-v",
        "quiet",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=bit_rate",
        "-of",
        "json",
        video_path,
    ]

    # Run ffprobe and capture output
    output = subprocess.check_output(cmd)
    data = json.loads(output)

    # Extract bitrate from JSON response
    if "streams" in data and len(data["streams"]) > 0:
        bitrate = data["streams"][0].get("bit_rate")
        return round(float(bitrate) / 1000) if bitrate else 0

    return 0


def calculate_video_bitrate(file_path, target_size_mb):
    v_len = get_video_length(file_path)
    print(f"Video duration: {v_len} seconds")
    a_rate = get_audio_bitrate(file_path)
    print(f"Audio Bitrate: {a_rate}k")
    total_bitrate = (target_size_mb * 8192.0 * 0.98) / (1.048576 * v_len) - a_rate
    return max(1, round(total_bitrate))


def is_encoder_supported(encoder_name, pix_fmt=None):
    """
    Checks if the hardware actually supports the encoder by running a 1-frame test.
    This is highly reliable as it interacts directly with the drivers.
    """
    try:
        cmd = [
            g.ffmpeg_path,
            "-v", "error",
            "-f", "lavfi",
            "-i", "color=c=black:s=128x128",
            "-c:v", encoder_name,
            "-frames:v", "1"
        ]
        if pix_fmt:
            cmd.extend(["-pix_fmt", pix_fmt])
        
        cmd.extend(["-f", "null", "-"])
        
        kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "check": True, "timeout": 5}
        if platform.system() == "Windows":
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW

        subprocess.run(cmd, **kwargs)
        return True
    except:
        return False




def get_available_encoders():
    """Detects available video encoders from ffmpeg."""
    print("  get_available_encoders start")
    try:
        cmd = [g.ffmpeg_path, "-hide_banner", "-encoders"]
        print(f"  Running: {' '.join(cmd)}")
        kwargs = {"universal_newlines": True}
        if platform.system() == "Windows":
            kwargs["creationflags"] = 0x08000000
        output = subprocess.check_output(cmd, **kwargs)
        
        encoders = []
        # common encoders we are interested in (priority)
        hardware_priority = [
            "h264_nvenc", "hevc_nvenc", "av1_nvenc",
            "h264_amf", "hevc_amf", "av1_amf",
            "h264_qsv", "hevc_qsv", "av1_qsv",
            "h264_vaapi", "hevc_vaapi", "av1_vaapi",
            "libx264", "libx265", "libsvtav1", "libaom-av1", "libvvenc"
        ]
        
        all_video_encoders = []
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
                    name = parts[1]
                    all_video_encoders.append(name)
        
        # Build the final list: Priority ones first (if supported)
        encoders = []
        for name in hardware_priority:
            if name in all_video_encoders:
                # For hardware encoders, check if they are actually supported by the current hardware
                if any(hw in name for hw in ["nvenc", "amf", "qsv", "vaapi"]):
                    print(f"  Testing hardware encoder: {name}")
                    if is_encoder_supported(name):
                        # For NVENC, also check 10-bit support
                        if "nvenc" in name:
                            if is_encoder_supported(name, "p010le"):
                                encoders.append(f"{name} (Modern 10-bit)")
                            encoders.append(f"{name} (Standard 8-bit)")
                        else:
                            encoders.append(name)
                else:
                    encoders.append(name)
        
        # Add a default if nothing detected
        if not encoders:
            encoders = ["libx264"]
            
        return encoders
    except Exception as e:
        print(f"Error getting encoders: {e}")
        return ["libx264"]


def get_hardware_info():
    """Detects CPU and GPU information. Uses PowerShell on Windows, /proc and lspci on Linux."""
    print("  get_hardware_info start")
    info = {"cpu": "Unknown CPU", "gpus": []}
    try:
        if platform.system() == "Windows":
            creation_flags = 0x08000000  # CREATE_NO_WINDOW
            # Detect CPU
            cpu_cmd = ["powershell", "-Command", "Get-CimInstance Win32_Processor | Select-Object -ExpandProperty Name"]
            print("  Running PowerShell for CPU...")
            cpu_output = subprocess.check_output(cpu_cmd, universal_newlines=True, creationflags=creation_flags).strip()
            print(f"  CPU detected: {cpu_output}")
            if cpu_output:
                info["cpu"] = cpu_output
            # Detect GPUs
            gpu_cmd = ["powershell", "-Command", "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"]
            print("  Running PowerShell for GPUs...")
            gpu_output = subprocess.check_output(gpu_cmd, universal_newlines=True, creationflags=creation_flags).strip()
            print(f"  GPU output received: {gpu_output}")
            if gpu_output:
                info["gpus"] = [line.strip() for line in gpu_output.splitlines() if line.strip()]
        else:
            # Linux: CPU from /proc/cpuinfo
            try:
                with open("/proc/cpuinfo", "r") as f:
                    for line in f:
                        if line.startswith("model name"):
                            info["cpu"] = line.split(":")[1].strip()
                            break
            except:
                pass
            # Linux: GPUs from lspci
            try:
                gpu_output = subprocess.check_output(["lspci"], universal_newlines=True)
                for line in gpu_output.splitlines():
                    if "VGA" in line or "3D" in line or "Display" in line:
                        # Format: "00:02.0 VGA compatible controller: Intel ..."
                        gpu_name = line.split(": ", 1)[-1] if ": " in line else line
                        info["gpus"].append(gpu_name.strip())
            except:
                info["gpus"] = ["Unknown GPU"]
    except Exception as e:
        print(f"Error detecting hardware: {e}")
    return info


class CompressionThread(QThread):
    update_log = Signal(str)
    update_progress = Signal(int)
    error_msg = Signal(str)
    completed = Signal()

    def __init__(self, target_size_mb, codec, export_format="Original", audio_codec="copy", is_audio_only=False, parent=None):
        super().__init__(parent)
        self.target_size_mb = target_size_mb
        self.codec = codec
        self.export_format = export_format
        self.audio_codec = audio_codec
        self.is_audio_only = is_audio_only
        self.process = None

    def run_audio_pass(self, file_path):
        file_name = os.path.basename(file_path)

        total_steps = len(g.queue)
        current_step = len(g.completed)
        progress_percentage = (current_step / total_steps) * 100
        self.update_progress.emit(int(progress_percentage))
        
        status_msg = f"""
[Audio Encoding Status]
File: {file_name}
Queue: {len(g.completed) + 1}/{len(g.queue)}
Preset: {self.codec}
"""
        file_name_without_ext, original_ext = os.path.basename(file_path).rsplit(".", 1)
        
        out_ext = original_ext
        if self.export_format != "Original" and self.export_format:
            out_ext = self.export_format.lower().replace(".", "")
            
        output_path = os.path.join(
            g.output_dir, f"{file_name_without_ext}-compressed.{out_ext}"
        )
        print(status_msg)

        cmd_args = [
            f'"{g.ffmpeg_path}"',
            f'-i "{file_path}"',
            "-y",
        ]

        if "MP3" in self.codec:
            cmd_args.extend(["-c:a", "libmp3lame"])
            if "128" in self.codec: cmd_args.extend(["-b:a", "128k"])
            elif "192" in self.codec: cmd_args.extend(["-b:a", "192k"])
            elif "320" in self.codec: cmd_args.extend(["-b:a", "320k"])
        elif "AAC" in self.codec:
            cmd_args.extend(["-c:a", "aac"])
            if "128" in self.codec: cmd_args.extend(["-b:a", "128k"])
            elif "192" in self.codec: cmd_args.extend(["-b:a", "192k"])
            elif "256" in self.codec: cmd_args.extend(["-b:a", "256k"])
        elif "FLAC" in self.codec:
            cmd_args.extend(["-c:a", "flac"])
        elif "WAV" in self.codec:
            cmd_args.extend(["-c:a", "pcm_s16le"])
        elif "Copy" in self.codec:
            cmd_args.extend(["-c:a", "copy"])

        cmd_args.append(f'"{output_path}"')

        cmd = " ".join(cmd_args)
        print(f"Running command: {cmd}")
        self.update_log.emit(status_msg)
        self.process = subprocess.check_call(cmd, shell=True)

    def run_pass(self, file_path):
        video_rate = calculate_video_bitrate(file_path, self.target_size_mb)
        metadata = get_video_metadata(file_path)
        pix_fmt = metadata.get("pix_fmt", "unknown")
        file_name = os.path.basename(file_path)

        orig_depth = metadata.get("depth", "Unknown")
        target_depth = orig_depth
        if "nvenc" in self.codec and "10" in pix_fmt:
            target_depth = "8-bit (Converted for compatibility)"

        for i in range(2):
            # Calculate total progress based on queue position and current pass
            total_steps = len(g.queue) * 2  # Total number of passes for all videos
            current_step = (
                len(g.completed) * 2
            ) + i  # Completed videos * 2 passes + current pass
            progress_percentage = (current_step / total_steps) * 100
            self.update_progress.emit(int(progress_percentage))
            
            status_msg = f"""
[Compression Status]
File: {file_name}
Queue: {len(g.completed) + 1}/{len(g.queue)}
Pass: {i + 1}/2
Target Size: {self.target_size_mb}MB
Bitrate: {video_rate}k
Encoder: {self.codec}
Depth: {orig_depth} -> {target_depth}
"""

            # Rest of the existing code remains the same
            bitrate_str = f"{video_rate}k"
            file_name_without_ext, original_ext = os.path.basename(file_path).rsplit(
                ".", 1
            )
            
            # Determine output extension
            out_ext = original_ext
            if self.export_format != "Original" and self.export_format:
                out_ext = self.export_format.lower().replace(".", "")
                
            output_path = os.path.join(
                g.output_dir, f"{file_name_without_ext}-compressed.{out_ext}"
            )
            print(f"New bitrate: {bitrate_str}")
            print(status_msg)

            # Base command arguments
            pure_codec = self.codec.split(" ")[0]
            cmd_args = [
                f'"{g.ffmpeg_path}"',
                f'-i "{file_path}"',
                "-y",
                f"-b:v {bitrate_str}",
                f"-c:v {pure_codec}"
            ]

            # VAAPI specific flags for Linux
            if "vaapi" in pure_codec and platform.system() == "Linux":
                # Add hwaccel flags for VAAPI
                vaapi_flags = [
                    "-hwaccel vaapi",
                    "-hwaccel_output_format vaapi",
                    "-vaapi_device /dev/dri/renderD128"
                ]
                for flag in reversed(vaapi_flags):
                    cmd_args.insert(1, flag)

            # Handle bit-depth variants for NVENC
            if "(Modern 10-bit)" in self.codec:
                cmd_args.append("-pix_fmt p010le")
            elif "(Standard 8-bit)" in self.codec:
                cmd_args.append("-pix_fmt yuv420p")
            elif "nvenc" in pure_codec and "10" in pix_fmt:
                # Fallback for old code paths or other nvenc uses
                print(f"Detected 10-bit input ({pix_fmt}) with NVENC. Forcing 8-bit output for compatibility.")
                cmd_args.append("-pix_fmt yuv420p")

            if i == 0:
                cmd_args.extend(["-an", "-pass", "1", "-f", "mp4", "TEMP"])
            else:
                # Audio handling for pass 2
                if self.audio_codec == "none":
                    cmd_args.append("-an")
                elif self.audio_codec == "copy":
                    cmd_args.extend(["-c:a", "copy"])
                elif self.audio_codec == "aac":
                    cmd_args.extend(["-c:a", "aac", "-b:a", "192k"])
                elif self.audio_codec == "mp3":
                    cmd_args.extend(["-c:a", "libmp3lame", "-b:a", "192k"])
                elif self.audio_codec == "opus":
                    cmd_args.extend(["-c:a", "libopus", "-b:a", "128k"])
                elif self.audio_codec == "flac":
                    cmd_args.extend(["-c:a", "flac"])
                else:
                    cmd_args.extend(["-c:a", "copy"])
                cmd_args.extend(["-pass", "2", f'"{output_path}"'])

            cmd = " ".join(cmd_args)
            print(f"Running command: {cmd}")
            self.update_log.emit(status_msg)
            self.process = subprocess.check_call(cmd, shell=True)

    def run(self):
        g.completed = []

        try:
            for file_path in g.queue:
                if not g.compressing:
                    break

                if self.is_audio_only:
                    self.run_audio_pass(file_path)
                else:
                    self.run_pass(file_path)
                g.completed.append(file_path)

            msg = (
                f"Compressed {len(g.completed)} video(s)!" if g.compressing else "Aborted!"
            )
        except Exception as e:
            error_text = str(e)
            if any(term in error_text.lower() for term in ["encoder", "codec", "not implemented", "invalid argument"]):
                self.error_msg.emit("Codec no compatible")
            
            msg = f"Error during compression: {e}"
            print(msg)
            g.compressing = False

        print(msg)
        self.update_log.emit(msg)
        self.completed.emit()
