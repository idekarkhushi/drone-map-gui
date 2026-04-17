import serial
import serial.tools.list_ports
from tkinter import messagebox
import customtkinter
from customtkinter import *

# ================= WINDOW =================
win = customtkinter.CTk()
win.title("ApnaGCS")
win.resizable(False, False)

window_width = 900
window_height = 600

screen_width = win.winfo_screenwidth()
screen_height = win.winfo_screenheight()
x = (screen_width - window_width) // 2
y = (screen_height - window_height) // 2
win.geometry(f"{window_width}x{window_height}+{x+100}+{y+50}")

# ================= GET COM PORTS =================
def get_com_ports():
    serial_ports_info = []
    serial_con = serial.tools.list_ports.comports()
    
    for port in serial_con:
        port_info = f"{port.device} {port.description}"
        serial_ports_info.append(port_info)

    if not serial_ports_info:
        serial_ports_info = ["No ports available"]

    return serial_ports_info

# ================= CONNECTION FUNCTION =================
def connection_estd():
    usb_port = usb_value.get()

    # Check valid selection
    if not usb_port or "COM" not in usb_port:
        messagebox.showerror("Error", "Please select a valid COM port")
        return

    selected_port = usb_port.split()[0]

    try:
        serial_com = serial.Serial(selected_port, baudrate=9600, timeout=1)

        print("Connecting to " + usb_port)
        messagebox.showinfo("Connection Established", f"Connected to {usb_port}")
        print("Connected to " + usb_port)

    except Exception as e:
        messagebox.showerror("Connection Error", str(e))

# ================= UI =================        
usb_value = CTkComboBox(
    master=win,
    values=get_com_ports(),
    width=200,
    fg_color='white'
)
usb_value.set("Select COM Port")
usb_value.place(x=80, y=90)

connect_btn = customtkinter.CTkButton(
    master=win,
    text="Connect",
    height=30,
    width=130,
    command=connection_estd,
    fg_color='#198450',
    corner_radius=30
)
connect_btn.place(x=120, y=150)

# ================= RUN =================
win.mainloop()