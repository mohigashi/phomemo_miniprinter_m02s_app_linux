# phomemo_gui/renderer.py
"""Paper composition logic for the Phomemo M02S.

Kept independent of any GUI toolkit so it can be imported and tested
headlessly (no tkinter required).
"""
from __future__ import annotations

import PIL.Image
import PIL.ImageDraw

from phomemo_gui import fonts


# The M02S paper is 512 dots wide (full width).
PAPER_WIDTH_DOTS = 512


# aliases for text colors (RGB)
TEXT_BLACK = (0, 0, 0)
TEXT_WHITE = (255, 255, 255)


def text_bounds(draw, text, font):
    """Return (w, h) of the rendered text using PIL anchor-independent math."""
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return (bbox[2] - bbox[0], bbox[3] - bbox[1])
    except Exception:
        return font.getsize(text) if hasattr(font, "getsize") else (0, 0)


class TextItem:
    """A single text layer placed on the paper (in dots).

    x, y are the top-left of the rendered text. font_label is a key from
    ``phomemo_gui.fonts.get_font_names()``. size is the font pixel size.
    color is TEXT_BLACK or TEXT_WHITE. multiline text is split on \\n.
    """

    def __init__(self, text="", font_label=None, size=32, x=8, y=8,
                 color=TEXT_BLACK):
        self.text = text
        self.font_label = font_label or fonts.get_font_names()[0]
        self.size = size
        self.x = x
        self.y = y
        self.color = color

    def to_dict(self):
        return {
            "text": self.text,
            "font_label": self.font_label,
            "size": self.size,
            "x": self.x,
            "y": self.y,
            "color": "white" if self.color == TEXT_WHITE else "black",
        }

    @classmethod
    def from_dict(cls, d):
        color = TEXT_WHITE if d.get("color") == "white" else TEXT_BLACK
        return cls(
            text=d.get("text", ""),
            font_label=d.get("font_label"),
            size=int(d.get("size", 32)),
            x=int(d.get("x", 8)),
            y=int(d.get("y", 8)),
            color=color,
        )


class PaperRenderer:
    """Simulates the printable paper strip and composites layers onto it.

    The paper is always PAPER_WIDTH_DOTS wide. The image has its own
    'dot size' (width in dots), scaled by the zoom factor, applied at an
    offset with rotation. Text layers are drawn on top at fixed dot
    coordinates.
    """

    def __init__(self):
        self._original = None          # PIL image as loaded (RGB, not resized)
        self.rotation = 0              # degrees, multiple of 90
        self.zoom = 1.0                # 1.0 = image printed at its full dot width
        self.off_x = 0                 # dots, image left edge within paper
        self.off_y = 0
        self.text_items = []           # list[TextItem]

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
        self.text_items = []

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

    def text_extent(self):
        return self._text_extent(self.text_items)

    def _text_extent(self, items):
        """(x, y, w, h) union of all text items (None if none)."""
        if not items:
            return None
        draw = PIL.ImageDraw.Draw(PIL.Image.new("RGB", (1, 1)))
        xs, ys, xe, ye = [], [], [], []
        for it in items:
            if not it.text:
                continue
            font = fonts.load_font(it.font_label, it.size)
            # handle multiline
            lines = it.text.split("\n")
            line_h = it.size
            w = max(text_bounds(draw, ln, font)[0] for ln in lines) if lines else 0
            h = line_h * len(lines)
            xs.append(it.x); ys.append(it.y)
            xe.append(it.x + w); ye.append(it.y + h)
        if not xs:
            return None
        return (min(xs), min(ys), max(xe) - min(xs), max(ye) - min(ys))

    def paper_height_dots(self, text_items=None):
        """Height of the printable strip: covers image and text extent."""
        items = self.text_items if text_items is None else text_items
        x, y, w, h = self.bounding_box()
        bottom = max(0, y + h)
        te = self._text_extent(items)
        if te:
            bottom = max(bottom, te[1] + te[3])
        return int(max(bottom, 40))

    # --- compositing for preview & print -----------------------------
    def compose(self, mode="RGB", margin_bottom=0, text_items=None):
        """Return a PIL image of the paper strip with image + text layers.

        text_items may override self.text_items (used for live preview drafts
        before the layer is committed).
        """
        items = self.text_items if text_items is None else text_items
        # image layer (optional)
        height = 0
        paper = None
        if self.has_image():
            rot = self.rotated(self._original, self.rotation)
            w_dots, h_dots = self.image_dot_size()
            if w_dots <= 0:
                raise RuntimeError("Image has zero width")
            img = rot.resize((w_dots, h_dots), PIL.Image.LANCZOS)
            x, y, w, h = self.bounding_box()
            height = max(height, y + h)

        te = self._text_extent(items)
        if te:
            height = max(height, te[1] + te[3])

        if not self.has_image() and not items:
            raise RuntimeError("Nothing to compose")

        height = max(height, 40) + margin_bottom
        paper = PIL.Image.new(mode, (PAPER_WIDTH_DOTS, height), "white")
        d = PIL.ImageDraw.Draw(paper)

        if self.has_image():
            img = self.rotated(self._original, self.rotation).resize(
                self.image_dot_size(), PIL.Image.LANCZOS
            )
            x, y = self.off_x, self.off_y
            paper.paste(img, (x, y))

        for it in items:
            if not it.text:
                continue
            font = fonts.load_font(it.font_label, it.size)
            lines = it.text.split("\n")
            line_h = it.size
            yy = it.y
            for ln in lines:
                d.text((it.x, yy), ln, fill=it.color, font=font)
                yy += line_h
        return paper

    def build_printable(self):
        """Return the final paper strip to send to the printer (RGB)."""
        return self.compose(mode="RGB", margin_bottom=10)

    def render_preview(self, height_px, text_items=None):
        """Return an ImageTk.PhotoImage for preview given a target strip pixel height."""
        page = self.compose(mode="RGB", margin_bottom=8, text_items=text_items)
        scale = height_px / page.height
        disp = page.resize(
            (max(1, int(page.width * scale)), height_px), PIL.Image.NEAREST
        )
        import PIL.ImageTk  # only needed for on-screen preview
        return PIL.ImageTk.PhotoImage(disp)
