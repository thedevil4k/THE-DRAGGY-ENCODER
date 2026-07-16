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


def predict_compression(file_path, mode, target_size_mb, target_bitrate_kbps,
                        codec, audio_codec, resolution, audio_boost,
                        trim_enabled=False, trim_start_s=0.0,
                        trim_end_s=None):
    """Pure function that mirrors run_pass decision tree (lines ~714-776 and
    650-653).  Returns a dict with the predicted outcome WITHOUT running any
    re-encoding.  Keep in sync with run_pass if that logic changes.
    """
    full_duration = get_video_length(file_path)
    source_meta = get_video_metadata(file_path)
    source_audio_rate = 0
    try:
        source_audio_rate = get_audio_bitrate(file_path)
    except Exception:
        source_audio_rate = 0
    source_size_bytes = 0
    try:
        import os
        source_size_bytes = os.path.getsize(file_path)
    except Exception:
        pass

    audio_rates = {
        "aac": 192,
        "mp3": 192,
        "opus": 128,
        "flac": None,
        "copy": source_audio_rate,
        "none": 0,
    }
    a_rate = audio_rates.get(audio_codec, source_audio_rate)

    is_remux = codec == "Copy (Remux)"
    is_hw = any(hw in codec for hw in ["nvenc", "amf", "qsv", "vaapi"])
    is_lossless = codec == "ffv1"
    pure_codec = codec.split(" ")[0] if not is_remux else "copy"
    is_crf = (not is_hw and not is_lossless and pure_codec != "libvvenc"
              and mode != "bitrate" and not is_remux)

    # ── Trim handling ────────────────────────────────────────────────
    eff_start = float(trim_start_s or 0.0)
    eff_end = (float(trim_end_s)
               if (trim_enabled and trim_end_s is not None)
               else full_duration)
    if trim_enabled:
        eff_end = min(eff_end, full_duration)
        if eff_end < eff_start:
            eff_end = full_duration
    seg_len = max(0.0, eff_end - eff_start) if trim_enabled else full_duration
    if seg_len <= 0.05:
        seg_len = full_duration
        trim_active = False
    else:
        trim_active = trim_enabled
    duration = seg_len if trim_active else full_duration

    warnings = []

    if is_remux:
        algorithm = "Remux (copy, sin re-codificación)"
        estimated_size_mb = source_size_bytes / (1024 * 1024)
        video_rate = 0
        warnings.append("ℹ Copy (Remux) no re-codifica video ni audio.")
    elif mode == "size":
        total_budget = (target_size_mb * 8192.0 * 0.98) / (1.048576 * max(1, duration))
        if a_rate:
            video_rate = max(1, round(total_budget - a_rate))
        else:
            video_rate = max(1, round(total_budget))
        estimated_size_mb = target_size_mb
        if is_hw or is_lossless:
            algorithm = "1-pass HW" if is_hw else "1-pass lossless"
        elif is_crf:
            algorithm = "1-pass CRF (calidad fija, tamaño aproximado)"
            warnings.append("⚠ El modo 'Tamaño objetivo' con codec software usa CRF.")
            warnings.append("⚠ El tamaño final puede variar significativamente.")
        else:
            algorithm = "2-pass SW (tamaño/bitrate preciso)"
    else:
        video_rate = target_bitrate_kbps
        total_rate = video_rate + (a_rate or 0)
        estimated_size_mb = (total_rate * max(1, duration)) / 8192.0
        if is_hw or is_lossless:
            algorithm = "1-pass HW" if is_hw else "1-pass lossless"
        else:
            algorithm = "2-pass SW (tamaño/bitrate preciso)"

    output_resolution = resolution
    if resolution != "Original" and not is_remux:
        resolutions_map = {
            "4K (2160p)": "3840x2160",
            "1440p (QHD)": "2560x1440",
            "1080p (FHD)": "1920x1080",
            "720p (HD)": "1280x720",
            "480p (SD)": "854x480",
            "360p": "640x360",
        }
        output_resolution = resolutions_map.get(resolution, resolution)
        warnings.append(f"ℹ Escalado a {output_resolution}.")

    if audio_codec == "none" and not is_remux:
        warnings.append("ℹ Sin audio (-an).")
    elif audio_boost and audio_codec not in ("copy", "none"):
        warnings.append("ℹ Filtro audio: loudnorm=I=-14:TP=-1:LRA=11 (EBU R128).")
    elif audio_boost and audio_codec in ("copy", "none"):
        warnings.append("⚠ Audio Boost deshabilitado (codec audio no permite filtros).")

    if trim_active:
        warnings.append(
            f"✂ Trim aplicado: {format_seconds(eff_start)} → {format_seconds(eff_end)} "
            f"(duración efectiva {format_seconds(seg_len)})."
        )

    return {
        "source_resolution": source_meta.get("resolution", "Unknown"),
        "output_resolution": output_resolution,
        "source_codec": source_meta.get("codec", "Unknown"),
        "codec": "copy" if is_remux else pure_codec,
        "video_bitrate_kbps": video_rate,
        "audio_codec": audio_codec,
        "audio_bitrate_kbps": a_rate,
        "audio_boost": audio_boost,
        "estimated_size_mb": round(estimated_size_mb, 2),
        "algorithm": algorithm,
        "warnings": warnings,
        "duration_seconds": duration,
        "full_duration_seconds": full_duration,
        "trim_active": trim_active,
        "trim_start_s": eff_start,
        "trim_end_s": eff_end,
        "source_size_bytes": source_size_bytes,
    }


