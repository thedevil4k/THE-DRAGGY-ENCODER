import os
import glob
import platform
import shutil
import subprocess
from pathlib import Path
import src.globals as g


# ──────────────────────────────────────────────
# Model catalog
# ──────────────────────────────────────────────

COLORIZE_MODELS = {
    "deoldify-artistic": {
        "name": "DeOldify Artistic (FP32)",
        "description": "Full quality, vibrant colors, best for B&W film restoration",
        "vram_mb": 500,
        "speed": "Medium",
        "speed_fps": "5-10 FPS (1080p)",
        "quality": 5,
        "best_for": "B&W video, old film, historical footage",
        "model_url": "https://github.com/instant-high/deoldify-onnx/releases/download/deoldify-onnx/deoldify.onnx",
        "model_filename": "deoldify.onnx",
        "render_factor_default": 256,
    },
    "deoldify-artistic-fp16": {
        "name": "DeOldify Artistic (FP16 Fast)",
        "description": "Half size, faster, slightly lower quality",
        "vram_mb": 350,
        "speed": "Fast",
        "speed_fps": "10-20 FPS (1080p)",
        "quality": 4,
        "best_for": "B&W video, quick previews, weaker GPUs",
        "model_url": "https://github.com/instant-high/deoldify-onnx/releases/download/deoldify-onnx/deoldify_fp16.onnx",
        "model_filename": "deoldify_fp16.onnx",
        "render_factor_default": 256,
    },
}

UPSCALE_MODELS = {
    "realesr-animevideov3": {
        "name": "Anime Video v3",
        "description": "Fast, optimized for anime/cartoon content",
        "vram_mb": 300,
        "speed": "Fast",
        "speed_fps": "2-5 FPS (1080p)",
        "quality": 3,
        "best_for": "Anime, cartoons, animation",
        "scale_options": [2, 3, 4],
    },
    "realesrgan-x4plus-anime": {
        "name": "Anime (x4plus)",
        "description": "Anime-optimized with better detail",
        "vram_mb": 450,
        "speed": "Medium",
        "speed_fps": "1-2 FPS (1080p)",
        "quality": 4,
        "best_for": "Anime illustrations, drawings",
        "scale_options": [4],
    },
    "realesrgan-x4plus": {
        "name": "General (x4plus)",
        "description": "General-purpose, highest quality",
        "vram_mb": 900,
        "speed": "Slow",
        "speed_fps": "0.3-0.8 FPS (1080p)",
        "quality": 5,
        "best_for": "Photos, natural images, general video",
        "scale_options": [4],
    },
    "realesr-general-x4v3": {
        "name": "General v3 (Fast)",
        "description": "Tiny model, very fast processing",
        "vram_mb": 225,
        "speed": "Very Fast",
        "speed_fps": "3-8 FPS (1080p)",
        "quality": 3,
        "best_for": "Speed-critical tasks, batch processing",
        "scale_options": [4],
    },
    "realesr-general-wdn-x4v3": {
        "name": "Denoise v3",
        "description": "Denoising variant for noisy sources",
        "vram_mb": 225,
        "speed": "Very Fast",
        "speed_fps": "3-8 FPS (1080p)",
        "quality": 3,
        "best_for": "Noisy/low quality sources, YouTube rips",
        "scale_options": [4],
    },
}

INTERPOLATION_MODELS = {
    "rife-v2.3": {
        "name": "RIFE v2.3 (Fast)",
        "description": "Default model, good speed/quality balance",
        "vram_mb": 300,
        "speed": "Fast",
        "speed_fps": "15-25 FPS (1080p)",
        "quality": 3,
        "best_for": "General use, quick preview",
    },
    "rife-v3.1": {
        "name": "RIFE v3.1",
        "description": "Improved flow estimation over v2",
        "vram_mb": 300,
        "speed": "Fast",
        "speed_fps": "15-22 FPS (1080p)",
        "quality": 4,
        "best_for": "Good balance of speed and quality",
    },
    "rife-v4": {
        "name": "RIFE v4",
        "description": "Major improvement, supports custom frame rates",
        "vram_mb": 550,
        "speed": "Medium",
        "speed_fps": "10-18 FPS (1080p)",
        "quality": 5,
        "best_for": "High quality, arbitrary multipliers",
    },
    "rife-v4.6": {
        "name": "RIFE v4.6 (Best)",
        "description": "Latest model, best quality available",
        "vram_mb": 650,
        "speed": "Slow",
        "speed_fps": "8-15 FPS (1080p)",
        "quality": 5,
        "best_for": "Maximum quality interpolation",
    },
}


