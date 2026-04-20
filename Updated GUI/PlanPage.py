import tkinter as tk
from tkinter import ttk
import customtkinter as ctk
import tkintermapview


class PlanPage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="#1e1e1e")

        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=1)

        self._build_top_section()
        self._build_bottom_panel()

    # ================= TOP SECTION =================
    def _build_top_section(self):
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 4))
        top.grid_rowconfigure(0, weight=1)
        top.grid_columnconfigure(0, weight=10)
        top.grid_columnconfigure(1, weight=1)

        # MAP
        map_shell = ctk.CTkFrame(top, fg_color="#2a2a2a", corner_radius=0)
        map_shell.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        map_shell.grid_rowconfigure(0, weight=1)
        map_shell.grid_columnconfigure(0, weight=1)

        self.map = tkintermapview.TkinterMapView(map_shell, corner_radius=0)
        self.map.grid(row=0, column=0, sticky="nsew")
        self.map.set_position(19.0760, 72.8777)  # Mumbai
        self.map.set_zoom(12)

        # CLICK EVENT → ADD WAYPOINT
        self.map.add_left_click_map_command(self.add_waypoint)

        # SIDEBAR
        right_panel = ctk.CTkFrame(top, fg_color="#232323", width=60)
        right_panel.grid(row=0, column=1, sticky="ns")
        right_panel.grid_propagate(False)

        self._add_sidebar_controls(right_panel)

    def _add_sidebar_controls(self, parent):
        section = ctk.CTkFrame(parent, fg_color="transparent")
        section.pack(fill="both", expand=True, padx=2, pady=4)

        buttons = ["Load", "Read", "Write", "Start", "Clear"]
        for b in buttons:
            ctk.CTkButton(section, text=b, height=34).pack(fill="x", pady=4)

    # ================= BOTTOM PANEL =================
    def _build_bottom_panel(self):
        bottom = ctk.CTkFrame(self, fg_color="#202020")
        bottom.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        bottom.grid_columnconfigure(0, weight=1)

        # CONTROLS
        controls = ctk.CTkFrame(bottom, fg_color="#202020")
        controls.grid(row=0, column=0, sticky="ew", padx=6, pady=4)

        self._small_field(controls, "WP Radius", "30").grid(row=0, column=0, padx=5)
        self._small_field(controls, "Loiter Radius", "30").grid(row=0, column=1, padx=5)
        self._small_field(controls, "Default Alt", "50").grid(row=0, column=2, padx=5)

        # TABLE
        table_frame = ctk.CTkFrame(bottom)
        table_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=4)
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        columns = (
            "sel", "#", "Command", "Delay",
            "P1", "P2", "P3", "P4",
            "Lat", "Long", "Alt",
            "Delete", "Up", "Down", "Dist"
        )

        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=6)
        self.tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        widths = {
            "sel": 30, "#": 40, "Command": 120, "Delay": 50,
            "P1": 40, "P2": 40, "P3": 40, "P4": 40,
            "Lat": 100, "Long": 100, "Alt": 60,
            "Delete": 60, "Up": 40, "Down": 40, "Dist": 80
        }

        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=widths[col], anchor="center")
            
        # CLICK HANDLER FOR X / ↑ / ↓
        self.tree.bind("<Button-1>", self.handle_table_click)


    # ================= WAYPOINT LOGIC =================
    def add_waypoint(self, coords):
        lat, lon = coords

        # Add marker on map
        self.map.set_marker(lat, lon)

        # Row number
        index = len(self.tree.get_children()) + 1

        # Default altitude
        alt = 50

        self.tree.insert("", "end", values=(
            "",
            index,
            "WAYPOINT",
            0,
            0, 0, 0, 0,
            f"{lat:.6f}",
            f"{lon:.6f}",
            alt,
            "X",
            "⬆",
            "⬇",
            "0"
        ))
    
    #Table Handler
    def handle_table_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        row_id = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)

        if not row_id:
            return

        col_index = int(col.replace("#", "")) - 1
        columns = self.tree["columns"]
        col_name = columns[col_index]

        if col_name == "Delete":
            self.delete_waypoint(row_id)

        elif col_name == "Up":
            self.move_up(row_id)

        elif col_name == "Down":
            self.move_down(row_id)
                
    #Delete waypoint from map and table
    def delete_waypoint(self, row_id):
        self.tree.delete(row_id)
        self.map.delete_all_marker()
        self.redraw_markers()
        self.reindex_waypoints()
        
    #Move waypoint up/down
    def move_up(self, row_id):
        prev_id = self.tree.prev(row_id)
        if not prev_id:
            return

        current_values = self.tree.item(row_id, "values")
        prev_values = self.tree.item(prev_id, "values")

        # Swap values
        self.tree.item(row_id, values=prev_values)
        self.tree.item(prev_id, values=current_values)

        self.reindex_waypoints()
        self.refresh_map()
            
    def move_down(self, row_id):
        next_id = self.tree.next(row_id)
        if not next_id:
            return

        current_values = self.tree.item(row_id, "values")
        next_values = self.tree.item(next_id, "values")

        # Swap values
        self.tree.item(row_id, values=next_values)
        self.tree.item(next_id, values=current_values)

        self.reindex_waypoints()
        self.refresh_map()
    
    def refresh_map(self):
        self.map.delete_all_marker()

        for item in self.tree.get_children():
            values = self.tree.item(item, "values")
            lat = float(values[8])
            lon = float(values[9])
            self.map.set_marker(lat, lon)
                
    # ================= HELPERS =================
    def reindex_waypoints(self):
        for i, item in enumerate(self.tree.get_children(), start=1):
            values = list(self.tree.item(item, "values"))
            values[1] = i
            self.tree.item(item, values=values)

    def redraw_markers(self):
        for item in self.tree.get_children():
            values = self.tree.item(item, "values")
            lat = float(values[8])
            lon = float(values[9])
            self.map.set_marker(lat, lon)
    
    # ================= SMALL INPUT =================
    def _small_field(self, parent, label, value):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        ctk.CTkLabel(frame, text=label).pack(anchor="w")
        entry = ctk.CTkEntry(frame, width=60, height=24)
        entry.pack()
        entry.insert(0, value)
        return frame
