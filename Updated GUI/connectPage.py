import re
import socket
import subprocess
import threading
import time
 
import customtkinter as ctk
import tkinter.messagebox as messagebox
 
# ── Optional dependencies ────────────────────────────────────────────────────
try:
    from serial.tools import list_ports
    import serial
except Exception:
    list_ports = None
    serial     = None
 
try:
    from pymavlink import mavutil
except Exception:
    mavutil = None
 
try:
    import winreg
    WINREG_AVAILABLE = True
except ImportError:
    winreg           = None
    WINREG_AVAILABLE = False
 
# ── Mode constants ───────────────────────────────────────────────────────────
MODE_SERIAL    = "Serial"
MODE_BLUETOOTH = "Bluetooth"
MODE_WIFI      = "WiFi"
 
# ── Palette — navy / black / grey / white ────────────────────────────────────
ACCENT       = "#ffffff"       # white — primary text / active highlights
ACCENT_GREEN = "#27af44"       # muted green for connected state
ACCENT_RED   = "#dd3b3b"       # red for errors / disconnect
ACCENT_WARN  = "#e0a020"       # amber for warnings / scanning
BG_PANEL     = "#080d1a"       # near-black window background
BG_CARD      = "#16386B"       # navy — card / tab content background
BG_INNER     = "#111827"       # dark grey — input fields, inner frames
BG_ROW_SEL   = "#395886"       # brighter navy — selected row highlight
BORDER_CLR   = "#628ECB"       # subtle navy border
TEXT_MAIN    = "#ffffff"        # white — all primary labels
TEXT_SUB     = "#B1C9EF"        # grey-blue — secondary / description text
BTN_ACTIVE   = "#395886"        # navy button active state
 
 
# ─────────────────────────────────────────────────────────────────────────────
# Helpers — Bluetooth
# ─────────────────────────────────────────────────────────────────────────────
 
def _get_bluetooth_devices():
    """
    Return list of dicts:
        { 'name': str, 'port': str, 'desc': str }
    Combines Windows registry scan + pyserial description filter.
    """
    devices = {}   # port -> { name, desc }
 
    # ── 1. Registry ──────────────────────────────────────────────────────────
    if WINREG_AVAILABLE:
        for reg_path in (r"SYSTEM\CurrentControlSet\Enum\BTHENUM",
                         r"SYSTEM\CurrentControlSet\Services\BTHMODEM"):
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        sub = winreg.OpenKey(key, winreg.EnumKey(key, i))
                        for j in range(winreg.QueryInfoKey(sub)[0]):
                            try:
                                leaf = winreg.OpenKey(sub, winreg.EnumKey(sub, j))
                                try:
                                    friendly, _ = winreg.QueryValueEx(leaf, "FriendlyName")
                                    params      = winreg.OpenKey(leaf, r"Device Parameters")
                                    port_name, _ = winreg.QueryValueEx(params, "PortName")
                                    if port_name not in devices:
                                        devices[port_name] = {
                                            "name": friendly,
                                            "port": port_name,
                                            "desc": "Bluetooth Serial Port"
                                        }
                                except (FileNotFoundError, OSError):
                                    pass
                            except OSError:
                                pass
                    except OSError:
                        pass
            except OSError:
                pass
 
    # ── 2. pyserial filter ───────────────────────────────────────────────────
    if list_ports is not None:
        try:
            for p in list_ports.comports():
                d = (p.description or "").lower()
                h = (p.hwid       or "").lower()
                if any(kw in d or kw in h
                       for kw in ("bluetooth", "bth", "rfcomm",
                                  "standard serial over bluetooth")):
                    if p.device not in devices:
                        devices[p.device] = {
                            "name": p.description or "Bluetooth Serial",
                            "port": p.device,
                            "desc": p.description or "Bluetooth Serial Port",
                        }
                    else:
                        # Enrich description if registry gave us only FriendlyName
                        if devices[p.device]["desc"] == "Bluetooth Serial Port" and p.description:
                            devices[p.device]["desc"] = p.description
        except Exception:
            pass
 
    return list(devices.values())
 
 
# ─────────────────────────────────────────────────────────────────────────────
# Helpers — WiFi scan  (Windows  netsh  /  Linux  nmcli)
# ─────────────────────────────────────────────────────────────────────────────
 
def _scan_wifi_networks():
    """
    Return list of dicts:
        { 'ssid': str, 'signal': int (0-100), 'security': str, 'bssid': str }
    Works on Windows (netsh) and Linux (nmcli).  Returns [] on failure.
    """
    networks = []
    try:
        import platform
        if platform.system() == "Windows":
            networks = _scan_wifi_windows()
        else:
            networks = _scan_wifi_linux()
    except Exception:
        pass
    # De-duplicate by SSID, keep strongest signal
    seen = {}
    for n in networks:
        ssid = n["ssid"]
        if ssid and (ssid not in seen or n["signal"] > seen[ssid]["signal"]):
            seen[ssid] = n
    return sorted(seen.values(), key=lambda x: -x["signal"])
 
 
