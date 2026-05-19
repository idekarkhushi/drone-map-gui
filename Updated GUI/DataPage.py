import customtkinter as ctk
import tkintermapview
import tkinter as tk
import math


# ═══════════════════════════════════════════════════════════
#  HUD WIDGET
#  - All geometry is computed from (W, H) every redraw
#  - Call resize(w) from outside to trigger a proper redraw
# ═══════════════════════════════════════════════════════════
class HUDWidget(tk.Canvas):

    def __init__(self, parent, **kw):
        super().__init__(
            parent,
            bg="#0b0f18",
            highlightthickness=1,
            highlightbackground="#1e3048",
            **kw
        )

        # telemetry
        self.pitch = 0.0
        self.roll = 0.0
        self.heading = 0
        self.airspeed = 0.0
        self.altitude = 0.0
        self.vspeed = 0.0

        self._W = 230
        self._H = 180

        self.configure(width=self._W, height=self._H)

        self._draw()

    # ======================================================
    # Resize
    # ======================================================

    def resize(self, width: int):

        w = max(180, width - 12)
        h = int(w * 0.60)

        if w == self._W and h == self._H:
            return

        self._W = w
        self._H = h

        self.configure(width=w, height=h)

        self._redraw_all()

    # ======================================================
    # Public update
    # ======================================================

    def redraw(
        self,
        pitch=0.0,
        roll=0.0,
        heading=0,
        airspeed=0.0,
        altitude=0.0,
        vspeed=0.0
    ):

        self.pitch = pitch
        self.roll = roll
        self.heading = heading
        self.airspeed = airspeed
        self.altitude = altitude
        self.vspeed = vspeed

        self._redraw_all()

    # ======================================================
    # Helpers
    # ======================================================

    @property
    def cx(self):
        return self._W // 2

    @property
    def cy(self):
        return self._H // 2

    @property
    def tape_w(self):
        return int(self._W * 0.13)

    @property
    def heading_h(self):
        return int(self._H * 0.12)

    def _redraw_all(self):
        self.delete("all")
        self._draw()

    # ======================================================
    # Main draw
    # ======================================================

    def _draw(self):

        self._draw_horizon()
        self._draw_pitch_ladder()
        self._draw_roll_scale()
        self._draw_heading_tape()
        self._draw_speed_tape()
        self._draw_altitude_tape()
        self._draw_flight_path_marker()
        self._draw_crosshair()

    # ======================================================
    # Artificial Horizon
    # ======================================================

    def _draw_horizon(self):

        w = self._W
        h = self._H

        cx = self.cx
        cy = self.cy

        pitch_scale = h / 60
        pitch_offset = self.pitch * pitch_scale

        angle = math.radians(self.roll)

        length = w * 3

        x1 = -length
        y1 = pitch_offset

        x2 = length
        y2 = pitch_offset

        rx1 = x1 * math.cos(angle) - y1 * math.sin(angle)
        ry1 = x1 * math.sin(angle) + y1 * math.cos(angle)

        rx2 = x2 * math.cos(angle) - y2 * math.sin(angle)
        ry2 = x2 * math.sin(angle) + y2 * math.cos(angle)

        # SKY
        self.create_polygon(
            0, 0,
            w, 0,
            cx + rx2, cy + ry2,
            cx + rx1, cy + ry1,
            fill="#1f4f88",
            outline=""
        )

        # GROUND
        self.create_polygon(
            0, h,
            w, h,
            cx + rx2, cy + ry2,
            cx + rx1, cy + ry1,
            fill="#586d0b",
            outline=""
        )

        # Horizon line
        self.create_line(
            cx + rx1,
            cy + ry1,
            cx + rx2,
            cy + ry2,
            fill="#00d4ff",
            width=2
        )

    # ======================================================
    # Pitch Ladder
    # ======================================================

    def _draw_pitch_ladder(self):

        cx = self.cx
        cy = self.cy

        angle = math.radians(self.roll)

        scale = self._H / 60

        for deg in range(-30, 35, 5):

            if deg == 0:
                continue

            offset = (deg - self.pitch) * scale

            center_x = cx + offset * math.sin(angle)
            center_y = cy + offset * math.cos(angle)

            line_w = self._W * 0.12 if deg % 10 == 0 else self._W * 0.07

            dx = math.cos(angle) * line_w
            dy = -math.sin(angle) * line_w

            color = "#00d4ff" if deg % 10 == 0 else "#4f90aa"

            self.create_line(
                center_x - dx,
                center_y - dy,
                center_x + dx,
                center_y + dy,
                fill=color,
                width=2
            )

            if deg % 10 == 0:

                self.create_text(
                    center_x - dx - 12,
                    center_y,
                    text=str(abs(deg)),
                    fill="#00d4ff",
                    font=("Courier", 10, "bold")
                )

                self.create_text(
                    center_x + dx + 12,
                    center_y,
                    text=str(abs(deg)),
                    fill="#00d4ff",
                    font=("Courier", 10, "bold")
                )

    # ======================================================
    # Roll Scale
    # ======================================================

    def _draw_roll_scale(self):

        cx = self.cx
        cy = self.cy

        r = int(min(self._W, self._H) * 0.38)

        self.create_arc(
            cx - r,
            cy - r,
            cx + r,
            cy + r,
            start=30,
            extent=120,
            style="arc",
            outline="#4d87aa",
            width=2
        )

        for deg in [-60, -45, -30, -20, -10, 0, 10, 20, 30, 45, 60]:

            a = math.radians(90 - deg)

            inner = r - 12 if deg % 30 == 0 else r - 7

            x1 = cx + inner * math.cos(a)
            y1 = cy - inner * math.sin(a)

            x2 = cx + r * math.cos(a)
            y2 = cy - r * math.sin(a)

            self.create_line(
                x1,
                y1,
                x2,
                y2,
                fill="#00d4ff" if deg == 0 else "#4d87aa",
                width=2
            )

        # Roll pointer

        roll_a = math.radians(90 - self.roll)

        tip_x = cx + r * math.cos(roll_a)
        tip_y = cy - r * math.sin(roll_a)

        base_x = cx + (r - 14) * math.cos(roll_a)
        base_y = cy - (r - 14) * math.sin(roll_a)

        perp = math.radians(180 - self.roll)

        w = 7

        self.create_polygon(
            tip_x,
            tip_y,

            base_x + w * math.cos(perp),
            base_y - w * math.sin(perp),

            base_x - w * math.cos(perp),
            base_y + w * math.sin(perp),

            fill="#00d4ff",
            outline=""
        )

    # ======================================================
    # Crosshair
    # ======================================================

    def _draw_crosshair(self):

        cx = self.cx
        cy = self.cy

        wing = int(self._W * 0.13)

        gap = 12

        self.create_line(
            cx - wing,
            cy,
            cx - gap,
            cy,
            fill="#00d4ff",
            width=3
        )

        self.create_line(
            cx + gap,
            cy,
            cx + wing,
            cy,
            fill="#00d4ff",
            width=3
        )

        self.create_line(
            cx,
            cy + 5,
            cx,
            cy + 22,
            fill="#00d4ff",
            width=3
        )

        self.create_oval(
            cx - 3,
            cy - 3,
            cx + 3,
            cy + 3,
            fill="#00d4ff",
            outline=""
        )

    # ======================================================
    # Flight Path Marker
    # ======================================================

    def _draw_flight_path_marker(self):

        cx = self.cx
        cy = self.cy

        x = cx
        y = cy - self.vspeed * 4

        r = 10

        self.create_oval(
            x - r,
            y - r,
            x + r,
            y + r,
            outline="#00ff88",
            width=2
        )

        self.create_line(x - 18, y, x - 8, y,
                         fill="#00ff88", width=2)

        self.create_line(x + 8, y, x + 18, y,
                         fill="#00ff88", width=2)

        self.create_line(x, y - 18, x, y - 8,
                         fill="#00ff88", width=2)

    # ======================================================
    # Speed Tape
    # ======================================================

    def _draw_speed_tape(self):

        w = self.tape_w
        h = self._H

        x0 = 0
        x1 = w

        self.create_rectangle(
            x0,
            0,
            x1,
            h,
            fill="#09131d",
            outline="#1f3d55"
        )

        self.create_text(
            w // 2,
            h // 2,
            text=f"{self.airspeed:.1f}",
            fill="#ffffff",
            font=("Courier", 15, "bold")
        )

        self.create_text(
            w // 2,
            16,
            text="SPD",
            fill="#00d4ff",
            font=("Courier", 10, "bold")
        )

    # ======================================================
    # Altitude Tape
    # ======================================================

    def _draw_altitude_tape(self):

        w = self.tape_w
        h = self._H

        x0 = self._W - w
        x1 = self._W

        self.create_rectangle(
            x0,
            0,
            x1,
            h,
            fill="#09131d",
            outline="#1f3d55"
        )

        self.create_text(
            (x0 + x1) // 2,
            h // 2,
            text=f"{self.altitude:.1f}",
            fill="#ffffff",
            font=("Courier", 15, "bold")
        )

        self.create_text(
            (x0 + x1) // 2,
            16,
            text="ALT",
            fill="#00d4ff",
            font=("Courier", 10, "bold")
        )

    # ======================================================
    # Heading Tape
    # ======================================================

    def _draw_heading_tape(self):

        w = self._W
        h = self.heading_h

        y0 = self._H - h
        y1 = self._H

        self.create_rectangle(
            self.tape_w,
            y0,
            w - self.tape_w,
            y1,
            fill="#09131d",
            outline="#1f3d55"
        )

        cx = self.cx

        spacing = 22

        for i in range(-5, 6):

            hdg = (self.heading + i * 5) % 360

            x = cx + i * spacing

            self.create_line(
                x,
                y0 + 2,
                x,
                y0 + 10,
                fill="#4f90aa"
            )

            if hdg % 10 == 0:

                self.create_text(
                    x,
                    y1 - 10,
                    text=f"{hdg:03d}",
                    fill="#7ad4ff",
                    font=("Courier", 9)
                )

        self.create_polygon(
            cx - 6,
            y0 + 2,
            cx + 6,
            y0 + 2,
            cx,
            y0 + 10,
            fill="#00d4ff"
        )

        self.create_text(
            cx,
            y1 - 10,
            text=f"{self.heading:03d}°",
            fill="#ffffff",
            font=("Courier", 10, "bold")
        )


