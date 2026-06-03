import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkintermapview
import serial.tools.list_ports
import sys
import os
import csv
import xml.etree.ElementTree as ET

from HUD import HUDState, HUDRenderer
 
# ─── Appearance ──────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
 
# ─── Color Palette ────────────────────────────────────────────────────────────
BG_DARK       = "#0a0e14"
BG_PANEL      = "#0f1520"
BG_CARD       = "#131c2b"
BORDER        = "#1e2d42"
ACCENT_BLUE   = "#0d8fe0"
ACCENT_GREEN  = "#00d084"
ACCENT_RED    = "#ff3c5a"
TEXT_PRIMARY  = "#e8f0fe"
TEXT_MUTED    = "#5a7fa0"
ACTIVE_MODE   = "#0d8fe0"
 
 
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
            text=label,          # ← just the label, no icon
            command=self._click,
            height=44,
            corner_radius=8,
            fg_color=BG_CARD,
            hover_color="#1a2a3f",
            border_color=BORDER,
            border_width=1,
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Times New Roman", size=12, weight="bold"),
            **kwargs,
        )

    def _click(self):
        self._on_select(self._label)

    def set_active(self, active: bool):
        self._active = active
        if active:
            self.configure(
                fg_color="#0d2a4a",
                border_color=ACCENT_BLUE,
                text_color=ACCENT_BLUE,
                border_width=2,
            )
        else:
            self.configure(
                fg_color=BG_CARD,
                border_color=BORDER,
                text_color=TEXT_MUTED,
                border_width=1,
            )
 
 
