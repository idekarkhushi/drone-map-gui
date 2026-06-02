import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Optional
 
import customtkinter as ctk
 
try:
    from pymavlink import mavutil
except ImportError:
    mavutil = None
 
 
# ── Palette (matches SetupPage) ───────────────────────────────────────────────
BG       = "#0d1117"
CARD_BG  = "#21262d"
ACCENT   = "#1f6feb"
BORDER   = "#30363d"
TXT_PRI  = "#e6edf3"
TXT_SEC  = "#8b949e"
SUCCESS  = "#3fb950"
WARN     = "#d29922"
ERROR    = "#f85149"
FONT     = "Times New Roman"
 
 
# ── Data structures ───────────────────────────────────────────────────────────
 
@dataclass
class MotorInfo:
    number: int = 0
    test_order: int = 0
    rotation: str = "?"
    roll: float = 0.0
    pitch: float = 0.0
 
 
@dataclass
class FrameLayout:
    frame_class: int = 0
    frame_type: int = 0
    motors: list = field(default_factory=list)   # list[MotorInfo]
 
 
# Q_FRAME_CLASS → MAV_TYPE int (safe without mavutil import)
_Q_FRAME_CLASS_MAP = {0: 2, 1: 2, 2: 13, 5: 13, 3: 11, 4: 11, 6: 4, 7: 15}
_MAV_TYPE_MOTOR_COUNT = {2: 4, 13: 6, 11: 8, 4: 0, 15: 4, 12: 12}
_GROUND_TYPES = {10, 12}   # GROUND_ROVER=10, SURFACE_BOAT=12
 
 
# ── Backend ───────────────────────────────────────────────────────────────────
 