# ═══════════════════════════════════════════════════════════
#  TELEMETRY CARD  (2-column grid)
# ═══════════════════════════════════════════════════════════
class TelemetryCard(ctk.CTkFrame):
    def __init__(self, parent, label, value="0.00", unit="", **kw):
        super().__init__(parent, fg_color="#0c1a28", corner_radius=6, **kw)
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text=label,
                     font=("Courier", 14), text_color="#3a8aaa",
                     anchor="w",
                     ).grid(row=0, column=0, sticky="w", padx=8, pady=(6, 0))

        self._val = ctk.CTkLabel(self,
                                  text=f"{value} {unit}".strip(),
                                  font=("Courier", 16, "bold"),
                                  text_color="#00d4ff", anchor="w")
        self._val.grid(row=1, column=0, sticky="w", padx=8, pady=(0, 6))

    def update(self, value, unit=""):
        self._val.configure(text=f"{value} {unit}".strip())


# ═══════════════════════════════════════════════════════════
#  BATTERY WIDGET
# ═══════════════════════════════════════════════════════════
class BatteryWidget(ctk.CTkFrame):
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="#0c1a28", corner_radius=6, **kw)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="⚡  BATTERY",
                     font=("Courier", 11, "bold"), text_color="#e8b000",
                     ).grid(row=0, column=0, columnspan=2, sticky="w",
                            padx=10, pady=(8, 4))

        for col, (lbl, attr) in enumerate([("Voltage", "_volt"), ("Charge", "_pct")]):
            ctk.CTkLabel(self, text=lbl, font=("Courier", 9),
                         text_color="#6a7a8a",
                         ).grid(row=1, column=col, sticky="w", padx=10)
            lw = ctk.CTkLabel(self, text="--",
                               font=("Courier", 14, "bold"), text_color="#e8b000")
            lw.grid(row=2, column=col, sticky="w", padx=10, pady=(0, 6))
            setattr(self, attr, lw)

        self._bar = ctk.CTkProgressBar(self, height=7, corner_radius=3,
                                        fg_color="#0f2030", progress_color="#e8b000")
        self._bar.set(0)
        self._bar.grid(row=3, column=0, columnspan=2, sticky="ew",
                       padx=10, pady=(0, 10))

    def update(self, voltage, percent):
        self._volt.configure(text=f"{voltage:.1f} V")
        self._pct.configure(text=f"{percent:.0f} %")
        self._bar.set(max(0.0, min(1.0, percent / 100.0)))
        col = "#00d47f" if percent > 40 else "#ffaa00" if percent > 15 else "#ff3a3a"
        self._bar.configure(progress_color=col)


