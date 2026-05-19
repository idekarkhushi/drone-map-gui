import math
import customtkinter as ctk
from DataPage import DataPage

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

root = ctk.CTk()
root.title("Mission Planner – DataPage Preview")
root.geometry("1100x680")
root.minsize(800, 500)

page = DataPage(root)
page.pack(fill="both", expand=True)

t = [0.0]

def tick():
    t[0] += 0.04
    pitch = 15 * math.sin(t[0])
    roll = 25 * math.sin(t[0] * 0.7)
    yaw = (t[0] * 18) % 360
    page.update_attitude(pitch, roll, yaw)
    page.update_telemetry(
        alt=50 + 10 * math.sin(t[0] * 0.5),
        spd=12.4, dist=134.2, yaw=yaw,
        vspd=0.8 * math.sin(t[0]), dmav=210.0,
    )
    root.after(60, tick)

root.after(400, tick)
root.mainloop()