def format_seconds(s):
    """Format seconds as h:mm:ss / mm:ss."""
    if s is None:
        return "?"
    s = max(0.0, float(s))
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = s - h * 3600 - m * 60
    if h > 0:
        return f"{h}:{m:02d}:{int(sec):02d}"
    return f"{m:02d}:{int(sec):02d}"


def is_encoder_supported(encoder_name, pix_fmt=None):
    """
    Probe whether the installed FFmpeg can really encode with the given encoder.

    Returns:
        status: "pass" | "inconclusive" | "missing"
        reason: human readable string when not "pass"

    Three-state semantics:
        "pass"         - test encode succeeded (rc==0)
        "inconclusive" - FFmpeg advertises the encoder but the short probe
                          failed (often cold-init / driver-compat). Could still
                          work with a real input. We do NOT exclude these.
        "missing"      - FFmpeg does not list the encoder at all.
    """
    try:
        cmd = [
            str(g.ffmpeg_path),
            "-v", "error",
            "-f", "lavfi",
            "-i", "color=c=black:s=640x360:d=1",
            "-c:v", encoder_name,
            "-frames:v", "5",
        ]

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
            "timeout": 30,
        }
        if platform.system() == "Windows":
            kwargs["creationflags"] = 0x08000000

        result = subprocess.run(cmd, **kwargs)

        if result.returncode == 0:
            return "pass", ""

        stderr_text = result.stderr.decode("utf-8", errors="ignore") if result.stderr else ""
        reason = stderr_text[:400] if stderr_text else f"return code {result.returncode}"
        print(f"  Encoder {encoder_name} probe inconclusive: {reason[:200]}")
        return "inconclusive", reason

    except subprocess.TimeoutExpired:
        print(f"  Encoder {encoder_name} probe timed out")
        return "inconclusive", "Probe timed out (cold driver init?)"
    except Exception as e:
        print(f"  Encoder {encoder_name} probe error: {e}")
        return "inconclusive", str(e)


def get_available_encoders():
    """Detects available video encoders from ffmpeg.
    
    Each hardware encoder is tested with a quality-based encode to verify
    real hardware support. Software encoders are assumed available if present.
    """
    print("  get_available_encoders start")
    try:
        cmd = [str(g.ffmpeg_path), "-hide_banner", "-encoders"]
        print(f"  Running: {' '.join(cmd)}")
        kwargs = {"text": True, "encoding": "utf-8", "errors": "replace"}
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
        
        # Build the final list. Honest policy:
        #   - software encoders (libx264, libx265, ...): always include if
        #     present in ffmpeg binary.
        #   - HW encoders: ALWAYS include if ffmpeg exposes them. Mark
        #     pass/inconclusive with a suffix so UI can display the truth.
        encoders = []
        encoder_errors = {}
        for name in hardware_priority:
            if name in all_video_encoders:
                if any(hw in name for hw in ["nvenc", "amf", "qsv", "vaapi"]):
                    status8, reason8 = is_encoder_supported(name)
                    status10, _ = is_encoder_supported(name, "p010le")
                    if status8 == "pass":
                        encoders.append(f"{name} (Standard 8-bit)")
                        if status10 == "pass":
                            encoders.append(f"{name} (Modern 10-bit)")
                    elif status8 == "inconclusive":
                        # Keep the encoder visible; user may still try it.
                        encoder_errors[name] = ("inconclusive", reason8)
                        encoders.append(f"{name} (Standard 8-bit) ⚠")
                        if status10 == "pass":
                            encoders.append(f"{name} (Modern 10-bit)")
                        elif status10 == "inconclusive":
                            encoders.append(f"{name} (Modern 10-bit) ⚠")
                    else:
                        encoder_errors[name] = ("missing", reason8)
                else:
                    encoders.append(name)
            else:
                if any(hw in name for hw in ["nvenc", "amf", "qsv", "vaapi"]):
                    encoder_errors[name] = ("missing", "FFmpeg binary does not advertise this encoder")

        if not encoders:
            encoders = ["libx264"]

        g.encoder_errors = encoder_errors
        return encoders
    except Exception as e:
        print(f"Error getting encoders: {e}")
        return ["libx264"]


