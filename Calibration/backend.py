import logging
import threading
import time

from pymavlink import mavutil
from serial import SerialException

log = logging.getLogger(__name__)


class DroneBackend:
    ACCEL_POSITION_LABELS = {
        1: "level",
        2: "on its LEFT side",
        3: "on its RIGHT side",
        4: "nose DOWN",
        5: "nose UP",
        6: "upside DOWN",
    }

    ACCEL_TERMINAL_POSITIONS = {16777215, 16777216}

    def __init__(self):
        self.master = None
        self.running = False
        self.last_heartbeat = None

        self._lock = threading.Lock()

        # Accelerometer calibration is a request/confirm flow:
        # autopilot requests a pose -> UI enables "Next" -> user confirms pose.
        self.in_calibration = False
        self.current_step = 0
        self._current_requested_position = None
        self._ack_in_flight = False

        self.compass_calibration = False
        self.is_moving = False

        self.cb_status = None
        self.cb_text = None
        self.cb_telemetry = None
        self.cb_ack = None
        self.cb_progress = None
        self.cb_confirm_ready = None
        self.cb_calibration_done = None
        self.cb_position_update = None  # (position, state) state = "active"|"done"|"reset"

    # ================= CONNECTION =================

    def connect(self, port, baud):
        try:
            self.master = mavutil.mavlink_connection(port, baud=baud)
            self.master.wait_heartbeat(timeout=8)

            self.running = True
            self.last_heartbeat = time.time()

            self._status(f"Connected to {port}", "green")

            threading.Thread(target=self._reader_loop, daemon=True).start()
            threading.Thread(target=self._heartbeat_watchdog, daemon=True).start()
            return True

        except Exception as e:
            self.master = None
            self._status(f"Connection failed: {e}", "red")
            return False

    def disconnect(self):
        self.running = False
        if self.master:
            try:
                self.master.close()
            except Exception:
                pass
        self.master = None
        self._status("Disconnected", "#cccccc")

    # ================= ACCEL =================

    def start_accel_calibration(self):
        if not self.master:
            self._status("Not connected", "red")
            return False

        # MAV_CMD_PREFLIGHT_CALIBRATION uses param5=1 to start accel calibration.
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_PREFLIGHT_CALIBRATION,
            0,
            0, 0, 0, 0,
            1,
            0, 0,
        )

        with self._lock:
            self.in_calibration = True
            self.current_step = 0
            self._current_requested_position = None
            self._ack_in_flight = False

        self._progress(0)
        self._confirm_ready(False)
        self._position_update(0, "reset")
        self._status("Accel calibration started - waiting for position request", "#f0ad4e")
        return True

    def confirm_position(self):
        with self._lock:
            pos = self._current_requested_position
            moving = self.is_moving

        if pos is None:
            self._status("No position requested yet", "red")
            return

        if moving:
            self._status("Keep drone still!", "red")
            return

        self._confirm_ready(False)
        with self._lock:
            self._current_requested_position = None
            self._ack_in_flight = True

        self._next_accel_step(pos)

    def _next_accel_step(self, position):
        # Send the currently requested orientation back to the flight controller
        # to acknowledge that the vehicle has been placed and kept still.
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_ACCELCAL_VEHICLE_POS,
            0,
            float(position),
            0, 0, 0, 0, 0, 0,
        )

        with self._lock:
            self.current_step = position
            self._ack_in_flight = False

        self._position_update(position, "done")
        progress = min(int((position / 6) * 100), 100)
        self._progress(progress)

    def _accel_position_text(self, position):
        label = self.ACCEL_POSITION_LABELS.get(position)
        if label is None:
            return f"position {position}"
        return f"position {position} ({label})"

    # ================= COMPASS =================

    def start_compass_calibration(self):
        if not self.master:
            self._status("Not connected", "red")
            return False

        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_PREFLIGHT_CALIBRATION,
            0,
            0, 1, 0, 0,
            0, 0, 0,
        )

        with self._lock:
            self.compass_calibration = True

        self._progress(0)
        self._status("Compass calibration started", "#f0ad4e")
        return True

    # ================= MAVLINK LOOP =================

    def _reader_loop(self):
        while self.running:
            try:
                msg = self.master.recv_match(blocking=True, timeout=1)
                if not msg:
                    continue

                msg_type = msg.get_type()

                if msg_type == "HEARTBEAT":
                    with self._lock:
                        self.last_heartbeat = time.time()
                    mode = mavutil.mode_string_v10(msg)
                    self._telemetry(mode=mode)

                elif msg_type == "SYS_STATUS":
                    battery = getattr(msg, "battery_remaining", -1)
                    self._telemetry(battery=battery)

                elif msg_type == "RAW_IMU":
                    ax = msg.xacc / 1000.0
                    ay = msg.yacc / 1000.0
                    az = msg.zacc / 1000.0

                    # Use a simple stillness heuristic so "Next" is only accepted
                    # when the vehicle is roughly stationary and upright enough.
                    moving = (
                        abs(ax) > 0.3 or
                        abs(ay) > 0.3 or
                        abs(az - 1.0) > 0.2
                    )

                    with self._lock:
                        self.is_moving = moving

                    if moving:
                        self._status("Drone moving!", "red")

                elif msg_type == "STATUSTEXT":
                    raw = msg.text
                    if isinstance(raw, bytes):
                        text = raw.decode("utf-8", errors="ignore").rstrip("\x00")
                    else:
                        text = str(raw).rstrip("\x00")

                    self._text(text)
                    lowered = text.lower()

                    if "successful" in lowered:
                        self._progress(100)
                        with self._lock:
                            self.in_calibration = False
                            self.compass_calibration = False
                            self._current_requested_position = None
                            self._ack_in_flight = False
                        self._confirm_ready(False)
                        self._status("Calibration successful", "green")
                        self._calibration_done(success=True)

                    elif "failed" in lowered:
                        with self._lock:
                            self.in_calibration = False
                            self.compass_calibration = False
                            self._current_requested_position = None
                            self._ack_in_flight = False
                        self._confirm_ready(False)
                        self._status("Calibration failed", "red")
                        self._calibration_done(success=False)

                elif msg_type == "COMMAND_LONG":
                    if msg.command == mavutil.mavlink.MAV_CMD_ACCELCAL_VEHICLE_POS:
                        position = int(msg.param1)

                        # Some firmwares send terminal sentinel values at the end
                        # of the accel-cal sequence instead of a real placement.
                        if position in self.ACCEL_TERMINAL_POSITIONS:
                            log.info("Accel cal terminal signal received: %d", position)
                            continue

                        position_text = self._accel_position_text(position)

                        with self._lock:
                            ack_in_flight = self._ack_in_flight
                            self._current_requested_position = position

                        if not ack_in_flight:
                            self._position_update(position, "active")
                            self._status(
                                f"Place drone {position_text}, keep it still, then click Next",
                                "#f0ad4e",
                            )
                            self._text(f"Please place vehicle {position_text}")
                            self._confirm_ready(True)

                elif msg_type == "MAG_CAL_PROGRESS":
                    self._progress(msg.completion_pct)

                elif msg_type == "MAG_CAL_REPORT":
                    if msg.cal_status == mavutil.mavlink.MAG_CAL_SUCCESS:
                        self._status("Compass success", "green")
                    else:
                        self._status("Compass failed", "red")

                elif msg_type == "COMMAND_ACK":
                    self._ack(msg.result)

            except SerialException as e:
                log.error("Serial port lost: %s", e)
                self.running = False
                with self._lock:
                    self.in_calibration = False
                    self.compass_calibration = False
                    self._current_requested_position = None
                    self._ack_in_flight = False
                self._confirm_ready(False)
                self._status("Disconnected - cable unplugged or device reset", "red")
                self._calibration_done(success=False)
                break

            except Exception as e:
                log.exception("Reader loop error")
                self._status(f"Error: {e}", "red")

    def _heartbeat_watchdog(self):
        while self.running:
            time.sleep(1)
            with self._lock:
                last = self.last_heartbeat
            # Surface a stale-link warning even if the serial port is still open.
            if last is not None and (time.time() - last) > 5:
                self._status("Heartbeat lost!", "red")
        
    # ================= CALLBACKS =================

    def _status(self, text, color):
        if self.cb_status:
            self.cb_status(text, color)

    def _text(self, text):
        if self.cb_text:
            self.cb_text(text)

    def _telemetry(self, mode=None, battery=None):
        if self.cb_telemetry:
            self.cb_telemetry(mode, battery)

    def _ack(self, result):
        if self.cb_ack:
            self.cb_ack(result)

    def _progress(self, value):
        if self.cb_progress:
            self.cb_progress(value)

    def _confirm_ready(self, enabled: bool):
        if self.cb_confirm_ready:
            self.cb_confirm_ready(enabled)

    def _calibration_done(self, success: bool):
        if self.cb_calibration_done:
            self.cb_calibration_done(success)

    def _position_update(self, position: int, state: str):
        if self.cb_position_update:
            self.cb_position_update(position, state)