# ──────────────────────────────────────────────
# VRAM detection
# ──────────────────────────────────────────────

def get_gpu_vram_mb():
    """Detect dedicated GPU VRAM in MB. Returns 0 if unknown."""
    if platform.system() == "Windows":
        # Method 1: nvidia-smi (NVIDIA, most reliable)
        try:
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                universal_newlines=True, stderr=subprocess.DEVNULL,
                creationflags=0x08000000,
            )
            values = [int(x.strip()) for x in output.strip().splitlines() if x.strip().isdigit()]
            if values:
                return max(values)
        except Exception:
            pass

        # Method 2: Windows Registry (bypasses 4GB WMI limit)
        try:
            ps_script = (
                "$regPath = 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e968-e325-11ce-bfc1-08002be10318}'\n"
                "$maxVram = 0\n"
                "Get-ChildItem $regPath -ErrorAction SilentlyContinue | Where-Object { $_.PSChildName -match '^\\d{4}$' } | ForEach-Object {\n"
                "    $props = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue\n"
                "    if ($props -and $props.HardwareInformation.MemorySize) {\n"
                "        $mem = $props.HardwareInformation.MemorySize\n"
                "        if ($mem -is [byte[]]) { $vram = [BitConverter]::ToUInt64($mem, 0) / 1MB }\n"
                "        else { $vram = $mem / 1MB }\n"
                "        if ($vram -gt $maxVram) { $maxVram = $vram }\n"
                "    }\n"
                "}\n"
                "[int]$maxVram"
            )
            output = subprocess.check_output(
                ["powershell", "-Command", ps_script],
                universal_newlines=True, stderr=subprocess.DEVNULL,
                creationflags=0x08000000,
            )
            vram = int(float(output.strip()))
            if vram > 0:
                return vram
        except Exception:
            pass

    else:
        # Linux: nvidia-smi
        try:
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                universal_newlines=True, stderr=subprocess.DEVNULL,
            )
            values = [int(x.strip()) for x in output.strip().splitlines() if x.strip().isdigit()]
            if values:
                return max(values)
        except Exception:
            pass

        # Linux: sysfs (AMD)
        try:
            for f in glob.glob("/sys/class/drm/card*/device/mem_info_vram_total"):
                with open(f) as fh:
                    return int(fh.read().strip()) // (1024 * 1024)
        except Exception:
            pass

    return 0


def get_gpu_name():
    """Detect primary GPU name."""
    if platform.system() == "Windows":
        try:
            output = subprocess.check_output(
                ["powershell", "-Command",
                 "(Get-CimInstance Win32_VideoController | Select-Object -First 1).Name"],
                universal_newlines=True, stderr=subprocess.DEVNULL,
                creationflags=0x08000000,
            )
            name = output.strip()
            if name:
                return name
        except Exception:
            pass
    else:
        try:
            output = subprocess.check_output(["lspci"], universal_newlines=True, stderr=subprocess.DEVNULL)
            for line in output.splitlines():
                if "VGA" in line or "3D" in line:
                    return line.split(": ", 1)[-1].strip() if ": " in line else line.strip()
        except Exception:
            pass
    return "Unknown GPU"


