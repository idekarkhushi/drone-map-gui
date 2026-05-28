# ============================================================
#preflight
# ============================================================

import threading
import time
from pymavlink import mavutil

class PreflightChecker:
    """
    Runs MAVLink preflight checks in a background thread.
 
    Usage:
        checker = PreflightChecker(
            connection_string="udp:127.0.0.1:14550",
            on_message=my_callback          # fn(text, level)
        )
        checker.run()                       # non-blocking
    """
    def __init__(
            self,
            connection_string: str = None,
            serial_port: str = None,
            baudrate: int = 921600,
            on_message=None,
            existing_connection=None       # pass your live mavutil connection directly
        ):

        self._conn_str          = connection_string
        self._serial_port       = serial_port
        self._baudrate          = baudrate
        self._on_message        = on_message
        self._master            = None
        self._existing_conn     = existing_connection
 
    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------
 
    def run(self):
        """Spawn the checks in a daemon thread (non-blocking)."""
        t = threading.Thread(target=self._worker, daemon=True)
        t.start()
 
    # ----------------------------------------------------------
    # Internal helpers
    # ----------------------------------------------------------
 
    def _log(self, text: str, level: str = "INFO"):
        """Forward a message to whoever owns the UI."""
        self._on_message(text, level)
 
    def _connect(self) -> bool:
        try:
            self._log("Connecting to vehicle...", "INFO")

            # SERIAL
            if self._serial_port:
                self._master = mavutil.mavlink_connection(
                    self._serial_port,
                    baud=self._baudrate,
                    source_system = 255
                )

            # UDP/TCP
            else:
                self._master = mavutil.mavlink_connection(
                    self._conn_str
                )

            # WAIT FOR HEARTBEAT
            self._master.wait_heartbeat(timeout=10)
            # Request MAVLink data streams
            self._master.mav.request_data_stream_send(
                self._master.target_system,
                self._master.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_ALL,
                4,   # rate Hz
                1    # start
)

            self._log(
                "Heartbeat received — vehicle connected.",
                "OK"
            )

            return True

        except Exception as e:
            self._log(f"Connection failed: {e}", "ERROR")
            self._master = None
            return False

    def _request_streams(self):
        """Request individual data streams explicitly."""
        m = self._master

        streams = [
            mavutil.mavlink.MAV_DATA_STREAM_EXTENDED_STATUS,  # SYS_STATUS, GPS
            mavutil.mavlink.MAV_DATA_STREAM_RAW_SENSORS,      # IMU, MAG
            mavutil.mavlink.MAV_DATA_STREAM_EXTRA2,           # EKF (on some builds)
            mavutil.mavlink.MAV_DATA_STREAM_ALL,              # catch-all
        ]

        for stream_id in streams:
            m.mav.request_data_stream_send(
                m.target_system,
                m.target_component,
                stream_id,
                10,   # 10 Hz
                1     # start
            )

        self._log("Stream requests sent — waiting for data...", "INFO")
        time.sleep(2)  # give vehicle time to start streaming
 
    # ----------------------------------------------------------
    # Worker (runs on background thread)
    # ----------------------------------------------------------
 
    def _worker(self):
        failed = []

        # If caller passed a live connection, reuse it — don't open a new one
        if self._existing_conn is not None:
            self._master = self._existing_conn
            self._log("Using existing vehicle connection.", "INFO")
        elif not self._connect():
            return

        m = self._master
        self._log("── Starting preflight checks ──", "INFO")
        self._log("Vehicle armable — connected via heartbeat", "OK")

        self._request_streams()   # <── request streams HERE, after connect settles

        gps     = None
        battery = None
        ekf     = None
        mag     = None

        start = time.time()

        while time.time() - start < 10:
            msg = m.recv_match(blocking=False)
            if not msg:
                time.sleep(0.05)
                continue

            msg_type = msg.get_type()

            if msg_type == "GPS_RAW_INT":
                gps = msg

            elif msg_type == "SYS_STATUS":
                battery = msg
                mag = bool(battery.onboard_control_sensors_health & 0x00000004)

            elif msg_type == "EKF_STATUS_REPORT":
                ekf = msg

            if all(x is not None for x in [gps, battery, ekf, mag]):
                break

        # ── GPS ───────────────────────────────────────────────────
        if gps:
            sats = gps.satellites_visible
            if sats >= 6:
                self._log(f"GPS lock — {sats} satellites", "OK")
            else:
                self._log(f"Low GPS satellites ({sats})", "WARN")
                failed.append(f"Low GPS satellites ({sats})")
        else:
            self._log("GPS not detected", "ERROR")
            failed.append("GPS not detected")

        # ── BATTERY ───────────────────────────────────────────────
        if battery:
            voltage = battery.voltage_battery / 1000.0
            if voltage > 10.5:
                self._log(f"Battery healthy — {voltage:.1f} V", "OK")
            else:
                self._log(f"Low battery — {voltage:.1f} V", "WARN")
                failed.append(f"Low battery ({voltage:.1f} V)")
        else:
            self._log("Battery data unavailable", "ERROR")
            failed.append("Battery data unavailable")

        # ── EKF ───────────────────────────────────────────────────
        if ekf:
            flags = ekf.flags
            # bit 0x1F = velocity/pos/terrain/const_pos/pred_horiz flags
            healthy = bool(flags & 0x01)  # EKF_ATTITUDE at minimum
            if healthy:
                self._log("EKF healthy", "OK")
            else:
                self._log("EKF flags indicate unhealthy state", "WARN")
                failed.append("EKF unhealthy")
        else:
            # Fallback: EKF_STATUS_REPORT not sent — check STATUSTEXT
            self._log("EKF_STATUS_REPORT not received (may still be OK in SITL)", "WARN")

        # ── COMPASS ───────────────────────────────────────────────
        if mag is True:
            self._log("Compass healthy (sensor bitmask OK)", "OK")
        elif mag is False:
            self._log("Compass unhealthy (sensor bitmask)", "ERROR")
            failed.append("Compass unhealthy")
        else:
            self._log("Compass status unavailable (no SYS_STATUS)", "ERROR")
            failed.append("Compass status unavailable")

        # ── RESULT ────────────────────────────────────────────────
        if not failed:
            self._log("── All checks passed ──", "OK")
        else:
            self._log(f"── {len(failed)} check(s) failed ──", "ERROR")
            for item in failed:
                self._log(f"   • {item}", "WARN")