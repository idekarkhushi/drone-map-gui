"""
CAN_GPSOrder.py
---------------
GPS CAN node order configuration panel for SetupPage.
Import CANGPSOrderPanel and place it in SetupPage's content area.
"""

from __future__ import annotations

import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox
from dataclasses import dataclass
from typing import List

try:
    from pymavlink import mavutil as _mavutil
except ImportError:
    _mavutil = None


# ═══════════════════════════════════════════════════════════════════════════════
#  PALETTE  (matches SetupPage / Motortest)
# ═══════════════════════════════════════════════════════════════════════════════

BG       = "#0d1117"
CARD_BG  = "#21262d"
SURFACE  = "#2d333b"
ACCENT   = "#1f6feb"
CYAN     = "#22d3ee"
BORDER   = "#30363d"
TXT_PRI  = "#e6edf3"
TXT_SEC  = "#8b949e"
BTN_GPS1 = "#1d4ed8"
BTN_GPS2 = "#0e7490"
HOV_GPS1 = "#2563eb"
HOV_GPS2 = "#0891b2"
ROW_ODD  = "#161b22"
ROW_EVEN = "#1c2128"
FONT     = "Times New Roman"

_P_GPS1_OVRIDE = "GPS1_CAN_OVRIDE"
_P_GPS2_OVRIDE = "GPS2_CAN_OVRIDE"
_P_NODEID1     = "GPS_CAN_NODEID1"
_P_NODEID2     = "GPS_CAN_NODEID2"


# ═══════════════════════════════════════════════════════════════════════════════
#  DATA MODEL
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class GPSCAN:
    order:   int
    name:    str
    node_id: int


# ═══════════════════════════════════════════════════════════════════════════════
#  BACKEND  (MAVLink param read / write)
# ═══════════════════════════════════════════════════════════════════════════════

