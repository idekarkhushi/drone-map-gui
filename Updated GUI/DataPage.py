import customtkinter as ctk
import tkintermapview
import tkinter as tk
import math

from core.battery import BatteryHandler

from Hud_core import HUDRenderer, HUDState
from preflight import PreflightChecker

import threading


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

        self._W = 230
        self._H = 180
        self.configure(width=self._W, height=self._H)
 
        # All telemetry lives here – set any field directly
        self.state = HUDState()
 
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

        self._draw()

    # ----------------------------------------------------------
    # Public update – accepts the same kwargs as before PLUS
    # any HUDState field for the extended telemetry.
    # ----------------------------------------------------------
    def redraw(
        self,
        pitch: float        = None,
        roll: float         = None,
        heading: float      = None,
        airspeed: float     = None,
        altitude: float     = None,
        vspeed: float       = None,
        # ── extended fields ───────────────────────────────────
        groundspeed: float  = None,
        targetspeed: float  = None,
        targetalt: float    = None,
        targetheading: float = None,
        groundcourse: float = None,
        groundalt: float    = None,
        verticalspeed: float = None,
        batterylevel: float = None,
        batteryremaining: float = None,
        current: float      = None,
        batterylevel2: float = None,
        batteryremaining2: float = None,
        current2: float     = None,
        batterycellcount: int = None,
        lowvoltagealert: bool = None,
        criticalvoltagealert: bool = None,
        gpsfix: float       = None,
        gpshdop: float      = None,
        gpsfix2: float      = None,
        gpshdop2: float     = None,
        xtrack_error: float = None,
        turnrate: float     = None,
        disttowp: float     = None,
        wpno: int           = None,
        mode: str           = None,
        linkqualitygcs: float = None,
        vibex: float        = None,
        vibey: float        = None,
        vibez: float        = None,
        ekfstatus: float    = None,
        prearmstatus: bool  = None,
        status: bool        = None,
        safetyactive: bool  = None,
        failsafe: bool      = None,
        connected: bool     = None,
        load: float         = None,
        message: str        = None,
        message_color: str  = None,
        lowairspeed: bool   = None,
        lowgroundspeed: bool = None,
        AOA: float          = None,
        SSA: float          = None,
        distunit: str       = None,
        speedunit: str      = None,
        altunit: str        = None,
        # display toggles
        displayheading: bool   = None,
        displayspeed: bool     = None,
        displayalt: bool       = None,
        displayconninfo: bool  = None,
        displayxtrack: bool    = None,
        displayrollpitch: bool = None,
        displaygps: bool       = None,
        bgon: bool             = None,
        batteryon: bool        = None,
        batteryon2: bool       = None,
        displayekf: bool       = None,
        displayvibe: bool      = None,
        displayprearm: bool    = None,
        displayAOASSA: bool    = None,
        displayCellVoltage: bool = None,
    ):
        s = self.state
 
        # ── attitude ──────────────────────────────────────────
        if pitch        is not None: s.pitch        = pitch
        if roll         is not None: s.roll         = roll
        if heading      is not None: s.heading      = float(heading)
        # legacy alias: altitude → alt
        if altitude     is not None: s.alt          = altitude
        # legacy alias: vspeed → verticalspeed
        if vspeed       is not None: s.verticalspeed = vspeed
 
        # ── extended ──────────────────────────────────────────
        if airspeed          is not None: s.airspeed          = airspeed
        if groundspeed       is not None: s.groundspeed       = groundspeed
        if targetspeed       is not None: s.targetspeed       = targetspeed
        if targetalt         is not None: s.targetalt         = targetalt
        if targetheading     is not None: s.targetheading     = targetheading
        if groundcourse      is not None: s.groundcourse      = groundcourse
        if groundalt         is not None: s.groundalt         = groundalt
        if verticalspeed     is not None: s.verticalspeed     = verticalspeed
        if batterylevel      is not None: s.batterylevel      = batterylevel
        if batteryremaining  is not None: s.batteryremaining  = batteryremaining
        if current           is not None: s.current           = current
        if batterylevel2     is not None: s.batterylevel2     = batterylevel2
        if batteryremaining2 is not None: s.batteryremaining2 = batteryremaining2
        if current2          is not None: s.current2          = current2
        if batterycellcount  is not None: s.batterycellcount  = batterycellcount
        if lowvoltagealert   is not None: s.lowvoltagealert   = lowvoltagealert
        if criticalvoltagealert is not None: s.criticalvoltagealert = criticalvoltagealert
        if gpsfix            is not None: s.gpsfix            = gpsfix
        if gpshdop           is not None: s.gpshdop           = gpshdop
        if gpsfix2           is not None: s.gpsfix2           = gpsfix2
        if gpshdop2          is not None: s.gpshdop2          = gpshdop2
        if xtrack_error      is not None: s.xtrack_error      = xtrack_error
        if turnrate          is not None: s.turnrate          = turnrate
        if disttowp          is not None: s.disttowp          = disttowp
        if wpno              is not None: s.wpno              = wpno
        if mode              is not None: s.set_mode(mode)
        if linkqualitygcs    is not None: s.linkqualitygcs    = linkqualitygcs
        if vibex             is not None: s.vibex             = vibex
        if vibey             is not None: s.vibey             = vibey
        if vibez             is not None: s.vibez             = vibez
        if ekfstatus         is not None: s.ekfstatus         = ekfstatus
        if prearmstatus      is not None: s.prearmstatus      = prearmstatus
        if status            is not None: s.status            = status
        if safetyactive      is not None: s.safetyactive      = safetyactive
        if failsafe          is not None: s.failsafe          = failsafe
        if connected         is not None: s.connected         = connected
        if load              is not None: s.load              = load
        if message           is not None: s.message           = message
        if message_color     is not None: s.message_color     = message_color
        if lowairspeed       is not None: s.lowairspeed       = lowairspeed
        if lowgroundspeed    is not None: s.lowgroundspeed    = lowgroundspeed
        if AOA               is not None: s.AOA               = AOA
        if SSA               is not None: s.SSA               = SSA
        if distunit          is not None: s.distunit          = distunit
        if speedunit         is not None: s.speedunit         = speedunit
        if altunit           is not None: s.altunit           = altunit
        # toggles
        if displayheading    is not None: s.displayheading    = displayheading
        if displayspeed      is not None: s.displayspeed      = displayspeed
        if displayalt        is not None: s.displayalt        = displayalt
        if displayconninfo   is not None: s.displayconninfo   = displayconninfo
        if displayxtrack     is not None: s.displayxtrack     = displayxtrack
        if displayrollpitch  is not None: s.displayrollpitch  = displayrollpitch
        if displaygps        is not None: s.displaygps        = displaygps
        if bgon              is not None: s.bgon              = bgon
        if batteryon         is not None: s.batteryon         = batteryon
        if batteryon2        is not None: s.batteryon2        = batteryon2
        if displayekf        is not None: s.displayekf        = displayekf
        if displayvibe       is not None: s.displayvibe       = displayvibe
        if displayprearm     is not None: s.displayprearm     = displayprearm
        if displayAOASSA     is not None: s.displayAOASSA     = displayAOASSA
        if displayCellVoltage is not None: s.displayCellVoltage = displayCellVoltage
 
        self._draw()
        
    # ----------------------------------------------------------
    # Internal
    # ----------------------------------------------------------
    def _draw(self):
        HUDRenderer.render(self, self.state, self._W, self._H)

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

        # ── Tab view: Telemetry + Messages ────────────────────────
        _section(sb, "DATA", r); r += 1

        self._tabs = ctk.CTkTabview(sb, height=220, fg_color="#060c14",
                                    segmented_button_fg_color="#0c1a28",
                                    segmented_button_selected_color="#1a3a5c",
                                    segmented_button_selected_hover_color="#1f4870",
                                    segmented_button_unselected_color="#0c1a28",
                                    segmented_button_unselected_hover_color="#12243a",
                                    text_color="#00d4ff",
                                    text_color_disabled="#3a5a7a",
                                    corner_radius=8)
        self._tabs.grid(row=r, column=0, sticky="ew", padx=6, pady=(2, 4)); r += 1
        self._tabs.add("Telemetry")
        self._tabs.add("Messages")
        self._tabs.set("Telemetry")   # default tab

        # ── Telemetry tab contents ────────────────────────────────
        telem_tab = self._tabs.tab("Telemetry")
        telem_tab.grid_columnconfigure(0, weight=1)

        telem_grid = ctk.CTkFrame(telem_tab, fg_color="transparent")
        telem_grid.grid(row=0, column=0, sticky="ew", padx=2, pady=4)
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

        # ── Messages tab contents ─────────────────────────────────
        msg_tab = self._tabs.tab("Messages")
        msg_tab.grid_rowconfigure(0, weight=1)
        msg_tab.grid_columnconfigure(0, weight=1)

        self._msg_box = tk.Text(
            msg_tab,
            bg="#060c14", fg="#b0cce0",
            font=("Courier", 10),
            relief="flat",
            state="disabled",
            wrap="word",
            highlightthickness=0,
            insertbackground="#00d4ff",
            selectbackground="#1a3a5c",
            height=10
        )
        self._msg_box.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        # colour tags for severity levels
        self._msg_box.tag_config("INFO",  foreground="#7ad4ff")
        self._msg_box.tag_config("WARN",  foreground="#ffcc44")
        self._msg_box.tag_config("ERROR", foreground="#ff5555")
        self._msg_box.tag_config("OK",    foreground="#00d47f")
        
        #preflight 
        run_btn = ctk.CTkButton(
            msg_tab,
            text="Run PreFlight Checks",
            font=("Courier", 12, "bold"),
            fg_color="#1a3a5c",
            hover_color="#1f4870",
            text_color="#00d4ff",
            height=32,
            command=self._run_preflight
        )
        run_btn.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 4))

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
        
        # Battery handler
        self.battery_handler = BatteryHandler()
        self.after(1000, self.update_battery_ui)
        
        self._mav_conn = None
        self.after(100, self._telemetry_tick)

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
                   airspeed=0.0, altitude=0.0, vspeed=0.0, **extra):
        self.hud.redraw(pitch=pitch, roll=roll, heading=heading,
                        airspeed=airspeed, altitude=altitude, vspeed=vspeed, **extra)

    def update_telemetry(self, key: str, value: float):
        if key in self.telem_rows:
            card, unit = self.telem_rows[key]
            card.update(f"{value:.2f}", unit)

    def set_connection(self, conn, mode=None, description=""):
        self._mav_conn = conn
        if self.battery_handler.attach_connection(conn):
            self.battery_handler.start()
            source = f"{mode} connection" if mode else "connection"
            self.append_message(f"Battery monitor attached to {source}", "OK")

    def clear_connection(self):
        self._mav_conn = None
        self.battery_handler.disconnect()
        self.append_message("Battery monitor disconnected", "INFO")
        
    def _telemetry_tick(self):
        if self._mav_conn is not None:
            try:
                for _ in range(10):
                    msg = self._mav_conn.recv_match(blocking=False)
                    if msg is None:
                        break
                    mtype = msg.get_type()

                    if mtype == "ATTITUDE":
                        self.hud.redraw(
                            pitch   = math.degrees(msg.pitch),
                            roll    = math.degrees(msg.roll),
                            heading = math.degrees(msg.yaw) % 360,
                        )
                    elif mtype == "VFR_HUD":
                        self.hud.redraw(
                            airspeed    = msg.airspeed,
                            altitude    = msg.alt,
                            vspeed      = msg.climb,
                            groundspeed = msg.groundspeed,
                            heading     = msg.heading,
                        )
                    elif mtype == "GPS_RAW_INT":
                        self.hud.redraw(gpsfix=msg.fix_type)

                    elif mtype == "SYS_STATUS":
                        self.hud.redraw(
                            batterylevel     = msg.voltage_battery / 1000.0,
                            current          = msg.current_battery / 100.0,
                            batteryremaining = msg.battery_remaining,
                        )
                    elif mtype == "HEARTBEAT":
                        from pymavlink import mavutil
                        armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                        self.hud.redraw(status=armed)

                    elif mtype == "GLOBAL_POSITION_INT":
                        self.update_telemetry("ALT", msg.relative_alt / 1000.0)
                        self.update_telemetry("VS",  msg.vz / 100.0)

                    elif mtype == "NAV_CONTROLLER_OUTPUT":
                        self.hud.redraw(
                            xtrack_error  = msg.xtrack_error,
                            targetheading = msg.target_bearing,
                            disttowp      = msg.wp_dist,
                        )
                        self.update_telemetry("WP", msg.wp_dist)

            except Exception as e:
                print(f"Telemetry tick error: {e}")

        self.after(50, self._telemetry_tick)

    def update_battery_ui(self):

        try:
            voltage = self.battery_handler.voltage
            percent = self.battery_handler.battery_remaining

            if voltage is not None and percent is not None:
                self.battery.update(voltage, percent)

        except Exception as e:
            print("Battery UI update error:", e)

        # refresh every 1 sec
        self.after(1000, self.update_battery_ui)
        
    def _run_preflight(self):
        if self._mav_conn is None:
            self.append_message("No vehicle connected — connect first before running preflight.", "ERROR")
            return
        checker = PreflightChecker(
            existing_connection=self._mav_conn,
            on_message=self.append_message
        )
        checker.run()                            # non-blocking

    def append_message(self, text: str, level: str = "INFO"):
        import datetime
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {text}\n"
        self.after(0, self._insert_message, line, level.upper())

    def _insert_message(self, line: str, level: str):
        self._msg_box.configure(state="normal")
        self._msg_box.insert("end", line, level)
        self._msg_box.see("end")
        self._msg_box.configure(state="disabled")