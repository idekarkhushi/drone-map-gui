from pymavlink import mavutil
import threading
import time


class DroneBackend:
    def __init__(self):
        self.master = None
        self.running = False
        self.last_heartbeat = None

        # Calibration state
        self.in_calibration = False
        self.current_step = 0

        # GUI callbacks
        self.cb_status = None
        self.cb_text = None
        self.cb_telemetry = None
        self.cb_ack = None

    # ================= CONNECTION =================

    def connect(self, port, baud):
        try:
            self.master = mavutil.mavlink_connection(port, baud=baud)
            self.master.wait_heartbeat(timeout=8)

            self.running = True
            self.last_heartbeat = time.time()

            self._status(f"Connected to {port}", "green")

            threading.Thread(target=self._reader_loop, daemon=True).start()

        except Exception as e:
            self._status(f"Connection failed: {e}", "red")

    def disconnect(self):
        self.running = False

        if self.master:
            try:
                self.master.close()
            except:
                pass

        self.master = None
        self._status("Disconnected", "#cccccc")

    # ================= ACCEL CALIBRATION =================

    def start_accel_calibration(self):
        """Start calibration (FIRST CLICK)"""
        if not self.master:
            self._status("Not connected", "red")
            return

        try:
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_PREFLIGHT_CALIBRATION,
                0,
                0, 0, 0, 0,
                1,  # accelerometer calibration
                0, 0
            )

            self.in_calibration = True
            self.current_step = 0

            self._status("Calibration started - follow instructions", "#f0ad4e")

        except Exception as e:
            self._status(f"Calibration error: {e}", "red")

    def next_accel_step(self, position):
        """Next step (EVERY CLICK AFTER FIRST)"""
        if not self.master or not self.in_calibration:
            self._status("Not in calibration mode", "red")
            return

        try:
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_ACCELCAL_VEHICLE_POS,
                0,
                float(position),  # step position
                0, 0, 0, 0, 0, 0
            )

            self.current_step = position
            self._status(f"Step {position} sent", "#f0ad4e")

        except Exception as e:
            self._status(f"Calibration error: {e}", "red")

    # ================= MAVLINK LOOP =================

    def _reader_loop(self):
        while self.running:
            try:
                msg = self.master.recv_match(blocking=True, timeout=1)
                if not msg:
                    continue

                msg_type = msg.get_type()

                # ================= HEARTBEAT =================
                if msg_type == "HEARTBEAT":
                    self.last_heartbeat = time.time()
                    mode = mavutil.mode_string_v10(msg)
                    self._telemetry(mode=mode)

                # ================= BATTERY =================
                elif msg_type == "SYS_STATUS":
                    battery = getattr(msg, "battery_remaining", -1)
                    self._telemetry(battery=battery)

                # ================= STATUSTEXT =================
                elif msg_type == "STATUSTEXT":
                    text = msg.text
                    self._text(text)

                    if not self.in_calibration:
                        continue

                    t = text.lower()

                    # ONLY completion / failure (manual control logic)
                    if "calibration successful" in t or "calibration complete" in t:
                        self.in_calibration = False
                        self._status("Calibration Completed ✅", "green")

                    elif "failed" in t or "error" in t:
                        self.in_calibration = False
                        self._status(f"Calibration Failed: {text}", "red")

                # ================= ACK =================
                elif msg_type == "COMMAND_ACK":
                    self._ack(msg.result)

            except Exception as e:
                self._status(f"Error: {e}", "red")
                break

    # ================= CALLBACK HELPERS =================

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