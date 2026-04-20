import customtkinter as ctk
import tkintermapview


class DataPage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent)

        self.battery_labels = {}

        # ===== MAP =====
        self.map = tkintermapview.TkinterMapView(self)
        self.map.pack(fill="both", expand=True)

        self.map.set_position(19.0760, 72.8777)
        self.map.set_zoom(12)

        # ===== TELEMETRY GRID =====
        panel = ctk.CTkFrame(self)
        panel.place(relx=0.02, rely=0.98, anchor="sw")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_columnconfigure(1, weight=1)
        panel.grid_columnconfigure(2, weight=1)

        values = [
            ("Altitude (m)", "0.00"),
            ("GroundSpeed (m/s)", "0.00"),
            ("Dist to WP (m)", "0.00"),
            ("Yaw (deg)", "0.00"),
            ("Vertical Speed (m/s)", "0.00"),
            ("DistToMAV", "0.00"),
        ]

        for i, (label, val) in enumerate(values):
            card = ctk.CTkFrame(panel, width=180, height=90)
            card.grid(row=i // 2, column=i % 2, padx=10, pady=10)

            ctk.CTkLabel(card, text=label, font=("Arial", 13)).pack(pady=5)
            ctk.CTkLabel(card, text=val, font=("Arial", 22, "bold")).pack()

        battery = ctk.CTkFrame(panel, fg_color="#202020", corner_radius=0)
        battery.grid(row=0, column=2, rowspan=2, sticky="nsew", padx=(12, 10), pady=10)
        battery.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            battery,
            text="Battery Status",
            font=("Arial", 14, "bold"),
            text_color="#f0f0f0",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(8, 6))

        for row, key in enumerate(["Voltage", "Battery"], start=1):
            ctk.CTkLabel(
                battery, text=key, font=("Arial", 12), text_color="#bdbdbd"
            ).grid(row=row, column=0, sticky="w", padx=12, pady=2)

            value = ctk.CTkLabel(
                battery,
                text="--",
                font=("Arial", 12, "bold"),
                text_color="#f4f4f4",
            )
            value.grid(row=row, column=1, sticky="e", padx=12, pady=2)
            self.battery_labels[key] = value

    def update_battery(self, voltage, percent):
        self.battery_labels["Voltage"].configure(text=f"{voltage} V")
        self.battery_labels["Battery"].configure(text=f"{percent} %")
