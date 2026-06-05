# Actiontab.py  — all output goes to GUI console
import customtkinter as ctk
from datetime import datetime
import threading
from pymavlink import mavutil

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

SITL_UDP = "udp:127.0.0.1:14550"


# ── Actions Tab widget ───────────────────────────────────────
class ActionsTab(ctk.CTkFrame):
    def __init__(self, parent, mav_connection=None, log_fn=None):
        super().__init__(parent)
        self.mav = mav_connection
        self._armed = False
        # use provided log_fn, or fall back to print
        self._log = log_fn if log_fn else lambda msg, lvl="info": print(f"[{lvl}] {msg}")
        self._build_ui()

    def _build_ui(self):
        BTN_GREEN  = "#4a8a20"
        BTN_HOVER  = "#5aa030"
        BTN_BORDER = "#6ab030"

        btn_kw = dict(
            fg_color=BTN_GREEN,
            hover_color=BTN_HOVER,
            border_color=BTN_BORDER,
            border_width=1,
            corner_radius=3,
            text_color="white",
            font=("Times New Roman", 12),
            height=28,
        )

        def entry_with_focus(parent, textvariable, width, on_enter):
            e = ctk.CTkEntry(parent, textvariable=textvariable,
                             width=width, font=("Times New Roman", 12))
            e.bind("<FocusIn>",  lambda _: e.configure(border_color="#8acc40", border_width=2))
            e.bind("<FocusOut>", lambda _: e.configure(border_color="#555",    border_width=1))
            e.bind("<Return>",   lambda _: on_enter())
            return e

        # ── Row 0: Change Speed ──────────────────────────────
        r0 = ctk.CTkFrame(self, fg_color="transparent")
        r0.grid(row=0, column=0, sticky="ew", padx=8, pady=4)
        self.speed_var = ctk.StringVar(value="5")
        entry_with_focus(r0, self.speed_var, 70, self._change_speed).grid(row=0, column=0, padx=4)
        ctk.CTkLabel(r0, text="Change Speed (m/s)",
                     font=("Times New Roman", 12)).grid(row=0, column=1, padx=4)

        # ── Row 1: Change Altitude ───────────────────────────
        r1 = ctk.CTkFrame(self, fg_color="transparent")
        r1.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        self.alt_var = ctk.StringVar(value="50")
        entry_with_focus(r1, self.alt_var, 70, self._change_altitude).grid(row=0, column=0, padx=4)
        ctk.CTkLabel(r1, text="Change Altitude (m)",
                     font=("Times New Roman", 12)).grid(row=0, column=1, padx=4)

        # ── Row 2: Set Loiter Radius ─────────────────────────
        r2 = ctk.CTkFrame(self, fg_color="transparent")
        r2.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
        self.loiter_rad_var = ctk.StringVar(value="100")
        entry_with_focus(r2, self.loiter_rad_var, 70, self._set_loiter_radius).grid(row=0, column=0, padx=4)
        ctk.CTkLabel(r2, text="Set Loiter Radius (m)",
                     font=("Times New Roman", 12)).grid(row=0, column=1, padx=4)

        # ── Row 3: RTL / Loiter / Arm/Disarm ────────────────
        r3 = ctk.CTkFrame(self, fg_color="transparent")
        r3.grid(row=3, column=0, sticky="ew", padx=8, pady=8)

        self.rtl_btn = ctk.CTkButton(
            r3, text="RTL", command=self._set_rtl, **btn_kw, width=100)
        self.rtl_btn.grid(row=0, column=0, padx=6)

        self.loiter_btn = ctk.CTkButton(
            r3, text="Loiter", command=self._set_loiter, **btn_kw, width=100)
        self.loiter_btn.grid(row=0, column=1, padx=6)
        
        self.takeoff_btn = ctk.CTkButton(
            r3, text="TakeOff", command=self._set_takeoff, **btn_kw, width=100)
        self.takeoff_btn.grid(row=0, column=2, padx=6)

        self.arm_btn = ctk.CTkButton(
            r3, text="Arm", command=self._arm_disarm, **btn_kw, width=100)
        self.arm_btn.grid(row=0, column=3, padx=6)

    # ── MAVLink helpers ──────────────────────────────────────
    def _send_command_long(self, command, p1=0, p2=0, p3=0, p4=0, p5=0, p6=0, p7=0):
        if not self.mav:
            self._log("No MAVLink connection", "err"); return
        self.mav.mav.command_long_send(
            self.mav.target_system,
            self.mav.target_component,
            command, 0,
            p1, p2, p3, p4, p5, p6, p7)
        # Check ACK in background so UI doesn't freeze
        threading.Thread(target=self._wait_ack, args=(command,), daemon=True).start()
        
    def _wait_ack(self,command):
        ACK_RESULT = {
            0: ("ACCEPTED",        "cmd"),
            1: ("TEMPORARILY REJECTED", "warn"),
            2: ("DENIED",          "err"),
            3: ("UNSUPPORTED",     "err"),
            4: ("FAILED",          "err"),
        }
        try:
            msg = self.mav.recv_match(type="COMMAND_ACK",blocking=True, timeout=3)
            if msg:
                text, level = ACK_RESULT.get(msg.result, (f"UNKNOWN({msg.result})", "warn"))
                self.after(0, lambda: self._log(f"ACK cmd={command} → {text}", level))
            else:
                self.after(0, lambda: self._log(f"ACK timeout for cmd={command}", "warn"))
        except Exception as e:
            self.after(0, lambda err=e: self._log(f"ACK error: {err}", "warn"))

    def _set_flight_mode(self, mode_name: str):
        MODE_MAP = {"Stabilize": 0, "Auto": 3, "Guided": 4,
                    "Loiter": 5, "RTL": 6, "Land": 9}
        mode_num = MODE_MAP.get(mode_name)
        if mode_num is None:
            self._log(f"Unknown mode: {mode_name}", "err"); return
        self.mav.mav.set_mode_send(
            self.mav.target_system,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            mode_num)
        self._log(f"Mode set → {mode_name}", "cmd")

    def _flash_button(self, btn, ms=600):
        orig = btn.cget("fg_color")
        btn.configure(fg_color="#1a5a00")
        self.after(ms, lambda: btn.configure(fg_color=orig))

    # ── 6 command handlers ───────────────────────────────────
    def _change_speed(self):
        try:
            speed = float(self.speed_var.get())
            assert 0 < speed <= 50
        except (ValueError, AssertionError):
            self._log("Change Speed: invalid value (0–50 m/s)", "err"); return
        self._send_command_long(
            mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED,
            p1=0, p2=speed, p3=-1)
        self._log(f"Change Speed → {speed} m/s", "cmd")

    def _change_altitude(self):
        try:
            alt = float(self.alt_var.get())
            assert 0 <= alt <= 500
        except (ValueError, AssertionError):
            self._log("Change Altitude: invalid value (0–500 m)", "err"); return
        if not self.mav:
            self._log("No MAVLink connection", "err"); return
        self.mav.mav.set_position_target_global_int_send(
            0,
            self.mav.target_system,
            self.mav.target_component,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            0b111111111000,
            0, 0, alt,
            0, 0, 0, 0, 0, 0, 0, 0)
        self._log(f"Change Altitude → {alt} m", "cmd")

    def _set_loiter_radius(self):
        try:
            radius = float(self.loiter_rad_var.get())
            assert 0 < abs(radius) <= 1000
        except (ValueError, AssertionError):
            self._log("Loiter Radius: invalid value (0–1000 m)", "err"); return
        if not self.mav:
            self._log("No MAVLink connection", "err"); return
        self.mav.mav.param_set_send(
            self.mav.target_system,
            self.mav.target_component,
            b"WP_LOITER_RAD",
            radius,
            mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
        self._log(f"Loiter Radius → {radius} m", "cmd")

    def _set_rtl(self):
        self._set_flight_mode("RTL")
        self._flash_button(self.rtl_btn)

    def _set_loiter(self):
        self._set_flight_mode("Loiter")
        self._flash_button(self.loiter_btn)
        
    def _set_takeoff(self):
        try:
            alt= float(self.alt_var.get())
            assert 0 < alt <=500
        except(ValueError, AssertionError):
            self._log("Takeoff: Invalid Altitude (0-500m)","err"); return
        # 1. Switch to Guided mode first (required for takeoff command)
        self._set_flight_mode("Guided")
        # 2. Send NAV_TAKEOFF command
        self._send_command_long(
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
            p7=alt   # p7 = target altitude in metres
        )
        self._log(f"Takeoff → {alt} m", "cmd")
        self._flash_button(self.takeoff_btn)
            

    # ── ARM / DISARM ─────────────────────────────────────────────
    def _arm_disarm(self):

        # =========================================================
        # ARM
        # =========================================================
        if not self._armed:

            self._send_command_long(
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                p1=1,
                p2=21196
            )

            threading.Thread(
                target=self._wait_arm_ack,
                args=(True,),
                daemon=True
            ).start()

            return

        # =========================================================
        # DISARM CONFIRM
        # =========================================================
        self._show_disarm_confirm()


    # ── DISARM CONFIRM POPUP FRAME ──────────────────────────────
    def _show_disarm_confirm(self):

        # prevent duplicate popup
        if hasattr(self, "confirm_popup") and self.confirm_popup.winfo_exists():
            return

        # overlay
        self.confirm_overlay = ctk.CTkFrame(
            self,
            fg_color="#000000"
        )

        self.confirm_overlay.place(
            relx=0,
            rely=0,
            relwidth=1,
            relheight=1
        )

        # popup frame
        self.confirm_popup = ctk.CTkFrame(
            self,
            width=340,
            height=160,
            corner_radius=8,
            fg_color="#1e1e1e",
            border_width=1,
            border_color="#444"
        )

        self.confirm_popup.place(
            relx=0.5,
            rely=0.5,
            anchor="center"
        )

        # title
        ctk.CTkLabel(
            self.confirm_popup,
            text="Disarm",
            font=("Times New Roman", 16, "bold")
        ).pack(pady=(12, 8))

        # message
        ctk.CTkLabel(
            self.confirm_popup,
            text="Are you sure you want to Disarm",
            font=("Times New Roman", 13)
        ).pack(pady=(10, 25))

        # buttons frame
        btn_frame = ctk.CTkFrame(
            self.confirm_popup,
            fg_color="transparent"
        )

        btn_frame.pack()

        # close helper
        def close_popup():

            if hasattr(self, "confirm_popup"):
                self.confirm_popup.destroy()

            if hasattr(self, "confirm_overlay"):
                self.confirm_overlay.destroy()

        # YES
        def yes_disarm():

            close_popup()

            # normal disarm first
            self._send_command_long(
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                p1=0,
                p2=0
            )

            threading.Thread(
                target=self._check_disarm_result,
                daemon=True
            ).start()

        # buttons
        ctk.CTkButton(
            btn_frame,
            text="Yes",
            width=90,
            fg_color="#99cc33",
            hover_color="#88bb22",
            text_color="black",
            command=yes_disarm
        ).grid(row=0, column=0, padx=10)

        ctk.CTkButton(
            btn_frame,
            text="No",
            width=90,
            fg_color="#99cc33",
            hover_color="#88bb22",
            text_color="black",
            command=close_popup
        ).grid(row=0, column=1, padx=10)


    # ── CHECK DISARM RESULT ─────────────────────────────────────
    def _check_disarm_result(self):
        try:
            msg = self.mav.recv_match(type="COMMAND_ACK",blocking=True,timeout=3)

            # success
            if msg and msg.result == 0:
                self._armed = False
                self.after(0,lambda: self._apply_arm_state(False))
                return

            # failed -> show force disarm popup
            self.after(0,self._show_force_disarm_popup)

        except Exception as e:
            self.after(0,lambda err=e: self._log(f"Disarm error: {err}","err"))


    # ── FORCE DISARM POPUP ──────────────────────────────────────
    def _show_force_disarm_popup(self):

        # prevent duplicate popup
        if hasattr(self, "force_popup") and self.force_popup.winfo_exists():
            return

        # overlay
        root = self.winfo_toplevel()
        
        self.force_overlay = ctk.CTkFrame(
            root,
            fg_color="#000000"
        )

        self.force_overlay.place(
            relx=0,
            rely=0,
            relwidth=1,
            relheight=1
        )

        # popup frame
        self.force_popup = ctk.CTkFrame(
            self.winfo_toplevel(),
            width=380,
            height=200,
            corner_radius=8,
            fg_color="#1e1e1e",
            border_width=1,
            border_color="#444"
        )

        self.force_popup.place(
            relx=0.5,
            rely=0.5,
            anchor="center"
        )

        # title
        ctk.CTkLabel(
            self.force_popup,
            text="Error",
            font=("Times New Roman", 16, "bold")
        ).pack(pady=(14, 10))

        # warning text
        warning_text = (
            "Disarm failed.\n\n"
            "Force Disarm can bypass safety checks,\n"
            "which can lead to the vehicle crashing\n"
            "and causing serious injuries.\n\n"
            "Do you wish to Force Disarm?"
        )

        ctk.CTkLabel(
            self.force_popup,
            text=warning_text,
            justify="center",
            font=("Times New Roman", 13)
        ).pack(pady=(5, 22))

        # buttons frame
        btn_frame = ctk.CTkFrame(
            self.force_popup,
            fg_color="transparent"
        )

        btn_frame.pack()

        # close helper
        def close_popup():

            if hasattr(self, "force_popup"):
                self.force_popup.destroy()

            if hasattr(self, "force_overlay"):
                self.force_overlay.destroy()

        # force disarm
        def force_disarm():

            close_popup()

            self._send_command_long(
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                p1=0,
                p2=21196
            )

            threading.Thread(
                target=self._wait_arm_ack,
                args=(False,),
                daemon=True
            ).start()

        # cancel
        def cancel():
            close_popup()

        # buttons
        ctk.CTkButton(
            btn_frame,
            text="Force Disarm",
            width=130,
            fg_color="#99cc33",
            hover_color="#88bb22",
            text_color="black",
            command=force_disarm
        ).grid(row=0, column=0, padx=12)

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=100,
            fg_color="#99cc33",
            hover_color="#88bb22",
            text_color="black",
            command=cancel
        ).grid(row=0, column=1, padx=12)
        
    def _wait_arm_ack(self, target_state: bool):
        try:
            msg = self.mav.recv_match(type="COMMAND_ACK", blocking=True, timeout=3)
            if msg and msg.result == 0:  # ACCEPTED
                self._armed = target_state
                self.after(0, lambda: self._apply_arm_state(self._armed))
            else:
                result = msg.result if msg else "timeout"
                self.after(0, lambda r=result: self._log(
                    f"Arm/Disarm rejected by FC (result={r}) — vehicle may be in-flight!", "err"))
                # Revert button to actual state
                self.after(0, lambda: self._apply_arm_state(self._armed))
        except Exception as e:
            self.after(0, lambda err=e: self._log(f"Arm ACK error: {err}", "warn"))

    def _apply_arm_state(self, armed: bool):
        self.arm_btn.configure(
            text="Disarm" if armed else "Arm",
            fg_color="#8a2020" if armed else "#4a8a20",
            hover_color="#aa3030" if armed else "#5aa030")
        self._log(f"{'Armed' if armed else 'Disarmed'}", "cmd")

    def sync_arm_state(self, is_armed: bool):
        if is_armed != self._armed:          # only update on actual change
            self._armed = is_armed
            self._apply_arm_state(is_armed)