def get_hardware_info():
    """Detects CPU and GPU information, including VRAM and native codec support for each GPU."""
    print("  get_hardware_info start")
    info = {"cpu": "Unknown CPU", "gpus": [], "gpu_details": []}
    
    # 1. Detect CPU
    try:
        if platform.system() == "Windows":
            creation_flags = 0x08000000  # CREATE_NO_WINDOW
            cpu_cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-Command", "Get-CimInstance Win32_Processor | Select-Object -ExpandProperty Name"]
            cpu_output = subprocess.check_output(cpu_cmd, text=True, encoding="utf-8", errors="replace", creationflags=creation_flags).strip()
            if cpu_output:
                info["cpu"] = cpu_output
        else:
            try:
                with open("/proc/cpuinfo", "r") as f:
                    for line in f:
                        if line.startswith("model name"):
                            info["cpu"] = line.split(":")[1].strip()
                            break
            except:
                pass
    except Exception as e:
        print(f"Error detecting CPU: {e}")

    # 2. Detect GPUs
    try:
        from src.ai_tools import detect_gpu_devices
        gpu_list = detect_gpu_devices()
    except Exception as e:
        print(f"Error running detect_gpu_devices: {e}")
        gpu_list = []

    # 3. Get all video encoders available in FFmpeg binary
    ffmpeg_encoders = []
    try:
        cmd = [str(g.ffmpeg_path), "-hide_banner", "-encoders"]
        kwargs = {"text": True, "encoding": "utf-8", "errors": "replace"}
        if platform.system() == "Windows":
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        output = subprocess.check_output(cmd, **kwargs)
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
                    ffmpeg_encoders.append(parts[1])
    except Exception as e:
        print(f"Error getting ffmpeg encoders: {e}")

    # 4. Map and test codecs per GPU
    for gpu in gpu_list:
        vendor = gpu.get("vendor", "Other").upper()
        gpu_type = gpu.get("type", "dedicated")
        
        # Determine candidate encoders based on GPU brand/type
        candidates = []
        if vendor == "NVIDIA":
            candidates = ["h264_nvenc", "hevc_nvenc", "av1_nvenc"]
        elif vendor == "INTEL":
            candidates = ["h264_qsv", "hevc_qsv", "av1_qsv"]
        elif vendor == "AMD":
            candidates = ["h264_amf", "hevc_amf", "av1_amf"]
            
        # Add VAAPI candidates as fallback or for Linux
        candidates.extend(["h264_vaapi", "hevc_vaapi", "av1_vaapi"])
        candidates = list(dict.fromkeys(candidates)) # Remove duplicates
        
        supported = []
        for codec in candidates:
            if codec in ffmpeg_encoders:
                status8, _ = is_encoder_supported(codec)
                status10, _ = is_encoder_supported(codec, "p010le")
                if status8 in ("pass", "inconclusive"):
                    codec_details = {"name": codec, "profiles": ["8-bit"], "status": status8}
                    if status10 in ("pass", "inconclusive"):
                        codec_details["profiles"].append("10-bit")
                    supported.append(codec_details)
                    
        gpu["supported_codecs"] = supported
        info["gpu_details"].append(gpu)
        info["gpus"].append(gpu["name"])
        
    return info


