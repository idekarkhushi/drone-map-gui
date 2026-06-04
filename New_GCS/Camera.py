import cv2
import threading
import time
import tkinter as tk
import customtkinter as ctk
from PIL import Image
 
# ── Default capture settings ──────────────────────────────────────────────────
_DEFAULT_INDEX  = 0
_DEFAULT_W      = 640
_DEFAULT_H      = 480
 
_RES_MAP = {
    "640×480":   (640,  480),
    "1280×720":  (1280, 720),
    "1920×1080": (1920, 1080),
}
 
# ── Colour tokens (must match GCS palette) ────────────────────────────────────
BG_CARD      = "#131c2b"
BG_PANEL     = "#0f1520"
BORDER       = "#1e2d42"
ACCENT_BLUE  = "#0d8fe0"
ACCENT_GREEN = "#00d084"
ACCENT_RED   = "#ff3c5a"
TEXT_PRIMARY = "#e8f0fe"
TEXT_MUTED   = "#5a7fa0"
 
 
# ═══════════════════════════════════════════════════════════════════════════════
#  BACKEND  —  runs on a daemon thread, fires callback on the Tk event loop
# ═══════════════════════════════════════════════════════════════════════════════
class CameraBackend:
 
    def __init__(self, tk_root: tk.Misc):
        self._root          = tk_root
        self._cap           = None
        self._active        = False
        self._thread        = None
 
        # public callbacks — assign before calling start()
        self.on_frame:  callable = None   # (photo_image: tk.PhotoImage, fps: float)
        self.on_status: callable = None   # (text: str, color: str)
 
    # ── public API ─────────────────────────────────────────────────────────────
    @property
    def is_active(self) -> bool:
        return self._active
 
    def start(self, index: int = _DEFAULT_INDEX,
              width: int = _DEFAULT_W, height: int = _DEFAULT_H):
        if self._active:
            return
 
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)   # CAP_DSHOW on Win; falls back on Linux
        if not cap.isOpened():
            cap = cv2.VideoCapture(index)               # retry without backend hint
 
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)
 
        if not cap.isOpened():
            self._fire_status(f"Cannot open camera {index}", ACCENT_RED)
            return
 
        self._cap    = cap
        self._active = True
        self._fire_status("● LIVE", ACCENT_GREEN)
 
        self._thread = threading.Thread(
            target=self._grab_loop,
            args=(width, height),
            daemon=True,
        )
        self._thread.start()
 
    def stop(self):
        self._active = False
        # thread will exit on next iteration; cap released inside loop
        self._fire_status("● NO SIGNAL", ACCENT_RED)
 
    # ── internal ───────────────────────────────────────────────────────────────
    def _grab_loop(self, disp_w: int, disp_h: int):
        prev = time.time()
 
        while self._active:
            ok, frame = self._cap.read()
            if not ok:
                break
 
            now  = time.time()
            fps  = 1.0 / max(now - prev, 1e-9)
            prev = now
 
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img   = Image.fromarray(frame_rgb)
            pil_img.thumbnail((disp_w, disp_h), Image.LANCZOS)
 
            # Convert to tk.PhotoImage on the main thread
            self._root.after(0, self._deliver_frame, pil_img, fps)
 
        # cleanup
        if self._cap:
            self._cap.release()
            self._cap = None
        self._active = False
        self._root.after(0, self._fire_status, "● NO SIGNAL", ACCENT_RED)
 
    def _deliver_frame(self, pil_img: Image.Image, fps: float):
        if not self.on_frame:
            return
        # Build PhotoImage on the main thread (required by Tk)
        photo = self._pil_to_photo(pil_img)
        self.on_frame(photo, fps)
 
    @staticmethod
    def _pil_to_photo(pil_img: Image.Image) -> tk.PhotoImage:
        """Convert PIL image → tk.PhotoImage without ImageTk dependency."""
        # Use ImageTk if available for speed; otherwise fall back to PPM trick
        try:
            from PIL import ImageTk
            return ImageTk.PhotoImage(pil_img)
        except ImportError:
            import io, base64
            buf = io.BytesIO()
            pil_img.save(buf, format="PPM")
            return tk.PhotoImage(data=base64.b64encode(buf.getvalue()))
 
    def _fire_status(self, text: str, color: str):
        if self.on_status:
            self.on_status(text, color)
 
 
