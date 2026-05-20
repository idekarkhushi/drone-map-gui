"""
rc.py — RC channel calibration logic for DroneBackend.

Mixin class: RCCalMixin
Expects the host class to provide:
    - self.master              (MAVLink connection)
    - self._lock               (threading.Lock)
    - RC_CHANNEL_COUNT         (class-level int, e.g. 12)
    - Callback dispatchers: _status, _rc_progress
    - Optional RC callbacks wired by the GUI:
        cb_rc_update, cb_rc_done, cb_rc_channel_state, cb_rc_progress
"""

import logging
from pymavlink import mavutil

log = logging.getLogger(__name__)


class RCCalMixin:
    # How many RC channels to track (ArduPilot reports up to 18).
    RC_CHANNEL_COUNT = 12

    # ------------------------------------------------------------------
    # State initialisation  (call from DroneBackend.__init__)
    # ------------------------------------------------------------------

    def _init_rc_state(self):
        self.rc_calibration = False
        self._rc_values = {}
        self._rc_min = {}
        self._rc_max = {}
        self._rc_trim = {}
        self._rc_completed_channels = set()

        # GUI callbacks — set these from outside before calibrating.
        self.cb_rc_update = None
        self.cb_rc_done = None
        self.cb_rc_channel_state = None
        self.cb_rc_progress = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_rc_calibration(self):
        """
        Enter RC calibration mode.  The backend tracks min/max from
        RC_CHANNELS messages — no MAVLink command is needed on the FC.
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
        Write captured min / trim / max values to ArduPilot parameters
        and exit RC calibration mode.
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

        log.info(
            "Saving RC calibration: min=%s, max=%s, trim=%s",
            min_vals, max_vals, trim_vals,
        )

        for ch in range(1, self.RC_CHANNEL_COUNT + 1):
            rc_min = min_vals.get(ch, 1000)
            rc_max = max_vals.get(ch, 2000)
            rc_trim = trim_vals.get(ch, 1500)

            # Clamp to sane PWM range.
            rc_min = max(800, min(rc_min, 1500))
            rc_max = min(2200, max(rc_max, 1500))
            rc_trim = max(rc_min, min(rc_trim, rc_max))

            log.info("Setting RC%d: min=%d, max=%d, trim=%d", ch, rc_min, rc_max, rc_trim)
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

    # ------------------------------------------------------------------
    # MAVLink message handler  (called from DroneBackend._reader_loop)
    # ------------------------------------------------------------------

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
        else:  # RC_CHANNELS_RAW — channels 1-8 only
            for ch in range(1, 13):
                val = getattr(msg, f"chan{ch}_raw", 0)
                if val and val != 65535:
                    values[ch] = val

        if values:
            log.debug("RC values: %s", values)

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

                        if span > 200:  # reasonable sweep range = calibrated
                            self._rc_completed_channels.add(ch)
                            self._rc_channel_state_update(ch, "done")
                        else:
                            self._rc_channel_state_update(ch, "active")

            min_snap = dict(self._rc_min)
            max_snap = dict(self._rc_max)

            if in_cal:
                partial = 0
                for ch in range(1, self.RC_CHANNEL_COUNT + 1):
                    if ch in self._rc_completed_channels:
                        partial += 100
                    elif ch in self._rc_values:
                        partial += 10   # receiving values but not fully swept
                progress = int(partial / self.RC_CHANNEL_COUNT)
                self._rc_progress(progress)

        if self.cb_rc_update:
            for ch, val in values.items():
                lo = min_snap.get(ch, val)
                hi = max_snap.get(ch, val)
                self.cb_rc_update(ch, val, lo, hi)

    def _reset_rc_state_on_disconnect(self):
        """Call this from the connection-lost / serial-error paths."""
        with self._lock:
            self.rc_calibration = False
            self._rc_min = {}
            self._rc_max = {}
            self._rc_trim = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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
            log.info("Set parameter %s = %s", param_id, value)
        except Exception as e:
            log.warning("Failed to set %s: %s", param_id, e)

    def _rc_channel_state_update(self, channel: int, state: str):
        if self.cb_rc_channel_state:
            self.cb_rc_channel_state(channel, state)