# ── Main window ──────────────────────────────────────────────
class ActionsTestWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Actions Tab — SITL UDP")
        self.geometry("480x400")
        self.resizable(False, False)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)   # row 2 = console expands

        self.mav      = None
        self.tab      = None
        self._running = False

        self._build_toolbar()   # row 0
        # row 1 = ActionsTab (inserted after connect)
        self._build_console()   # row 2

        self._log(f"Click Connect to open {SITL_UDP}", "info")
        self._log("Make sure Mission Planner SITL is running.", "info")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Toolbar ──────────────────────────────────────────────
    def _build_toolbar(self):
        bar = ctk.CTkFrame(self, fg_color="#1e1e1e", corner_radius=0, height=36)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_propagate(False)

        self.conn_btn = ctk.CTkButton(
            bar, text="Connect", width=90, height=26,
            font=("Times New Roman", 12),
            fg_color="#1a5a80", hover_color="#2a7aaa",
            command=self._connect)
        self.conn_btn.pack(side="left", padx=8, pady=4)

        self.status_lbl = ctk.CTkLabel(
            bar, text="● Disconnected",
            font=("Times New Roman", 11), text_color="#cc4444")
        self.status_lbl.pack(side="left", padx=4)

        ctk.CTkButton(
            bar, text="Clear", width=70, height=26,
            font=("Times New Roman", 11),
            fg_color="#333", hover_color="#444",
            command=self._clear).pack(side="right", padx=8, pady=4)

    # ── Console ──────────────────────────────────────────────
    def _build_console(self):
        frame = ctk.CTkFrame(self, fg_color="#111", corner_radius=0)
        frame.grid(row=2, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        self.console = ctk.CTkTextbox(
            frame, font=("Times New Roman", 12),
            fg_color="#111", text_color="#ccc",
            corner_radius=0, state="disabled")
        self.console.grid(row=0, column=0, sticky="nsew")

        # colour tags
        self.console._textbox.tag_config("cmd",  foreground="#8acc40")  # green
        self.console._textbox.tag_config("info", foreground="#5599cc")  # blue
        self.console._textbox.tag_config("warn", foreground="#cc9933")  # orange
        self.console._textbox.tag_config("err",  foreground="#cc4444")  # red

    # ── Connect ──────────────────────────────────────────────
    def _connect(self):
        if self.mav:
            self._log("Already connected.", "warn"); return
        self.conn_btn.configure(state="disabled", text="Connecting…")
        self._log(f"Connecting → {SITL_UDP}", "info")

        def do_connect():
            try:
                mav = mavutil.mavlink_connection(SITL_UDP)
                self.after(0, lambda: self._log("Waiting for heartbeat…", "info"))
                mav.wait_heartbeat(timeout=10)
                self.mav = mav
                self.after(0, self._on_connected)
            except Exception as e:
                self.after(0, lambda err=e: self._on_failed(str(err)))

        threading.Thread(target=do_connect, daemon=True).start()

    def _on_connected(self):
        self._log(
            f"Heartbeat received  "
            f"sys={self.mav.target_system}  "
            f"comp={self.mav.target_component}", "cmd")
        self.status_lbl.configure(text="● Connected", text_color="#8acc40")
        self.conn_btn.configure(text="Connected", state="disabled",
                                fg_color="#1a5a00")

        # Build ActionsTab now, passing _log as callback
        if self.tab:
            self.tab.destroy()
        self.tab = ActionsTab(self, mav_connection=self.mav, log_fn=self._log)
        self.tab.grid(row=1, column=0, sticky="ew", padx=8, pady=8)

        # Start heartbeat sync loop
        self._running = True
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()

    def _on_failed(self, err):
        self._log(f"Connection failed: {err}", "err")
        self.conn_btn.configure(state="normal", text="Connect")

    # ── Heartbeat loop ───────────────────────────────────────
    def _heartbeat_loop(self):
        while self._running and self.mav:
            try:
                msg = self.mav.recv_match(type=["HEARTBEAT", "STATUSTEXT"], blocking=True, timeout=2)
                if msg is None:
                    continue

                if msg.get_type() == "HEARTBEAT":
                    armed = bool(
                        msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)

                    if self.tab:
                        self.after(0, lambda a=armed: self.tab.sync_arm_state(a))

                elif msg.get_type() == "STATUSTEXT":
                    severity = msg.severity
                    text = msg.text.strip()

                    level = "err" if severity <= 3 else \
                            "warn" if severity <= 5 else "info"

                    self.after(0, lambda t=text, l=level:
                            self._log(f"[FC] {t}", l))
                    
            except Exception as e:
                self.after(0, lambda err=e: self._log(f"Heartbeat error: {err}", "warn"))
                break

    # ── Helpers ──────────────────────────────────────────────
    def _log(self, msg: str, level: str = "info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self.console.configure(state="normal")
        self.console.insert("end", f"[{ts}] {msg}\n", level)
        self.console.see("end")
        self.console.configure(state="disabled")

    def _clear(self):
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")

    def _on_close(self):
        self._running = False
        self.destroy()


if __name__ == "__main__":
    app = ActionsTestWindow()
    app.mainloop()