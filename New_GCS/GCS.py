import customtkinter as ctk
import tkinter as tk
from numpy import inner
import tkintermapview
import serial.tools.list_ports
import cv2
from PIL import Image, ImageTk
import sys
import math
import time
from pathlib import Path

from HUD import HUDState, HUDRenderer
from Camera import CameraControlStrip
from Actions import ActionHandler, AbortMode
from Systemstatus import SystemStatusHandler
 
# ─── Appearance ──────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BASE_DIR = Path(__file__).resolve().parent
ASSET_DIR = BASE_DIR / "assets"
 
# ─── Color Palette ────────────────────────────────────────────────────────────
BG_DARK       = "#0a0e14"
BG_PANEL      = "#0f1520"
BG_CARD       = "#131c2b"
BORDER        = "#1e2d42"
ACCENT_BLUE   = "#0d8fe0"
ACCENT_GREEN  = "#00d084"
ACCENT_RED    = "#ff3c5a"
ACCENT_CYAN   = "#00e5ff"
TEXT_PRIMARY  = "#e8f0fe"
TEXT_MUTED    = "#5a7fa0"
ACTIVE_MODE   = "#0d8fe0"
RADAR_GREEN   = "#00ff88"
 
 
# ═══════════════════════════════════════════════════════════════════════════════
#  FLIGHT MODE BUTTON
# ═══════════════════════════════════════════════════════════════════════════════
class FlightModeButton(ctk.CTkButton):
    """Single flight-mode toggle button."""

    def __init__(self, master, label: str, on_select, **kwargs):
        self._label = label
        self._on_select = on_select
        self._active = False

        super().__init__(
            master,
            text=label, command=self._click,height=44,corner_radius=8,
            fg_color=BG_CARD,hover_color="#1a2a3f",border_color=BORDER,
            border_width=1,text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Times New Roman", size=12, weight="bold"),
            **kwargs,
        )

    def _click(self):
        self._on_select(self._label)

    def set_active(self, active: bool):
        self._active = active
        if active:
            self.configure(
                fg_color="#0d2a4a",border_color=ACCENT_BLUE,
                text_color=ACCENT_BLUE,border_width=2,
            )
        else:
            self.configure(
                fg_color=BG_CARD,border_color=BORDER,
                text_color=TEXT_MUTED,border_width=1,
            )
 
 
# ═══════════════════════════════════════════════════════════════════════════════
#  LEFT PANEL
# ═══════════════════════════════════════════════════════════════════════════════
class LeftPanel(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            width=320,fg_color=BG_PANEL,corner_radius=0,
            border_width=1,border_color=BORDER,
            **kwargs,
        )
        self.grid_propagate(False)
        self._active_mode: str | None = None
        self._mode_buttons: dict[str, FlightModeButton] = {}
        self._build()

    # ── Build ──────────────────────────────────────────────────────────────────
    def _build(self):
        self.grid_rowconfigure(0, weight=0)   # HUD area
        self.grid_rowconfigure(1, weight=0)   # divider
        self.grid_rowconfigure(2, weight=1)   # tabview (expands)
        self.grid_columnconfigure(0, weight=1)

        # ── HUD Import Area ──────────────────────────────────────────────────
        self._build_hud_area()

        # ── Divider ──────────────────────────────────────────────────────────
        div = ctk.CTkFrame(self, height=1, fg_color=BORDER, corner_radius=0)
        div.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 0))

        # ── TabView ──────────────────────────────────────────────────────────
        self._build_tabview()

    def _build_hud_area(self):
        hud_frame = ctk.CTkFrame(
            self,
            fg_color=BG_CARD,
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
        )
        hud_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 8))
        hud_frame.grid_columnconfigure(0, weight=1)

        lbl_header = ctk.CTkLabel(
            hud_frame,
            text="HUD",
            font=ctk.CTkFont(family="Times New Roman", size=10, weight="bold"),
            text_color=TEXT_MUTED,
        )
        lbl_header.grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))

        self.hud_canvas = tk.Canvas(
            hud_frame,
            bg="#0b131e",
            highlightthickness=0,
            height=200,
        )
        self.hud_canvas.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))

        self.hud_state = HUDState()

        def _refresh_hud():
            w = self.hud_canvas.winfo_width()
            h = self.hud_canvas.winfo_height()
            HUDRenderer.render(self.hud_canvas, self.hud_state, w, h)
            self.hud_canvas.after(50, _refresh_hud)

        self.hud_canvas.after(100, _refresh_hud)
        self.hud_frame = hud_frame

    def _build_tabview(self):
        self.tabview = ctk.CTkTabview(
            self,
            fg_color=BG_CARD,
            segmented_button_fg_color=BG_PANEL,
            segmented_button_selected_color=ACCENT_BLUE,
            segmented_button_selected_hover_color="#0b7ac4",
            segmented_button_unselected_color=BG_PANEL,
            segmented_button_unselected_hover_color="#1a2a3f",
            text_color=TEXT_PRIMARY,
            text_color_disabled=TEXT_MUTED,
            border_color=BORDER,
            border_width=1,
            corner_radius=10,
        )
        self.tabview.grid(row=2, column=0, sticky="nsew", padx=10, pady=(8, 10))

        # ── Tab 1: Flight Mode ────────────────────────────────────────────────
        tab_fm = self.tabview.add("Flight Mode")
        tab_fm.grid_columnconfigure((0, 1), weight=1)

        modes = ["Training", "Kamikaze", "Hand Launch", "Ground Launch", "High Speed"]
        for idx, mode in enumerate(modes):
            row = idx // 2
            col = idx % 2
            btn = FlightModeButton(tab_fm, mode, self._select_mode)
            btn.grid(row=row, column=col, sticky="ew", padx=4, pady=3)
            self._mode_buttons[mode] = btn

        # ── Tab 2: Messages ───────────────────────────────────────────────────
        tab_msg = self.tabview.add("Messages")
        tab_msg.grid_rowconfigure(0, weight=1)
        tab_msg.grid_columnconfigure(0, weight=1)

        self.msg_box = ctk.CTkTextbox(
            tab_msg,
            fg_color="#0b131e",
            text_color=ACCENT_GREEN,
            font=ctk.CTkFont(family="Courier New", size=11),
            corner_radius=6,
            border_color=BORDER,
            border_width=1,
            state="disabled",       # read-only
            wrap="word",
        )
        self.msg_box.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        # Seed with a boot message
        self._append_message("System", "GCS initialised. Awaiting flight mode selection.")

    # ── Mode selection ─────────────────────────────────────────────────────────
    def _select_mode(self, mode: str):
        # Deactivate previous button
        if self._active_mode:
            self._mode_buttons[self._active_mode].set_active(False)
        self._active_mode = mode
        self._mode_buttons[mode].set_active(True)

        # Log to Messages tab
        self._append_message("FLIGHT MODE", f"Selected → {mode}")

        # Switch to Messages tab so the pilot sees the confirmation
        self.tabview.set("Messages")

    def _append_message(self, source: str, text: str):
        """Append a timestamped line to the Messages textbox."""
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] [{source}] {text}\n"
        self.msg_box.configure(state="normal")
        self.msg_box.insert("end", line)
        self.msg_box.see("end")          # auto-scroll to latest
        self.msg_box.configure(state="disabled")

    def get_active_mode(self) -> str | None:
        return self._active_mode

    # ── Public helper so other modules can push messages ──────────────────────
    def log_message(self, source: str, text: str):
        self._append_message(source, text)
 
