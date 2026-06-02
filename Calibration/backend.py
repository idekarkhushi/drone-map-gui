import logging
import threading
import time
 
from pymavlink import mavutil
from serial import SerialException
 
from .accel   import AccelCalMixin
from .compass import CompassCalMixin
from .rc      import RCCalMixin
 
log = logging.getLogger(__name__)
 
 
class DroneBackend(AccelCalMixin, CompassCalMixin, RCCalMixin):
    # Time in seconds without HEARTBEAT before considering connection lost.
    HEARTBEAT_TIMEOUT = 5
 
    def __init__(self):
        # ── Serial / MAVLink connection ──────────────────────────────────
        self.master = None
        self.running = False
        self.last_heartbeat = None
 
        self._lock = threading.Lock()
 
        # Movement detection (used by accel mixin)
        self.is_moving = False
        self.is_level = False
 
        # ── Mixin state ──────────────────────────────────────────────────
        self._init_accel_state()
        self._init_compass_state()
        self._init_rc_state()
 
        # ── Core GUI callbacks ───────────────────────────────────────────
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
 
    # =========================================================================
    # CONNECTION
    # =========================================================================
 
    def connect(self, port, baud):
        try:
            self.master = mavutil.mavlink_connection(port, baud=baud)
            self.master.wait_heartbeat(timeout=8)
 
            self.running = True
            self.last_heartbeat = time.time()
 
            # Legacy stream request keeps older ArduPilot versions happy.
            self.master.mav.request_data_stream_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_RC_CHANNELS,
                10,   # 10 Hz
                1,    # start
            )
 
            # Newer ArduPilot versions prefer SET_MESSAGE_INTERVAL.
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
 
                # ── RAW_IMU — delegated to accel mixin ───────────────────
                elif msg_type == "RAW_IMU":
                    ax = msg.xacc / 1000.0
                    ay = msg.yacc / 1000.0
                    az = msg.zacc / 1000.0
                    self._handle_accel_raw_imu(ax, ay, az)
 
                # ── RC_CHANNELS — delegated to rc mixin ──────────────────
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
                    # Let the accel mixin check the text first.
                    self._handle_accel_statustext(text)
 
                # ── COMMAND_LONG — accel position requests ────────────────
                elif msg_type == "COMMAND_LONG":
                    if msg.command == mavutil.mavlink.MAV_CMD_ACCELCAL_VEHICLE_POS:
                        self._handle_accel_command_long(msg)
 
                # ── MAG_CAL_PROGRESS — delegated to compass mixin ─────────
                elif msg_type == "MAG_CAL_PROGRESS":
                    self._handle_mag_cal_progress(msg)
 
                # ── MAG_CAL_REPORT — delegated to compass mixin ───────────
                elif msg_type == "MAG_CAL_REPORT":
                    self._handle_mag_cal_report(msg)
 
                # ── COMMAND_ACK ──────────────────────────────────────────
                elif msg_type == "COMMAND_ACK":
                    self._ack(msg.result)
 
            except SerialException as e:
                log.error("Serial port lost: %s", e)
                self.running = False
                self._reset_accel_state_on_disconnect()
                self._reset_compass_state_on_disconnect()
                self._reset_rc_state_on_disconnect()
                self._status("Disconnected — cable unplugged or device reset", "red")
                self._calibration_done(success=False)
                self._connection_lost()
                break
 
            except Exception as e:
                log.exception("Reader loop error")
                self._status(f"Error: {e}", "red")
 
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
                self._reset_accel_state_on_disconnect()
                self._reset_compass_state_on_disconnect()
                self._reset_rc_state_on_disconnect()
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
