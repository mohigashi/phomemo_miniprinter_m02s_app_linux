# phomemo_gui/fonts.py
"""Font discovery and loading for the Phomemo M02S GUI.

Scans common system font directories, builds a curated list of usable
fonts (preferring CJK-capable families plus common Latin families), and
provides a loader for Pillow.
"""
from __future__ import annotations

import os
import glob


# Manual map for families whose file names don't follow family==basename.
# key: display/family name -> list of candidate relative paths (preferred first).
_MANUAL = {
    "Noto Sans CJK JP": [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ],
    "Noto Sans CJK JP (Bold)": [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    ],
    "Noto Serif CJK JP": [
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSerifCJK-Regular.ttc",
    ],
    "Noto Serif CJK JP (Bold)": [
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSerifCJK-Bold.ttc",
    ],
}

# Families that map directly to a .ttf file whose basename is the family (or
# a common variant).
_LATIN = [
    "Arial", "Verdana", "Times New Roman", "Georgia", "Impact",
    "Trebuchet MS", "Courier New", "Comic Sans MS", "DejaVu Sans",
    "DejaVu Serif", "DejaVu Sans Mono", "Liberation Sans",
]


_CACHE_CURATED = None


def _renderer_paths():
    return ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts"), os.path.expanduser("~/.local/share/fonts")]


def _find_file(basename):
    for root in _renderer_paths():
        for f in glob.glob(os.path.join(root, "**", basename), recursive=True):
            return f
    return None


def curated_fonts():
    """Return ordered list of (label, font_path) available on this system."""
    global _CACHE_CURATED
    if _CACHE_CURATED is not None:
        return _CACHE_CURATED
    result = []  # (label, path)
    seen = set()

    # CJK first (so the GUI defaults to something readable for Japanese)
    for label, cands in _MANUAL.items():
        for c in cands:
            if os.path.isfile(c):
                result.append((label, c))
                seen.add(c)
                break

    # Latin families: family.ttf in msttcorefonts / dejavu / liberation
    mstt = "/usr/share/fonts/truetype/msttcorefonts"
    dejavu = "/usr/share/fonts/truetype/dejavu"
    lib = "/usr/share/fonts/truetype/liberation2"
    for fam in ["Arial", "Verdana", "Times New Roman", "Georgia", "Impact",
                "Trebuchet MS", "Courier New", "Comic Sans MS"]:
        fn = (fam.lower().replace(" ", "")) + ".ttf"
        for d in (mstt,):
            p = os.path.join(d, fn)
            if os.path.isfile(p):
                result.append((fam, p))
                seen.add(p)
                break
    for fam in ["DejaVu Sans", "DejaVu Serif", "DejaVu Sans Mono"]:
        fn = fam.replace(" ", "") + ".ttf"
        p = os.path.join(dejavu, fn)
        if os.path.isfile(p):
            result.append((fam, p))
            seen.add(p)

    # generic fallback candidates for any label not matched above
    _CACHE_CURATED = result
    return result


def font_label_to_path(label):
    for lbl, p in curated_fonts():
        if lbl == label:
            return p
    return None


def get_font_names():
    return [lbl for lbl, _ in curated_fonts()]


def load_font(label, size):
    from PIL import ImageFont
    path = font_label_to_path(label) or curated_fonts()[0][1]
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()