# ═══════════════════════════════════════════════════════════════════════════════
#  CENTRE PANEL  (map — was RightPanel, now occupies the middle column)
# ═══════════════════════════════════════════════════════════════════════════════
class CentrePanel(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=BG_DARK, corner_radius=0, **kwargs)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._build()

    def _build(self):
        try:
            self.map_widget = tkintermapview.TkinterMapView(self, corner_radius=0)
            self.map_widget.grid(row=0, column=0, sticky="nsew")
            self.map_widget.set_position(28.6139, 77.2090)
            self.map_widget.set_zoom(13)
            self.map_widget.set_tile_server(
                "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"
            )
        except Exception as e:
            fallback = ctk.CTkLabel(
                self,
                text=f"[ MAP ]\npip install tkintermapview\n\n{e}",
                font=ctk.CTkFont(family="Times New Roman", size=12),
                text_color="#1e3a5a",
                justify="center",
            )
            fallback.grid(row=0, column=0)
            
    def update_gps_position(self, lat, lon):
        if not hasattr(self, "map_widget"):
            return

        self.map_widget.set_position(lat, lon)

        if hasattr(self, "_vehicle_marker"):
            self._vehicle_marker.delete()

        self._vehicle_marker = self.map_widget.set_marker(
            lat,
            lon,
            text="AIRCRAFT",
            marker_color_circle=ACCENT_GREEN,
            marker_color_outside=ACCENT_GREEN,
        )

# ═══════════════════════════════════════════════════════════════════════════════
#  TITLE BAR  (now includes port, refresh, load GPS)
# ═══════════════════════════════════════════════════════════════════════════════
class TitleBar(ctk.CTkFrame):
    def __init__(self, master, centre_panel=None, **kwargs):
        super().__init__(
            master,
            height=40,
            fg_color="#060b11",
            corner_radius=0,
            border_width=1,
            border_color=BORDER,
            **kwargs,
        )
        self.grid_propagate(False)
        self._centre = centre_panel

        # col layout: logo | spacer | PORT label | port menu | refresh | divider | load gps | version
        self.grid_columnconfigure(1, weight=1)

        # ── Logo ──────────────────────────────────────────────────────────────
        ctk.CTkLabel(
            self,
            text="GCS DASHBOARD",
            font=ctk.CTkFont(family="Times New Roman", size=11, weight="bold"),
            text_color=ACCENT_BLUE,
        ).grid(row=0, column=0, padx=(14, 0), pady=0, sticky="w")

        # ── PORT label ────────────────────────────────────────────────────────
        ctk.CTkLabel(
            self,
            text="PORT",
            font=ctk.CTkFont(family="Times New Roman", size=9, weight="bold"),
            text_color=TEXT_MUTED,
        ).grid(row=0, column=2, padx=(0, 4), pady=0, sticky="e")

        # ── Port dropdown ─────────────────────────────────────────────────────
        self.port_var = tk.StringVar(value="Select port…")
        self.port_menu = ctk.CTkOptionMenu(
            self,
            variable=self.port_var,values=self._get_serial_ports(),
            width=140,height=26,
            fg_color=BG_CARD,button_color="#1a2a3f",button_hover_color="#243a57",
            dropdown_fg_color=BG_CARD,text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Times New Roman", size=10),corner_radius=5,
        )
        self.port_menu.grid(row=0, column=3, padx=(0, 4), pady=7)

        # ── Refresh button ────────────────────────────────────────────────────
        ctk.CTkButton(
            self,
            text="↻",
            width=26,
            height=26,
            fg_color=BG_CARD,
            hover_color="#1a2a3f",
            text_color=ACCENT_BLUE,
            font=ctk.CTkFont(size=14),
            corner_radius=5,
            command=self._refresh_ports,
        ).grid(row=0, column=4, padx=(0, 10), pady=7)

        # ── Thin divider ──────────────────────────────────────────────────────
        div = ctk.CTkFrame(self, width=1, height=22, fg_color=BORDER, corner_radius=0)
        div.grid(row=0, column=5, padx=(0, 10), pady=9)

        # ── Version ───────────────────────────────────────────────────────────
        ctk.CTkLabel(
            self,
            text="v1.0.0",
            font=ctk.CTkFont(family="Times New Roman", size=9),
            text_color=TEXT_MUTED,
        ).grid(row=0, column=7, padx=(0, 14), pady=0, sticky="e")

    def _get_serial_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        return ports if ports else ["No ports found"]

    def _refresh_ports(self):
        ports = self._get_serial_ports()
        self.port_menu.configure(values=ports)
        self.port_var.set(ports[0] if ports else "No ports found")

    def set_centre(self, centre_panel):
        """Late-bind centre panel after construction."""
        self._centre = centre_panel


