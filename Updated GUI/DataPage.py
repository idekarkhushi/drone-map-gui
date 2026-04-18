class DataPage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent)

        # Map
        self.map = tkintermapview.TkinterMapView(self)
        self.map.pack(fill="both", expand=True)

        self.map.set_position(19.0760, 72.8777)
        self.map.set_zoom(12)

        self.marker = self.map.set_marker(19.0760, 72.8777, text="Drone")

        # Telemetry Overlay Panel
        self.panel = ctk.CTkFrame(self, width=220)
        self.panel.place(relx=0.01, rely=0.05)

        self.labels = {}

        fields = [
            "Altitude", "GroundSpeed",
            "Yaw", "Vertical Speed"
        ]

        for f in fields:
            lbl = ctk.CTkLabel(self.panel, text=f"{f}: 0.00")
            lbl.pack(anchor="w", padx=10, pady=5)
            self.labels[f] = lbl

        self.update_data()

    def update_data(self):
        for key in self.labels:
            self.labels[key].configure(text=f"{key}: {random.uniform(0,100):.2f}")

        # Simulate drone movement
        lat, lon = self.marker.position
        lat += random.uniform(-0.001, 0.001)
        lon += random.uniform(-0.001, 0.001)
        self.marker.set_position(lat, lon)

        self.after(1000, self.update_data)
