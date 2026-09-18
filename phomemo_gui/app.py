# phomemo_gui/app.py
"""Phomemo M02S GUI — Linux desktop app for the Phomemo M02S bluetooth thermal printer.

Features:
  - Connect to the M02S over Bluetooth RFCOMM
  - Load an image and preview it on a simulated paper strip (512 dots wide)
  - Scale (拡大/縮小), move (移動), rotate (回転) the print area
  - Add / edit text layers with selectable font, size and position
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

from phomemo_gui import fonts
from phomemo_gui.renderer import PaperRenderer, TextItem, PAPER_WIDTH_DOTS


CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.ini")
DISPLAY_DPI = 2.0


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Phomemo M02S Printer")
        self.geometry("1080x720")
        self.minsize(820, 560)

        self.renderer = PaperRenderer()
        self.preview_img = None
        self._print_thread = None
        self._sel_text_index = None

        self.cfg = configparser.ConfigParser()
        if os.path.exists(CONFIG_PATH):
            self.cfg.read(CONFIG_PATH)
        if not self.cfg.has_section("device"):
            self.cfg["device"] = {"mac": "", "port": "6"}

        self._build_toolbar()
        body = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self._build_text_panel(body)
        self._build_canvas(body)
        self._build_statusbar()

        self._refresh_preview()

    # ---- UI construction ---------------------------------------------
    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=(6, 4))
        bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(bar, text="画像を開く", command=self.open_image).pack(side=tk.LEFT)
        ttk.Button(bar, text="リセット", command=self.reset_transform).pack(
            side=tk.LEFT, padx=(6, 0))

        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

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

    def _build_text_panel(self, parent):
        panel = ttk.Frame(parent, padding=8, width=300)
        panel.pack(side=tk.LEFT, fill=tk.Y)

        ttk.Label(panel, text="テキスト", font=("", 11, "bold")).pack(anchor=tk.W)
        ttk.Label(panel, text="内容（改行OK）:").pack(anchor=tk.W, pady=(6, 2))
        self.text_entry = tk.Text(panel, height=3, width=34)
        self.text_entry.pack(fill=tk.X)
        self.text_entry.bind("<Control-Return>", lambda e: self.text_add())

        row1 = ttk.Frame(panel)
        row1.pack(fill=tk.X, pady=(6, 2))
        ttk.Label(row1, text="フォント:").pack(side=tk.LEFT)
        self.font_var = tk.StringVar(value=fonts.get_font_names()[0])
        self.font_combo = ttk.Combobox(
            row1, textvariable=self.font_var, state="readonly",
            values=fonts.get_font_names(), width=24)
        self.font_combo.pack(side=tk.LEFT, padx=(4, 0))

        row2 = ttk.Frame(panel)
        row2.pack(fill=tk.X, pady=(0, 2))
        ttk.Label(row2, text="サイズ:").pack(side=tk.LEFT)
        self.size_var = tk.IntVar(value=32)
        self.size_spin = ttk.Spinbox(row2, from_=8, to=200, textvariable=self.size_var,
                                     width=6)
        self.size_spin.pack(side=tk.LEFT, padx=(4, 0))
        ttk.Label(row2, text="色:").pack(side=tk.LEFT, padx=(10, 0))
        self.color_var = tk.StringVar(value="黒")
        self.color_combo = ttk.Combobox(row2, textvariable=self.color_var,
                                        state="readonly", values=["黒", "白"], width=4)
        self.color_combo.pack(side=tk.LEFT, padx=(4, 0))

        row3 = ttk.Frame(panel)
        row3.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(row3, text="X:").pack(side=tk.LEFT)
        self.tx_var = tk.IntVar(value=8)
        ttk.Spinbox(row3, from_=0, to=PAPER_WIDTH_DOTS, textvariable=self.tx_var,
                    width=5, command=self.text_sync_current).pack(side=tk.LEFT, padx=(2, 8))
        ttk.Label(row3, text="Y:").pack(side=tk.LEFT)
        self.ty_var = tk.IntVar(value=8)
        ttk.Spinbox(row3, from_=0, to=2000, textvariable=self.ty_var, width=5,
                    command=self.text_sync_current).pack(side=tk.LEFT, padx=(2, 0))

        btnrow = ttk.Frame(panel)
        btnrow.pack(fill=tk.X, pady=(4, 6))
        ttk.Button(btnrow, text="新規追加", command=self.text_add).pack(side=tk.LEFT)
        ttk.Button(btnrow, text="選択を更新", command=self.text_update).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(btnrow, text="削除", command=self.text_delete).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(btnrow, text="クリア", command=self.text_clear).pack(side=tk.LEFT, padx=(4, 0))

        # layer list
        ttk.Label(panel, text="レイヤー（上=先に描画）:").pack(anchor=tk.W)
        self.text_list = tk.Listbox(panel, height=8, activestyle="dotbox")
        self.text_list.pack(fill=tk.BOTH, expand=True)
        self.text_list.bind("<<ListboxSelect>>", self._on_text_select)

        lrow = ttk.Frame(panel)
        lrow.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(lrow, text="上へ", command=lambda: self.text_move(-1)).pack(side=tk.LEFT)
        ttk.Button(lrow, text="下へ", command=lambda: self.text_move(1)).pack(side=tk.LEFT, padx=(4, 0))

    def _build_canvas(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(frame, bg="#888888")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", lambda e: self._refresh_preview())
        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self._on_wheel_unix(e, 1))
        self.canvas.bind("<Button-5>", lambda e: self._on_wheel_unix(e, -1))

        rotbar = ttk.Frame(self)
        rotbar.pack(side=tk.BOTTOM, fill=tk.X, padx=6, pady=4)
        ttk.Label(rotbar, text="画像回転:").pack(side=tk.LEFT)
        for label, angle in (("90°左", -90), ("90°右", 90), ("180°", 180)):
            b = ttk.Button(rotbar, text=label,
                           command=lambda a=angle: self.rotate_by(a))
            b.pack(side=tk.LEFT, padx=2)
        ttk.Label(rotbar, text=" ドラッグ: 画像移動 / ホイール: 画像回転").pack(side=tk.LEFT, padx=12)

    def _build_statusbar(self):
        self.status = tk.StringVar(value="準備完了")
        bar = ttk.Label(self, textvariable=self.status, anchor=tk.W,
                        relief=tk.SUNKEN, padding=(6, 2))
        bar.pack(side=tk.BOTTOM, fill=tk.X)

    # ---- text interactions -------------------------------------------
    def text_add(self):
        text = self.text_entry.get("1.0", "end-1c")
        if not text.strip():
            messagebox.showwarning("テキスト", "内容を入力してください。")
            return
        font_label = self.font_var.get()
        size = int(self.size_var.get())
        color = (255, 255, 255) if self.color_var.get() == "白" else (0, 0, 0)
        x, y = int(self.tx_var.get()), int(self.ty_var.get())
        it = TextItem(text, font_label, size, x, y, color)
        self.renderer.text_items.append(it)
        self._sel_text_index = len(self.renderer.text_items) - 1
        self._refresh_text_list()
        self._refresh_preview()

    def text_update(self):
        if self._sel_text_index is None or not (0 <= self._sel_text_index < len(self.renderer.text_items)):
            messagebox.showinfo("選択", "レイヤー一覧から更新したいテキストを選んでください。")
            return
        text = self.text_entry.get("1.0", "end-1c")
        if not text.strip():
            messagebox.showwarning("テキスト", "内容を入力してください。")
            return
        it = self.renderer.text_items[self._sel_text_index]
        it.text = text
        it.font_label = self.font_var.get()
        it.size = int(self.size_var.get())
        it.color = (255, 255, 255) if self.color_var.get() == "白" else (0, 0, 0)
        it.x, it.y = int(self.tx_var.get()), int(self.ty_var.get())
        self._refresh_text_list()
        self._refresh_preview()

    def text_sync_current(self):
        if self._sel_text_index is not None and 0 <= self._sel_text_index < len(self.renderer.text_items):
            it = self.renderer.text_items[self._sel_text_index]
            it.x = int(self.tx_var.get())
            it.y = int(self.ty_var.get())
            self._refresh_text_list()
            self._refresh_preview()

    def text_delete(self):
        if self._sel_text_index is None:
            return
        if 0 <= self._sel_text_index < len(self.renderer.text_items):
            del self.renderer.text_items[self._sel_text_index]
        self._sel_text_index = None
        self._refresh_text_list()
        self._refresh_preview()

    def text_clear(self):
        self.renderer.text_items = []
        self._sel_text_index = None
        self._refresh_text_list()
        self._refresh_preview()

    def text_move(self, delta):
        i = self._sel_text_index
        if i is None:
            return
        j = i + delta
        if 0 <= j < len(self.renderer.text_items):
            self.renderer.text_items[i], self.renderer.text_items[j] = \
                self.renderer.text_items[j], self.renderer.text_items[i]
            self._sel_text_index = j
            self._refresh_text_list()
            self._refresh_preview()

    def _on_text_select(self, _evt):
        sel = self.text_list.curselection()
        if not sel:
            return
        i = sel[0]
        if 0 <= i < len(self.renderer.text_items):
            self._load_text_into_form(i)

    def _load_text_into_form(self, i):
        it = self.renderer.text_items[i]
        self._sel_text_index = i
        self.text_entry.delete("1.0", "end")
        self.text_entry.insert("1.0", it.text)
        self.font_var.set(it.font_label)
        self.size_var.set(it.size)
        self.color_var.set("白" if it.color == (255, 255, 255) else "黒")
        self.tx_var.set(it.x)
        self.ty_var.set(it.y)
        self.text_list.selection_clear(0, tk.END)
        self.text_list.selection_set(i)

    def _refresh_text_list(self):
        self.text_list.delete(0, tk.END)
        for idx, it in enumerate(self.renderer.text_items):
            preview = (it.text or "").replace("\n", " ⏎ ")
            if len(preview) > 24:
                preview = preview[:24] + "…"
            self.text_list.insert(tk.END, f"{idx}: {preview}")
        if self._sel_text_index is not None:
            self.text_list.selection_set(self._sel_text_index)

    # ---- image / print interactions ----------------------------------
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
        self.renderer.set_image(img)  # note: reset_transform clears text too
        self.zoom_var.set(100)
        self.status.set(f"読み込み: {os.path.basename(path)}  {img.size[0]}x{img.size[1]}")
        self._refresh_text_list()
        self._refresh_preview()

    def reset_transform(self):
        self.renderer.reset_transform()
        self._sel_text_index = None
        self.zoom_var.set(100)
        self._refresh_text_list()
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
        if not self.renderer.has_image() and not self.renderer.text_items:
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
        if not self.renderer.has_image() and not self.renderer.text_items:
            messagebox.showwarning("内容なし", "画像またはテキストを追加してください。")
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