# ═══════════════════════════════════════════════════════════════════════════════
#  RIGHT PANEL  —  Radar overview  +  Camera feed
# ═══════════════════════════════════════════════════════════════════════════════
class RightPanel(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            width=300,
            fg_color=BG_PANEL,
            corner_radius=0,
            border_width=1,
            border_color=BORDER,
            **kwargs,
        )
        self.grid_propagate(False)
        self.grid_rowconfigure(0, weight=1)   # radar  — takes upper half
        self.grid_rowconfigure(1, weight=1)   # camera — takes lower half
        self.grid_columnconfigure(0, weight=1)
        
        # camera_strip is injected by GCSApp after construction
        self._camera_strip: CameraControlStrip | None = None
        
        self._build()

    # ── build ──────────────────────────────────────────────────────────────────
    def _build(self):
        self._build_radar()
        self._build_camera()

    # ── Radar ──────────────────────────────────────────────────────────────────
    def _build_radar(self):
        outer = ctk.CTkFrame(
            self,
            fg_color=BG_CARD,
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
        )
        outer.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 4))
        outer.grid_rowconfigure(1, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        # header row
        hdr = ctk.CTkFrame(outer, fg_color="transparent", height=28)
        hdr.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 0))
        hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            hdr,
            text="RADAR OVERVIEW",
            font=ctk.CTkFont(family="Times New Roman", size=10, weight="bold"),
            text_color=TEXT_MUTED,
        ).grid(row=0, column=0, sticky="w")

        self.radar_status = ctk.CTkLabel(
            hdr,
            text="● ACTIVE",
            font=ctk.CTkFont(family="Times New Roman", size=9, weight="bold"),
            text_color=ACCENT_GREEN,
        )
        self.radar_status.grid(row=0, column=1, sticky="e")

        # canvas — backend will draw on this
        self.radar_canvas = tk.Canvas(
            outer,
            bg="#060d15",
            highlightthickness=0,
        )
        self.radar_canvas.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 8))

        # placeholder sweep lines drawn at idle so the frame looks non-empty
        self.radar_canvas.bind("<Configure>", self._draw_radar_placeholder)

        self.radar_outer = outer

    def _draw_radar_placeholder(self, event=None):
        c = self.radar_canvas
        c.delete("placeholder")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 4 or h < 4:
            return
        cx, cy = w // 2, h // 2
        r_max = min(cx, cy) - 6

        # concentric rings
        for i in range(1, 5):
            r = r_max * i // 4
            c.create_oval(
                cx - r, cy - r, cx + r, cy + r,
                outline="#0d3a2a", width=1, tags="placeholder",
            )
        # crosshairs
        c.create_line(cx, cy - r_max, cx, cy + r_max,
                      fill="#0d3a2a", width=1, tags="placeholder")
        c.create_line(cx - r_max, cy, cx + r_max, cy,
                      fill="#0d3a2a", width=1, tags="placeholder")
        # static sweep line
        import math
        angle = math.radians(45)
        c.create_line(
            cx, cy,
            cx + r_max * math.cos(angle),
            cy - r_max * math.sin(angle),
            fill=RADAR_GREEN, width=1, tags="placeholder",
        )
        # centre dot
        c.create_oval(cx - 3, cy - 3, cx + 3, cy + 3,
                      fill=RADAR_GREEN, outline="", tags="placeholder")
        # label
        c.create_text(
            cx, cy + r_max + 14,
            text="awaiting radar backend…",
            fill=TEXT_MUTED,
            font=("Times New Roman", 9),
            tags="placeholder",
        )

    # ── Camera ─────────────────────────────────────────────────────────────────
    def _build_camera(self):
        """
        Card layout (rows):
          0 – header bar  (CAMERA FEED label + status pill)
          1 – cam_canvas  (video frame, expands to fill)
          2 – control strip (index / resolution / start-stop / fps)
        """
        outer = ctk.CTkFrame(
            self, fg_color=BG_CARD, corner_radius=10,
            border_width=1, border_color=BORDER,
        )
        outer.grid(row=1, column=0, sticky="nsew", padx=10, pady=(4, 10))
        outer.grid_rowconfigure(1, weight=1)   # canvas expands
        outer.grid_rowconfigure(2, weight=0)   # control strip fixed height
        outer.grid_columnconfigure(0, weight=1)
 
        # header
        hdr = ctk.CTkFrame(outer, fg_color="transparent", height=28)
        hdr.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 0))
        hdr.grid_columnconfigure(1, weight=1)
 
        ctk.CTkLabel(
            hdr, text="CAMERA FEED",
            font=ctk.CTkFont(family="Times New Roman", size=10, weight="bold"),
            text_color= TEXT_MUTED,
        ).grid(row=0, column=0, sticky="w")
 
        self.cam_status = ctk.CTkLabel(
            hdr, text="● NO SIGNAL",
            font=ctk.CTkFont(family="Times New Roman", size=9, weight="bold"),
            text_color=ACCENT_RED,
        )
        self.cam_status.grid(row=0, column=1, sticky="e")
 
        # video canvas
        self.cam_canvas = tk.Canvas(
            outer, bg="#060d15", highlightthickness=0,
        )
        self.cam_canvas.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 0))
        self.cam_canvas.bind("<Configure>", self._draw_cam_placeholder)
 
        # control strip placeholder frame — filled by inject_camera_strip()
        self._cam_strip_slot = ctk.CTkFrame(
            outer, fg_color=BG_CARD, height=36, corner_radius=0,
        )
        self._cam_strip_slot.grid(row=2, column=0, sticky="ew", padx=0, pady=(2, 6))
        self._cam_strip_slot.grid_propagate(False)
        self._cam_strip_slot.grid_columnconfigure(0, weight=1)
 
        self.cam_outer = outer
 
    def _draw_cam_placeholder(self, event=None):
        c = self.cam_canvas
        c.delete("ph")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 4 or h < 4:
            return
        for x in range(0, w, 24):
            c.create_line(x, 0, x, h, fill="#0d1e2e", width=1, tags="ph")
        for y in range(0, h, 24):
            c.create_line(0, y, w, y, fill="#0d1e2e", width=1, tags="ph")
        cx, cy = w // 2, h // 2
        c.create_line(cx-20, cy, cx+20, cy, fill="#1a3a5a", width=1, tags="ph")
        c.create_line(cx, cy-20, cx, cy+20, fill="#1a3a5a", width=1, tags="ph")
        c.create_oval(cx-4, cy-4, cx+4, cy+4, outline="#1a3a5a", width=1, tags="ph")
        for bx, by, dx, dy in [(8,8,1,1),(w-8,8,-1,1),(8,h-8,1,-1),(w-8,h-8,-1,-1)]:
            c.create_line(bx, by, bx+dx*14, by, fill="#1a3a5a", width=1, tags="ph")
            c.create_line(bx, by, bx, by+dy*14, fill="#1a3a5a", width=1, tags="ph")
        c.create_text(cx, cy+28, text="awaiting camera backend…",
                      fill=TEXT_MUTED, font=("Times New Roman", 9), tags="ph")
 
    # ── Public: inject the control strip (called by GCSApp) ───────────────────
    def inject_camera_strip(self, strip: "CameraControlStrip"):
        """Place the already-constructed CameraControlStrip into the card."""
        self._camera_strip = strip
        strip.grid(in_=self._cam_strip_slot, row=0, column=0, sticky="ew")
 
    # ── Public: receive a frame from CameraBackend ────────────────────────────
    def update_camera_frame(self, photo_image: tk.PhotoImage):
        """Push a PhotoImage frame onto the camera canvas."""
        c = self.cam_canvas
        c.delete("ph")
        c.delete("frame")
        c._img = photo_image   # keep reference to prevent GC
        cw = c.winfo_width()
        ch = c.winfo_height()
        # centre the image in the canvas
        c.create_image(cw // 2, ch // 2, anchor="center",
                       image=photo_image, tags="frame")
        
    # ── Public: radar helper ──────────────────────────────────────────────────
    def set_radar_active(self, active: bool):
        if active:
            self.radar_status.configure(text="● ACTIVE", text_color=ACCENT_GREEN)
        else:
            self.radar_status.configure(text="● OFFLINE", text_color=ACCENT_RED)


