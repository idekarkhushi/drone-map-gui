import customtkinter as ctk
from PIL import Image, ImageEnhance

from Calibration.calibration_gui import (
    CalibrationPanel, POSITION_LABELS, RC_CHANNEL_NAMES, MAG_STATUS_COLORS
)
from Calibration.backend import DroneBackend
from Motortest import MotorTestPanel
from failsafe import FailsafePanel
from CAN_GPSOrder import CANGPSOrderPanel

class SetupPage(ctk.CTkFrame):

    BG         = "#0d1117"
    SIDEBAR_BG = "#161b22"
    CARD_BG    = "#21262d"
    ACCENT     = "#1f6feb"
    ACCENT_HVR = "#388bfd"
    BORDER     = "#30363d"
    TXT_PRI    = "#e6edf3"
    TXT_SEC    = "#8b949e"

    FONT = "Times New Roman"

    def __init__(self, parent):
        super().__init__(parent, fg_color=self.BG)
 
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)   # sidebar
        self.grid_columnconfigure(1, weight=1)   # content (empty)
 
        self._calib_expanded = False
        self._mavlink_conn = None        # set by newmain via set_connection()
        self._motor_test_panel = None
        
        self._build_content_area()
        self._build_sidebar()
        self._calibration_panel = None
        self._on_motor_test()
 
    # ═══════════════════════════════════════════════════════════════════════════
    #  SIDEBAR
    # ═══════════════════════════════════════════════════════════════════════════
 
    def _build_sidebar(self):
        self._sidebar = ctk.CTkFrame(
            self,
            width=210,
            fg_color=self.SIDEBAR_BG,
            corner_radius=0,
        )
        self._sidebar.grid(row=0, column=0, sticky="nsew")
        self._sidebar.grid_propagate(False)
 
        # ── 1. >> Calibration (expandable) ────────────────────────────────────
        self._calib_btn = ctk.CTkButton(
            self._sidebar,
            text=">> Calibration",
            anchor="w",
            height=34,
            fg_color="transparent",
            hover_color="#2d333b",
            text_color=self.TXT_PRI,
            font=(self.FONT, 12, "bold"),
            corner_radius=0,
            border_width=0,
            command=self._toggle_calibration,
        )
        self._calib_btn.pack(fill="x", padx=0, pady=0)
 
        # ── 2. Submenu (packed right here, then hidden) ────────────────────────
        self._calib_submenu = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        submenu_items = [
            ("Accelerometer", self._on_accel),
            ("Compass",       self._on_compass),
            ("Radio",         self._on_rc),
        ]
        for text, cmd in submenu_items:
            ctk.CTkButton(
                self._calib_submenu,
                text=f"    {text}",
                anchor="w",
                height=30,
                fg_color="transparent",
                hover_color="#2d333b",
                text_color=self.TXT_SEC,
                font=(self.FONT, 11),
                corner_radius=0,
                border_width=0,
                command=cmd,
            ).pack(fill="x", padx=0, pady=0)
 
        # Pack submenu NOW so it sits right below calib_btn in widget order,
        # then immediately hide it — this preserves its position when shown later
        self._calib_submenu.pack(fill="x", padx=0, pady=0)
        self._calib_submenu.pack_forget()
 
        # ── 3. Remaining top-level items (appear AFTER submenu slot) ──────────
        self.backend = DroneBackend()
        self._accel_images = self._load_accel_images()
        # ── 2-5 nav buttons ─────────────────────────────────────────────────────
        buttons = [
            ("Failsafe",    self._on_failsafe),
            ("Motor Test", self._on_motor_test),
            ("CAN GPS",    self._on_can_gps),
            ("Theme",      self._on_theme),
        ]
 
        for text, command in buttons:
            ctk.CTkButton(
                self._sidebar,
                text=text,
                anchor="w",
                height=36,
                fg_color=self.CARD_BG,
                hover_color="#2d333b",
                text_color=self.TXT_PRI,
                font=(self.FONT, 12, "bold"),
                corner_radius=6,
                command=command,
            ).pack(fill="x", padx=8, pady=(0, 2))
 
            ctk.CTkFrame(self._sidebar, height=1, fg_color=self.BORDER).pack(
                fill="x", padx=10, pady=(2, 4)
            )
            
    # ═══════════════════════════════════════════════════════════════════════════
    #  CALIBRATION DROPDOWN TOGGLE
    # ═══════════════════════════════════════════════════════════════════════════
 
    def _toggle_calibration(self):
        self._calib_expanded = not self._calib_expanded
        if self._calib_expanded:
            self._calib_btn.configure(text="Calibration")
            self._calib_submenu.pack(
                fill="x",
                padx=8,
                pady=(0, 4),
                after=self._calib_btn,
            )
        else:
            self._calib_btn.configure(text="Calibration")
            self._calib_submenu.pack_forget()
 
    # ═══════════════════════════════════════════════════════════════════════════
    #  CONTENT AREA (empty)
    # ═══════════════════════════════════════════════════════════════════════════
 
    def _build_content_area(self):
        self._content = ctk.CTkFrame(self, fg_color=self.BG, corner_radius=0)
        self._content.grid(row=0, column=1, sticky="nsew")
 
    def _clear_content(self):
        for child in self._content.winfo_children():
            child.destroy()
        self._calibration_panel = None
        self._motor_test_panel = None
 
    def _show_calibration_tab(self, tab_name):
        if self._calibration_panel is None or not self._calibration_panel.winfo_exists():
            self._clear_content()
            self._calibration_panel = CalibrationPanel(self._content)
            self._calibration_panel.place(relx=0, rely=0, relwidth=1, relheight=1)
 
        self._calibration_panel.show_tab(tab_name)
 
    def _load_accel_images(self):
        image_paths = {
            1: "Calibration/assets/Level.png",
            2: "Calibration/assets/Left side.png",
            3: "Calibration/assets/Right side.png",
            4: "Calibration/assets/Nose Down.png",
            5: "Calibration/assets/Nose Up.png",
            6: "Calibration/assets/Upside Down.png",
        }
        size = (100, 80)
        result = {}
 
        for pos, path in image_paths.items():
            try:
                original = Image.open(path).convert("RGBA").resize(size)
                idle_img = ImageEnhance.Brightness(original.copy()).enhance(0.6)
                active_img = original.copy()
                done_img = original.copy()
 
                result[pos] = {
                    "idle": ctk.CTkImage(idle_img, size=size),
                    "active": ctk.CTkImage(active_img, size=size),
                    "done": ctk.CTkImage(done_img, size=size),
                }
            except FileNotFoundError:
                result[pos] = None
 
        return result
 
    # ═══════════════════════════════════════════════════════════════════════════
    #  BUTTON CALLBACKS (stubs)
    # ═══════════════════════════════════════════════════════════════════════════
 
    def _on_accel(self):
        self._show_calibration_tab("Accelerometer")
 
    def _on_compass(self):
        self._show_calibration_tab("Compass")
 
    def _on_rc(self):
        self._show_calibration_tab("RC Calibration")
    
    def set_connection(self, conn, mode=None, description=None):
        """Called by newmain when MAVLink connects."""
        self._mavlink_conn = conn
        if self._motor_test_panel is not None and self._motor_test_panel.winfo_exists():
            self._motor_test_panel.set_connection(conn)
 
    def clear_connection(self):
        """Called by newmain when MAVLink disconnects."""
        self._mavlink_conn = None
        if self._motor_test_panel is not None and self._motor_test_panel.winfo_exists():
            self._motor_test_panel.set_connection(None)
 
    def _on_failsafe(self):

        self._clear_content()

        panel = FailsafePanel(self._content)

        panel.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=10
        )
    
    def _on_motor_test(self):
        try:
            self._clear_content()
            self._motor_test_panel = MotorTestPanel(self._content)

            self._motor_test_panel.place(
                relx=0,
                rely=0,
                relwidth=1,
                relheight=1
            )

            self._motor_test_panel.set_connection(self._mavlink_conn)

        except Exception as e:
            print("ERROR:", e)
 
    def _on_can_gps(self):
        self._clear_content()
        self._can_gps_panel = CANGPSOrderPanel(self._content)
        self._can_gps_panel.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._can_gps_panel.set_connection(self._mavlink_conn)
 
    def _on_theme(self):
        pass