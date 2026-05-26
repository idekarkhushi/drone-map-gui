# ============================================================
#preflight
# ============================================================

import threading
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
            on_message=None
        ):

        self._conn_str   = connection_string
        self._serial_port = serial_port
        self._baudrate    = baudrate
        self._on_message = on_message
        self._master     = None
 
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
 
    # ----------------------------------------------------------
    # Worker (runs on background thread)
    # ----------------------------------------------------------
 
    def _worker(self):
        failed = []
 
        if not self._connect():
            return
 
        m = self._master
        self._log("── Starting preflight checks ──", "INFO")
 
        # Connection itself confirmed heartbeat — vehicle is alive
        self._log("Vehicle armable — connected via heartbeat", "OK")

        m = self._master
        self._log("── Starting preflight checks ──", "INFO")
 
        import time

        gps = None
        battery = None
        ekf = None
        imu = None

        start = time.time()

        # Collect MAVLink packets for 8 seconds
        while time.time() - start < 8:

            msg = m.recv_match(blocking=True, timeout=1)

            if not msg:
                continue

            msg_type = msg.get_type()

            # GPS
            if msg_type == "GPS_RAW_INT":
                gps = msg

            # Battery
            elif msg_type == "SYS_STATUS":
                battery = msg

            # EKF
            elif msg_type == "EKF_STATUS_REPORT":
                ekf = msg

            # IMU / Compass
            elif msg_type == "RAW_IMU":
                imu = msg

        # ── GPS ───────────────────────────────────────────
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

        # ── BATTERY ───────────────────────────────────────
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

        # ── EKF ───────────────────────────────────────────
        if ekf:
            self._log("EKF healthy", "OK")
        else:
            self._log("EKF not healthy", "ERROR")
            failed.append("EKF not healthy")

        # ── COMPASS ───────────────────────────────────────
        if imu:
            self._log("Compass detected", "OK")
        else:
            self._log("Compass not detected", "ERROR")
            failed.append("Compass not detected")
 
        # ── RESULT ────────────────────────────────────────
        if not failed:
            self._log("── All checks passed──", "OK")
        else:
            self._log(f"── {len(failed)} check(s) failed ──", "ERROR")
            for item in failed:
                self._log(f"   • {item}", "WARN")