# ─── rebuild camera placeholder with a proper canvas ──────────────────────────
# Replace the tk.Label in _build_camera with a tk.Canvas for crisp placeholder:
# (patch applied inline — no separate file needed)
_orig_build_camera = RightPanel._build_camera

def _patched_build_camera(self):
    outer = ctk.CTkFrame(
        self,
        fg_color=BG_CARD,
        corner_radius=10,
        border_width=1,
        border_color=BORDER,
    )
    outer.grid(row=1, column=0, sticky="nsew", padx=10, pady=(4, 10))
    outer.grid_rowconfigure(1, weight=1)
    outer.grid_columnconfigure(0, weight=1)

    hdr = ctk.CTkFrame(outer, fg_color="transparent", height=28)
    hdr.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 0))
    hdr.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(
        hdr,
        text="CAMERA FEED",
        font=ctk.CTkFont(family="Times New Roman", size=10, weight="bold"),
        text_color=TEXT_MUTED,
    ).grid(row=0, column=0, sticky="w")

    self.cam_status = ctk.CTkLabel(
        hdr,
        text="● NO SIGNAL",
        font=ctk.CTkFont(family="Times New Roman", size=9, weight="bold"),
        text_color=ACCENT_RED,
    )
    self.cam_status.grid(row=0, column=1, sticky="e")

    # use Canvas so we can draw the placeholder and later display frames
    self.cam_canvas = tk.Canvas(
        outer,
        bg="#060d15",
        highlightthickness=0,
    )
    self.cam_canvas.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 8))
    self.cam_canvas.bind("<Configure>", self._draw_cam_canvas_placeholder)

    self.cam_outer = outer

