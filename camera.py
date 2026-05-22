import cv2
import customtkinter as ctk
from PIL import Image, ImageTk
import threading

# ── Config ────────────────────────────────────────────────────────────────────
CAPTURE_INDEX   = 0
STREAM_WIDTH    = 640
STREAM_HEIGHT   = 480
FLOAT_WIN_W     = 640   # floating window width  (px)
FLOAT_WIN_H     = 480   # floating window height (px)
# ─────────────────────────────────────────────────────────────────────────────

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class DroneApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Drone Ground Control")
        self.geometry("480x320")
        self.resizable(False, False)

        # stream state
        self.cap            = None
        self.stream_active  = False
        self.stream_thread  = None
        self.float_win      = None          # the floating Toplevel

        self._build_ui()

    # ── UI layout ─────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Header
        header = ctk.CTkLabel(
            self,
            text="Drone Ground Control Station",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        header.pack(pady=(28, 4))

        sub = ctk.CTkLabel(
            self,
            text="VTX live feed viewer",
            font=ctk.CTkFont(size=13),
            text_color="gray",
        )
        sub.pack(pady=(0, 28))

        # Camera toggle button
        self.cam_btn = ctk.CTkButton(
            self,
            text="Open Camera",
            width=200,
            height=44,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._toggle_camera,
        )
        self.cam_btn.pack(pady=8)

        # Status label
        self.status_lbl = ctk.CTkLabel(
            self,
            text="Camera: off",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        self.status_lbl.pack(pady=(12, 0))

    # ── Camera toggle ─────────────────────────────────────────────────────────
    def _toggle_camera(self):
        if self.stream_active:
            self._stop_stream()
        else:
            self._start_stream()

    # ── Start stream ──────────────────────────────────────────────────────────
    def _start_stream(self):
        cap = cv2.VideoCapture(CAPTURE_INDEX)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  STREAM_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, STREAM_HEIGHT)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            self.status_lbl.configure(
                text=f"Error: cannot open camera index {CAPTURE_INDEX}",
                text_color="red",
            )
            return

        self.cap           = cap
        self.stream_active = True

        # Update button appearance
        self.cam_btn.configure(text="⏹  Close Camera", fg_color="#D32F2F", hover_color="#B71C1C")
        self.status_lbl.configure(text="Camera: streaming…", text_color="#4CAF50")

        # Open the floating video window
        self._open_float_window()

        # Start grab loop in background thread
        self.stream_thread = threading.Thread(target=self._grab_loop, daemon=True)
        self.stream_thread.start()

    # ── Floating window ───────────────────────────────────────────────────────
    def _open_float_window(self):
        self.float_win = ctk.CTkToplevel(self)
        self.float_win.title("VTX Live Stream")
        self.float_win.geometry(f"{FLOAT_WIN_W}x{FLOAT_WIN_H}")
        self.float_win.resizable(False, False)
        # Keep on top of main window
        self.float_win.attributes("-topmost", True)
        # Intercept close button
        self.float_win.protocol("WM_DELETE_WINDOW", self._stop_stream)

        # Canvas that fills the window
        self.video_label = ctk.CTkLabel(self.float_win, text="")
        self.video_label.pack(expand=True, fill="both")

        # Bottom bar
        bar = ctk.CTkFrame(self.float_win, height=40, corner_radius=0)
        bar.pack(fill="x", side="bottom")

        self.fps_lbl = ctk.CTkLabel(bar, text="FPS: --", font=ctk.CTkFont(size=11))
        self.fps_lbl.pack(side="left", padx=12)

        close_btn = ctk.CTkButton(
            bar, text="Close", width=90, height=28,
            fg_color="#D32F2F", hover_color="#B71C1C",
            command=self._stop_stream,
        )
        close_btn.pack(side="right", padx=10, pady=6)

    # ── Grab loop (runs in background thread) ─────────────────────────────────
    def _grab_loop(self):
        import time
        prev = time.time()

        while self.stream_active:
            ok, frame = self.cap.read()
            if not ok:
                break

            # FPS calculation
            now  = time.time()
            fps  = 1.0 / max(now - prev, 1e-6)
            prev = now

            # Convert BGR → RGB → PIL → CTkImage
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img   = Image.fromarray(frame_rgb)

            # Fit the frame inside the video label area
            label_w = FLOAT_WIN_W
            label_h = FLOAT_WIN_H - 40          # subtract bottom bar

            pil_img.thumbnail((label_w, label_h), Image.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=pil_img, size=pil_img.size)

            # Schedule GUI update on main thread
            if self.stream_active and self.float_win and self.float_win.winfo_exists():
                self.float_win.after(0, self._update_frame, ctk_img, fps)

        # Stream ended — clean up from main thread
        self.after(0, self._on_stream_ended)

    # ── GUI update (main thread) ──────────────────────────────────────────────
    def _update_frame(self, ctk_img, fps: float):
        if not self.stream_active:
            return
        try:
            self.video_label.configure(image=ctk_img)
            self.video_label.image = ctk_img       # prevent GC
            self.fps_lbl.configure(text=f"FPS: {fps:.0f}")
        except Exception:
            pass

    # ── Stop stream ───────────────────────────────────────────────────────────
    def _stop_stream(self):
        self.stream_active = False
        if self.cap:
            self.cap.release()
            self.cap = None

    def _on_stream_ended(self):
        # Close the floating window (if still open)
        if self.float_win and self.float_win.winfo_exists():
            self.float_win.destroy()
        self.float_win = None

        # Reset button
        self.cam_btn.configure(
            text="Open Camera",
            fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"],
            hover_color=ctk.ThemeManager.theme["CTkButton"]["hover_color"],
        )
        self.status_lbl.configure(text="Camera: off", text_color="gray")

    # ── Quit cleanly ──────────────────────────────────────────────────────────
    def on_close(self):
        self._stop_stream()
        self.destroy()


if __name__ == "__main__":
    app = DroneApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()