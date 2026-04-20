import customtkinter as ctk
from PIL import Image

from DataPage import DataPage
from PlanPage import PlanPage

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Mission Planner")
        self.geometry("1200x700")
        
        #DATA
        self.waypoints = []
        self.map_markers = []
        self.table_rows = []


        # ===== TOP TOOLBAR =====
        self.toolbar = ctk.CTkFrame(self, height=34)
        self.toolbar.pack(fill="x")
        self.toolbar.pack_propagate(False)

        self.left_toolbar = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        self.left_toolbar.pack(side="left", padx=(4, 0), pady=2)

        self.right_toolbar = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        self.right_toolbar.pack(side="right", padx=8, pady=2)

        self.icons = {
            "data": ctk.CTkImage(Image.open(r"Updated GUI/data.png"), size=(18, 18)),
            "plan": ctk.CTkImage(Image.open(r"Updated GUI/plan.png"), size=(18, 18)),
        }

        self.add_toolbar_button("DATA", self.icons["data"], lambda: self.show("data"))
        self.add_toolbar_button("PLAN", self.icons["plan"], lambda: self.show("plan"))

        self.com_port_combo = ctk.CTkComboBox(
            self.right_toolbar,
            values=["COM3", "COM4", "COM5"],
            width=90,
            height=28
        )
        self.com_port_combo.pack(side="left", padx=(0, 6))
        self.com_port_combo.set("COM3")

        self.connect_button = ctk.CTkButton(
            self.right_toolbar,
            text="CONNECT",
            width=90,
            height=28
        )
        self.connect_button.pack(side="left")

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
            self.left_toolbar,
            text=text,
            image=icon,
            compound="top",
            width=58,
            height=30,
            corner_radius=6,
            font=("Arial", 10),
            command=command
        )
        btn.pack(side="left", padx=5, pady=0)

    def show(self, name):
        self.frames[name].tkraise()

# RUN
if __name__ == "__main__":
    app = App()
    app.mainloop()