def _draw_cam_canvas_placeholder(self, event=None):
    c = self.cam_canvas
    c.delete("ph")
    w = c.winfo_width()
    h = c.winfo_height()
    if w < 4 or h < 4:
        return
    # grid
    for x in range(0, w, 24):
        c.create_line(x, 0, x, h, fill="#0d1e2e", width=1, tags="ph")
    for y in range(0, h, 24):
        c.create_line(0, y, w, y, fill="#0d1e2e", width=1, tags="ph")
    # centre crosshair
    cx, cy = w // 2, h // 2
    c.create_line(cx - 20, cy, cx + 20, cy, fill="#1a3a5a", width=1, tags="ph")
    c.create_line(cx, cy - 20, cx, cy + 20, fill="#1a3a5a", width=1, tags="ph")
    c.create_oval(cx - 4, cy - 4, cx + 4, cy + 4,
                  outline="#1a3a5a", width=1, tags="ph")
    # corner brackets
    for bx, by, dx, dy in [(8,8,1,1),(w-8,8,-1,1),(8,h-8,1,-1),(w-8,h-8,-1,-1)]:
        c.create_line(bx, by, bx+dx*14, by, fill="#1a3a5a", width=1, tags="ph")
        c.create_line(bx, by, bx, by+dy*14, fill="#1a3a5a", width=1, tags="ph")
    c.create_text(
        cx, cy + 28,
        text="awaiting camera backend…",
        fill=TEXT_MUTED,
        font=("Times New Roman", 9),
        tags="ph",
    )

def update_camera_frame_v2(self, photo_image: tk.PhotoImage):
    """Push a PhotoImage frame from your camera backend."""
    self.cam_canvas.delete("ph")
    self.cam_canvas.delete("frame")
    self.cam_canvas._img = photo_image
    self.cam_canvas.create_image(0, 0, anchor="nw", image=photo_image, tags="frame")
    self.cam_status.configure(text="● LIVE", text_color=ACCENT_GREEN)

# monkey-patch cleaner canvas approach onto RightPanel
RightPanel._build_camera = _patched_build_camera
RightPanel._draw_cam_canvas_placeholder = _draw_cam_canvas_placeholder
RightPanel._draw_camera_placeholder = _draw_cam_canvas_placeholder
RightPanel.update_camera_frame = update_camera_frame_v2


