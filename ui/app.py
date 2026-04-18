import customtkinter as ctk
import tkintermapview
import threading
from pathlib import Path
from PIL import Image, ImageTk
from tkinter import filedialog, messagebox

import serial
import serial.tools.list_ports

from core.battery import BatteryHandler
from ui.geofence_window import GeoFenceWindow
from ui.geofence_logic import handle_map_click
from utils.file_loader import load_csv_waypoints
from core.simulation import DroneSimulation


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class MapApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Drone Mission Planner")
        self.geometry("1200x700")

        # ===== DATA =====
        self.points = []
        self.serial_com = None
        self.connected_port = None
        self.connected_baudrate = 57600
        self.geofence_mode = None
        self.geofence_points = []
        self.geofence_shapes = []
        self.drone_marker = None
        self.total_distance = 0
        self.speed = 5
        self._drone_base_image = self.load_drone_image()
        self._drone_icon = None
        self._drone_icon_cache = {}

        # ===== BATTERY =====
        self.battery = BatteryHandler()

        # ===== LAYOUT =====
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ================= TELEMETRY BAR =================
        self.telemetry_bar = ctk.CTkFrame(self, height=70)
        self.telemetry_bar.grid(row=0, column=0, columnspan=3, sticky="ew", padx=5, pady=5)

        self.telemetry_bar.grid_columnconfigure((0, 1, 2, 3), weight=1)

        ctk.CTkLabel(self.telemetry_bar, text="Mission Info").grid(row=0, column=0, sticky="w", padx=10)
        
        # LEFT
        self.wp_title = ctk.CTkLabel(
            self.telemetry_bar, text="Selected Waypoint", font=("Arial", 12, "bold")
        )
        self.wp_title.grid(row=0, column=0, sticky="w", padx=15, pady=(5, 0))

        self.wp_info = ctk.CTkLabel(
            self.telemetry_bar,
            text="Alt diff: 0 m | Azimuth: 0 | Gradient: 0% | Heading: 0 | Distance: 0 m"
        )
        self.wp_info.grid(row=1, column=0, sticky="w", padx=15)

        self.telemetry_status = ctk.CTkLabel(
            self.telemetry_bar, text="Status: Idle", font=("Arial", 12, "bold")
        )
        self.telemetry_status.grid(row=2, column=0, sticky="w", padx=15)

        self.telemetry_data = ctk.CTkLabel(
            self.telemetry_bar, text="Speed: 0 m/s | Distance: 0 m", font=("Arial", 12)
        )
        self.telemetry_data.grid(row=3, column=0, sticky="w", padx=(15,5))
        

        # CENTER
        self.mission_title = ctk.CTkLabel(
            self.telemetry_bar, text="Total Mission", font=("Arial", 12, "bold")
        )
        self.mission_title.grid(row=0, column=1, sticky="w", padx=15, pady=(5, 0))

        self.mission_info = ctk.CTkLabel(
            self.telemetry_bar,
            text="Distance: 0 m | Time: 00:00 | Telem dist: 0 m"
        )
        self.mission_info.grid(row=1, column=1, sticky="w", padx=15)

        # ===== COM PORT DROPDOWN =====
        self.port_menu = ctk.CTkComboBox(self.telemetry_bar, values=self.get_com_ports(), width=250)
        self.port_menu.grid(row=0, column=2, sticky="e", padx=10)

        # ===== CONNECT BUTTON =====
        self.connect_btn = ctk.CTkButton(self.telemetry_bar, text="CONNECT", command=self.connect_drone)
        self.connect_btn.grid(row=0, column=3, sticky="e", padx=10)

        # ===== STATUS =====
        self.status_label = ctk.CTkLabel(self.telemetry_bar, text="Checking COM ports...")
        self.status_label.grid(row=1, column=2, columnspan=2, sticky="e", padx=10)

        # ===== LEFT PANEL =====
        self.left_panel = ctk.CTkFrame(self, width=100)
        self.left_panel.grid(row=1, column=0, sticky="ns", padx=5, pady=5)

        ctk.CTkButton(self.left_panel, text="Load File", command=self.load_file).pack(pady=10)
        ctk.CTkButton(self.left_panel, text="Clear", command=self.clear_all).pack(pady=10)

        # ===== RIGHT PANEL =====
        self.right_panel = ctk.CTkFrame(self, width=200)
        self.right_panel.grid(row=1, column=2, sticky="ns", padx=5, pady=5)

        # --- SPEED ---
        self.speed_entry = ctk.CTkEntry(self.right_panel, placeholder_text="Speed (m/s)")
        self.speed_entry.pack(pady=10)

        self.distance_label = ctk.CTkLabel(self.right_panel, text="Distance: 0 m")
        self.distance_label.pack(pady=10)

        # --- BUTTONS ---
        ctk.CTkButton(self.right_panel, text="Start Mission", command=self.start_simulation).pack(pady=10)
        ctk.CTkButton(self.right_panel, text="GeoFence", command=self.open_geofence).pack(pady=10)

        self.message_label = ctk.CTkLabel(self.right_panel, text="")
        self.message_label.pack(pady=5)

        # --- BATTERY ---
        ctk.CTkLabel(self.right_panel, text="Battery", font=("Arial", 14, "bold")).pack(pady=5)

        self.voltage_label = ctk.CTkLabel(self.right_panel, text="Voltage: -- V")
        self.voltage_label.pack()

        self.battery_label = ctk.CTkLabel(self.right_panel, text="Battery: -- %")
        self.battery_label.pack()

        self.battery_bar = ctk.CTkProgressBar(self.right_panel)
        self.battery_bar.set(0)
        self.battery_bar.pack(pady=10)

        # ===== MAP =====
        self.map_widget = tkintermapview.TkinterMapView(self)
        self.map_widget.grid(row=1, column=1, sticky="nsew", padx=5, pady=5)

        self.map_widget.set_position(19.0760, 72.8777)
        self.map_widget.set_zoom(12)

        self.map_widget.add_left_click_map_command(self.map_click)

        # ===== SIM =====
        self.simulation = DroneSimulation(self)

        # Start loops
        self.refresh_com_ports()
        self.update_battery_ui()

    def load_drone_image(self):
        for path in (Path("assets/drone.png"), Path("drone.png")):
            if path.exists():
                image = Image.open(path).convert("RGBA")
                image.thumbnail((60, 60))
                return image
        return None

    def get_rotated_drone(self, angle):
        if self._drone_base_image is None:
            return None

        normalized_angle = int(angle) % 360
        if normalized_angle not in self._drone_icon_cache:
            rotated = self._drone_base_image.rotate(normalized_angle, expand=True)
            self._drone_icon_cache[normalized_angle] = ImageTk.PhotoImage(rotated)

        self._drone_icon = self._drone_icon_cache[normalized_angle]
        return self._drone_icon

    # ================= COM PORT =================
    def get_com_ports(self):
        ports = [
            f"{port.device} {port.description}"
            for port in serial.tools.list_ports.comports()
        ]
        return ports if ports else ["No ports available"]

    def refresh_com_ports(self):
        ports = self.get_com_ports()
        current = self.port_menu.get()

        self.port_menu.configure(values=ports)

        if current in ports:
            self.port_menu.set(current)
        elif ports[0] != "No ports available":
            self.port_menu.set(ports[0])
        else:
            self.port_menu.set("No ports available")

        if ports[0] == "No ports available":
            self.status_label.configure(text="No COM ports detected", text_color="red")
            self.connect_btn.configure(state="disabled")
        else:
            self.connect_btn.configure(state="normal")
            if not self.connected_port:
                self.status_label.configure(text="Select port and connect", text_color="gray")

        self.after(2000, self.refresh_com_ports)

    # ================= CONNECT =================
    def connect_drone(self):
        port = self.port_menu.get()

        if "COM" not in port:
            messagebox.showerror("Error", "Invalid COM port")
            return

        selected_port = port.split()[0]

        try:
            self.battery.stop()
            self.connected_port = selected_port

            self.connect_btn.configure(state="disabled")
            self.status_label.configure(text=f"Connected to {selected_port} | Battery connecting...", text_color="orange")
            threading.Thread(target=self.connect_battery_async, daemon=True).start()

        except Exception as e:
            self.connected_port = None
            self.status_label.configure(text="Connection failed", text_color="red")
            messagebox.showerror("Error", str(e))

    def connect_battery_async(self):
        connected = self.battery.connect(
            connection_string=self.connected_port,
            baudrate=self.connected_baudrate,
            timeout=5
        )
        self.after(0, lambda: self.on_battery_connected(connected))

    def on_battery_connected(self, connected):
        self.connect_btn.configure(state="normal")

        if connected:
            self.battery.start()
            self.status_label.configure(
                text=f"Connected to {self.connected_port} | Battery connected",
                text_color="green"
            )
        else:
            self.status_label.configure(
                text=f"Connected to {self.connected_port} | Battery offline",
                text_color="orange"
            )

    # ================= BATTERY =================
    def update_battery_ui(self):
        voltage = self.battery.voltage
        battery = self.battery.battery_remaining

        if voltage is not None and voltage > 0:
            self.voltage_label.configure(text=f"Voltage: {voltage:.2f} V")
        else:
            self.voltage_label.configure(text="Voltage: -- V")

        if battery is not None and battery >= 0:
            self.battery_label.configure(text=f"Battery: {battery} %")
            self.battery_bar.set(battery / 100)

            if battery < 20:
                self.battery_bar.configure(progress_color="red")
            elif battery < 50:
                self.battery_bar.configure(progress_color="yellow")
            else:
                self.battery_bar.configure(progress_color="green")
        else:
            self.battery_label.configure(text="Battery: -- %")
            self.battery_bar.set(0)
            self.battery_bar.configure(progress_color="gray")

        self.after(1000, self.update_battery_ui)

    # ================= FILE =================
    def load_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if not file_path:
            return

        self.points = load_csv_waypoints(file_path)
        self.map_widget.delete_all_marker()
        self.map_widget.delete_all_path()

        for lat, lon in self.points:
            self.map_widget.set_marker(lat, lon)

        if len(self.points) > 1:
            self.map_widget.set_path(self.points)

    # ================= MAP =================
    def map_click(self, coords):
        if handle_map_click(self, coords):
            return

        lat, lon = coords
        self.points.append((lat, lon))
        self.map_widget.set_marker(lat, lon)

        if len(self.points) > 1:
            self.map_widget.set_path(self.points)

    # ================= GEOFENCE =================
    def open_geofence(self):
        self.geo_window = GeoFenceWindow(self)

    # ================= SIM =================
    def start_simulation(self):
        self.simulation.start()

    # ================= CLEAR =================
    def clear_all(self):
        self.points.clear()
        self.geofence_points.clear()
        self.geofence_mode = None
        self.geofence_shapes.clear()
        self.map_widget.delete_all_marker()
        self.map_widget.delete_all_path()

        if self.drone_marker:
            self.drone_marker = None

        self.distance_label.configure(text="Distance: 0 m")
        self.message_label.configure(text="Cleared")


if __name__ == "__main__":
    app = MapApp()
    app.mainloop()
