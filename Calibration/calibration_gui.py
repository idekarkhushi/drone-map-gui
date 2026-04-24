import customtkinter as ctk
import serial.tools.list_ports

from backend import DroneBackend

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Maps ArduPilot position numbers (1-6) to display names shown in the
# sidebar indicators. Must stay in sync with DroneBackend.ACCEL_POSITION_LABELS.
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

        # Backend
        self.backend = DroneBackend()

        # Wire all backend callbacks through self.after so Tk is never
        # touched from the background MAVLink reader thread.
        self.backend.cb_status = lambda t, c: self.after(0, self.set_status, t, c)
        self.backend.cb_text = lambda t: self.after(0, self.handle_statustext, t)
        self.backend.cb_telemetry = lambda m, b: self.after(0, self.update_telemetry, m, b)
        self.backend.cb_ack = lambda r: self.after(0, self.handle_ack, r)
        self.backend.cb_progress = lambda v: self.after(0, self.update_progress, v)
        self.backend.cb_confirm_ready = lambda e: self.after(0, self.set_confirm_ready, e)
        self.backend.cb_calibration_done = lambda s: self.after(0, self.on_calibration_done, s)
        self.backend.cb_position_update = lambda p, s: self.after(
            0, self.update_position_indicator, p, s
        )

        # Left panel
        self.left_panel = ctk.CTkFrame(self)
        self.left_panel.pack(side="left", fill="y", padx=8, pady=8)

        # Accelerometer button doubles as the "Next" button once calibration
        # starts. State transitions:
        #   "Accelerometer" (normal) -> click -> start_accel_calibration()
        #   "Next" (disabled)        -> ArduPilot requests pose -> "Next" (normal)
        #   "Next" (normal)          -> click -> confirm_position()
        #   "Accelerometer" (normal) <- calibration done / failed
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

        # Position indicator sidebar
        # One row per accel pose. Dot colour encodes state:
        #   grey   (#555555) - not yet reached
        #   amber  (#f0ad4e) - currently requested by ArduPilot
        #   green  (#2ecc71) - confirmed and accepted
        ctk.CTkLabel(
            self.left_panel,
            text="Accel positions",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        ).pack(anchor="w", padx=6, pady=(16, 4))

        # Dict keyed by position number (1-6); each value holds references to
        # the three widgets in that row so update_position_indicator can
        # reconfigure them without querying the widget tree.
        self._position_rows = {}

        for pos, name in POSITION_LABELS.items():
            row = ctk.CTkFrame(self.left_panel, fg_color="transparent")
            row.pack(fill="x", padx=6, pady=2)

            dot = ctk.CTkLabel(
                row,
                text="●",
                width=18,
                font=ctk.CTkFont(size=14),
                text_color="#555555",
            )
            dot.pack(side="left")

            lbl = ctk.CTkLabel(
                row,
                text=f"{pos}. {name}",
                font=ctk.CTkFont(size=13),
                anchor="w",
            )
            lbl.pack(side="left", fill="x", expand=True)

            pct = ctk.CTkLabel(
                row,
                text="",
                width=36,
                font=ctk.CTkFont(size=12),
                text_color="gray",
            )
            pct.pack(side="right")

            self._position_rows[pos] = {"dot": dot, "label": lbl, "pct": pct}

        # Right panel
        self.right_panel = ctk.CTkFrame(self)
        self.right_panel.pack(side="right", fill="both", expand=True, padx=8, pady=8)

        # Connection bar
        top = ctk.CTkFrame(self.right_panel)
        top.pack(fill="x", pady=(0, 6))

        # Maps the human-readable combo entry back to the raw COM port name.
        self._port_display_map = {}

        # Port combo shows both the COM port and its device description.
        self.port_combo = ctk.CTkComboBox(top, width=260)
        self.port_combo.pack(side="left", padx=4)

        self.baud_combo = ctk.CTkComboBox(top, values=["57600", "115200"], width=100)
        self.baud_combo.set("115200")
        self.baud_combo.pack(side="left", padx=4)

        ctk.CTkButton(
            top, text="Refresh", width=80, command=self.refresh_ports
        ).pack(side="left", padx=4)

        self.connect_btn = ctk.CTkButton(
            top, text="Connect", width=100, command=self.toggle_connection
        )
        self.connect_btn.pack(side="left", padx=4)

        # Status textbox
        # Receives every STATUSTEXT message from the flight controller plus
        # pose placement prompts from the calibration sequence.
        self.textbox = ctk.CTkTextbox(self.right_panel)
        self.textbox.pack(fill="both", expand=True)

        # Status and telemetry labels
        self.status_label = ctk.CTkLabel(self.right_panel, text="Status: Ready")
        self.status_label.pack(anchor="w")

        # Shows flight mode and battery percentage from HEARTBEAT / SYS_STATUS.
        self.telemetry_label = ctk.CTkLabel(self.right_panel, text="")
        self.telemetry_label.pack(anchor="w")

        # Progress bar
        # During accel cal: advances 1/6 per confirmed pose (0 -> 17 -> 33 ...100%).
        # During compass cal: driven by MAG_CAL_PROGRESS completion_pct.
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

    # =========================================================================
    # CONNECTION
    # =========================================================================

    def refresh_ports(self):
        current_display = self.port_combo.get()
        ports = sorted(
            serial.tools.list_ports.comports(),
            key=lambda port: (port.device or "", port.description or ""),
        )

        display_values = []
        self._port_display_map = {}

        for port in ports:
            description = port.description or "Unknown device"
            display = f"{port.device} - {description}"
            display_values.append(display)
            self._port_display_map[display] = port.device

        self.port_combo.configure(values=display_values)
        if current_display in self._port_display_map:
            self.port_combo.set(current_display)
        elif display_values:
            self.port_combo.set(display_values[0])
        else:
            self.port_combo.set("")

    def toggle_connection(self):
        """Connect if disconnected, disconnect if connected."""
        if self.backend.master:
            self.backend.disconnect()
            self.connect_btn.configure(text="Connect")
            return

        selected_display = self.port_combo.get()
        selected_port = self._port_display_map.get(selected_display, selected_display)
        connected = self.backend.connect(
            selected_port, int(self.baud_combo.get())
        )
        self.connect_btn.configure(text="Disconnect" if connected else "Connect")

    # =========================================================================
    # ACCELEROMETER CALIBRATION
    # =========================================================================

    def on_accel_click(self):
        if not self.backend.in_calibration:
            self.accel_btn.configure(text="Next", state="disabled")
            if not self.backend.start_accel_calibration():
                # start failed (not connected) - revert button immediately
                self.accel_btn.configure(text="Accelerometer", state="normal")
        else:
            self.backend.confirm_position()

    def set_confirm_ready(self, enabled: bool):
        """
        Enable or disable the Next button.
        Called by cb_confirm_ready - True when ArduPilot requests a new pose,
        False immediately after the user clicks Next or when calibration ends.
        """
        self.accel_btn.configure(state="normal" if enabled else "disabled")

    def on_calibration_done(self, success: bool):
        """
        Reset the Accelerometer button to its initial state after calibration
        completes (success or failure) or after a serial disconnect.
        """
        self.accel_btn.configure(text="Accelerometer", state="normal")

    def update_position_indicator(self, position: int, state: str):
        """
        state values:
          "reset"  - calibration just started; reset all rows to grey
          "active" - ArduPilot is requesting this position (amber)
          "done"   - user confirmed this position (green) with % shown
        """
        if state == "reset":
            # Clear all rows back to their default grey state.
            for row in self._position_rows.values():
                row["dot"].configure(text_color="#555555")
                row["label"].configure(text_color=("gray20", "gray80"))
                row["pct"].configure(text="")
            return

        if position not in self._position_rows:
            return

        row = self._position_rows[position]

        if state == "active":
            # Amber = waiting for user to place and confirm.
            row["dot"].configure(text_color="#f0ad4e")
            row["label"].configure(text_color="#f0ad4e")
            row["pct"].configure(text="...")

        elif state == "done":
            # Green = ack sent. Show the step percentage (17, 33, 50, 67, 83, 100).
            pct = min(int((position / 6) * 100), 100)
            row["dot"].configure(text_color="#2ecc71")
            row["label"].configure(text_color="#2ecc71")
            row["pct"].configure(text=f"{pct}%")

    # =========================================================================
    # COMPASS CALIBRATION
    # =========================================================================

    def on_compass_click(self):
        """Start onboard compass calibration."""
        self.backend.start_compass_calibration()

    # =========================================================================
    # BACKEND CALLBACKS  (all called via self.after - main thread only)
    # =========================================================================

    def set_status(self, text, color):
        """Update the status bar label with text and colour."""
        self.status_label.configure(text=text, text_color=color)

    def handle_statustext(self, text):
        """Append a raw STATUSTEXT line to the textbox and scroll to bottom."""
        self.textbox.insert("end", f"{text}\n")
        self.textbox.see("end")

    def update_telemetry(self, mode, battery):
        """Refresh the telemetry label with the latest mode and battery %."""
        parts = []
        if mode is not None:
            parts.append(f"Mode: {mode}")
        if battery is not None:
            parts.append(f"Battery: {battery}%")
        self.telemetry_label.configure(text="  |  ".join(parts))

    def handle_ack(self, result):
        """Placeholder for COMMAND_ACK handling (result code from ArduPilot)."""
        pass

    def update_progress(self, value):
        """
        Set the progress bar and percentage label.
        value is 0-100 (int); CTkProgressBar expects 0.0-1.0.
        """
        self.progress.set(value / 100)
        self.progress_label.configure(text=f"{int(value)}%")


if __name__ == "__main__":
    app = CalibrationWindow()
    app.mainloop()