# ═══════════════════════════════════════════════════════════════════════════════
#  BOTTOM PANEL  —  3 frames: Interceptor Control · Action · System status
# ═══════════════════════════════════════════════════════════════════════════════
class BottomPanel(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(
            master, height=160, fg_color=BG_PANEL, corner_radius=0,
            border_width=1, border_color=BORDER, **kwargs,
        )
        self.grid_propagate(False)    # ← THIS is the critical line
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=2)
        self.grid_columnconfigure(2, weight=1)
        self.grid_columnconfigure(3, weight=2)
        self._build()

    def _build(self):
        self._build_ready()
        self._build_action()
        self._build_system_status()

    # ── helpers ────────────────────────────────────────────────────────────────
    def _section(self, col: int, title: str, accent: str, span: int = 1):
        card = ctk.CTkFrame(
            self, fg_color=BG_CARD, corner_radius=10,
            border_width=1, border_color=BORDER,
        )
        card.grid(row=0, column=col, columnspan=span, sticky="nsew",
                padx=(10 if col == 0 else 3, 10 if col == 3 else 3), pady=4)
        card.grid_rowconfigure(0, weight=0)
        card.grid_rowconfigure(1, weight=1)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(family="Times New Roman", size=9, weight="bold"),
            text_color=accent,
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(4, 2))

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 4))
        inner.grid_columnconfigure(0, weight=1)
        return inner

    def _status_row(self, parent, row: int, label: str, value: str, color: str):
        ctk.CTkLabel(
            parent,
            text=label,
            font=ctk.CTkFont(family="Times New Roman", size=9),
            text_color=TEXT_MUTED,
            anchor="w",
        ).grid(row=row, column=0, sticky="w")
        lbl = ctk.CTkLabel(
            parent,
            text=value,
            font=ctk.CTkFont(family="Times New Roman", size=9, weight="bold"),
            text_color=color,
            anchor="e",
        )
        lbl.grid(row=row, column=1, sticky="e")
        return lbl

    # ── Frame 1:Interceptor Control  ───────────────────────────────────────────
    def _build_ready(self):
        inner = self._section(0, "INTERCEPTOR CONTROL", TEXT_MUTED, span=2)
        inner.grid_rowconfigure(0, weight=0)
        inner.grid_rowconfigure(1, weight=1)
        inner.grid_columnconfigure(0, weight=1)

        self.interceptor_status_label = ctk.CTkLabel(
            inner,
            font=ctk.CTkFont(family="Times New Roman", size=11, weight="bold"),
            text_color=ACCENT_GREEN,
            anchor="w",
        )
        self.interceptor_status_label.grid(row=0, column=0, sticky="ew", pady=(0, 4), padx=(4, 0))

        # ── Video canvas ──────────────────────────────────────────────────────────
        self.video_canvas = tk.Canvas(
            inner,
            bg=BG_CARD,
            highlightthickness=0,
        )
        self.video_canvas.grid(row=1, column=0, sticky="nsew", padx=0, pady=(0, 2))

        # ── Start video loop ──────────────────────────────────────────────────────
        self._video_cap = None
        self._video_path = str(ASSET_DIR / "Missile _Video.mp4")
        self._video_after_id = None
        self._video_started = False

        # Wait until canvas has real dimensions before starting
        self.video_canvas.bind("<Configure>", self._on_video_canvas_ready)

    def _start_video(self):
        """Open the video file and begin the frame loop."""
        try:
            self._video_cap = cv2.VideoCapture(self._video_path)
            if not self._video_cap.isOpened():
                self._draw_video_placeholder("Video not found")
                return
            fps = self._video_cap.get(cv2.CAP_PROP_FPS) or 30
            self._video_frame_delay = max(16, int(1000 / fps))
            self._pump_video_frame()
        except Exception as e:
            self._draw_video_placeholder(str(e))

    def _pump_video_frame(self):
        """Decode one frame, display it, schedule the next."""
        cap = self._video_cap
        if cap is None or not cap.isOpened():
            return

        ret, frame = cap.read()
        if not ret:
            # Loop: rewind to start
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
            if not ret:
                return

        c = self.video_canvas
        cw = c.winfo_width()
        ch = c.winfo_height()
        if cw < 4 or ch < 4:
            self._video_after_id = c.after(self._video_frame_delay, self._pump_video_frame)
            return

        # Resize frame to fit canvas, preserving aspect ratio
        frame_rgba = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
        visible_mask = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) > 18
        coords = cv2.findNonZero(visible_mask.astype("uint8"))

        if coords is not None:
            x, y, w, h = cv2.boundingRect(coords)
            pad = 12
            x0 = max(0, x - pad)
            y0 = max(0, y - pad)
            x1 = min(frame_rgba.shape[1], x + w + pad)
            y1 = min(frame_rgba.shape[0], y + h + pad)
            frame_rgba = frame_rgba[y0:y1, x0:x1]
            visible_mask = visible_mask[y0:y1, x0:x1]

        frame_rgba[:, :, 3] = (visible_mask * 255).astype("uint8")

        fh, fw = frame_rgba.shape[:2]
        scale = max((cw * 0.96) / fw, (ch * 0.88) / fh)
        nw, nh = max(1, int(fw * scale)), max(1, int(fh * scale))
        frame_resized = cv2.resize(frame_rgba, (nw, nh), interpolation=cv2.INTER_LINEAR)

        # BGR → RGB → PhotoImage
        pil_img = Image.fromarray(frame_resized)
        photo = ImageTk.PhotoImage(pil_img)

        c.delete("vframe")
        c._photo = photo  # prevent GC
        c.create_image(cw // 2, ch // 2, anchor="center", image=photo, tags="vframe")

        self._video_after_id = c.after(self._video_frame_delay, self._pump_video_frame)

    def _draw_video_placeholder(self, msg: str = "no video"):
        c = self.video_canvas
        c.delete("all")
        w, h = c.winfo_width() or 160, c.winfo_height() or 70
        c.create_text(w // 2, h // 2, text=f"[ {msg} ]",
                    fill=TEXT_MUTED, font=("Times New Roman", 9))
        
    def _on_video_canvas_ready(self, event):
        if not self._video_started and event.width > 10 and event.height > 10:
            self._video_started = True
            self._start_video()

    
    # ── Frame 2: Action ────────────────────────────────────────────────────────
    def _build_action(self):
        inner = self._section(2, "ACTION", TEXT_MUTED)
        inner.grid_columnconfigure(0, weight=1)
        inner.grid_rowconfigure((0, 1), weight=1)

        self.launch_icon = ctk.CTkImage(
            light_image=Image.open(ASSET_DIR / "Launch.png"),
            dark_image=Image.open(ASSET_DIR / "Launch_white.png"),
            size=(22, 22)
        )
        self.abort_icon = ctk.CTkImage(
            light_image=Image.open(ASSET_DIR / "Abort.png"),
            dark_image=Image.open(ASSET_DIR / "Abort.png"),
            size=(22, 22)
        )

        self.launch_btn = ctk.CTkButton(
            inner, text="LAUNCH", image=self.launch_icon, compound="left",
            height=40, fg_color="#0a1f0e", hover_color="#243a57",
            border_color="#0d5a1e", border_width=1, text_color=ACCENT_GREEN,
            font=ctk.CTkFont(family="Times New Roman", size=12, weight="bold"),
            corner_radius=6,
        )
        self.launch_btn.grid(row=0, column=0, sticky="ew", pady=(0, 3))

        self.abort_btn = ctk.CTkButton(
            inner, text="ABORT", image=self.abort_icon, compound="left",
            height=40, fg_color="#1f0a0a", hover_color="#243a57",
            border_color="#5a0d0d", border_width=1, text_color=ACCENT_RED,
            font=ctk.CTkFont(family="Times New Roman", size=12, weight="bold"),
            corner_radius=6,
        )
        self.abort_btn.grid(row=1, column=0, sticky="ew")

    # ── Frame 3: System status ─────────────────────────────────────────────────
    def _build_system_status(self):
        inner = self._section(3, "SYSTEM STATUS", TEXT_MUTED)
        inner.grid_columnconfigure((0, 1), weight=1)
        inner.grid_rowconfigure((0, 1), weight=1) 

        self._sys_rows = {}
        rows = [
            ("Battery",   "OFFLINE", ACCENT_RED),
            ("Altitude",  "OFFLINE", ACCENT_RED),
            ("Speed",     "OFFLINE", ACCENT_GREEN),
            ("Distance",  "OFFLINE", ACCENT_GREEN),
        ]
        for i, (lbl, val, color) in enumerate(rows):
            r = i // 2
            c = i % 2
            self._sys_rows[lbl] = self._sys_badge(inner, r, c, lbl, val, color)

    def _sys_badge(self, parent, row, col, label, value, color):
        
        parent.grid_rowconfigure(row, weight=1)
        parent.grid_columnconfigure(col, weight=1)
        
        f = ctk.CTkFrame(
            parent, fg_color=BG_CARD, corner_radius=8,
            border_width=1, border_color=color,
        )
        f.grid(row=row, column=col, sticky="nsew",
               padx=(0, 3) if col == 0 else (3, 0),
               pady=(0, 3) if row == 0 else 0)
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
             f, text=label,
            font=ctk.CTkFont(family="Times New Roman", size=10),
            text_color=TEXT_MUTED, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=4, pady=(1, 0))

        val_lbl = ctk.CTkLabel(
            f, text=value,
            font=ctk.CTkFont(family="Times New Roman", size=9, weight="bold"),
            text_color=color, anchor="w",
        )
        # Store the frame too so we can update border colour live if needed
        val_lbl.grid(row=1, column=0, sticky="w", padx=5, pady=(1, 4))
        return val_lbl
        

    # ── Public API called by GCSApp ───────────────────────────────────────────
    
        
    def update_status_badge(self, key: str, value: str, color: str):
        """
        Thread-safe entry point — call this from ANY thread.
        Schedules the actual widget update on the Tkinter main thread.
        """
        self.after(0, self._apply_status_badge, key, value, color)
 
    def _apply_status_badge(self, key: str, value: str, color: str):
        if key not in self._sys_rows:
            return
        frame = self._sys_rows[key]
        frame._value_label.configure(text=value, text_color=color)
        frame.configure(border_color=color)
 
    def get_active_launch_mode(self) -> str | None:
        return self._active_launch
 