class CompressionThread(QThread):
    update_log = Signal(str)
    update_progress = Signal(int)
    error_msg = Signal(str)
    completed = Signal()
    task_started = Signal(int)

    def __init__(self, target_size_mb, codec, export_format="Original", audio_codec="copy", is_audio_only=False, resolution="Original", custom_name="", ai_config=None, audio_boost=False, compression_mode="size", target_bitrate_kbps=0, parent=None, trim_enabled=False, trim_start_s=0.0, trim_end_s=None):
        super().__init__(parent)
        self.target_size_mb = target_size_mb
        self.codec = codec
        self.export_format = export_format
        self.audio_codec = audio_codec
        self.is_audio_only = is_audio_only
        self.resolution = resolution
        self.custom_name = custom_name
        self.ai_config = ai_config
        self.audio_boost = audio_boost
        self.compression_mode = compression_mode
        self.target_bitrate_kbps = target_bitrate_kbps
        self.process = None
        self._task_queue = None
        self.trim_enabled = bool(trim_enabled)
        self.trim_start_s = max(0.0, float(trim_start_s or 0.0))
        self.trim_end_s = (None if trim_end_s in (None, "")
                            else max(0.0,
                                     float(trim_end_s)))
        if self.trim_enabled and self.trim_end_s is not None:
            if self.trim_end_s <= self.trim_start_s:
                print(
                    "Trim end ≤ start; ignoring trim range."
                )
                self.trim_enabled = False
        # Defensive: Audio Boost cannot be applied when the chosen audio
        # strategy is "copy" or "none", because the loudnorm filter requires
        # an actual re-encoded audio stream. Auto-disable with a log so the
        # user is never silently misled.
        if self.audio_boost and self.audio_codec in ("copy", "none"):
            print(
                "Audio Boost requested but Audio codec is "
                f"'{self.audio_codec}'. Auto-disabling Audio Boost "
                "(loudnorm requires re-encoded audio)."
            )
            self.audio_boost = False

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
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation_flags
        )

        if self.process.stdout:
            for line in self.process.stdout:
                if not g.compressing:
                    self.process.terminate()
                    break
                try:
                    print(line, end="", flush=True)
                except UnicodeEncodeError:
                    safe = line.encode("ascii", errors="replace").decode("ascii")
                    print(safe, end="", flush=True)
                
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
        metadata = get_video_metadata(file_path)
        pix_fmt = metadata.get("pix_fmt", "unknown")
        file_name = file_path.name

        pure_codec = self.codec.split(" ")[0]
        is_remux = pure_codec == "Copy"

        # ── Trim handling ────────────────────────────────────────────────
        # If trim is enabled, override the effective length used for
        # progress computation. Real encoding time is small either way.
        trim_active = self.trim_enabled
        trim_start = self.trim_start_s if trim_active else 0.0
        trim_end = self.trim_end_s if trim_active else None
        if trim_active:
            if trim_end is None or trim_end > v_len:
                trim_end = v_len
            seg_len = max(0.0, trim_end - trim_start)
            if seg_len <= 0.05:
                print(
                    f"Trim range {trim_start:.2f}-{trim_end:.2f} is empty; "
                    "skipping trim.")
                trim_active = False
        seg_len = (trim_end - trim_start) if trim_active else v_len
        eff_v_len = seg_len if trim_active else v_len
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

        if is_remux:
            total_steps = len(g.queue)
            current_step = len(g.completed)
            base_percentage = (current_step / total_steps) * 100
            self.update_progress.emit(int(base_percentage))

            status_msg = f"\n[Remux Status]\nFile: {file_name}\nQueue: {len(g.completed) + 1}/{len(g.queue)}\nMode: Copy (Remux)\nTarget: {out_ext.upper()}\n"
            print(status_msg)
            self.update_log.emit(status_msg)

            cmd = [str(g.ffmpeg_path), "-y"]
            if trim_active:
                cmd.extend(["-ss", f"{trim_start:.3f}"])
            cmd.extend(["-i", str(file_path)])
            if trim_active:
                cmd.extend(["-t", f"{seg_len:.3f}"])
            cmd.extend(["-c:v", "copy"])

            match self.audio_codec:
                case "none": cmd.append("-an")
                case "copy": cmd.extend(["-c:a", "copy"])
                case "aac":
                    if self.audio_boost:
                        cmd.extend(["-af", "loudnorm=I=-14:TP=-1:LRA=11", "-c:a", "aac", "-b:a", "192k"])
                    else:
                        cmd.extend(["-c:a", "aac", "-b:a", "192k"])
                case "mp3":
                    if self.audio_boost:
                        cmd.extend(["-af", "loudnorm=I=-14:TP=-1:LRA=11", "-c:a", "libmp3lame", "-b:a", "192k"])
                    else:
                        cmd.extend(["-c:a", "libmp3lame", "-b:a", "192k"])
                case "opus":
                    if self.audio_boost:
                        cmd.extend(["-af", "loudnorm=I=-14:TP=-1:LRA=11", "-c:a", "libopus", "-b:a", "128k"])
                    else:
                        cmd.extend(["-c:a", "libopus", "-b:a", "128k"])
                case "flac":
                    if self.audio_boost:
                        cmd.extend(["-af", "loudnorm=I=-14:TP=-1:LRA=11", "-c:a", "flac"])
                    else:
                        cmd.extend(["-c:a", "flac"])
                case _: cmd.extend(["-c:a", "copy"])

            cmd.append(str(output_path))

            cmd_str = ' '.join(f'"{c}"' if ' ' in str(c) else str(c) for c in cmd)
            print(f"FULL CMD: {cmd_str}")

            creation_flags = 0x08000000 if platform.system() == "Windows" else 0
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
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
                    match = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", line)
                    if match and eff_v_len > 0:
                        h, m, s = map(float, match.groups())
                        current_time = h * 3600 + m * 60 + s
                        pass_progress = min(1.0, current_time / eff_v_len)
                        current_percentage = base_percentage + (pass_progress * 100 / total_steps)
                        self.update_progress.emit(int(current_percentage))

            self.process.wait()
            if self.process.returncode != 0:
                error_detail = "\n".join(last_lines[-5:]) if last_lines else "Unknown error"
                print(f"FFmpeg ERROR output:\n{error_detail}")
                raise Exception(f"FFmpeg error: {error_detail}")
            return
        if self.compression_mode == "bitrate":
            video_rate = self.target_bitrate_kbps
        else:
            video_rate = calculate_video_bitrate(file_path, self.target_size_mb)
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
        
        if is_lossless and out_ext not in ["mkv", "avi"]:
            out_ext = "mkv"
                
        if self.custom_name:
            out_name = self.custom_name
            if len(g.queue) > 1:
                out_name = f"{self.custom_name}_{len(g.completed) + 1}"
            output_path = Path(g.output_dir) / f"{out_name}.{out_ext}"
        else:
            output_path = Path(g.output_dir) / f"{file_name_stem}-compressed.{out_ext}"

        # Software encoders (libx264, libx265, etc.):
        # - If user explicitly chose bitrate mode: 2-pass target bitrate
        # - Otherwise (target-size or quality): single-pass CRF for much better quality/size ratio
        use_crf = (not is_hw_encoder and not is_lossless and pure_codec != "libvvenc" and self.compression_mode != "bitrate")
        if is_hw_encoder or is_lossless or pure_codec == "libvvenc":
            num_passes = 1
        elif use_crf:
            num_passes = 1
        else:
            num_passes = 2

        for i in range(num_passes):
            total_steps = len(g.queue) * num_passes
            current_step = (len(g.completed) * num_passes) + i
            base_percentage = (current_step / total_steps) * 100
            self.update_progress.emit(int(base_percentage))
            
            encoder_mode = "Quality (1-pass)" if is_hw_encoder or pure_codec == "libvvenc" else ("Lossless" if is_lossless else f"Pass {i + 1}/2")
            if self.compression_mode == "bitrate":
                status_msg = f"\n[Compression Status]\nFile: {file_name}\nQueue: {len(g.completed) + 1}/{len(g.queue)}\nMode: {encoder_mode}\nTarget Bitrate: {video_rate} kbps\nEncoder: {self.codec}\nDepth: {orig_depth} -> {target_depth}\n"
            else:
                status_msg = f"\n[Compression Status]\nFile: {file_name}\nQueue: {len(g.completed) + 1}/{len(g.queue)}\nMode: {encoder_mode}\nTarget Size: {self.target_size_mb}MB\nBitrate: {video_rate}k\nEncoder: {self.codec}\nDepth: {orig_depth} -> {target_depth}\n"

            bitrate_str = f"{video_rate}k"

            print(status_msg)

            cmd = [str(g.ffmpeg_path), "-y"]

            if trim_active:
                cmd.extend(["-ss", f"{trim_start:.3f}"])

            # libvvenc often requires experimental flag
            if pure_codec == "libvvenc":
                cmd.extend(["-strict", "experimental"])

            cmd.extend(["-i", str(file_path)])

            if trim_active:
                cmd.extend(["-t", f"{seg_len:.3f}"])

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
            elif use_crf:
                # Software encoders in CRF mode (single-pass quality-based)
                cmd.extend(["-c:v", pure_codec])
                crf_value = "23"
                if "libx265" in pure_codec:
                    cmd.extend(["-preset", "medium", "-crf", crf_value])
                elif "libx264" in pure_codec:
                    cmd.extend(["-preset", "medium", "-crf", crf_value])
                elif "libsvtav1" in pure_codec:
                    cmd.extend(["-preset", "6", "-crf", crf_value])
                elif "libaom-av1" in pure_codec:
                    cmd.extend(["-cpu-used", "4", "-crf", crf_value])
                else:
                    cmd.extend(["-b:v", bitrate_str])
            else:
                # Software encoders: 2-pass encoding with target bitrate
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

            if is_hw_encoder or is_lossless or use_crf:
                # Single-pass: output directly
                # Audio handling
                audio_boost_filter = "loudnorm=I=-14:TP=-1:LRA=11," if self.audio_boost else ""
                match self.audio_codec:
                    case "none": cmd.append("-an")
                    case "copy": cmd.extend(["-c:a", "copy"])
                    case "aac":
                        if self.audio_boost:
                            cmd.extend(["-af", audio_boost_filter.rstrip(","), "-c:a", "aac", "-b:a", "192k"])
                        else:
                            cmd.extend(["-c:a", "aac", "-b:a", "192k"])
                    case "mp3":
                        if self.audio_boost:
                            cmd.extend(["-af", audio_boost_filter.rstrip(","), "-c:a", "libmp3lame", "-b:a", "192k"])
                        else:
                            cmd.extend(["-c:a", "libmp3lame", "-b:a", "192k"])
                    case "opus":
                        if self.audio_boost:
                            cmd.extend(["-af", audio_boost_filter.rstrip(","), "-c:a", "libopus", "-b:a", "128k"])
                        else:
                            cmd.extend(["-c:a", "libopus", "-b:a", "128k"])
                    case "flac":
                        if self.audio_boost:
                            cmd.extend(["-af", audio_boost_filter.rstrip(","), "-c:a", "flac"])
                        else:
                            cmd.extend(["-c:a", "flac"])
                    case _: cmd.extend(["-c:a", "copy"])
                cmd.append(str(output_path))
            else:
                passlogfile_path = str(Path(g.output_dir) / f"{file_name_stem}_passlog")
                cmd.extend(["-passlogfile", passlogfile_path])
                # 2-pass encoding for software codecs
                if i == 0:
                    cmd.extend(["-an", "-pass", "1", "-f", "null", os.devnull])
                else:
                    audio_boost_filter = "loudnorm=I=-14:TP=-1:LRA=11," if self.audio_boost else ""
                    match self.audio_codec:
                        case "none": cmd.append("-an")
                        case "copy": cmd.extend(["-c:a", "copy"])
                        case "aac":
                            if self.audio_boost:
                                cmd.extend(["-af", audio_boost_filter.rstrip(","), "-c:a", "aac", "-b:a", "192k"])
                            else:
                                cmd.extend(["-c:a", "aac", "-b:a", "192k"])
                        case "mp3":
                            if self.audio_boost:
                                cmd.extend(["-af", audio_boost_filter.rstrip(","), "-c:a", "libmp3lame", "-b:a", "192k"])
                            else:
                                cmd.extend(["-c:a", "libmp3lame", "-b:a", "192k"])
                        case "opus":
                            if self.audio_boost:
                                cmd.extend(["-af", audio_boost_filter.rstrip(","), "-c:a", "libopus", "-b:a", "128k"])
                            else:
                                cmd.extend(["-c:a", "libopus", "-b:a", "128k"])
                        case "flac":
                            if self.audio_boost:
                                cmd.extend(["-af", audio_boost_filter.rstrip(","), "-c:a", "flac"])
                            else:
                                cmd.extend(["-c:a", "flac"])
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
                text=True,
                encoding="utf-8",
                errors="replace",
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
                    if match and eff_v_len > 0:
                        h, m, s = map(float, match.groups())
                        current_time = h * 3600 + m * 60 + s
                        pass_progress = min(1.0, current_time / eff_v_len)
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
        temp_base = Path(g.output_dir) / ".ai_temp" / file_path.stem
        temp_base.mkdir(parents=True, exist_ok=True)

        frames_dir = temp_base / "frames"
        colorized_dir = temp_base / "colorized"
        upscaled_dir = temp_base / "upscaled"
        interpolated_dir = temp_base / "interpolated"
        audio_path = temp_base / "audio.m4a"
        intermediate_video = temp_base / f"{file_path.stem}_intermediate.mp4"

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
        self.update_progress.emit(100)
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
            self.trim_enabled = bool(compress.get("trim_enabled", False))
            trim_start = compress.get("trim_start_s")
            trim_end = compress.get("trim_end_s")
            self.trim_start_s = max(0.0, float(trim_start or 0.0))
            self.trim_end_s = (None if trim_end in (None, "")
                                else max(0.0, float(trim_end)))
            if self.trim_enabled and self.trim_end_s is not None:
                if self.trim_end_s <= self.trim_start_s:
                    self.trim_enabled = False

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
            task_output_dir = task.get("output_dir", "")
            if task_output_dir:
                g.output_dir = task_output_dir

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