# ═══════════════════════════════════════════════════════════
#  SECTION LABEL helper
# ═══════════════════════════════════════════════════════════
def _section(parent, text, row):
    ctk.CTkLabel(parent, text=text, font=("Courier", 14, "bold"),
                 text_color="#3a7aaa",
                 ).grid(row=row, column=0, sticky="w", padx=12, pady=(8, 2))


def _divider(parent, row):
    ctk.CTkFrame(parent, height=1, fg_color="#162840"
                 ).grid(row=row, column=0, sticky="ew", padx=8, pady=1)


# ═══════════════════════════════════════════════════════════
#  DATA PAGE
# ═══════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════
#  DATA PAGE (Updated: Scrollbar Removed)
# ═══════════════════════════════════════════════════════════
class DataPage(ctk.CTkFrame):
    SIDEBAR_W = 220  

    def __init__(self, parent):
        super().__init__(parent, fg_color="#080d12")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, minsize=200, weight=1)   # sidebar – never grows
        self.grid_columnconfigure(1, weight=5)   # map – takes the rest

        # ── SIDEBAR ──────────────────────────────────────
        self._sb_outer = tk.Frame(self, bg="#060c14")
        self._sb_outer.grid(row=0, column=0, sticky="nsew")
        self._sb_outer.grid_rowconfigure(0, weight=1)
        self._sb_outer.grid_columnconfigure(0, weight=1)

        # Scrollable canvas inside sidebar (Scrollbar widget removed)
        self._sb_canvas = tk.Canvas(self._sb_outer, bg="#060c14",
                                     highlightthickness=0)
        self._sb_canvas.grid(row=0, column=0, sticky="nsew")

        # inner CTkFrame – all widgets go here
        self._sb = ctk.CTkFrame(self._sb_canvas, fg_color="#060c14", corner_radius=0)
        self._sb_win = self._sb_canvas.create_window(
            (0, 0), window=self._sb, anchor="nw", width=self.SIDEBAR_W
        )

        self._sb.bind("<Configure>", self._on_inner_configure)
        self._sb_canvas.bind("<Configure>", self._on_canvas_configure)
        self._sb_outer.bind("<Configure>", self._on_sidebar_configure)
        
        # Keep mousewheel bindings so users can still scroll using trackpad/mousewheel
        self._sb_canvas.bind_all("<MouseWheel>", self._on_scroll)
        self._sb_canvas.bind_all("<Button-4>",   self._on_scroll)
        self._sb_canvas.bind_all("<Button-5>",   self._on_scroll)

        # ── populate sidebar ──────────────────────────────
        sb = self._sb
        sb.grid_columnconfigure(0, weight=1)
        r = 0

        # HUD
        _section(sb, "HUD", r); r += 1
        self.hud = HUDWidget(sb)
        self.hud.grid(row=r, column=0, sticky="ew", padx=6, pady=(2, 6)); r += 1
        _divider(sb, r); r += 1

        # Telemetry
        _section(sb, "TELEMETRY", r); r += 1

        telem_grid = ctk.CTkFrame(sb, fg_color="transparent")
        telem_grid.grid(row=r, column=0, sticky="ew", padx=6, pady=(2, 4)); r += 1
        telem_grid.grid_columnconfigure(0, weight=1)
        telem_grid.grid_columnconfigure(1, weight=1)

        self.telem_rows = {}
        telem_items = [
            ("ALT", "Altitude",   "0.00", "m"),
            ("GS",  "Gnd Speed",  "0.00", "m/s"),
            ("VS",  "Vert Speed", "0.00", "m/s"),
            ("YAW", "Yaw",        "0.00", "°"),
            ("WP",  "Dist WP",    "0.00", "m"),
            ("MAV", "Dist MAV",   "0.00", "m"),
        ]
        for idx, (key, label, val, unit) in enumerate(telem_items):
            card = TelemetryCard(telem_grid, label=label, value=val, unit=unit)
            card.grid(row=idx // 2, column=idx % 2, sticky="ew", padx=3, pady=3)
            self.telem_rows[key] = (card, unit)

        _divider(sb, r); r += 1

        # Battery
        _section(sb, "POWER", r); r += 1
        self.battery = BatteryWidget(sb)
        self.battery.grid(row=r, column=0, sticky="ew", padx=6, pady=(2, 14)); r += 1

        # ── MAP ──────────────────────────────────────────
        map_wrap = tk.Frame(self, bg="#080d12")
        map_wrap.grid(row=0, column=1, sticky="nsew")
        map_wrap.grid_rowconfigure(0, weight=1)
        map_wrap.grid_columnconfigure(0, weight=1)

        self.map = tkintermapview.TkinterMapView(map_wrap)
        self.map.grid(row=0, column=0, sticky="nsew")
        self.map.set_position(19.0760, 72.8777)
        self.map.set_zoom(12)

    # ── scrollable sidebar internals ──────────────────────
    def _on_inner_configure(self, _e):
        # Keeps internal boundaries calculated for mouse scrolling
        self._sb_canvas.configure(scrollregion=self._sb_canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self._sb_canvas.itemconfig(self._sb_win, width=event.width)

    def _on_sidebar_configure(self, event):
        new_w = event.width
        self._sb_canvas.itemconfig(self._sb_win, width=new_w)
        self.hud.resize(new_w)

    def _on_scroll(self, event):
        if event.num == 4:
            self._sb_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._sb_canvas.yview_scroll(1, "units")
        else:
            self._sb_canvas.yview_scroll(int(-event.delta / 120), "units")

    # ── public update API ─────────────────────────────────
    def update_hud(self, pitch=0.0, roll=0.0, heading=0,
                   airspeed=0.0, altitude=0.0, vspeed=0.0):
        self.hud.redraw(pitch=pitch, roll=roll, heading=heading,
                        airspeed=airspeed, altitude=altitude, vspeed=vspeed)

    def update_telemetry(self, key: str, value: float):
        if key in self.telem_rows:
            card, unit = self.telem_rows[key]
            card.update(f"{value:.2f}", unit)

    def update_battery(self, voltage: float, percent: float):
        self.battery.update(voltage, percent)