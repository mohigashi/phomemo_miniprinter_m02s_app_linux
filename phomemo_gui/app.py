# phomemo_gui/app.py
"""Phomemo M02S GUI — Linux desktop app for the Phomemo M02S bluetooth thermal printer.

Features:
  - Connect to the M02S over Bluetooth RFCOMM (channel 6)
  - Load an image and preview it on a simulated paper strip (512 dots wide)
  - Scale (拡大/縮小), move (移動), rotate (回転) the print area
  - Print to the physical printer over bluetooth
"""
from __future__ import annotations

import configparser
import os
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import PIL.Image
import PIL.ImageTk

from phomemo_gui.renderer import PaperRenderer, PAPER_WIDTH_DOTS


CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.ini")
# Display scale: how many screen px per dot when at 100%.
DISPLAY_DPI = 2.0


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Phomemo M02S Printer")
        self.geometry("880x720")
        self.minsize(680, 520)

        self.renderer = PaperRenderer()
        self.preview_img = None
        self._print_thread = None

        self.cfg = configparser.ConfigParser()
        if os.path.exists(CONFIG_PATH):
            self.cfg.read(CONFIG_PATH)
        if not self.cfg.has_section("device"):
            self.cfg["device"] = {"mac": "", "port": "6"}

        self._build_toolbar()
        self._build_canvas()
        self._build_statusbar()

        self._refresh_preview()

    # ---- UI construction ---------------------------------------------
    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=(6, 4))
        bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(bar, text="画像を開く", command=self.open_image).pack(side=tk.LEFT)
        ttk.Button(bar, text="リセット", command=self.reset_transform).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        # Connection
        ttk.Label(bar, text="MAC:").pack(side=tk.LEFT)
        self.mac_var = tk.StringVar(value=self.cfg.get("device", "mac", fallback=""))
        self.mac_entry = ttk.Entry(bar, textvariable=self.mac_var, width=20)
        self.mac_entry.pack(side=tk.LEFT, padx=(2, 6))
        self.conn_btn = ttk.Button(bar, text="接続", command=self.toggle_connect)
        self.conn_btn.pack(side=tk.LEFT)

        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        self.scale_btn = ttk.Button(bar, text="印刷", command=self.print_image)
        self.scale_btn.pack(side=tk.RIGHT)

        ttk.Label(bar, text="ズーム:").pack(side=tk.RIGHT, padx=(0, 4))
        self.zoom_var = tk.DoubleVar(value=100)
        zoom = ttk.Scale(bar, from_=10, to=400, variable=self.zoom_var,
                         orient=tk.HORIZONTAL, length=140, command=self._on_zoom)
        zoom.pack(side=tk.RIGHT)

        self.conn = None  # holds Printer instance

    def _build_canvas(self):
        frame = ttk.Frame(self)
        frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(frame, bg="#888888")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", lambda e: self._refresh_preview())
        # drag to move
        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        # wheel = rotate; ctrl+wheel would be zoom but we have a slider
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self._on_wheel_unix(e, 1))
        self.canvas.bind("<Button-5>", lambda e: self._on_wheel_unix(e, -1))

        # right-click panel for rotation
        rotbar = ttk.Frame(self)
        rotbar.pack(side=tk.BOTTOM, fill=tk.X, padx=6, pady=4)
        ttk.Label(rotbar, text="回転:").pack(side=tk.LEFT)
        for label, angle in (("90°左", -90), ("90°右", 90), ("180°", 180)):
            b = ttk.Button(rotbar, text=label,
                           command=lambda a=angle: self.rotate_by(a))
            b.pack(side=tk.LEFT, padx=2)
        ttk.Label(rotbar, text=" ドラッグ: 移動 / ホイール: 回転").pack(side=tk.LEFT, padx=12)

    def _build_statusbar(self):
        self.status = tk.StringVar(value="準備完了")
        bar = ttk.Label(self, textvariable=self.status, anchor=tk.W,
                        relief=tk.SUNKEN, padding=(6, 2))
        bar.pack(side=tk.BOTTOM, fill=tk.X)

    # ---- interactions -------------------------------------------------
    def open_image(self):
        path = filedialog.askopenfilename(
            title="画像を選択",
            filetypes=[("画像", "*.png *.jpg *.jpeg *.bmp *.gif *.webp")],
        )
        if not path:
            return
        try:
            img = PIL.Image.open(path)
        except Exception as e:
            messagebox.showerror("エラー", f"画像を開けませんでした:\n{e}")
            return
        self.renderer.set_image(img)
        self.zoom_var.set(100)
        self.status.set(f"読み込み: {os.path.basename(path)}  {img.size[0]}x{img.size[1]}")
        self._refresh_preview()

    def reset_transform(self):
        self.renderer.reset_transform()
        self.zoom_var.set(100)
        self._refresh_preview()

    def rotate_by(self, angle):
        self.renderer.rotation = (self.renderer.rotation + angle) % 360
        self._refresh_preview()

    def _on_zoom(self, _val=None):
        self.renderer.zoom = self.zoom_var.get() / 100.0
        self._refresh_preview()

    def _on_drag_start(self, event):
        self._drag_start = (event.x, event.y)

    def _on_drag(self, event):
        if not self.renderer.has_image():
            return
        dx_px = event.x - self._drag_start[0]
        dy_px = event.y - self._drag_start[1]
        self._drag_start = (event.x, event.y)
        px_per_dot = self.canvas.winfo_width() / PAPER_WIDTH_DOTS
        self.renderer.off_x += int(dx_px / px_per_dot)
        self.renderer.off_y += int(dy_px / px_per_dot)
        self._refresh_preview()

    def _on_wheel(self, event):
        self.rotate_by(90 if event.delta > 0 else -90)

    def _on_wheel_unix(self, event, direction):
        self.rotate_by(90 * direction)

    def _refresh_preview(self):
        self.canvas.delete("all")
        if not self.renderer.has_image():
            return
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            return
        try:
            page = self.renderer.compose(mode="RGB")
        except RuntimeError:
            return
        scale = (ch - 16) / max(1, page.height)
        disp_h = max(20, int(page.height * scale))
        self.preview_img = self.renderer.render_preview(disp_h)
        disp_w = self.preview_img.width()
        x0 = (cw - disp_w) // 2
        y0 = (ch - disp_h) // 2
        self.canvas.create_image(x0, y0, anchor=tk.NW, image=self.preview_img)
        self.canvas.create_rectangle(x0 - 1, y0 - 1, x0 + disp_w + 1, y0 + disp_h + 1,
                                     outline="black", width=2)

    # ---- bluetooth + print ---------------------------------------------
    def toggle_connect(self):
        # Deferred import so PIL-only dev mode works
        from phomemo_m02s import Printer as _Printer
        mac = self.mac_var.get().strip()
        if not mac:
            messagebox.showwarning("MAC未設定", "Bluetooth MAC アドレスを入力してください。")
            return
        if self.conn is not None:
            self.conn = None
            self.conn_btn.config(text="接続")
            self.status.set("切断しました")
            return
        self._save_cfg(mac)
        self.status.set("接続中…")
        self.update_idletasks()
        try:
            self.conn = _Printer(mac=mac)
            self.conn.initialize()
            fw = self.conn.get_firmware_version()
            self.conn_btn.config(text="切断")
            self.status.set(f"接続OK  Firmware {fw}")
        except Exception as e:
            self.conn = None
            self.conn_btn.config(text="接続")
            self.status.set("接続失敗")
            messagebox.showerror("接続エラー",
                "Bluetooth接続に失敗しました。\n"
                f"M02Sの電源ON・ペアリングを確認してください。\n\n{e}")

    def _save_cfg(self, mac):
        self.cfg["device"]["mac"] = mac
        try:
            with open(CONFIG_PATH, "w") as f:
                self.cfg.write(f)
        except OSError:
            pass

    def print_image(self):
        if not self.renderer.has_image():
            messagebox.showwarning("画像なし", "先に画像を読み込んでください。")
            return
        if self.conn is None:
            messagebox.showwarning("未接続", "先にBluetoothで接続してください。")
            return
        if self._print_thread and self._print_thread.is_alive():
            return
        self._print_thread = threading.Thread(target=self._do_print, daemon=True)
        self._print_thread.start()

    def _do_print(self):
        def on_main(fn):
            self.after(0, fn)

        try:
            on_main(lambda: self.status.set("印刷中…"))
            page = self.renderer.build_printable()
            # The library's print_image takes a file path (it opens it itself).
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp_path = tmp.name
            tmp.close()
            try:
                page.save(tmp_path)
                self.conn.print_image(tmp_path, width=PAPER_WIDTH_DOTS)
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            on_main(lambda: self.status.set("印刷完了"))
        except Exception as e:
            on_main(lambda: messagebox.showerror("印刷エラー", str(e)))
            on_main(lambda: self.status.set("印刷失敗"))


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