def classify_vram(gpu_vram_mb, required_mb):
    """Returns compatibility status string."""
    if gpu_vram_mb == 0:
        return "unknown", "Unknown GPU VRAM - may work but untested"
    ratio = gpu_vram_mb / required_mb
    if ratio >= 2.0:
        return "excellent", f"Excellent ({gpu_vram_mb}MB available, {required_mb}MB needed)"
    elif ratio >= 1.5:
        return "good", f"Good ({gpu_vram_mb}MB available, {required_mb}MB needed)"
    elif ratio >= 1.0:
        return "marginal", f"Marginal ({gpu_vram_mb}MB available, {required_mb}MB needed) - use small tiles"
    else:
        return "insufficient", f"Insufficient ({gpu_vram_mb}MB available, {required_mb}MB needed) - may crash"


def detect_gpu_devices():
    """Detect available GPU devices for AI processing.

    Returns:
        List of dicts: [{"id": 0, "name": "...", "type": "dedicated"/"integrated"}, ...]
    """
    gpus = []

    # Try nvidia-smi for NVIDIA GPUs
    try:
        import subprocess
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,name", "--format=csv,noheader"],
            universal_newlines=True, stderr=subprocess.DEVNULL
        )
        for line in output.strip().splitlines():
            parts = line.split(", ", 1)
            if len(parts) == 2:
                gpu_id = int(parts[0])
                gpu_name = parts[1].strip()
                gpus.append({"id": gpu_id, "name": gpu_name, "type": "dedicated"})
    except Exception:
        pass

    # Try Windows WMI for Intel/AMD integrated GPUs
    if platform.system() == "Windows":
        try:
            import subprocess
            ps_cmd = (
                'Get-CimInstance Win32_VideoController | '
                'Select-Object Name, AdapterRAM | ConvertTo-Json'
            )
            output = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                universal_newlines=True, stderr=subprocess.DEVNULL
            )
            import json
            data = json.loads(output)
            if not isinstance(data, list):
                data = [data]
            existing_names = {g["name"] for g in gpus}
            for gpu in data:
                name = gpu.get("Name", "").strip()
                if not name or name in existing_names:
                    continue
                gpu_type = "integrated" if any(w in name.lower() for w in ["intel", "amd"]) else "dedicated"
                next_id = max([g["id"] for g in gpus], default=-1) + 1
                gpus.append({"id": next_id, "name": name, "type": gpu_type})
        except Exception:
            pass

    return gpus


def stars_rating(n):
    """Returns star string like ★★★☆☆."""
    return "★" * n + "☆" * (5 - n)


# ──────────────────────────────────────────────
# Frame extraction / encoding helpers
# ──────────────────────────────────────────────

