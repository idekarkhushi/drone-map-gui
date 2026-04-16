import customtkinter as ctk


class GeoFenceWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)

        self.title("GeoFence Settings")
        self.geometry("300x400")

        self.grab_set()

        # ===== TITLE =====
        ctk.CTkLabel(self, text="GeoFence", font=("Arial", 14, "bold")).pack(pady=10)

        ctk.CTkLabel(
            self,
            text="Set a virtual fence around the area",
            wraplength=250
        ).pack(pady=5)

        # ===== BUTTONS =====
        ctk.CTkLabel(self, text="Insert GeoFence").pack(pady=5)

        ctk.CTkButton(
            self,
            text="Polygon Fence",
            command=self.start_polygon
        ).pack(pady=5)

        ctk.CTkButton(
            self,
            text="Circular Fence",
            command=self.start_circle
        ).pack(pady=5)

    # ===== VERY IMPORTANT: THESE MUST BE INSIDE CLASS =====
    def start_polygon(self):
        self.master.geofence_mode = "polygon"
        self.master.geofence_points = []
        self.destroy()

    def start_circle(self):
        self.master.geofence_mode = "circle"
        self.master.geofence_points = []
        self.destroy()