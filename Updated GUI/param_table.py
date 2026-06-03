# param_table.py

import tkinter as tk
from tkinter import ttk
import customtkinter as ctk

# Column config: (header text, width, stretch)
COLUMNS = [
    ("Command",  180, False),
    ("Value",     80, False),
    ("Units",     60, False),
    ("Options",  160, False),
    ("Desc",     400, True),
    ("Fav",       40, False),
]

class ParamTable(ctk.CTkFrame):
    def __init__(self, master, on_value_change=None, **kwargs):
        super().__init__(master, **kwargs)
        self.on_value_change = on_value_change
        self._params = []           # currently displayed Parameter objects
        self._sort_col = "Command"
        self._sort_asc = True
        self._editing_item = None

        self._build_table()

    def _build_table(self):
        # Style for the treeview (dark Mission Planner look)
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Params.Treeview",
            background="#12192a",
            foreground="#c8d0d8",
            fieldbackground="#12192a",
            rowheight=22,
            font=("Times New Roman", 10),
            borderwidth=0,
        )
        style.configure("Params.Treeview.Heading",
            background="#0f1117",
            foreground="#8a9ab0",
            font=("Times New Roman", 10, "bold"),
            relief="flat",
        )
        style.map("Params.Treeview",
            background=[("selected", "#1e3a5a")],
            foreground=[("selected", "#ffffff")],
        )
        style.map("Params.Treeview.Heading",
            background=[("active", "#1a2236")],
        )

        # Define tag colors
        col_ids = [c[0] for c in COLUMNS]
        self._tree = ttk.Treeview(
            self,
            columns=col_ids,
            show="headings",
            style="Params.Treeview",
            selectmode="browse",
        )

        # Set up each column header with sort on click
        for name, width, stretch in COLUMNS:
            self._tree.heading(name, text=name,
                command=lambda c=name: self._sort_by(c))
            self._tree.column(name, width=width,
                stretch=tk.YES if stretch else tk.NO,
                anchor="w")

        # Row color tags
        self._tree.tag_configure("even",     background="#12192a")
        self._tree.tag_configure("odd",      background="#161e30")
        self._tree.tag_configure("modified", background="#1a2a1a")
        self._tree.tag_configure("fav",      foreground="#ffaa00")

        # Scrollbars
        vsb = ttk.Scrollbar(self, orient="vertical",   command=self._tree.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        # Layout
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Double-click to edit value
        self._tree.bind("<Double-1>", self._on_double_click)

    def load_params(self, params):
        """Populate the table with a list of Parameter objects."""
        self._params = params
        self._refresh()

    def _refresh(self):
        """Clear and re-draw all rows."""
        for item in self._tree.get_children():
            self._tree.delete(item)

        for i, p in enumerate(self._params):
            tags = []
            tags.append("even" if i % 2 == 0 else "odd")
            if p.modified:
                tags = ["modified"]   # override row color
            if p.favourite:
                tags.append("fav")

            fav_mark = "★" if p.favourite else "☆"
            self._tree.insert("", "end", iid=p.name, values=(
                p.name,
                p.value,
                p.units,
                p.options,
                p.desc,
                fav_mark,
            ), tags=tags)

    def _sort_by(self, col):
        """Sort table by column header click."""
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True

        reverse = not self._sort_asc
        col_map = {"Command": "name", "Value": "value",
                   "Units": "units", "Options": "options",
                   "Desc": "desc", "Fav": "favourite"}
        attr = col_map.get(col, "name")

        self._params.sort(
            key=lambda p: str(getattr(p, attr)).lower(),
            reverse=reverse
        )
        self._refresh()

    def _on_double_click(self, event):
        """Open an inline edit Entry when user double-clicks the Value column."""
        region = self._tree.identify_region(event.x, event.y)
        col    = self._tree.identify_column(event.x)
        item   = self._tree.identify_row(event.y)

        if region != "cell" or not item:
            return

        if col == "#6":
            # Toggle favourites by clicking the star column
            self._on_fav_click(item)
            return

        if col != "#2":
            return   # only Value column is editable

        # Get cell bounding box
        x, y, w, h = self._tree.bbox(item, col)
        param = next((p for p in self._params if p.name == item), None)
        if not param:
            return

        # Create floating Entry widget on top of the cell
        entry = tk.Entry(self._tree,
            font=("Times New Roman", 10),
            bg="#1a3a1a", fg="#90ee90",
            insertbackground="#90ee90",
            relief="flat", bd=1,
        )
        entry.place(x=x, y=y, width=w, height=h)
        entry.insert(0, str(param.value))
        entry.select_range(0, "end")
        entry.focus_set()

        def commit(e=None):
            new_text = entry.get()
            entry.destroy()
            try:
                new_val = float(new_text)
            except ValueError:
                return  # invalid input, ignore
            if new_val != param.value:
                param.value = new_val
                param.modified = True
                if self.on_value_change:
                    self.on_value_change(param.name, new_val)
            self._refresh()

        entry.bind("<Return>",  commit)
        entry.bind("<FocusOut>", commit)
        entry.bind("<Escape>",  lambda e: entry.destroy())

    def _on_fav_click(self, item):
        param = next((p for p in self._params if p.name == item), None)
        if not param:
            return
        param.favourite = not param.favourite
        param.modified = True
        if self.on_value_change:
            self.on_value_change(param.name, param.value)
        self._refresh()

    def toggle_favourite(self, name):
        """Toggle the favourite flag for a parameter by name."""
        param = next((p for p in self._params if p.name == name), None)
        if param:
            param.favourite = not param.favourite
            param.modified = True
            if self.on_value_change:
                self.on_value_change(param.name, param.value)
            self._refresh()

    def get_params(self):
        return self._params