def _scan_wifi_windows():
    out = subprocess.check_output(
        ["netsh", "wlan", "show", "networks", "mode=bssid"],
        stderr=subprocess.DEVNULL,
        timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    ).decode("utf-8", errors="replace")
 
    networks = []
    current  = {}
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("SSID") and "BSSID" not in line:
            if current.get("ssid"):
                networks.append(current)
            val = line.split(":", 1)[-1].strip()
            current = {"ssid": val, "signal": 0, "security": "Unknown", "bssid": ""}
        elif "BSSID" in line:
            current["bssid"] = line.split(":", 1)[-1].strip()
        elif "Signal" in line:
            try:
                current["signal"] = int(line.split(":", 1)[-1].strip().replace("%", ""))
            except ValueError:
                pass
        elif "Authentication" in line:
            current["security"] = line.split(":", 1)[-1].strip()
    if current.get("ssid"):
        networks.append(current)
    return networks
 
 
def _scan_wifi_linux():
    out = subprocess.check_output(
        ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,BSSID", "dev", "wifi", "list"],
        stderr=subprocess.DEVNULL,
        timeout=10,
    ).decode("utf-8", errors="replace")
 
    networks = []
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 3:
            networks.append({
                "ssid":     parts[0],
                "signal":   int(parts[1]) if parts[1].isdigit() else 0,
                "security": parts[2] or "Open",
                "bssid":    parts[3] if len(parts) > 3 else "",
            })
    return networks
 
 
def _signal_bars(signal: int) -> str:
    """Return a unicode bar indicator for signal strength 0-100."""
    if signal >= 80: return "████"
    if signal >= 60: return "███░"
    if signal >= 40: return "██░░"
    if signal >= 20: return "█░░░"
    return "░░░░"
 
 
# ─────────────────────────────────────────────────────────────────────────────
# ConnectPanel
# ─────────────────────────────────────────────────────────────────────────────
 
