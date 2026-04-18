from pymavlink import mavutil
import threading
import time


class BatteryHandler:
    def __init__(self):
        self.master = None
        self.running = False
        self.connection_string = None

        self.voltage = None
        self.battery_remaining = None

    def connect(self, connection_string='udp:127.0.0.1:14552', baudrate=57600, timeout=3):
        try:
            self.connection_string = connection_string
            self.master = mavutil.mavlink_connection(connection_string, baud=baudrate)
            self.master.wait_heartbeat(timeout=timeout)
            self.request_battery_stream()
            print(f"Battery: Connected to {connection_string}")
            return True
        except Exception as e:
            print("Battery connection failed:", e)
            self.master = None
            return False

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
        self.running = True
        threading.Thread(target=self.read_data, daemon=True).start()

    def read_data(self):
        while self.running:
            try:
                if self.master is None:
                    time.sleep(1)
                    continue

                msg = self.master.recv_match(type='SYS_STATUS', blocking=True)

                if msg:
                    self.voltage = msg.voltage_battery / 1000.0
                    self.battery_remaining = msg.battery_remaining

            except:
                time.sleep(1)

    def stop(self):
        self.running = False
