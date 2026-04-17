from pymavlink import mavutil
import threading

class MAVLinkHandler:
    def __init__(self):
        self.master = None
        self.running = False
        
        self.connection_types = ["TCP", "UDP", "Serial"]

    def connect(self, conn_type, ip, port, com, baud):
        if conn_type == "TCP":
            conn_str = f"tcp:{ip}:{port}"
        elif conn_type == "UDP":
            conn_str = f"udp:{ip}:{port}"
        else:
            conn_str = com

        self.master = mavutil.mavlink_connection(conn_str, baud=baud)
        self.master.wait_heartbeat()

        self.running = True
        return True

    def start_telemetry(self, callback):
        def loop():
            while self.running:
                msg = self.master.recv_match(blocking=True)
                if msg:
                    callback(msg)

        threading.Thread(target=loop, daemon=True).start()