class _GPSCANBackend:

    def __init__(self):
        self._conn = None
        self._params: dict[str, float] = {}

    def set_connection(self, conn) -> None:
        self._conn = conn

    @property
    def is_connected(self) -> bool:
        return self._conn is not None

    def load(self) -> bool:
        if not self.is_connected:
            return False
        fetched: dict[str, float] = {}
        for name in (_P_GPS1_OVRIDE, _P_GPS2_OVRIDE, _P_NODEID1, _P_NODEID2):
            try:
                self._conn.mav.param_request_read_send(
                    self._conn.target_system,
                    self._conn.target_component,
                    name.encode(), -1,
                )
                msg = self._conn.recv_match(type="PARAM_VALUE", blocking=True, timeout=3)
                fetched[name] = (
                    float(msg.param_value)
                    if msg and msg.param_id.strip("\x00") == name
                    else 0.0
                )
            except Exception:
                fetched[name] = 0.0
        self._params = fetched
        return _P_GPS1_OVRIDE in self._params

    def feature_available(self) -> bool:
        return _P_GPS1_OVRIDE in self._params

    def _get(self, key: str) -> float:
        return self._params.get(key, 0.0)

    def build_node_list(self) -> List[GPSCAN]:
        id1    = self._get(_P_NODEID1)
        id2    = self._get(_P_NODEID2)
        id1ovr = self._get(_P_GPS1_OVRIDE)
        id2ovr = self._get(_P_GPS2_OVRIDE)
        rows: List[GPSCAN] = []
        if id1ovr != 0:
            rows.append(GPSCAN(order=1,  name="GPS Override 1", node_id=int(id1ovr)))
        if id2ovr != 0:
            rows.append(GPSCAN(order=2,  name="GPS Override 2", node_id=int(id2ovr)))
        if id1 != 0 and id1 != id1ovr and id1 != id2ovr:
            rows.append(GPSCAN(order=98, name="GPS Detect 1",   node_id=int(id1)))
        if id2 != 0 and id2 != id1ovr and id2 != id2ovr:
            rows.append(GPSCAN(order=99, name="GPS Detect 2",   node_id=int(id2)))
        return rows

    def set_gps1(self, node_id: int) -> None:
        self._write(_P_GPS1_OVRIDE, float(node_id))

    def set_gps2(self, node_id: int) -> None:
        self._write(_P_GPS2_OVRIDE, float(node_id))

    def _write(self, name: str, value: float) -> None:
        if not self.is_connected:
            raise RuntimeError("No MAVLink connection available.")
        self._conn.mav.param_set_send(
            self._conn.target_system,
            self._conn.target_component,
            name.encode(), value,
            _mavutil.mavlink.MAV_PARAM_TYPE_REAL32 if _mavutil else 9,
        )
        self._params[name] = value

    def status_text(self) -> str:
        id1ovr = self._get(_P_GPS1_OVRIDE)
        id2ovr = self._get(_P_GPS2_OVRIDE)
        id1    = self._get(_P_NODEID1)
        id2    = self._get(_P_NODEID2)
        return (
            f"GPS1 override: node {int(id1ovr) if id1ovr else '—'}   "
            f"GPS2 override: node {int(id2ovr) if id2ovr else '—'}   "
            f"Detected: {int(id1) if id1 else '—'}, {int(id2) if id2 else '—'}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  UI PANEL
# ═══════════════════════════════════════════════════════════════════════════════

class CANGPSOrderPanel(ctk.CTkFrame):

    _COLS   = ("Order", "Name", "Node ID", "Set as GPS 1", "Set as GPS 2")
    _WIDTHS = (60, 200, 90, 120, 120)

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=BG, **kwargs)
        self._backend = _GPSCANBackend()
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._build_ui()

    def set_connection(self, conn) -> None:
        self._backend.set_connection(conn)
        self._refresh()

    def _build_ui(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=0, height=75)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_columnconfigure(1, weight=1)
        hdr.grid_propagate(False)

        # Accent strip
        ctk.CTkFrame(
            hdr,
            fg_color=ACCENT,
            width=4,
            corner_radius=0
        ).place(x=0, y=0, relheight=1)

        # Title
        ctk.CTkLabel(
            hdr,
            text="GPS CAN Node Order",
            font=ctk.CTkFont(FONT, 18, weight="bold"),
            text_color=TXT_PRI,
        ).place(x=18, y=14)

        # Subtitle
        ctk.CTkLabel(
            hdr,
            text="Assign CAN GPS nodes to GPS1 / GPS2 slots on your autopilot.",
            font=ctk.CTkFont(FONT, 11),
            text_color=TXT_SEC,
        ).place(x=18, y=42)

        # Refresh button
        ctk.CTkButton(
            hdr,
            text="⟳ Refresh",
            width=100,
            height=28,
            fg_color=SURFACE,
            hover_color=BORDER,
            text_color=TXT_PRI,
            font=ctk.CTkFont(FONT, 11),
            command=self._refresh,
        ).place(relx=1.0, x=-120, y=22)

        # Status bar
        self._status_var = tk.StringVar(value="Not connected.")
        ctk.CTkLabel(
            self, textvariable=self._status_var,
            font=ctk.CTkFont(FONT, 10), text_color=TXT_SEC, anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(6, 2))

        # Table card
        tbl = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=8)
        tbl.grid(row=2, column=0, sticky="nsew", padx=16, pady=(4, 12))
        tbl.grid_columnconfigure(0, weight=1)
        tbl.grid_rowconfigure(1, weight=1)

        col_hdr = ctk.CTkFrame(tbl, fg_color=SURFACE, corner_radius=0)
        col_hdr.grid(row=0, column=0, sticky="ew")
        for i, (col, w) in enumerate(zip(self._COLS, self._WIDTHS)):
            ctk.CTkLabel(
                col_hdr, text=col.upper(),
                font=ctk.CTkFont(FONT, 10, weight="bold"),
                text_color=TXT_SEC, width=w, anchor="w",
            ).grid(row=0, column=i, padx=(14 if i == 0 else 4, 4), pady=7)

        self._body = ctk.CTkScrollableFrame(
            tbl, fg_color=CARD_BG,
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=ACCENT,
        )
        self._body.grid(row=1, column=0, sticky="nsew")
        self._body.grid_columnconfigure(0, weight=1)

        # Legend
        leg = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=6)
        leg.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 14))
        for ci, (colour, label) in enumerate([
            (BTN_GPS1, "Set as GPS 1"),
            (BTN_GPS2, "Set as GPS 2"),
            (ACCENT,   "Override node"),
            (TXT_SEC,  "Auto-detected"),
        ]):
            ctk.CTkFrame(leg, fg_color=colour, width=10, height=10,
                         corner_radius=5).grid(row=0, column=ci * 2, padx=(14, 4), pady=8)
            ctk.CTkLabel(
                leg, text=label,
                font=ctk.CTkFont(FONT, 10), text_color=TXT_SEC,
            ).grid(row=0, column=ci * 2 + 1, padx=(0, 16))

    def _refresh(self) -> None:
        if not self._backend.is_connected:
            self._status_var.set("⚠  No MAVLink connection.")
            self._render_rows([])
            return
        ok = self._backend.load()
        if not ok or not self._backend.feature_available():
            self._status_var.set("⚠  GPS1_CAN_OVRIDE not found – feature unavailable on this firmware.")
            self._render_rows([])
            return
        self._status_var.set(self._backend.status_text())
        self._render_rows(self._backend.build_node_list())

    def _render_rows(self, rows: List[GPSCAN]) -> None:
        for w in self._body.winfo_children():
            w.destroy()
        if not rows:
            ctk.CTkLabel(
                self._body, text="No GPS CAN nodes found.",
                font=ctk.CTkFont(FONT, 12), text_color=TXT_SEC,
            ).grid(row=0, column=0, padx=20, pady=20)
            return
        for r_idx, gps in enumerate(rows):
            bg          = ROW_ODD if r_idx % 2 == 0 else ROW_EVEN
            name_colour = ACCENT if "Override" in gps.name else TXT_PRI
            row = ctk.CTkFrame(self._body, fg_color=bg, corner_radius=0)
            row.grid(row=r_idx, column=0, sticky="ew", pady=1)
            ctk.CTkLabel(
                row, text=str(gps.order), width=self._WIDTHS[0],
                font=ctk.CTkFont("Courier New", 13, weight="bold"),
                text_color=CYAN, anchor="w",
            ).grid(row=0, column=0, padx=(14, 4), pady=10)
            ctk.CTkLabel(
                row, text=gps.name, width=self._WIDTHS[1],
                font=ctk.CTkFont(FONT, 12), text_color=name_colour, anchor="w",
            ).grid(row=0, column=1, padx=4, pady=10)
            ctk.CTkLabel(
                row, text=str(gps.node_id), width=self._WIDTHS[2],
                font=ctk.CTkFont("Courier New", 12), text_color=TXT_PRI, anchor="w",
            ).grid(row=0, column=2, padx=4, pady=10)
            ctk.CTkButton(
                row, text="▶  GPS 1",
                width=self._WIDTHS[3] - 8, height=26,
                fg_color=BTN_GPS1, hover_color=HOV_GPS1,
                font=ctk.CTkFont(FONT, 11, weight="bold"), text_color="white",
                command=lambda g=gps: self._on_set_gps1(g),
            ).grid(row=0, column=3, padx=4, pady=7)
            ctk.CTkButton(
                row, text="▶  GPS 2",
                width=self._WIDTHS[4] - 8, height=26,
                fg_color=BTN_GPS2, hover_color=HOV_GPS2,
                font=ctk.CTkFont(FONT, 11, weight="bold"), text_color="white",
                command=lambda g=gps: self._on_set_gps2(g),
            ).grid(row=0, column=4, padx=(4, 14), pady=7)

    def _on_set_gps1(self, gps: GPSCAN) -> None:
        try:
            self._backend.set_gps1(gps.node_id)
            self._refresh()
        except Exception as ex:
            messagebox.showerror("Failed to set param", str(ex))

    def _on_set_gps2(self, gps: GPSCAN) -> None:
        try:
            self._backend.set_gps2(gps.node_id)
            self._refresh()
        except Exception as ex:
            messagebox.showerror("Failed to set param", str(ex))