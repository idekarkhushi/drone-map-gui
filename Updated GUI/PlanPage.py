import customtkinter as ctk
import tkintermapview
from PIL import Image

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Mission Planner UI Prototype")
        self.geometry("1200x700")

        # ===== TOP TOOLBAR =====
        self.toolbar = ctk.CTkFrame(self, height=70)
        self.toolbar.pack(fill="x")

        self.icons = {
            "data": ctk.CTkImage(Image.open(r"Updated GUI\data.png"), size=(25, 25)),
            "plan": ctk.CTkImage(Image.open(r"Updated GUI\plan.png"), size=(25, 25)),
        }

        self.add_toolbar_button("DATA", self.icons["data"], lambda: self.show("data"))
        self.add_toolbar_button("PLAN", self.icons["plan"], lambda: self.show("plan"))

        # ===== MAIN AREA =====
        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True)

        self.frames = {
            "data": DataPage(self.container),
            "plan": PlanPage(self.container)
        }

        for frame in self.frames.values():
            frame.place(relwidth=1, relheight=1)

        self.show("data")

    def add_toolbar_button(self, text, icon, command):
        btn = ctk.CTkButton(
            self.toolbar,
            text=text,
            image=icon,
            compound="top",
            width=80,
            height=60,
            command=command
        )
        btn.pack(side="left", padx=10, pady=5)

    def show(self, name):
        self.frames[name].tkraise()


# DATA PAGE 
class DataPage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent)

        # ===== MAP =====
        self.map = tkintermapview.TkinterMapView(self)
        self.map.pack(fill="both", expand=True)

        self.map.set_position(19.0760, 72.8777)
        self.map.set_zoom(12)

        # ===== TELEMETRY GRID (like your 1st image) =====
        panel = ctk.CTkFrame(self)
        panel.place(relx=0.02, rely=0.98, anchor="sw")

        values = [
            ("Altitude (m)", "0.00"),
            ("GroundSpeed (m/s)", "0.00"),
            ("Dist to WP (m)", "0.00"),
            ("Yaw (deg)", "0.00"),
            ("Vertical Speed (m/s)", "0.00"),
            ("DistToMAV", "0.00")
        ]

        for i, (label, val) in enumerate(values):
            card = ctk.CTkFrame(panel, width=180, height=90)
            card.grid(row=i // 2, column=i % 2, padx=10, pady=10)

            ctk.CTkLabel(card, text=label, font=("Arial", 13)).pack(pady=5)
            ctk.CTkLabel(card, text=val, font=("Arial", 22, "bold")).pack()


# PLAN PAGE
class PlanPage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent)

        # ===== FULL MAP =====
        self.map = tkintermapview.TkinterMapView(self)
        self.map.pack(fill="both", expand=True)

        self.map.set_position(19.0760, 72.8777)
        self.map.set_zoom(12)

        # ===== BOTTOM INFO BAR (like your 2nd image) =====
        bottom = ctk.CTkFrame(self, height=70)
        bottom.pack(fill="x")

        # LEFT SIDE
        left = ctk.CTkFrame(bottom)
        left.pack(side="left", padx=20, pady=10)

        ctk.CTkLabel(left, text="Selected Waypoint", font=("Arial", 14, "bold")).pack(anchor="w")
        ctk.CTkLabel(
            left,
            text="Alt diff: 0 m | Azimuth: 0 | Gradient: 0% | Heading: 0 | Distance: 0 m",
            font=("Arial", 12)
        ).pack(anchor="w")

        # RIGHT SIDE
        right = ctk.CTkFrame(bottom)
        right.pack(side="right", padx=20, pady=10)

        ctk.CTkLabel(right, text="Total Mission", font=("Arial", 14, "bold")).pack(anchor="e")
        ctk.CTkLabel(
            right,
            text="Distance: 0 m | Time: 00:00 | Telem dist: 0 m",
            font=("Arial", 12)
        ).pack(anchor="e")


# RUN
if __name__ == "__main__":
    app = App()
    app.mainloop()