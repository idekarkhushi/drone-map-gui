"""
compass.py — Compass calibration logic for DroneBackend.

Mixin class: CompassCalMixin
Expects the host class to provide:
    - self.master      (MAVLink connection)
    - self._lock       (threading.Lock)
    - Callback dispatchers: _status, _progress, _calibration_done
    - Optional compass callbacks wired by the GUI:
        cb_compass_progress, cb_compass_done, cb_compass_state
"""

import logging
from pymavlink import mavutil

log = logging.getLogger(__name__)


class CompassCalMixin:

    # ------------------------------------------------------------------
    # State initialisation  (call from DroneBackend.__init__)
    # ------------------------------------------------------------------

    def _init_compass_state(self):
        self.compass_calibration = False
        self._compass_progress = {}
        self._compass_results = {}

        # GUI callbacks — set these from outside before calibrating.
        self.cb_compass_progress = None
        self.cb_compass_done = None
        self.cb_compass_state = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_compass_calibration(self):
        """
        Send PREFLIGHT_CALIBRATION with param2=1 to start onboard compass
        calibration. Also sends MAV_CMD_DO_START_MAG_CAL where supported.
        """
        if not self.master:
            self._status("Not connected", "red")
            return False

        log.info("Sending compass calibration command")
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_PREFLIGHT_CALIBRATION,
            0,
            0, 1, 0, 0, 0, 0, 0,   # param2=1 → compass cal
        )

        # Some firmware versions accept this command more reliably.
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
        MAV_CMD_DO_CANCEL_MAG_CAL (bitmask 255 = all compasses).
        Safe to call even if not currently calibrating.
        """
        if not self.master:
            return
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_DO_CANCEL_MAG_CAL,
            0,
            255,
            0, 0, 0, 0, 0, 0,
        )
        with self._lock:
            self.compass_calibration = False
        self._status("Compass calibration cancelled", "#cccccc")

    # ------------------------------------------------------------------
    # MAVLink message handlers  (called from DroneBackend._reader_loop)
    # ------------------------------------------------------------------

    def _handle_mag_cal_progress(self, msg):
        """Process MAG_CAL_PROGRESS messages."""
        compass_id = getattr(msg, "compass_id", 0)
        pct = getattr(msg, "completion_pct", 0)
        log.info("Compass %d progress: %d%%", compass_id, pct)

        with self._lock:
            self._compass_progress[compass_id] = pct
            self._compass_state_update(compass_id, "rotating")
            all_pcts = list(self._compass_progress.values())

        avg_pct = int(sum(all_pcts) / len(all_pcts)) if all_pcts else 0
        self._progress(avg_pct)

        if self.cb_compass_progress:
            self.cb_compass_progress(compass_id, pct)

    def _handle_mag_cal_report(self, msg):
        """
        Process MAG_CAL_REPORT messages.
        Only marks calibration complete once ALL magnetometers that
        reported progress have also returned a result.
        """
        compass_id = getattr(msg, "compass_id", 0)
        success = (msg.cal_status == mavutil.mavlink.MAG_CAL_SUCCESS)
        log.info(
            "Compass %d calibration result: %s",
            compass_id,
            "SUCCESS" if success else "FAILED",
        )

        with self._lock:
            self._compass_results[compass_id] = success
            results = dict(self._compass_results)
            expected = max(len(self._compass_progress), 1)
            all_done = len(results) >= expected
            if all_done:
                self.compass_calibration = False

        if not all_done:
            return

        overall = all(results.values())
        state = "done" if success else "failed"
        self._compass_state_update(compass_id, state)

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

    def _reset_compass_state_on_disconnect(self):
        """Call this from the connection-lost / serial-error paths."""
        with self._lock:
            self.compass_calibration = False

    # ------------------------------------------------------------------
    # Internal callback dispatcher
    # ------------------------------------------------------------------

    def _compass_state_update(self, compass_id: int, state: str):
        if self.cb_compass_state:
            self.cb_compass_state(compass_id, state)