# ═══════════════════════════════════════════════════════════════════════════════
#  TITLE BAR
# ═══════════════════════════════════════════════════════════════════════════════
class TitleBar(ctk.CTkFrame):
    def __init__(self, master, centre_panel=None, **kwargs):
        super().__init__(
            master,
            height=40,
            fg_color="#060b11",
            corner_radius=0,
            border_width=1,
            border_color=BORDER,
            **kwargs,
        )
        self.grid_propagate(False)
        self._centre = centre_panel

        # col layout: logo | spacer | PORT label | port menu | refresh | divider | load gps | version
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self,
            text="GCS DASHBOARD",
            font=ctk.CTkFont(family="Times New Roman", size=11, weight="bold"),
            text_color=ACCENT_BLUE,
        ).grid(row=0, column=0, padx=(14, 0), pady=0, sticky="w")

        ctk.CTkLabel(
            self,
            text="PORT",
            font=ctk.CTkFont(family="Times New Roman", size=9, weight="bold"),
            text_color=TEXT_MUTED,
        ).grid(row=0, column=2, padx=(0, 4), pady=0, sticky="e")

        self.port_var = tk.StringVar(value="Select port…")
        self.port_menu = ctk.CTkOptionMenu(
            self,
            variable=self.port_var,
            values=self._get_serial_ports(),
            width=140,
            height=26,
            fg_color=BG_CARD,
            button_color="#1a2a3f",
            button_hover_color="#243a57",
            dropdown_fg_color=BG_CARD,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Times New Roman", size=10),
            corner_radius=5,
        )
        self.port_menu.grid(row=0, column=3, padx=(0, 4), pady=7)

        ctk.CTkButton(
            self,
            text="REFRESH",
            width=36,
            height=26,
            fg_color=BG_CARD,
            hover_color="#1a2a3f",
            text_color=ACCENT_BLUE,
            font=ctk.CTkFont(size=10),
            corner_radius=5,
            command=self._refresh_ports,
        ).grid(row=0, column=4, padx=(0, 10), pady=7)

        div = ctk.CTkFrame(self, width=1, height=22, fg_color=BORDER, corner_radius=0)
        div.grid(row=0, column=5, padx=(0, 10), pady=9)

        ctk.CTkLabel(
            self,
            text="v1.0.0",
            font=ctk.CTkFont(family="Times New Roman", size=9),
            text_color=TEXT_MUTED,
        ).grid(row=0, column=7, padx=(0, 14), pady=0, sticky="e")

    def _get_serial_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        return ports if ports else ["No ports found"]

    def _refresh_ports(self):
        ports = self._get_serial_ports()
        self.port_menu.configure(values=ports)
        self.port_var.set(ports[0] if ports else "No ports found")

    def set_centre(self, centre_panel):
        self._centre = centre_panel
 
 
# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════
class GCSApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.iconbitmap(str(ASSET_DIR / "Aeromac.ico"))
 
        self.title("GCS Dashboard")
        self.geometry("1280x800")
        self.minsize(1024, 680)
        self.configure(fg_color=BG_DARK)
 
        # ── Layout grid ───────────────────────────────────────────────────────
        self.grid_rowconfigure(0, weight=0)   # title bar
        self.grid_rowconfigure(1, weight=1)   # main panels
        self.grid_rowconfigure(2, weight=0)   # bottom panel
        self.grid_columnconfigure(0, weight=0)  # left  (~320 px)
        self.grid_columnconfigure(1, weight=1)  # centre (flex)
        self.grid_columnconfigure(2, weight=0)  # right  (~300 px)
 
        # ── Widgets ───────────────────────────────────────────────────────────
        self.centre_panel = CentrePanel(self)
        self.centre_panel.grid(row=1, column=1, sticky="nsew")
        
        self.title_bar = TitleBar(self, centre_panel=self.centre_panel)
        self.title_bar.grid(row=0, column=0, columnspan=3, sticky="ew")

        self.left_panel = LeftPanel(self)
        self.left_panel.grid(row=1, column=0, sticky="nsew")

        self.right_panel = RightPanel(self)
        self.right_panel.grid(row=1, column=2, sticky="nsew")

        self.bottom_panel = BottomPanel(self)
        self.bottom_panel.grid(row=2, column=0, columnspan=3, sticky="ew")
        
        # ── ActionsHandler ───────────────────────────────────────────────
        self._action_handler = ActionHandler()
        self._wire_action_handler()

        # ── SystemStatusHandler ───────────────────────────────────────────────
        self._status_handler = SystemStatusHandler()
        self._wire_status_handler()

        # ── Keyboard shortcuts ────────────────────────────────────────────────
        self.bind("<Escape>", lambda e: self.quit())
        self.bind("<F11>", self._toggle_fullscreen)
        self._fullscreen = False
        
        self._connect_status_handler_udp()
    
    # ── Actions wiring ───────────────────────────────────────────────────
    def _wire_action_handler(self):
        ah = self._action_handler

        # Launch messages
        ah.on_launch_status = (
            lambda msg, ok:
            self.left_panel.after(
                0,
                self.left_panel.log_message,
                "LAUNCH",
                msg
            )
        )

        # Abort messages
        ah.on_abort_status = (
            lambda msg, ok:
            self.left_panel.after(
                0,
                self.left_panel.log_message,
                "ABORT",
                msg
            )
        )

        # State changes
        ah.on_state_change = (
            lambda state:
            self.left_panel.after(
                0,
                self.left_panel.log_message,
                "STATE",
                f"State → {state}"
            )
        )
        
    # ── SystemStatus wiring ───────────────────────────────────────────────────
 
    def _wire_status_handler(self):
        bp = self.bottom_panel

        self._status_handler.on_status = bp.update_status_badge

        self._status_handler.on_gps = (
            lambda lat, lon:
            self.centre_panel.after(
                0,
                self.centre_panel.update_gps_position,
                lat,
                lon
            )
        )
 
    def _connect_status_handler_udp(self):
        import threading
 
        def _try_connect():
            ok = self._status_handler.connect(
                connection_string="udp:127.0.0.1:14550",
                timeout=5,
            )
            if ok:
                self._status_handler.start()
                self.left_panel.log_message("SYS", "Telemetry connected → udp:14550")
            else:
                self.left_panel.after(
                    0, self.left_panel.log_message,
                    "SYS", "Telemetry offline — connect manually via ConnectPanel",
                )
 
        threading.Thread(target=_try_connect, daemon=True).start()
 
    # ── Public: attach an existing connection (call from ConnectPanel) ─────────
    def attach_mavlink(self, master):
        """
        Pass in the pymavlink master object already opened by ConnectPanel.
        The handler will poll the shared message cache — no port conflict.
        """
        self._status_handler.attach_connection(master)
        self._status_handler.start()

        self._action_handler.attach_connection(master)
        self.left_panel.log_message("SYS", "Telemetry attached to active connection.")
 
    def _toggle_fullscreen(self, _=None):
        self._fullscreen = not self._fullscreen
        self.attributes("-fullscreen", self._fullscreen)
 
    # ── Public API ─────────────────────────────────────────────────────────────
    def embed_hud(self, hud_widget_class):
        hud = hud_widget_class(self.left_panel.hud_placeholder)
        hud.pack(fill="both", expand=True)
 
    def get_selected_port(self) -> str:
        return self.right_panel.port_var.get()
 
    def get_selected_mode(self) -> str:
        return self.right_panel.mode_var.get()
 
    def get_flight_mode(self) -> str | None:
        return self.left_panel.get_active_mode()
    
    def on_closing(self):
        # Stop video playback
        bp = self.bottom_panel
        if hasattr(bp, '_video_after_id') and bp._video_after_id:
            bp.video_canvas.after_cancel(bp._video_after_id)
        if hasattr(bp, '_video_cap') and bp._video_cap:
            bp._video_cap.release()

        self._status_handler.disconnect()
        self.destroy()
 
 
# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = GCSApp()
    app.mainloop()
