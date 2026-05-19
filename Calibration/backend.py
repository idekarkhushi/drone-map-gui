import logging
import threading
import time

from pymavlink import mavutil
from serial import SerialException

log = logging.getLogger(__name__)


class DroneBackend:
    # Human-readable labels for the six ArduPilot accelerometer poses.
    ACCEL_POSITION_LABELS = {
        1: "level",
        2: "on its LEFT side",
        3: "on its RIGHT side",
        4: "nose DOWN",
        5: "nose UP",
        6: "upside DOWN",
    }

    ACCEL_TERMINAL_POSITIONS = {16777215, 16777216}

    # RC channel count to track (ArduPilot reports up to 18 channels)
    RC_CHANNEL_COUNT = 12

    # Time in seconds without HEARTBEAT before considering connection lost.
    HEARTBEAT_TIMEOUT = 5

    def __init__(self):
        # ── Serial / MAVLink connection ──────────────────────────────────
        self.master = None
        self.running = False
        self.last_heartbeat = None

        self._lock = threading.Lock()

        # ── Accelerometer calibration state ─────────────────────────────
        self.in_calibration = False
        self.current_step = 0
        self._current_requested_position = None
        self._ack_in_flight = False
        self._last_displayed_position = None
        self._pending_accel_success = False

        # ── Compass calibration state ────────────────────────────────────
        self.compass_calibration = False
        self._compass_progress = {}
        self._compass_results = {}

        # ── RC calibration state ─────────────────────────────────────────
        self.rc_calibration = False
        self._rc_values = {}
        self._rc_min = {}
        self._rc_max = {}
        self._rc_trim = {}
        self._rc_completed_channels = set()

        # ── Movement detection ───────────────────────────────────────────
        self.is_moving = False
        self.is_level = False

        # ── GUI callbacks ────────────────────────────────────────────────
        self.cb_status = None
        self.cb_text = None
        self.cb_telemetry = None
        self.cb_ack = None
        self.cb_progress = None
        self.cb_confirm_ready = None
        self.cb_calibration_done = None
        self.cb_accel_done = None
        self.cb_accel_progress = None
        self.cb_position_update = None
        self.cb_connection_lost = None

        # Compass-specific callbacks
        self.cb_compass_progress = None
        self.cb_compass_done = None
        self.cb_compass_state = None

        # RC-specific callbacks
        self.cb_rc_update = None
        self.cb_rc_done = None
        self.cb_rc_channel_state = None
        self.cb_rc_progress = None

    # =========================================================================
    # CONNECTION
    # =========================================================================

    def connect(self, port, baud):
        try:
            self.master = mavutil.mavlink_connection(port, baud=baud)
            self.master.wait_heartbeat(timeout=8)

            self.running = True
            self.last_heartbeat = time.time()

            # FIX: Use both the legacy stream request AND the newer
            # SET_MESSAGE_INTERVAL command so RC_CHANNELS arrive on all
            # ArduPilot versions.
            self.master.mav.request_data_stream_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_RC_CHANNELS,
                10,   # 10 Hz
                1,    # start
            )

            # Newer ArduPilot versions respond better to SET_MESSAGE_INTERVAL.
            # RC_CHANNELS message ID = 65, interval in microseconds.
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
                0,
                65,       # MAVLINK_MSG_ID_RC_CHANNELS
                100000,   # 100 ms = 10 Hz
                0, 0, 0, 0, 0,
            )

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

    # =========================================================================
    # ACCELEROMETER CALIBRATION
    # =========================================================================

    def start_accel_calibration(self):
        if not self.master:
            self._status("Not connected", "red")
            return False

        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_PREFLIGHT_CALIBRATION,
            0,
            0, 0, 0, 0,
            1,   # param5=1 → accel cal
            0, 0,
        )

        with self._lock:
            self.in_calibration = True
            self.current_step = 0
            self._current_requested_position = None
            self._ack_in_flight = False
            self._last_displayed_position = None
            self._pending_accel_success = False

        self._accel_progress(0)
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

        self._confirm_ready(False)
        with self._lock:
            self._current_requested_position = None
            self._ack_in_flight = True
            self._last_displayed_position = None

        self._next_accel_step(pos)

    def _next_accel_step(self, position):
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
        self._accel_progress(progress)

    def _accel_position_text(self, position):
        label = self.ACCEL_POSITION_LABELS.get(position)
        if label is None:
            return f"position {position}"
        return f"position {position} ({label})"

    def _finalize_accel_success(self):
        with self._lock:
            self.in_calibration = False
            self._current_requested_position = None
            self._ack_in_flight = False
            self._pending_accel_success = False

        self._accel_progress(100)
        self._confirm_ready(False)
        self._status("Accelerometer calibration successful", "green")
        self._accel_done(success=True)
        self._calibration_done(success=True)

    # =========================================================================
    # COMPASS CALIBRATION
    # =========================================================================

    def start_compass_calibration(self):
        """
        Send PREFLIGHT_CALIBRATION with param2=1 to start onboard compass
        calibration. Sends a reset (all zeros) first to clear any stuck state,
        then sends the actual calibration command.
        """
        if not self.master:
            self._status("Not connected", "red")
            return False

        # FIX: Send a reset command first to clear any stuck calibration state,
        # then send the actual compass cal command after a short delay.
        # NOTE: Removed the reset as it might interfere with calibration
        # self.master.mav.command_long_send(
        #     self.master.target_system,
        #     self.master.target_component,
        #     mavutil.mavlink.MAV_CMD_PREFLIGHT_CALIBRATION,
        #     0,
        #     0, 0, 0, 0, 0, 0, 0,
        # )
        # time.sleep(0.1)

        log.info("Sending compass calibration command")
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_PREFLIGHT_CALIBRATION,
            0,
            0, 1, 0, 0, 0, 0, 0,   # param2=1 → compass cal
        )

        # Also send the direct start-mag-cal command when supported. Some
        # flight controller firmwares accept this more reliably than the
        # older PREFLIGHT_CALIBRATION pattern.
        if hasattr(mavutil.mavlink, "MAV_CMD_DO_START_MAG_CAL"):
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_DO_START_MAG_CAL,
                0,
                0, 0, 0, 0, 0, 0, 0,
            )

        with self._lock:
            self.compass_calibration = True
            self._compass_progress = {}
            self._compass_results = {}

        self._progress(0)
        self._status(
            "Compass calibration started — rotate vehicle in all orientations",
            "#f0ad4e",
        )
        return True

    def cancel_compass_calibration(self):
        """
        Cancel an in-progress compass calibration by sending
        MAV_CMD_DO_CANCEL_MAG_CAL. Safe to call even if not calibrating.
        """
        if not self.master:
            return
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_DO_CANCEL_MAG_CAL,
            0,
            255,   # bitmask 255 = cancel all compasses
            0, 0, 0, 0, 0, 0,
        )
        with self._lock:
            self.compass_calibration = False
        self._status("Compass calibration cancelled", "#cccccc")

    # =========================================================================
    # RC CALIBRATION
    # =========================================================================

    def start_rc_calibration(self):
        """
        Enter RC calibration mode. The backend begins tracking min/max
        values from RC_CHANNELS messages. No MAVLink command is needed to
        start ArduPilot's RC cal — it is purely ground-side data capture.
        Call save_rc_calibration() when the user has swept all sticks.
        """
        if not self.master:
            self._status("Not connected", "red")
            return False

        with self._lock:
            self.rc_calibration = True
            self._rc_values = {}
            self._rc_min = {}
            self._rc_max = {}
            self._rc_trim = {}
            self._rc_completed_channels = set()

        log.info("Starting RC calibration")
        self._rc_progress(0)
        self._status(
            "RC calibration started — move all sticks and switches to extremes",
            "#f0ad4e",
        )
        return True

    def capture_rc_trims(self):
        """
        Snapshot current RC values as the trim / neutral position.
        Call this when the user has centred all sticks.
        """
        with self._lock:
            if not self.rc_calibration:
                return
            self._rc_trim = dict(self._rc_values)
        self._status("Trims captured — continue sweeping sticks to extremes", "#f0ad4e")

    def save_rc_calibration(self):
        """
        Write the captured min / trim / max values to ArduPilot parameters
        and end RC calibration mode.
        """
        if not self.master:
            self._status("Not connected", "red")
            return False

        with self._lock:
            if not self.rc_calibration:
                self._status("RC calibration not running", "red")
                return False
            min_vals = dict(self._rc_min)
            max_vals = dict(self._rc_max)
            trim_vals = dict(self._rc_trim)
            self.rc_calibration = False

        log.info(f"Saving RC calibration: min={min_vals}, max={max_vals}, trim={trim_vals}")

        for ch in range(1, self.RC_CHANNEL_COUNT + 1):
            rc_min = min_vals.get(ch, 1000)
            rc_max = max_vals.get(ch, 2000)
            rc_trim = trim_vals.get(ch, 1500)

            # Clamp to sane PWM range.
            rc_min = max(800, min(rc_min, 1500))
            rc_max = min(2200, max(rc_max, 1500))
            rc_trim = max(rc_min, min(rc_trim, rc_max))

            log.info(f"Setting RC{ch}: min={rc_min}, max={rc_max}, trim={rc_trim}")
            self._set_param(f"RC{ch}_MIN", rc_min)
            self._set_param(f"RC{ch}_MAX", rc_max)
            self._set_param(f"RC{ch}_TRIM", rc_trim)

        self._status("RC calibration saved", "green")
        if self.cb_rc_done:
            self.cb_rc_done(min_vals, max_vals, trim_vals)
        return True

    def cancel_rc_calibration(self):
        """Discard captured data and exit RC calibration mode."""
        with self._lock:
            self.rc_calibration = False
            self._rc_min = {}
            self._rc_max = {}
            self._rc_trim = {}
        self._status("RC calibration cancelled", "#cccccc")

    def _set_param(self, param_id, value):
        """Send a PARAM_SET message to write a single float parameter."""
        try:
            self.master.mav.param_set_send(
                self.master.target_system,
                self.master.target_component,
                param_id.encode("utf-8"),
                float(value),
                mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
            )
            log.info(f"Set parameter {param_id} = {value}")
        except Exception as e:
            log.warning("Failed to set %s: %s", param_id, e)

    # =========================================================================
    # MAVLINK READER LOOP
    # =========================================================================

    def _reader_loop(self):
        while self.running:
            try:
                msg = self.master.recv_match(blocking=True, timeout=1)
                if not msg:
                    continue

                msg_type = msg.get_type()

                # ── HEARTBEAT ────────────────────────────────────────────
                if msg_type == "HEARTBEAT":
                    with self._lock:
                        self.last_heartbeat = time.time()
                    mode = mavutil.mode_string_v10(msg)
                    self._telemetry(mode=mode)

                # ── SYS_STATUS ───────────────────────────────────────────
                elif msg_type == "SYS_STATUS":
                    battery = getattr(msg, "battery_remaining", -1)
                    self._telemetry(battery=battery)

                # ── RAW_IMU ──────────────────────────────────────────────
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
                        self._finalize_accel_success()

                # ── RC_CHANNELS ──────────────────────────────────────────
                elif msg_type in ("RC_CHANNELS", "RC_CHANNELS_RAW"):
                    self._handle_rc_channels(msg, msg_type)

                # ── STATUSTEXT ───────────────────────────────────────────
                elif msg_type == "STATUSTEXT":
                    raw = msg.text
                    if isinstance(raw, bytes):
                        text = raw.decode("utf-8", errors="ignore").rstrip("\x00")
                    else:
                        text = str(raw).rstrip("\x00")

                    self._text(text)
                    lowered = text.lower()

                    if "successful" in lowered:
                        with self._lock:
                            accel_success_ready = self.in_calibration and self.current_step >= 6
                            already_level = self.is_level

                        if accel_success_ready and not already_level:
                            with self._lock:
                                self._pending_accel_success = True
                            self._status(
                                "Calibration data saved. Place drone level to finish.",
                                "#f0ad4e",
                            )
                            self._text("Please return vehicle to the original level position")
                        else:
                            self._finalize_accel_success()

                    elif "failed" in lowered:
                        with self._lock:
                            accel_active = self.in_calibration
                            compass_active = self.compass_calibration
                            self.in_calibration = False
                            self._current_requested_position = None
                            self._ack_in_flight = False
                            self._pending_accel_success = False
                            if compass_active:
                                self.compass_calibration = False
                        self._confirm_ready(False)
                        self._status("Calibration failed", "red")
                        if accel_active:
                            self._accel_done(success=False)
                        self._calibration_done(success=False)

                # ── COMMAND_LONG (accel cal position requests) ────────────
                elif msg_type == "COMMAND_LONG":
                    if msg.command == mavutil.mavlink.MAV_CMD_ACCELCAL_VEHICLE_POS:
                        position = int(msg.param1)

                        if position in self.ACCEL_TERMINAL_POSITIONS:
                            log.info("Accel cal terminal signal received: %d", position)
                            continue

                        position_text = self._accel_position_text(position)

                        with self._lock:
                            ack_in_flight = self._ack_in_flight
                            already_displayed = self._last_displayed_position == position
                            self._current_requested_position = position

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
                elif msg_type == "MAG_CAL_PROGRESS":
                    compass_id = getattr(msg, "compass_id", 0)
                    pct = getattr(msg, "completion_pct", 0)
                    log.info(f"Compass {compass_id} progress: {pct}%")

                    with self._lock:
                        self._compass_progress[compass_id] = pct
                        self._compass_state_update(compass_id, "rotating")
                        all_pcts = list(self._compass_progress.values())

                    avg_pct = int(sum(all_pcts) / len(all_pcts)) if all_pcts else 0
                    self._progress(avg_pct)
                    if self.cb_compass_progress:
                        self.cb_compass_progress(compass_id, pct)

                # ── MAG_CAL_REPORT ───────────────────────────────────────
                # FIX: Only set compass_calibration = False once ALL expected
                # magnetometers have reported, not just the first one.
                elif msg_type == "MAG_CAL_REPORT":
                    compass_id = getattr(msg, "compass_id", 0)
                    success = (msg.cal_status == mavutil.mavlink.MAG_CAL_SUCCESS)
                    log.info(f"Compass {compass_id} calibration result: {'SUCCESS' if success else 'FAILED'}")

                    with self._lock:
                        self._compass_results[compass_id] = success
                        results = dict(self._compass_results)
                        # Only finish when all mags that reported progress
                        # have also reported a result.
                        expected = max(len(self._compass_progress), 1)
                        all_done = len(results) >= expected
                        if all_done:
                            self.compass_calibration = False

                    if all_done:
                        overall = all(results.values())
                        if success:
                            self._compass_state_update(compass_id, "done")
                        else:
                            self._compass_state_update(compass_id, "failed")
                        if overall:
                            self._progress(100)
                            self._status("Compass calibration successful", "green")
                        else:
                            failed_ids = [k for k, v in results.items() if not v]
                            self._status(
                                f"Compass calibration failed (mag IDs: {failed_ids})", "red"
                            )

                        if self.cb_compass_done:
                            self.cb_compass_done(results)

                # ── COMMAND_ACK ──────────────────────────────────────────
                elif msg_type == "COMMAND_ACK":
                    self._ack(msg.result)

            except SerialException as e:
                log.error("Serial port lost: %s", e)
                self.running = False
                with self._lock:
                    self.in_calibration = False
                    self.compass_calibration = False
                    self.rc_calibration = False
                    self._current_requested_position = None
                    self._ack_in_flight = False
                    self._pending_accel_success = False
                self._confirm_ready(False)
                self._status("Disconnected — cable unplugged or device reset", "red")
                self._calibration_done(success=False)
                self._connection_lost()
                break

            except Exception as e:
                log.exception("Reader loop error")
                self._status(f"Error: {e}", "red")

    def _handle_rc_channels(self, msg, msg_type):
        """
        Parse RC_CHANNELS or RC_CHANNELS_RAW into a channel→PWM dict,
        update rolling min/max during calibration, and fire cb_rc_update.
        """
        values = {}

        if msg_type == "RC_CHANNELS":
            for ch in range(1, 19):
                val = getattr(msg, f"chan{ch}_raw", 0)
                if val and val != 65535:   # 65535 = not available
                    values[ch] = val
        else:  # RC_CHANNELS_RAW — only channels 1-8
            for ch in range(1, 13):
                val = getattr(msg, f"chan{ch}_raw", 0)
                if val and val != 65535:
                    values[ch] = val

        if values:
            log.debug(f"RC values: {values}")

        with self._lock:
            self._rc_values.update(values)
            in_cal = self.rc_calibration
            if in_cal:
                for ch, val in values.items():
                    if ch not in self._rc_min:
                        self._rc_min[ch] = val
                        self._rc_max[ch] = val
                    else:
                        if val < self._rc_min[ch]:
                            self._rc_min[ch] = val
                        if val > self._rc_max[ch]:
                            self._rc_max[ch] = val
                        span = self._rc_max[ch] - self._rc_min[ch]
                        
                        if span > 200:  # Consider channel calibrated if it has a reasonable range
                            self._rc_completed_channels.add(ch)
                            self._rc_channel_state_update(ch, "done")
                        else:
                            self._rc_channel_state_update(ch, "active")                
            min_snap = dict(self._rc_min)
            max_snap = dict(self._rc_max)
            
            if in_cal:
                # Partial credit: channels with any data get 10%, fully swept get 100%
                parial = 0
                for ch in range(1, self.RC_CHANNEL_COUNT + 1):
                    if ch in self._rc_completed_channels:
                        parial += 100
                    elif ch in self._rc_values:
                        parial += 10 #recieving values but not fully swept yet
                progress = int(parial / self.RC_CHANNEL_COUNT)
                self._rc_progress(progress)


        if self.cb_rc_update:
            for ch, val in values.items():
                lo = min_snap.get(ch, val)
                hi = max_snap.get(ch, val)
                self.cb_rc_update(ch, val, lo, hi)

    # =========================================================================
    # HEARTBEAT WATCHDOG
    # =========================================================================

    def _heartbeat_watchdog(self):
        while self.running:
            time.sleep(1)
            with self._lock:
                last = self.last_heartbeat
            if last is not None and (time.time() - last) > self.HEARTBEAT_TIMEOUT:
                log.warning("Heartbeat timed out after %s seconds", self.HEARTBEAT_TIMEOUT)
                self.running = False
                try:
                    if self.master:
                        self.master.close()
                except Exception:
                    pass
                self.master = None
                with self._lock:
                    self.in_calibration = False
                    self.compass_calibration = False
                    self.rc_calibration = False
                    self._current_requested_position = None
                    self._ack_in_flight = False
                    self._pending_accel_success = False
                self._confirm_ready(False)
                self._status("Heartbeat timeout — disconnected", "red")
                self._calibration_done(success=False)
                self._connection_lost()
                break

    # =========================================================================
    # CALLBACK DISPATCHERS
    # =========================================================================

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

    def _accel_progress(self, value):
        if self.cb_accel_progress:
            self.cb_accel_progress(value)

    def _rc_progress(self, value):
        if self.cb_rc_progress:
            self.cb_rc_progress(value)

    def _confirm_ready(self, enabled: bool):
        if self.cb_confirm_ready:
            self.cb_confirm_ready(enabled)

    def _calibration_done(self, success: bool):
        if self.cb_calibration_done:
            self.cb_calibration_done(success)

    def _accel_done(self, success: bool):
        if self.cb_accel_done:
            self.cb_accel_done(success)

    def _connection_lost(self):
        if self.cb_connection_lost:
            self.cb_connection_lost()

    def _position_update(self, position: int, state: str):
        if self.cb_position_update:
            self.cb_position_update(position, state)
    
    def _compass_state_update(self, compass_id: int, state: str):
        if self.cb_compass_state:
            self.cb_compass_state(compass_id, state)

    def _rc_channel_state_update(self, channel: int, state: str):
        if self.cb_rc_channel_state:
            self.cb_rc_channel_state(channel, state)