class ConnectPanel:
    """
    Floating CTkToplevel with three tabs: Serial | Bluetooth | WiFi.
 
    Parameters
    ----------
    master            : root CTk window
    on_connected      : callable(conn, mode, description)
    on_disconnected   : callable()
    heartbeat_timeout : int seconds
    """
 
    def __init__(self, master, *,
                 on_connected=None,
                 on_disconnected=None,
                 heartbeat_timeout: int = 5):
        self.master            = master
        self.on_connected      = on_connected
        self.on_disconnected   = on_disconnected
        self.heartbeat_timeout = heartbeat_timeout
 
        # Connection state
        self.serial_conn       = None
        self._port_display_map = {}
        self._port_desc_map    = {}
        self._bt_devices       = []          # list of dicts from _get_bluetooth_devices()
        self._bt_selected_idx  = None
        self._wifi_networks    = []          # list of dicts from _scan_wifi_networks()
        self._wifi_selected_idx = None
        self.last_heartbeat    = None
        self._heartbeat_thread = None
        self._mavlink_thread   = None
 
        self._window  = None
        self._visible = False
 
    # ── Public ───────────────────────────────────────────────────────────────
 
    def toggle(self, anchor_widget=None):
        if self._visible:
            self._hide()
        else:
            self._show(anchor_widget)
 
    def is_connected(self) -> bool:
        if self.serial_conn:
            v = getattr(self.serial_conn, "is_open", None)
            return v if v is not None else True
        return False
 
    def disconnect(self):
        self._disconnect_all()
 
    # ── Window lifecycle ──────────────────────────────────────────────────────
 
    def _show(self, anchor_widget=None):
        if self._window is None or not self._window.winfo_exists():
            self._build_window()
        if anchor_widget is not None:
            try:
                ax = anchor_widget.winfo_rootx()
                ay = anchor_widget.winfo_rooty() + anchor_widget.winfo_height() + 4
                self._window.geometry(f"+{ax}+{ay}")
            except Exception:
                pass
        self._window.deiconify()
        self._window.lift()
        self._window.focus_force()
        self._visible = True
 
    def _hide(self):
        if self._window and self._window.winfo_exists():
            self._window.withdraw()
        self._visible = False
 
    def _on_close(self):
        self._hide()
 
    # ── Build window ──────────────────────────────────────────────────────────
 
    def _build_window(self):
        win = ctk.CTkToplevel(self.master)
        win.title("Connection Settings")
        win.geometry("500x420")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.protocol("WM_DELETE_WINDOW", self._on_close)
        win.configure(fg_color=BG_PANEL)
        self._window = win
 
        # Header
        header = ctk.CTkFrame(win, fg_color="#395886", corner_radius=0, height=40)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(
            header, text="CONNECTION SETTINGS",
            font=ctk.CTkFont("Times New Roman", 13, weight="bold"),
            text_color=TEXT_MAIN
        ).pack(side="left", padx=14, pady=8)
        ctk.CTkButton(
            header, text="✕", width=30, height=26,
            fg_color="transparent", hover_color="#2a0a0a",
            text_color=ACCENT_RED, font=ctk.CTkFont(size=13),
            command=self._on_close
        ).pack(side="right", padx=8)
 
        # Status
        self.status_label = ctk.CTkLabel(
            win, text="● Not connected",
            font=ctk.CTkFont("Times New Roman", 11),
            text_color=TEXT_SUB, anchor="w"
        )
        self.status_label.pack(fill="x", padx=14, pady=(6, 2))
 
        # Tabs
        self.tabview = ctk.CTkTabview(
            win,
            fg_color=BG_CARD,
            segmented_button_fg_color="#2C4468",
            segmented_button_selected_color="#395886",
            segmented_button_selected_hover_color="#3E6196",
            segmented_button_unselected_color="#243E64",
            segmented_button_unselected_hover_color="#1A2744",
            text_color=TEXT_MAIN,
            border_color=BORDER_CLR,
            border_width=1,
            corner_radius=10,
        )
        self.tabview.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.tabview.add(MODE_SERIAL)
        self.tabview.add(MODE_BLUETOOTH)
        self.tabview.add(MODE_WIFI)
 
        self._build_serial_tab(self.tabview.tab(MODE_SERIAL))
        self._build_bluetooth_tab(self.tabview.tab(MODE_BLUETOOTH))
        self._build_wifi_tab(self.tabview.tab(MODE_WIFI))
 
        # Connect button
        self.connect_btn = ctk.CTkButton(
            win, text="CONNECT", height=36,
            font=ctk.CTkFont("Times New Roman", 13, weight="bold"),
            fg_color="#395886", hover_color="#628ECB", text_color=TEXT_MAIN,
            border_width=1, border_color=BORDER_CLR,
            corner_radius=8, command=self._on_connect_click,
        )
        self.connect_btn.pack(fill="x", padx=14, pady=(0, 12))
        self._refresh_connect_btn()
 
    # ── Serial tab ────────────────────────────────────────────────────────────
 
    def _build_serial_tab(self, parent):
        parent.columnconfigure(1, weight=1)
 
        self._lbl(parent, "COM Port").grid(
            row=0, column=0, sticky="w", padx=(10, 6), pady=(14, 6))
 
        pv = self._scan_serial_ports()
        self.com_port_combo = ctk.CTkComboBox(
            parent, values=pv, width=230, height=30,
            fg_color=BG_INNER, border_color=BORDER_CLR, button_color="#395886",
            text_color=TEXT_MAIN, dropdown_fg_color=BG_INNER,
            dropdown_text_color=TEXT_MAIN, dropdown_hover_color=BG_ROW_SEL,
            command=self._on_port_selected,
        )
        self.com_port_combo.set(pv[0] if pv else "No ports")
        self.com_port_combo.grid(row=0, column=1, sticky="ew", padx=(0, 6), pady=(14, 6))
 
        ctk.CTkButton(
            parent, text="↻", width=34, height=30,
            fg_color=BG_INNER, hover_color="#395886", text_color=TEXT_MAIN,
            font=ctk.CTkFont(size=15),
            command=self.refresh_com_ports
        ).grid(row=0, column=2, pady=(14, 6))
 
        self._lbl(parent, "Baud Rate").grid(
            row=1, column=0, sticky="w", padx=(10, 6), pady=6)
        self.baud_combo = ctk.CTkComboBox(
            parent, values=["9600", "19200", "38400", "57600", "115200", "921600"],
            width=140, height=30,
            fg_color=BG_INNER, border_color=BORDER_CLR, button_color="#395886",
            text_color=TEXT_MAIN, dropdown_fg_color=BG_INNER,
            dropdown_text_color=TEXT_MAIN, dropdown_hover_color=BG_ROW_SEL,
        )
        self.baud_combo.set("57600")
        self.baud_combo.grid(row=1, column=1, sticky="w", pady=6)
 
        self.serial_desc_label = ctk.CTkLabel(
            parent, text="—",
            font=ctk.CTkFont("Times New Roman", 10), text_color=TEXT_SUB, anchor="w"
        )
        self.serial_desc_label.grid(
            row=2, column=0, columnspan=3, sticky="w", padx=10, pady=(2, 10))
 
    # ── Bluetooth tab — rich card list ────────────────────────────────────────
 
    def _build_bluetooth_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
 
        # Toolbar row
        tb = ctk.CTkFrame(parent, fg_color="transparent")
        tb.grid(row=0, column=0, sticky="ew", padx=8, pady=(10, 4))
 
        ctk.CTkButton(
            tb, text="⟳  SCAN", width=90, height=28,
            fg_color="#0c1a28", hover_color=BG_ROW_SEL, text_color=TEXT_MAIN,
            font=ctk.CTkFont("Times New Roman", 11, weight="bold"),
            command=self._scan_bluetooth_devices
        ).pack(side="left", padx=(0, 8))
 
        self._lbl(tb, "Baud:").pack(side="left", padx=(0, 4))
        self.bt_baud_combo = ctk.CTkComboBox(
            tb, values=["9600", "19200", "38400", "57600", "115200"],
            width=110, height=28,
            fg_color=BG_INNER, border_color=BORDER_CLR, button_color="#0c1a28",
            text_color=TEXT_MAIN, dropdown_fg_color=BG_INNER,
            dropdown_text_color=TEXT_MAIN, dropdown_hover_color=BG_ROW_SEL,
        )
        self.bt_baud_combo.set("57600")
        self.bt_baud_combo.pack(side="left")
 
        ctk.CTkButton(
            tb, text="＋ Pair", width=70, height=28,
            fg_color="transparent", border_width=1,
            border_color=BORDER_CLR, text_color=TEXT_SUB,
            hover_color=BG_INNER,
            command=lambda: subprocess.Popen(
                ["explorer", "ms-settings:bluetooth"], shell=True)
        ).pack(side="right")
 
        # Scrollable device list
        self.bt_scroll = ctk.CTkScrollableFrame(
            parent, fg_color="#080d1a", corner_radius=8,
            border_color=BORDER_CLR, border_width=1,
        )
        self.bt_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.bt_scroll.columnconfigure(0, weight=1)
 
        self._bt_placeholder = ctk.CTkLabel(
            self.bt_scroll,
            text="Click  ⟳ SCAN  to discover paired Bluetooth devices",
            font=ctk.CTkFont("Times New Roman", 11), text_color=TEXT_SUB
        )
        self._bt_placeholder.pack(pady=20)
 
        self._bt_row_frames = []   # list of CTkFrame cards
 
    def _scan_bluetooth_devices(self):
        self._set_status("Scanning for paired Bluetooth COM ports…", ACCENT_WARN)
        self._clear_bt_list()
        self._bt_placeholder.configure(text="Scanning…", text_color=ACCENT_WARN)
        self._bt_placeholder.pack(pady=20)
 
        def _do():
            devs = _get_bluetooth_devices()
            self.master.after(0, lambda: self._populate_bt_list(devs))
 
        threading.Thread(target=_do, daemon=True).start()
 
    def _clear_bt_list(self):
        for f in self._bt_row_frames:
            f.destroy()
        self._bt_row_frames = []
        self._bt_devices      = []
        self._bt_selected_idx = None
 
    def _populate_bt_list(self, devices):
        self._bt_placeholder.pack_forget()
        self._clear_bt_list()
        self._bt_devices = devices
 
        if not devices:
            self._bt_placeholder.configure(
                text="No paired Bluetooth COM ports found.\nPair your device in Windows Settings first.",
                text_color=ACCENT_RED
            )
            self._bt_placeholder.pack(pady=20)
            self._set_status("No Bluetooth COM ports found", ACCENT_RED)
            return
 
        for idx, dev in enumerate(devices):
            self._make_bt_card(idx, dev)
 
        self._set_status(
            f"Found {len(devices)} Bluetooth device(s) — select one and click CONNECT",
            ACCENT
        )
 
    def _make_bt_card(self, idx, dev):
        card = ctk.CTkFrame(
            self.bt_scroll,
            fg_color=BG_CARD, corner_radius=6,
            border_color=BORDER_CLR, border_width=1,
        )
        card.pack(fill="x", padx=4, pady=3)
        card.columnconfigure(1, weight=1)
 
        # BT icon
        ctk.CTkLabel(
            card, text="⬡", font=ctk.CTkFont(size=22), text_color=TEXT_SUB, width=34
        ).grid(row=0, column=0, rowspan=2, padx=(10, 6), pady=8)
 
        # Name (bold-ish)
        ctk.CTkLabel(
            card, text=dev["name"],
            font=ctk.CTkFont("Times New Roman", 12, weight="bold"),
            text_color=TEXT_MAIN, anchor="w"
        ).grid(row=0, column=1, sticky="w", pady=(8, 0))
 
        # COM port + description
        detail = f"{dev['port']}  ·  {dev['desc']}"
        ctk.CTkLabel(
            card, text=detail,
            font=ctk.CTkFont("Times New Roman", 10),
            text_color=TEXT_SUB, anchor="w"
        ).grid(row=1, column=1, sticky="w", pady=(0, 8))
 
        # Select radio-style button
        sel_btn = ctk.CTkButton(
            card, text="SELECT", width=72, height=26,
            fg_color=BG_INNER, hover_color=BG_ROW_SEL,
            text_color=TEXT_MAIN, font=ctk.CTkFont("Times New Roman", 10, weight="bold"),
            border_width=1, border_color=BORDER_CLR,
            command=lambda i=idx: self._select_bt_device(i)
        )
        sel_btn.grid(row=0, column=2, rowspan=2, padx=10)
 
        card._sel_btn = sel_btn
        self._bt_row_frames.append(card)
 
    def _select_bt_device(self, idx):
        self._bt_selected_idx = idx
        for i, card in enumerate(self._bt_row_frames):
            if i == idx:
                card.configure(fg_color=BG_ROW_SEL, border_color="#3a5aaa")
                card._sel_btn.configure(text="✔ SELECTED",
                                        fg_color="#050677", text_color=TEXT_MAIN,
                                        border_color="#3a5aaa")
            else:
                card.configure(fg_color=BG_CARD, border_color=BORDER_CLR)
                card._sel_btn.configure(text="SELECT",
                                        fg_color=BG_INNER, text_color=TEXT_MAIN,
                                        border_color=BORDER_CLR)
 
    # ── WiFi tab — scan + pick ─────────────────────────────────────────────────
 
    def _build_wifi_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
 
        # Toolbar
        tb = ctk.CTkFrame(parent, fg_color="transparent")
        tb.grid(row=0, column=0, sticky="ew", padx=8, pady=(10, 4))
 
        ctk.CTkButton(
            tb, text="⟳  SCAN", width=90, height=28,
            fg_color="#0c1a4e", hover_color=BG_ROW_SEL, text_color=TEXT_MAIN,
            font=ctk.CTkFont("Times New Roman", 11, weight="bold"),
            command=self._scan_wifi
        ).pack(side="left", padx=(0, 8))
 
        self._lbl(tb, "Port:").pack(side="left", padx=(0, 4))
        self.wifi_port_entry = ctk.CTkEntry(
            tb, width=70, height=28, placeholder_text="14550",
            fg_color=BG_INNER, border_color=BORDER_CLR,
            text_color=TEXT_MAIN, placeholder_text_color=TEXT_SUB,
        )
        self.wifi_port_entry.pack(side="left", padx=(0, 10))
 
        self._lbl(tb, "Password:").pack(side="left", padx=(0, 4))
        self.wifi_pass_entry = ctk.CTkEntry(
            tb, width=110, height=28, placeholder_text="(if required)",
            fg_color=BG_INNER, border_color=BORDER_CLR, show="*",
            text_color=TEXT_MAIN, placeholder_text_color=TEXT_SUB,
        )
        self.wifi_pass_entry.pack(side="left")
 
        # Scrollable network list
        self.wifi_scroll = ctk.CTkScrollableFrame(
            parent, fg_color="#080d1a", corner_radius=8,
            border_color=BORDER_CLR, border_width=1,
        )
        self.wifi_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.wifi_scroll.columnconfigure(0, weight=1)
 
        self._wifi_placeholder = ctk.CTkLabel(
            self.wifi_scroll,
            text="Click  ⟳ SCAN  to discover nearby Wi-Fi networks",
            font=ctk.CTkFont("Times New Roman", 11), text_color=TEXT_SUB
        )
        self._wifi_placeholder.pack(pady=20)
 
        self._wifi_row_frames = []
 
    def _scan_wifi(self):
        self._set_status("Scanning for Wi-Fi networks…", ACCENT_WARN)
        self._clear_wifi_list()
        self._wifi_placeholder.configure(text="Scanning…", text_color=ACCENT_WARN)
        self._wifi_placeholder.pack(pady=20)
 
        def _do():
            nets = _scan_wifi_networks()
            self.master.after(0, lambda: self._populate_wifi_list(nets))
 
        threading.Thread(target=_do, daemon=True).start()
 
    def _clear_wifi_list(self):
        for f in self._wifi_row_frames:
            f.destroy()
        self._wifi_row_frames    = []
        self._wifi_networks      = []
        self._wifi_selected_idx  = None
 
    def _populate_wifi_list(self, networks):
        self._wifi_placeholder.pack_forget()
        self._clear_wifi_list()
        self._wifi_networks = networks
 
        if not networks:
            self._wifi_placeholder.configure(
                text="No Wi-Fi networks found.\nEnsure the Wi-Fi adapter is enabled.",
                text_color=ACCENT_RED
            )
            self._wifi_placeholder.pack(pady=20)
            self._set_status("No Wi-Fi networks found", ACCENT_RED)
            return
 
        for idx, net in enumerate(networks):
            self._make_wifi_card(idx, net)
 
        self._set_status(
            f"Found {len(networks)} network(s) — select one, enter port/password, then CONNECT",
            ACCENT
        )
 
    def _make_wifi_card(self, idx, net):
        card = ctk.CTkFrame(
            self.wifi_scroll,
            fg_color=BG_CARD, corner_radius=6,
            border_color=BORDER_CLR, border_width=1,
        )
        card.pack(fill="x", padx=4, pady=3)
        card.columnconfigure(1, weight=1)
 
        # Signal icon
        bars = _signal_bars(net["signal"])
        sig_color = (ACCENT_GREEN if net["signal"] >= 60
                     else ACCENT_WARN if net["signal"] >= 30
                     else ACCENT_RED)
        ctk.CTkLabel(
            card, text=bars,
            font=ctk.CTkFont("Times New Roman", 13), text_color=sig_color, width=50
        ).grid(row=0, column=0, rowspan=2, padx=(8, 4), pady=8)
 
        # SSID
        ctk.CTkLabel(
            card, text=net["ssid"] or "(Hidden network)",
            font=ctk.CTkFont("Times New Roman", 12, weight="bold"),
            text_color=TEXT_MAIN, anchor="w"
        ).grid(row=0, column=1, sticky="w", pady=(8, 0))
 
        # Signal % + security
        detail = f"{net['signal']}%  ·  {net['security']}"
        if net.get("bssid"):
            detail += f"  ·  {net['bssid']}"
        ctk.CTkLabel(
            card, text=detail,
            font=ctk.CTkFont("Times New Roman", 10),
            text_color=TEXT_SUB, anchor="w"
        ).grid(row=1, column=1, sticky="w", pady=(0, 8))
 
        # Lock icon for secured networks
        lock = "🔒" if net["security"] not in ("Open", "None", "", "Unknown") else "🔓"
        ctk.CTkLabel(
            card, text=lock, font=ctk.CTkFont(size=14), width=24
        ).grid(row=0, column=2, rowspan=2, padx=(0, 4))
 
        # Select button
        sel_btn = ctk.CTkButton(
            card, text="SELECT", width=72, height=26,
            fg_color=BG_INNER, hover_color=BG_ROW_SEL,
            text_color=TEXT_MAIN, font=ctk.CTkFont("Times New Roman", 10, weight="bold"),
            border_width=1, border_color=BORDER_CLR,
            command=lambda i=idx: self._select_wifi_network(i)
        )
        sel_btn.grid(row=0, column=3, rowspan=2, padx=10)
 
        card._sel_btn = sel_btn
        self._wifi_row_frames.append(card)
 
    def _select_wifi_network(self, idx):
        self._wifi_selected_idx = idx
        for i, card in enumerate(self._wifi_row_frames):
            if i == idx:
                card.configure(fg_color=BG_ROW_SEL, border_color="#3a5aaa")
                card._sel_btn.configure(text="✔ SELECTED",
                                        fg_color="#050677", text_color=TEXT_MAIN,
                                        border_color="#3a5aaa")
            else:
                card.configure(fg_color=BG_CARD, border_color=BORDER_CLR)
                card._sel_btn.configure(text="SELECT",
                                        fg_color=BG_INNER, text_color=TEXT_MAIN,
                                        border_color=BORDER_CLR)
 
    # ── Shared helpers ────────────────────────────────────────────────────────
 
    @staticmethod
    def _lbl(parent, text, color=TEXT_MAIN):
        return ctk.CTkLabel(
            parent, text=text,
            font=ctk.CTkFont("Times New Roman", 11), text_color=color
        )
 
    def _refresh_connect_btn(self):
        if self._window is None or not self._window.winfo_exists():
            return
        if self.is_connected():
            self.connect_btn.configure(
                text="DISCONNECT",
                fg_color="#3a0a0a", hover_color="#5a1010",
                text_color=ACCENT_RED, border_color="#5a1010"
            )
        else:
            self.connect_btn.configure(
                text="CONNECT",
                fg_color="#0c1a4e", hover_color="#1a2e6e",
                text_color=TEXT_MAIN, border_color=BORDER_CLR
            )
 
    def _set_status(self, text, color=ACCENT):
        if self._window and self._window.winfo_exists():
            self.status_label.configure(text=f"● {text}", text_color=color)
 
    # ── Serial helpers ────────────────────────────────────────────────────────
 
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
            display = f"{p.device} — {desc}"
            values.append(display)
            self._port_display_map[display] = p.device
            self._port_desc_map[display]    = desc
        return values if values else ["No ports"]
 
    def refresh_com_ports(self, preserve_selection=True):
        pv       = self._scan_serial_ports()
        selected = self.com_port_combo.get()
        self.com_port_combo.configure(values=pv)
        if preserve_selection and selected in pv:
            self.com_port_combo.set(selected)
        elif pv and pv[0] != "No ports":
            self.com_port_combo.set(pv[0])
        else:
            self.com_port_combo.set("No ports")
        self._on_port_selected(self.com_port_combo.get())
 
    def _on_port_selected(self, selected_display):
        if not hasattr(self, "serial_desc_label"):
            return
        if not selected_display or selected_display == "No ports":
            self.serial_desc_label.configure(text="No port selected", text_color=TEXT_SUB)
            return
        desc   = self._port_desc_map.get(selected_display, "")
        device = self._port_display_map.get(selected_display, selected_display)
        if desc and desc != "Unknown device":
            self.serial_desc_label.configure(text=f"{desc}  ·  {device}", text_color=TEXT_MAIN)
        else:
            self.serial_desc_label.configure(text=f"{device} — no description", text_color=TEXT_SUB)
 
    # ── Connect / Disconnect ──────────────────────────────────────────────────
 
    def _on_connect_click(self):
        if self.is_connected():
            self._disconnect_all()
            return
        mode = self.tabview.get()
        if   mode == MODE_SERIAL:    self._connect_serial()
        elif mode == MODE_BLUETOOTH: self._connect_bluetooth()
        elif mode == MODE_WIFI:      self._connect_wifi()
 
    # ── Connecting dialog (progress bar popup) ──────────────────────

    def _show_connecting_dialog(self, cancel_event):
        """
        Show a 'Connecting Mavlink' modal dialog with an indeterminate progress
        bar.  cancel_event is a threading.Event; setting it signals abort.
        Returns the CTkToplevel so the caller can destroy it when done.
        """
        dlg = ctk.CTkToplevel(self.master)
        dlg.title("Connecting Mavlink")
        dlg.geometry("320x130")
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.configure(fg_color=BG_PANEL)
        dlg.grab_set()

        ctk.CTkLabel(
            dlg, text="Connecting Mavlink",
            font=ctk.CTkFont("Times New Roman", 12, weight="bold"),
            text_color=TEXT_MAIN, anchor="w"
        ).pack(fill="x", padx=14, pady=(12, 2))

        ctk.CTkLabel(
            dlg, text="Mavlink Connecting...",
            font=ctk.CTkFont("Times New Roman", 11),
            text_color=TEXT_SUB, anchor="w"
        ).pack(fill="x", padx=14, pady=(0, 6))

        import tkinter.ttk as ttk
        style = ttk.Style(dlg)
        style.theme_use("default")
        style.configure(
            "Mav.Horizontal.TProgressbar",
            troughcolor="#1a1a2e",
            background=ACCENT_GREEN,
            thickness=14,
        )
        pb = ttk.Progressbar(
            dlg, style="Mav.Horizontal.TProgressbar",
            orient="horizontal", mode="indeterminate", length=290
        )
        pb.pack(padx=14, pady=(0, 8))
        pb.start(12)

        def _cancel():
            cancel_event.set()
            try:
                dlg.destroy()
            except Exception:
                pass

        ctk.CTkButton(
            dlg, text="Cancel", width=80, height=26,
            fg_color="#395886", hover_color="#628ECB", text_color=TEXT_MAIN,
            font=ctk.CTkFont("Times New Roman", 11),
            command=_cancel
        ).pack(anchor="e", padx=14, pady=(0, 10))

        return dlg

    def _show_heartbeat_received(self, description: str):
        """
        Show a 'Heartbeat Received' success popup that auto-closes after 2.5 s.
        """
        dlg = ctk.CTkToplevel(self.master)
        dlg.title("Heartbeat Received")
        dlg.geometry("300x120")
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.configure(fg_color=BG_PANEL)
        dlg.grab_set()

        header = ctk.CTkFrame(dlg, fg_color=ACCENT_GREEN, corner_radius=0, height=36)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(
            header, text="✔  Heartbeat Received",
            font=ctk.CTkFont("Times New Roman", 12, weight="bold"),
            text_color="#ffffff"
        ).pack(side="left", padx=12, pady=6)

        ctk.CTkLabel(
            dlg, text="MAVLink connection established successfully.",
            font=ctk.CTkFont("Times New Roman", 11),
            text_color=TEXT_SUB, anchor="w", wraplength=270
        ).pack(fill="x", padx=14, pady=(10, 4))

        ctk.CTkLabel(
            dlg, text=description,
            font=ctk.CTkFont("Times New Roman", 10),
            text_color=ACCENT_GREEN, anchor="w", wraplength=270
        ).pack(fill="x", padx=14)

        dlg.after(2500, lambda: dlg.destroy() if dlg.winfo_exists() else None)

    # ── Threaded connect helpers ─────────────────────────────────

    def _run_in_thread(self, worker_fn):
        """
        Run worker_fn(cancel_event) in a background thread.
        worker_fn must return (conn, description) on success or raise on failure.
        Shows the Connecting dialog while waiting, Heartbeat popup on success.
        """
        import threading as _threading
        cancel_event = _threading.Event()
        dlg = self._show_connecting_dialog(cancel_event)
        result_holder = {}

        def worker():
            try:
                conn, desc = worker_fn(cancel_event)
                result_holder["conn"] = conn
                result_holder["desc"] = desc
            except Exception as exc:
                result_holder["error"] = exc

        def poll():
            if not dlg.winfo_exists():
                return
            if t.is_alive():
                dlg.after(100, poll)
                return
            try:
                dlg.destroy()
            except Exception:
                pass
            if cancel_event.is_set():
                return
            if "error" in result_holder:
                messagebox.showerror("Connection Failed", str(result_holder["error"]))
            else:
                self.serial_conn    = result_holder["conn"]
                self.last_heartbeat = time.time()
                self._start_heartbeat_monitor()
                desc = result_holder["desc"]
                self._post_connect(desc)
                self._show_heartbeat_received(desc)

        t = _threading.Thread(target=worker, daemon=True)
        t.start()
        dlg.after(100, poll)

    def _connect_serial(self):
        if serial is None:
            messagebox.showerror("Serial Error", "pyserial is not installed.")
            return
        self.refresh_com_ports(preserve_selection=True)
        selected = self.com_port_combo.get()
        if not selected or selected == "No ports":
            messagebox.showwarning("No Port", "No COM port selected or available.")
            return
        try:
            baud_int = int(self.baud_combo.get())
        except ValueError:
            baud_int = 57600
        port = self._port_display_map.get(selected, selected)
        desc_label = self._port_desc_map.get(selected, "")

        if mavutil is not None:
            def worker(cancel_event):
                conn = mavutil.mavlink_connection(port, baud=baud_int)
                conn.wait_heartbeat(timeout=self.heartbeat_timeout)
                return conn, f"Serial \u2192 {desc_label} ({port})"
            self._run_in_thread(worker)
        else:
            try:
                self.serial_conn = serial.Serial(port, baudrate=baud_int, timeout=1)
                self._post_connect(f"Serial \u2192 {desc_label} ({port})")
            except Exception as e:
                messagebox.showerror("Connection Failed", f"Failed to open {port}:\n{e}")
                self.serial_conn = None

    def _connect_bluetooth(self):
        if self._bt_selected_idx is None or not self._bt_devices:
            messagebox.showwarning(
                "No Device Selected",
                "Please SCAN and select a Bluetooth device first."
            )
            return
        dev = self._bt_devices[self._bt_selected_idx]
        device_path = dev["port"]
        try:
            baud_int = int(self.bt_baud_combo.get())
        except ValueError:
            baud_int = 57600

        if mavutil is not None:
            def worker(cancel_event):
                conn = mavutil.mavlink_connection(device_path, baud=baud_int)
                conn.wait_heartbeat(timeout=self.heartbeat_timeout)
                return conn, f"Bluetooth \u2192 {dev['name']} ({device_path})"
            self._run_in_thread(worker)
        else:
            try:
                self.serial_conn = serial.Serial(device_path, baudrate=baud_int, timeout=1)
                self._post_connect(f"Bluetooth \u2192 {dev['name']} ({device_path})")
            except Exception as e:
                messagebox.showerror("Bluetooth Failed", str(e))
                self.serial_conn = None

    def _connect_wifi(self):
        if self._wifi_selected_idx is None or not self._wifi_networks:
            messagebox.showwarning(
                "No Network Selected",
                "Please SCAN and select a Wi-Fi network first."
            )
            return
        net = self._wifi_networks[self._wifi_selected_idx]
        ssid = net["ssid"]

        port_text = self.wifi_port_entry.get().strip()
        try:
            port_num = int(port_text) if port_text else 14550
        except ValueError:
            messagebox.showwarning("Invalid Port", "Please enter a valid port number.")
            return

        try:
            gateway_ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            gateway_ip = "192.168.1.1"

        if mavutil is not None:
            def worker(cancel_event):
                conn_str = f"tcp:{gateway_ip}:{port_num}"
                conn = mavutil.mavlink_connection(conn_str)
                conn.wait_heartbeat(timeout=self.heartbeat_timeout)
                return conn, f"WiFi TCP \u2192 {ssid}  {gateway_ip}:{port_num}"
            self._run_in_thread(worker)
        else:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((gateway_ip, port_num))
                self.serial_conn = sock
                self._post_connect(f"WiFi TCP \u2192 {ssid}  {gateway_ip}:{port_num}")
            except Exception as e:
                messagebox.showerror("WiFi Connection Failed", str(e))
                self.serial_conn = None

    def _post_connect(self, description: str):
        self._set_status(f"Connected  \u00b7  {description}", ACCENT_GREEN)
        self._refresh_connect_btn()
        if self.on_connected:
            self.on_connected(self.serial_conn, self.tabview.get(), description)
 
    def _disconnect_all(self):
        if self.serial_conn:
            try:
                self.serial_conn.close()
            except Exception:
                pass
            self.serial_conn = None
        self.last_heartbeat    = None
        self._heartbeat_thread = None
        self._mavlink_thread   = None
        self._set_status("Disconnected", "gray")
        self._refresh_connect_btn()
        if self.on_disconnected:
            self.on_disconnected()
 
    # ── Heartbeat / MAVLink threads ───────────────────────────────────────────
 
    def _start_heartbeat_monitor(self):
        if mavutil is None or self.serial_conn is None:
            return
        if self._mavlink_thread is None or not self._mavlink_thread.is_alive():
            self._mavlink_thread = threading.Thread(
                target=self._mavlink_receive_loop, daemon=True)
            self._mavlink_thread.start()
        if self._heartbeat_thread is None or not self._heartbeat_thread.is_alive():
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_watchdog, daemon=True)
            self._heartbeat_thread.start()
 
    def _mavlink_receive_loop(self):
        while self.is_connected():
            try:
                msg = self.serial_conn.recv_match(blocking=True, timeout=1)
                if msg and msg.get_type() == "HEARTBEAT":
                    self.last_heartbeat = time.time()
            except Exception:
                time.sleep(0.1)

    def _refresh_cached_heartbeat_time(self):
        if self.serial_conn is None:
            return
        try:
            heartbeat = getattr(self.serial_conn, "messages", {}).get("HEARTBEAT")
            timestamp = getattr(heartbeat, "_timestamp", None)
            if timestamp and (self.last_heartbeat is None or timestamp > self.last_heartbeat):
                self.last_heartbeat = timestamp
        except Exception:
            pass
 
    def _heartbeat_watchdog(self):
        while self.is_connected():
            self._refresh_cached_heartbeat_time()
            if (self.last_heartbeat is not None and
                    (time.time() - self.last_heartbeat) > self.heartbeat_timeout):
                self.master.after(0, lambda: messagebox.showwarning(
                    "Heartbeat Timeout",
                    "No heartbeat received within timeout. Disconnecting."
                ))
                self.master.after(0, self._disconnect_all)
                break
            time.sleep(1)
