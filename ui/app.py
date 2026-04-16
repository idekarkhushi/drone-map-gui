import customtkinter as ctk
import tkintermapview
from PIL import Image, ImageTk
from tkinter import filedialog

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
        self.drone_marker = None
        self.drone_images = []
        self.total_distance = 0
        self.speed = 5

        # ===== GEOFENCE DATA =====
        self.geofence_mode = None
        self.geofence_points = []
        self.geofence_shapes = []

        # ===== LOAD IMAGE =====
        self.base_drone_img = Image.open(
            r"C:\Users\ADMIN\Desktop\Drone GUI\assets\drone.png"
        ).convert("RGBA").resize((30, 30))

        # ===== LAYOUT =====
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)

        # ================= TELEMETRY BAR =================
        self.telemetry_bar = ctk.CTkFrame(self, height=70)
        self.telemetry_bar.grid(row=0, column=0, columnspan=3, sticky="ew", padx=5, pady=5)

        self.telemetry_bar.grid_columnconfigure(0, weight=1)
        self.telemetry_bar.grid_columnconfigure(1, weight=1)
        self.telemetry_bar.grid_columnconfigure(2, weight=1)

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

        # CENTER
        self.telemetry_status = ctk.CTkLabel(
            self.telemetry_bar, text="Status: Idle", font=("Arial", 12, "bold")
        )
        self.telemetry_status.grid(row=0, column=1, pady=(5, 0))

        self.telemetry_speed = ctk.CTkLabel(
            self.telemetry_bar, text="Speed: 0 m/s"
        )
        self.telemetry_speed.grid(row=1, column=1)

        self.telemetry_distance = ctk.CTkLabel(
            self.telemetry_bar, text="Distance: 0 m"
        )
        self.telemetry_distance.grid(row=2, column=1)

        # RIGHT
        self.mission_title = ctk.CTkLabel(
            self.telemetry_bar, text="Total Mission", font=("Arial", 12, "bold")
        )
        self.mission_title.grid(row=0, column=2, sticky="e", padx=15, pady=(5, 0))

        self.mission_info = ctk.CTkLabel(
            self.telemetry_bar,
            text="Distance: 0 m | Time: 00:00 | Telem dist: 0 m"
        )
        self.mission_info.grid(row=1, column=2, sticky="e", padx=15)

        # ===== LEFT PANEL =====
        self.left_panel = ctk.CTkFrame(self, width=100)
        self.left_panel.grid(row=1, column=0, sticky="ns", padx=5, pady=5)

        ctk.CTkButton(self.left_panel, text="Load File", command=self.load_file).pack(pady=10)
        ctk.CTkButton(self.left_panel, text="Clear", command=self.clear_all).pack(pady=10)

        # ===== RIGHT PANEL =====
        self.right_panel = ctk.CTkFrame(self, width=200)
        self.right_panel.grid(row=1, column=2, sticky="ns", padx=5, pady=5)

        self.speed_entry = ctk.CTkEntry(self.right_panel, placeholder_text="Speed (m/s)")
        self.speed_entry.pack(pady=10)

        self.distance_label = ctk.CTkLabel(self.right_panel, text="Distance: 0 m")
        self.distance_label.pack(pady=10)

        ctk.CTkButton(
            self.right_panel,
            text="Start Mission",
            command=self.start_simulation
        ).pack(pady=10)

        self.message_label = ctk.CTkLabel(self.right_panel, text="")
        self.message_label.pack(pady=10)

        ctk.CTkButton(
            self.right_panel,
            text="GeoFence",
            command=self.open_geofence
        ).pack(pady=10)

        # ===== MAP =====
        self.map_widget = tkintermapview.TkinterMapView(self)
        self.map_widget.grid(row=1, column=1, sticky="nsew", padx=5, pady=5)

        self.map_widget.set_position(19.0760, 72.8777)
        self.map_widget.set_zoom(12)

        self.map_widget.add_left_click_map_command(self.map_click)

        # ===== SIMULATION =====
        self.simulation = DroneSimulation(self)

    # ================= FILE LOAD =================
    def load_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )

        if not file_path:
            return

        try:
            self.points = load_csv_waypoints(file_path)

            self.map_widget.delete_all_marker()
            self.map_widget.delete_all_path()

            for i, (lat, lon) in enumerate(self.points):
                self.map_widget.set_marker(lat, lon, text=str(i + 1))

            if len(self.points) > 1:
                self.map_widget.set_path(self.points)

            self.message_label.configure(text=f"{len(self.points)} waypoints loaded")

        except Exception as e:
            self.message_label.configure(text=str(e))

    # ================= MAP CLICK =================
    def map_click(self, coords):
        handled = handle_map_click(self, coords)
        if handled:
            return

        lat, lon = coords

        self.points.append((lat, lon))
        self.map_widget.set_marker(lat, lon, text=str(len(self.points)))

        if len(self.points) > 1:
            self.map_widget.set_path(self.points)

    # ================= GEOFENCE =================
    def open_geofence(self):
        if hasattr(self, "geo_window") and self.geo_window.winfo_exists():
            self.geo_window.focus()
            return

        self.geo_window = GeoFenceWindow(self)

    # ================= SIMULATION =================
    def start_simulation(self):
        self.simulation.start()

    def get_rotated_drone(self, angle):
        rotated = self.base_drone_img.rotate(angle, expand=True)
        img = ImageTk.PhotoImage(rotated)
        self.drone_images.append(img)
        return img

    # ================= CLEAR =================
    def clear_all(self):
        self.points.clear()
        self.map_widget.delete_all_marker()
        self.map_widget.delete_all_path()

        for shape in self.geofence_shapes:
            shape.delete()

        self.geofence_shapes.clear()

        if self.drone_marker:
            self.drone_marker.delete()

        self.drone_marker = None
        self.drone_images.clear()

        self.total_distance = 0
        self.distance_label.configure(text="Distance: 0 m")
        self.message_label.configure(text="Cleared")

        # Reset telemetry
        self.telemetry_status.configure(text="Status: Idle")
        self.telemetry_speed.configure(text="Speed: 0 m/s")
        self.telemetry_distance.configure(text="Distance: 0 m")
        self.mission_info.configure(text="Distance: 0 m | Time: 00:00 | Telem dist: 0 m")
        self.wp_info.configure(
            text="Alt diff: 0 m | Azimuth: 0 | Gradient: 0% | Heading: 0 | Distance: 0 m"
        )