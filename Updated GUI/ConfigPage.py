import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import json
from pathlib import Path

from param_data import get_default_params
from param_table import ParamTable

# File to persist modified parameters
PARAMS_SAVE_FILE = Path(__file__).parent / "param_backup.json"


class ConfigPage(ctk.CTkFrame):

    def __init__(self, parent):
        super().__init__(parent, fg_color="#0d1117")

        # ---------------------------------------------------------
        # IMPORTANT CHANGE
        # ---------------------------------------------------------
        # Mission Planner style logic:
        #
        # Parameters should NOT load immediately.
        # They should only appear AFTER connecting to drone.
        #
        # So start with empty parameter list.
        # ---------------------------------------------------------

        self._params = []

        # Drone connection state
        self.connected = False

        self.pack_propagate(False)

        self._build_ui()

        # Load empty table initially
        self._load_table(self._params)

    # =============================================================
    # UI CONSTRUCTION
    # =============================================================

    def _build_ui(self):

        # Outer layout
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)

        self._build_left_nav()
        self._build_center()
        self._build_right_panel()
        self._build_status_bar()

    # =============================================================
    # LEFT NAVIGATION
    # =============================================================

    def _build_left_nav(self):

        nav = ctk.CTkFrame(
            self,
            width=170,
            fg_color="#161b22",
            corner_radius=0
        )

        nav.grid(row=0, column=0, sticky="nsew")
        nav.grid_propagate(False)

        ctk.CTkLabel(
            nav,
            text="CONFIG",
            font=("Arial", 12, "bold"),
            text_color="#58a6ff",
        ).pack(anchor="w", padx=12, pady=(14, 8))

        ctk.CTkFrame(
            nav,
            height=1,
            fg_color="#30363d"
        ).pack(fill="x", padx=8, pady=(0, 8))

        ctk.CTkButton(
            nav,
            text="Full Parameter List",
            anchor="w",
            height=34,
            fg_color="#1f6feb",
            hover_color="#388bfd",
            text_color="#ffffff",
            font=("Arial", 12),
            corner_radius=6,
        ).pack(fill="x", padx=8, pady=2)

    # =============================================================
    # CENTER AREA
    # =============================================================

    def _build_center(self):

        center = ctk.CTkFrame(self, fg_color="transparent")

        center.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(4, 0)
        )

        center.grid_rowconfigure(1, weight=1)
        center.grid_columnconfigure(0, weight=1)

        # ---------------------------------------------------------
        # SEARCH BAR
        # ---------------------------------------------------------

        search_bar = ctk.CTkFrame(
            center,
            fg_color="#161b22",
            height=44,
            corner_radius=8
        )

        search_bar.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=8,
            pady=(8, 4)
        )

        search_bar.grid_propagate(False)

        ctk.CTkLabel(
            search_bar,
            text="Search:",
            text_color="#8b949e",
            font=("Arial", 12)
        ).pack(side="left", padx=(12, 4), pady=10)

        self._search_var = ctk.StringVar()

        self._search_var.trace_add(
            "write",
            lambda *_: self._apply_filter()
        )

        ctk.CTkEntry(
            search_bar,
            textvariable=self._search_var,
            width=220,
            height=26,
            font=("Arial", 12),
            fg_color="#0d1117",
            border_color="#30363d",
            text_color="#c9d1d9",
        ).pack(side="left", padx=6, pady=10)

        # Modified checkbox
        self._modified_var = ctk.BooleanVar()

        ctk.CTkCheckBox(
            search_bar,
            text="Modified only",
            variable=self._modified_var,
            command=self._apply_filter,
            font=("Arial", 11),
            text_color="#8b949e",
            fg_color="#1f6feb",
            hover_color="#388bfd",
        ).pack(side="left", padx=14)

        # Favourite checkbox
        self._favs_var = ctk.BooleanVar()

        ctk.CTkCheckBox(
            search_bar,
            text="Favourites only",
            variable=self._favs_var,
            command=self._apply_filter,
            font=("Arial", 11),
            text_color="#8b949e",
            fg_color="#1f6feb",
            hover_color="#388bfd",
        ).pack(side="left", padx=4)

        # Count label
        self._count_label = ctk.CTkLabel(
            search_bar,
            text="No Parameters Loaded",
            text_color="#484f58",
            font=("Arial", 10)
        )

        self._count_label.pack(side="right", padx=12)

        # ---------------------------------------------------------
        # PARAMETER TABLE
        # ---------------------------------------------------------

        self._table = ParamTable(
            center,
            on_value_change=self._on_value_changed,
            fg_color="transparent",
        )

        self._table.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=8,
            pady=0
        )

    # =============================================================
    # RIGHT PANEL
    # =============================================================

    def _build_right_panel(self):

        panel = ctk.CTkFrame(
            self,
            width=160,
            fg_color="#161b22",
            corner_radius=0
        )

        panel.grid(row=0, column=2, sticky="nsew", padx=(4, 0))
        panel.grid_propagate(False)

        # ---------------------------------------------------------
        # Helper button creator
        # ---------------------------------------------------------

        def rp_btn(text, cmd, primary=False, danger=False):

            if primary:
                fg, hover, tc = "#1f6feb", "#388bfd", "#ffffff"

            elif danger:
                fg, hover, tc = "#3d1c1c", "#da3633", "#ff7b72"

            else:
                fg, hover, tc = "#21262d", "#30363d", "#c9d1d9"

            return ctk.CTkButton(
                panel,
                text=text,
                command=cmd,
                height=30,
                fg_color=fg,
                hover_color=hover,
                text_color=tc,
                font=("Arial", 11),
                corner_radius=6,
            )

        # Separator helper
        def sep():
            ctk.CTkFrame(
                panel,
                height=1,
                fg_color="#30363d"
            ).pack(fill="x", padx=8, pady=6)

        # ---------------------------------------------------------
        # CONNECT BUTTON
        # ---------------------------------------------------------
        # This simulates Mission Planner connection flow
        # ---------------------------------------------------------

        rp_btn(
            "Connect Drone",
            self.connect_drone,
            primary=True
        ).pack(fill="x", padx=8, pady=(12, 3))

        # File actions
        rp_btn(
            "Load from file",
            self.load_from_file
        ).pack(fill="x", padx=8, pady=3)

        rp_btn(
            "Save to file",
            self.save_to_file
        ).pack(fill="x", padx=8, pady=3)

        sep()

        # Vehicle actions
        rp_btn(
            "Write Params",
            self.write_params,
            primary=True
        ).pack(fill="x", padx=8, pady=3)

        rp_btn(
            "Refresh Params",
            self.refresh_params
        ).pack(fill="x", padx=8, pady=3)

        rp_btn(
            "Compare Params",
            self.compare_params
        ).pack(fill="x", padx=8, pady=3)

        sep()

        ctk.CTkLabel(
            panel,
            text="All units in raw\nformat, no scaling",
            font=("Arial", 9),
            text_color="#484f58",
            justify="left",
        ).pack(anchor="w", padx=10, pady=2)

        sep()

        # Vehicle selection
        ctk.CTkLabel(
            panel,
            text="Vehicle type:",
            font=("Arial", 10),
            text_color="#8b949e",
        ).pack(anchor="w", padx=10)

        self._vehicle_var = ctk.StringVar(value="ArduCopter")

        ctk.CTkOptionMenu(
            panel,
            values=["ArduCopter", "ArduPlane", "ArduRover"],
            variable=self._vehicle_var,
            font=("Arial", 10),
            height=26,
            fg_color="#21262d",
            button_color="#30363d",
            button_hover_color="#3d444d",
            text_color="#c9d1d9",
        ).pack(fill="x", padx=8, pady=6)

        sep()

        rp_btn(
            "Load Preserved",
            self.load_preserved
        ).pack(fill="x", padx=8, pady=3)

        rp_btn(
            "Reset to Default",
            self.reset_to_default,
            danger=True
        ).pack(fill="x", padx=8, pady=3)

    # =============================================================
    # STATUS BAR
    # =============================================================

    def _build_status_bar(self):

        bar = ctk.CTkFrame(
            self,
            fg_color="#161b22",
            height=26,
            corner_radius=0
        )

        bar.grid(row=1, column=0, columnspan=3, sticky="ew")
        bar.grid_propagate(False)

        self._status_total = ctk.CTkLabel(
            bar,
            text="Parameters: 0",
            font=("Arial", 10),
            text_color="#8b949e"
        )

        self._status_total.pack(side="left", padx=12)

        ctk.CTkFrame(
            bar,
            width=1,
            fg_color="#30363d"
        ).pack(side="left", fill="y", pady=4)

        self._status_mod = ctk.CTkLabel(
            bar,
            text="Modified: 0",
            font=("Arial", 10),
            text_color="#3fb950"
        )

        self._status_mod.pack(side="left", padx=12)

        ctk.CTkFrame(
            bar,
            width=1,
            fg_color="#30363d"
        ).pack(side="left", fill="y", pady=4)

        self._status_fav = ctk.CTkLabel(
            bar,
            text="Favourites: 0",
            font=("Arial", 10),
            text_color="#d29922"
        )

        self._status_fav.pack(side="left", padx=12)

    # =============================================================
    # DRONE CONNECTION LOGIC
    # =============================================================

    def connect_drone(self):

        """
        Simulates:
        1. Drone connection
        2. Parameter download
        """

        if self.connected:
            messagebox.showinfo(
                "Connection",
                "Drone already connected."
            )
            return

        self.connected = True

        messagebox.showinfo(
            "Connection",
            "Drone connected successfully.\n"
            "Starting parameter download..."
        )

        # Start downloading params
        self.download_parameters()

    # =============================================================
    # PARAMETER DOWNLOAD
    # =============================================================

    def download_parameters(self):

        """
        Simulates Mission Planner downloading parameters
        one-by-one using MAVLink PARAM_VALUE messages.
        Also loads any previously saved modifications.
        """

        fetched_params = get_default_params()

        # Load any previously saved parameter values
        self._load_saved_params(fetched_params)

        self._params.clear()

        total = len(fetched_params)

        for i, param in enumerate(fetched_params):

            # Simulate progressive MAVLink param reception
            self.after(
                i * 15,
                lambda p=param, idx=i + 1, t=total:
                self._receive_param(p, idx, t)
            )

    # =============================================================
    # PARAM RECEIVER
    # =============================================================

    def _receive_param(self, param, current, total):

        """
        Called whenever a parameter arrives from drone.
        """

        self._params.append(param)

        # Reload table dynamically
        self._load_table(self._params)

        # Update progress text
        self._count_label.configure(
            text=f"Downloading Params: {current}/{total}"
        )

        # Download complete
        if current == total:

            self._count_label.configure(
                text=f"{total} Parameters Loaded"
            )

            messagebox.showinfo(
                "Parameters",
                f"{total} parameters downloaded successfully."
            )

    # =============================================================
    # TABLE HELPERS
    # =============================================================

    def _load_table(self, params):

        self._table.load_params(params)

        self._update_status(params)

        if self.connected:
            self._count_label.configure(
                text=f"{len(params)} / {len(self._params)} shown"
            )

    def _apply_filter(self):

        q = self._search_var.get().lower().strip()

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

        mod = sum(1 for p in self._params if p.modified)

        fav = sum(1 for p in self._params if p.favourite)

        self._status_total.configure(
            text=f"Parameters: {total}"
        )

        self._status_mod.configure(
            text=f"Modified: {mod}"
        )

        self._status_fav.configure(
            text=f"Favourites: {fav}"
        )

    # =============================================================
    # PARAMETER CHANGED
    # =============================================================

    def _on_value_changed(self, name, new_value):

        self._update_status(self._params)

    # =============================================================
    # FILE OPERATIONS
    # =============================================================

    def load_from_file(self):

        path = filedialog.askopenfilename(
            title="Load Parameters",
            filetypes=[
                ("Param files", "*.param *.txt"),
                ("All files", "*.*")
            ]
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

                    param = next(
                        (p for p in self._params if p.name == name),
                        None
                    )

                    if param:
                        param.value = val
                        param.modified = True
                        loaded += 1

        self._apply_filter()

        messagebox.showinfo(
            "Load Parameters",
            f"Loaded {loaded} parameters from\n"
            f"{os.path.basename(path)}"
        )

    def save_to_file(self):

        path = filedialog.asksaveasfilename(
            title="Save Parameters",
            defaultextension=".param",
            filetypes=[
                ("Param files", "*.param"),
                ("Text files", "*.txt")
            ]
        )

        if not path:
            return

        with open(path, "w") as f:

            f.write("# ArduPilot Parameter File\n")

            f.write(
                f"# Vehicle: {self._vehicle_var.get()}\n\n"
            )

            for p in self._params:
                f.write(f"{p.name},{p.value}\n")

        messagebox.showinfo(
            "Save Parameters",
            f"Saved {len(self._params)} parameters."
        )

    def write_params(self):

        mod = [p for p in self._params if p.modified]

        if mod:
            # Save modified values and favourite flags to persistent storage
            self._save_params_to_file()
            
            messagebox.showinfo(
                "Write Params",
                f"{len(mod)} modified parameter(s) "
                f"saved successfully.\n"
                f"(Saved to param_backup.json)"
            )

        else:
            messagebox.showinfo(
                "Write Params",
                "No modified parameters to write."
            )

    def refresh_params(self):

        for p in self._params:
            p.modified = False

        self._apply_filter()

        messagebox.showinfo(
            "Refresh",
            "All parameters marked as unmodified."
        )

    def compare_params(self):

        messagebox.showinfo(
            "Compare Params",
            "Comparison logic placeholder."
        )

    def load_preserved(self):
        """
        Load previously saved parameter modifications back into the current session.
        """
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

            # Support both old flat mapping format and the new structured format
            if isinstance(saved_data, dict) and "values" in saved_data:
                saved_values = saved_data.get("values", {})
                saved_favourites = set(saved_data.get("favourites", []))
            else:
                saved_values = saved_data
                saved_favourites = set()
            
            loaded_count = 0
            for param in self._params:
                if param.name in saved_values:
                    param.value = saved_values[param.name]
                    param.modified = False
                    loaded_count += 1
                if param.name in saved_favourites:
                    param.favourite = True
            
            self._apply_filter()
            
            messagebox.showinfo(
                "Load Preserved",
                f"Loaded {loaded_count} saved parameters."
            )
        except Exception as e:
            messagebox.showerror(
                "Load Error",
                f"Failed to load saved parameters: {str(e)}"
            )

    def reset_to_default(self):

        if messagebox.askyesno(
                "Reset",
                "Reset all parameters to default?"):

            self._params = get_default_params()

            self._load_table(self._params)

    # =============================================================
    # PARAMETER PERSISTENCE (SAVE/LOAD)
    # =============================================================

    def _save_params_to_file(self):
        """
        Save modified parameters to a JSON file so they persist
        across application restarts.
        """
        try:
            values = {
                p.name: p.value
                for p in self._params
                if p.modified
            }
            favourites = [p.name for p in self._params if p.favourite]

            data = {
                "values": values,
                "favourites": favourites,
            }

            with open(PARAMS_SAVE_FILE, "w") as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            messagebox.showerror(
                "Save Error",
                f"Failed to save parameters: {str(e)}"
            )

    def _load_saved_params(self, params):
        """
        Load previously saved parameter values from JSON file
        and apply them to the parameter list.
        
        Args:
            params: List of Parameter objects to update with saved values
        """
        if not PARAMS_SAVE_FILE.exists():
            return  # No saved parameters yet
            
        try:
            with open(PARAMS_SAVE_FILE, "r") as f:
                saved_data = json.load(f)

            if isinstance(saved_data, dict) and "values" in saved_data:
                saved_values = saved_data.get("values", {})
                saved_favourites = set(saved_data.get("favourites", []))
            else:
                saved_values = saved_data
                saved_favourites = set()
            
            # Apply saved values and favourite flags to parameters
            for param in params:
                if param.name in saved_values:
                    param.value = saved_values[param.name]
                if param.name in saved_favourites:
                    param.favourite = True
                    # Do not mark as modified for loading saved data
                    # param.modified = False
                    
        except Exception as e:
            # Silently ignore load errors (corrupted file, etc.)
            print(f"Warning: Could not load saved parameters: {e}")