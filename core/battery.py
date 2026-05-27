from pymavlink import mavutil
import threading
import time


class BatteryHandler:
    def __init__(self):
        self.master = None
        self.running = False
        self.connection_string = None
        self._owns_connection = False
        self._poll_cached_messages = False
        self._thread = None

        self.voltage = None
        self.battery_remaining = None

    def connect(self, connection_string='udp:127.0.0.1:14552', baudrate=57600, timeout=3):
        try:
            self.connection_string = connection_string
            self.master = mavutil.mavlink_connection(connection_string, baud=baudrate)
            self.master.wait_heartbeat(timeout=timeout)
            self._owns_connection = True
            self._poll_cached_messages = False
            self.request_battery_stream()
            print(f"Battery: Connected to {connection_string}")
            return True
        except Exception as e:
            print("Battery connection failed:", e)
            self.master = None
            return False

    def attach_connection(self, master):
        """
        Use an existing pymavlink connection, such as the one opened by
        ConnectPanel for Serial, Bluetooth, or WiFi.

        ConnectPanel already reads packets to monitor heartbeat, so this handler
        polls pymavlink's latest-message cache instead of reading from the port.
        """
        self.stop()
        self.master = master
        self.connection_string = getattr(master, "address", None)
        self._owns_connection = False
        self._poll_cached_messages = True
        self.voltage = None
        self.battery_remaining = None
        self.request_battery_stream()
        return self.master is not None

    def request_battery_stream(self):
        if self.master is None:
            return

        try:
            # Ask the autopilot to start sending extended status, including SYS_STATUS.
            self.master.mav.request_data_stream_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_EXTENDED_STATUS,
                2,
                1
            )
        except Exception as e:
            print("Battery stream request failed:", e)

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self.read_data, daemon=True)
        self._thread.start()

    def read_data(self):
        while self.running:
            try:
                if self.master is None:
                    time.sleep(1)
                    continue

                if self._poll_cached_messages:
                    msg = getattr(self.master, "messages", {}).get("SYS_STATUS")
                    time.sleep(0.5)
                else:
                    msg = self.master.recv_match(
                        type='SYS_STATUS',
                        blocking=True,
                        timeout=1
                    )

                if msg:
                    self.voltage = msg.voltage_battery / 1000.0
                    if msg.battery_remaining >= 0:
                        self.battery_remaining = msg.battery_remaining

            except Exception:
                time.sleep(1)

    def stop(self):
        self.running = False

    def disconnect(self):
        self.stop()
        if self._owns_connection and self.master is not None:
            try:
                self.master.close()
            except Exception:
                pass
        self.master = None
        self._owns_connection = False
        self._poll_cached_messages = False
        self.voltage = None
        self.battery_remaining = None
