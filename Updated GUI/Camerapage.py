import cv2
import threading
import time
import customtkinter as ctk
from PIL import Image

# ── Stream config ─────────────────────────────────────────────────────────────
CAPTURE_INDEX  = 0
STREAM_WIDTH   = 640
STREAM_HEIGHT  = 480
FLOAT_WIN_W    = 720
FLOAT_WIN_H    = 580
# ─────────────────────────────────────────────────────────────────────────────


class CameraPage(ctk.CTkFrame):
    """Camera tab – shows controls; spawns a fixed-size floating stream window."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        # stream state
        self.cap           = None
        self.stream_active = False
        self.stream_thread = None
        self.float_win     = None
        self._fps_val      = 0.0

        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Centre everything vertically
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Title
        ctk.CTkLabel(
            self,
            text="Camera / VTX Live Feed",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=1, column=0, pady=(0, 6))

        ctk.CTkLabel(
            self,
            text="Opens a fixed-size floating window when streaming is active.",
            font=ctk.CTkFont(size=13),
            text_color="gray",
        ).grid(row=2, column=0, pady=(0, 24))

        # Controls card
        card = ctk.CTkFrame(self, corner_radius=12, width=360)
        card.grid(row=3, column=0)
        card.grid_propagate(False)

        # Camera index picker
        idx_row = ctk.CTkFrame(card, fg_color="transparent")
        idx_row.pack(fill="x", padx=24, pady=(20, 8))

        ctk.CTkLabel(idx_row, text="Camera index:", width=120, anchor="w").pack(side="left")
        self.cam_index_entry = ctk.CTkEntry(idx_row, width=60, placeholder_text="0")
        self.cam_index_entry.insert(0, str(CAPTURE_INDEX))
        self.cam_index_entry.pack(side="left", padx=(8, 0))

        # Resolution row
        res_row = ctk.CTkFrame(card, fg_color="transparent")
        res_row.pack(fill="x", padx=24, pady=(0, 16))

        ctk.CTkLabel(res_row, text="Resolution:", width=120, anchor="w").pack(side="left")
        self.res_combo = ctk.CTkComboBox(
            res_row,
            values=["640×480", "1280×720", "1920×1080"],
            width=130,
        )
        self.res_combo.set("640×480")
        self.res_combo.pack(side="left", padx=(8, 0))

        # Toggle button
        self.cam_btn = ctk.CTkButton(
            card,
            text="▶  Open Camera",
            width=220,
            height=44,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._toggle_camera,
        )
        self.cam_btn.pack(pady=(0, 12))

        # Status
        self.status_lbl = ctk.CTkLabel(
            card,
            text="● Camera off",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        self.status_lbl.pack(pady=(0, 20))

    # ── Toggle ────────────────────────────────────────────────────────────────
    def _toggle_camera(self):
        if self.stream_active:
            self._stop_stream()
        else:
            self._start_stream()

    # ── Start ─────────────────────────────────────────────────────────────────
    def _start_stream(self):
        # parse index
        try:
            idx = int(self.cam_index_entry.get())
        except ValueError:
            idx = 0

        # parse resolution
        res_map = {"640×480": (640, 480), "1280×720": (1280, 720), "1920×1080": (1920, 1080)}
        w, h = res_map.get(self.res_combo.get(), (640, 480))

        cap = cv2.VideoCapture(idx)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            self.status_lbl.configure(
                text=f"Cannot open camera index {idx}",
                text_color="#EF5350",
            )
            return

        self.cap           = cap
        self.stream_active = True

        self.cam_btn.configure(
            text="Close Camera",
            fg_color="#C62828",
            hover_color="#B71C1C",
        )
        self.status_lbl.configure(text="● Streaming…", text_color="#66BB6A")

        self._open_float_window()

        self.stream_thread = threading.Thread(target=self._grab_loop, daemon=True)
        self.stream_thread.start()

    # ── Floating window ───────────────────────────────────────────────────────
    def _open_float_window(self):
        root = self.winfo_toplevel()
        self.float_win = ctk.CTkToplevel(root)
        self.float_win.title("VTX Live Stream")
        self.float_win.geometry(f"{FLOAT_WIN_W}x{FLOAT_WIN_H}")
        self.float_win.resizable(False, False)          # fixed size
        self.float_win.attributes("-topmost", True)

        # Video display
        self.video_label = ctk.CTkLabel(self.float_win, text="")
        self.video_label.pack(expand=True, fill="both")

        # Bottom bar
        bar = ctk.CTkFrame(self.float_win, height=42, corner_radius=0)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self.fps_lbl = ctk.CTkLabel(
            bar, text="FPS: --", font=ctk.CTkFont(size=11), text_color="#90A4AE"
        )
        self.fps_lbl.pack(side="left", padx=14)

        ctk.CTkLabel(
            bar,
            text=f"Fixed  {FLOAT_WIN_W}×{FLOAT_WIN_H - 42}",
            font=ctk.CTkFont(size=11),
            text_color="#546E7A",
        ).pack(side="left", padx=4)


    # ── Grab loop (background thread) ─────────────────────────────────────────
    def _grab_loop(self):
        prev = time.time()
        vid_h = FLOAT_WIN_H - 42   # subtract bottom bar

        while self.stream_active:
            ok, frame = self.cap.read()
            if not ok:
                break

            now  = time.time()
            fps  = 1.0 / max(now - prev, 1e-9)
            prev = now

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img   = Image.fromarray(frame_rgb)
            pil_img.thumbnail((FLOAT_WIN_W, vid_h), Image.LANCZOS)
            ctk_img   = ctk.CTkImage(light_image=pil_img, size=pil_img.size)

            if self.stream_active and self.float_win and self.float_win.winfo_exists():
                self.float_win.after(0, self._update_frame, ctk_img, fps)

        self.winfo_toplevel().after(0, self._on_stream_ended)

    # ── Frame update (main thread) ────────────────────────────────────────────
    def _update_frame(self, ctk_img, fps: float):
        if not self.stream_active:
            return
        try:
            self.video_label.configure(image=ctk_img)
            self.video_label.image = ctk_img
            self.fps_lbl.configure(text=f"FPS: {fps:.0f}")
        except Exception:
            pass

    # ── Stop ──────────────────────────────────────────────────────────────────
    def _stop_stream(self):
        self.stream_active = False
        if self.cap:
            self.cap.release()
            self.cap = None

    def _on_stream_ended(self):
        if self.float_win and self.float_win.winfo_exists():
            self.float_win.destroy()
        self.float_win = None

        try:
            theme_fg    = ctk.ThemeManager.theme["CTkButton"]["fg_color"]
            theme_hover = ctk.ThemeManager.theme["CTkButton"]["hover_color"]
        except Exception:
            theme_fg    = ["#1f538d", "#1f538d"]
            theme_hover = ["#14375e", "#14375e"]

        self.cam_btn.configure(
            text="Open Camera",
            fg_color=theme_fg,
            hover_color=theme_hover,
        )
        self.status_lbl.configure(text="● Camera off", text_color="gray")