import os
from tkinter import font
from PIL import Image, ImageEnhance
import customtkinter as ctk
import serial.tools.list_ports

from backend import DroneBackend

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Maps ArduPilot position numbers (1-6) to display names.
POSITION_LABELS = {
    1: "Level",
    2: "Left side",
    3: "Right side",
    4: "Nose down",
    5: "Nose up",
    6: "Upside down",
}

# Standard RC channel names for the first 8 channels.
RC_CHANNEL_NAMES = {
    1: "Roll",
    2: "Pitch",
    3: "Throttle",
    4: "Yaw",
    5: "Flight Mode",
    6: "Tuning",
    7: "Aux 1",
    8: "Aux 2",
    9: "Aux 3",
    10: "Aux 4",
    11: "Aux 5",
    12: "Aux 6",
}

# Compass status colour mapping.
MAG_STATUS_COLORS = {
    "idle":    "#888888",
    "running": "#f0ad4e",
    "pass":    "#2ecc71",
    "fail":    "#e74c3c",
}


class CalibrationWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("MAVLink Calibration Interface")
        self.geometry("1080x680")
        self.minsize(900, 580)

        self.backend = DroneBackend()

        # Wire backend callbacks through self.after so Tk is never touched
        # from the background MAVLink reader thread.
        self.backend.cb_status          = lambda t, c: self.after(0, self.set_status, t, c)
        self.backend.cb_text            = lambda t:    self.after(0, self.handle_statustext, t)
        self.backend.cb_telemetry       = lambda m, b: self.after(0, self.update_telemetry, m, b)
        self.backend.cb_ack             = lambda r:    self.after(0, self.handle_ack, r)
        self.backend.cb_progress        = lambda v:    self.after(0, self.update_progress, v)
        self.backend.cb_confirm_ready   = lambda e:    self.after(0, self.set_confirm_ready, e)
        self.backend.cb_calibration_done= lambda s:    self.after(0, self.on_calibration_done, s)
        self.backend.cb_accel_done      = lambda s:    self.after(0, self.on_accel_done, s)
        self.backend.cb_accel_progress  = lambda v:    self.after(0, self.update_accel_progress, v)
        self.backend.cb_position_update = lambda p, s: self.after(0, self.update_position_indicator, p, s)
        self.backend.cb_compass_progress= lambda cid, pct: self.after(0, self.on_compass_progress, cid, pct)
        self.backend.cb_compass_done    = lambda res:  self.after(0, self.on_compass_done, res)
        self.backend.cb_compass_state   = lambda cid, s: self.after(0, self.on_compass_state_update, cid, s)
        self.backend.cb_rc_update       = lambda ch, val, lo, hi: self.after(0, self.on_rc_update, ch, val, lo, hi)
        self.backend.cb_rc_done         = lambda mn, mx, tr: self.after(0, self.on_rc_done, mn, mx, tr)
        self.backend.cb_rc_channel_state = lambda ch, s: self.after(0, self.on_rc_channel_state_update, ch, s)
        self.backend.cb_rc_progress     = lambda v:    self.after(0, self.update_rc_progress, v)
        self.backend.cb_connection_lost = lambda: self.after(0, self.on_connection_lost)

        self._progress_values = {
            "Accelerometer": 0,
            "Compass": 0,
            "RC Calibration": 0,
            "Log": 0,
        }
        
        self._accel_images = self._load_accel_images()

        # ── Top connection bar ────────────────────────────────────────────
        self._build_connection_bar()

        # ── Main area: left sidebar + tabview ────────────────────────────
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._build_left_panel(main)
        self._build_right_panel(main)

        self.refresh_ports()

    # =========================================================================
    # CONNECTION BAR
    # =========================================================================

    def _build_connection_bar(self):
        # ── Row 1: port selector + connect controls ───────────────────────
        bar = ctk.CTkFrame(self)
        bar.pack(fill="x", padx=8, pady=(6, 2))

        self._port_display_map = {}

        self.port_combo = ctk.CTkComboBox(
            bar, width=260, command=self._on_port_selected
        )
        self.port_combo.pack(side="left", padx=4)

        self.baud_combo = ctk.CTkComboBox(bar, values=["57600", "115200"], width=100)
        self.baud_combo.set("115200")
        self.baud_combo.pack(side="left", padx=4)

        ctk.CTkButton(bar, text="Refresh", width=80, command=self.refresh_ports).pack(side="left", padx=4)

        self.connect_btn = ctk.CTkButton(bar, text="Connect", width=100, command=self.toggle_connection)
        self.connect_btn.pack(side="left", padx=4)

        self.telemetry_label = ctk.CTkLabel(bar, text="", font=ctk.CTkFont(size=12))
        self.telemetry_label.pack(side="right", padx=12)

        # ── Row 2: port description label ────────────────────────────────
        desc_bar = ctk.CTkFrame(self, fg_color="transparent")
        desc_bar.pack(fill="x", padx=12, pady=(0, 4))

        self.port_desc_label = ctk.CTkLabel(
            desc_bar,
            text="No port selected",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w",
        )
        self.port_desc_label.pack(side="left")

    # =========================================================================
    # LEFT PANEL  (calibration buttons)
    # =========================================================================

    def _build_left_panel(self, parent):
        self.left_panel = ctk.CTkFrame(parent, width=160)
        self.left_panel.pack(side="left", fill="y", padx=(0, 8))
        self.left_panel.pack_propagate(False)

        ctk.CTkLabel(
            self.left_panel, text="Calibration",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(pady=(12, 6))

        self.accel_btn = ctk.CTkButton(
            self.left_panel, text="Accelerometer", command=self.on_accel_click
        )
        self.accel_btn.pack(fill="x", padx=8, pady=4)

        self.compass_btn = ctk.CTkButton(
            self.left_panel, text="Compass", command=self.on_compass_start
        )
        self.compass_btn.pack(fill="x", padx=8, pady=4)

        self.rc_btn = ctk.CTkButton(
            self.left_panel, text="RC Calibration", command=self.on_rc_start
        )
        self.rc_btn.pack(fill="x", padx=8, pady=4) 

    # =========================================================================
    # RIGHT PANEL  (tabview with per-calibration views + shared log)
    # =========================================================================

    def _build_right_panel(self, parent):
        right = ctk.CTkFrame(parent, fg_color="transparent")
        right.pack(side="right", fill="both", expand=True)

        button_row = ctk.CTkFrame(right, fg_color="transparent")
        button_row.pack(fill="x", padx=12, pady=(0, 8))

        self.start_btn = ctk.CTkButton(
            button_row,
            text="Start Calibration",
            fg_color="#219653",
            hover_color="#1b7b43",
            command=self.on_start_calibration,
            width=180,
        )
        self.start_btn.pack(side="left")

        # Tabview
        self.tabview = ctk.CTkTabview(right, command=self.on_tab_changed)
        self.tabview.pack(fill="both", expand=True)

        for name in ("Accelerometer", "Compass", "RC Calibration", "Log"):
            self.tabview.add(name)

        self._build_accel_tab()
        self._build_compass_tab()
        self._build_rc_tab()
        self._build_log_tab()

        # Status + progress bar beneath the tabview
        self.status_label = ctk.CTkLabel(right, text="", anchor="w",font=ctk.CTkFont(size=12))
        self.status_label.pack_forget()  # hide status label by default; only show when there's a status to display

        progress_row = ctk.CTkFrame(right, fg_color="transparent")
        progress_row.pack(fill="x", pady=(2, 4))

        self.progress = ctk.CTkProgressBar(progress_row)
        self.progress.pack(side="left", fill="x", expand=True)
        self.progress.set(0)

        self.progress_label = ctk.CTkLabel(
            progress_row, text="0%", width=40, font=ctk.CTkFont(size=13)
        )
        self.progress_label.pack(side="left", padx=(6, 0))

    # ──────────────────────────────────────────────────────────────────────────
    # ACCELEROMETER TAB
    # ──────────────────────────────────────────────────────────────────────────

    def _load_accel_images(self):
        """
        Load the 6 accel position images in 3 states:
        - "idle":   greyscale / dimmed
        - "active": full colour (original)
        - "done":   green-tinted
        Returns dict: {position: {"idle": CTkImage, "active": CTkImage, "done": CTkImage}}
        """
        IMAGE_PATHS = {
            1: "Calibration/Level.png",
            2: "Calibration/Left side.png",
            3: "Calibration/Right side.png",
            4: "Calibration/Nose Down.png",
            5: "Calibration/Nose Up.png",
            6: "Calibration/Upside Down.png",
        }
        SIZE = (100, 80)
        result = {}

        for pos, path in IMAGE_PATHS.items():
            try:
                original = Image.open(path).convert("RGBA").resize(SIZE)

                # Idle: original image, slightly dimmed
                idle_img = ImageEnhance.Brightness(original.copy()).enhance(0.6)

                # Active: full colour (slightly brightened)
                active_img = original.copy()

                # Done: green tint overlay
                done_img = original.copy()

                result[pos] = {
                    "idle":   ctk.CTkImage(idle_img,   size=SIZE),
                    "active": ctk.CTkImage(active_img, size=SIZE),
                    "done":   ctk.CTkImage(done_img,   size=SIZE),
                }
            except FileNotFoundError:
                result[pos] = None  # graceful fallback

        return result

    def _build_accel_tab(self):
        tab = self.tabview.tab("Accelerometer")

        # Instruction text
        self._accel_instruction = ctk.CTkLabel(
            tab,
            text="Select the Accelerometer tab and click 'Start Calibration' in the right panel to begin.",
            font=ctk.CTkFont(size=13),
            wraplength=500,
            justify="left",
            anchor="w",
        )
        self._accel_instruction.pack(anchor="w", padx=12, pady=(12, 4))

        # Position indicator grid (2 rows × 3 columns)
        ctk.CTkLabel(
            tab,
            text="Positions",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        ).pack(anchor="w", padx=12, pady=(8, 2))

        indicator_frame = ctk.CTkFrame(tab, fg_color="transparent")
        indicator_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        for col in range(3):
            indicator_frame.columnconfigure(col, weight=1)
        indicator_frame.rowconfigure(0, weight=1)
        indicator_frame.rowconfigure(1, weight=1)

        self._position_rows = {}
        for pos, name in POSITION_LABELS.items():
            row_idx = (pos - 1) // 3
            col_idx = (pos - 1) % 3

            cell = ctk.CTkFrame(indicator_frame, fg_color="#1F1E1E", corner_radius=10, border_width=2, border_color="#1F1E1E")
            cell.grid(row=row_idx, column=col_idx, padx=6, pady=6, sticky="nsew")

            imgs = self._accel_images.get(pos)
            if imgs:
                img_lbl = ctk.CTkLabel(cell, image=imgs["idle"], text="")
            else:
                img_lbl = ctk.CTkLabel(cell, text="●", font=ctk.CTkFont(size=24),
                                    text_color="#555555")
            img_lbl.pack(pady=(10, 4))

            name_lbl = ctk.CTkLabel(
                cell, text=f"{pos}. {name}",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#888888",
            )
            name_lbl.pack()

            pct_lbl = ctk.CTkLabel(
                cell, text="",
                font=ctk.CTkFont(size=11),
                text_color="gray",
            )
            pct_lbl.pack(pady=(2, 8))

            self._position_rows[pos] = {
                "cell": cell,
                "img_lbl": img_lbl,
                "label": name_lbl,
                "pct": pct_lbl,
                "has_image": imgs is not None,
            }

        # Next button
        self.accel_next_btn = ctk.CTkButton(
            tab,
            text="Next Position",
            command=self.on_accel_next,
            state="disabled",
            fg_color="#219653",
            hover_color="#1b7b43",
        )
        self.accel_next_btn.pack(anchor="w", padx=12, pady=(8, 4))

    # ──────────────────────────────────────────────────────────────────────────
    # COMPASS TAB
    # ──────────────────────────────────────────────────────────────────────────

    def _build_compass_tab(self):
        tab = self.tabview.tab("Compass")

        ctk.CTkLabel(
            tab,
            text=(
                "Select the Compass tab and click 'Start Calibration' in the right panel, "
                "then rotate the vehicle slowly through all orientations until complete."
            ),
            font=ctk.CTkFont(size=13),
            wraplength=560,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(12, 8))

        # Per-magnetometer progress rows (up to 3 mags).
        ctk.CTkLabel(
            tab, text="Magnetometers", font=ctk.CTkFont(size=12), text_color="gray"
        ).pack(anchor="w", padx=12)

        self._mag_rows = {}   # compass_id → {frame, status_dot, pct_lbl, bar}
        # FIX: Track last known bar value ourselves since CTkProgressBar has no .get()
        self._mag_bar_values = {}
        self._active_mag_ids = set()

        for mag_id in range(3):
            row_frame = ctk.CTkFrame(tab, fg_color="transparent")
            row_frame.pack(fill="x", padx=12, pady=3)

            dot = ctk.CTkLabel(
                row_frame, text="●", width=18, font=ctk.CTkFont(size=14),
                text_color=MAG_STATUS_COLORS["idle"]
            )
            dot.pack(side="left")

            ctk.CTkLabel(
                row_frame, text=f"Compass {mag_id + 1}", width=80,
                font=ctk.CTkFont(size=13), anchor="w"
            ).pack(side="left")

            bar = ctk.CTkProgressBar(row_frame, width=200, height=14)
            bar.set(0)
            bar.pack(side="left", padx=(6, 4))

            pct_lbl = ctk.CTkLabel(
                row_frame, text="0 %", width=40, font=ctk.CTkFont(size=12), text_color="gray"
            )
            pct_lbl.pack(side="left")

            status_lbl = ctk.CTkLabel(
                row_frame, text="idle", width=60, font=ctk.CTkFont(size=12),
                text_color=MAG_STATUS_COLORS["idle"]
            )
            status_lbl.pack(side="left", padx=4)

            self._mag_rows[mag_id] = {
                "dot": dot,
                "bar": bar,
                "pct_lbl": pct_lbl,
                "status_lbl": status_lbl,
            }
            self._mag_bar_values[mag_id] = 0.0
            
        # ── Compass calibration illustration ──────────────────────────────
        try:
            from PIL import Image as _PILImage
            _compass_img = _PILImage.open("Calibration/Compass_cal.png").convert("RGBA")
            _w, _h = _compass_img.size
            # Scale to fit nicely (max 420 wide)
            _scale = min(420 / _w, 160 / _h)
            _display_size = (int(_w * _scale), int(_h * _scale))
            self._compass_ctk_image = ctk.CTkImage(
                light_image=_compass_img,
                dark_image=_compass_img,
                size=_display_size,
            )
            _has_compass_img = True
        except Exception:
            self._compass_ctk_image = None
            _has_compass_img = False

        # Outer border frame — colour changes on pass/fail
        self._compass_img_border = ctk.CTkFrame(
            tab,
            corner_radius=12,
            border_width=2,
            border_color="#333333",
            fg_color="#111111",
        )
        self._compass_img_border.pack(anchor="w", padx=12, pady=(10, 0))

        if _has_compass_img:
            self._compass_img_lbl = ctk.CTkLabel(
                self._compass_img_border,
                image=self._compass_ctk_image,
                text="",
            )
        else:
            self._compass_img_lbl = ctk.CTkLabel(
                self._compass_img_border,
                text="[compass_cal.png not found]",
                font=ctk.CTkFont(size=11),
                text_color="gray",
            )
        self._compass_img_lbl.pack(padx=8, pady=8)

        # ── Notification bar (below image) ───────────────────────────────
        self._notif_bar = ctk.CTkFrame(
            tab,
            corner_radius=8,
            fg_color="transparent",
            height=0,
        )
        self._notif_bar.pack(fill="x", padx=12, pady=(14, 0))
        self._notif_bar.pack_propagate(False)

        self._notif_icon = ctk.CTkLabel(
            self._notif_bar,
            text="",
            width=24, height=24,
            font=ctk.CTkFont(size=14),
            fg_color="transparent",
            anchor="center",
        )
        self._notif_icon.pack(side="left", padx=(10, 8), pady=8)

        notif_text_col = ctk.CTkFrame(self._notif_bar, fg_color="transparent")
        notif_text_col.pack(side="left", fill="both", expand=True, pady=8)

        self._notif_title = ctk.CTkLabel(
            notif_text_col,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        )
        self._notif_title.pack(anchor="w")

        self._notif_sub = ctk.CTkLabel(
            notif_text_col,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w",
        )
        self._notif_sub.pack(anchor="w")

        # Cancel + retry buttons
        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.pack(anchor="w", padx=12, pady=(16, 4))

        self.compass_cancel_btn = ctk.CTkButton(
            tab,
            text="Cancel Compass Cal",
            fg_color="#c0392b",
            hover_color="#a93226",
            command=self.on_compass_cancel,
            state="disabled",
        )
        self.compass_cancel_btn.pack(side="left", padx=(0, 8))

        self.compass_retry_btn = ctk.CTkButton(
            tab,
            text="Retry",
            fg_color="#27ae60",
            hover_color="#219653",
            command=self.on_compass_retry,
        )
        self.compass_retry_btn.pack(side="left", padx=(6, 0))
        self.compass_retry_btn.pack_forget()  # hide retry button by default; only show on failure
        

    # ──────────────────────────────────────────────────────────────────────────
    # RC CALIBRATION TAB
    # ──────────────────────────────────────────────────────────────────────────

    def _build_rc_tab(self):
        tab = self.tabview.tab("RC Calibration")

        ctk.CTkLabel(
            tab,
            text=(
                "1. Select the RC Calibration tab and click 'Start Calibration'.\n"
                "2. Move ALL sticks and switches to their full extents.\n"
                "3. Centre all sticks and click 'Set Trims'.\n"
                "4. Click 'Save & Finish' to write values to the flight controller."
            ),
            font=ctk.CTkFont(size=13),
            justify="left",
            anchor="w",
        ).pack(anchor="w", padx=12, pady=(12, 10))

        # Channel bars
        channels_frame = ctk.CTkScrollableFrame(tab, height=260, fg_color="transparent")
        channels_frame.pack(fill="x", padx=12)

        header_row = ctk.CTkFrame(channels_frame, fg_color="transparent")
        header_row.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(header_row, text="Channel", width=90, font=ctk.CTkFont(size=11, weight="bold"), anchor="w").pack(side="left")
        ctk.CTkLabel(header_row, text="Min", width=40, font=ctk.CTkFont(size=11, weight="bold"), anchor="w").pack(side="left")
        ctk.CTkLabel(header_row, text="", width=220, font=ctk.CTkFont(size=11), anchor="w").pack(side="left")
        ctk.CTkLabel(header_row, text="Max", width=40, font=ctk.CTkFont(size=11, weight="bold"), anchor="w").pack(side="left")
        ctk.CTkLabel(header_row, text="Value", width=46, font=ctk.CTkFont(size=11, weight="bold"), anchor="w").pack(side="left", padx=(6, 0))
        ctk.CTkLabel(header_row, text="Trim", width=16, font=ctk.CTkFont(size=11, weight="bold"), anchor="w").pack(side="left")

        self._rc_rows = {}  # ch → {val_lbl, bar, min_entry, max_entry}

        for ch in range(1, self.backend.RC_CHANNEL_COUNT + 1):
            name = RC_CHANNEL_NAMES.get(ch, f"Ch {ch}")
            row = ctk.CTkFrame(channels_frame, fg_color="transparent")
            row.pack(fill="x", pady=3)

            ctk.CTkLabel(row, text=f"Ch{ch} {name}", width=90, font=ctk.CTkFont(size=12), anchor="w").pack(side="left")

            min_entry = ctk.CTkEntry(row, width=40, font=ctk.CTkFont(size=11))
            min_entry.insert(0, "—")
            min_entry.pack(side="left")

            bar = ctk.CTkProgressBar(row, width=220, height=14)
            bar.set(0.5)
            bar.pack(side="left", padx=4)

            max_entry = ctk.CTkEntry(row, width=40, font=ctk.CTkFont(size=11))
            max_entry.insert(0, "—")
            max_entry.pack(side="left")

            val_lbl = ctk.CTkLabel(row, text="—", width=46, font=ctk.CTkFont(size=12))
            val_lbl.pack(side="left", padx=(6, 0))

            trim_dot = ctk.CTkLabel(row, text="◆", width=16, font=ctk.CTkFont(size=10), text_color="#555")
            trim_dot.pack(side="left")

            self._rc_rows[ch] = {
                "bar": bar,
                "val_lbl": val_lbl,
                "min_entry": min_entry,
                "max_entry": max_entry,
                "trim_dot": trim_dot,
            }

        # RC action buttons
        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(10, 4))

        self.rc_trim_btn = ctk.CTkButton(
            btn_row, text="Set Trims", width=120,
            command=self.on_rc_set_trims, state="disabled"
        )
        self.rc_trim_btn.pack(side="left", padx=(0, 6))

        self.rc_save_btn = ctk.CTkButton(
            btn_row, text="Save & Finish", width=130,
            command=self.on_rc_save, state="disabled"
        )
        self.rc_save_btn.pack(side="left", padx=(0, 6))

        self.rc_cancel_btn = ctk.CTkButton(
            btn_row, text="Cancel", width=90,
            fg_color="#555", hover_color="#333",
            command=self.on_rc_cancel, state="disabled"
        )
        self.rc_cancel_btn.pack(side="left")

    # ──────────────────────────────────────────────────────────────────────────
    # LOG TAB
    # ──────────────────────────────────────────────────────────────────────────

    def _build_log_tab(self):
        tab = self.tabview.tab("Log")

        self.textbox = ctk.CTkTextbox(tab, font=ctk.CTkFont(size=12, family="Courier"))
        self.textbox.pack(fill="both", expand=True, padx=4, pady=4)

        ctk.CTkButton(
            tab, text="Clear", width=80,
            command=lambda: self.textbox.delete("1.0", "end")
        ).pack(anchor="e", padx=4, pady=(0, 4))

    # =========================================================================
    # CONNECTION
    # =========================================================================

    def refresh_ports(self):
        current_display = self.port_combo.get()
        ports = sorted(
            serial.tools.list_ports.comports(),
            key=lambda p: (p.device or "", p.description or ""),
        )
        display_values = []
        self._port_display_map = {}
        # Also store full description keyed by display string so we can
        # show it in the label when a port is selected.
        self._port_desc_map = {}

        for port in ports:
            desc = port.description or "Unknown device"
            display = f"{port.device} - {desc}"
            display_values.append(display)
            self._port_display_map[display] = port.device
            self._port_desc_map[display] = desc

        self.port_combo.configure(values=display_values)
        if current_display in self._port_display_map:
            self.port_combo.set(current_display)
        elif display_values:
            self.port_combo.set(display_values[0])
        else:
            self.port_combo.set("")

        # Refresh the description label for whichever port is now selected.
        self._update_port_desc(self.port_combo.get())

    def _on_port_selected(self, selected_display: str):
        """Called by CTkComboBox whenever the user picks a different port."""
        self._update_port_desc(selected_display)

    def _update_port_desc(self, selected_display: str):
        """Update the small description label beneath the port dropdown."""
        if not selected_display:
            self.port_desc_label.configure(text="No port selected", text_color="gray")
            return

        desc = getattr(self, "_port_desc_map", {}).get(selected_display, "")
        device = self._port_display_map.get(selected_display, selected_display)

        if desc and desc != "Unknown device":
            # Show something like:  ArduPilot Mega 2560  ·  COM3
            self.port_desc_label.configure(
                text=f"🔌  {desc}  ·  {device}",
                text_color="#4fc3f7",   # light blue so it stands out
            )
        elif device:
            self.port_desc_label.configure(
                text=f"🔌  {device}  — no description available",
                text_color="gray",
            )
        else:
            self.port_desc_label.configure(text="No port selected", text_color="gray")

    def toggle_connection(self):
        if self.backend.master:
            self.backend.disconnect()
            self.connect_btn.configure(text="Connect")
            self.show_notif("Warning", "Disconnected", "No COM port connected")
            return

        selected_display = self.port_combo.get()
        selected_port = self._port_display_map.get(selected_display, selected_display)
        connected = self.backend.connect(selected_port, int(self.baud_combo.get()))
        self.connect_btn.configure(text="Disconnect" if connected else "Connect")
        if connected:
            self.show_notif("success", f"Connected to {selected_port}", "Device ready for calibration")
        else:
            self.show_notif("error", f"Failed to connect to {selected_port}", "Please check the port and try again")

    def on_tab_changed(self):
        """Called when user switches tabs - update progress bar to show current calibration progress"""
        current_tab = self.tabview.get()
        progress_value = self._progress_values.get(current_tab, 0)
        self.progress.set(progress_value / 100)
        self.progress_label.configure(text=f"{int(progress_value)}%")

    # =========================================================================
    # ACCELEROMETER CALIBRATION
    # =========================================================================

    def on_accel_click(self):
        # Just switch to the Accelerometer tab - calibration is started by the Start button
        self.tabview.set("Accelerometer")

    def on_accel_next(self):
        # Confirm the current position during accelerometer calibration
        self.backend.confirm_position()

    def set_confirm_ready(self, enabled: bool):
        self.accel_next_btn.configure(state="normal" if enabled else "disabled")

    def on_accel_done(self, success: bool):
        self.on_calibration_done(success)
        if success:
            self.show_notif("success", "Accelerometer calibration complete", "Accel calibration finished successfully.")
        else:
            self.show_notif("error", "Accelerometer calibration failed", "Please retry the accelerometer calibration.")

    def on_calibration_done(self, success: bool):
        # Reset the Next button state when calibration completes
        self.accel_next_btn.configure(state="disabled")

    def update_position_indicator(self, position: int, state: str):
        if state == "reset":
            for pos, row in self._position_rows.items():
                imgs = self._accel_images.get(pos)
                if row["has_image"] and imgs:
                    row["img_lbl"].configure(image=imgs["idle"])
                else:
                    row["img_lbl"].configure(text_color="#555555")
                row["cell"].configure(fg_color="#1a1a2e", border_width=0)
                row["label"].configure(text_color="#888888")
                row["pct"].configure(text="")
            self._accel_instruction.configure(
                text="Waiting for first position request from flight controller…"
            )
            return

        if position not in self._position_rows:
            return

        row = self._position_rows[position]
        imgs = self._accel_images.get(position)
        name = POSITION_LABELS.get(position, f"Position {position}")

        if state == "active":
            if row["has_image"] and imgs:
                row["img_lbl"].configure(image=imgs["active"])
            else:
                row["img_lbl"].configure(text_color="#f0ad4e")
            # Highlight the card with an amber border
            row["cell"].configure(fg_color="#2a2010", border_width=2, border_color="#f0ad4e")
            row["label"].configure(text_color="#f0ad4e")
            row["pct"].configure(text="…")
            self._accel_instruction.configure(
                text=f"Step {position}/6 — Place drone {name.lower()} and hold still, then click 'Next'."
            )

        elif state == "done":
            pct = min(int((position / 6) * 100), 100)
            if row["has_image"] and imgs:
                row["img_lbl"].configure(image=imgs["done"])
            else:
                row["img_lbl"].configure(text_color="#2ecc71")
            # Green card border on completion
            row["cell"].configure(fg_color="#0d1f0d", border_width=2, border_color="#2ecc71")
            row["label"].configure(text_color="#2ecc71")
            row["pct"].configure(text=f"{pct}%")
            if position == 6:
                self._accel_instruction.configure(
                    text="All positions confirmed! Return drone to level to complete calibration."
                )

    # =========================================================================
    # COMPASS CALIBRATION
    # =========================================================================

    def on_compass_start(self):
        # Just switch to the Compass tab - calibration is started by the Start button
        self.tabview.set("Compass")

    def on_compass_cancel(self):
        self.backend.cancel_compass_calibration()
        self.compass_cancel_btn.configure(state="disabled")
        self.show_notif("warning", "Calibration cancelled", "Press Compass to start again")
        
    def on_compass_retry(self):
        # Directly start compass calibration for retry.
        self.compass_retry_btn.pack_forget()
        self.show_notif("info", "Calibration Started", "Rotate the drone slowly through all orientations until complete.")

        # Reset mag rows and compass progress.
        for mag_id, row in self._mag_rows.items():
            row["dot"].configure(text_color=MAG_STATUS_COLORS["idle"])
            row["bar"].set(0)
            row["pct_lbl"].configure(text="0 %")
            row["status_lbl"].configure(text="idle", text_color=MAG_STATUS_COLORS["idle"])
            self._mag_bar_values[mag_id] = 0.0
        self._active_mag_ids.clear()
        if hasattr(self, "_compass_img_border"):
            self._compass_img_border.configure(border_color="#333333")
        self._progress_values["Compass"] = 0
        if self.tabview.get() == "Compass":
            self.progress.set(0)
            self.progress_label.configure(text="0%")

        self.compass_cancel_btn.configure(state="normal")
        self.backend.start_compass_calibration()

    def on_start_calibration(self):
        selected = self.tabview.get()
        if selected == "Accelerometer":
            if not self.backend.in_calibration:
                if not self.backend.start_accel_calibration():
                    self.show_notif("error", "Failed to start accelerometer calibration", "Check drone connection and try again.")
            else:
                self.show_notif("warning", "Accelerometer calibration already running", "Use the Next button in the Accelerometer tab to confirm each position.")
        elif selected == "Compass":
            self.compass_retry_btn.pack_forget()
            self.show_notif("info", "Calibration Started", "Rotate the drone slowly through all orientations until complete.")
            for mag_id, row in self._mag_rows.items():
                row["dot"].configure(text_color=MAG_STATUS_COLORS["idle"])
                row["bar"].set(0)
                row["pct_lbl"].configure(text="0 %")
                row["status_lbl"].configure(text="idle", text_color=MAG_STATUS_COLORS["idle"])
                self._mag_bar_values[mag_id] = 0.0
            self._active_mag_ids.clear()
            if hasattr(self, "_compass_img_border"):
                self._compass_img_border.configure(border_color="#333333")
            self._progress_values["Compass"] = 0
            if self.tabview.get() == "Compass":
                self.progress.set(0)
                self.progress_label.configure(text="0%")

            self.compass_cancel_btn.configure(state="normal")
            self.backend.start_compass_calibration()
        elif selected == "RC Calibration":
            for row in self._rc_rows.values():
                row["min_entry"].delete(0, "end")
                row["min_entry"].insert(0, "—")
                row["max_entry"].delete(0, "end")
                row["max_entry"].insert(0, "—")
                row["val_lbl"].configure(text="—")
                row["bar"].set(0.5)
                row["trim_dot"].configure(text_color="#555")

            self.rc_trim_btn.configure(state="normal")
            self.rc_save_btn.configure(state="normal")
            self.rc_cancel_btn.configure(state="normal")
            self.show_notif("info", "RC Calibration Started", "Move all sticks and switches to their full extents.")
            self.backend.start_rc_calibration()
        else:
            self.show_notif("warning", "Select a calibration tab", "Choose Accelerometer, Compass, or RC Calibration.")

    def show_notif(self, state: str, title: str, subtext: str=""):
        cfg = {
            "info":    {"bg": "#1e2a3a", "border": "#185fa5", "icon_bg": "#0c3058", "icon": "ℹ",  "icon_color": "#85b7eb", "title_color": "#b5d4f4"},
            "success": {"bg": "#0f1f0a", "border": "#3b6d11", "icon_bg": "#1a3a08", "icon": "✓",  "icon_color": "#97c459", "title_color": "#c0dd97"},
            "error":   {"bg": "#1f0808", "border": "#a32d2d", "icon_bg": "#3a0c0c", "icon": "✕",  "icon_color": "#f09595", "title_color": "#f7c1c1"},
            "warning": {"bg": "#1e1608", "border": "#854f0b", "icon_bg": "#3a2a04", "icon": "⚠",  "icon_color": "#ef9f27", "title_color": "#fac775"},
        }
        c = cfg.get(state, cfg["info"])
        self._notif_bar.configure(fg_color=c["bg"], border_color=c["border"], border_width=1, height=58)
        self._notif_icon.configure(text=c["icon"], fg_color=c["icon_bg"], text_color=c["icon_color"])
        self._notif_title.configure(text=title, text_color=c["title_color"])
        self._notif_sub.configure(text=subtext, text_color="gray")
        self._notif_bar.pack_propagate(False)  # prevent the frame from resizing to fit its contents
        
    def hide_notif(self):
        self._notif_bar.configure(height=0, fg_color="transparent", border_width=0)
        
    def on_compass_progress(self, compass_id: int, pct: int):
        if compass_id not in self._mag_rows:
            return
        row = self._mag_rows[compass_id]
        bar_val = pct / 100
        row["dot"].configure(text_color=MAG_STATUS_COLORS["running"])
        row["bar"].set(bar_val)
        row["pct_lbl"].configure(text=f"{pct} %")
        row["status_lbl"].configure(text="running", text_color=MAG_STATUS_COLORS["running"])
        # FIX: Track bar value ourselves since CTkProgressBar has no .get()
        self._mag_bar_values[compass_id] = bar_val
        self._active_mag_ids.add(compass_id)

        # Calculate average progress across only the magnetometers that actually reported progress.
        active_values = [self._mag_bar_values[mid] for mid in self._active_mag_ids]
        avg_progress = sum(active_values) / len(active_values) if active_values else 0
        self._progress_values["Compass"] = int(avg_progress * 100)

        if self.tabview.get() == "Compass":
            self.progress.set(avg_progress)
            self.progress_label.configure(text=f"{int(avg_progress * 100)}%")

    def on_compass_done(self, results: dict):
        """results: {compass_id: bool}"""
        self.compass_cancel_btn.configure(state="disabled")
        
        #show retry button if any compass failed
        any_failed = not all(results.values())
        passed_count = sum(1 for v in results.values() if v)
        failed_count = sum(1 for v in results.values() if not v)
        if any_failed:
            self.compass_retry_btn.pack(side="left")
            self.show_notif("error", f"Compass Calibration Failed", f"{failed_count} magnetometer(s) did not pass — click Retry")
        else:
            self.compass_retry_btn.pack_forget()
            self.show_notif("success", "Compass Calibration Successful", f"{passed_count} magnetometer(s) passed calibration")
        # Update compass image border colour
        if hasattr(self, "_compass_img_border"):
            border_color = "#e74c3c" if any_failed else "#2ecc71"
            self._compass_img_border.configure(border_color=border_color)
            
        for cid, passed in results.items():
            if cid not in self._mag_rows:
                continue
            row = self._mag_rows[cid]
            color = MAG_STATUS_COLORS["pass"] if passed else MAG_STATUS_COLORS["fail"]
            status_text = "PASS" if passed else "FAIL"
            row["dot"].configure(text_color=color)
            row["status_lbl"].configure(text=status_text, text_color=color)

            if passed:
                # FIX: Set bar to 1.0 and update label on pass.
                row["bar"].set(1.0)
                row["pct_lbl"].configure(text="100 %")
                self._mag_bar_values[cid] = 1.0
            # On fail, bar and pct_lbl stay at whatever progress was reached —
            # no .get() needed since we track it in _mag_bar_values.

        if all(results.values()):
            self._progress_values["Compass"] = 100
            if self.tabview.get() == "Compass":
                self.progress.set(1.0)
                self.progress_label.configure(text="100%")

    def on_compass_state_update(self, compass_id: int, state: str):
        if compass_id not in self._mag_rows:
            return
        row = self._mag_rows[compass_id]
        if state == "rotating":
            row["status_lbl"].configure(text="rotating", text_color=MAG_STATUS_COLORS["running"])
            row["dot"].configure(text_color=MAG_STATUS_COLORS["running"])
        elif state == "done":
            row["status_lbl"].configure(text="done", text_color=MAG_STATUS_COLORS["pass"])
            row["dot"].configure(text_color=MAG_STATUS_COLORS["pass"])
        elif state == "failed":
            row["status_lbl"].configure(text="failed", text_color=MAG_STATUS_COLORS["fail"])
            row["dot"].configure(text_color=MAG_STATUS_COLORS["fail"])

    def on_rc_channel_state_update(self, ch: int, state: str):
        if ch not in self._rc_rows:
            return
        row = self._rc_rows[ch]
        if state == "done":
            row["trim_dot"].configure(text_color="#2ecc71")
        else:
            row["trim_dot"].configure(text_color="#555")

    # =========================================================================
    # RC CALIBRATION
    # =========================================================================

    def on_rc_start(self):
        # Just switch to the RC Calibration tab - calibration is started by the Start button
        self.tabview.set("RC Calibration")

    def on_rc_set_trims(self):
        self.backend.capture_rc_trims()
        # Highlight trim dots green to indicate trims captured
        for row in self._rc_rows.values():
            row["trim_dot"].configure(text_color="#2ecc71")
        self.show_notif("info", "Trims Captured", "Centre position recorded — click 'Save & Finish' when done sweeping.")

    def on_rc_save(self):
        # Apply manual min/max overrides before saving.
        for ch, row in self._rc_rows.items():
            min_override = self._parse_int(row["min_entry"].get())
            max_override = self._parse_int(row["max_entry"].get())
            if min_override is not None:
                self.backend._rc_min[ch] = min_override
            if max_override is not None:
                self.backend._rc_max[ch] = max_override

        self.backend.save_rc_calibration()
        self.rc_trim_btn.configure(state="disabled")
        self.rc_save_btn.configure(state="disabled")
        self.rc_cancel_btn.configure(state="disabled")

    def on_rc_cancel(self):
        self.backend.cancel_rc_calibration()
        self.rc_trim_btn.configure(state="disabled")
        self.rc_save_btn.configure(state="disabled")
        self.rc_cancel_btn.configure(state="disabled")
        
        for row in self._rc_rows.values():
            row["min_entry"].delete(0, "end")
            row["min_entry"].insert(0, "—")
            row["max_entry"].delete(0, "end")
            row["max_entry"].insert(0, "—")
            row["val_lbl"].configure(text="—")
            row["bar"].set(0.5)
            row["trim_dot"].configure(text_color="#555")

        self._progress_values["RC Calibration"] = 0
        if self.tabview.get() == "RC Calibration":
            self.progress.set(0)
            self.progress_label.configure(text="0%")
            
        self.show_notif("warning", "RC Calibration Cancelled", "No values were saved to the flight controller.")


    def on_rc_done(self, min_vals, max_vals, trim_vals):
        self.rc_trim_btn.configure(state="disabled")
        self.rc_save_btn.configure(state="disabled")
        self.rc_cancel_btn.configure(state="disabled")
        
        # Reset every channel row back to its initial blank state
        for row in self._rc_rows.values():
            row["min_entry"].delete(0, "end")
            row["min_entry"].insert(0, "—")
            row["max_entry"].delete(0, "end")
            row["max_entry"].insert(0, "—")
            row["val_lbl"].configure(text="—")
            row["bar"].set(0.5)
            row["trim_dot"].configure(text_color="#555")

        self._progress_values["RC Calibration"] = 0
        if self.tabview.get() == "RC Calibration":
            self.progress.set(0)
            self.progress_label.configure(text="0%")

        self.show_notif("success", "RC Calibration Successful", "Min / max / trim values written to the flight controller.")

    def _parse_int(self, text):
        try:
            return int(str(text).strip())
        except (ValueError, TypeError):
            return None

    def on_rc_update(self, ch: int, val: int, lo: int, hi: int):
        if ch not in self._rc_rows:
            return
        row = self._rc_rows[ch]

        # Use fixed PWM range (800-2200) for the bar so it moves
        # immediately with stick movement, regardless of swept min/max.
        PWM_MIN = 800
        PWM_MAX = 2200
        norm = max(0.0, min(1.0, (val - PWM_MIN) / (PWM_MAX - PWM_MIN)))

        row["bar"].set(norm)
        row["val_lbl"].configure(text=str(val))

        # Only update min/max entries if calibration has produced real data
        # (i.e. lo != hi, meaning the stick has actually been moved)
        if lo != hi:
            row["min_entry"].delete(0, "end")
            row["min_entry"].insert(0, str(lo))
            row["max_entry"].delete(0, "end")
            row["max_entry"].insert(0, str(hi))
        elif lo == hi and row["min_entry"].get() in ("—", str(lo)):
            # First data point — show current value as placeholder
            row["min_entry"].delete(0, "end")
            row["min_entry"].insert(0, str(lo))
            row["max_entry"].delete(0, "end")
            row["max_entry"].insert(0, str(hi))

    # =========================================================================
    # SHARED STATUS / LOG CALLBACKS
    # =========================================================================

    def set_status(self, text, color):
        self.status_label.configure(text=text, text_color=color)

    def handle_statustext(self, text):
        self.textbox.insert("end", f"{text}\n")
        self.textbox.see("end")

    def update_telemetry(self, mode, battery):
        parts = []
        if mode is not None:
            parts.append(f"Mode: {mode}")
        if battery is not None:
            parts.append(f"Battery: {battery}%")
        self.telemetry_label.configure(text="  |  ".join(parts))

    def handle_ack(self, result):
        pass   # extend if you need COMMAND_ACK feedback in the UI

    def update_progress(self, value):
        current_tab = self.tabview.get()
        self._progress_values[current_tab] = int(value)
        self.progress.set(value / 100)
        self.progress_label.configure(text=f"{int(value)}%")

    def update_accel_progress(self, value):
        self._progress_values["Accelerometer"] = int(value)
        if self.tabview.get() == "Accelerometer":
            self.progress.set(value / 100)
            self.progress_label.configure(text=f"{int(value)}%")

    def update_rc_progress(self, value):
        self._progress_values["RC Calibration"] = int(value)
        if self.tabview.get() == "RC Calibration":
            self.progress.set(value / 100)
            self.progress_label.configure(text=f"{int(value)}%")


if __name__ == "__main__":
    app = CalibrationWindow()
    app.mainloop()