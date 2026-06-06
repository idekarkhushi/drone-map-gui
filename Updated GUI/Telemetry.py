import math
import threading
import time
from typing import Callable, Optional


# ─────────────────────────────────────────────────────────────────────────────
#  TelemetryState  –  holds the latest value of every field DataPage uses
# ─────────────────────────────────────────────────────────────────────────────
class TelemetryState:
    """Plain data container; all fields map directly to HUDWidget.redraw() kwargs."""

    def __init__(self):
        # ── Attitude ─────────────────────────────────────────────────────────
        self.pitch: float = 0.0          # degrees
        self.roll: float = 0.0           # degrees
        self.heading: float = 0.0        # degrees (0-360)

        # ── Speed / Altitude ─────────────────────────────────────────────────
        self.airspeed: float = 0.0       # m/s
        self.groundspeed: float = 0.0    # m/s
        self.altitude: float = 0.0       # m  (relative)
        self.vspeed: float = 0.0         # m/s (climb rate)

        # ── GPS ──────────────────────────────────────────────────────────────
        self.gpsfix: int = 0             # fix type (0=no fix, 3=3D)
        self.gpshdop: float = 99.9

        # ── Battery ──────────────────────────────────────────────────────────
        self.batterylevel: float = 0.0   # V
        self.batteryremaining: float = 0.0  # %
        self.current: float = 0.0        # A

        # ── Navigation ───────────────────────────────────────────────────────
        self.xtrack_error: float = 0.0
        self.targetheading: float = 0.0
        self.disttowp: float = 0.0
        self.wpno: int = 0

        # ── Vehicle status ───────────────────────────────────────────────────
        self.armed: bool = False
        self.mode: str = "UNKNOWN"

        # ── Telemetry card values (keyed exactly as telem_rows in DataPage) ──
        self.ALT: float = 0.0            # relative altitude  m
        self.GS: float = 0.0             # ground speed       m/s
        self.VS: float = 0.0             # vertical speed     m/s
        self.YAW: float = 0.0            # yaw / heading      °
        self.WP: float = 0.0             # dist to waypoint   m
        self.MAV: float = 0.0            # dist to MAV (home) m


