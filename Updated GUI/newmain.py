import os
import sys
import threading
import time
import socket
import subprocess
import customtkinter as ctk
from PIL import Image
import tkinter.messagebox as messagebox

# Ensure local GUI modules can be imported when running this file directly
base_dir = os.path.dirname(os.path.abspath(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

try:
    from serial.tools import list_ports
    import serial
except Exception:
    list_ports = None
    serial = None

try:
    from pymavlink import mavutil
except Exception:
    mavutil = None

# Windows registry access for Bluetooth COM port discovery
try:
    import winreg
    WINREG_AVAILABLE = True
except ImportError:
    winreg = None
    WINREG_AVAILABLE = False

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Connection mode constants
MODE_SERIAL    = "Serial"
MODE_BLUETOOTH = "Bluetooth"
MODE_WIFI      = "WiFi / UDP"


def _get_bluetooth_com_ports():
    """
    Scan for Bluetooth-paired virtual COM ports on Windows using two methods:
    1. Windows registry (BTHENUM entries in COM port database)
    2. pyserial port scan filtered by Bluetooth-related descriptions
    Returns list of (display_label, device_path) tuples.
    """
    bt_ports = {}  # device -> label

    # ── Method 1: Registry scan ───────────────────────────────────────────
    if WINREG_AVAILABLE:
        reg_paths = [
            r"SYSTEM\CurrentControlSet\Enum\BTHENUM",
            r"SYSTEM\CurrentControlSet\Services\BTHMODEM",
        ]
        for reg_path in reg_paths:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        sub_name = winreg.EnumKey(key, i)
                        sub_key  = winreg.OpenKey(key, sub_name)
                        for j in range(winreg.QueryInfoKey(sub_key)[0]):
                            try:
                                leaf_name = winreg.EnumKey(sub_key, j)
                                leaf_key  = winreg.OpenKey(sub_key, leaf_name)
                                try:
                                    friendly, _ = winreg.QueryValueEx(leaf_key, "FriendlyName")
                                    # Look for PortName under Device Parameters
                                    params_key = winreg.OpenKey(
                                        leaf_key, r"Device Parameters"
                                    )
                                    port_name, _ = winreg.QueryValueEx(params_key, "PortName")
                                    bt_ports[port_name] = friendly
                                except (FileNotFoundError, OSError):
                                    pass
                            except OSError:
                                pass
                    except OSError:
                        pass
            except OSError:
                pass

    # ── Method 2: pyserial description filter ────────────────────────────
    if list_ports is not None:
        try:
            for p in list_ports.comports():
                desc = (p.description or "").lower()
                hwid = (p.hwid or "").lower()
                if any(kw in desc or kw in hwid for kw in
                       ("bluetooth", "bth", "rfcomm", "standard serial over bluetooth")):
                    label = p.description or "Bluetooth Serial"
                    if p.device not in bt_ports:
                        bt_ports[p.device] = label
        except Exception:
            pass

    return [(f"{label}  ({dev})", dev) for dev, label in bt_ports.items()]


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Mission Planner")
        self.geometry("1200x700")
        self.minsize(900, 580)

        # DATA
        self.waypoints  = []
        self.map_markers = []
        self.table_rows  = []

        # Connection state
        self.serial_conn   = None
        self.udp_socket    = None
        self._port_display_map = {}
        self._port_desc_map    = {}
        self._bt_port_map      = {}   # label -> device path for BT ports
        self.heartbeat_timeout = 5
        self.last_heartbeat    = None
        self._heartbeat_thread = None
        self._mavlink_thread   = None

        # ── TOP TOOLBAR ──────────────────────────────────────────────────
        self.toolbar = ctk.CTkFrame(self, height=34)
        self.toolbar.pack(fill="x")
        self.toolbar.pack_propagate(False)

        self.left_toolbar = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        self.left_toolbar.pack(side="left", padx=(4, 0), pady=2)

        self.right_toolbar = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        self.right_toolbar.pack(side="right", padx=8, pady=2)

        self.icons = {
            "data":   ctk.CTkImage(Image.open(r"Updated GUI\data.png"),   size=(18, 18)),
            "plan":   ctk.CTkImage(Image.open(r"Updated GUI\plan.png"),   size=(18, 18)),
            "config": ctk.CTkImage(Image.open(r"Updated GUI\config.png"), size=(18, 18)),
            "camera": ctk.CTkImage(Image.open(r"Updated GUI\camera.png"), size=(18, 18)),
        }

        self.add_toolbar_button("DATA",   self.icons["data"],   lambda: self.show("data"))
        self.add_toolbar_button("PLAN",   self.icons["plan"],   lambda: self.show("plan"))
        self.add_toolbar_button("CONFIG", self.icons["config"], lambda: self.show("config"))
        self.add_toolbar_button("CAMERA", self.icons["camera"], lambda: self.show("camera"))

        # ── CONNECTION PANEL (right side) ─────────────────────────────────
        connection_bar = ctk.CTkFrame(self.right_toolbar, fg_color="transparent")
        connection_bar.pack(side="top", fill="x")

        ctk.CTkLabel(connection_bar, text="Mode:").pack(side="left", padx=(0, 4))

        self.mode_combo = ctk.CTkComboBox(
            connection_bar,
            values=[MODE_SERIAL, MODE_BLUETOOTH, MODE_WIFI],
            width=110,
            height=28,
            command=self._on_mode_changed
        )
        self.mode_combo.set(MODE_SERIAL)
        self.mode_combo.pack(side="left", padx=(0, 8))

        # Container for dynamic panels
        self.conn_widget_frame = ctk.CTkFrame(connection_bar, fg_color="transparent")
        self.conn_widget_frame.pack(side="left", fill="x", expand=True)

        self._build_serial_panel()
        self._build_bluetooth_panel()
        self._build_wifi_panel()

        # Shared CONNECT button
        self.connect_button = ctk.CTkButton(
            connection_bar,
            text="CONNECT",
            width=90,
            height=28,
            command=self.toggle_connection
        )
        self.connect_button.pack(side="left", padx=(6, 0))

        # Status label
        self.port_desc_label = ctk.CTkLabel(
            self.right_toolbar,
            text="No connection",
            font=("Arial", 10),
            text_color="gray"
        )
        self.port_desc_label.pack(side="top", fill="x", padx=(0, 4), pady=(2, 0))

        self._on_mode_changed(MODE_SERIAL)

        # ── MAIN AREA ─────────────────────────────────────────────────────
        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True)

        from DataPage   import DataPage
        from PlanPage   import PlanPage
        from ConfigPage import ConfigPage
        from Camerapage import CameraPage

        self.frames = {
            "data":   DataPage(self.container),
            "plan":   PlanPage(self.container),
            "config": ConfigPage(self.container),
            "camera": CameraPage(self.container),
        }
        for frame in self.frames.values():
            frame.place(relwidth=1, relheight=1)

        self.show("data")

    # ─────────────────────────────────────────────────────────────────────
    # PANEL BUILDERS
    # ─────────────────────────────────────────────────────────────────────

    def _build_serial_panel(self):
        self.serial_panel = ctk.CTkFrame(self.conn_widget_frame, fg_color="transparent")

        ctk.CTkLabel(self.serial_panel, text="COM Port:").pack(side="left", padx=(0, 4))
        port_values = self._scan_serial_ports()
        self.com_port_combo = ctk.CTkComboBox(
            self.serial_panel, values=port_values,
            width=220, height=28, command=self._on_port_selected
        )
        self.com_port_combo.set(port_values[0] if port_values else "No ports")
        self.com_port_combo.pack(side="left", padx=(0, 6))

        ctk.CTkLabel(self.serial_panel, text="Baud:").pack(side="left", padx=(0, 4))
        self.baud_combo = ctk.CTkComboBox(
            self.serial_panel,
            values=["9600", "19200", "38400", "57600", "115200"],
            width=100, height=28
        )
        self.baud_combo.set("57600")
        self.baud_combo.pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            self.serial_panel, text="REFRESH", width=80, height=28,
            command=self.refresh_com_ports
        ).pack(side="left")

    def _build_bluetooth_panel(self):
        """
        Bluetooth panel — no PyBluez needed.
        Uses Windows-paired virtual COM ports discovered via registry / pyserial.
        """
        self.bt_panel = ctk.CTkFrame(self.conn_widget_frame, fg_color="transparent")

        ctk.CTkLabel(self.bt_panel, text="BT Device:").pack(side="left", padx=(0, 4))

        self.bt_device_combo = ctk.CTkComboBox(
            self.bt_panel, values=["Click SCAN to find paired devices"],
            width=260, height=28
        )
        self.bt_device_combo.set("Click SCAN to find paired devices")
        self.bt_device_combo.pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            self.bt_panel, text="SCAN", width=70, height=28,
            command=self._scan_bluetooth_com_ports
        ).pack(side="left", padx=(0, 6))

        ctk.CTkLabel(self.bt_panel, text="Baud:").pack(side="left", padx=(0, 4))
        self.bt_baud_combo = ctk.CTkComboBox(
            self.bt_panel,
            values=["9600", "19200", "38400", "57600", "115200"],
            width=100, height=28
        )
        self.bt_baud_combo.set("57600")
        self.bt_baud_combo.pack(side="left", padx=(0, 4))

        # Hint button — opens Windows BT settings
        ctk.CTkButton(
            self.bt_panel, text="＋ Pair Device", width=100, height=28,
            fg_color="transparent", border_width=1,
            command=lambda: subprocess.Popen(
                ["explorer", "ms-settings:bluetooth"], shell=True
            )
        ).pack(side="left", padx=(6, 0))

    def _build_wifi_panel(self):
        self.wifi_panel = ctk.CTkFrame(self.conn_widget_frame, fg_color="transparent")

        ctk.CTkLabel(self.wifi_panel, text="IP:").pack(side="left", padx=(0, 4))
        self.wifi_ip_entry = ctk.CTkEntry(
            self.wifi_panel, width=140, height=28, placeholder_text="192.168.1.1"
        )
        self.wifi_ip_entry.pack(side="left", padx=(0, 6))

        ctk.CTkLabel(self.wifi_panel, text="Port:").pack(side="left", padx=(0, 4))
        self.wifi_port_entry = ctk.CTkEntry(
            self.wifi_panel, width=70, height=28, placeholder_text="14550"
        )
        self.wifi_port_entry.pack(side="left", padx=(0, 6))

        ctk.CTkLabel(self.wifi_panel, text="Protocol:").pack(side="left", padx=(0, 4))
        self.wifi_proto_combo = ctk.CTkComboBox(
            self.wifi_panel, values=["UDP", "TCP"], width=75, height=28
        )
        self.wifi_proto_combo.set("UDP")
        self.wifi_proto_combo.pack(side="left")

    # ─────────────────────────────────────────────────────────────────────
    # MODE SWITCHING
    # ─────────────────────────────────────────────────────────────────────

    def _on_mode_changed(self, mode):
        for panel in (self.serial_panel, self.bt_panel, self.wifi_panel):
            panel.pack_forget()

        if mode == MODE_SERIAL:
            self.serial_panel.pack(side="left", fill="x", expand=True)
            self._update_port_desc(self.com_port_combo.get())
        elif mode == MODE_BLUETOOTH:
            self.bt_panel.pack(side="left", fill="x", expand=True)
            self.port_desc_label.configure(
                text="Bluetooth — click SCAN to list paired devices  |  Use '＋ Pair Device' to pair new ones",
                text_color="gray"
            )
        elif mode == MODE_WIFI:
            self.wifi_panel.pack(side="left", fill="x", expand=True)
            self.port_desc_label.configure(
                text="WiFi / UDP — enter IP and port then click CONNECT",
                text_color="gray"
            )

    # ─────────────────────────────────────────────────────────────────────
    # SERIAL HELPERS
    # ─────────────────────────────────────────────────────────────────────

    def _scan_serial_ports(self):
        self._port_display_map = {}
        self._port_desc_map    = {}
        if list_ports is None:
            return ["No ports"]
        try:
            ports = list_ports.comports()
        except Exception:
            return ["No ports"]
        values = []
        for p in ports:
            desc    = p.description or "Unknown device"
            display = f"{p.device} - {desc}"
            values.append(display)
            self._port_display_map[display] = p.device
            self._port_desc_map[display]    = desc
        return values if values else ["No ports"]

    def refresh_com_ports(self, preserve_selection=True):
        port_values = self._scan_serial_ports()
        selected    = self.com_port_combo.get()
        self.com_port_combo.configure(values=port_values)
        if preserve_selection and selected in port_values:
            self.com_port_combo.set(selected)
        elif port_values and port_values[0] != "No ports":
            self.com_port_combo.set(port_values[0])
        else:
            self.com_port_combo.set("No ports")
        self._update_port_desc(self.com_port_combo.get())

    def _on_port_selected(self, selected_display):
        self._update_port_desc(selected_display)

    def _update_port_desc(self, selected_display):
        if not selected_display or selected_display == "No ports":
            self.port_desc_label.configure(text="No port selected", text_color="gray")
            return
        desc   = self._port_desc_map.get(selected_display, "")
        device = self._port_display_map.get(selected_display, selected_display)
        if desc and desc != "Unknown device":
            self.port_desc_label.configure(text=f"{desc}  ·  {device}", text_color="#4fc3f7")
        else:
            self.port_desc_label.configure(text=f"{device}  — no description available", text_color="gray")

    # ─────────────────────────────────────────────────────────────────────
    # BLUETOOTH HELPERS  (no PyBluez — uses Windows virtual COM ports)
    # ─────────────────────────────────────────────────────────────────────

    def _scan_bluetooth_com_ports(self):
        """Scan for Bluetooth virtual COM ports in a background thread."""
        self.port_desc_label.configure(
            text="Scanning for paired Bluetooth COM ports…", text_color="#ffd54f"
        )
        self.update_idletasks()

        def _do_scan():
            results = _get_bluetooth_com_ports()
            self.after(0, lambda: self._populate_bt_combo(results))

        threading.Thread(target=_do_scan, daemon=True).start()

    def _populate_bt_combo(self, results):
        """Populate the BT device dropdown after scan completes."""
        self._bt_port_map = {}

        if not results:
            self.bt_device_combo.configure(values=["No paired Bluetooth COM ports found"])
            self.bt_device_combo.set("No paired Bluetooth COM ports found")
            self.port_desc_label.configure(
                text="No Bluetooth COM ports found — pair your device in Windows Bluetooth settings first",
                text_color="#ef9a9a"
            )
            return

        labels = [label for label, _ in results]
        for label, device in results:
            self._bt_port_map[label] = device

        self.bt_device_combo.configure(values=labels)
        self.bt_device_combo.set(labels[0])
        self.port_desc_label.configure(
            text=f"Found {len(results)} Bluetooth COM port(s) — select and click CONNECT",
            text_color="#4fc3f7"
        )

    def _connect_bluetooth(self):
        """Connect to a Bluetooth device via its Windows virtual COM port."""
        selected = self.bt_device_combo.get()
        if selected in ("Click SCAN to find paired devices", "No paired Bluetooth COM ports found", ""):
            messagebox.showwarning(
                "No Device Selected",
                "Click SCAN first to find paired Bluetooth devices.\n\n"
                "If no devices appear, pair your device in Windows:\n"
                "Settings → Bluetooth & devices → Add device"
            )
            return

        device_path = self._bt_port_map.get(selected)
        if not device_path:
            # Fallback: try to extract COM port from label like "Name  (COM5)"
            import re
            m = re.search(r'(COM\d+)', selected)
            if m:
                device_path = m.group(1)
            else:
                messagebox.showerror("Error", f"Could not resolve COM port for: {selected}")
                return

        baud_text = self.bt_baud_combo.get()
        try:
            baud_int = int(baud_text)
        except ValueError:
            baud_int = 57600

        try:
            if mavutil is not None:
                self.serial_conn = mavutil.mavlink_connection(device_path, baud=baud_int)
                self.serial_conn.wait_heartbeat(timeout=self.heartbeat_timeout)
                self.last_heartbeat = time.time()
                self._start_heartbeat_monitor()
            else:
                self.serial_conn = serial.Serial(device_path, baudrate=baud_int, timeout=1)

            self.connect_button.configure(text="DISCONNECT")
            self.port_desc_label.configure(
                text=f"Bluetooth connected → {selected}", text_color="#81c784"
            )
        except Exception as e:
            messagebox.showerror("Bluetooth Connection Failed", str(e))
            self.serial_conn = None

    # ─────────────────────────────────────────────────────────────────────
    # WiFi HELPERS
    # ─────────────────────────────────────────────────────────────────────

    def _connect_wifi(self):
        ip        = self.wifi_ip_entry.get().strip()
        port_text = self.wifi_port_entry.get().strip()
        proto     = self.wifi_proto_combo.get()

        if not ip:
            messagebox.showwarning("No IP", "Please enter an IP address.")
            return
        try:
            port_num = int(port_text)
        except ValueError:
            messagebox.showwarning("Invalid Port", "Please enter a valid port number.")
            return

        try:
            if mavutil is not None:
                prefix   = "udpin" if proto == "UDP" else "tcp"
                conn_str = f"{prefix}:{ip}:{port_num}"
                self.serial_conn = mavutil.mavlink_connection(conn_str)
                self.serial_conn.wait_heartbeat(timeout=self.heartbeat_timeout)
                self.last_heartbeat = time.time()
                self._start_heartbeat_monitor()
            else:
                self.udp_socket = socket.socket(
                    socket.AF_INET,
                    socket.SOCK_DGRAM if proto == "UDP" else socket.SOCK_STREAM
                )
                if proto == "TCP":
                    self.udp_socket.connect((ip, port_num))

            self.connect_button.configure(text="DISCONNECT")
            self.port_desc_label.configure(
                text=f"{proto} connected → {ip}:{port_num}", text_color="#81c784"
            )
        except Exception as e:
            messagebox.showerror(f"{proto} Connection Failed", str(e))
            self.serial_conn = None
            self.udp_socket  = None

    def _disconnect_wifi(self):
        if self.udp_socket:
            try:
                self.udp_socket.close()
            except Exception:
                pass
            self.udp_socket = None

    # ─────────────────────────────────────────────────────────────────────
    # UNIFIED CONNECT / DISCONNECT
    # ─────────────────────────────────────────────────────────────────────

    def toggle_connection(self):
        if self._is_connected():
            self._disconnect_all()
        else:
            mode = self.mode_combo.get()
            if mode == MODE_SERIAL:
                self._connect_serial()
            elif mode == MODE_BLUETOOTH:
                self._connect_bluetooth()
            elif mode == MODE_WIFI:
                self._connect_wifi()

    def _disconnect_all(self):
        if self.serial_conn:
            try:
                self.serial_conn.close()
            except Exception:
                pass
            self.serial_conn = None
        if self.udp_socket:
            try:
                self.udp_socket.close()
            except Exception:
                pass
            self.udp_socket = None
        self.last_heartbeat    = None
        self._heartbeat_thread = None
        self._mavlink_thread   = None
        self.connect_button.configure(text="CONNECT")
        mode = self.mode_combo.get()
        if mode == MODE_SERIAL:
            self._update_port_desc(self.com_port_combo.get())
        else:
            self.port_desc_label.configure(text="Disconnected", text_color="gray")

    def _connect_serial(self):
        if serial is None:
            messagebox.showerror("Serial Error", "pyserial is not installed.")
            return

        self.refresh_com_ports(preserve_selection=True)
        selected_display = self.com_port_combo.get()
        if not selected_display or selected_display == "No ports":
            messagebox.showwarning("No Port", "No COM port selected or available.")
            return

        baud_int = 57600
        try:
            baud_int = int(self.baud_combo.get())
        except Exception:
            pass

        port = self._port_display_map.get(selected_display, selected_display)

        try:
            if mavutil is not None:
                self.serial_conn = mavutil.mavlink_connection(port, baud=baud_int)
                self.serial_conn.wait_heartbeat(timeout=self.heartbeat_timeout)
                self.last_heartbeat = time.time()
                self._start_heartbeat_monitor()
            else:
                self.serial_conn = serial.Serial(port, baudrate=baud_int, timeout=1)

            self.connect_button.configure(text="DISCONNECT")
            desc = self._port_desc_map.get(selected_display, "Connected")
            self.port_desc_label.configure(
                text=f"Connected to {desc} ({port})", text_color="#4fc3f7"
            )
        except Exception as e:
            messagebox.showerror("Connection Failed", f"Failed to open {port} at {baud_int}: {e}")
            self.serial_conn = None

    # ─────────────────────────────────────────────────────────────────────
    # HEARTBEAT / MAVLINK THREADS
    # ─────────────────────────────────────────────────────────────────────

    def _is_connected(self):
        if self.serial_conn:
            is_open = getattr(self.serial_conn, 'is_open', None)
            return is_open if is_open is not None else True
        if self.udp_socket:
            return True
        return False

    def _start_heartbeat_monitor(self):
        if mavutil is None or self.serial_conn is None:
            return
        if self._mavlink_thread is None or not self._mavlink_thread.is_alive():
            self._mavlink_thread = threading.Thread(target=self._mavlink_receive_loop, daemon=True)
            self._mavlink_thread.start()
        if self._heartbeat_thread is None or not self._heartbeat_thread.is_alive():
            self._heartbeat_thread = threading.Thread(target=self._heartbeat_watchdog, daemon=True)
            self._heartbeat_thread.start()

    def _mavlink_receive_loop(self):
        while self._is_connected():
            try:
                msg = self.serial_conn.recv_match(blocking=True, timeout=1)
                if msg and msg.get_type() == "HEARTBEAT":
                    self.last_heartbeat = time.time()
            except Exception:
                time.sleep(0.1)

    def _heartbeat_watchdog(self):
        while self._is_connected():
            if (self.last_heartbeat is not None and
                    (time.time() - self.last_heartbeat) > self.heartbeat_timeout):
                self.after(0, lambda: messagebox.showwarning(
                    "Heartbeat Timeout",
                    "No heartbeat received within timeout. Disconnecting."
                ))
                self.after(0, self._disconnect_all)
                break
            time.sleep(1)

    # ─────────────────────────────────────────────────────────────────────
    # TOOLBAR & NAVIGATION
    # ─────────────────────────────────────────────────────────────────────

    def add_toolbar_button(self, text, icon, command):
        btn = ctk.CTkButton(
            self.left_toolbar, text=text, image=icon, compound="top",
            width=58, height=30, corner_radius=6, font=("Arial", 10), command=command
        )
        btn.pack(side="left", padx=5, pady=0)

    def show(self, name):
        self.frames[name].tkraise()


# RUN
if __name__ == "__main__":
    app = App()
    app.mainloop()