class MotorTestBackend:
    """
    Handles param fetching, layout lookup and MAVLink command sending.
    Completely decoupled from the UI.
    """
 
    def __init__(self, master, layout_json_path: str = "APMotorLayout.json"):
        self.master = master          # pymavlink connection object
        self.layout_json_path = layout_json_path
        self.motor_count: int = 0
        self.layout: Optional[FrameLayout] = None
        self.frame_class_label: str = "—"
        self.frame_type_label:  str = "—"
        self._params: dict = {}
 
    # ── Public ────────────────────────────────────────────────────────────────
 
    def refresh(self):
        """Fetch params, detect motor count and load layout. Call off the UI thread."""
        self._params = self._fetch_params()
        self.motor_count = self._get_motor_count()
 
    def test_motor(self, motor: int, speed_pct: int, duration_s: int, motor_count: int = 0):
        if self.master is None or mavutil is None:
            return
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST,
            0,
            float(motor),
            float(mavutil.mavlink.MOTOR_TEST_THROTTLE_PERCENT),
            float(speed_pct),
            float(duration_s),
            float(motor_count),
            0, 0,
        )
 
    def test_all(self, speed_pct: int, duration_s: int):
        for i in range(1, self.motor_count + 1):
            self.test_motor(i, speed_pct, duration_s)
 
    def test_all_sequence(self, speed_pct: int, duration_s: int):
        self.test_motor(1, speed_pct, duration_s, motor_count=self.motor_count)
 
    def stop_all(self):
        for i in range(1, self.motor_count + 1):
            self.test_motor(i, 0, 0)
 
    def motor_slots(self) -> list:
        """Return list of dicts for UI button building."""
        result = []
        for i in range(1, self.motor_count + 1):
            entry = {
                "test_order": i,
                "label": f"Motor {chr(ord('A') + i - 1)}",
                "number": None,
                "rotation": None,
            }
            if self.layout:
                for m in self.layout.motors:
                    if m.test_order == i:
                        entry["number"] = m.number
                        entry["rotation"] = m.rotation if m.rotation != "?" else None
                        break
            result.append(entry)
        return result
 
    # ── Private ───────────────────────────────────────────────────────────────
 
    def _fetch_params(self) -> dict:
        if self.master is None or mavutil is None:
            return {}
        wanted = {"FRAME", "FRAME_CLASS", "FRAME_TYPE",
                  "Q_FRAME_CLASS", "Q_FRAME_TYPE"}
        params = {}
        try:
            self.master.param_fetch_all()
            deadline = time.time() + 8
            while time.time() < deadline:
                msg = self.master.recv_match(type="PARAM_VALUE", blocking=True, timeout=1)
                if msg is None:
                    break
                name = msg.param_id.strip("\x00")
                if name in wanted:
                    params[name] = msg.param_value
                if len(params) >= len(wanted):
                    break
        except Exception:
            pass
        return params
 
    def _get_motor_count(self) -> int:
        default = 4
        aptype = self._get_aptype()
        if aptype in _GROUND_TYPES:
            return 4
 
        has_frame  = "FRAME"        in self._params
        has_qframe = "Q_FRAME_TYPE" in self._params
        has_ftype  = "FRAME_TYPE"   in self._params
 
        if not (has_frame or has_qframe or has_ftype):
            return default
 
        for cls_key, typ_key in (("FRAME_CLASS", "FRAME_TYPE"),
                                  ("Q_FRAME_CLASS", "Q_FRAME_TYPE")):
            if self._resolve_layout(cls_key, typ_key):
                if self.layout and self.layout.motors:
                    return len(self.layout.motors)
                break
 
        mav_type = self._infer_mav_type(aptype)
        return _MAV_TYPE_MOTOR_COUNT.get(mav_type, default)
 
    def _infer_mav_type(self, aptype) -> int:
        if "Q_FRAME_CLASS" in self._params:
            return _Q_FRAME_CLASS_MAP.get(int(self._params["Q_FRAME_CLASS"]), 2)
        return aptype
 
    def _resolve_layout(self, cls_key: str, typ_key: str) -> bool:
        if cls_key not in self._params or typ_key not in self._params:
            return False
        fc = int(self._params[cls_key])
        ft = int(self._params[typ_key])
        self.frame_class_label = f"Class {fc}"
        self.frame_type_label  = f"Type {ft}"
        self._lookup_layout(fc, ft)
        return True
 
    def _lookup_layout(self, frame_class: int, frame_type: int):
        path = self.layout_json_path
        if not os.path.isabs(path):
            path = os.path.join(os.path.dirname(__file__), path)
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                data = json.load(f)
            if data.get("Version") != "AP_Motors library test ver 1.2":
                return
            for layout in data.get("layouts", []):
                if layout.get("Class") == frame_class and layout.get("Type") == frame_type:
                    self.layout = FrameLayout(
                        frame_class=frame_class,
                        frame_type=frame_type,
                        motors=[
                            MotorInfo(
                                number=m.get("Number", 0),
                                test_order=m.get("TestOrder", 0),
                                rotation=m.get("Rotation", "?"),
                                roll=m.get("Roll", 0.0),
                                pitch=m.get("Pitch", 0.0),
                            )
                            for m in layout.get("motors", [])
                        ],
                    )
                    return
        except Exception as e:
            print(f"[MotorTest] Layout load error: {e}")
 
    def _get_aptype(self) -> int:
        if self.master is None or mavutil is None:
            return 2   # default quad
        try:
            hb = self.master.recv_match(type="HEARTBEAT", blocking=True, timeout=2)
            if hb:
                return hb.type
        except Exception:
            pass
        return 2
 
 
# ── UI Panel ──────────────────────────────────────────────────────────────────
 
