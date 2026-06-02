import customtkinter as ctk


class FailsafePanel(ctk.CTkFrame):

    def __init__(self, parent, master_conn=None):
        super().__init__(parent)

        self.master_conn = master_conn

        self.build_ui()

    def build_ui(self):

        # Battery
        battery_frame = ctk.CTkFrame(self)
        battery_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(
            battery_frame,
            text="Battery"
        ).pack(anchor="w")

        self.low_battery = ctk.CTkEntry(battery_frame)
        self.low_battery.insert(0, "7.2")
        self.low_battery.pack(fill="x")

        self.reserved_mah = ctk.CTkEntry(battery_frame)
        self.reserved_mah.insert(0, "0")
        self.reserved_mah.pack(fill="x")

        self.low_timer = ctk.CTkEntry(battery_frame)
        self.low_timer.insert(0, "10")
        self.low_timer.pack(fill="x")

        self.batt_action = ctk.CTkComboBox(
            battery_frame,
            values=["Land", "RTL", "Smart RTL"]
        )
        self.batt_action.set("Land")
        self.batt_action.pack(fill="x")

        # Radio
        radio_frame = ctk.CTkFrame(self)
        radio_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(
            radio_frame,
            text="Radio"
        ).pack(anchor="w")

        self.radio_action = ctk.CTkComboBox(
            radio_frame,
            values=[
                "Enabled always Land",
                "Enabled Continue Mission",
                "Disabled"
            ]
        )
        self.radio_action.set("Enabled always Land")
        self.radio_action.pack(fill="x")

        self.fs_pwm = ctk.CTkEntry(radio_frame)
        self.fs_pwm.insert(0, "975")
        self.fs_pwm.pack(fill="x")

        # GCS
        gcs_frame = ctk.CTkFrame(self)
        gcs_frame.pack(fill="x", padx=10, pady=5)

        self.gcs_enable = ctk.BooleanVar(value=True)

        ctk.CTkCheckBox(
            gcs_frame,
            text="GCS FS Enable",
            variable=self.gcs_enable
        ).pack(anchor="w")

        # Save
        ctk.CTkButton(
            self,
            text="Save",
            command=self.save_parameters
        ).pack(pady=10)

    # Backend stays inside same file
    def save_parameters(self):

        data = {
            "low_battery": self.low_battery.get(),
            "reserved_mah": self.reserved_mah.get(),
            "low_timer": self.low_timer.get(),
            "battery_action": self.batt_action.get(),
            "radio_action": self.radio_action.get(),
            "fs_pwm": self.fs_pwm.get(),
            "gcs_enable": self.gcs_enable.get()
        }

        print("Failsafe Settings")
        print(data)