import json
import subprocess
import os
import platform
import src.globals as g
from pathlib import Path
from math import ceil, floor
from PySide6.QtCore import QThread, Signal


def get_video_length(file_path):
    cmd = [
        str(g.ffprobe_path),
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "json",
        str(file_path),
    ]
    try:
        output = subprocess.check_output(cmd)
        data = json.loads(output)
        if "format" in data:
            duration = data["format"].get("duration")
            return float(duration) if duration else 0
    except Exception as e:
        print(f"Error getting video length: {e}")
    return 0


def get_video_metadata(file_path):
    """Returns a dictionary with video and audio metadata."""
    file_path = str(file_path)
    try:
        # Video stream info
        cmd_video = [
            str(g.ffprobe_path), "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,codec_name,bit_rate,pix_fmt,display_aspect_ratio",
            "-of", "json", file_path,
        ]
        output = subprocess.check_output(cmd_video)
        data = json.loads(output)

        width, height, codec, bitrate, pix_fmt, display_ar = None, None, None, None, "Unknown", None
        if "streams" in data and (streams := data["streams"]):
            stream = streams[0]
            width = stream.get("width")
            height = stream.get("height")
            codec = stream.get("codec_name")
            bitrate = stream.get("bit_rate")
            pix_fmt = stream.get("pix_fmt", "Unknown")
            display_ar = stream.get("display_aspect_ratio")

        # Overall bitrate fallback
        if not bitrate:
            cmd_fmt = [
                str(g.ffprobe_path), "-v", "quiet",
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
                str(g.ffprobe_path), "-v", "quiet",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_name,bit_rate",
                "-of", "json", file_path,
            ]
            audio_output = subprocess.check_output(cmd_audio)
            audio_data = json.loads(audio_output)
            if "streams" in audio_data and (a_streams := audio_data["streams"]):
                a_stream = a_streams[0]
                audio_codec = a_stream.get("codec_name", "Unknown")
                if a_br := a_stream.get("bit_rate"):
                    audio_bitrate = f"{round(float(a_br) / 1000)} kbps"
        except Exception:
            pass

        ar_str = ""
        if display_ar and display_ar != "N/A" and display_ar != "0:1":
            ar_str = display_ar
        elif width and height:
            import math
            ratio = width / height
            if abs(ratio - 16/9) < 0.05: ar_str = "16:9"
            elif abs(ratio - 9/16) < 0.05: ar_str = "9:16"
            elif abs(ratio - 4/3) < 0.05: ar_str = "4:3"
            elif abs(ratio - 3/4) < 0.05: ar_str = "3:4"
            elif abs(ratio - 1.0) < 0.05: ar_str = "1:1"
            elif abs(ratio - 21/9) < 0.05: ar_str = "21:9"
            elif abs(ratio - 18/9) < 0.05: ar_str = "18:9"
            elif abs(ratio - 9/18) < 0.05: ar_str = "9:18"
            else:
                g_val = math.gcd(width, height)
                ar_str = f"{width//g_val}:{height//g_val}"

        res_str = f"{width}x{height}" if width and height else "Unknown"
        if ar_str:
            res_str += f" ({ar_str})"

        codec_str = codec if codec else "Unknown"
        bitrate_str = f"{round(float(bitrate) / 1000)} kbps" if bitrate else "Unknown"
        depth = "10-bit" if "10" in pix_fmt else "12-bit" if "12" in pix_fmt else "8-bit"
        
        return {
            "resolution": res_str,
            "width": width,
            "height": height,
            "codec": codec_str,
            "bitrate": bitrate_str,
            "pix_fmt": pix_fmt,
            "depth": depth,
            "audio_codec": audio_codec,
            "audio_bitrate": audio_bitrate,
        }
    except Exception as e:
        print(f"Error getting metadata: {e}")

    return {"resolution": "Unknown", "width": None, "height": None, "codec": "Unknown", "bitrate": "Unknown", "pix_fmt": "Unknown", "depth": "Unknown", "audio_codec": "Unknown", "audio_bitrate": "Unknown"}



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
    Checks if the hardware truly supports the encoder by running a short test encode.
    Uses quality-based encoding (like HandBrake's ICQ mode) which is more compatible
    with hardware encoders than bitrate mode.
    """
    try:
        cmd = [
            str(g.ffmpeg_path),
            "-v", "error",
            "-f", "lavfi",
            "-i", "color=c=black:s=256x256:d=1",
            "-c:v", encoder_name,
            "-frames:v", "5",
        ]
        
        # Use quality-based encoding for hardware encoders (more compatible)
        if "qsv" in encoder_name:
            cmd.extend(["-global_quality", "25"])
        elif "nvenc" in encoder_name:
            cmd.extend(["-cq", "28"])
        elif "amf" in encoder_name:
            cmd.extend(["-quality", "balanced"])
        elif "vaapi" in encoder_name:
            cmd.extend(["-qp", "25"])
        
        if pix_fmt:
            cmd.extend(["-pix_fmt", pix_fmt])

        cmd.extend(["-f", "null", "-"])

        kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.PIPE,
            "timeout": 15,
        }
        if platform.system() == "Windows":
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW

        result = subprocess.run(cmd, **kwargs)

        if result.returncode != 0:
            stderr_text = result.stderr.decode("utf-8", errors="ignore") if result.stderr else ""
            print(f"  Encoder {encoder_name} failed (rc={result.returncode}): {stderr_text[:200]}")
            return False

        return True
    except subprocess.TimeoutExpired:
        print(f"  Encoder {encoder_name} timed out")
        return False
    except Exception as e:
        print(f"  Encoder {encoder_name} error: {e}")
        return False


def get_available_encoders(gpu_names=None):
    """Detects available video encoders from ffmpeg.
    
    Each hardware encoder is tested with a quality-based encode to verify
    real hardware support. Software encoders are assumed available if present.
    """
    print("  get_available_encoders start")
    try:
        cmd = [str(g.ffmpeg_path), "-hide_banner", "-encoders"]
        print(f"  Running: {' '.join(cmd)}")
        kwargs = {"universal_newlines": True}
        if platform.system() == "Windows":
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        output = subprocess.check_output(cmd, **kwargs)
        
        encoders = []
        # Hardware encoders to check (in priority order)
        hardware_priority = [
            "h264_nvenc", "hevc_nvenc", "av1_nvenc",
            "h264_amf", "hevc_amf", "av1_amf",
            "h264_qsv", "hevc_qsv", "av1_qsv",
            "h264_vaapi", "hevc_vaapi", "av1_vaapi",
            "libx264", "libx265", "libsvtav1", "libaom-av1", "libvvenc", "ffv1"
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
        
        # Build the final list: Priority ones first (if truly supported)
        encoders = []
        for name in hardware_priority:
            if name in all_video_encoders:
                # For hardware encoders, run a quality-based capability test
                if any(hw in name for hw in ["nvenc", "amf", "qsv", "vaapi"]):
                    if is_encoder_supported(name):
                        # For all hardware encoders, check 10-bit support
                        if is_encoder_supported(name, "p010le"):
                            encoders.append(f"{name} (Modern 10-bit)")
                        encoders.append(f"{name} (Standard 8-bit)")
                    else:
                        print(f"  Encoder {name} failed test, skipping.")
                else:
                    # Software encoders (libx264, libx265, ffv1, etc.)
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
    task_started = Signal(int)

    def __init__(self, target_size_mb, codec, export_format="Original", audio_codec="copy", is_audio_only=False, resolution="Original", custom_name="", ai_config=None, parent=None):
        super().__init__(parent)
        self.target_size_mb = target_size_mb
        self.codec = codec
        self.export_format = export_format
        self.audio_codec = audio_codec
        self.is_audio_only = is_audio_only
        self.resolution = resolution
        self.custom_name = custom_name
        self.ai_config = ai_config
        self.process = None
        self._task_queue = None

    @classmethod
    def from_task_queue(cls, task_list):
        """Create a CompressionThread from a list of task dicts."""
        thread = cls(
            target_size_mb=0, codec="", parent=None
        )
        thread._task_queue = list(task_list)
        return thread

    def run_audio_pass(self, file_path):
        import re
        file_path = Path(file_path)
        file_name = file_path.name
        v_len = get_video_length(file_path)

        total_steps = len(g.queue)
        current_step = len(g.completed)
        base_percentage = (current_step / total_steps) * 100
        self.update_progress.emit(int(base_percentage))
        
        status_msg = f"\n[Audio Encoding Status]\nFile: {file_name}\nQueue: {len(g.completed) + 1}/{len(g.queue)}\nPreset: {self.codec}\n"
        
        file_name_stem = file_path.stem
        original_ext = file_path.suffix.lstrip(".")
        
        out_ext = original_ext
        if self.export_format != "Original" and self.export_format:
            out_ext = self.export_format.lower().replace(".", "")
            
        if self.custom_name:
            out_name = self.custom_name
            if len(g.queue) > 1:
                out_name = f"{self.custom_name}_{len(g.completed) + 1}"
            output_path = Path(g.output_dir) / f"{out_name}.{out_ext}"
        else:
            output_path = Path(g.output_dir) / f"{file_name_stem}-compressed.{out_ext}"
        print(status_msg)

        cmd = [str(g.ffmpeg_path), "-i", str(file_path), "-y"]

        match self.codec:
            case c if "MP3" in c:
                cmd.extend(["-c:a", "libmp3lame"])
                if "128" in c: cmd.extend(["-b:a", "128k"])
                elif "192" in c: cmd.extend(["-b:a", "192k"])
                elif "320" in c: cmd.extend(["-b:a", "320k"])
            case c if "AAC" in c:
                cmd.extend(["-c:a", "aac"])
                if "128" in c: cmd.extend(["-b:a", "128k"])
                elif "192" in c: cmd.extend(["-b:a", "192k"])
                elif "256" in c: cmd.extend(["-b:a", "256k"])
            case c if "FLAC" in c:
                cmd.extend(["-c:a", "flac"])
            case c if "WAV" in c:
                cmd.extend(["-c:a", "pcm_s16le"])
            case c if "Copy" in c:
                cmd.extend(["-c:a", "copy"])
            case _:
                cmd.extend(["-c:a", "copy"])

        cmd.append(str(output_path))

        print(f"Running command: {' '.join(cmd)}")
        self.update_log.emit(status_msg)
        
        creation_flags = 0x08000000 if platform.system() == "Windows" else 0
        self.process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            universal_newlines=True, 
            creationflags=creation_flags
        )
        
        if self.process.stdout:
            for line in self.process.stdout:
                if not g.compressing:
                    self.process.terminate()
                    break
                print(line, end="")
                
                # Parse time=... for real-time progress
                match = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", line)
                if match and v_len > 0:
                    h, m, s = map(float, match.groups())
                    current_time = h * 3600 + m * 60 + s
                    pass_progress = min(1.0, current_time / v_len)
                    current_percentage = base_percentage + (pass_progress * 100 / total_steps)
                    self.update_progress.emit(int(current_percentage))
                    # Optionally update the log with the time string if desired
                    
        self.process.wait()

    def run_pass(self, file_path):
        import re
        file_path = Path(file_path)
        v_len = get_video_length(file_path)
        video_rate = calculate_video_bitrate(file_path, self.target_size_mb)
        metadata = get_video_metadata(file_path)
        pix_fmt = metadata.get("pix_fmt", "unknown")
        file_name = file_path.name

        pure_codec = self.codec.split(" ")[0]
        is_hw_encoder = any(hw in pure_codec for hw in ["nvenc", "amf", "qsv", "vaapi"])
        is_lossless = pure_codec == "ffv1"

        orig_depth = metadata.get("depth", "Unknown")
        target_depth = orig_depth
        if is_hw_encoder and "10" in pix_fmt and "(Standard 8-bit)" in self.codec:
            target_depth = "8-bit (Converted for compatibility)"

        # Resolution scaling logic
        orig_width = metadata.get("width")
        orig_height = metadata.get("height")
        try:
            orig_width = int(orig_width) if orig_width else 0
            orig_height = int(orig_height) if orig_height else 0
        except ValueError:
            orig_width = orig_height = 0

        target_res = None
        if self.resolution != "Original":
            match = re.search(r"(\d+)p", self.resolution)
            if match:
                target_res = int(match.group(1))

        vf_filters = []
        if target_res:
            if orig_width > 0 and orig_height > 0:
                if orig_width >= orig_height:
                    # Landscape: target_res is height (e.g. 1080p -> height=1080)
                    vf_filters.append(f"scale=-2:{target_res}")
                else:
                    # Portrait: target_res is width (e.g. 1080p vertical -> width=1080)
                    vf_filters.append(f"scale={target_res}:-2")
            else:
                # Fallback if original dimensions are unknown
                vf_filters.append(f"scale=-2:{target_res}")
        elif "qsv" in pure_codec:
            # HW codecs (like QSV) heavily require even pixel dimensions (mod-2)
            vf_filters.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")

        file_name_stem = file_path.stem
        original_ext = file_path.suffix.lstrip(".")
        
        out_ext = original_ext
        if self.export_format != "Original" and self.export_format:
            out_ext = self.export_format.lower().replace(".", "")
        
        # FFV1 only works in MKV/AVI containers
        if is_lossless and out_ext not in ["mkv", "avi"]:
            out_ext = "mkv"
                
        if self.custom_name:
            out_name = self.custom_name
            if len(g.queue) > 1:
                out_name = f"{self.custom_name}_{len(g.completed) + 1}"
            output_path = Path(g.output_dir) / f"{out_name}.{out_ext}"
        else:
            output_path = Path(g.output_dir) / f"{file_name_stem}-compressed.{out_ext}"

        # Hardware encoders, FFV1 and H.266 (VVC): single-pass
        # Software encoders (libx264, libx265, etc.): 2-pass for better quality
        if is_hw_encoder or is_lossless or pure_codec == "libvvenc":
            num_passes = 1
        else:
            num_passes = 2

        for i in range(num_passes):
            total_steps = len(g.queue) * num_passes
            current_step = (len(g.completed) * num_passes) + i
            base_percentage = (current_step / total_steps) * 100
            self.update_progress.emit(int(base_percentage))
            
            encoder_mode = "Quality (1-pass)" if is_hw_encoder or pure_codec == "libvvenc" else ("Lossless" if is_lossless else f"Pass {i + 1}/2")
            status_msg = f"\n[Compression Status]\nFile: {file_name}\nQueue: {len(g.completed) + 1}/{len(g.queue)}\nMode: {encoder_mode}\nTarget Size: {self.target_size_mb}MB\nBitrate: {video_rate}k\nEncoder: {self.codec}\nDepth: {orig_depth} -> {target_depth}\n"

            bitrate_str = f"{video_rate}k"

            print(status_msg)

            cmd = [str(g.ffmpeg_path), "-y"]
            
            # libvvenc often requires experimental flag
            if pure_codec == "libvvenc":
                cmd.extend(["-strict", "experimental"])
                
            cmd.extend(["-i", str(file_path)])

            if is_lossless:
                # FFV1: lossless codec, no bitrate control needed
                cmd.extend(["-c:v", "ffv1", "-level", "3", "-slicecrc", "1"])
            elif is_hw_encoder:
                # Hardware encoders: single-pass with target bitrate
                cmd.extend(["-c:v", pure_codec, "-b:v", bitrate_str])
                
                # Add quality-based encoding hints for each HW family
                if "qsv" in pure_codec:
                    cmd.extend(["-preset", "medium"])
                elif "nvenc" in pure_codec:
                    cmd.extend(["-preset", "p4", "-tune", "hq"])
                elif "amf" in pure_codec:
                    cmd.extend(["-quality", "balanced"])
            else:
                # Software encoders: 2-pass encoding
                cmd.extend(["-b:v", bitrate_str, "-c:v", pure_codec])

            if "vaapi" in pure_codec and platform.system() == "Linux":
                cmd[1:1] = ["-hwaccel", "vaapi", "-hwaccel_output_format", "vaapi", "-vaapi_device", "/dev/dri/renderD128"]

            if vf_filters:
                cmd.extend(["-vf", ",".join(vf_filters)])

            # Pixel format handling
            if not is_lossless:
                match self.codec:
                    case c if "(Modern 10-bit)" in c:
                        cmd.extend(["-pix_fmt", "p010le"])
                    case c if "(Standard 8-bit)" in c:
                        fmt = "nv12" if "qsv" in pure_codec else "yuv420p"
                        cmd.extend(["-pix_fmt", fmt])

            if is_hw_encoder or is_lossless:
                # Single-pass: output directly
                # Audio handling
                match self.audio_codec:
                    case "none": cmd.append("-an")
                    case "copy": cmd.extend(["-c:a", "copy"])
                    case "aac": cmd.extend(["-c:a", "aac", "-b:a", "192k"])
                    case "mp3": cmd.extend(["-c:a", "libmp3lame", "-b:a", "192k"])
                    case "opus": cmd.extend(["-c:a", "libopus", "-b:a", "128k"])
                    case "flac": cmd.extend(["-c:a", "flac"])
                    case _: cmd.extend(["-c:a", "copy"])
                cmd.append(str(output_path))
            else:
                passlogfile_path = str(Path(g.output_dir) / f"{file_name_stem}_passlog")
                cmd.extend(["-passlogfile", passlogfile_path])
                # 2-pass encoding for software codecs
                if i == 0:
                    cmd.extend(["-an", "-pass", "1", "-f", "null", os.devnull])
                else:
                    match self.audio_codec:
                        case "none": cmd.append("-an")
                        case "copy": cmd.extend(["-c:a", "copy"])
                        case "aac": cmd.extend(["-c:a", "aac", "-b:a", "192k"])
                        case "mp3": cmd.extend(["-c:a", "libmp3lame", "-b:a", "192k"])
                        case "opus": cmd.extend(["-c:a", "libopus", "-b:a", "128k"])
                        case "flac": cmd.extend(["-c:a", "flac"])
                        case _: cmd.extend(["-c:a", "copy"])
                    
                    cmd.extend(["-pass", "2", str(output_path)])

            cmd_str = ' '.join(f'"{c}"' if ' ' in str(c) else str(c) for c in cmd)
            print(f"FULL CMD: {cmd_str}")
            self.update_log.emit(status_msg)
            
            creation_flags = 0x08000000 if platform.system() == "Windows" else 0
            self.process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                universal_newlines=True, 
                creationflags=creation_flags
            )
            
            last_lines = []
            if self.process.stdout:
                for line in self.process.stdout:
                    if not g.compressing:
                        self.process.terminate()
                        break
                    line_stripped = line.strip()
                    if line_stripped:
                        last_lines.append(line_stripped)
                        if len(last_lines) > 10:
                            last_lines.pop(0)
                    
                    # Parse time=... for real-time progress
                    match = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", line)
                    if match and v_len > 0:
                        h, m, s = map(float, match.groups())
                        current_time = h * 3600 + m * 60 + s
                        pass_progress = min(1.0, current_time / v_len)
                        current_percentage = base_percentage + (pass_progress * 100 / total_steps)
                        self.update_progress.emit(int(current_percentage))
                        
            self.process.wait()
            if self.process.returncode != 0:
                error_detail = "\n".join(last_lines[-5:]) if last_lines else "Unknown error"
                print(f"FFmpeg ERROR output:\n{error_detail}")
                raise Exception(f"FFmpeg error: {error_detail}")
            
            # Clean up pass log files after successful pass 2
            if not is_hw_encoder and not is_lossless and i == 1:
                try:
                    for suffix in [".log", ".log.mbtree"]:
                        p = Path(f"{passlogfile_path}-0{suffix}")
                        if p.exists():
                            p.unlink()
                except Exception as e:
                    print(f"Error cleaning up passlogs: {e}")

    def run_ai_processing(self, file_path):
        """Run AI processing pipeline if enabled. Returns path to processed video for encoding."""
        if not self.ai_config or not self.ai_config.get("mode") or self.ai_config["mode"] == "Disabled":
            return file_path

        from src.ai_tools import (
            AIProcessor, UPSCALE_MODELS, INTERPOLATION_MODELS, COLORIZE_MODELS,
            extract_frames, encode_from_frames, extract_audio,
            get_video_fps, count_frames, cleanup_temp, mux_audio,
        )

        file_path = Path(file_path)
        temp_base = Path(g.output_dir) / ".ai_temp"
        temp_base.mkdir(exist_ok=True)

        frames_dir = temp_base / "frames"
        colorized_dir = temp_base / "colorized"
        upscaled_dir = temp_base / "upscaled"
        interpolated_dir = temp_base / "interpolated"
        audio_path = temp_base / "audio.m4a"
        intermediate_video = temp_base / "intermediate.mp4"

        # Get user-defined order (default: colorize -> upscale -> interpolate)
        ai_order = self.ai_config.get("ai_order", ["colorize", "upscale", "interpolate"])

        try:
            # 1. Extract frames
            self.update_log.emit("[AI] Extracting frames...")
            extract_frames(file_path, frames_dir)

            original_fps = get_video_fps(file_path)
            current_frames_dir = frames_dir
            current_fps = original_fps

            # 2. Run AI steps in user-defined order
            for step in ai_order:
                if not g.compressing:
                    break

                if step == "colorize" and self.ai_config.get("colorize_enabled"):
                    render_factor = self.ai_config.get("colorize_render_factor", 256)
                    colorize_model = self.ai_config.get("colorize_model", "deoldify-artistic")
                    colorize_device = self.ai_config.get("colorize_device")  # None=auto, -1=cpu, 0,1,2=gpu
                    self.update_log.emit(f"[AI] Colorizing: {colorize_model} (render_factor={render_factor})")

                    from src.ai_tools import DeOldifyProcessor
                    processor = DeOldifyProcessor(self.update_log.emit, self.update_progress.emit)
                    processor.colorize_frames(current_frames_dir, colorized_dir, render_factor, model_key=colorize_model, device=colorize_device)
                    current_frames_dir = colorized_dir

                elif step == "upscale" and "Upscale" in self.ai_config.get("mode", ""):
                    model_key = self.ai_config.get("upscale_model", "realesrgan-x4plus")
                    scale = self.ai_config.get("upscale_scale", 4)
                    upscale_device = self.ai_config.get("upscale_device")  # None=auto, -1=cpu, 0,1,2=gpu

                    model_info = UPSCALE_MODELS.get(model_key, {})
                    self.update_log.emit(f"[AI] Upscaling: {model_info.get('name', model_key)} x{scale}")

                    processor = AIProcessor(self.update_log.emit, self.update_progress.emit)
                    processor.upscale_frames(current_frames_dir, upscaled_dir, model_key, scale, gpu_id=upscale_device)
                    current_frames_dir = upscaled_dir

                elif step == "interpolate" and "Interpolation" in self.ai_config.get("mode", ""):
                    model_key = self.ai_config.get("interp_model", "rife-v4")
                    multiplier = self.ai_config.get("interp_multiplier", 2)
                    interp_device = self.ai_config.get("interp_device")  # None=auto, -1=cpu, 0,1,2=gpu

                    model_info = INTERPOLATION_MODELS.get(model_key, {})
                    self.update_log.emit(f"[AI] Interpolating: {model_info.get('name', model_key)} x{multiplier}")

                    processor = AIProcessor(self.update_log.emit, self.update_progress.emit)
                    processor.interpolate_frames(current_frames_dir, interpolated_dir, model_key, multiplier, gpu_id=interp_device)
                    current_frames_dir = interpolated_dir
                    current_fps = original_fps * multiplier

            # 5. Extract audio
            from src.ai_tools import has_audio_stream
            has_audio = has_audio_stream(file_path)
            if has_audio:
                self.update_log.emit("[AI] Extracting audio...")
                extract_audio(file_path, audio_path)
            else:
                self.update_log.emit("[AI] No audio track found, skipping audio extraction.")

            # 6. Encode intermediate video from processed frames
            self.update_log.emit("[AI] Encoding processed video...")
            encode_from_frames(current_frames_dir, intermediate_video, current_fps)

            # 7. Mux audio back (if we have audio)
            if has_audio:
                final_output = temp_base / "final_with_audio.mp4"
                mux_audio(intermediate_video, audio_path, final_output)
            else:
                final_output = intermediate_video

            self.update_log.emit("[AI] Processing complete. Continuing with compression...")
            return str(final_output)

        except Exception as e:
            self.error_msg.emit(f"AI processing failed: {str(e)[:200]}")
            raise

    def run(self):
        g.completed = []
        try:
            if self._task_queue:
                self._run_task_queue()
            else:
                self._run_legacy()
        except Exception as e:
            error_text = str(e)
            display_error = error_text[:200] if len(error_text) > 200 else error_text
            self.error_msg.emit(f"❌ {display_error}")
            msg = f"Error during compression: {e}"
            print(msg)
            g.compressing = False
        finally:
            self._cleanup_ai_temp()

        print("Done" if g.compressing else "Aborted")
        self.completed.emit()

    def _run_task_queue(self):
        """Process all tasks from the task queue."""
        total_tasks = len(self._task_queue)
        for task_idx, task in enumerate(self._task_queue):
            if not g.compressing:
                break

            self.task_started.emit(task["id"])

            # Apply task settings to self
            pipeline = task.get("pipeline", {})
            compress = pipeline.get("compress", {})
            self.target_size_mb = compress.get("size_mb", 20)
            self.codec = compress.get("codec", "libx264")
            self.export_format = compress.get("export_format", "Original")
            self.audio_codec = compress.get("audio_codec", "copy")
            self.is_audio_only = task.get("is_audio_only", False)
            self.resolution = compress.get("resolution", "Original")
            self.custom_name = compress.get("custom_name", "")

            # Build AI config from pipeline
            self.ai_config = None
            ai_parts = []
            if pipeline.get("upscale", {}).get("enabled"):
                ai_parts.append("Upscale")
            if pipeline.get("interpolate", {}).get("enabled"):
                ai_parts.append("Interpolation")
            if pipeline.get("colorize", {}).get("enabled"):
                ai_parts.append("Colorize")

            if ai_parts:
                self.ai_config = {"mode": " + ".join(ai_parts)}
                self.ai_config["ai_order"] = task.get("ai_order", ["colorize", "upscale", "interpolate"])
                if pipeline.get("colorize", {}).get("enabled"):
                    self.ai_config["colorize_enabled"] = True
                    self.ai_config["colorize_model"] = pipeline["colorize"].get("model", "deoldify-artistic")
                    self.ai_config["colorize_render_factor"] = pipeline["colorize"].get("render_factor", 256)
                if pipeline.get("upscale", {}).get("enabled"):
                    self.ai_config["upscale_model"] = pipeline["upscale"].get("model", "realesrgan-x4plus")
                    self.ai_config["upscale_scale"] = pipeline["upscale"].get("scale", 2)
                if pipeline.get("interpolate", {}).get("enabled"):
                    self.ai_config["interp_model"] = pipeline["interpolate"].get("model", "rife-v4.6")
                    self.ai_config["interp_multiplier"] = pipeline["interpolate"].get("multiplier", 2)

            # Set output dir
            g.output_dir = task.get("output_dir", g.output_dir)

            self.update_log.emit(f"Task {task_idx + 1}/{total_tasks}: Processing {len(task['source_files'])} file(s)...")

            for file_path in task["source_files"]:
                if not g.compressing:
                    break
                if self.is_audio_only:
                    self.run_audio_pass(file_path)
                else:
                    processed_path = self.run_ai_processing(file_path)
                    self.run_pass(processed_path)
                    self._cleanup_ai_temp()
                g.completed.append(file_path)

        msg = f"Completed {len(g.completed)} file(s)!" if g.compressing else "Aborted!"
        self.update_log.emit(msg)

    def _run_legacy(self):
        """Legacy mode: process files from g.queue."""
        for file_path in g.queue:
            if not g.compressing:
                break
            if self.is_audio_only:
                self.run_audio_pass(file_path)
            else:
                processed_path = self.run_ai_processing(file_path)
                self.run_pass(processed_path)
                self._cleanup_ai_temp()
            g.completed.append(file_path)
        msg = f"Compressed {len(g.completed)} video(s)!" if g.compressing else "Aborted!"
        self.update_log.emit(msg)

    def _cleanup_ai_temp(self):
        """Remove AI temporary directory."""
        import shutil
        temp_base = Path(g.output_dir) / ".ai_temp"
        if temp_base.exists():
            try:
                shutil.rmtree(temp_base, ignore_errors=True)
            except Exception:
                pass
