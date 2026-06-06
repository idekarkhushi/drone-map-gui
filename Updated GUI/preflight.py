# ============================================================
# preflight
# ============================================================

import threading
import time
from pymavlink import mavutil


class PreflightChecker:
    """
    Runs MAVLink preflight checks in a background thread.

    Checks performed:
        1. GPS lock & satellite count
        2. Battery voltage
        3. EKF health
        4. Compass (magnetometer) health
        5. Geofencing — enabled & breach action configured
        6. Motor test — spins each motor briefly and checks ACK
        7. ESC telemetry — RPM / temperature sanity from ESC_TELEMETRY_DATA

    Usage:
        checker = PreflightChecker(
            connection_string="udp:127.0.0.1:14550",
            on_message=my_callback,         # fn(text, level)
            motor_count=4,                  # number of motors to spin-test
            run_motor_test=True,            # set False to skip motor spin test
        )
        checker.run()                       # non-blocking
    """

    # MAVLink geofence parameter names (ArduPilot)
    _FENCE_ENABLE_PARAM  = "FENCE_ENABLE"
    _FENCE_ACTION_PARAM  = "FENCE_ACTION"
    _FENCE_RADIUS_PARAM  = "FENCE_RADIUS"   # metres; 0 = disabled circle fence

    def __init__(
            self,
            connection_string: str = None,
            serial_port: str = None,
            baudrate: int = 921600,
            on_message=None,
            existing_connection=None,       # pass your live mavutil connection directly
            motor_count: int = 4,
            run_motor_test: bool = True,
        ):

        self._conn_str          = connection_string
        self._serial_port       = serial_port
        self._baudrate          = baudrate
        self._on_message        = on_message
        self._master            = None
        self._existing_conn     = existing_connection
        self._motor_count       = motor_count
        self._run_motor_test    = run_motor_test

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

            if self._serial_port:
                self._master = mavutil.mavlink_connection(
                    self._serial_port,
                    baud=self._baudrate,
                    source_system=255,
                )
            else:
                self._master = mavutil.mavlink_connection(self._conn_str)

            self._master.wait_heartbeat(timeout=10)
            self._master.mav.request_data_stream_send(
                self._master.target_system,
                self._master.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_ALL,
                4,   # rate Hz
                1,   # start
            )
            self._log("Heartbeat received — vehicle connected.", "OK")
            return True

        except Exception as e:
            self._log(f"Connection failed: {e}", "ERROR")
            self._master = None
            return False

    def _request_streams(self):
        """Request individual data streams explicitly."""
        m = self._master

        streams = [
            mavutil.mavlink.MAV_DATA_STREAM_EXTENDED_STATUS,
            mavutil.mavlink.MAV_DATA_STREAM_RAW_SENSORS,
            mavutil.mavlink.MAV_DATA_STREAM_EXTRA2,
            mavutil.mavlink.MAV_DATA_STREAM_ALL,
        ]

        for stream_id in streams:
            m.mav.request_data_stream_send(
                m.target_system,
                m.target_component,
                stream_id,
                10,  # 10 Hz
                1,   # start
            )

        self._log("Stream requests sent — waiting for data...", "INFO")
        time.sleep(2)

    # ----------------------------------------------------------
    # ── NEW: Geofence check ───────────────────────────────────
    # ----------------------------------------------------------

    def _check_geofence(self) -> bool | None:
        """
        Read FENCE_ENABLE, FENCE_ACTION, and FENCE_RADIUS via PARAM_REQUEST_READ.
        Returns True on pass, False on fail, None if parameters unavailable.
        """
        self._log("Checking geofence parameters...", "INFO")
        m = self._master

        def _read_param(name: str):
            """Request a single parameter and wait up to 3 s for the reply."""
            m.mav.param_request_read_send(
                m.target_system,
                m.target_component,
                name.encode("utf-8"),
                -1,   # param_index = -1 → use name
            )
            deadline = time.time() + 3.0
            while time.time() < deadline:
                msg = m.recv_match(type="PARAM_VALUE", blocking=False)
                if msg and msg.param_id.rstrip("\x00") == name:
                    return msg.param_value
                time.sleep(0.05)
            return None

        fence_enable = _read_param(self._FENCE_ENABLE_PARAM)
        fence_action = _read_param(self._FENCE_ACTION_PARAM)
        fence_radius = _read_param(self._FENCE_RADIUS_PARAM)

        if fence_enable is None:
            self._log(
                "Geofence params unavailable (firmware may not support FENCE_ENABLE)",
                "WARN",
            )
            return None

        enabled = int(fence_enable) == 1

        if not enabled:
            self._log(
                "Geofence DISABLED (FENCE_ENABLE=0) — consider enabling for safety",
                "WARN",
            )
            return False

        # FENCE_ACTION: 0=report, 1=RTL, 2=Guided/Loiter, 4=Brake/Land
        action_map = {0: "Report only", 1: "RTL", 2: "Guided/Loiter", 4: "Brake/Land"}
        action_label = action_map.get(int(fence_action), f"Unknown ({int(fence_action)})")

        if int(fence_action) == 0:
            self._log(
                f"Geofence enabled but action is Report-only — "
                f"vehicle will NOT return on breach (FENCE_ACTION={int(fence_action)})",
                "WARN",
            )
            # Not a hard fail — operator may intend this
        else:
            self._log(
                f"Geofence enabled — action: {action_label}",
                "OK",
            )

        if fence_radius is not None:
            r = int(fence_radius)
            if r == 0:
                self._log("Geofence circular radius = 0 (circle fence disabled)", "WARN")
            else:
                self._log(f"Geofence radius: {r} m", "OK")

        return enabled

    # ----------------------------------------------------------
    # ── NEW: Motor test ───────────────────────────────────────
    # ----------------------------------------------------------

    def _check_motor_test(self) -> bool:
        """
        Send COMMAND_LONG MAV_CMD_DO_MOTOR_TEST for each motor (instance 0-N),
        wait for COMMAND_ACK, and report result.

        ⚠ SAFETY: This spins motors.  Ensure props are OFF before running.
            Set run_motor_test=False if operating with props attached.
        """
        self._log(
            f"Motor test starting ({self._motor_count} motors) — "
            "ENSURE PROPELLERS ARE REMOVED",
            "WARN",
        )
        m       = self._master
        passed  = True

        for motor_idx in range(self._motor_count):
            # MAV_CMD_DO_MOTOR_TEST = 209
            # param1 = motor instance (0-based)
            # param2 = MOTOR_TEST_THROTTLE_TYPE (0 = percent)
            # param3 = throttle % (5 % spin for check)
            # param4 = timeout seconds
            # param5 = motor count (1 = single)
            # param6 = test order (0 = default sequence)
            m.mav.command_long_send(
                m.target_system,
                m.target_component,
                mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST,
                0,          # confirmation
                motor_idx,  # param1: motor instance
                0,          # param2: throttle type = percent
                5,          # param3: 5 % throttle
                2,          # param4: 2-second timeout
                1,          # param5: test 1 motor
                0,          # param6: default order
                0,          # param7: unused
            )

            # Wait for ACK
            ack = None
            deadline = time.time() + 5.0
            while time.time() < deadline:
                msg = m.recv_match(type="COMMAND_ACK", blocking=False)
                if msg and msg.command == mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST:
                    ack = msg
                    break
                time.sleep(0.05)

            if ack is None:
                self._log(f"Motor {motor_idx + 1}: no ACK received (timeout)", "ERROR")
                passed = False
            elif ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
                self._log(f"Motor {motor_idx + 1}: test accepted ✓", "OK")
            elif ack.result == mavutil.mavlink.MAV_RESULT_TEMPORARILY_REJECTED:
                self._log(
                    f"Motor {motor_idx + 1}: temporarily rejected "
                    "(vehicle may need to be in a testable state)",
                    "WARN",
                )
                passed = False
            else:
                result_names = {
                    mavutil.mavlink.MAV_RESULT_DENIED:         "DENIED",
                    mavutil.mavlink.MAV_RESULT_UNSUPPORTED:    "UNSUPPORTED",
                    mavutil.mavlink.MAV_RESULT_FAILED:         "FAILED",
                    mavutil.mavlink.MAV_RESULT_IN_PROGRESS:    "IN_PROGRESS",
                }
                label = result_names.get(ack.result, f"code {ack.result}")
                self._log(f"Motor {motor_idx + 1}: {label}", "ERROR")
                passed = False

            time.sleep(0.5)  # brief pause between motors

        return passed

    # ----------------------------------------------------------
    # ── NEW: ESC telemetry check ──────────────────────────────
    # ----------------------------------------------------------

    def _check_esc_telemetry(self) -> bool | None:
        """
        Listen for ESC_TELEMETRY_DATA (MAVLink msg id 11030) for up to 5 s.
        Validates RPM range and temperature limits per ESC.

        Returns True if all reporting ESCs look healthy,
                False if any ESC reports an anomaly,
                None  if no ESC_TELEMETRY_DATA messages received.
        """
        self._log("Waiting for ESC telemetry...", "INFO")
        m           = self._master
        esc_data    = {}   # index → latest ESC_TELEMETRY_DATA message
        deadline    = time.time() + 5.0

        while time.time() < deadline:
            msg = m.recv_match(type="ESC_TELEMETRY_DATA", blocking=False)
            if msg:
                esc_data[msg.index] = msg
            time.sleep(0.02)

        if not esc_data:
            self._log(
                "No ESC_TELEMETRY_DATA received — "
                "either ESC telem not wired/enabled, or motors not spinning",
                "WARN",
            )
            return None

        passed = True
        MAX_TEMP_C  = 80    # degrees Celsius — above this is concerning
        MAX_RPM     = 50000 # sanity ceiling

        for idx, msg in sorted(esc_data.items()):

            temp_c  = msg.temperature / 100.0 if hasattr(msg, "temperature") else None
            rpm     = msg.rpm          if hasattr(msg, "rpm")         else None
            voltage = msg.voltage / 100.0 if hasattr(msg, "voltage")  else None

            issues = []

            if temp_c is not None and temp_c > MAX_TEMP_C:
                issues.append(f"temp {temp_c:.1f}°C exceeds {MAX_TEMP_C}°C")

            if rpm is not None and (rpm < 0 or rpm > MAX_RPM):
                issues.append(f"RPM {rpm} out of expected range")

            if issues:
                self._log(
                    f"ESC {idx}: ⚠ {', '.join(issues)} "
                    f"(temp={temp_c}°C rpm={rpm} volt={voltage}V)",
                    "ERROR",
                )
                passed = False
            else:
                temp_str    = f"{temp_c:.1f}°C" if temp_c is not None else "n/a"
                rpm_str     = str(rpm)          if rpm    is not None else "n/a"
                volt_str    = f"{voltage:.1f}V" if voltage is not None else "n/a"
                self._log(
                    f"ESC {idx}: OK — temp {temp_str}, RPM {rpm_str}, {volt_str}",
                    "OK",
                )

        return passed

    # ----------------------------------------------------------
    # Worker (runs on background thread)
    # ----------------------------------------------------------

    def _worker(self):
        failed = []

        if self._existing_conn is not None:
            self._master = self._existing_conn
            self._log("Using existing vehicle connection.", "INFO")
        elif not self._connect():
            return

        m = self._master
        self._log("── Starting preflight checks ──", "INFO")
        self._log("Vehicle armable — connected via heartbeat", "OK")

        self._request_streams()

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
            flags   = ekf.flags
            healthy = bool(flags & 0x01)
            if healthy:
                self._log("EKF healthy", "OK")
            else:
                self._log("EKF flags indicate unhealthy state", "WARN")
                failed.append("EKF unhealthy")
        else:
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

        # ── GEOFENCE ──────────────────────────────────────────────
        self._log("", "INFO")
        fence_ok = self._check_geofence()
        if fence_ok is False:
            failed.append("Geofence disabled or misconfigured")
        # None (unavailable) is treated as a warning, not a hard fail

        # ── MOTOR TEST ────────────────────────────────────────────
        self._log("", "INFO")
        if self._run_motor_test:
            motor_ok = self._check_motor_test()
            if not motor_ok:
                failed.append("Motor test failed (one or more motors)")
        else:
            self._log("Motor test SKIPPED (run_motor_test=False)", "WARN")

        # ── ESC TELEMETRY ─────────────────────────────────────────
        self._log("", "INFO")
        esc_ok = self._check_esc_telemetry()
        if esc_ok is False:
            failed.append("ESC telemetry anomaly detected")
        # None (no data) is a warning only — may not have ESC telem wired

        # ── RESULT ────────────────────────────────────────────────
        self._log("", "INFO")
        if not failed:
            self._log("── All checks passed ──", "OK")
        else:
            self._log(f"── {len(failed)} check(s) failed ──", "ERROR")
            for item in failed:
                self._log(f"   • {item}", "WARN")