class MotorTestPanel(ctk.CTkFrame):
    """
    CustomTkinter panel that renders motor test controls.
    Pass the live pymavlink connection via set_connection().
    """
 
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=BG, **kwargs)
        self._backend: Optional[MotorTestBackend] = None
        self._motor_buttons: list = []
        self._build_ui()
        self._status("No connection — connect to vehicle first", TXT_SEC)
 
    # ── Public API ────────────────────────────────────────────────────────────
 
    def set_connection(self, conn):
        """Call from SetupPage whenever the MAVLink connection changes."""
        if conn is None:
            self._backend = None
            self._status("No connection — connect to vehicle first", TXT_SEC)
            return
        self._backend = MotorTestBackend(conn)
        self._status("Fetching frame info…", WARN)
        threading.Thread(target=self._load, daemon=True).start()
 
    # ── Build static skeleton ─────────────────────────────────────────────────
 
    def _build_ui(self):
        # ── Title ─────────────────────────────────────────────────────────────
        ctk.CTkLabel(
            self, text="Motor Test",
            font=(FONT, 18, "bold"), text_color=TXT_PRI,
        ).pack(anchor="w", padx=20, pady=(16, 2))
 
        ctk.CTkLabel(
            self, text="Arm the vehicle before testing. Keep props off.",
            font=(FONT, 11), text_color=WARN,
        ).pack(anchor="w", padx=20, pady=(0, 10))
 
        # ── Frame info row ────────────────────────────────────────────────────
        info_row = ctk.CTkFrame(self, fg_color="transparent")
        info_row.pack(fill="x", padx=20, pady=(0, 8))
        self._class_lbl = ctk.CTkLabel(info_row, text="Frame Class: —",
                                        font=(FONT, 11), text_color=TXT_SEC)
        self._class_lbl.pack(side="left", padx=(0, 20))
        self._type_lbl = ctk.CTkLabel(info_row, text="Frame Type: —",
                                       font=(FONT, 11), text_color=TXT_SEC)
        self._type_lbl.pack(side="left")
 
        # ── Throttle & duration controls ──────────────────────────────────────
        ctrl_row = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=8)
        ctrl_row.pack(fill="x", padx=20, pady=(0, 12))
 
        ctk.CTkLabel(ctrl_row, text="Throttle %", font=(FONT, 11), text_color=TXT_SEC
                     ).pack(side="left", padx=(14, 4), pady=10)
        self._thr_var = ctk.StringVar(value="10")
        self._thr_spin = ctk.CTkEntry(ctrl_row, textvariable=self._thr_var,
                                       width=60, font=(FONT, 12))
        self._thr_spin.pack(side="left", padx=(0, 20), pady=10)
 
        ctk.CTkLabel(ctrl_row, text="Duration (s)", font=(FONT, 11), text_color=TXT_SEC
                     ).pack(side="left", padx=(0, 4), pady=10)
        self._dur_var = ctk.StringVar(value="2")
        self._dur_spin = ctk.CTkEntry(ctrl_row, textvariable=self._dur_var,
                                       width=60, font=(FONT, 12))
        self._dur_spin.pack(side="left", padx=(0, 14), pady=10)
 
        # ── Motor buttons area (rebuilt after refresh) ────────────────────────
        self._motors_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._motors_frame.pack(fill="x", padx=20, pady=(0, 12))
 
        # ── Global action buttons ─────────────────────────────────────────────
        action_row = ctk.CTkFrame(self, fg_color="transparent")
        action_row.pack(fill="x", padx=20, pady=(0, 10))
 
        for text, cmd, color in [
            ("Test All",         self._test_all,      ACCENT),
            ("Test in Sequence", self._test_sequence,  "#2ea043"),
            ("Stop All",         self._stop_all,       ERROR),
            ("Refresh",          self._refresh,        CARD_BG),
        ]:
            ctk.CTkButton(
                action_row, text=text, command=cmd, width=130, height=32,
                fg_color=color, hover_color=self._lighten(color),
                font=(FONT, 12, "bold"), corner_radius=6,
            ).pack(side="left", padx=(0, 8))
 
        # ── Status bar ────────────────────────────────────────────────────────
        self._status_lbl = ctk.CTkLabel(
            self, text="No connection", font=(FONT, 11), text_color=TXT_SEC,
        )
        self._status_lbl.pack(anchor="w", padx=20, pady=(4, 12))
 
    # ── Motor button grid (rebuilt after backend refresh) ─────────────────────
 
    def _build_motor_buttons(self):
        for w in self._motors_frame.winfo_children():
            w.destroy()
        self._motor_buttons.clear()
 
        if self._backend is None:
            return
 
        slots = self._backend.motor_slots()
        cols = 4
        for idx, slot in enumerate(slots):
            row, col = divmod(idx, cols)
            sub = ctk.CTkFrame(self._motors_frame, fg_color=CARD_BG, corner_radius=8)
            sub.grid(row=row, column=col, padx=6, pady=6, sticky="ew")
            self._motors_frame.grid_columnconfigure(col, weight=1)
 
            ctk.CTkLabel(sub, text=slot["label"],
                          font=(FONT, 12, "bold"), text_color=TXT_PRI
                          ).pack(pady=(8, 2))
 
            details = ""
            if slot["number"] is not None:
                details += f"#{slot['number']}"
            if slot["rotation"]:
                details += f"  {slot['rotation']}"
            if details:
                ctk.CTkLabel(sub, text=details,
                              font=(FONT, 10), text_color=TXT_SEC
                              ).pack(pady=(0, 4))
 
            order = slot["test_order"]
            btn = ctk.CTkButton(
                sub, text="Test", width=90, height=28,
                fg_color=ACCENT, hover_color="#363738",
                font=(FONT, 11), corner_radius=5,
                command=lambda o=order: self._test_single(o),
            )
            btn.pack(pady=(2, 8))
            self._motor_buttons.append(btn)
 
    # ── Backend loading (off UI thread) ──────────────────────────────────────
 
    def _load(self):
        if self._backend:
            self._backend.refresh()
        self.after(0, self._on_loaded)
 
    def _on_loaded(self):
        if self._backend is None:
            self._status("No connection", TXT_SEC)
            return
        self._class_lbl.configure(text=f"Frame Class: {self._backend.frame_class_label}")
        self._type_lbl.configure(text=f"Frame Type:  {self._backend.frame_type_label}")
        count = self._backend.motor_count
        self._build_motor_buttons()
        self._status(f"Ready — {count} motor{'s' if count != 1 else ''} detected", SUCCESS)
 
    # ── Button callbacks ──────────────────────────────────────────────────────
 
    def _test_single(self, motor: int):
        if not self._check_conn():
            return
        spd, dur = self._get_controls()
        self._backend.test_motor(motor, spd, dur)
        self._status(f"Testing motor {chr(ord('A') + motor - 1)} at {spd}% for {dur}s", ACCENT)
 
    def _test_all(self):
        if not self._check_conn():
            return
        spd, dur = self._get_controls()
        threading.Thread(target=self._backend.test_all, args=(spd, dur), daemon=True).start()
        self._status(f"Testing all motors at {spd}% for {dur}s", ACCENT)
 
    def _test_sequence(self):
        if not self._check_conn():
            return
        spd, dur = self._get_controls()
        threading.Thread(target=self._backend.test_all_sequence, args=(spd, dur), daemon=True).start()
        self._status(f"Running sequence at {spd}% for {dur}s", ACCENT)
 
    def _stop_all(self):
        if not self._check_conn():
            return
        threading.Thread(target=self._backend.stop_all, daemon=True).start()
        self._status("Stop sent to all motors", WARN)
 
    def _refresh(self):
        if self._backend is None:
            self._status("No connection — connect first", ERROR)
            return
        self._status("Refreshing…", WARN)
        threading.Thread(target=self._load, daemon=True).start()
 
    # ── Helpers ───────────────────────────────────────────────────────────────
 
    def _get_controls(self) -> tuple:
        try:
            spd = max(0, min(100, int(self._thr_var.get())))
        except Exception:
            spd = 10
        try:
            dur = max(0, int(self._dur_var.get()))
        except Exception:
            dur = 2
        return spd, dur
 
    def _check_conn(self) -> bool:
        if self._backend is None or self._backend.master is None:
            self._status("Not connected", ERROR)
            return False
        return True
 
    def _status(self, msg: str, color: str = TXT_SEC):
        self._status_lbl.configure(text=msg, text_color=color)
 
    @staticmethod
    def _lighten(hex_color: str) -> str:
        """Simple brightness bump for hover color."""
        try:
            h = hex_color.lstrip("#")
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            r, g, b = min(255, r + 30), min(255, g + 30), min(255, b + 30)
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex_color