class PreviewThread(QThread):
    """Generates a 5-second mini-preview of a queued video.
    Extracts a short clip at a random timestamp, compresses it with the
    user's current settings, extracts one frame from the original and one
    from the compressed clip, and emits them as QPixmap-compatible PNGs.
    """
    info_ready = Signal(object)
    original_frame_ready = Signal(object)   # bytes of PNG
    compressed_frame_ready = Signal(object)  # bytes of PNG
    progress = Signal(int)
    failed = Signal(str)
    finished_ok = Signal(object)

    def __init__(self, file_path, mode, target_size_mb, target_bitrate_kbps,
                 codec, audio_codec, resolution, audio_boost, parent=None,
                 trim_enabled=False, trim_start_s=0.0, trim_end_s=None):
        super().__init__(parent)
        self.file_path = str(file_path)
        self.mode = mode
        self.target_size_mb = target_size_mb
        self.target_bitrate_kbps = target_bitrate_kbps
        self.codec = codec
        self.audio_codec = audio_codec
        self.resolution = resolution
        self.audio_boost = audio_boost and audio_codec not in ("copy", "none")
        self.trim_enabled = bool(trim_enabled)
        self.trim_start_s = max(0.0, float(trim_start_s or 0.0))
        self.trim_end_s = (None if trim_end_s in (None, "")
                            else max(0.0, float(trim_end_s)))
        self._tempfiles = []
        self._cancel = False

    def _tmp(self, suffix):
        import tempfile
        f = tempfile.NamedTemporaryFile(
            prefix="draggy_preview_", suffix=suffix, delete=False)
        f.close()
        self._tempfiles.append(f.name)
        return f.name

    def _cleanup(self):
        import os
        for p in self._tempfiles:
            try:
                os.unlink(p)
            except Exception:
                pass
        self._tempfiles.clear()

    def cleanup_tempfiles(self):
        """Called from the main thread after dialog close."""
        self._cleanup()

    def cancel(self):
        self._cancel = True

    def _run_ffmpeg(self, cmd):
        creation_flags = 0x08000000 if platform.system() == "Windows" else 0
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation_flags,
        )
        _, err = proc.communicate()
        return proc.returncode, err

    def run(self):
        try:
            self.progress.emit(10)
            info = predict_compression(
                self.file_path, self.mode, self.target_size_mb,
                self.target_bitrate_kbps, self.codec,
                self.audio_codec, self.resolution, self.audio_boost,
                trim_enabled=self.trim_enabled,
                trim_start_s=self.trim_start_s,
                trim_end_s=self.trim_end_s,
            )
            self.info_ready.emit(info)

            v_len = get_video_length(self.file_path)
            seg_lo = self.trim_start_s if self.trim_enabled else 0.0
            seg_hi = self.trim_end_s if (
                self.trim_enabled and self.trim_end_s is not None
            ) else v_len
            seg_hi = min(seg_hi, v_len)
            seg_len = max(0.0, seg_hi - seg_lo)
            if seg_len <= 0.5:
                seg_lo = 0.0
                seg_hi = v_len
                seg_len = v_len

            if seg_len <= 6:
                seek = seg_lo
            else:
                import random
                seek = random.uniform(seg_lo,
                                       max(seg_lo, seg_hi - 6))

            clip_path = self._tmp(".mp4")
            orig_frame_path = self._tmp(".png")
            comp_frame_path = self._tmp(".png")
            comp_clip_path = self._tmp(".mp4")

            self.progress.emit(25)

            clip_cmd = [
                str(g.ffmpeg_path), "-y", "-ss", f"{seek:.2f}",
                "-i", self.file_path, "-t", "5",
                "-c", "copy", clip_path,
            ]
            rc, err = self._run_ffmpeg(clip_cmd)
            if rc != 0:
                self.failed.emit(f"Clip extraction failed: {err.strip()[-300:]}")
                return
            self.progress.emit(40)

            orig_frame_cmd = [
                str(g.ffmpeg_path), "-y",
                "-i", clip_path,
                "-frames:v", "1", "-q:v", "2",
                orig_frame_path,
            ]
            rc, err = self._run_ffmpeg(orig_frame_cmd)
            if rc != 0:
                self.failed.emit(f"Original frame extraction failed: {err.strip()[-300:]}")
                return
            self.progress.emit(55)

            with open(orig_frame_path, "rb") as f:
                orig_png = f.read()
            self.original_frame_ready.emit(orig_png)
            self.progress.emit(65)

            cinfo = self._build_compressed_clip(clip_path, comp_clip_path, info)
            if cinfo is None:
                return
            self.progress.emit(80)

            comp_frame_cmd = [
                str(g.ffmpeg_path), "-y",
                "-i", comp_clip_path,
                "-frames:v", "1", "-q:v", "2",
                comp_frame_path,
            ]
            rc, err = self._run_ffmpeg(comp_frame_cmd)
            if rc != 0:
                self.failed.emit(f"Compressed frame extraction failed: {err.strip()[-300:]}")
                return

            with open(comp_frame_path, "rb") as f:
                comp_png = f.read()
            self.compressed_frame_ready.emit(comp_png)
            self.progress.emit(100)
            self.finished_ok.emit(info)

        except Exception as e:
            self.failed.emit(str(e))
        finally:
            self._cleanup()

    def _build_compressed_clip(self, in_path, out_path, info):
        codec = info["codec"]
        pure_codec = codec.split(" ")[0] if codec else "libx264"
        is_remux = codec == "copy"
        is_hw = any(hw in pure_codec for hw in ["nvenc", "amf", "qsv", "vaapi"])
        is_lossless = pure_codec == "ffv1"
        use_crf = (not is_hw and not is_lossless
                   and pure_codec != "libvvenc"
                   and self.mode != "bitrate" and not is_remux)

        cmd = [str(g.ffmpeg_path), "-y", "-i", in_path]

        if is_remux:
            cmd.extend(["-c:v", "copy"])
        elif is_lossless:
            cmd.extend(["-c:v", "ffv1", "-level", "3", "-slicecrc", "1"])
        elif is_hw:
            cmd.extend(["-c:v", pure_codec, "-b:v", f"{info['video_bitrate_kbps']}k"])
            if "qsv" in pure_codec:
                cmd.extend(["-preset", "medium"])
            elif "nvenc" in pure_codec:
                cmd.extend(["-preset", "p4", "-tune", "hq"])
            elif "amf" in pure_codec:
                cmd.extend(["-quality", "balanced"])
        elif use_crf:
            cmd.extend(["-c:v", pure_codec])
            crf_value = "23"
            if "libx265" in pure_codec:
                cmd.extend(["-preset", "medium", "-crf", crf_value])
            elif "libx264" in pure_codec:
                cmd.extend(["-preset", "medium", "-crf", crf_value])
            elif "libsvtav1" in pure_codec:
                cmd.extend(["-preset", "6", "-crf", crf_value])
            elif "libaom-av1" in pure_codec:
                cmd.extend(["-cpu-used", "4", "-crf", crf_value])
            else:
                cmd.extend(["-b:v", f"{info['video_bitrate_kbps']}k"])
        else:
            cmd.extend(["-c:v", pure_codec, "-b:v", f"{info['video_bitrate_kbps']}k"])

        vf_filters = []
        if self.resolution != "Original" and not is_remux:
            import re
            match = re.search(r"(\d+)p", self.resolution)
            if match:
                target_res = int(match.group(1))
                vf_filters.append(f"scale=-2:{target_res}")

        if is_remux and not vf_filters:
            pass
        elif not vf_filters and "qsv" in pure_codec:
            vf_filters.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")

        if vf_filters:
            cmd.extend(["-vf", ",".join(vf_filters)])

        if not is_lossless:
            full_codec = self.codec
            if "(Modern 10-bit)" in full_codec:
                cmd.extend(["-pix_fmt", "p010le"])
            elif "(Standard 8-bit)" in full_codec:
                fmt = "nv12" if "qsv" in pure_codec else "yuv420p"
                cmd.extend(["-pix_fmt", fmt])

        audio_filter = ("loudnorm=I=-14:TP=-1:LRA=11"
                        if self.audio_boost else None)
        if not is_remux:
            match self.audio_codec:
                case "none":
                    cmd.append("-an")
                case "copy":
                    cmd.extend(["-c:a", "copy"])
                case "aac":
                    if audio_filter:
                        cmd.extend(["-af", audio_filter, "-c:a", "aac", "-b:a", "192k"])
                    else:
                        cmd.extend(["-c:a", "aac", "-b:a", "192k"])
                case "mp3":
                    if audio_filter:
                        cmd.extend(["-af", audio_filter, "-c:a", "libmp3lame", "-b:a", "192k"])
                    else:
                        cmd.extend(["-c:a", "libmp3lame", "-b:a", "192k"])
                case "opus":
                    if audio_filter:
                        cmd.extend(["-af", audio_filter, "-c:a", "libopus", "-b:a", "128k"])
                    else:
                        cmd.extend(["-c:a", "libopus", "-b:a", "128k"])
                case "flac":
                    if audio_filter:
                        cmd.extend(["-af", audio_filter, "-c:a", "flac"])
                    else:
                        cmd.extend(["-c:a", "flac"])
                case _:
                    cmd.extend(["-c:a", "copy"])

        cmd.append(out_path)
        rc, err = self._run_ffmpeg(cmd)
        if rc != 0:
            short = err.strip()[-400:] if err else "Unknown error"
            self.failed.emit(f"Compressed clip encoding failed: {short}")
            return None
        return True

