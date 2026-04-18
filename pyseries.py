import serial
import serial.tools.list_ports
from tkinter import messagebox
import customtkinter


customtkinter.set_appearance_mode("light")
customtkinter.set_default_color_theme("blue")

win = customtkinter.CTk()
win.title("COM Port Connector")
win.resizable(False, False)
win.geometry("420x220")

serial_com = None
connected_port = None


def set_status(text, color):
    status_label.configure(text=text, text_color=color)


def get_com_ports():
    ports = [
        f"{port.device} {port.description}"
        for port in serial.tools.list_ports.comports()
    ]
    return ports if ports else ["No ports available"]


def refresh_com_ports():
    current_value = usb_value.get()
    ports = get_com_ports()

    usb_value.configure(values=ports)

    if current_value in ports:
        usb_value.set(current_value)
    elif ports[0] != "No ports available":
        usb_value.set(ports[0])
    else:
        usb_value.set("No ports available")

    connect_btn.configure(state="normal" if ports[0] != "No ports available" else "disabled")
    if ports[0] == "No ports available":
        set_status("No COM ports detected", "#c0392b")
    elif not connected_port:
        set_status("Select a COM port and press Connect", "#4a5568")
    win.after(2000, refresh_com_ports)


def connection_estd():
    global serial_com, connected_port

    usb_port = usb_value.get()

    if not usb_port or "COM" not in usb_port:
        set_status("Please choose a valid COM port", "#c0392b")
        messagebox.showerror("Error", "Please select a valid COM port")
        return

    selected_port = usb_port.split()[0]

    if connected_port == selected_port and serial_com and serial_com.is_open:
        set_status(f"Connected to {selected_port}", "#198754")
        messagebox.showinfo("Connected", f"Already connected to {selected_port}")
        return

    if serial_com and serial_com.is_open:
        serial_com.close()

    try:
        serial_com = serial.Serial(selected_port, baudrate=9600, timeout=1)
        connected_port = selected_port
        set_status(f"Connected to {selected_port}", "#198754")
        messagebox.showinfo("Connection Established", f"Connected to {usb_port}")
    except Exception as e:
        serial_com = None
        connected_port = None
        set_status("Connection failed", "#c0392b")
        messagebox.showerror("Connection Error", str(e))


title_label = customtkinter.CTkLabel(
    master=win,
    text="COM Port Connector",
    font=("Arial", 22, "bold")
)
title_label.pack(pady=(24, 12))

usb_value = customtkinter.CTkComboBox(
    master=win,
    values=get_com_ports(),
    width=280,
    height=38
)
usb_value.pack(pady=(0, 16))

if usb_value.cget("values")[0] != "No ports available":
    usb_value.set(usb_value.cget("values")[0])
else:
    usb_value.set("No ports available")

connect_btn = customtkinter.CTkButton(
    master=win,
    text="Connect",
    width=160,
    height=38,
    command=connection_estd
)
connect_btn.pack()

status_label = customtkinter.CTkLabel(
    master=win,
    text="Checking COM ports...",
    font=("Arial", 13)
)
status_label.pack(pady=(18, 0))


refresh_com_ports()
win.mainloop()
