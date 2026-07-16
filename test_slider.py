"""Slider diagnostic — opens a tiny window with one SliderCompareLabel
and a button that prints drag state. Save as test_slider.py and run."""
from __future__ import annotations
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt

# Re-use the actual class
import main as main_module
SliderCompareLabel = main_module.SliderCompareLabel

class W(QWidget):
    def __init__(self):
        super().__init__()
        self.resize(800, 500)
        lay = QVBoxLayout(self)
        self.btn_paint = QPushButton("Dump slider state")
        self.btn_paint.clicked.connect(self.dump)
        lay.addWidget(self.btn_paint)
        self.info = QLabel("press the button after dragging")
        lay.addWidget(self.info)
        self.compare = SliderCompareLabel()
        lay.addWidget(self.compare, 1)
        # Create dummy pixmaps
        pix1 = QPixmap(640, 360)
        pix1.fill(Qt.red)
        pix2 = QPixmap(640, 360)
        pix2.fill(Qt.blue)
        self.compare.set_original(self._pixmap_to_png(pix1))
        self.compare.set_compressed(self._pixmap_to_png(pix2))

    def _pixmap_to_png(self, pix):
        from PySide6.QtCore import QBuffer, QIODevice
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        pix.save(buf, "PNG")
        return bytes(buf.data())

    def dump(self):
        z = self.compare.zoom_factor()
        s = self.compare._slider
        self.info.setText(f"slider={s:.3f}  zoom={z:.3f}")


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    w = W()
    w.show()
    sys.exit(app.exec())
