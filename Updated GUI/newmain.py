import os
import sys
import threading
import time
import customtkinter as ctk
from PIL import Image
import tkinter.messagebox as messagebox

# Ensure local GUI modules can be imported when running this file directly
base_dir = os.path.dirname(os.path.abspath(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

try:
    from serial.tools import list_ports
    import serial
except Exception:
    list_ports = None
    serial = None

try:
    from pymavlink import mavutil
except Exception:
    mavutil = None

from DataPage import DataPage
from PlanPage import PlanPage
from ConfigPage import ConfigPage 

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
     

        self.title("Mission Planner")
        self.geometry("1200x700")
        self.minsize(900, 580)
        
        #DATA
        self.waypoints = []
        self.map_markers = []
        self.table_rows = []
    


        # ===== TOP TOOLBAR =====
        self.toolbar = ctk.CTkFrame(self, height=34)
        self.toolbar.pack(fill="x")
        self.toolbar.pack_propagate(False)

        self.left_toolbar = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        self.left_toolbar.pack(side="left", padx=(4, 0), pady=2)

        self.right_toolbar = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        self.right_toolbar.pack(side="right", padx=8, pady=2)

        self.icons = {
            "data": ctk.CTkImage(Image.open(r"Updated GUI\data.png"), size=(18, 18)),
            "plan": ctk.CTkImage(Image.open(r"Updated GUI\plan.png"), size=(18, 18)),
            "config": ctk.CTkImage(Image.open(r"Updated GUI\config.png"), size=(18, 18)),
        }

        self.add_toolbar_button("DATA", self.icons["data"], lambda: self.show("data"))
        self.add_toolbar_button("PLAN", self.icons["plan"], lambda: self.show("plan"))
        self.add_toolbar_button("CONFIG", self.icons["config"], lambda: self.show("config"))

        # serial / MAVLink connection state
        self.serial_conn = None
        self._port_display_map = {}
        self._port_desc_map = {}
        self.heartbeat_timeout = 5
        self.last_heartbeat = None
        self._heartbeat_thread = None
        self._mavlink_thread = None

        # populate COM port list dynamically if pyserial is available
        port_values = ["No ports"]
        if list_ports is not None:
            try:
                ports = list_ports.comports()
                port_values = []
                for port in ports:
                    desc = port.description or "Unknown device"
                    display = f"{port.device} - {desc}"
                    port_values.append(display)
                    self._port_display_map[display] = port.device
                    self._port_desc_map[display] = desc
                if not port_values:
                    port_values = ["No ports"]
            except Exception:
                port_values = ["No ports"]

        connection_bar = ctk.CTkFrame(self.right_toolbar, fg_color="transparent")
        connection_bar.pack(side="top", fill="x")

        self.port_label = ctk.CTkLabel(connection_bar, text="COM Port:")
        self.port_label.pack(side="left", padx=(0, 4))

        self.com_port_combo = ctk.CTkComboBox(
            connection_bar,
            values=port_values,
            width=260,
            height=28,
            command=self._on_port_selected
        )
        self.com_port_combo.pack(side="left", padx=(0, 6))
        # select first available port if any
        if port_values and port_values[0] != "No ports":
            self.com_port_combo.set(port_values[0])
        else:
            self.com_port_combo.set("No ports")

        self.baud_label = ctk.CTkLabel(connection_bar, text="Baud:")
        self.baud_label.pack(side="left", padx=(0, 4))

        self.baud_combo = ctk.CTkComboBox(
            connection_bar,
            values=["9600", "19200", "38400", "57600", "115200"],
            width=100,
            height=28
        )
        self.baud_combo.pack(side="left", padx=(0, 6))
        self.baud_combo.set("57600")

        self.connect_button = ctk.CTkButton(
            connection_bar,
            text="CONNECT",
            width=90,
            height=28,
            command=self.toggle_connection
        )
        self.connect_button.pack(side="left")

        self.refresh_button = ctk.CTkButton(
            connection_bar,
            text="REFRESH",
            width=90,
            height=28,
            command=self.refresh_com_ports
        )
        self.refresh_button.pack(side="left", padx=(6, 0))

        self.port_desc_label = ctk.CTkLabel(
            self.right_toolbar,
            text="No port selected",
            font=("Arial", 10),
            text_color="gray"
        )
        self.port_desc_label.pack(side="top", fill="x", padx=(0, 4), pady=(2, 0))
        self._update_port_desc(self.com_port_combo.get())

        # ===== MAIN AREA =====
        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True)

        self.frames = {
            "data": DataPage(self.container),
            "plan": PlanPage(self.container),
            "config": ConfigPage(self.container)
        }

        for frame in self.frames.values():
            frame.place(relwidth=1, relheight=1)

        self.show("data")

    def add_toolbar_button(self, text, icon, command):
        btn = ctk.CTkButton(
            self.left_toolbar,
            text=text,
            image=icon,
            compound="top",
            width=58,
            height=30,
            corner_radius=6,
            font=("Arial", 10),
            command=command
        )
        btn.pack(side="left", padx=5, pady=0)

    def connect_serial(self):
        # Open serial connection to selected COM port
        if serial is None:
            messagebox.showerror("Serial Error", "pyserial is not installed or failed to import.")
            return

        self.refresh_com_ports(preserve_selection=True)

        port = self.com_port_combo.get()
        if not port or port == "No ports":
            messagebox.showwarning("No Port", "No COM port selected or available.")
            return

        if self._is_connected():
            # already connected -> disconnect
            self.disconnect_serial()
            return

        baud_value = self.baud_combo.get() if hasattr(self, 'baud_combo') else "57600"
        try:
            baud_int = int(baud_value)
        except Exception:
            baud_int = 57600

        selected_display = self.com_port_combo.get()
        port = self._port_display_map.get(selected_display, selected_display)

        try:
            if mavutil is not None:
                self.serial_conn = mavutil.mavlink_connection(port, baud=baud_int)
                self.serial_conn.wait_heartbeat(timeout=self.heartbeat_timeout)
                self.last_heartbeat = time.time()
                self._start_heartbeat_monitor()
            else:
                self.serial_conn = serial.Serial(port, baudrate=baud_int, timeout=1)

            self.connect_button.configure(text="DISCONNECT")
            desc = self._port_desc_map.get(self.com_port_combo.get(), "Connected")
            self.port_desc_label.configure(
                text=f"🔌 Connected to {desc} ({port})",
                text_color="#4fc3f7"
            )
        except Exception as e:
            messagebox.showerror("Connection Failed", f"Failed to open {port} at {baud_int}: {e}")
            self.serial_conn = None
            self.last_heartbeat = None

    def refresh_com_ports(self, preserve_selection=True):
        if list_ports is None:
            return

        try:
            ports = list_ports.comports()
        except Exception:
            ports = []

        port_values = []
        new_display_map = {}
        new_desc_map = {}
        for port in ports:
            desc = port.description or "Unknown device"
            display = f"{port.device} - {desc}"
            port_values.append(display)
            new_display_map[display] = port.device
            new_desc_map[display] = desc

        if not port_values:
            port_values = ["No ports"]

        selected = self.com_port_combo.get()
        self._port_display_map = new_display_map
        self._port_desc_map = new_desc_map
        self.com_port_combo.configure(values=port_values)

        if preserve_selection and selected in port_values:
            self.com_port_combo.set(selected)
        elif port_values and port_values[0] != "No ports":
            self.com_port_combo.set(port_values[0])
        else:
            self.com_port_combo.set("No ports")

        self._update_port_desc(self.com_port_combo.get())

    def _on_port_selected(self, selected_display):
        self._update_port_desc(selected_display)

    def _update_port_desc(self, selected_display):
        if not selected_display:
            self.port_desc_label.configure(text="No port selected", text_color="gray")
            return

        desc = self._port_desc_map.get(selected_display, "")
        device = self._port_display_map.get(selected_display, selected_display)

        if desc and desc != "Unknown device":
            self.port_desc_label.configure(
                text=f"🔌  {desc}  ·  {device}",
                text_color="#4fc3f7",
            )
        elif device:
            self.port_desc_label.configure(
                text=f"🔌  {device}  — no description available",
                text_color="gray",
            )
        else:
            self.port_desc_label.configure(text="No port selected", text_color="gray")

    def _is_connected(self):
        if not self.serial_conn:
            return False
        is_open = getattr(self.serial_conn, 'is_open', None)
        if is_open is not None:
            return is_open
        return True

    def _start_heartbeat_monitor(self):
        if mavutil is None or self.serial_conn is None:
            return

        if self._mavlink_thread is None or not self._mavlink_thread.is_alive():
            self._mavlink_thread = threading.Thread(target=self._mavlink_receive_loop, daemon=True)
            self._mavlink_thread.start()

        if self._heartbeat_thread is None or not self._heartbeat_thread.is_alive():
            self._heartbeat_thread = threading.Thread(target=self._heartbeat_watchdog, daemon=True)
            self._heartbeat_thread.start()

    def _mavlink_receive_loop(self):
        while self._is_connected():
            try:
                msg = self.serial_conn.recv_match(blocking=True, timeout=1)
                if msg and msg.get_type() == "HEARTBEAT":
                    self.last_heartbeat = time.time()
            except Exception:
                time.sleep(0.1)

    def _heartbeat_watchdog(self):
        while self._is_connected():
            if self.last_heartbeat is not None and (time.time() - self.last_heartbeat) > self.heartbeat_timeout:
                self.after(0, lambda: messagebox.showwarning(
                    "Heartbeat Timeout",
                    "No heartbeat received within timeout period. Disconnecting."
                ))
                self.after(0, self.disconnect_serial)
                break
            time.sleep(1)

    def disconnect_serial(self):
        if self.serial_conn:
            try:
                self.serial_conn.close()
            except Exception:
                pass
        self.serial_conn = None
        self.last_heartbeat = None
        self._heartbeat_thread = None
        self._mavlink_thread = None
        self.connect_button.configure(text="CONNECT")
        self._update_port_desc(self.com_port_combo.get())

    def toggle_connection(self):
        if self._is_connected():
            self.disconnect_serial()
            return
        self.connect_serial()

    def show(self, name):
        self.frames[name].tkraise()

# RUN
if __name__ == "__main__":
    app = App()
    app.mainloop()
