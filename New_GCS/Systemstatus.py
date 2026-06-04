from __future__ import annotations
 
import math
import threading
import time
from typing import Callable, Optional
 
from pymavlink import mavutil
 
 
# ─── helpers ──────────────────────────────────────────────────────────────────
 
def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS-84 points."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
 
 
# ─── main class ───────────────────────────────────────────────────────────────
 
class SystemStatusHandler:
    """
    Reads MAVLink telemetry and fires user-supplied callbacks with parsed data.
 
    All callbacks are invoked from the background polling thread.
    Wrap GUI updates in `widget.after(0, ...)` on the Tkinter side if needed.
    """
 
    # Callback signatures (assign before calling start())
    on_battery:  Optional[Callable[[float, Optional[int]], None]]  = None
    on_altitude: Optional[Callable[[float], None]]                 = None
    on_speed:    Optional[Callable[[float], None]]                 = None
    on_distance: Optional[Callable[[float], None]]                 = None
    # generic: key (str), display-value (str), color hint (str)
    on_status:   Optional[Callable[[str, str, str], None]]         = None
    on_gps: Optional[Callable[[float, float], None]] = None
 
    # ── internal colours (mirror gcs.py palette so callers can pass straight through) ──
    COLOR_OK      = "#00d084"   # ACCENT_GREEN
    COLOR_WARN    = "#f0a500"   # amber
    COLOR_ERROR   = "#ff3c5a"   # ACCENT_RED
    COLOR_OFFLINE = "#5a7fa0"   # TEXT_MUTED
 
    def __init__(self) -> None:
        self.master: Optional[mavutil.mavudp] = None
        self.running: bool = False
        self._owns_connection: bool = False
        self._poll_cache: bool = False
        self._thread: Optional[threading.Thread] = None
 
        # Live telemetry (readable externally as fallback)
        self.voltage: Optional[float]          = None
        self.battery_remaining: Optional[int]  = None
        self.altitude_m: Optional[float]       = None
        self.groundspeed_ms: Optional[float]   = None
        self.distance_m: Optional[float]       = None
 
        # Home / arming position (set on first valid GPS fix)
        self._home_lat: Optional[float] = None
        self._home_lon: Optional[float] = None
 
        # Last GPS position
        self._lat: Optional[float] = None
        self._lon: Optional[float] = None
 
    # ── connection ────────────────────────────────────────────────────────────
 
    def connect(
        self,
        connection_string: str = "udp:127.0.0.1:14550",
        baudrate: int = 57600,
        timeout: int = 5,
    ) -> bool:
        """Open a fresh MAVLink connection owned by this handler."""
        try:
            self.master = mavutil.mavlink_connection(connection_string, baud=baudrate)
            self.master.wait_heartbeat(timeout=timeout)
            self._owns_connection = True
            self._poll_cache      = False
            self._request_streams()
            print(f"[SystemStatus] Connected → {connection_string}")
            return True
        except Exception as exc:
            print(f"[SystemStatus] Connection failed: {exc}")
            self.master = None
            return False
 
    def attach_connection(self, master) -> bool:
        """
        Share an existing pymavlink connection (e.g. opened by ConnectPanel).
        Switches to cache-polling so we don't starve the primary reader.
        """
        self.stop()
        self.master            = master
        self._owns_connection  = False
        self._poll_cache       = True
        self._reset_state()
        self._request_streams()
        return self.master is not None
 
    # ── stream requests ───────────────────────────────────────────────────────
 
    def _request_streams(self) -> None:
        if self.master is None:
            return
        try:
            mav = self.master.mav
            tgt_sys  = self.master.target_system
            tgt_comp = self.master.target_component
 
            # SYS_STATUS (battery)
            mav.request_data_stream_send(
                tgt_sys, tgt_comp,
                mavutil.mavlink.MAV_DATA_STREAM_EXTENDED_STATUS, 2, 1,
            )
            # GLOBAL_POSITION_INT (altitude, lat/lon for distance)
            mav.request_data_stream_send(
                tgt_sys, tgt_comp,
                mavutil.mavlink.MAV_DATA_STREAM_POSITION, 4, 1,
            )
            # VFR_HUD (groundspeed, climb-rate)
            mav.request_data_stream_send(
                tgt_sys, tgt_comp,
                mavutil.mavlink.MAV_DATA_STREAM_EXTRA1, 4, 1,
            )
        except Exception as exc:
            print(f"[SystemStatus] Stream request failed: {exc}")
 
    # ── lifecycle ─────────────────────────────────────────────────────────────
 
    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
 
    def stop(self) -> None:
        self.running = False
 
    def disconnect(self) -> None:
        self.stop()
        if self._owns_connection and self.master is not None:
            try:
                self.master.close()
            except Exception:
                pass
        self.master = None
        self._owns_connection = False
        self._poll_cache      = False
        self._reset_state()
 
    # ── polling loop ──────────────────────────────────────────────────────────
 
    def _poll_loop(self) -> None:
        while self.running:
            if self.master is None:
                time.sleep(1.0)
                continue
            try:
                if self._poll_cache:
                    self._poll_from_cache()
                    time.sleep(0.5)
                else:
                    self._poll_from_stream()
            except Exception as exc:
                print(f"[SystemStatus] Poll error: {exc}")
                time.sleep(1.0)
 
    # ── cache mode (shared connection) ────────────────────────────────────────
 
    def _poll_from_cache(self) -> None:
        msgs = getattr(self.master, "messages", {})
 
        # --- Battery ---
        sys_status = msgs.get("SYS_STATUS")
        if sys_status:
            self._handle_sys_status(sys_status)
 
        # --- Altitude + Distance ---
        gpos = msgs.get("GLOBAL_POSITION_INT")
        if gpos:
            self._handle_global_position(gpos)
 
        # --- Speed ---
        vfr = msgs.get("VFR_HUD")
        if vfr:
            self._handle_vfr_hud(vfr)
 
    # ── stream mode (own connection) ──────────────────────────────────────────
 
    def _poll_from_stream(self) -> None:
        msg = self.master.recv_match(
            type=["SYS_STATUS", "GLOBAL_POSITION_INT", "VFR_HUD"],
            blocking=True,
            timeout=1.0,
        )
        if msg is None:
            return
        t = msg.get_type()
        if t == "SYS_STATUS":
            self._handle_sys_status(msg)
        elif t == "GLOBAL_POSITION_INT":
            self._handle_global_position(msg)
        elif t == "VFR_HUD":
            self._handle_vfr_hud(msg)
 
    # ── message handlers ──────────────────────────────────────────────────────
 
    def _handle_sys_status(self, msg) -> None:
        volts = msg.voltage_battery / 1000.0
        pct   = msg.battery_remaining if msg.battery_remaining >= 0 else None
 
        self.voltage           = volts
        self.battery_remaining = pct
 
        # colour thresholds: <20 % or <10.5 V → red; <40 % or <11.1 V → amber
        if pct is not None:
            color = (self.COLOR_ERROR  if pct < 20
                     else self.COLOR_WARN if pct < 40
                     else self.COLOR_OK)
        else:
            color = self.COLOR_WARN
 
        pct_str  = f"{pct}%" if pct is not None else "?%"
        disp_val = f"{volts:.1f}V {pct_str}"
 
        if self.on_battery:
            self.on_battery(volts, pct)
        if self.on_status:
            self.on_status("Battery", disp_val, color)
 
    def _handle_global_position(self, msg) -> None:
        # altitude relative to home (mm → m)
        alt_m = msg.relative_alt / 1000.0
        self.altitude_m = alt_m
 
        lat = msg.lat / 1e7
        lon = msg.lon / 1e7
        self._lat = lat
        self._lon = lon
        
        if self.on_gps:
            self.on_gps(lat, lon)
 
        # Set home on first valid fix (lat/lon non-zero)
        if self._home_lat is None and (lat != 0.0 or lon != 0.0):
            self._home_lat = lat
            self._home_lon = lon
            print(f"[SystemStatus] Home set → {lat:.6f}, {lon:.6f}")
 
        # Distance
        if self._home_lat is not None:
            dist_m = _haversine(self._home_lat, self._home_lon, lat, lon)
            self.distance_m = dist_m
            if self.on_distance:
                self.on_distance(dist_m)
            if self.on_status:
                dist_disp = (f"{dist_m:.0f} m" if dist_m < 1000
                             else f"{dist_m/1000:.2f} km")
                self.on_status("Distance", dist_disp, self.COLOR_OK)
 
        # Altitude callback + badge
        alt_color = (self.COLOR_ERROR  if alt_m < 0
                     else self.COLOR_OK)
        if self.on_altitude:
            self.on_altitude(alt_m)
        if self.on_status:
            self.on_status("Altitude", f"{alt_m:.1f} m", alt_color)
 
    def _handle_vfr_hud(self, msg) -> None:
        spd = msg.groundspeed   # m/s
        self.groundspeed_ms = spd
 
        spd_color = self.COLOR_OK if spd < 30 else self.COLOR_WARN
        if self.on_speed:
            self.on_speed(spd)
        if self.on_status:
            self.on_status("Speed", f"{spd:.1f} m/s", spd_color)
 
    # ── helpers ───────────────────────────────────────────────────────────────
 
    def _reset_state(self) -> None:
        self.voltage           = None
        self.battery_remaining = None
        self.altitude_m        = None
        self.groundspeed_ms    = None
        self.distance_m        = None
        self._home_lat         = None
        self._home_lon         = None
        self._lat              = None
        self._lon              = None
 
    def reset_home(self) -> None:
        """Call this to re-arm the home position on next valid GPS fix."""
        self._home_lat = None
        self._home_lon = None