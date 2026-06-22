#!/usr/bin/env python3
"""
AIO Core Vision 360 — Crop, Trim & Loop Tool
Vereisten: pip install Pillow opencv-python
"""
import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess, sys, os, tempfile
from pathlib import Path

try:
    from PIL import Image, ImageTk, ImageDraw
    import cv2
    import numpy as np
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "Pillow", "opencv-python"], check=True)
    from PIL import Image, ImageTk, ImageDraw
    import cv2
    import numpy as np

SCREEN = 480
SRC_W, SRC_H = 270, 480
OUT_W = 240
TL_H = 44


def find_ffmpeg():
    for cmd in ["ffmpeg", "ffmpeg.exe"]:
        try:
            subprocess.run([cmd, "-version"], capture_output=True, check=True)
            return cmd
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass
    for p in [Path(sys.executable).parent / "ffmpeg.exe",
              Path(sys.executable).parent / "bin" / "ffmpeg.exe"]:
        if p.exists():
            return str(p)
    return None


FFMPEG = find_ffmpeg()
FFPROBE = FFMPEG.replace("ffmpeg", "ffprobe") if FFMPEG else None
BG, BG2 = "#1a1a1a", "#252525"


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("AIO Core Vision 360 — Crop & Loop Tool")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        self.cap = None
        self.video_path = None
        self.fps = 30.0
        self.total_frames = 0
        self.duration = 0.0
        self.vid_w = self.vid_h = 0
        self.is_portrait = True
        self.max_crop = 0

        self.playing = False
        self._play_job = None
        self._cur_pil = None
        self._cur_pos = 0.0

        self.trim_in = 0.0
        self.trim_out = 0.0

        self.loop_start = None
        self.loop_end = None
        self.loop_search_from = 0.0
        self.loop_search_to = 0.0

        self._src_tk = self._out_tk = None
        self._tl_w = SRC_W + 14 + OUT_W

        self._build_ui()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _btn(self, parent, text, cmd, bg="#2d2d2d", fg="white", **kw):
        return tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg,
                         activebackground="#3d3d3d", activeforeground="white",
                         relief="flat", cursor="hand2", **kw)

    def _build_ui(self):
        # ── Header
        hdr = tk.Frame(self.root, bg=BG)
        hdr.pack(fill="x", padx=14, pady=(12, 6))
        tk.Label(hdr, text="AIO Core Vision 360", bg=BG, fg="#fff",
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        self._btn(hdr, "Kies video…", self.pick_file,
                  bg="#0078d4", font=("Segoe UI", 9),
                  padx=10, pady=4).pack(side="right")
        self.lbl_file = tk.Label(hdr, text="Geen video", bg=BG, fg="#555",
                                  font=("Segoe UI", 9))
        self.lbl_file.pack(side="right", padx=10)

        # ── Previews
        pf = tk.Frame(self.root, bg=BG)
        pf.pack(padx=14, pady=(0, 6))

        lf = tk.Frame(pf, bg=BG)
        lf.pack(side="left", padx=(0, 14))
        tk.Label(lf, text="Bronvideo  (blauw kader = crop)", bg=BG, fg="#444",
                 font=("Segoe UI", 7)).pack(anchor="w", pady=(0, 2))
        self.src_canvas = tk.Canvas(lf, width=SRC_W, height=SRC_H,
                                     bg=BG2, highlightthickness=0)
        self.src_canvas.pack()

        rf = tk.Frame(pf, bg=BG)
        rf.pack(side="left")
        tk.Label(rf, text="Output  480 × 480", bg=BG, fg="#444",
                 font=("Segoe UI", 7)).pack(anchor="w", pady=(0, 2))
        self.out_canvas = tk.Canvas(rf, width=OUT_W, height=OUT_W,
                                     bg=BG2, highlightthickness=0)
        self.out_canvas.pack()

        # ── Transport
        tr = tk.Frame(self.root, bg=BG)
        tr.pack(fill="x", padx=14, pady=(0, 4))
        self.btn_play = self._btn(tr, "▶", self.toggle_play,
                                   font=("Segoe UI", 12), padx=8, pady=2)
        self.btn_play.pack(side="left")
        self._btn(tr, "⏹", self.stop,
                  font=("Segoe UI", 12), padx=8, pady=2).pack(side="left", padx=(2, 10))
        self.lbl_time = tk.Label(tr, text="0:00.0 / 0:00.0", bg=BG, fg="#aaa",
                                  font=("Segoe UI", 9, "bold"))
        self.lbl_time.pack(side="left")

        # ── Timeline
        tlf = tk.Frame(self.root, bg=BG)
        tlf.pack(fill="x", padx=14, pady=(0, 6))
        self.tl = tk.Canvas(tlf, width=self._tl_w, height=TL_H,
                             bg=BG2, highlightthickness=0, cursor="hand2")
        self.tl.pack(fill="x")
        self.tl.bind("<Button-1>", self._tl_seek)
        self.tl.bind("<B1-Motion>", self._tl_seek)

        # ── Trim
        def _trim_row(parent, label, color, trough, cmd, side="left"):
            f = tk.Frame(parent, bg=BG)
            f.pack(fill="x", padx=14, pady=(0, 3))
            tk.Label(f, text=label, bg=BG, fg=color,
                     font=("Segoe UI", 8, "bold"), width=9, anchor="w").pack(side="left")
            sl = tk.Scale(f, from_=0, to=1000, orient="horizontal",
                          bg=BG, fg=color, troughcolor=trough,
                          highlightthickness=0, showvalue=False, command=cmd)
            sl.pack(side="left", fill="x", expand=True)
            lbl = tk.Label(f, text="0:00.0", bg=BG, fg=color,
                           font=("Segoe UI", 8), width=7)
            lbl.pack(side="left")
            return sl, lbl

        self.sl_in,  self.lbl_in  = _trim_row(self.root, "Trim  IN",  "#4caf50", "#1d3520", self._on_trim_in)
        self.sl_out, self.lbl_out = _trim_row(self.root, "Trim  OUT", "#f44336", "#3d1d1d", self._on_trim_out)
        self.sl_out.set(1000)

        # ── Crop
        cf = tk.Frame(self.root, bg=BG)
        cf.pack(fill="x", padx=14, pady=(2, 6))
        tk.Label(cf, text="Crop positie", bg=BG, fg="#ccc",
                 font=("Segoe UI", 8, "bold"), width=9, anchor="w").pack(side="left")
        self.sl_crop = tk.Scale(cf, from_=0, to=100, orient="horizontal",
                                 bg=BG, fg="#0078d4", troughcolor="#1d2d3d",
                                 highlightthickness=0, showvalue=False,
                                 command=lambda _: self._refresh_preview())
        self.sl_crop.set(50)
        self.sl_crop.pack(side="left", fill="x", expand=True)
        for lbl, val in [("↑", 0), ("↕", 50), ("↓", 100)]:
            self._btn(cf, lbl, lambda v=val: (self.sl_crop.set(v), self._refresh_preview()),
                      font=("Segoe UI", 9), padx=5, pady=2).pack(side="left", padx=1)

        # ── Loop zoekbereik
        tk.Label(self.root, text="Loop zoekbereik", bg=BG, fg="#aa88cc",
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=14, pady=(4, 0))

        lsf = tk.Frame(self.root, bg=BG)
        lsf.pack(fill="x", padx=14, pady=(1, 2))
        tk.Label(lsf, text="Van", bg=BG, fg="#aa88cc",
                 font=("Segoe UI", 8), width=9, anchor="w").pack(side="left")
        self.sl_lsf = tk.Scale(lsf, from_=0, to=1000, orient="horizontal",
                                bg=BG, fg="#aa88cc", troughcolor="#2d1d3d",
                                highlightthickness=0, showvalue=False,
                                command=self._on_lsf)
        self.sl_lsf.pack(side="left", fill="x", expand=True)
        self.lbl_lsf = tk.Label(lsf, text="0:00.0", bg=BG, fg="#aa88cc",
                                 font=("Segoe UI", 8), width=7)
        self.lbl_lsf.pack(side="left")

        lst = tk.Frame(self.root, bg=BG)
        lst.pack(fill="x", padx=14, pady=(0, 6))
        tk.Label(lst, text="Tot", bg=BG, fg="#aa88cc",
                 font=("Segoe UI", 8), width=9, anchor="w").pack(side="left")
        self.sl_lst = tk.Scale(lst, from_=0, to=1000, orient="horizontal",
                                bg=BG, fg="#aa88cc", troughcolor="#2d1d3d",
                                highlightthickness=0, showvalue=False,
                                command=self._on_lst)
        self.sl_lst.set(1000)
        self.sl_lst.pack(side="left", fill="x", expand=True)
        self.lbl_lst = tk.Label(lst, text="0:00.0", bg=BG, fg="#aa88cc",
                                 font=("Segoe UI", 8), width=7)
        self.lbl_lst.pack(side="left")

        # ── Loop knoppen
        lf2 = tk.Frame(self.root, bg=BG)
        lf2.pack(fill="x", padx=14, pady=(0, 8))
        self._btn(lf2, "🔍  Zoek beste loop", self.find_loop,
                  bg="#3d2060", font=("Segoe UI", 9),
                  padx=10, pady=5).pack(side="left")
        self._btn(lf2, "▶  Preview loop", self.preview_loop,
                  bg="#1d3d1d", font=("Segoe UI", 9),
                  padx=10, pady=5).pack(side="left", padx=6)
        self.lbl_loop = tk.Label(lf2, text="Nog geen loop", bg=BG, fg="#444",
                                  font=("Segoe UI", 8))
        self.lbl_loop.pack(side="left", padx=4)

        # ── Export
        ef = tk.Frame(self.root, bg=BG)
        ef.pack(fill="x", padx=14, pady=(0, 4))
        self.btn_exp = self._btn(ef, "Export clip  (480×480)", self.export_clip,
                                  bg="#107c10", font=("Segoe UI", 9, "bold"),
                                  padx=12, pady=7, state="disabled")
        self.btn_exp.pack(side="left")
        self.btn_exp_loop = self._btn(ef, "Export loop", self.export_loop,
                                       bg="#5d1d7d", font=("Segoe UI", 9, "bold"),
                                       padx=12, pady=7, state="disabled")
        self.btn_exp_loop.pack(side="left", padx=8)

        self.lbl_status = tk.Label(self.root, text="", bg=BG, fg="#444",
                                    font=("Segoe UI", 8))
        self.lbl_status.pack(anchor="w", padx=14, pady=(0, 10))

    # ── LADEN ────────────────────────────────────────────────────────────────

    def pick_file(self):
        p = filedialog.askopenfilename(
            filetypes=[("Video", "*.mp4 *.mov *.avi *.mkv *.m4v *.MP4 *.MOV"),
                       ("Alle bestanden", "*.*")])
        if p:
            self.load_video(p)

    def load_video(self, path):
        if not FFMPEG:
            messagebox.showerror("ffmpeg niet gevonden",
                                  "Voeg de Shotcut-map (of ffmpeg) toe aan PATH.")
            return
        self.stop()
        if self.cap:
            self.cap.release()

        self.video_path = path
        self.lbl_file.config(text=Path(path).name, fg="#ddd")
        self.lbl_status.config(text="Laden…")
        self.root.update()

        self.cap = cv2.VideoCapture(path)
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.duration = self.total_frames / self.fps
        self.vid_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.vid_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.is_portrait = self.vid_h >= self.vid_w
        self.max_crop = abs(self.vid_h - self.vid_w)

        self.trim_in = 0.0
        self.trim_out = self.duration
        self.sl_in.set(0)
        self.sl_out.set(1000)
        self.lbl_in.config(text=self._fmt(0))
        self.lbl_out.config(text=self._fmt(self.duration))

        self.loop_start = self.loop_end = None
        self.loop_search_from = 0.0
        self.loop_search_to = self.duration
        self.sl_lsf.set(0)
        self.sl_lst.set(1000)
        self.lbl_lsf.config(text=self._fmt(0))
        self.lbl_lst.config(text=self._fmt(self.duration))
        self.lbl_loop.config(text="Nog geen loop")
        self.btn_exp_loop.config(state="disabled")
        self.btn_exp.config(state="normal")

        self._seek(0)
        self.lbl_status.config(
            text=f"{self.vid_w}×{self.vid_h}  ·  {self.duration:.1f}s  ·  {self.fps:.0f} fps")

    # ── AFSPELEN ─────────────────────────────────────────────────────────────

    def toggle_play(self):
        if self.playing:
            self.pause()
        else:
            self.play()

    def play(self):
        if not self.cap:
            return
        self.playing = True
        self.btn_play.config(text="⏸")
        self._tick()

    def pause(self):
        self.playing = False
        self.btn_play.config(text="▶")
        if self._play_job:
            self.root.after_cancel(self._play_job)

    def stop(self):
        self.pause()
        if self.cap:
            self._seek(self.trim_in)

    def _tick(self):
        if not self.playing or not self.cap:
            return
        ret, frame = self.cap.read()
        if not ret:
            self.stop()
            return
        pos = self.cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        if pos >= self.trim_out:
            self._seek(self.trim_in)
            self._play_job = self.root.after(int(1000 / self.fps), self._tick)
            return
        self._show(frame, pos)
        self._play_job = self.root.after(int(1000 / self.fps), self._tick)

    def _seek(self, sec):
        if not self.cap:
            return
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, int(sec * self.fps))
        ret, frame = self.cap.read()
        if ret:
            self._show(frame, sec)

    def _tl_seek(self, event):
        if not self.cap or not self.duration:
            return
        pct = max(0.0, min(1.0, event.x / self._tl_w))
        was = self.playing
        self.pause()
        self._seek(pct * self.duration)
        if was:
            self.play()

    # ── TEKENEN ──────────────────────────────────────────────────────────────

    def _show(self, cv_frame, pos):
        rgb = cv2.cvtColor(cv_frame, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        self._cur_pil = pil
        self._cur_pos = pos
        self._draw_src(pil)
        self._draw_out(pil)
        self._draw_tl(pos)
        self.lbl_time.config(text=f"{self._fmt(pos)} / {self._fmt(self.duration)}")

    def _refresh_preview(self):
        if self._cur_pil:
            self._draw_src(self._cur_pil)
            self._draw_out(self._cur_pil)

    def _crop_offset(self):
        return int(self.max_crop * self.sl_crop.get() / 100)

    def _draw_src(self, pil):
        w, h = self.vid_w, self.vid_h
        sc = min(SRC_W / w, SRC_H / h)
        dw, dh = int(w * sc), int(h * sc)
        ox, oy = (SRC_W - dw) // 2, (SRC_H - dh) // 2

        base = Image.new("RGB", (SRC_W, SRC_H), (26, 26, 26))
        base.paste(pil.resize((dw, dh), Image.LANCZOS), (ox, oy))

        off = self._crop_offset()
        if self.is_portrait:
            rx1, rx2 = ox, ox + dw
            ry1 = oy + int(off * sc)
            ry2 = oy + int((off + w) * sc)
        else:
            ry1, ry2 = oy, oy + dh
            rx1 = ox + int(off * sc)
            rx2 = ox + int((off + h) * sc)

        ov = Image.new("RGBA", (SRC_W, SRC_H), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        dim = (0, 0, 0, 155)
        if self.is_portrait:
            if ry1 > oy:      d.rectangle([rx1, oy, rx2, ry1-1], fill=dim)
            if ry2 < oy+dh:   d.rectangle([rx1, ry2+1, rx2, oy+dh], fill=dim)
        else:
            if rx1 > ox:      d.rectangle([ox, ry1, rx1-1, ry2], fill=dim)
            if rx2 < ox+dw:   d.rectangle([rx2+1, ry1, ox+dw, ry2], fill=dim)

        out = Image.alpha_composite(base.convert("RGBA"), ov).convert("RGB")
        ImageDraw.Draw(out).rectangle([rx1, ry1, rx2-1, ry2-1],
                                       outline=(0, 170, 255), width=2)
        self._src_tk = ImageTk.PhotoImage(out)
        self.src_canvas.delete("all")
        self.src_canvas.create_image(0, 0, anchor="nw", image=self._src_tk)

    def _draw_out(self, pil):
        off = self._crop_offset()
        w, h = self.vid_w, self.vid_h
        crop = pil.crop((0, off, w, off+w) if self.is_portrait else (off, 0, off+h, h))
        prev = crop.resize((OUT_W, OUT_W), Image.LANCZOS)
        self._out_tk = ImageTk.PhotoImage(prev)
        self.out_canvas.delete("all")
        self.out_canvas.create_image(0, 0, anchor="nw", image=self._out_tk)

    def _draw_tl(self, pos):
        c, w = self.tl, self._tl_w
        c.delete("all")
        c.create_rectangle(0, 0, w, TL_H, fill=BG2, outline="")

        if self.duration:
            xi = int(self.trim_in  / self.duration * w)
            xo = int(self.trim_out / self.duration * w)
            c.create_rectangle(xi, 6, xo, TL_H-6, fill="#1e2e1e", outline="")

            # Zoekbereik (paars kader)
            xs0 = int(self.loop_search_from / self.duration * w)
            xs1 = int(self.loop_search_to   / self.duration * w)
            c.create_rectangle(xs0, 2, xs1, TL_H-2, outline="#aa88cc", width=1)

            # Gevonden loop (gevuld paars)
            if self.loop_start is not None:
                xl0 = int(self.loop_start / self.duration * w)
                xl1 = int(self.loop_end   / self.duration * w)
                c.create_rectangle(xl0, 10, xl1, TL_H-10, fill="#3d1d5d", outline="")

            c.create_line(xi, 2, xi, TL_H-2, fill="#4caf50", width=2)
            c.create_line(xo, 2, xo, TL_H-2, fill="#f44336", width=2)
            xp = int(pos / self.duration * w)
            c.create_line(xp, 0, xp, TL_H, fill="#ffffff", width=2)

    # ── TRIM ─────────────────────────────────────────────────────────────────

    def _on_trim_in(self, val):
        if not self.duration: return
        self.trim_in = float(val) / 1000 * self.duration
        if self.trim_in >= self.trim_out - 0.1:
            self.trim_in = self.trim_out - 0.1
            self.sl_in.set(int(self.trim_in / self.duration * 1000))
        self.lbl_in.config(text=self._fmt(self.trim_in))
        self._draw_tl(self._cur_pos)

    def _on_trim_out(self, val):
        if not self.duration: return
        self.trim_out = float(val) / 1000 * self.duration
        if self.trim_out <= self.trim_in + 0.1:
            self.trim_out = self.trim_in + 0.1
            self.sl_out.set(int(self.trim_out / self.duration * 1000))
        self.lbl_out.config(text=self._fmt(self.trim_out))
        self._draw_tl(self._cur_pos)

    def _on_lsf(self, val):
        if not self.duration: return
        self.loop_search_from = float(val) / 1000 * self.duration
        if self.loop_search_from >= self.loop_search_to - 0.5:
            self.loop_search_from = self.loop_search_to - 0.5
            self.sl_lsf.set(int(self.loop_search_from / self.duration * 1000))
        self.lbl_lsf.config(text=self._fmt(self.loop_search_from))
        self._draw_tl(self._cur_pos)

    def _on_lst(self, val):
        if not self.duration: return
        self.loop_search_to = float(val) / 1000 * self.duration
        if self.loop_search_to <= self.loop_search_from + 0.5:
            self.loop_search_to = self.loop_search_from + 0.5
            self.sl_lst.set(int(self.loop_search_to / self.duration * 1000))
        self.lbl_lst.config(text=self._fmt(self.loop_search_to))
        self._draw_tl(self._cur_pos)

    # ── LOOP FINDER ──────────────────────────────────────────────────────────

    def find_loop(self):
        if not self.cap:
            messagebox.showwarning("Geen video", "Laad eerst een video.")
            return

        search_from = self.loop_search_from
        search_to   = self.loop_search_to
        range_sec   = search_to - search_from

        if range_sec < 2.0:
            messagebox.showwarning("Bereik te klein",
                                    "Het zoekbereik moet minstens 2 seconden zijn.")
            return

        self.lbl_loop.config(text="Zoeken…")
        self.lbl_status.config(
            text=f"Loop zoeken tussen {self._fmt(search_from)} en {self._fmt(search_to)}…")
        self.root.update()

        cap2 = cv2.VideoCapture(self.video_path)
        step      = max(1, int(self.fps * 0.5))  # sample elke ~0.5s
        min_gap   = max(int(self.fps * 1.0),      # loop min. 1s (of 20% van bereik)
                        int(self.fps * range_sec * 0.2))
        frame_from = int(search_from * self.fps)
        frame_to   = int(search_to   * self.fps)

        frames = []
        for i in range(frame_from, frame_to, step):
            cap2.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret, fr = cap2.read()
            if not ret:
                break
            thumb = cv2.resize(fr, (32, 32)).astype(np.float32)
            frames.append((i, thumb))
        cap2.release()

        if len(frames) < 2:
            messagebox.showwarning("Te weinig frames",
                                    "Vergroot het zoekbereik — te weinig frames gevonden.")
            return

        best, bi, bj = float("inf"), frames[0][0], frames[-1][0]
        for a, (fi, ti) in enumerate(frames):
            for b, (fj, tj) in enumerate(frames):
                if fj - fi < min_gap:
                    continue
                score = float(np.mean(np.abs(ti - tj)))
                if score < best:
                    best, bi, bj = score, fi, fj

        self.loop_start = bi / self.fps
        self.loop_end   = bj / self.fps
        match = max(0, 100 - best / 2.55)

        self.lbl_loop.config(
            text=f"{self._fmt(self.loop_start)} → {self._fmt(self.loop_end)}   Match: {match:.0f}%")
        self.btn_exp_loop.config(state="normal")
        self.lbl_status.config(
            text=f"Loop: {self._fmt(self.loop_start)} → {self._fmt(self.loop_end)}  ({match:.0f}% match)")
        self._draw_tl(self._cur_pos)

    def preview_loop(self):
        if self.loop_start is None:
            messagebox.showinfo("Geen loop", "Zoek eerst een loop.")
            return
        _orig_in, _orig_out = self.trim_in, self.trim_out
        self.trim_in, self.trim_out = self.loop_start, self.loop_end
        self.pause()
        self._seek(self.loop_start)
        self.play()
        # Herstel trim na de preview (wanneer de loop stopt)
        def _restore():
            if not self.playing:
                self.trim_in, self.trim_out = _orig_in, _orig_out
            else:
                self.root.after(500, _restore)
        self.root.after(500, _restore)

    # ── EXPORT ───────────────────────────────────────────────────────────────

    def _vf(self):
        off = self._crop_offset()
        w, h = self.vid_w, self.vid_h
        if self.is_portrait:
            return f"crop={w}:{w}:0:{off},scale={SCREEN}:{SCREEN}"
        return f"crop={h}:{h}:{off}:0,scale={SCREEN}:{SCREEN}"

    def _export(self, start, end, default_name):
        out = filedialog.asksaveasfilename(
            title="Opslaan als…", defaultextension=".mp4",
            initialfile=default_name, filetypes=[("MP4", "*.mp4")])
        if not out:
            return
        self.lbl_status.config(text="Exporteren…")
        self.btn_exp.config(state="disabled")
        self.btn_exp_loop.config(state="disabled")
        self.root.update()
        try:
            subprocess.run([
                FFMPEG,
                "-ss", str(start), "-i", self.video_path,
                "-t", str(end - start),
                "-vf", self._vf(),
                "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                "-y", out
            ], check=True, capture_output=True)
            self.lbl_status.config(text=f"Klaar: {Path(out).name}")
            messagebox.showinfo("Klaar!", f"Opgeslagen:\n{out}")
        except subprocess.CalledProcessError as e:
            messagebox.showerror("Export mislukt", e.stderr.decode(errors="replace"))
        finally:
            self.btn_exp.config(state="normal")
            if self.loop_start is not None:
                self.btn_exp_loop.config(state="normal")

    def export_clip(self):
        if self.video_path:
            self._export(self.trim_in, self.trim_out,
                         Path(self.video_path).stem + "_480x480.mp4")

    def export_loop(self):
        if self.video_path and self.loop_start is not None:
            self._export(self.loop_start, self.loop_end,
                         Path(self.video_path).stem + "_loop480.mp4")

    # ── HELPERS ──────────────────────────────────────────────────────────────

    @staticmethod
    def _fmt(s):
        s = abs(float(s))
        return f"{int(s//60)}:{s%60:04.1f}"


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
        app.load_video(sys.argv[1])
    root.mainloop()
