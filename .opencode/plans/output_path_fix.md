# Fix: output_path missing in non-remux encoding path

## Problem
When `run_pass()` is called with a non-remux codec (libx264, libx265, etc.), the
variable `output_path` is never defined because it's only set in the remux branch
(lines 517-523). The normal encoding path at line 641+ defines `file_name_stem` and
`original_ext` but does NOT calculate `out_ext` or `output_path`.

This causes a `NameError` when ffmpeg tries to use `output_path` (line 689+).

## Fix in src/thread.py

Find these lines (around line 641):
```python
        file_name_stem = file_path.stem
        original_ext = file_path.suffix.lstrip(".")
        # Software encoders (libx264, libx265, etc.): 2-pass for better quality
```

Replace with:
```python
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

        # Software encoders (libx264, libx265, etc.): 2-pass for better quality
        if is_hw_encoder or is_lossless or pure_codec == "libvvenc":
```

## verify
After fix, `python -m py_compile src/thread.py` should pass.