# ═══════════════════════════════════════════════════════════════════════════════
#  CONTROL STRIP  —  tiny CTkFrame with index / resolution / toggle / fps
# ═══════════════════════════════════════════════════════════════════════════════
class CameraControlStrip(ctk.CTkFrame):
 
    def __init__(self, parent, right_panel, tk_root, **kwargs):
        super().__init__(
            parent,
            fg_color=BG_CARD,
            corner_radius=0,
            **kwargs,
        )
        self._rp   = right_panel
        self._root = tk_root
 
        self._backend = CameraBackend(tk_root)
        self._backend.on_frame  = self._on_frame
        self._backend.on_status = self._on_status
 
        self._build()
 
    # ── build ──────────────────────────────────────────────────────────────────
    def _build(self):
        self.grid_columnconfigure(4, weight=1)   # fps label takes remaining space
 
        # ── Camera index ──────────────────────────────────────────────────────
        ctk.CTkLabel(
            self,
            text="IDX",
            font=ctk.CTkFont(family="Times New Roman", size=9, weight="bold"),
            text_color=TEXT_MUTED,
        ).grid(row=0, column=0, padx=(8, 2), pady=6)
 
        self._idx_entry = ctk.CTkEntry(
            self,
            width=36,
            height=24,
            font=ctk.CTkFont(size=11),
            fg_color=BG_PANEL,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
            corner_radius=4,
        )
        self._idx_entry.insert(0, str(_DEFAULT_INDEX))
        self._idx_entry.grid(row=0, column=1, padx=(0, 6), pady=6)
 
        # ── Resolution ────────────────────────────────────────────────────────
        self._res_combo = ctk.CTkComboBox(
            self,
            values=list(_RES_MAP.keys()),
            width=100,
            height=24,
            font=ctk.CTkFont(size=10),
            fg_color=BG_PANEL,
            border_color=BORDER,
            button_color=BORDER,
            button_hover_color="#243a57",
            dropdown_fg_color=BG_PANEL,
            text_color=TEXT_PRIMARY,
            corner_radius=4,
        )
        self._res_combo.set("640×480")
        self._res_combo.grid(row=0, column=2, padx=(0, 6), pady=6)
 
        # ── Toggle button ─────────────────────────────────────────────────────
        self._btn = ctk.CTkButton(
            self,
            text="Start",
            width=72,
            height=24,
            font=ctk.CTkFont(family="Times New Roman", size=10, weight="bold"),
            fg_color="#0a2a10",
            hover_color="#0d3a18",
            border_color=ACCENT_GREEN,
            border_width=1,
            text_color=ACCENT_GREEN,
            corner_radius=4,
            command=self._toggle,
        )
        self._btn.grid(row=0, column=3, padx=(0, 6), pady=6)
 
        # ── FPS label ─────────────────────────────────────────────────────────
        self._fps_lbl = ctk.CTkLabel(
            self,
            text="FPS: --",
            font=ctk.CTkFont(family="Times New Roman", size=9),
            text_color=TEXT_MUTED,
            anchor="e",
        )
        self._fps_lbl.grid(row=0, column=4, padx=(0, 8), pady=6, sticky="e")
 
    # ── toggle ─────────────────────────────────────────────────────────────────
    def _toggle(self):
        if self._backend.is_active:
            self._backend.stop()
            self._btn.configure(
                text="Start",
                fg_color="#0a2a10",
                hover_color="#0d3a18",
                border_color=ACCENT_GREEN,
                text_color=ACCENT_GREEN,
            )
        else:
            try:
                idx = int(self._idx_entry.get())
            except ValueError:
                idx = 0
            w, h = _RES_MAP.get(self._res_combo.get(), (_DEFAULT_W, _DEFAULT_H))
            self._backend.start(idx, w, h)
            self._btn.configure(
                text="Stop",
                fg_color="#2a0a0a",
                hover_color="#3a0d0d",
                border_color=ACCENT_RED,
                text_color=ACCENT_RED,
            )
 
    # ── callbacks ──────────────────────────────────────────────────────────────
    def _on_frame(self, photo: tk.PhotoImage, fps: float):
        self._fps_lbl.configure(text=f"FPS: {fps:.0f}")
        if self._rp:
            self._rp.update_camera_frame(photo)
 
    def _on_status(self, text: str, color: str):
        if self._rp and hasattr(self._rp, "cam_status"):
            self._rp.cam_status.configure(text=text, text_color=color)
        # also reset button if backend died unexpectedly
        if text != "● LIVE":
            self._btn.configure(
                text="Start",
                fg_color="#0a2a10",
                hover_color="#0d3a18",
                border_color=ACCENT_GREEN,
                text_color=ACCENT_GREEN,
            )
            self._fps_lbl.configure(text="FPS: --")
 
    # ── public ─────────────────────────────────────────────────────────────────
    def stop(self):
        """Call on app exit to cleanly release the capture device."""
        self._backend.stop()