# ═══════════════════════════════════════════════════════════════════════════════
#  LEFT PANEL
# ═══════════════════════════════════════════════════════════════════════════════
class LeftPanel(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            width=320,
            fg_color=BG_PANEL,
            corner_radius=0,
            border_width=1,
            border_color=BORDER,
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
        self.grid_rowconfigure(2, weight=0)   # flight modes
        self.grid_rowconfigure(3, weight=1)   # spacer
        self.grid_columnconfigure(0, weight=1)
 
        # ── HUD Import Area ──────────────────────────────────────────────────
        self._build_hud_area()
 
        # ── Divider ──────────────────────────────────────────────────────────
        div = ctk.CTkFrame(self, height=1, fg_color=BORDER, corner_radius=0)
        div.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 0))
 
        # ── Flight Modes ─────────────────────────────────────────────────────
        self._build_flight_modes()
 
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
 
        # ── Section label ────────────────────────────────────────────────────
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
            self.hud_canvas.after(50, _refresh_hud)  # 20 fps

        self.hud_canvas.after(100, _refresh_hud)
 
        # Store reference so caller can embed HUD widget
        self.hud_frame = hud_frame
 
    def _build_flight_modes(self):
        wrapper = ctk.CTkFrame(self, fg_color="transparent")
        wrapper.grid(row=2, column=0, sticky="ew", padx=10, pady=(8, 10))
        wrapper.grid_columnconfigure((0, 1), weight=1)
 
        # Section header
        header = ctk.CTkLabel(
            wrapper,
            text="FLIGHT MODE",
            font=ctk.CTkFont(family="Times New Roman", size=10, weight="bold"),
            text_color=TEXT_MUTED,
        )
        header.grid(row=0, column=0, columnspan=2, sticky="w", padx=4, pady=(4, 8))
 
        modes = ["Training", "Kamikaze", "Hand Launch", "Ground Launch", "High Speed"]
 
        for idx, mode in enumerate(modes):
            row = (idx // 2) + 1
            col = idx % 2
            btn = FlightModeButton(wrapper, mode, self._select_mode)
            btn.grid(row=row, column=col, sticky="ew", padx=4, pady=3)
            self._mode_buttons[mode] = btn
 
    # ── Mode selection ─────────────────────────────────────────────────────────
    def _select_mode(self, mode: str):
        if self._active_mode:
            self._mode_buttons[self._active_mode].set_active(False)
        self._active_mode = mode
        self._mode_buttons[mode].set_active(True)
 
    def get_active_mode(self) -> str | None:
        return self._active_mode
 
 
# ═══════════════════════════════════════════════════════════════════════════════
#  RIGHT PANEL  (top bar + map)
# ═══════════════════════════════════════════════════════════════════════════════
class RightPanel(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            fg_color=BG_DARK,
            corner_radius=0,
            **kwargs,
        )
        self.grid_rowconfigure(0, weight=0)  # top bar
        self.grid_rowconfigure(1, weight=1)  # map
        self.grid_columnconfigure(0, weight=1)
        self._build()
 
    # ── Build ──────────────────────────────────────────────────────────────────
    def _build(self):
        self._build_topbar()
        self._build_map()
 
    def _build_topbar(self):
        bar = ctk.CTkFrame(
            self,
            height=56,
            fg_color=BG_PANEL,
            corner_radius=0,
            border_width=1,
            border_color=BORDER,
        )
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(6, weight=1)   # push status to right
 
        # ── Serial port ───────────────────────────────────────────────────────
        port_lbl = ctk.CTkLabel(
            bar,
            text="PORT",
            font=ctk.CTkFont(family="Times New Roman", size=10, weight="bold"),
            text_color=TEXT_MUTED,
        )
        port_lbl.grid(row=0, column=0, padx=(14, 4), pady=10, sticky="w")
 
        self.port_var = tk.StringVar(value="Select port…")
        self.port_menu = ctk.CTkOptionMenu(
            bar,
            variable=self.port_var,
            values=self._get_serial_ports(),
            width=150,
            height=32,
            fg_color=BG_CARD,
            button_color="#1a2a3f",
            button_hover_color="#243a57",
            dropdown_fg_color=BG_CARD,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Times New Roman", size=11),
            corner_radius=6,
        )
        self.port_menu.grid(row=0, column=1, padx=(0, 6), pady=10, sticky="w")
 
        # Refresh button
        refresh_btn = ctk.CTkButton(
            bar,
            text="↻",
            width=32,
            height=32,
            fg_color=BG_CARD,
            hover_color="#1a2a3f",
            text_color=ACCENT_BLUE,
            font=ctk.CTkFont(size=16),
            corner_radius=6,
            command=self._refresh_ports,
        )
        refresh_btn.grid(row=0, column=2, padx=(0, 18), pady=10)
 
        # ── Mode dropdown ──────────────────────────────────────────────────────
        mode_lbl = ctk.CTkLabel(
            bar,
            text="MODE",
            font=ctk.CTkFont(family="Times New Roman", size=10, weight="bold"),
            text_color=TEXT_MUTED,
        )
        mode_lbl.grid(row=0, column=3, padx=(0, 4), pady=10, sticky="w")
 
        self.mode_var = tk.StringVar(value="LOITER")
        mode_options = ["AUTO", "GUIDED", "RTL", "LOITER"]
        self.mode_menu = ctk.CTkOptionMenu(
            bar,
            variable=self.mode_var,
            values=mode_options,
            width=140,
            height=32,
            fg_color=BG_CARD,
            button_color="#1a2a3f",
            button_hover_color="#243a57",
            dropdown_fg_color=BG_CARD,
            text_color=ACCENT_GREEN,
            font=ctk.CTkFont(family="Times New Roman", size=11, weight="bold"),
            corner_radius=6,
        )
        self.mode_menu.grid(row=0, column=4, padx=(0, 14), pady=10, sticky="w")

        # ── Load GPS File button ───────────────────────────────────────────────
        load_gps_btn = ctk.CTkButton(
            bar,
            text="Load GPS",
            width=110,
            height=32,
            fg_color=BG_CARD,
            hover_color="#1a2a3f",
            border_color=ACCENT_BLUE,
            border_width=1,
            text_color=ACCENT_BLUE,
            font=ctk.CTkFont(family="Times New Roman", size=11, weight="bold"),
            corner_radius=6,
            command=self._load_gps_file,
        )
        load_gps_btn.grid(row=0, column=5, padx=(0, 14), pady=10, sticky="w")

        # ── Status indicator ──────────────────────────────────────────────────
        self.status_dot = ctk.CTkLabel(
            bar,
            text="● DISCONNECTED",
            font=ctk.CTkFont(family="Times New Roman", size=10, weight="bold"),
            text_color=ACCENT_RED,
        )
        self.status_dot.grid(row=0, column=6, padx=(0, 14), pady=10, sticky="e")
        bar.grid_columnconfigure(6, weight=1)
 
    def _build_map(self):
        map_frame = ctk.CTkFrame(
            self,
            fg_color=BG_DARK,
            corner_radius=0,
        )
        map_frame.grid(row=1, column=0, sticky="nsew")
        map_frame.grid_rowconfigure(0, weight=1)
        map_frame.grid_columnconfigure(0, weight=1)
 
        try:
            self.map_widget = tkintermapview.TkinterMapView(
                map_frame,
                corner_radius=0,
            )
            self.map_widget.grid(row=0, column=0, sticky="nsew")
            # Default: Bangalore (adjust to your ops area)
            self.map_widget.set_position(12.9716, 77.5946)
            self.map_widget.set_zoom(13)
            # Use OpenStreetMap (works offline with tile cache)
            self.map_widget.set_tile_server(
                "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"
            )
        except Exception as e:
            # Graceful fallback if tkintermapview not installed
            fallback = ctk.CTkLabel(
                map_frame,
                text=f"[ MAP WIDGET ]\nInstall tkintermapview:\n  pip install tkintermapview\n\n{e}",
                font=ctk.CTkFont(family="Times New Roman", size=12),
                text_color="#1e3a5a",
                justify="center",
            )
            fallback.grid(row=0, column=0)
 
    # ── Helpers ────────────────────────────────────────────────────────────────
    def _load_gps_file(self):
        """Open a GPS file (GPX or CSV) and place a marker at the start point."""
        filepath = filedialog.askopenfilename(
            title="Load GPS File",
            filetypes=[
                ("GPS files", "*.gpx *.csv *.txt"),
                ("GPX files", "*.gpx"),
                ("CSV files", "*.csv *.txt"),
                ("All files", "*.*"),
            ],
        )
        if not filepath:
            return

        try:
            ext = os.path.splitext(filepath)[1].lower()
            lat, lon = None, None

            if ext == ".gpx":
                lat, lon = self._parse_gpx(filepath)
            elif ext in (".csv", ".txt"):
                lat, lon = self._parse_csv(filepath)
            else:
                # Try GPX first, fall back to CSV
                try:
                    lat, lon = self._parse_gpx(filepath)
                except Exception:
                    lat, lon = self._parse_csv(filepath)

            if lat is None or lon is None:
                messagebox.showerror(
                    "GPS Load Error",
                    "Could not find a valid GPS start point in the file.\n"
                    "Supported formats:\n"
                    "  • GPX  — standard <trkpt> or <wpt> elements\n"
                    "  • CSV  — columns named lat/lon or latitude/longitude",
                )
                return

            # ── Update map ────────────────────────────────────────────────────
            if hasattr(self, "map_widget"):
                # Remove previous start marker if any
                if hasattr(self, "_gps_start_marker") and self._gps_start_marker:
                    self._gps_start_marker.delete()

                self.map_widget.set_position(lat, lon)
                self.map_widget.set_zoom(15)
                self._gps_start_marker = self.map_widget.set_marker(
                    lat, lon,
                    text="START",
                    marker_color_circle=ACCENT_BLUE,
                    marker_color_outside=ACCENT_BLUE,
                    text_color=ACCENT_BLUE,
                )

        except Exception as exc:
            messagebox.showerror("GPS Load Error", f"Failed to parse file:\n{exc}")

    # ── GPS parsers ────────────────────────────────────────────────────────────
    def _parse_gpx(self, filepath: str):
        """Return (lat, lon) of the first track-point or waypoint in a GPX file."""
        tree = ET.parse(filepath)
        root = tree.getroot()

        # GPX namespace may vary; strip it for generic matching
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"

        # Search order: trkpt → rtept → wpt
        for tag in (f"{ns}trkpt", f"{ns}rtept", f"{ns}wpt"):
            point = root.find(f".//{tag}")
            if point is not None:
                lat = float(point.attrib["lat"])
                lon = float(point.attrib["lon"])
                return lat, lon

        return None, None

    def _parse_csv(self, filepath: str):
        """Return (lat, lon) of the first data row in a CSV/TXT GPS log."""
        with open(filepath, newline="", encoding="utf-8-sig") as f:
            # Sniff delimiter
            sample = f.read(4096)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",\t; ")
            except csv.Error:
                dialect = csv.excel  # fallback

            reader = csv.DictReader(f, dialect=dialect)
            headers = [h.strip().lower() for h in (reader.fieldnames or [])]

            # Detect lat/lon column names
            lat_key = next((h for h in headers if h in ("lat", "latitude", "lat_deg")), None)
            lon_key = next((h for h in headers if h in ("lon", "longitude", "lng", "long", "lon_deg")), None)

            if lat_key is None or lon_key is None:
                # Try positional: assume col 0 = lat, col 1 = lon (no header)
                f.seek(0)
                plain = csv.reader(f, dialect=dialect)
                for row in plain:
                    if len(row) >= 2:
                        try:
                            return float(row[0]), float(row[1])
                        except ValueError:
                            continue
                return None, None

            for row in reader:
                try:
                    # Strip whitespace from keys
                    norm = {k.strip().lower(): v for k, v in row.items()}
                    return float(norm[lat_key]), float(norm[lon_key])
                except (ValueError, KeyError):
                    continue

        return None, None

    def _get_serial_ports(self) -> list[str]:
        ports = [p.device for p in serial.tools.list_ports.comports()]
        return ports if ports else ["No ports found"]
 
    def _refresh_ports(self):
        ports = self._get_serial_ports()
        self.port_menu.configure(values=ports)
        self.port_var.set(ports[0] if ports else "No ports found")
 
    def set_connected(self, connected: bool):
        if connected:
            self.status_dot.configure(text="● CONNECTED", text_color=ACCENT_GREEN)
        else:
            self.status_dot.configure(text="● DISCONNECTED", text_color=ACCENT_RED)
 
 
