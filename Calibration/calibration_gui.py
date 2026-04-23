import customtkinter as ctk
import serial.tools.list_ports

from backend import DroneBackend

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class CalibrationWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("MAVLink Calibration Interface")
        self.geometry("980x560")

        self.backend = DroneBackend()

        # Tk widgets must be updated on the main thread, so each backend
        # callback hops back into Tkinter with self.after(...).
        self.backend.cb_status = lambda t, c: self.after(0, self.set_status, t, c)
        self.backend.cb_text = lambda t: self.after(0, self.handle_statustext, t)
        self.backend.cb_telemetry = lambda m, b: self.after(0, self.update_telemetry, m, b)
        self.backend.cb_ack = lambda r: self.after(0, self.handle_ack, r)
        self.backend.cb_progress = lambda v: self.after(0, self.update_progress, v)
        self.backend.cb_confirm_ready = lambda e: self.after(0, self.set_confirm_ready, e)
        self.backend.cb_calibration_done = lambda s: self.after(0, self.on_calibration_done, s)

        # LEFT PANEL
        self.left_panel = ctk.CTkFrame(self)
        self.left_panel.pack(side="left", fill="y", padx=8, pady=8)

        self.accel_btn = ctk.CTkButton(
            self.left_panel,
            text="Accelerometer",
            command=self.on_accel_click,
        )
        self.accel_btn.pack(fill="x", pady=5)

        self.compass_btn = ctk.CTkButton(
            self.left_panel,
            text="Compass",
            command=self.on_compass_click,
        )
        self.compass_btn.pack(fill="x", pady=5)

        # RIGHT PANEL
        self.right_panel = ctk.CTkFrame(self)
        self.right_panel.pack(side="right", fill="both", expand=True, padx=8, pady=8)

        top = ctk.CTkFrame(self.right_panel)
        top.pack(fill="x", pady=(0, 6))

        self.port_combo = ctk.CTkComboBox(top, width=120)
        self.port_combo.pack(side="left", padx=4)

        self.baud_combo = ctk.CTkComboBox(top, values=["57600", "115200"], width=100)
        self.baud_combo.set("57600")
        self.baud_combo.pack(side="left", padx=4)

        ctk.CTkButton(top, text="Refresh", width=80, command=self.refresh_ports).pack(
            side="left", padx=4
        )

        self.connect_btn = ctk.CTkButton(top, text="Connect", width=100, command=self.toggle_connection)
        self.connect_btn.pack(side="left", padx=4)

        self.textbox = ctk.CTkTextbox(self.right_panel)
        self.textbox.pack(fill="both", expand=True)

        self.status_label = ctk.CTkLabel(self.right_panel, text="Status: Ready")
        self.status_label.pack(anchor="w")

        self.telemetry_label = ctk.CTkLabel(self.right_panel, text="")
        self.telemetry_label.pack(anchor="w")

        self.progress = ctk.CTkProgressBar(self.right_panel)
        self.progress.pack(fill="x", pady=4)
        self.progress.set(0)

        self.refresh_ports()

    # ================= CONNECTION =================

    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_combo.configure(values=ports)
        if ports:
            self.port_combo.set(ports[0])

    def toggle_connection(self):
        if self.backend.master:
            self.backend.disconnect()
            self.connect_btn.configure(text="Connect")
            return

        # Only switch to "Disconnect" after a successful heartbeat.
        connected = self.backend.connect(self.port_combo.get(), int(self.baud_combo.get()))
        self.connect_btn.configure(text="Disconnect" if connected else "Connect")

    # ================= ACCEL =================

    def on_accel_click(self):
        if not self.backend.in_calibration:
            # The backend enables "Next" only after ArduPilot requests a pose.
            self.accel_btn.configure(text="Next", state="disabled")
            if not self.backend.start_accel_calibration():
                self.accel_btn.configure(text="Accelerometer", state="normal")
        else:
            self.backend.confirm_position()

    def set_confirm_ready(self, enabled: bool):
        """Enable or disable the Next button based on backend signal."""
        state = "normal" if enabled else "disabled"
        self.accel_btn.configure(state=state)

    def on_calibration_done(self, success: bool):
        """Reset the accel button back to its initial state."""
        self.accel_btn.configure(text="Accelerometer", state="normal")

    # ================= COMPASS =================

    def on_compass_click(self):
        self.backend.start_compass_calibration()

    # ================= CALLBACKS =================

    def set_status(self, text, color):
        self.status_label.configure(text=text, text_color=color)

    def handle_statustext(self, text):
        self.textbox.insert("end", f"{text}\n")
        self.textbox.see("end")

    def update_telemetry(self, mode, battery):
        parts = []
        if mode is not None:
            parts.append(f"Mode: {mode}")
        if battery is not None:
            parts.append(f"Battery: {battery}%")
        self.telemetry_label.configure(text="  |  ".join(parts))

    def handle_ack(self, result):
        pass

    def update_progress(self, value):
        self.progress.set(value / 100)


if __name__ == "__main__":
    app = CalibrationWindow()
    app.mainloop()
