"""
accel.py — Accelerometer calibration logic for DroneBackend.

Mixin class: AccelCalMixin
Expects the host class to provide:
    - self.master          (MAVLink connection)
    - self._lock           (threading.Lock)
    - self.is_moving       (bool)
    - self.is_level        (bool)
    - self.current_step    (int)
    - Callback dispatchers: _status, _text, _confirm_ready,
      _accel_progress, _accel_done, _calibration_done, _position_update
"""

import logging
from pymavlink import mavutil

log = logging.getLogger(__name__)


class AccelCalMixin:
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

    # ------------------------------------------------------------------
    # State initialisation  (call from DroneBackend.__init__)
    # ------------------------------------------------------------------

    def _init_accel_state(self):
        self.in_calibration = False
        self.current_step = 0
        self._current_requested_position = None
        self._ack_in_flight = False
        self._last_displayed_position = None
        self._pending_accel_success = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # MAVLink message handlers  (called from DroneBackend._reader_loop)
    # ------------------------------------------------------------------

    def _handle_accel_command_long(self, msg):
        """Process MAV_CMD_ACCELCAL_VEHICLE_POS messages."""
        position = int(msg.param1)

        if position in self.ACCEL_TERMINAL_POSITIONS:
            log.info("Accel cal terminal signal received: %d", position)
            return

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

    def _handle_accel_statustext(self, text):
        """
        Inspect a STATUSTEXT message for accel-cal outcomes.
        Returns True if the message was consumed by accel logic.
        """
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
            return True

        if "failed" in lowered:
            with self._lock:
                accel_active = self.in_calibration
                self.in_calibration = False
                self._current_requested_position = None
                self._ack_in_flight = False
                self._pending_accel_success = False
            self._confirm_ready(False)
            self._status("Calibration failed", "red")
            if accel_active:
                self._accel_done(success=False)
            self._calibration_done(success=False)
            return True

        return False

    def _handle_accel_raw_imu(self, ax, ay, az):
        """
        Called from the RAW_IMU handler with normalised G values.
        Checks movement / level state and finalises if pending.
        """
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

    def _reset_accel_state_on_disconnect(self):
        """Call this from the connection-lost / serial-error paths."""
        with self._lock:
            self.in_calibration = False
            self._current_requested_position = None
            self._ack_in_flight = False
            self._pending_accel_success = False
        self._confirm_ready(False)