# ─────────────────────────────────────────────────────────────────────────────
#  TelemetryHandler
# ─────────────────────────────────────────────────────────────────────────────
class TelemetryHandler:
    def __init__(
        self,
        on_hud_update: Callable,
        on_telem_update: Callable,
        on_message: Optional[Callable] = None,
        poll_hz: int = 20,
    ):
        self._on_hud = on_hud_update
        self._on_telem = on_telem_update
        self._on_msg = on_message or (lambda t, l: None)

        self._interval = 1.0 / max(1, poll_hz)
        self._conn = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._home_lat: Optional[float] = None
        self._home_lon: Optional[float] = None
        self._cur_lat: Optional[float] = None
        self._cur_lon: Optional[float] = None

        self.state = TelemetryState()

    # ── Connection management ─────────────────────────────────────────────────

    def attach(self, conn) -> bool:
        """Attach a live MAVLink connection and start polling."""
        if conn is None:
            return False
        self._conn = conn
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="TelemetryPoller"
        )
        self._thread.start()
        self._on_msg("Telemetry handler started", "OK")
        return True

    def detach(self):
        """Stop polling and release the connection."""
        self._running = False
        self._conn = None
        self._on_msg("Telemetry handler stopped", "INFO")

    @property
    def connected(self) -> bool:
        return self._conn is not None and self._running

    # ── Background poll loop ─────────────────────────────────────────────────

    def _poll_loop(self):
        while self._running and self._conn is not None:
            try:
                # Drain up to 20 messages per tick to keep latency low
                for _ in range(20):
                    msg = self._conn.recv_match(blocking=False)
                    if msg is None:
                        break
                    self._dispatch(msg)
            except Exception as exc:
                self._on_msg(f"Telemetry error: {exc}", "ERROR")

            time.sleep(self._interval)

    # ── Message dispatcher ───────────────────────────────────────────────────

    def _dispatch(self, msg):
        mtype = msg.get_type()

        if mtype == "ATTITUDE":
            self._handle_attitude(msg)

        elif mtype == "VFR_HUD":
            self._handle_vfr_hud(msg)

        elif mtype == "GPS_RAW_INT":
            self._handle_gps_raw(msg)

        elif mtype == "GLOBAL_POSITION_INT":
            self._handle_global_pos(msg)

        elif mtype == "SYS_STATUS":
            self._handle_sys_status(msg)

        elif mtype == "HEARTBEAT":
            self._handle_heartbeat(msg)

        elif mtype == "NAV_CONTROLLER_OUTPUT":
            self._handle_nav_controller(msg)

        elif mtype == "MISSION_CURRENT":
            self._handle_mission_current(msg)

        elif mtype == "HOME_POSITION":
            self._handle_home_position(msg)

    # ── Individual message handlers ──────────────────────────────────────────

    def _handle_attitude(self, msg):
        s = self.state
        s.pitch = math.degrees(msg.pitch)
        s.roll = math.degrees(msg.roll)
        s.heading = math.degrees(msg.yaw) % 360
        s.YAW = s.heading

        self._on_hud(
            pitch=s.pitch,
            roll=s.roll,
            heading=s.heading,
        )
        self._on_telem("YAW", s.YAW)

    def _handle_vfr_hud(self, msg):
        s = self.state
        s.airspeed = msg.airspeed
        s.groundspeed = msg.groundspeed
        s.altitude = msg.alt
        s.vspeed = msg.climb
        s.heading = float(msg.heading)
        s.GS = s.groundspeed

        self._on_hud(
            airspeed=s.airspeed,
            groundspeed=s.groundspeed,
            altitude=s.altitude,
            vspeed=s.vspeed,
            heading=s.heading,
        )
        self._on_telem("GS", s.GS)

    def _handle_gps_raw(self, msg):
        s = self.state
        s.gpsfix = msg.fix_type
        s.gpshdop = msg.eph / 100.0 if msg.eph != 65535 else 99.9

        self._on_hud(
            gpsfix=s.gpsfix,
            gpshdop=s.gpshdop,
        )

    def _handle_global_pos(self, msg):
        s = self.state
        s.ALT = msg.relative_alt / 1000.0   # mm → m
        s.VS = msg.vz / 100.0               # cm/s → m/s

        # Store current position for MAV distance calculation
        self._cur_lat = msg.lat / 1e7
        self._cur_lon = msg.lon / 1e7

        self._on_telem("ALT", s.ALT)
        self._on_telem("VS", s.VS)
        self._on_hud(altitude=s.ALT, vspeed=s.VS)

        # Update distance to home (MAV)
        if self._home_lat is not None and self._cur_lat is not None:
            s.MAV = self._haversine(
                self._home_lat, self._home_lon,
                self._cur_lat, self._cur_lon,
            )
            self._on_telem("MAV", s.MAV)

    def _handle_sys_status(self, msg):
        s = self.state
        s.batterylevel = msg.voltage_battery / 1000.0       # mV → V
        s.current = msg.current_battery / 100.0             # cA → A
        s.batteryremaining = float(msg.battery_remaining)   # %

        self._on_hud(
            batterylevel=s.batterylevel,
            current=s.current,
            batteryremaining=s.batteryremaining,
        )

    def _handle_heartbeat(self, msg):
        try:
            from pymavlink import mavutil
            s = self.state
            s.armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)

            # Decode flight mode string
            mode_str = mavutil.mode_string_v10(msg)
            if mode_str and mode_str != "UNKNOWN":
                s.mode = mode_str

            self._on_hud(status=s.armed, mode=s.mode)
        except Exception:
            pass

    def _handle_nav_controller(self, msg):
        s = self.state
        s.xtrack_error = msg.xtrack_error
        s.targetheading = msg.target_bearing
        s.disttowp = msg.wp_dist
        s.WP = float(msg.wp_dist)

        self._on_hud(
            xtrack_error=s.xtrack_error,
            targetheading=s.targetheading,
            disttowp=s.disttowp,
        )
        self._on_telem("WP", s.WP)

    def _handle_mission_current(self, msg):
        self.state.wpno = msg.seq
        self._on_hud(wpno=self.state.wpno)

    def _handle_home_position(self, msg):
        self._home_lat = msg.latitude / 1e7
        self._home_lon = msg.longitude / 1e7

    # ── Utility ──────────────────────────────────────────────────────────────

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Return great-circle distance in metres between two GPS coordinates."""
        R = 6_371_000.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))