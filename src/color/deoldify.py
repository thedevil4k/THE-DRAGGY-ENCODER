import cv2
import numpy as np


class DeOldifyONNX:
    """DeOldify colorization using ONNX Runtime.

    Supports both FP16 (faster, smaller) and FP32 (more accurate) models.
    Uses render_factor to control internal processing resolution.
    """

    def __init__(self, model_path, device="cpu"):
        """Initialize the colorizer.

        Args:
            model_path: Path to the .onnx model file.
            device: 'cpu' or 'cuda'.
        """
        try:
            import onnxruntime as ort
        except ImportError:
            raise RuntimeError("onnxruntime is required. Install with: pip install onnxruntime-gpu")

        session_options = ort.SessionOptions()
        session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        if device == "cuda":
            providers = [
                ("CUDAExecutionProvider", {"cudnn_conv_algo_search": "DEFAULT"}),
                "CPUExecutionProvider",
            ]
        else:
            providers = ["CPUExecutionProvider"]

        self.session = ort.InferenceSession(model_path, sess_options=session_options, providers=providers)
        self.input_name = self.session.get_inputs()[0].name

    def colorize(self, image, render_factor=256):
        """Colorize a single BGR image.

        Args:
            image: Input BGR image (numpy array from cv2).
            render_factor: Internal processing resolution (higher = better quality, slower).

        Returns:
            Colorized BGR image.
        """
        h, w = image.shape[:2]

        # Extract L channel from original (for later merging)
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        target_l, _, _ = cv2.split(lab)

        # Convert to grayscale -> 3-channel RGB for model input
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        rgb_input = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)

        # Resize to render_factor
        rgb_resized = cv2.resize(rgb_input, (render_factor, render_factor))

        # Determine input dtype from model
        input_meta = self.session.get_inputs()[0]
        if "float16" in input_meta.type:
            input_tensor = rgb_resized.astype(np.float16)
        else:
            input_tensor = rgb_resized.astype(np.float32)

        input_tensor = input_tensor.transpose((2, 0, 1))  # HWC -> CHW
        input_tensor = np.expand_dims(input_tensor, axis=0)  # Add batch dim

        # Run inference
        output = self.session.run(None, {self.input_name: input_tensor})[0][0]

        # Post-process output
        if output.ndim == 3:
            colorized = output.transpose(1, 2, 0)  # CHW -> HWC
        else:
            colorized = output

        # Convert to uint8
        if colorized.dtype in (np.float16, np.float32):
            colorized = np.clip(colorized, 0, 255).astype(np.uint8)

        # Ensure RGB -> BGR for OpenCV
        if colorized.shape[2] == 3:
            colorized = cv2.cvtColor(colorized, cv2.COLOR_RGB2BGR)

        # Resize back to original dimensions
        colorized = cv2.resize(colorized, (w, h))

        # Light blur to smooth artifacts
        colorized = cv2.GaussianBlur(colorized, (13, 13), 0)

        # Merge: keep original L (sharpness/detail) with predicted A/B (color)
        colorized_lab = cv2.cvtColor(colorized, cv2.COLOR_BGR2LAB)
        _, a_pred, b_pred = cv2.split(colorized_lab)

        # Merge original L with predicted A/B
        merged_lab = cv2.merge((target_l, a_pred, b_pred))
        result = cv2.cvtColor(merged_lab, cv2.COLOR_LAB2BGR)

        return result
