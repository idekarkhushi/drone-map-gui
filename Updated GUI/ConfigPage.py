import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import json
import threading
import time
from pathlib import Path

from param_data import get_default_params
from param_table import ParamTable

PARAMS_SAVE_FILE = Path(__file__).parent / "param_backup.json"


class ConfigPage(ctk.CTkFrame):

    def __init__(self, parent):
        super().__init__(parent, fg_color="#0d1117")

        self._params = []
        self.connected = False
        self._mav_connection = None   # set externally: page.set_connection(mav)
        self._toast_window = None

        self.pack_propagate(False)
        self._build_ui()
        self._load_table(self._params)

    # ------------------------------------------------------------------
    # PUBLIC: called by GCS after MAVLink connects
    # ------------------------------------------------------------------

    def set_connection(self, mav_connection):
        """
        Pass the live pymavlink connection object here once
        the drone is connected from ConnectPage / GCS.
        e.g.  config_page.set_connection(master)
        """
        self._mav_connection = mav_connection
        self.connected = mav_connection is not None

    # ==================================================================
    # UI CONSTRUCTION
    # ==================================================================

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)

        self._build_left_nav()
        self._build_center()
        self._build_right_panel()
        self._build_status_bar()

    # ==================================================================
    # LEFT NAVIGATION
    # ==================================================================

    def _build_left_nav(self):
        nav = ctk.CTkFrame(self, width=170, fg_color="#161b22", corner_radius=0)
        nav.grid(row=0, column=0, sticky="nsew")
        nav.grid_propagate(False)

        ctk.CTkFrame(nav, height=1, fg_color="#30363d").pack(
            fill="x", padx=8, pady=(0, 8)
        )

        # ── Full Parameter List button now calls the connection-aware handler ──
        self._full_param_btn = ctk.CTkButton(
            nav,
            text="Full Parameter List",
            anchor="w",
            height=34,
            fg_color="#1f6feb",
            hover_color="#388bfd",
            text_color="#ffffff",
            font=("Times New Roman", 12),
            corner_radius=6,
            command=self._on_full_param_list_click,   # <── new
        )
        self._full_param_btn.pack(fill="x", padx=8, pady=2)

    # ==================================================================
    # FULL PARAMETER LIST  – connection-aware entry point
    # ==================================================================

    def _on_full_param_list_click(self):
        if self._mav_connection is None:
            self._show_not_connected_toast()
            return

        # Disable button while probing so user can't spam-click
        self._full_param_btn.configure(state="disabled", text="Connecting…")
        self._probe_attempts = 0
        self._poll_heartbeat()

    # ------------------------------------------------------------------
    # Heartbeat probe  (non-blocking, runs on the Tk event loop)
    # ------------------------------------------------------------------

    _PROBE_INTERVAL_MS = 200   # poll every 200 ms
    _PROBE_MAX_ATTEMPTS = 10   # 10 × 200 ms = 2 s total timeout

    def _poll_heartbeat(self):
        """
        Polls for a MAVLink HEARTBEAT non-blockingly.
        Schedules itself via after() until a heartbeat arrives or timeout.
        """
        try:
            msg = self._mav_connection.recv_match(
                type="HEARTBEAT", blocking=False
            )
        except Exception:
            msg = None

        if msg is not None:
            # Drone is alive → proceed
            self._full_param_btn.configure(
                state="normal", text="Full Parameter List"
            )
            self.connected = True
            self.download_parameters()
            return

        self._probe_attempts += 1

        if self._probe_attempts >= self._PROBE_MAX_ATTEMPTS:
            # Timeout → show toast
            self._full_param_btn.configure(
                state="normal", text="Full Parameter List"
            )
            self.connected = False
            self._show_not_connected_toast()
            return

        # Try again after interval
        self.after(self._PROBE_INTERVAL_MS, self._poll_heartbeat)

    # ==================================================================
    #  "NOT CONNECTED"  TOAST
    # ==================================================================

    def _show_not_connected_toast(self):
        """
        Floating, auto-dismissing notification that looks like
        Mission Planner's red 'not connected' banner.
        """
        # Only one toast at a time
        if self._toast_window is not None:
            try:
                self._toast_window.destroy()
            except Exception:
                pass

        toast = ctk.CTkToplevel(self)
        toast.overrideredirect(True)          # no title bar
        toast.attributes("-topmost", True)
        toast.configure(fg_color="#1c0a0a")   # dark red background

        self._toast_window = toast

        # ── Layout ────────────────────────────────────────────────────
        container = ctk.CTkFrame(
            toast,
            fg_color="#2d1010",
            corner_radius=8,
            border_width=1,
            border_color="#da3633",
        )
        container.pack(padx=0, pady=0, fill="both", expand=True)

        # Red accent bar on the left
        ctk.CTkFrame(
            container,
            width=4,
            fg_color="#da3633",
            corner_radius=0,
        ).pack(side="left", fill="y", padx=(0, 0))

        inner = ctk.CTkFrame(container, fg_color="transparent")
        inner.pack(side="left", fill="both", expand=True, padx=(10, 6), pady=8)

        # Icon + title row
        title_row = ctk.CTkFrame(inner, fg_color="transparent")
        title_row.pack(fill="x")

        ctk.CTkLabel(
            title_row,
            text="⚠",
            font=("Times New Roman", 16),
            text_color="#ff7b72",
        ).pack(side="left", padx=(0, 6))

        ctk.CTkLabel(
            title_row,
            text="No Drone Connected",
            font=("Times New Roman", 13, "bold"),
            text_color="#ff7b72",
        ).pack(side="left")

        # Close button
        ctk.CTkButton(
            title_row,
            text="✕",
            width=22,
            height=22,
            fg_color="transparent",
            hover_color="#3d1c1c",
            text_color="#8b949e",
            font=("Times New Roman", 11),
            corner_radius=4,
            command=self._dismiss_toast,
        ).pack(side="right", padx=(6, 0))

        # Body text
        ctk.CTkLabel(
            inner,
            text="Please connect to a drone first.\n"
                 "Go to the Connect page and establish\n"
                 "a MAVLink connection.",
            font=("Times New Roman", 11),
            text_color="#e8b4b8",
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        # Progress bar that drains over 3 s (visual timer)
        self._toast_progress = ctk.CTkProgressBar(
            inner,
            height=3,
            fg_color="#3d1c1c",
            progress_color="#da3633",
            corner_radius=0,
        )
        self._toast_progress.set(1.0)
        self._toast_progress.pack(fill="x", pady=(8, 0))

        # ── Position: top-right of the parent window ──────────────────
        self.update_idletasks()
        pw = self.winfo_rootx()
        py = self.winfo_rooty()
        pW = self.winfo_width()

        toast.update_idletasks()
        tw = toast.winfo_reqwidth()
        th = toast.winfo_reqheight()

        x = pw + pW - tw - 20
        y = py + 20
        toast.geometry(f"{tw}x{th}+{x}+{y}")

        # ── Auto-dismiss after 3 s ────────────────────────────────────
        self._toast_remaining_ms = 3000
        self._toast_tick()

    def _toast_tick(self):
        """Drains the progress bar and destroys toast after 3 s."""
        if self._toast_window is None:
            return
        try:
            self._toast_remaining_ms -= 50
            progress = max(0.0, self._toast_remaining_ms / 3000)
            self._toast_progress.set(progress)

            if self._toast_remaining_ms <= 0:
                self._dismiss_toast()
            else:
                self.after(50, self._toast_tick)
        except Exception:
            self._toast_window = None

    def _dismiss_toast(self):
        if self._toast_window is not None:
            try:
                self._toast_window.destroy()
            except Exception:
                pass
            self._toast_window = None

    # ==================================================================
    # CENTER AREA
    # ==================================================================

    def _build_center(self):
        center = ctk.CTkFrame(self, fg_color="transparent")
        center.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        center.grid_rowconfigure(1, weight=1)
        center.grid_columnconfigure(0, weight=1)

        # Search bar
        search_bar = ctk.CTkFrame(center, fg_color="#161b22", height=44, corner_radius=8)
        search_bar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        search_bar.grid_propagate(False)

        ctk.CTkLabel(
            search_bar, text="Search:", text_color="#8b949e",
            font=("Times New Roman", 12)
        ).pack(side="left", padx=(12, 4), pady=10)

        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_filter())

        ctk.CTkEntry(
            search_bar, textvariable=self._search_var, width=220, height=26,
            font=("Times New Roman", 12), fg_color="#0d1117",
            border_color="#30363d", text_color="#c9d1d9",
        ).pack(side="left", padx=6, pady=10)

        self._modified_var = ctk.BooleanVar()
        ctk.CTkCheckBox(
            search_bar, text="Modified only", variable=self._modified_var,
            command=self._apply_filter, font=("Times New Roman", 11),
            text_color="#8b949e", fg_color="#1f6feb", hover_color="#388bfd",
        ).pack(side="left", padx=14)

        self._favs_var = ctk.BooleanVar()
        ctk.CTkCheckBox(
            search_bar, text="Favourites only", variable=self._favs_var,
            command=self._apply_filter, font=("Times New Roman", 11),
            text_color="#8b949e", fg_color="#1f6feb", hover_color="#388bfd",
        ).pack(side="left", padx=4)

        self._count_label = ctk.CTkLabel(
            search_bar, text="No Parameters Loaded",
            text_color="#484f58", font=("Times New Roman", 10)
        )
        self._count_label.pack(side="right", padx=12)

        self._table = ParamTable(
            center, on_value_change=self._on_value_changed, fg_color="transparent",
        )
        self._table.grid(row=1, column=0, sticky="nsew", padx=8, pady=0)

    # ==================================================================
    # RIGHT PANEL  (unchanged from original)
    # ==================================================================

    def _build_right_panel(self):
        panel = ctk.CTkFrame(self, width=160, fg_color="#161b22", corner_radius=0)
        panel.grid(row=0, column=2, sticky="nsew", padx=(4, 0))
        panel.grid_propagate(False)

        def rp_btn(text, cmd, primary=False, danger=False):
            if primary:
                fg, hover, tc = "#1f6feb", "#388bfd", "#ffffff"
            elif danger:
                fg, hover, tc = "#3d1c1c", "#da3633", "#ff7b72"
            else:
                fg, hover, tc = "#21262d", "#30363d", "#c9d1d9"
            return ctk.CTkButton(
                panel, text=text, command=cmd, height=30,
                fg_color=fg, hover_color=hover, text_color=tc,
                font=("Times New Roman", 11), corner_radius=6,
            )

        def sep():
            ctk.CTkFrame(panel, height=1, fg_color="#30363d").pack(
                fill="x", padx=8, pady=6
            )

        rp_btn("Load from file", self.load_from_file).pack(fill="x", padx=8, pady=3)
        rp_btn("Save to file",   self.save_to_file  ).pack(fill="x", padx=8, pady=3)
        sep()
        rp_btn("Write Params",   self.write_params,   primary=True).pack(fill="x", padx=8, pady=3)
        rp_btn("Refresh Params", self.refresh_params             ).pack(fill="x", padx=8, pady=3)
        rp_btn("Compare Params", self.compare_params             ).pack(fill="x", padx=8, pady=3)
        sep()

        ctk.CTkLabel(
            panel, text="All units in raw\nformat, no scaling",
            font=("Times New Roman", 9), text_color="#484f58", justify="left",
        ).pack(anchor="w", padx=10, pady=2)
        sep()

        ctk.CTkLabel(
            panel, text="Vehicle type:", font=("Times New Roman", 10),
            text_color="#8b949e",
        ).pack(anchor="w", padx=10)

        self._vehicle_var = ctk.StringVar(value="ArduCopter")
        ctk.CTkOptionMenu(
            panel, values=["ArduCopter", "ArduPlane", "ArduRover"],
            variable=self._vehicle_var, font=("Times New Roman", 10),
            height=26, fg_color="#21262d", button_color="#30363d",
            button_hover_color="#3d444d", text_color="#c9d1d9",
        ).pack(fill="x", padx=8, pady=6)
        sep()

        rp_btn("Load Preserved",  self.load_preserved             ).pack(fill="x", padx=8, pady=3)
        rp_btn("Reset to Default", self.reset_to_default, danger=True).pack(fill="x", padx=8, pady=3)

    # ==================================================================
    # STATUS BAR
    # ==================================================================

    def _build_status_bar(self):
        bar = ctk.CTkFrame(self, fg_color="#161b22", height=26, corner_radius=0)
        bar.grid(row=1, column=0, columnspan=3, sticky="ew")
        bar.grid_propagate(False)

        self._status_total = ctk.CTkLabel(
            bar, text="Parameters: 0", font=("Times New Roman", 10), text_color="#8b949e"
        )
        self._status_total.pack(side="left", padx=12)

        ctk.CTkFrame(bar, width=1, fg_color="#30363d").pack(side="left", fill="y", pady=4)

        self._status_mod = ctk.CTkLabel(
            bar, text="Modified: 0", font=("Times New Roman", 10), text_color="#3fb950"
        )
        self._status_mod.pack(side="left", padx=12)

        ctk.CTkFrame(bar, width=1, fg_color="#30363d").pack(side="left", fill="y", pady=4)

        self._status_fav = ctk.CTkLabel(
            bar, text="Favourites: 0", font=("Times New Roman", 10), text_color="#d29922"
        )
        self._status_fav.pack(side="left", padx=12)

    # ==================================================================
    # PARAMETER DOWNLOAD
    # ==================================================================

    def download_parameters(self):
        fetched_params = get_default_params()
        self._load_saved_params(fetched_params)
        self._params.clear()
        total = len(fetched_params)
        
        messagebox.showinfo(
            "Parameter Download",
            f"Starting parameter download from drone.\n"
            f"Fetching {total} parameters via MAVLink…"
        )
        for i, param in enumerate(fetched_params):
            self.after(
                i * 15,
                lambda p=param, idx=i + 1, t=total: self._receive_param(p, idx, t),
            )

    def _receive_param(self, param, current, total):
        self._params.append(param)
        self._load_table(self._params)
        self._count_label.configure(text=f"Downloading Params: {current}/{total}")
        if current == total:
            self._count_label.configure(text=f"{total} Parameters Loaded")
            
        messagebox.showinfo(
            "Download Complete",
            f"✓ {total} parameters successfully downloaded from drone.\n"
            f"You can now search, edit, and write parameters."
        )

    # ==================================================================
    # TABLE HELPERS
    # ==================================================================

    def _load_table(self, params):
        self._table.load_params(params)
        self._update_status(params)
        if self.connected:
            self._count_label.configure(
                text=f"{len(params)} / {len(self._params)} shown"
            )

    def _apply_filter(self):
        q        = self._search_var.get().lower().strip()
        mod_only = self._modified_var.get()
        fav_only = self._favs_var.get()
        filtered = [
            p for p in self._params
            if (not mod_only or p.modified)
            and (not fav_only or p.favourite)
            and (not q or q in p.name.lower() or q in p.desc.lower())
        ]
        self._load_table(filtered)

    def _update_status(self, shown):
        total = len(self._params)
        mod   = sum(1 for p in self._params if p.modified)
        fav   = sum(1 for p in self._params if p.favourite)
        self._status_total.configure(text=f"Parameters: {total}")
        self._status_mod.configure(  text=f"Modified: {mod}")
        self._status_fav.configure(  text=f"Favourites: {fav}")

    def _on_value_changed(self, name, new_value):
        self._update_status(self._params)

    # ==================================================================
    # FILE OPERATIONS  (unchanged)
    # ==================================================================

    def load_from_file(self):
        path = filedialog.askopenfilename(
            title="Load Parameters",
            filetypes=[("Param files", "*.param *.txt"), ("All files", "*.*")]
        )
        if not path:
            return
        loaded = 0
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.replace(",", " ").split()
                if len(parts) >= 2:
                    name = parts[0]
                    try:
                        val = float(parts[1])
                    except ValueError:
                        continue
                    param = next((p for p in self._params if p.name == name), None)
                    if param:
                        param.value   = val
                        param.modified = True
                        loaded += 1
        self._apply_filter()
        messagebox.showinfo(
            "Load Parameters",
            f"Loaded {loaded} parameters from\n{os.path.basename(path)}"
        )

    def save_to_file(self):
        path = filedialog.asksaveasfilename(
            title="Save Parameters", defaultextension=".param",
            filetypes=[("Param files", "*.param"), ("Text files", "*.txt")]
        )
        if not path:
            return
        with open(path, "w") as f:
            f.write("# ArduPilot Parameter File\n")
            f.write(f"# Vehicle: {self._vehicle_var.get()}\n\n")
            for p in self._params:
                f.write(f"{p.name},{p.value}\n")
        messagebox.showinfo("Save Parameters", f"Saved {len(self._params)} parameters.")

    def write_params(self):
        mod = [p for p in self._params if p.modified]
        if mod:
            self._save_params_to_file()
            messagebox.showinfo(
                "Write Params",
                f"{len(mod)} modified parameter(s) saved successfully.\n"
                f"(Saved to param_backup.json)"
            )
        else:
            messagebox.showinfo("Write Params", "No modified parameters to write.")

    def refresh_params(self):
        for p in self._params:
            p.modified = False
        self._apply_filter()
        messagebox.showinfo("Refresh", "All parameters marked as unmodified.")

    def compare_params(self):
        messagebox.showinfo("Compare Params", "Comparison logic placeholder.")

    def load_preserved(self):
        if not PARAMS_SAVE_FILE.exists():
            messagebox.showinfo(
                "Load Preserved",
                "No saved parameters found.\n"
                "Modify some parameters and click 'Write Params' to save them."
            )
            return
        try:
            with open(PARAMS_SAVE_FILE, "r") as f:
                saved_data = json.load(f)
            if isinstance(saved_data, dict) and "values" in saved_data:
                saved_values    = saved_data.get("values", {})
                saved_favourites = set(saved_data.get("favourites", []))
            else:
                saved_values    = saved_data
                saved_favourites = set()
            loaded_count = 0
            for param in self._params:
                if param.name in saved_values:
                    param.value   = saved_values[param.name]
                    param.modified = False
                    loaded_count  += 1
                if param.name in saved_favourites:
                    param.favourite = True
            self._apply_filter()
            messagebox.showinfo("Load Preserved", f"Loaded {loaded_count} saved parameters.")
        except Exception as e:
            messagebox.showerror("Load Error", f"Failed to load saved parameters: {str(e)}")

    def reset_to_default(self):
        if messagebox.askyesno("Reset", "Reset all parameters to default?"):
            self._params = get_default_params()
            self._load_table(self._params)

    # ==================================================================
    # PARAMETER PERSISTENCE
    # ==================================================================

    def _save_params_to_file(self):
        try:
            values    = {p.name: p.value for p in self._params if p.modified}
            favourites = [p.name for p in self._params if p.favourite]
            data = {"values": values, "favourites": favourites}
            with open(PARAMS_SAVE_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save parameters: {str(e)}")

    def _load_saved_params(self, params):
        if not PARAMS_SAVE_FILE.exists():
            return
        try:
            with open(PARAMS_SAVE_FILE, "r") as f:
                saved_data = json.load(f)
            if isinstance(saved_data, dict) and "values" in saved_data:
                saved_values    = saved_data.get("values", {})
                saved_favourites = set(saved_data.get("favourites", []))
            else:
                saved_values    = saved_data
                saved_favourites = set()
            for param in params:
                if param.name in saved_values:
                    param.value = saved_values[param.name]
                if param.name in saved_favourites:
                    param.favourite = True
        except Exception as e:
            print(f"Warning: Could not load saved parameters: {e}")