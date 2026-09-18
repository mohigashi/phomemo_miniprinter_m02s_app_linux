# phomemo_gui/renderer.py
"""Paper composition logic for the Phomemo M02S.

Kept independent of any GUI toolkit so it can be imported and tested
headlessly (no tkinter required).
"""
from __future__ import annotations

import PIL.Image
import PIL.ImageDraw


# The M02S paper is 512 dots wide (full width).
PAPER_WIDTH_DOTS = 512


class PaperRenderer:
    """Simulates the printable paper strip and composites the image onto it.

    The paper is always PAPER_WIDTH_DOTS wide. The image has its own
    'dot size' (width in dots), scaled by the zoom factor. The image is
    composited at a pixel offset (off_x, off_y) inside the paper, clipped
    to the paper bounds, with rotation applied.
    """

    def __init__(self):
        self._original = None          # PIL image as loaded (RGB, not resized)
        self.rotation = 0              # degrees, multiple of 90
        self.zoom = 1.0                # 1.0 = image printed at its full dot width
        self.off_x = 0                 # dots, image left edge within paper
        self.off_y = 0

    def set_image(self, pil_img):
        self._original = pil_img.convert("RGB")
        self.reset_transform()

    def has_image(self):
        return self._original is not None

    def reset_transform(self):
        self.rotation = 0
        self.zoom = 1.0
        self.off_x = 0
        self.off_y = 0

    # --- helpers -----------------------------------------------------
    def rotated(self, img, angle):
        if angle == 0:
            return img
        return img.rotate(-angle, expand=True)

    def base_dim(self):
        """(w, h) of the (rotated) original in pixels."""
        if not self.has_image():
            return (0, 0)
        return self.rotated(self._original, self.rotation).size

    def image_dot_size(self):
        """(w, h) of the printed image in dots after zoom."""
        w, h = self.base_dim()
        return (int(round(w * self.zoom)), int(round(h * self.zoom)))

    def bounding_box(self):
        """(x, y, w, h) of the image's printed region within paper coords."""
        w, h = self.image_dot_size()
        if w <= 0:
            return (0, 0, 0, 0)
        return (self.off_x, self.off_y, w, h)

    def paper_height_dots(self):
        """Height of the printable strip: covers the image extent."""
        x, y, w, h = self.bounding_box()
        bottom = max(0, y + h)
        return int(max(bottom, 40))

    # --- compositing for preview & print -----------------------------
    def compose(self, mode="RGB", margin_bottom=0):
        """Return a PIL image of the paper strip containing the placed image."""
        if not self.has_image():
            raise RuntimeError("No image loaded")
        rot = self.rotated(self._original, self.rotation)
        w_dots, h_dots = self.image_dot_size()
        if w_dots <= 0:
            raise RuntimeError("Image has zero width")
        img = rot.resize((w_dots, h_dots), PIL.Image.LANCZOS)

        x, y, w, h = self.bounding_box()
        height = max(h, y + h) + margin_bottom
        paper = PIL.Image.new(mode, (PAPER_WIDTH_DOTS, height), "white")
        paper.paste(img, (x, y))
        return paper

    def build_printable(self):
        """Return the final paper strip to send to the printer (RGB)."""
        return self.compose(mode="RGB", margin_bottom=10)

    def render_preview(self, height_px):
        """Return an ImageTk.PhotoImage for preview given a target strip pixel height."""
        page = self.compose(mode="RGB", margin_bottom=8)
        scale = height_px / page.height
        disp = page.resize(
            (max(1, int(page.width * scale)), height_px), PIL.Image.NEAREST
        )
        import PIL.ImageTk  # only needed for on-screen preview
        return PIL.ImageTk.PhotoImage(disp)
