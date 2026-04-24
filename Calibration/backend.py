import logging
import threading
import time

from pymavlink import mavutil
from serial import SerialException

log = logging.getLogger(__name__)


class DroneBackend:
    # Human-readable labels for the six ArduPilot accelerometer poses.
    # ArduPilot requests these in order 1-6 via COMMAND_LONG.
    ACCEL_POSITION_LABELS = {
        1: "level",
        2: "on its LEFT side",
        3: "on its RIGHT side",
        4: "nose DOWN",
        5: "nose UP",
        6: "upside DOWN",
    }

    # ArduPilot sends these sentinel values in param1 of
    # MAV_CMD_ACCELCAL_VEHICLE_POS to signal end-of-sequence.
    # 16777215 = SUCCESS, 16777216 = FAILED.
    # These are NOT real placement requests and must be ignored.
    ACCEL_TERMINAL_POSITIONS = {16777215, 16777216}

    def __init__(self):
        # ── Serial / MAVLink connection ──────────────────────────────────
        self.master = None        # mavutil connection object, None when disconnected
        self.running = False      # set False to stop background threads cleanly
        self.last_heartbeat = None

        # Protects all mutable state below from concurrent access by the
        # reader thread and the main (GUI) thread.
        self._lock = threading.Lock()

        # ── Accelerometer calibration state ─────────────────────────────
        # ArduPilot drives a 6-step request/confirm flow:
        #   1. We send PREFLIGHT_CALIBRATION (param5=1)
        #   2. ArduPilot sends COMMAND_LONG(ACCELCAL_VEHICLE_POS, param1=<pos>)
        #   3. User places drone, clicks Next → we echo the same command back
        #   4. Repeat for all 6 positions
        #   5. ArduPilot sends STATUSTEXT "Calibration successful / failed"
        self.in_calibration = False
        self.current_step = 0                    # last position ack'd (1-6)
        self._current_requested_position = None  # position ArduPilot is waiting on
        self._ack_in_flight = False              # True between confirm click and ack send
        self._last_displayed_position = None     # prevents duplicate log lines per position
        self._pending_accel_success = False      # wait to announce success until vehicle is level again

        # ── Compass calibration state ────────────────────────────────────
        self.compass_calibration = False

        # ── Movement detection ───────────────────────────────────────────
        # Updated continuously from RAW_IMU; blocks "Next" when True.
        self.is_moving = False
        self.is_level = False

        # ── GUI callbacks ────────────────────────────────────────────────
        # Assign these before calling connect(). Each is called from the
        # background reader thread — wrap with after() in tkinter.
        self.cb_status = None           # (text: str, color: str)
        self.cb_text = None             # (text: str)  — raw STATUSTEXT lines
        self.cb_telemetry = None        # (mode: str|None, battery: int|None)
        self.cb_ack = None              # (result: int)
        self.cb_progress = None         # (value: int)  — 0-100
        self.cb_confirm_ready = None    # (enabled: bool) — enable/disable Next button
        self.cb_calibration_done = None # (success: bool)
        self.cb_position_update = None  # (position: int, state: str)
                                        # state: "reset" | "active" | "done"

    # =========================================================================
    # CONNECTION
    # =========================================================================

    def connect(self, port, baud):
        """
        Open a MAVLink connection on `port` at `baud` and wait for the first
        heartbeat (up to 8 seconds). Starts the reader and watchdog threads.
        Returns True on success, False on failure.
        """
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
        """
        Cleanly close the MAVLink connection and stop background threads.
        Safe to call even if not currently connected.
        """
        self.running = False
        if self.master:
            try:
                self.master.close()
            except Exception:
                pass
        self.master = None
        self._status("Disconnected", "#cccccc")

    # =========================================================================
    # ACCELEROMETER CALIBRATION
    # =========================================================================

    def start_accel_calibration(self):
        """
        Send the PREFLIGHT_CALIBRATION command with param5=1 to begin the
        6-position accelerometer calibration sequence. Resets all calibration
        state and disables the Next button until ArduPilot requests pose 1.
        Returns False if not connected.
        """
        if not self.master:
            self._status("Not connected", "red")
            return False

        # param5=1 selects accelerometer calibration in the preflight command.
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_PREFLIGHT_CALIBRATION,
            0,              # confirmation
            0, 0, 0, 0,     # param1-4 unused
            1,              # param5 = 1 → accel cal
            0, 0,           # param6-7 unused
        )

        with self._lock:
            self.in_calibration = True
            self.current_step = 0
            self._current_requested_position = None
            self._ack_in_flight = False
            self._last_displayed_position = None
            self._pending_accel_success = False

        self._progress(0)
        self._confirm_ready(False)
        self._position_update(0, "reset")
        self._status("Accel calibration started — waiting for position request", "#f0ad4e")
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

        # Disable button and mark ack in flight before sending so that any
        # repeated COMMAND_LONG from ArduPilot arriving during transmission
        # does not re-enable the button or print a duplicate log line.
        self._confirm_ready(False)
        with self._lock:
            self._current_requested_position = None
            self._ack_in_flight = True
            self._last_displayed_position = None  # allow next position to display

        self._next_accel_step(pos)

    def _next_accel_step(self, position):
        """
        Echo the requested position back to ArduPilot via
        MAV_CMD_ACCELCAL_VEHICLE_POS. ArduPilot uses this to confirm the
        drone is in the correct pose before sampling the IMU.
        """
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_ACCELCAL_VEHICLE_POS,
            0,
            float(position),    # param1 = position enum value
            0, 0, 0, 0, 0, 0,
        )

        with self._lock:
            self.current_step = position
            self._ack_in_flight = False

        # Mark this position green in the sidebar and update the progress bar.
        self._position_update(position, "done")
        progress = min(int((position / 6) * 100), 100)
        self._progress(progress)

    def _accel_position_text(self, position):
        """Return a human-readable string like 'position 4 (nose DOWN)'."""
        label = self.ACCEL_POSITION_LABELS.get(position)
        if label is None:
            return f"position {position}"
        return f"position {position} ({label})"

    def _finalize_success(self):
        with self._lock:
            self.in_calibration = False
            self.compass_calibration = False
            self._current_requested_position = None
            self._ack_in_flight = False
            self._pending_accel_success = False

        self._progress(100)
        self._confirm_ready(False)
        self._status("Calibration successful", "green")
        self._calibration_done(success=True)

    # =========================================================================
    # COMPASS CALIBRATION
    # =========================================================================

    def start_compass_calibration(self):
        """
        Send PREFLIGHT_CALIBRATION with param2=1 to start onboard compass
        calibration. Progress is reported via MAG_CAL_PROGRESS messages and
        the final result via MAG_CAL_REPORT.
        """
        if not self.master:
            self._status("Not connected", "red")
            return False

        # param2=1 selects magnetometer / compass calibration.
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_PREFLIGHT_CALIBRATION,
            0,
            0, 1, 0, 0,     # param2=1 → compass cal
            0, 0, 0,
        )

        with self._lock:
            self.compass_calibration = True

        self._progress(0)
        self._status("Compass calibration started", "#f0ad4e")
        return True

    # =========================================================================
    # MAVLINK READER LOOP
    # =========================================================================

    def _reader_loop(self):
        """
        Background thread: continuously reads MAVLink messages and dispatches
        them to the appropriate handler block.

        Exits cleanly on SerialException (physical disconnect) and sets
        self.running = False so the watchdog thread also stops.
        """
        while self.running:
            try:
                msg = self.master.recv_match(blocking=True, timeout=1)
                if not msg:
                    # timeout — no message in the last second, loop again
                    continue

                msg_type = msg.get_type()

                # ── HEARTBEAT ────────────────────────────────────────────
                # Refresh the heartbeat timestamp used by the watchdog and
                # update the flight mode shown in the telemetry bar.
                if msg_type == "HEARTBEAT":
                    with self._lock:
                        self.last_heartbeat = time.time()
                    mode = mavutil.mode_string_v10(msg)
                    self._telemetry(mode=mode)

                # ── SYS_STATUS ───────────────────────────────────────────
                # Battery percentage lives here; pass it to the telemetry bar.
                elif msg_type == "SYS_STATUS":
                    battery = getattr(msg, "battery_remaining", -1)
                    self._telemetry(battery=battery)

                # ── RAW_IMU ──────────────────────────────────────────────
                # compare total acceleration magnitude to 1g.
                # In any static orientation the magnitude is always ~1g.
                # Significant deviation means the drone is actually moving.
                elif msg_type == "RAW_IMU":
                    ax = msg.xacc / 1000.0
                    ay = msg.yacc / 1000.0
                    az = msg.zacc / 1000.0

                    magnitude = (ax**2 + ay**2 + az**2) ** 0.5
                    moving = abs(magnitude - 1.0) > 0.3
                    level = abs(ax) < 0.25 and abs(ay) < 0.25 and abs(az - 1.0) < 0.25

                    with self._lock:
                        self.is_moving = moving
                        self.is_level = level
                        pending_accel_success = self._pending_accel_success

                    if moving:
                        self._status("Drone moving!", "red")
                    elif pending_accel_success and level:
                        self._finalize_success()

                # ── STATUSTEXT ───────────────────────────────────────────
                # General text messages from the flight controller.
                # pymavlink returns msg.text as bytes (null-padded to 50 chars)
                # in Python 3, so it must be decoded before string operations.
                elif msg_type == "STATUSTEXT":
                    raw = msg.text
                    if isinstance(raw, bytes):
                        text = raw.decode("utf-8", errors="ignore").rstrip("\x00")
                    else:
                        text = str(raw).rstrip("\x00")

                    # Send every line to the textbox regardless of content.
                    self._text(text)
                    lowered = text.lower()

                    if "successful" in lowered:
                        with self._lock:
                            accel_success_ready = self.in_calibration and self.current_step >= 6
                            already_level = self.is_level

                        # Delay the final success message until the vehicle is
                        # back in the original level pose after the 6th step.
                        if accel_success_ready and not already_level:
                            with self._lock:
                                self._pending_accel_success = True
                            self._status(
                                "Calibration data saved. Place drone level to finish.",
                                "#f0ad4e",
                            )
                            self._text("Please return vehicle to the original level position")
                        else:
                            self._finalize_success()

                    elif "failed" in lowered:
                        with self._lock:
                            self.in_calibration = False
                            self.compass_calibration = False
                            self._current_requested_position = None
                            self._ack_in_flight = False
                            self._pending_accel_success = False
                        self._confirm_ready(False)
                        self._status("Calibration failed", "red")
                        self._calibration_done(success=False)

                # ── COMMAND_LONG ─────────────────────────────────────────
                # ArduPilot sends MAV_CMD_ACCELCAL_VEHICLE_POS to request each
                # of the 6 placement poses during accelerometer calibration.
                # It re-sends the same request every ~2 s until it receives the
                # echo-back ack, so _last_displayed_position prevents flooding
                # the textbox with duplicate lines.
                elif msg_type == "COMMAND_LONG":
                    if msg.command == mavutil.mavlink.MAV_CMD_ACCELCAL_VEHICLE_POS:
                        position = int(msg.param1)

                        # Ignore terminal sentinel values (SUCCESS / FAILED).
                        # These signal end-of-sequence, not a real pose request.
                        # Outcome is already handled by the STATUSTEXT branch.
                        if position in self.ACCEL_TERMINAL_POSITIONS:
                            log.info("Accel cal terminal signal received: %d", position)
                            continue

                        position_text = self._accel_position_text(position)

                        with self._lock:
                            ack_in_flight = self._ack_in_flight
                            already_displayed = self._last_displayed_position == position
                            self._current_requested_position = position

                        # Only update UI on the first arrival of each position
                        # request. Repeated requests while ack is in flight or
                        # for the same position are silently absorbed.
                        if not ack_in_flight and not already_displayed:
                            with self._lock:
                                self._last_displayed_position = position
                            self._position_update(position, "active")
                            self._status(
                                f"Place drone {position_text}, keep still, then click Next",
                                "#f0ad4e",
                            )
                            self._text(f"Please place vehicle {position_text}")
                            self._confirm_ready(True)

                # ── MAG_CAL_PROGRESS ─────────────────────────────────────
                # Compass calibration streams per-magnetometer completion
                # percentages. Forward directly to the progress bar.
                elif msg_type == "MAG_CAL_PROGRESS":
                    self._progress(msg.completion_pct)

                # ── MAG_CAL_REPORT ───────────────────────────────────────
                # Final compass calibration result per magnetometer.
                elif msg_type == "MAG_CAL_REPORT":
                    if msg.cal_status == mavutil.mavlink.MAG_CAL_SUCCESS:
                        self._status("Compass success", "green")
                    else:
                        self._status("Compass failed", "red")

                # ── COMMAND_ACK ──────────────────────────────────────────
                # Generic command acknowledgement — pass result code to GUI.
                elif msg_type == "COMMAND_ACK":
                    self._ack(msg.result)

            except SerialException as e:
                # Physical disconnect (USB unplugged, device reset, etc.).
                # Stop the loop immediately — retrying on a dead port would
                # spam the log and lock the thread.
                log.error("Serial port lost: %s", e)
                self.running = False
                with self._lock:
                    self.in_calibration = False
                    self.compass_calibration = False
                    self._current_requested_position = None
                    self._ack_in_flight = False
                    self._pending_accel_success = False
                self._confirm_ready(False)
                self._status("Disconnected — cable unplugged or device reset", "red")
                self._calibration_done(success=False)
                break

            except Exception as e:
                # Non-fatal error (malformed packet, etc.) — log and continue.
                log.exception("Reader loop error")
                self._status(f"Error: {e}", "red")

    # =========================================================================
    # HEARTBEAT WATCHDOG
    # =========================================================================

    def _heartbeat_watchdog(self):
        """
        Background thread: checks every second whether a HEARTBEAT was
        received within the last 5 seconds. Surfaces a warning if the link
        goes stale without a SerialException (e.g. wireless link dropout).
        """
        while self.running:
            time.sleep(1)
            with self._lock:
                last = self.last_heartbeat
            if last is not None and (time.time() - last) > 5:
                self._status("Heartbeat lost!", "red")

    # =========================================================================
    # CALLBACK DISPATCHERS
    # =========================================================================
    # Thin wrappers so callers never need to null-check cb_* directly.
    # All fired from background threads — GUI must use self.after(0, ...).

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
