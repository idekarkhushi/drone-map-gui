import os
import sys
import threading
import customtkinter as ctk
from PIL import Image, ImageTk
import cv2

# Ensure local GUI modules can be imported when running this file directly
base_dir = os.path.dirname(os.path.abspath(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── SPLASH / INTRO VIDEO WINDOW ───────────────────────────────────────────────
class SplashScreen(ctk.CTkToplevel):
    def __init__(self, parent, video_path, on_finish):
        super().__init__(parent)
        self.on_finish = on_finish

        # ── Window setup ──────────────────────────────────────────────────
        self.overrideredirect(True)          # borderless
        self.attributes("-topmost", True)
        self.configure(fg_color="black")

        # Center on screen
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = 1200, 700
        self.geometry(f"{w}x{h}+{(sw - w)//2}+{(sh - h)//2}")

        # Canvas to draw frames on
        self.canvas = ctk.CTkCanvas(self, width=w, height=h, bg="black",
                                    highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # Click to skip
        self.canvas.bind("<Button-1>", lambda e: self._finish())

        # Start playback in a background thread
        self._playing = True
        self._cap = cv2.VideoCapture(video_path)
        self._frame_delay = int(1000 / max(self._cap.get(cv2.CAP_PROP_FPS) or 30, 1))
        self._play()

    def _play(self):
        if not self._playing:
            return

        ret, frame = self._cap.read()
        if not ret:
            # Video ended
            self._finish()
            return

        # Convert BGR → RGB → PIL → CTk-compatible PhotoImage
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)

        # Scale to canvas size while keeping aspect ratio
        cw, ch = self.winfo_width() or 1200, self.winfo_height() or 700
        img.thumbnail((cw, ch), Image.LANCZOS)

        self._photo = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(cw // 2, ch // 2, anchor="center",
                                  image=self._photo)

        # Schedule next frame
        self._after_id = self.after(self._frame_delay, self._play)

    def _finish(self):
        if not self._playing:
            return
        self._playing = False
        try:
            self.after_cancel(self._after_id)
        except Exception:
            pass
        self._cap.release()
        self.destroy()
        self.on_finish()
        
# ── MAIN APP ──────────────────────────────────────────────────────────────────        
class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Mission Planner")
        self.geometry("1200x700")
        self.minsize(900, 580)
        
        #Hide main window until splash is done
        self.withdraw()

        # DATA
        self.waypoints   = []
        self.map_markers = []
        self.table_rows  = []
        
        # ── Build UI immediately (hidden), show after splash ───────────────
        self._build_ui()
        
        # ── Play intro video ───────────────────────────────────────────────
        VIDEO_PATH = r"Updated GUI\assets\flightdesk_intro.mp4"
        
        splash = SplashScreen(self, VIDEO_PATH, on_finish=self._show_main)
        
    def _show_main(self):
        self.deiconify()  # Show main window after splash finishes
        self.show("data")  # Show default page
        
    def _build_ui(self):

        # ── TOP TOOLBAR ───────────────────────────────────────────────────
        self.toolbar = ctk.CTkFrame(self, height=34)
        self.toolbar.pack(fill="x")
        self.toolbar.pack_propagate(False)

        self.left_toolbar = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        self.left_toolbar.pack(side="left", padx=(4, 0), pady=2)

        # Connection status label on the right side of toolbar
        self.conn_status_label = ctk.CTkLabel(
            self.toolbar,
            text="No connection",
            font=ctk.CTkFont("Courier", 10),
            text_color="gray",
        )
        self.conn_status_label.pack(side="right", padx=12)

        self.icons = {
            "data":    ctk.CTkImage(Image.open(r"Updated GUI\assets\data.png"),    size=(18, 18)),
            "plan":    ctk.CTkImage(Image.open(r"Updated GUI\assets\plan.png"),    size=(18, 18)),
            "config":  ctk.CTkImage(Image.open(r"Updated GUI\assets\config.png"),  size=(18, 18)),
            "camera":  ctk.CTkImage(Image.open(r"Updated GUI\assets\camera.png"),  size=(18, 18)),
            "connect": ctk.CTkImage(Image.open(r"Updated GUI\assets\connect.png"), size=(18, 18)),
        }

        self.add_toolbar_button("DATA",   self.icons["data"],   lambda: self.show("data"))
        self.add_toolbar_button("PLAN",   self.icons["plan"],   lambda: self.show("plan"))
        self.add_toolbar_button("CONFIG", self.icons["config"], lambda: self.show("config"))
        self.add_toolbar_button("CAMERA", self.icons["camera"], lambda: self.show("camera"))

        # CONNECT button — opens the floating panel, NOT a page
        self._connect_btn = self.add_toolbar_button(
            "CONNECT", self.icons["connect"], self._toggle_connect_panel
        )

        # ── MAIN AREA ─────────────────────────────────────────────────────
        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True)

        from DataPage    import DataPage
        from PlanPage    import PlanPage
        from ConfigPage  import ConfigPage
        from Camerapage  import CameraPage
        from connectPage import ConnectPanel   # floating panel — NOT a page

        # Only real pages go in self.frames
        self.frames = {
            "data":   DataPage(self.container),
            "plan":   PlanPage(self.container),
            "config": ConfigPage(self.container),
            "camera": CameraPage(self.container),
        }
        for frame in self.frames.values():
            frame.place(relwidth=1, relheight=1)

        # ConnectPanel is a floating Toplevel — instantiate separately
        self.connect_panel = ConnectPanel(
            self,
            on_connected=self._on_connected,
            on_disconnected=self._on_disconnected,
            heartbeat_timeout=5,
        )

        self.show("data")

    # ── Connect panel callbacks ───────────────────────────────────────────

    def _toggle_connect_panel(self):
        self.connect_panel.toggle(anchor_widget=self._connect_btn)

    def _on_connected(self, conn, mode, description):
        """Called by ConnectPanel when a link is established."""
        self.conn_status_label.configure(
            text=f"● {description}", text_color="#81c784"
        )
        # Forward conn to pages that need telemetry, e.g.:
        # self.frames["data"].set_connection(conn)

    def _on_disconnected(self):
        """Called by ConnectPanel when the link drops."""
        self.conn_status_label.configure(text="No connection", text_color="gray")

    # ── Toolbar & navigation ──────────────────────────────────────────────

    def add_toolbar_button(self, text, icon, command):
        btn = ctk.CTkButton(
            self.left_toolbar, text=text, image=icon, compound="top",
            width=58, height=30, corner_radius=6, font=("Arial", 10),
            command=command,
        )
        btn.pack(side="left", padx=5, pady=0)
        return btn   # return so caller can store a reference for anchor positioning

    def show(self, name):
        self.frames[name].tkraise()


# RUN
if __name__ == "__main__":
    app = App()
    app.mainloop()