import customtkinter as ctk
import serial.tools.list_ports

from backend import DroneBackend

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

POSITION_LABELS = {
    1: "Level",
    2: "Left side",
    3: "Right side",
    4: "Nose down",
    5: "Nose up",
    6: "Upside down",
}


class CalibrationWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("MAVLink Calibration Interface")
        self.geometry("980x620")

        self.backend = DroneBackend()

        # The backend runs its MAVLink reader on worker threads, so every UI
        # update is marshalled back onto Tk's main thread with `after`.
        self.backend.cb_status = lambda t, c: self.after(0, self.set_status, t, c)
        self.backend.cb_text = lambda t: self.after(0, self.handle_statustext, t)
        self.backend.cb_telemetry = lambda m, b: self.after(0, self.update_telemetry, m, b)
        self.backend.cb_ack = lambda r: self.after(0, self.handle_ack, r)
        self.backend.cb_progress = lambda v: self.after(0, self.update_progress, v)
        self.backend.cb_confirm_ready = lambda e: self.after(0, self.set_confirm_ready, e)
        self.backend.cb_calibration_done = lambda s: self.after(0, self.on_calibration_done, s)
        self.backend.cb_position_update = lambda p, s: self.after(0, self.update_position_indicator, p, s)

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

        # POSITION INDICATORS — one row per position
        ctk.CTkLabel(
            self.left_panel,
            text="Accel positions",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        ).pack(anchor="w", padx=6, pady=(16, 4))

        self._position_rows = {}  # position -> {"frame": ..., "dot": ..., "label": ..., "pct": ...}

        for pos, name in POSITION_LABELS.items():
            row = ctk.CTkFrame(self.left_panel, fg_color="transparent")
            row.pack(fill="x", padx=6, pady=2)

            dot = ctk.CTkLabel(row, text="●", width=18, font=ctk.CTkFont(size=14), text_color="#555555")
            dot.pack(side="left")

            lbl = ctk.CTkLabel(row, text=f"{pos}. {name}", font=ctk.CTkFont(size=13), anchor="w")
            lbl.pack(side="left", fill="x", expand=True)

            pct = ctk.CTkLabel(row, text="", width=36, font=ctk.CTkFont(size=12), text_color="gray")
            pct.pack(side="right")

            self._position_rows[pos] = {"frame": row, "dot": dot, "label": lbl, "pct": pct}

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

        self.connect_btn = ctk.CTkButton(
            top, text="Connect", width=100, command=self.toggle_connection
        )
        self.connect_btn.pack(side="left", padx=4)

        self.textbox = ctk.CTkTextbox(self.right_panel)
        self.textbox.pack(fill="both", expand=True)

        self.status_label = ctk.CTkLabel(self.right_panel, text="Status: Ready")
        self.status_label.pack(anchor="w")

        self.telemetry_label = ctk.CTkLabel(self.right_panel, text="")
        self.telemetry_label.pack(anchor="w")

        # Progress bar with percentage label
        progress_row = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        progress_row.pack(fill="x", pady=4)

        self.progress = ctk.CTkProgressBar(progress_row)
        self.progress.pack(side="left", fill="x", expand=True)
        self.progress.set(0)

        self.progress_label = ctk.CTkLabel(
            progress_row, text="0%", width=40, font=ctk.CTkFont(size=13)
        )
        self.progress_label.pack(side="left", padx=(6, 0))

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

        connected = self.backend.connect(
            self.port_combo.get(), int(self.baud_combo.get())
        )
        self.connect_btn.configure(text="Disconnect" if connected else "Connect")

    # ================= ACCEL =================

    def on_accel_click(self):
        if not self.backend.in_calibration:
            # The backend enables this button again once the autopilot actually
            # asks for the first placement.
            self.accel_btn.configure(text="Next", state="disabled")
            if not self.backend.start_accel_calibration():
                self.accel_btn.configure(text="Accelerometer", state="normal")
        else:
            self.backend.confirm_position()

    def set_confirm_ready(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.accel_btn.configure(state=state)

    def on_calibration_done(self, success: bool):
        self.accel_btn.configure(text="Accelerometer", state="normal")

    def update_position_indicator(self, position: int, state: str):
        """
        state values:
          "reset"  — calibration just started, clear all indicators
          "active" — drone is being asked to move to this position
          "done"   — ack sent for this position, mark it complete
        """
        if state == "reset":
            for row in self._position_rows.values():
                row["dot"].configure(text_color="#555555")
                row["label"].configure(text_color=("gray20", "gray80"))
                row["pct"].configure(text="")
            return

        if position not in self._position_rows:
            return

        row = self._position_rows[position]

        if state == "active":
            # Highlight current position in amber
            row["dot"].configure(text_color="#f0ad4e")
            row["label"].configure(text_color="#f0ad4e")
            row["pct"].configure(text="...")

        elif state == "done":
            # Show the nominal six-step progress for accelerometer calibration.
            pct = min(int((position / 6) * 100), 100)
            row["dot"].configure(text_color="#2ecc71")
            row["label"].configure(text_color="#2ecc71")
            row["pct"].configure(text=f"{pct}%")

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
        self.progress_label.configure(text=f"{int(value)}%")


if __name__ == "__main__":
    app = CalibrationWindow()
    app.mainloop()