# ═══════════════════════════════════════════════════════════════════════════════
#  TITLE BAR
# ═══════════════════════════════════════════════════════════════════════════════
class TitleBar(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            height=36,
            fg_color="#060b11",
            corner_radius=0,
            **kwargs,
        )
        self.grid_propagate(False)
        self.grid_columnconfigure(1, weight=1)
 
        logo = ctk.CTkLabel(
            self,
            text="GCS Dashboard",
            font=ctk.CTkFont(family="Times New Roman", size=11, weight="bold"),
            text_color=ACCENT_BLUE,
        )
        logo.grid(row=0, column=0, padx=16, pady=8, sticky="w")
 
        ver = ctk.CTkLabel(
            self,
            text="v1.0.0",
            font=ctk.CTkFont(family="Times New Roman", size=9),
            text_color=TEXT_MUTED,
        )
        ver.grid(row=0, column=1, padx=16, pady=8, sticky="e")
 
 
# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════
class GCSApp(ctk.CTk):
    def __init__(self):
        super().__init__()
 
        self.title("GCS Dashboard")
        self.geometry("1280x800")
        self.minsize(1024, 680)
        self.configure(fg_color=BG_DARK)
 
        # ── Layout grid ───────────────────────────────────────────────────────
        self.grid_rowconfigure(0, weight=0)   # title bar
        self.grid_rowconfigure(1, weight=1)   # main area
        self.grid_columnconfigure(0, weight=0)  # left panel
        self.grid_columnconfigure(1, weight=1)  # right panel
 
        # ── Widgets ───────────────────────────────────────────────────────────
        self.title_bar = TitleBar(self)
        self.title_bar.grid(row=0, column=0, columnspan=2, sticky="ew")
 
        self.left_panel = LeftPanel(self)
        self.left_panel.grid(row=1, column=0, sticky="nsew")
 
        self.right_panel = RightPanel(self)
        self.right_panel.grid(row=1, column=1, sticky="nsew")
 
        # ── Keyboard shortcuts ────────────────────────────────────────────────
        self.bind("<Escape>", lambda e: self.quit())
        self.bind("<F11>", self._toggle_fullscreen)
        self._fullscreen = False
 
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
 
 
# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = GCSApp()
    app.mainloop()