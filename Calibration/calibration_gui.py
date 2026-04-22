import customtkinter as ctk
import serial.tools.list_ports
from tkinter import messagebox
from backend import DroneBackend

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class CalibrationWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("MAVLink Calibration Interface")
        self.geometry("980x560")

        # BACKEND
        self.backend = DroneBackend()
        self.backend.cb_status = self.set_status
        self.backend.cb_text = self.handle_statustext
        self.backend.cb_telemetry = self.update_telemetry
        self.backend.cb_ack = self.handle_ack

        # Calibration state (GUI side)
        self.in_calibration = False
        self.current_step = 0

        # ================= LEFT PANEL =================
        self.left_panel = ctk.CTkFrame(self, fg_color="#252526", corner_radius=0)
        self.left_panel.pack(side="left", fill="y")

        ctk.CTkLabel(self.left_panel, text="CALIBRATION",
                     font=("Arial", 20, "bold"),
                     text_color="#569cd6").pack(pady=20)

        # 👇 IMPORTANT: button now uses NEW logic
        self.accel_btn = self.create_button("Accelerometer", self.on_accel_click)

        self.create_button("Compass", lambda: None)
        self.create_button("Gyroscope", lambda: None)
        self.create_button("Radio Control", lambda: None)

        # ================= RIGHT PANEL =================
        self.right_panel = ctk.CTkFrame(self)
        self.right_panel.pack(side="right", fill="both", expand=True, padx=20, pady=20)

        # CONNECTION BAR
        top = ctk.CTkFrame(self.right_panel)
        top.pack(fill="x", pady=5)

        self.port_combo = ctk.CTkComboBox(top, width=250)
        self.port_combo.pack(side="left", padx=5)

        self.baud_combo = ctk.CTkComboBox(top, values=["57600", "115200"])
        self.baud_combo.set("57600")
        self.baud_combo.pack(side="left", padx=5)

        ctk.CTkButton(top, text="Refresh", command=self.refresh_ports).pack(side="left", padx=5)

        self.connect_btn = ctk.CTkButton(top, text="Connect", command=self.toggle_connection)
        self.connect_btn.pack(side="left", padx=5)

        # TITLE
        self.title_label = ctk.CTkLabel(self.right_panel,
                                       text="Select a sensor to begin",
                                       font=("Arial", 18, "bold"))
        self.title_label.pack(anchor="w", pady=10)

        # TEXTBOX
        self.textbox = ctk.CTkTextbox(self.right_panel)
        self.textbox.pack(fill="both", expand=True)

        self.textbox.insert("1.0",
                            "Welcome to MAVLink Calibration Tool\n\n"
                            "1. Connect your flight controller\n"
                            "2. Wait for heartbeat\n"
                            "3. Select calibration module")

        # STATUS
        self.status = ctk.CTkLabel(self.right_panel, text="Status: Ready")
        self.status.pack(anchor="w", pady=5)

        self.telemetry = ctk.CTkLabel(self.right_panel,
                                     text="Hardware: Offline | Battery: -- | Mode: --")
        self.telemetry.pack(anchor="w")

        self.progress = ctk.CTkProgressBar(self.right_panel)
        self.progress.set(0)
        self.progress.pack(fill="x", pady=10)

        self.refresh_ports()

    def create_button(self, text, cmd):
        btn = ctk.CTkButton(self.left_panel, text=text, command=cmd)
        btn.pack(fill="x", padx=10, pady=5)
        return btn

    # ================= CONNECTION =================

    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if not ports:
            ports = ["No ports available"]

        self.port_combo.configure(values=ports)
        self.port_combo.set(ports[0])

    def toggle_connection(self):
        if self.backend.master:
            self.backend.disconnect()
            self.connect_btn.configure(text="Connect")
            return

        port = self.port_combo.get()

        if "No" in port:
            messagebox.showerror("Error", "No COM port found")
            return

        baud = int(self.baud_combo.get())

        self.backend.connect(port, baud)
        self.connect_btn.configure(text="Disconnect")

    # ================= 🚀 CALIBRATION BUTTON LOGIC =================

    def on_accel_click(self):
        # FIRST CLICK → start calibration
        if not self.backend.in_calibration:
            self.backend.start_accel_calibration()

            self.in_calibration = True
            self.current_step = 0

            self.accel_btn.configure(text="Next Step")

        # NEXT CLICKS → send step based on instruction
        else:
            self.backend.next_accel_step(self.current_step)

    # ================= CALLBACKS =================

    def set_status(self, text, color):
        self.status.configure(text=f"Status: {text}", text_color=color)

    def handle_statustext(self, text):
        self.textbox.insert("end", f"\n{text}")
        self.textbox.see("end")

        t = text.lower()

        # 👇 THIS decides which step to send next
        if "level" in t:
            self.current_step = 1
            self.progress.set(0.2)

        elif "left" in t:
            self.current_step = 2
            self.progress.set(0.35)

        elif "right" in t:
            self.current_step = 3
            self.progress.set(0.5)

        elif "nose down" in t:
            self.current_step = 4
            self.progress.set(0.65)

        elif "nose up" in t:
            self.current_step = 5
            self.progress.set(0.8)

        elif "back" in t:
            self.current_step = 6
            self.progress.set(0.9)

        elif "successful" in t:
            self.progress.set(1.0)
            self.backend.in_calibration = False
            self.accel_btn.configure(text="Accelerometer")

    def update_telemetry(self, mode, battery):
        txt = f"Hardware: Connected | Battery: {battery or '--'} | Mode: {mode or '--'}"
        self.telemetry.configure(text=txt)

    def handle_ack(self, result):
        self.set_status(f"ACK: {result}", "#cccccc")


if __name__ == "__main__":
    app = CalibrationWindow()
    app.mainloop()