import customtkinter as ctk
import tkintermapview
from PIL import Image
import random

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Mission Planner UI")
        self.geometry("1200x700")

        # ===== TOP TOOLBAR =====
        self.toolbar = ctk.CTkFrame(self, height=70)
        self.toolbar.pack(fill="x")

        self.icons = {
            "data": ctk.CTkImage(Image.open(r"C:\Users\ADMIN\Desktop\Drone GUI\Updated GUI\data.png"), size=(30, 30)),
            "plan": ctk.CTkImage(Image.open(r"C:\Users\ADMIN\Desktop\Drone GUI\Updated GUI\plan.png"), size=(30, 30)),
        }

        self.add_toolbar_button("DATA", self.icons["data"], lambda: self.show("data"))
        self.add_toolbar_button("PLAN", self.icons["plan"], lambda: self.show("plan"))

        # ===== MAIN CONTAINER =====
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

if __name__ == "__main__":
    app = App()
    app.mainloop()