def extract_frames(video_path, output_dir, fmt="jpg"):
    """Extract all frames from video to directory as JPEG."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(g.ffmpeg_path), "-y",
        "-i", str(video_path),
        "-qscale:v", "1",
        "-qmin", "1",
        "-qmax", "1",
        "-vsync", "0",
        str(output_dir / f"%08d.{fmt}"),
    ]
    _run_silent(cmd)


def has_audio_stream(video_path):
    """Check if a video file has any audio streams."""
    cmd = [
        str(g.ffprobe_path),
        "-v", "quiet",
        "-select_streams", "a",
        "-show_entries", "stream=index",
        "-of", "csv=p=0",
        str(video_path),
    ]
    try:
        output = subprocess.check_output(cmd, universal_newlines=True, stderr=subprocess.DEVNULL).strip()
        return bool(output)
    except Exception:
        return False


def extract_audio(video_path, output_path):
    """Extract audio track from video if present."""
    if not has_audio_stream(video_path):
        return False
    cmd = [
        str(g.ffmpeg_path), "-y",
        "-i", str(video_path),
        "-vn", "-acodec", "copy",
        str(output_path),
    ]
    _run_silent(cmd)
    return True


def get_video_fps(video_path):
    """Get video FPS as float."""
    cmd = [
        str(g.ffprobe_path),
        "-v", "quiet",
        "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate",
        "-of", "csv=p=0",
        str(video_path),
    ]
    try:
        output = subprocess.check_output(cmd, universal_newlines=True, stderr=subprocess.DEVNULL)
        fps_str = output.strip()
        if "/" in fps_str:
            num, den = fps_str.split("/")
            return float(num) / float(den)
        return float(fps_str)
    except Exception:
        return 30.0


def count_frames(frames_dir, fmt="jpg"):
    """Count frame files in directory."""
    frames_dir = Path(frames_dir)
    return len(list(frames_dir.glob(f"*.{fmt}")))


def encode_from_frames(frames_dir, output_path, fps, fmt="jpg"):
    """Encode video from frame sequence with given FPS."""
    cmd = [
        str(g.ffmpeg_path), "-y",
        "-framerate", str(fps),
        "-i", str(Path(frames_dir) / f"%08d.{fmt}"),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    _run_silent(cmd)


def mux_audio(video_path, audio_path, output_path):
    """Mux video + audio into final output."""
    cmd = [
        str(g.ffmpeg_path), "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "copy",
        str(output_path),
    ]
    _run_silent(cmd)


def cleanup_temp(*dirs):
    """Remove temporary directories."""
    for d in dirs:
        d = Path(d)
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)


def _run_silent(cmd):
    """Run a subprocess silently, raising on failure."""
    kwargs = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.PIPE,
    }
    if platform.system() == "Windows":
        kwargs["creationflags"] = 0x08000000
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        error = result.stderr.decode("utf-8", errors="ignore") if result.stderr else "Unknown error"
        raise RuntimeError(f"Command failed: {' '.join(str(c) for c in cmd[:3])}...\n{error[:300]}")


# ──────────────────────────────────────────────
# AI Processor
# ──────────────────────────────────────────────

class AIProcessor:
    """Runs Real-ESRGAN or RIFE ncnn-vulkan on frame directories."""

    def __init__(self, log_callback=None, progress_callback=None):
        self.log = log_callback or (lambda msg: None)
        self.progress = progress_callback or (lambda pct: None)
        self._process = None

    def upscale_frames(self, input_dir, output_dir, model_key, scale, tile_size=0, gpu_id=None):
        """Upscale frames using Real-ESRGAN ncnn-vulkan.

        Args:
            input_dir: Directory containing input frames.
            output_dir: Directory for upscaled output frames.
            model_key: Model key from UPSCALE_MODELS.
            scale: Upscale factor (2, 3, or 4).
            tile_size: Tile size (0=auto).
            gpu_id: GPU device index (None=auto, -1=CPU, 0,1,2...).
        """
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(g.realesrgan_path),
            "-i", str(input_dir),
            "-o", str(output_dir),
            "-n", model_key,
            "-s", str(scale),
            "-f", "jpg",
        ]
        if gpu_id is not None:
            cmd.extend(["-g", str(gpu_id)])
        if tile_size > 0:
            cmd.extend(["-t", str(tile_size)])

        self.log(f"Running Real-ESRGAN: {model_key} x{scale}")
        self._run_process(cmd)

    def interpolate_frames(self, input_dir, output_dir, model_key, multiplier, gpu_id=None):
        """Interpolate frames using RIFE ncnn-vulkan.

        Args:
            input_dir: Directory containing input frames.
            output_dir: Directory for interpolated output frames.
            model_key: Model key from INTERPOLATION_MODELS.
            multiplier: FPS multiplier (2, 3, or 4).
        """
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Determine model path for rife
        model_path = _find_rife_model(model_key)

        cmd = [
            str(g.rife_path),
            "-i", str(input_dir),
            "-o", str(output_dir),
            "-m", model_path,
            "-f", "%08d.jpg",
        ]
        if gpu_id is not None:
            cmd.extend(["-g", str(gpu_id)])

        if multiplier > 2 and "v4" in model_key:
            input_count = count_frames(input_dir)
            target_count = input_count * multiplier
            cmd.extend(["-n", str(target_count)])

        self.log(f"Running RIFE: {model_key} x{multiplier}")
        self._run_process(cmd)

    def abort(self):
        """Kill the active process."""
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()

    def _run_process(self, cmd):
        """Run an ncnn-vulkan process, forwarding stderr for progress."""
        kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "universal_newlines": True,
        }
        if platform.system() == "Windows":
            kwargs["creationflags"] = 0x08000000

        self._process = subprocess.Popen(cmd, **kwargs)
        if self._process.stdout:
            for line in self._process.stdout:
                stripped = line.strip()
                if stripped:
                    self.log(stripped)
        self._process.wait()

        if self._process.returncode != 0:
            raise RuntimeError(f"AI tool failed with return code {self._process.returncode}")


def _find_rife_model(model_key):
    """Find the model directory path for a RIFE model key."""
    # RIFE models are in: bin_dir/models/<model_key>/
    # The actual model dir may be named differently, search for it
    models_base = Path(g.bin_dir) / "models"
    candidate = models_base / model_key
    if candidate.exists():
        return str(candidate)

    # Fallback: search for any directory containing the model key
    if models_base.exists():
        for d in models_base.iterdir():
            if d.is_dir() and model_key in d.name:
                return str(d)

    # Last resort: use the models directory itself (older rife versions)
    return str(models_base)


# ──────────────────────────────────────────────
# ONNX Runtime detection
# ──────────────────────────────────────────────

def check_onnx_available():
    """Check if onnxruntime is available and return providers."""
    try:
        import onnxruntime as ort
        providers = ort.get_available_providers()
        has_cuda = "CUDAExecutionProvider" in providers
        return True, has_cuda, providers
    except ImportError:
        return False, False, []


def get_deoldify_model_path(model_key="deoldify-artistic"):
    """Get the path to a DeOldify ONNX model."""
    model_info = COLORIZE_MODELS.get(model_key)
    if not model_info:
        model_info = COLORIZE_MODELS["deoldify-artistic"]
    model_path = Path(g.bin_dir) / "models" / model_info["model_filename"]
    if model_path.exists():
        return str(model_path)
    return None


# ──────────────────────────────────────────────
# DeOldify Processor
# ──────────────────────────────────────────────

class DeOldifyProcessor:
    """Runs DeOldify ONNX colorization on frame directories."""

    def __init__(self, log_callback=None, progress_callback=None):
        self.log = log_callback or (lambda msg: None)
        self.progress = progress_callback or (lambda pct: None)
        self._colorizer = None

    def colorize_frames(self, input_dir, output_dir, render_factor=256, model_key="deoldify-artistic", device=None):
        """Colorize all frames in a directory using DeOldify ONNX.

        Args:
            input_dir: Directory with input frames.
            output_dir: Directory for colorized output frames.
            render_factor: Internal processing resolution.
            model_key: Key in COLORIZE_MODELS dict.
            device: "cuda", "cpu", or None for auto-detect.
        """
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        model_path = get_deoldify_model_path(model_key)
        if not model_path:
            raise RuntimeError("DeOldify model not found. Please restart to download it.")

        # Initialize colorizer with device selection
        if device is None:
            _, has_cuda, _ = check_onnx_available()
            device = "cuda" if has_cuda else "cpu"
        elif device == -1:
            device = "cpu"
        else:
            device = "cuda"
        self.log(f"Initializing DeOldify (device={device}, render_factor={render_factor})")

        from src.color.deoldify import DeOldifyONNX
        self._colorizer = DeOldifyONNX(model_path, device=device)

        # Process frames
        import cv2
        frame_files = sorted(input_dir.glob("*.jpg")) + sorted(input_dir.glob("*.png"))
        total = len(frame_files)

        for i, frame_path in enumerate(frame_files):
            image = cv2.imread(str(frame_path))
            if image is None:
                continue

            colorized = self._colorizer.colorize(image, render_factor)

            output_path = output_dir / frame_path.name
            cv2.imwrite(str(output_path), colorized)

            # Report progress
            pct = int((i + 1) / total * 100)
            self.progress(pct)
            if (i + 1) % 10 == 0 or (i + 1) == total:
                self.log(f"Colorized frame {i + 1}/{total}")

    def abort(self):
        """Abort processing (no subprocess to kill for ONNX)."""
        self._colorizer = None
