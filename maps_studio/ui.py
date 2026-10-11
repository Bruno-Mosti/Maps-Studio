"""Tkinter interface for Maps Studio. All map rules live in core.py and all file handling in storage.py."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Optional

from . import APP_NAME, VERSION
from .core import (BUILTIN_SIZES, CHANGED_NAME, MAX_SIDE, MIN_SIDE, STYLES, EditSession, MapError,
                   blank, check_name, default_endpoints, generate, line_cells, route_preview)
from .dnd import enable_drop
from .storage import SaveError, Workspace

C = {
    "bg": "#0e1621", "panel": "#141e2b", "card": "#1c293a", "card_hi": "#24354b", "line": "#2a3a4f",
    "text": "#e8eef6", "muted": "#93a5ba", "accent": "#5aa9ff", "accent_bg": "#1d3a5e",
    "danger": "#f07a82", "danger_bg": "#3b222b", "ok": "#46d39a", "warn": "#f2b84b", "warn_bg": "#3a3020",
    "canvas": "#e5eaf0", "free": "#fbfcfd", "wall": "#243145", "added": "#e0832b", "grid": "#cdd6e1",
    "start": "#119c69", "goal": "#d9475a", "route": "#1f78de", "axis": "#56667a",
}
PAD = 36
BASE_CELL = 24
MIN_CELL, MAX_CELL = 4, 72
TOOL_LABELS = [("wall", "Wall", "1"), ("erase", "Erase", "2"), ("start", "Start", "3"), ("goal", "Goal", "4")]


def pick_font(root) -> str:
    families = set(tkfont.families(root))
    for name in ("Segoe UI", "Inter", "Noto Sans", "Ubuntu", "Cantarell", "DejaVu Sans", "Helvetica"):
        if name in families:
            return name
    return "TkDefaultFont"


class Tooltip:
    def __init__(self, widget, text: str, font):
        self.widget, self.text, self.font, self.tip = widget, text, font, None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def show(self, _event=None):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 8
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, bg="#0a0f17", fg=C["text"], font=self.font, padx=8, pady=4,
                 justify="left", wraplength=320).pack()

    def hide(self, _event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class Studio:
    def __init__(self, root: tk.Tk, workspace: Workspace, read_only: bool = False, dnd: bool = False):
        self.root, self.ws, self.read_only, self.dnd_ready = root, workspace, read_only, dnd
        self.family = pick_font(root)
        self.session: Optional[EditSession] = None
        self.name: Optional[str] = None
        self.note = ""
        self.unsaved = False
        self.cells: list[list[int]] = []
        self.zoom = BASE_CELL
        self.tool = tk.StringVar(value="wall")
        self.show_route = tk.BooleanVar(value=True)
        self.show_grid = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Ready")
        self.route_text = tk.StringVar(value="")
        self.stats_text = tk.StringVar(value="")
        self.pointer = tk.StringVar(value="")
        self.drag_tool: Optional[str] = None
        self.last_cell = None
        self.toggle_pending = None
        self.lib_names: list[str] = []
        self._selecting = False
        self.tool_buttons: dict[str, tk.Button] = {}
        self.edit_buttons: list[tk.Button] = []

        root.title(f"{APP_NAME} {VERSION}")
        screen_w, screen_h = root.winfo_screenwidth(), root.winfo_screenheight()
        width, height = min(1320, screen_w - 60), min(860, screen_h - 90)
        root.geometry(f"{width}x{height}+{max(0, (screen_w - width) // 2)}+{max(0, (screen_h - height) // 3)}")
        root.minsize(900, 600)
        root.configure(bg=C["bg"])
        self._style()
        self._build()
        self._bind_keys()
        self.refresh_library()
        self.open_first_or_welcome()
        if self.ws.recovered:
            messagebox.showinfo("Recovered", "\n".join(self.ws.recovered), parent=root)
        root.protocol("WM_DELETE_WINDOW", self.close)

    # ================================================================ widgets
    def font(self, size=10, bold=False):
        return (self.family, size, "bold" if bold else "normal")

    def _style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TScrollbar", background=C["card"], troughcolor=C["panel"], bordercolor=C["panel"],
                        arrowcolor=C["muted"], lightcolor=C["card"], darkcolor=C["card"])
        style.configure("Treeview", background=C["card"], fieldbackground=C["card"], foreground=C["text"],
                        bordercolor=C["line"], rowheight=24, font=self.font(10))
        style.configure("Treeview.Heading", background=C["panel"], foreground=C["muted"], font=self.font(9, True))
        style.map("Treeview", background=[("selected", C["accent_bg"])])
        style.configure("TCombobox", fieldbackground=C["card"], background=C["card"], foreground=C["text"],
                        arrowcolor=C["text"])
        style.map("TCombobox", fieldbackground=[("readonly", C["card"])], foreground=[("readonly", C["text"])],
                  selectbackground=[("readonly", C["card"])], selectforeground=[("readonly", C["text"])])
        style.configure("Zoom.Horizontal.TScale", background=C["accent"], troughcolor=C["line"],
                        bordercolor=C["panel"], lightcolor=C["accent"], darkcolor=C["accent"])
        self.root.option_add("*TCombobox*Listbox.background", C["card"])
        self.root.option_add("*TCombobox*Listbox.foreground", C["text"])

    def label(self, parent, text="", size=10, color=None, bold=False, **kw):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color or C["text"],
                        font=self.font(size, bold), **kw)

    def button(self, parent, text, command, kind="normal", tip="", width=None, size=10):
        colors = {"normal": (C["card"], C["card_hi"], C["text"]),
                  "primary": (C["accent_bg"], "#27507f", C["text"]),
                  "danger": (C["danger_bg"], "#4d2a35", C["danger"]),
                  "quiet": (parent.cget("bg"), C["card"], C["text"])}[kind]
        b = tk.Button(parent, text=text, command=command, bg=colors[0], fg=colors[2], activebackground=colors[1],
                      activeforeground=C["text"], disabledforeground="#5b6b7e", relief="flat", bd=0,
                      highlightthickness=0, cursor="hand2", font=self.font(size), padx=10, pady=6)
        if width:
            b.configure(width=width)
        b._colors = colors
        b.bind("<Enter>", lambda e: b.configure(bg=b._colors[1]) if str(b["state"]) != "disabled" else None)
        b.bind("<Leave>", lambda e: b.configure(bg=getattr(b, "_bg_now", b._colors[0])))
        if tip:
            Tooltip(b, tip, self.font(9))
        return b

    def section(self, parent, text):
        self.label(parent, text, 9, C["muted"], True).pack(anchor="w", pady=(14, 6))

    def _build(self):
        # ---- top bar
        top = tk.Frame(self.root, bg=C["bg"], height=54)
        top.pack(fill="x", side="top")
        top.pack_propagate(False)
        # Display the same uploaded logo used for the taskbar and executable icon.
        # The 512px PNG is subsampled by Tk itself, so no imaging dependency is needed at runtime.
        app_icon = getattr(self.root, "_icon", None)
        if app_icon is not None:
            self._header_logo = app_icon.subsample(16, 16)
            tk.Label(top, image=self._header_logo, bg=C["bg"], bd=0).pack(side="left", padx=(14, 10))
        else:
            self.label(top, "▦", 16, C["accent"], True).pack(side="left", padx=(18, 8))
        self.label(top, "Maps Studio", 14, bold=True).pack(side="left")
        self.label(top, f"  v{VERSION}", 9, C["muted"]).pack(side="left", pady=(4, 0))
        right = tk.Frame(top, bg=C["bg"])
        right.pack(side="right", padx=12)
        self.top_buttons = {}
        for key, text, cmd, tip in [
            ("help", "Help", self.show_help, "Shortcuts, file format and where your maps are stored"),
            ("folder", "Open folder", self.open_folder, "Open the folder that holds your editable maps"),
            ("export", "Export ▾", self.export_menu, "Copy maps to a folder or a ZIP to share"),
            ("import", "Import ▾", self.import_menu, "Add maps from CSV/JSON files, a ZIP or a folder"),
            ("new", "New map…", self.new_map, "Create an empty map or generate a draft"),
        ]:
            b = self.button(right, text, cmd, "primary" if key == "new" else "normal", tip)
            b.pack(side="right", padx=3)
            self.top_buttons[key] = b
        if self.read_only:
            tk.Label(top, text="  READ-ONLY · Maps Studio is already open in another window  ", bg=C["warn_bg"],
                     fg=C["warn"], font=self.font(9, True)).pack(side="right", padx=10)

        body = tk.Frame(self.root, bg=C["bg"])
        body.pack(fill="both", expand=True)

        # ---- sidebar
        side = tk.Frame(body, bg=C["panel"], width=262)
        side.pack(side="left", fill="y", padx=(10, 0), pady=(0, 10))
        side.pack_propagate(False)
        panel = tk.Frame(side, bg=C["panel"])
        panel.pack(fill="both", expand=True, padx=14, pady=4)
        self.sidebar = side

        self.section(panel, "MAP LIBRARY")
        lib_frame = tk.Frame(panel, bg=C["line"], padx=1, pady=1)
        lib_frame.pack(fill="x")
        self.library = tk.Listbox(lib_frame, height=7, bg=C["card"], fg=C["text"], selectbackground=C["accent_bg"],
                                  selectforeground=C["text"], highlightthickness=0, bd=0, activestyle="none",
                                  font=self.font(10), exportselection=False)
        self.library.pack(fill="x")
        self.library.bind("<<ListboxSelect>>", self._library_selected)
        row = tk.Frame(panel, bg=C["panel"])
        row.pack(fill="x", pady=(6, 0))
        self.copy_btn = self.button(row, "Duplicate…", self.duplicate, tip="Save a copy of this map under a new name", size=9)
        self.copy_btn.pack(side="left", expand=True, fill="x", padx=(0, 3))
        self.remove_btn = self.button(row, "Remove…", self.remove_map, "danger",
                                      "Move a custom map to the trash folder (coursework maps are protected)", size=9)
        self.remove_btn.pack(side="left", expand=True, fill="x", padx=(3, 0))

        self.section(panel, "THIS MAP")
        self.label(panel, textvariable=self.stats_text, size=9, color=C["muted"], justify="left",
                   wraplength=230).pack(anchor="w")

        self.section(panel, "TOOLS")
        grid = tk.Frame(panel, bg=C["panel"])
        grid.pack(fill="x")
        tips = {"wall": "Draw walls (drag to paint lines)", "erase": "Remove walls, Start or Goal. Right-click also erases",
                "start": "Place Start (click it again to remove)", "goal": "Place Goal (click it again to remove)"}
        for i, (key, text, shortcut) in enumerate(TOOL_LABELS):
            b = self.button(grid, f"{text}  {shortcut}", lambda k=key: self.choose_tool(k), tip=tips[key])
            b.grid(row=i // 2, column=i % 2, sticky="ew", padx=2, pady=2)
            self.tool_buttons[key] = b
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        self.section(panel, "EDIT")
        row = tk.Frame(panel, bg=C["panel"])
        row.pack(fill="x")
        undo = self.button(row, "↶ Undo", self.undo, tip="Ctrl+Z")
        undo.pack(side="left", expand=True, fill="x", padx=(0, 2))
        redo = self.button(row, "↷ Redo", self.redo, tip="Ctrl+Y")
        redo.pack(side="left", expand=True, fill="x", padx=(2, 0))
        self.gen_btn = self.button(panel, "Generate draft…", self.generate_dialog,
                                   tip="Replace the walls with a random connected draft (undo is available)")
        self.gen_btn.pack(fill="x", pady=(5, 0))
        self.clear_btn = self.button(panel, "Clear map…", self.clear, "danger", "Remove all walls (undo is available)")
        self.clear_btn.pack(fill="x", pady=(5, 0))
        self.edit_buttons = [undo, redo, self.gen_btn, self.clear_btn, self.copy_btn, self.remove_btn]

        if self.dnd_ready:
            hint = "Tip: drag CSV, JSON or ZIP files from your file manager onto this window to import them."
        else:
            hint = "Tip: use Import ▾ to add CSV, JSON or ZIP maps."
        self.label(panel, hint, 8, C["muted"], justify="left", wraplength=230).pack(anchor="w", side="bottom", pady=(0, 8))

        # ---- main area: footer packed first so it is never squeezed off small screens
        main = tk.Frame(body, bg=C["bg"])
        main.pack(side="left", fill="both", expand=True, padx=10, pady=(0, 10))

        status = tk.Frame(main, bg=C["bg"], height=26)
        status.pack(side="bottom", fill="x")
        status.pack_propagate(False)
        self.status_label = self.label(status, textvariable=self.status, size=9, color=C["muted"], anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True, padx=4)
        self.label(status, textvariable=self.pointer, size=9, color=C["muted"]).pack(side="right", padx=6)

        footer = tk.Frame(main, bg=C["panel"], height=46)
        footer.pack(side="bottom", fill="x")
        footer.pack_propagate(False)
        self.label(footer, "ZOOM", 9, C["muted"], True).pack(side="left", padx=(14, 6))
        self.button(footer, "−", lambda: self.set_zoom(self.zoom - 3), "quiet", "Ctrl + −").pack(side="left")
        self.zoom_scale = ttk.Scale(footer, from_=MIN_CELL, to=MAX_CELL, orient="horizontal", length=150,
                                    style="Zoom.Horizontal.TScale", command=lambda v: self.set_zoom(int(float(v))))
        self.zoom_scale.pack(side="left", padx=2)
        self.button(footer, "+", lambda: self.set_zoom(self.zoom + 3), "quiet", "Ctrl + +").pack(side="left")
        self.zoom_label = self.label(footer, "100%", 10, bold=True, width=5)
        self.zoom_label.pack(side="left", padx=6)
        self.button(footer, "Fit", self.fit, tip="Fit the whole map in the window (F)").pack(side="left", padx=4)
        for text, var, cmd in (("Route preview", self.show_route, self.refresh_overlay),
                               ("Grid lines", self.show_grid, self.render)):
            tk.Checkbutton(footer, text=text, variable=var, command=cmd, bg=C["panel"], fg=C["text"],
                           activebackground=C["panel"], activeforeground=C["text"], selectcolor=C["card"],
                           highlightthickness=0, font=self.font(9)).pack(side="right", padx=8)

        header = tk.Frame(main, bg=C["panel"], height=46)
        header.pack(side="top", fill="x")
        header.pack_propagate(False)
        self.title_label = self.label(header, "", 12, bold=True)
        self.title_label.pack(side="left", padx=(16, 8))
        self.route_label = self.label(header, textvariable=self.route_text, size=9, color=C["accent"])
        self.route_label.pack(side="right", padx=14)
        Tooltip(self.route_label, "Eight-neighbour BFS connectivity preview, not A*, weighted shortest path or the continuous optimum.", self.font(9))

        self.banner = tk.Label(main, text="", bg=C["warn_bg"], fg=C["warn"], font=self.font(9), anchor="w",
                               justify="left", padx=12, pady=6, wraplength=900)

        self.workspace_frame = tk.Frame(main, bg=C["canvas"])
        self.workspace_frame.pack(side="top", fill="both", expand=True)
        self.canvas = tk.Canvas(self.workspace_frame, bg=C["canvas"], highlightthickness=0, cursor="crosshair")
        ys = ttk.Scrollbar(self.workspace_frame, orient="vertical", command=self.canvas.yview)
        xs = ttk.Scrollbar(self.workspace_frame, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.workspace_frame.rowconfigure(0, weight=1)
        self.workspace_frame.columnconfigure(0, weight=1)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")

        self.drop_overlay = tk.Label(self.workspace_frame, bg=C["accent_bg"], fg=C["text"], font=self.font(15, True),
                                     text="Drop CSV, JSON or ZIP files (or a folder) to import\n\n"
                                          "Nothing is replaced without asking first.", justify="center")

        c = self.canvas
        c.bind("<ButtonPress-1>", self.press)
        c.bind("<B1-Motion>", self.drag)
        c.bind("<ButtonRelease-1>", self.release)
        c.bind("<ButtonPress-3>", self.press)
        c.bind("<B3-Motion>", self.drag)
        c.bind("<ButtonRelease-3>", self.release)
        c.bind("<Motion>", self.hover)
        c.bind("<Configure>", lambda e: self.render() if self.session is None else None)
        c.bind("<Leave>", lambda e: self.pointer.set(""))
        c.bind("<Control-Button-4>", lambda e: self.wheel_zoom(e, 1))
        c.bind("<Control-Button-5>", lambda e: self.wheel_zoom(e, -1))
        c.bind("<Control-MouseWheel>", lambda e: self.wheel_zoom(e, 1 if e.delta > 0 else -1))
        c.bind("<Button-4>", lambda e: (c.yview_scroll(-3, "units"), "break")[1])
        c.bind("<Button-5>", lambda e: (c.yview_scroll(3, "units"), "break")[1])
        c.bind("<MouseWheel>", lambda e: (c.yview_scroll(-3 if e.delta > 0 else 3, "units"), "break")[1])
        c.bind("<Shift-Button-4>", lambda e: (c.xview_scroll(-3, "units"), "break")[1])
        c.bind("<Shift-Button-5>", lambda e: (c.xview_scroll(3, "units"), "break")[1])
        c.bind("<Shift-MouseWheel>", lambda e: (c.xview_scroll(-3 if e.delta > 0 else 3, "units"), "break")[1])

        if self.dnd_ready and not self.read_only:
            self.dnd_ready = enable_drop([self.root, self.canvas, self.library, side, main],
                                         self._drop_enter, self._drop_leave, self._drop)
        self.choose_tool("wall")
        self._apply_read_only()

    def _apply_read_only(self):
        if not self.read_only:
            return
        for b in list(self.edit_buttons) + [self.top_buttons["new"], self.top_buttons["import"]]:
            b.configure(state="disabled")

    # ================================================================ keys
    def _bind_keys(self):
        def guarded(action):
            def handler(event):
                if isinstance(event.widget, (tk.Entry, tk.Spinbox, ttk.Entry, ttk.Combobox, tk.Text)):
                    return None
                action()
                return "break"
            return handler

        for seq, action in [("<Control-z>", self.undo), ("<Control-y>", self.redo), ("<Control-Z>", self.redo),
                            ("<Control-s>", self.retry_save), ("<Control-plus>", lambda: self.set_zoom(self.zoom + 3)),
                            ("<Control-equal>", lambda: self.set_zoom(self.zoom + 3)),
                            ("<Control-minus>", lambda: self.set_zoom(self.zoom - 3)),
                            ("<Control-n>", self.new_map), ("<Control-o>", self.import_files),
                            ("<F1>", self.show_help), ("<KeyPress-f>", self.fit),
                            ("<KeyPress-t>", lambda: (self.show_route.set(not self.show_route.get()), self.refresh_overlay())),
                            ("<KeyPress-1>", lambda: self.choose_tool("wall")), ("<KeyPress-2>", lambda: self.choose_tool("erase")),
                            ("<KeyPress-3>", lambda: self.choose_tool("start")), ("<KeyPress-4>", lambda: self.choose_tool("goal"))]:
            self.root.bind(seq, guarded(action))

    def choose_tool(self, tool):
        self.tool.set(tool)
        for key, b in self.tool_buttons.items():
            selected = key == tool
            bg = C["accent_bg"] if selected else C["card"]
            b._bg_now = bg
            b.configure(bg=bg, fg=C["accent"] if selected else C["text"],
                        font=self.font(10, selected))
        self.set_status(f"Tool: {tool.capitalize()}")

    # ================================================================ status
    def set_status(self, text, kind="info"):
        self.status.set(text)
        self.status_label.configure(fg={"info": C["muted"], "ok": C["ok"], "error": C["danger"], "warn": C["warn"]}[kind])

    def update_title(self):
        if not self.name:
            self.title_label.configure(text="No map open")
            return
        d = self.session.data
        suffix = "   • NOT SAVED" if self.unsaved else ""
        lock = "   🔒 add-only" if self.session.add_only else ""
        self.title_label.configure(text=f"{self.name}   {d.width}×{d.height}{lock}{suffix}",
                                   fg=C["danger"] if self.unsaved else C["text"])

    def refresh_stats(self):
        if not self.session:
            self.stats_text.set("")
            return
        d = self.session.data
        total = d.width * d.height
        lines = [f"{d.width} × {d.height} cells", f"{d.walls} walls · {d.walls / total:.1%} blocked",
                 f"Start {self._cell_text(d.start)} · Goal {self._cell_text(d.goal)}"]
        if self.session.add_only:
            lines.append(f"Added since copy: {len(self.session.added_walls())} walls (orange)")
        self.stats_text.set("\n".join(lines))
        self.update_title()

    @staticmethod
    def _cell_text(cell):
        return "—" if cell is None else f"({cell[0]}, {cell[1]})"

    def show_banner(self, text):
        if text:
            self.banner.configure(text=text)
            self.banner.pack(side="top", fill="x", after=self.title_label.master)
        else:
            self.banner.pack_forget()

    # ================================================================ library
    def refresh_library(self, select: Optional[str] = None):
        infos = self.ws.list_maps()
        self.lib_names = [i.name for i in infos]
        self._selecting = True
        self.library.delete(0, "end")
        for info in infos:
            if not info.exists:
                text = f"  {info.name}   + create"
            elif info.error:
                text = f"  ⚠ {info.name}   (cannot open)"
            else:
                text = f"  {info.name}   {info.width}×{info.height}"
            self.library.insert("end", text)
            if not info.exists or info.error:
                self.library.itemconfigure("end", fg=C["muted"] if not info.error else C["danger"])
        self.library.configure(height=max(5, min(9, len(infos))))
        target = select or self.name
        if target in self.lib_names:
            index = self.lib_names.index(target)
            self.library.selection_clear(0, "end")
            self.library.selection_set(index)
            self.library.see(index)
        self._selecting = False

    def _library_selected(self, _event=None):
        if self._selecting:
            return
        selection = self.library.curselection()
        if selection:
            name = self.lib_names[selection[0]]
            if name != self.name:
                self.open_map(name)

    # ================================================================ open / save
    def _leave_current(self) -> bool:
        """Finish the current map before switching. Returns False if the user wants to stay."""
        if self.session and self.session.in_stroke:
            self.release()
        if self.unsaved and not self.retry_save():
            return messagebox.askyesno("Changes not saved",
                                       f"{self.name} could not be saved. Switch anyway and lose the unsaved edits?",
                                       parent=self.root)
        return True

    def open_map(self, name: str):
        if not self._leave_current():
            self.refresh_library()
            return
        try:
            if not self.ws.exists(name):
                if self.read_only:
                    raise MapError("This window is read-only, so new maps cannot be created here.")
                if name == CHANGED_NAME:
                    if not messagebox.askyesno("Create Medium Changed",
                                               "Create Medium Changed as an exact copy of Medium?\n\n"
                                               "You can then only ADD walls; Medium's walls, Start and Goal stay locked.",
                                               parent=self.root):
                        self.refresh_library()
                        return
                    self.ws.make_changed()
                else:
                    w, h = BUILTIN_SIZES.get(name, (20, 20))
                    if not messagebox.askyesno("Create map", f"{name} has not been created yet.\n\nCreate an empty {name} "
                                               f"map ({w}×{h})?\n\nTo use an existing {name}.csv instead, choose No and "
                                               "use Import.", parent=self.root):
                        self.refresh_library()
                        return
                    self.ws.create(blank(name, w, h))
            data = self.ws.load(name)
            base, note = (self.ws.changed_base() if name == CHANGED_NAME else (None, ""))
        except (MapError, SaveError, OSError) as error:
            messagebox.showerror("Cannot open map", str(error), parent=self.root)
            self.refresh_library()
            return
        self.session = EditSession(data, base)
        self.name = name
        self.unsaved = False
        self.note = note
        self.show_banner(note)
        self.refresh_library(select=name)
        self.update_buttons()
        self.refresh_stats()
        self.render()
        self.root.after(30, self.fit)
        self.set_status(f"Opened {name}. Changes save automatically." if not self.read_only else f"Opened {name} (read-only).")

    def save(self) -> bool:
        if not self.session or self.read_only:
            return True
        try:
            self.ws.save(self.session.data)
        except SaveError as error:
            first = not self.unsaved
            self.unsaved = True
            self.update_title()
            self.set_status(f"NOT SAVED: {error}  (Ctrl+S to retry)", "error")
            if first:
                messagebox.showerror("Save failed", f"{error}\n\nYour edits are still open. Press Ctrl+S to try again.",
                                     parent=self.root)
            return False
        self.unsaved = False
        self.update_title()
        self.set_status(f"Saved {self.name}.csv and {self.name}.json", "ok")
        return True

    def retry_save(self) -> bool:
        return self.save()

    # ================================================================ drawing
    def cell_fill(self, x, y):
        d = self.session.data
        if d.grid[y][x]:
            if self.session.add_only and not self.session.base[y][x]:
                return C["added"]
            return C["wall"]
        return C["free"]

    def update_buttons(self):
        """Enable only the actions that make sense for the open map (or for no map)."""
        has = self.session is not None
        add_only = has and self.session.add_only
        state = lambda ok: "normal" if ok and not self.read_only else "disabled"
        for b in self.edit_buttons[:2]:
            b.configure(state=state(has))
        self.gen_btn.configure(state=state(has and not add_only))
        self.clear_btn.configure(state=state(has), text="Remove added walls…" if add_only else "Clear map…")
        self.copy_btn.configure(state=state(has))
        self.remove_btn.configure(state=state(has and self.name not in BUILTIN_SIZES))
        self.top_buttons["export"].configure(state="normal" if self.ws.has_maps() else "disabled")

    def open_first_or_welcome(self):
        first = next((n for n in self.lib_names if self.ws.exists(n)), None)
        if first:
            self.open_map(first)
        else:
            self.session, self.name, self.unsaved = None, None, False
            self.refresh_stats()
            self.update_title()
            self.update_buttons()
            self.render()
            self.set_status("Your library is empty. Import your maps or create a new one.")

    def show_welcome(self):
        """Empty library: explain the three ways to add maps, with buttons."""
        c = self.canvas
        self.route_text.set("")
        c.update_idletasks()
        cx, cy = max(320, c.winfo_width() // 2), max(220, c.winfo_height() // 2)
        c.create_text(cx, cy - 110, text="No maps yet", fill=C["wall"], font=self.font(20, True))
        c.create_text(cx, cy - 68, fill=C["axis"], font=self.font(11), justify="center",
                      text=("Drag your CSV and JSON files (or a ZIP or a whole folder) onto this window,\n"
                            if self.dnd_ready else "") + "or use one of the buttons below. Your original files are never changed.")
        if getattr(self, "_welcome_row", None) is not None:
            self._welcome_row.destroy()
        row = self._welcome_row = tk.Frame(c, bg=C["canvas"])
        for text, cmd, kind in (("Import files…", self.import_files, "primary"),
                                ("Import a folder…", self.import_folder, "normal"),
                                ("New map…", self.new_map, "normal")):
            b = self.button(row, text, cmd, kind, size=11)
            if self.read_only:
                b.configure(state="disabled")
            b.pack(side="left", padx=6)
        c.create_window(cx, cy - 10, window=row)
        # A Wine, OneDrive, or university computer may have a very long folder path.
        # Keep the welcome panel readable; Help and Open folder show its exact location.
        c.create_text(cx, cy + 50, fill=C["axis"], font=self.font(9), justify="center",
                      width=max(300, c.winfo_width() - 80),
                      text="Maps are stored in your personal Maps Studio folder. Use Open folder to view them.")
        c.configure(scrollregion=(0, 0, c.winfo_width(), c.winfo_height()))

    def render(self):
        c = self.canvas
        c.delete("all")
        if not self.session:
            self.show_welcome()
            return
        d = self.session.data
        z = self.zoom
        outline = C["grid"] if self.show_grid.get() and z >= 9 else ""
        self.cells = []
        for y in range(d.height):
            row = []
            for x in range(d.width):
                left, top = PAD + x * z, PAD + y * z
                row.append(c.create_rectangle(left, top, left + z, top + z, fill=self.cell_fill(x, y),
                                              outline=outline, width=1))
            self.cells.append(row)
        step = next(s for s in (1, 2, 5, 10, 20, 50) if s * z >= 18)
        for i in range(0, d.width, step):
            c.create_text(PAD + (i + 0.5) * z, PAD - 13, text=str(i), fill=C["axis"], font=self.font(8))
        for i in range(0, d.height, step):
            c.create_text(PAD - 15, PAD + (i + 0.5) * z, text=str(i), fill=C["axis"], font=self.font(8))
        c.create_text(PAD + d.width * z, PAD - 13, text="  x →", fill=C["axis"], font=self.font(8), anchor="w")
        c.create_text(PAD - 15, PAD + d.height * z + 12, text="y ↓", fill=C["axis"], font=self.font(8))
        c.configure(scrollregion=(0, 0, 2 * PAD + d.width * z, 2 * PAD + d.height * z))
        self.zoom_label.configure(text=f"{round(100 * z / BASE_CELL)}%")
        self.zoom_scale.set(z)
        self.refresh_overlay()

    def refresh_overlay(self):
        c = self.canvas
        c.delete("route")
        c.delete("marker")
        if not self.session:
            self.route_text.set("")
            return
        d = self.session.data
        path = route_preview(d.grid, d.start, d.goal)
        if d.start is None or d.goal is None:
            self.route_text.set("Place Start and Goal to check connectivity")
            self.route_label.configure(fg=C["warn"])
        elif path is None:
            self.route_text.set("✕ Start and Goal are not connected")
            self.route_label.configure(fg=C["danger"])
        else:
            self.route_text.set(f"✓ Connected · {len(path) - 1} moves · BFS (not A*)")
            self.route_label.configure(fg=C["ok"])
            if self.show_route.get() and len(path) > 1:
                z = self.zoom
                points = [v for x, y in path for v in (PAD + (x + 0.5) * z, PAD + (y + 0.5) * z)]
                c.create_line(*points, fill=C["route"], width=max(2, z // 7), capstyle="round", joinstyle="round",
                              tags="route")
        z = self.zoom
        for cell, letter, color in ((d.start, "S", C["start"]), (d.goal, "G", C["goal"])):
            if cell is None:
                continue
            left, top = PAD + cell[0] * z, PAD + cell[1] * z
            c.create_rectangle(left, top, left + z, top + z, fill=color, outline="white", width=1, tags="marker")
            if z >= 12:
                c.create_text(left + z / 2, top + z / 2, text=letter, fill="white",
                              font=self.font(max(7, z // 2), True), tags="marker")

    def paint_cell(self, x, y):
        self.canvas.itemconfigure(self.cells[y][x], fill=self.cell_fill(x, y))

    # ================================================================ mouse
    def cell_at(self, event):
        if not self.session:
            return None
        x = int((self.canvas.canvasx(event.x) - PAD) // self.zoom)
        y = int((self.canvas.canvasy(event.y) - PAD) // self.zoom)
        d = self.session.data
        return (x, y) if 0 <= x < d.width and 0 <= y < d.height else None

    def hover(self, event):
        cell = self.cell_at(event)
        if cell is None:
            self.pointer.set("")
            return
        x, y = cell
        d = self.session.data
        kind = "Start" if cell == d.start else "Goal" if cell == d.goal else ("wall" if d.grid[y][x] else "free")
        self.pointer.set(f"x {x} · y {y} · {kind}")

    def _apply(self, cell, tool):
        if self.session.apply(cell, tool):
            if tool in ("start", "goal") or cell in (self.session.data.start, self.session.data.goal) or tool == "erase":
                self.refresh_overlay_markers_only()
            self.paint_cell(*cell)
            return True
        return False

    def refresh_overlay_markers_only(self):
        self.canvas.delete("marker")
        d, z = self.session.data, self.zoom
        for cell, letter, color in ((d.start, "S", C["start"]), (d.goal, "G", C["goal"])):
            if cell is None:
                continue
            left, top = PAD + cell[0] * z, PAD + cell[1] * z
            self.canvas.create_rectangle(left, top, left + z, top + z, fill=color, outline="white", tags="marker")
            if z >= 12:
                self.canvas.create_text(left + z / 2, top + z / 2, text=letter, fill="white",
                                        font=self.font(max(7, z // 2), True), tags="marker")

    def press(self, event):
        if self.drag_tool or not self.session:
            return
        cell = self.cell_at(event)
        if cell is None:
            return
        if self.read_only:
            self.set_status("Read-only window: close the other Maps Studio window to edit.", "warn")
            return
        tool = "erase" if event.num == 3 else self.tool.get()
        self.session.begin()
        self.drag_tool, self.last_cell = tool, cell
        d = self.session.data
        if tool in ("start", "goal") and getattr(d, tool) == cell:
            self.toggle_pending = cell
            return
        self.toggle_pending = None
        if not self._apply(cell, tool):
            self._explain_refusal(cell, tool)

    def _explain_refusal(self, cell, tool):
        s = self.session
        x, y = cell
        if s.add_only and tool == "erase" and s.base[y][x]:
            self.set_status("Medium Changed is add-only: walls copied from Medium cannot be erased.", "warn")
        elif s.add_only and tool in ("start", "goal", "erase") and (tool != "erase" or cell in (s.data.start, s.data.goal)):
            self.set_status("Medium Changed keeps Medium's Start and Goal. They are locked.", "warn")
        elif tool in ("start", "goal") and s.data.grid[y][x]:
            self.set_status(f"{tool.capitalize()} cannot go on a wall.", "warn")
        elif tool == "wall" and cell in (s.data.start, s.data.goal):
            self.set_status("Walls cannot cover Start or Goal.", "warn")

    def drag(self, event):
        if not self.drag_tool:
            return
        cell = self.cell_at(event)
        if cell is None or cell == self.last_cell:
            return
        self.toggle_pending = None
        if self.drag_tool in ("wall", "erase"):
            for c in line_cells(self.last_cell, cell):
                self._apply(c, self.drag_tool)
        else:
            self._apply(cell, self.drag_tool)
        self.last_cell = cell

    def release(self, _event=None):
        if not self.drag_tool:
            return
        if self.toggle_pending is not None:
            self.session.toggle_marker(self.toggle_pending, self.drag_tool)
        self.drag_tool, self.last_cell, self.toggle_pending = None, None, None
        if self.session.end():
            self.save()
        self.refresh_overlay()
        self.refresh_stats()

    # ================================================================ edit actions
    def undo(self):
        if self.session and not self.read_only and self.session.undo():
            self.render()
            self.refresh_stats()
            self.save()

    def redo(self):
        if self.session and not self.read_only and self.session.redo():
            self.render()
            self.refresh_stats()
            self.save()

    def clear(self):
        if not self.session or self.read_only:
            return
        question = ("Remove the walls you added to Medium Changed? Medium's own walls stay."
                    if self.session.add_only else f"Remove all walls, Start and Goal from {self.name}?")
        if not messagebox.askyesno("Clear", question + "\n\nUndo is available.", parent=self.root):
            return
        self.session.begin()
        self.session.clear()
        if self.session.end():
            self.save()
        self.render()
        self.refresh_stats()

    def duplicate(self):
        if not self.session or self.read_only:
            return
        suggestion = self.ws.free_name(f"{self.name}_copy")
        name = simpledialog.askstring("Duplicate map", "Name for the copy (lowercase letters, digits, - or _):",
                                      initialvalue=suggestion, parent=self.root)
        if not name:
            return
        try:
            name = check_name(name.strip())
            copy = self.session.data.copy(name)
            copy.validate()
            self.ws.create(copy)
        except (MapError, SaveError) as error:
            messagebox.showerror("Not duplicated", str(error), parent=self.root)
            return
        self.refresh_library()
        self.open_map(name)

    def remove_map(self):
        if not self.name or self.read_only:
            return
        if self.name in BUILTIN_SIZES:
            messagebox.showinfo("Protected", "The four coursework maps cannot be removed.", parent=self.root)
            return
        if not messagebox.askyesno("Remove map", f"Move {self.name} to the trash folder?\n\n"
                                   "The files are kept in .maps_studio/trash inside your maps folder.", parent=self.root):
            return
        try:
            self.ws.remove(self.name)
        except (MapError, OSError) as error:
            messagebox.showerror("Not removed", str(error), parent=self.root)
            return
        self.session, self.name, self.unsaved = None, None, False
        self.refresh_library()
        self.open_first_or_welcome()

    # ================================================================ generator & new map dialogs
    def _dialog(self, title):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=C["panel"], highlightthickness=1, highlightbackground=C["line"])
        win.transient(self.root)
        win.resizable(False, False)
        outer = tk.Frame(win, bg=C["panel"], padx=22, pady=16)
        outer.pack(fill="both", expand=True)
        self.label(outer, title, 13, bold=True).pack(anchor="w", pady=(0, 10))
        body = tk.Frame(outer, bg=C["panel"])
        body.pack(fill="both", expand=True)
        win.after_idle(lambda: self._centre(win))
        return win, body

    def _centre(self, win):
        try:
            win.update_idletasks()
            x = self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_reqwidth()) // 2
            y = self.root.winfo_rooty() + (self.root.winfo_height() - win.winfo_reqheight()) // 3
            win.geometry(f"+{max(0, x)}+{max(0, y)}")
        except tk.TclError:
            pass

    def _check(self, parent, text, var, **kw):
        return tk.Checkbutton(parent, text=text, variable=var, bg=C["panel"], fg=C["text"], selectcolor=C["card"],
                              activebackground=C["panel"], activeforeground=C["text"], highlightthickness=0,
                              font=self.font(10), **kw)

    def _radio(self, parent, text, var, value):
        return tk.Radiobutton(parent, text=text, value=value, variable=var, bg=C["panel"], fg=C["text"],
                              selectcolor=C["card"], activebackground=C["panel"], activeforeground=C["text"],
                              highlightthickness=0, font=self.font(10))

    def _field(self, parent, text, row, widget):
        self.label(parent, text, 10, C["muted"]).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 12))
        widget.grid(row=row, column=1, sticky="ew", pady=4)

    def _entry(self, parent, var, width=18):
        return tk.Entry(parent, textvariable=var, width=width, bg=C["card"], fg=C["text"], insertbackground=C["text"],
                        relief="flat", highlightthickness=1, highlightbackground=C["line"],
                        highlightcolor=C["accent"], font=self.font(10))

    def _generator_fields(self, body, start_row, vars_):
        style_names = list(STYLES.values())
        combo = ttk.Combobox(body, textvariable=vars_["style"], values=style_names, state="readonly", width=20)
        self._field(body, "Style", start_row, combo)
        self._field(body, "Obstacle density (%)", start_row + 1, self._entry(body, vars_["density"]))
        self._field(body, "Seed (same seed = same map)", start_row + 2, self._entry(body, vars_["seed"]))

    @staticmethod
    def _read_generator(vars_):
        style = {v: k for k, v in STYLES.items()}[vars_["style"].get()]
        try:
            density = float(vars_["density"].get()) / 100
            seed = int(vars_["seed"].get())
        except ValueError:
            raise MapError("Density must be a number and the seed a whole number.") from None
        return style, density, seed

    def generate_dialog(self):
        if not self.session or self.read_only or self.session.add_only:
            return
        d = self.session.data
        win, body = self._dialog("Generate draft")
        self.label(body, f"Replace the walls of {self.name} with a random connected draft.",
                   10, wraplength=380, justify="left").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        vars_ = {"style": tk.StringVar(value=STYLES["segments"]), "density": tk.StringVar(value="20"),
                 "seed": tk.StringVar(value="12345")}
        self._generator_fields(body, 1, vars_)
        corners = tk.BooleanVar(value=d.start is None or d.goal is None)
        self._check(body, "Place Start and Goal in opposite corners", corners).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.label(body, "Drafts are sketches to edit and justify yourself, not tested maps. Undo is available.",
                   9, C["muted"], wraplength=380, justify="left").grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))
        buttons = tk.Frame(body, bg=C["panel"])
        buttons.grid(row=6, column=0, columnspan=2, sticky="e", pady=(14, 0))

        def run():
            try:
                style, density, seed = self._read_generator(vars_)
                start, goal = (default_endpoints(d.width, d.height) if corners.get() or d.start is None or d.goal is None
                               else (d.start, d.goal))
                grid, used = generate(d.width, d.height, style, density, seed, start, goal)
            except MapError as error:
                messagebox.showerror("No draft", str(error), parent=win)
                return
            win.destroy()
            self.session.begin()
            self.session.replace_grid(grid)
            d.start, d.goal = start, goal
            if self.session.end():
                self.save()
            self.render()
            self.refresh_stats()
            self.set_status(f"Draft generated · {STYLES[style]} · seed {used} · undo with Ctrl+Z", "ok")

        self.button(buttons, "Cancel", win.destroy).pack(side="right", padx=(6, 0))
        self.button(buttons, "Generate", run, "primary").pack(side="right")
        win.bind("<Return>", lambda e: run())
        win.bind("<Escape>", lambda e: win.destroy())
        win.grab_set()
        win.wait_window()

    def new_map(self):
        if self.read_only:
            return
        win, body = self._dialog("New map")
        name = tk.StringVar(value=self.ws.free_name("map_1" if not self.ws.exists("map_1") else "map"))
        width, height = tk.StringVar(value="30"), tk.StringVar(value="30")
        content = tk.StringVar(value="empty")
        corners = tk.BooleanVar(value=True)
        vars_ = {"style": tk.StringVar(value=STYLES["segments"]), "density": tk.StringVar(value="20"),
                 "seed": tk.StringVar(value="12345")}
        self._field(body, "Name", 0, self._entry(body, name))
        size_row = tk.Frame(body, bg=C["panel"])
        self._entry(size_row, width, 6).pack(side="left")
        self.label(size_row, " × ", 10, C["muted"]).pack(side="left")
        self._entry(size_row, height, 6).pack(side="left")
        self.label(size_row, f"  ({MIN_SIDE}–{MAX_SIDE})", 9, C["muted"]).pack(side="left")
        self._field(body, "Size (width × height)", 1, size_row)
        modes = tk.Frame(body, bg=C["panel"])
        for value, text in (("empty", "Empty"), ("draft", "Generate a draft")):
            self._radio(modes, text, content, value).pack(side="left", padx=(0, 12))
        self._field(body, "Start with", 2, modes)
        self._generator_fields(body, 3, vars_)
        self._check(body, "Place Start and Goal in opposite corners", corners).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.label(body, "Names easy, medium and hard keep their coursework sizes (20, 40, 60).", 9, C["muted"],
                   wraplength=400, justify="left").grid(row=7, column=0, columnspan=2, sticky="w", pady=(8, 0))
        buttons = tk.Frame(body, bg=C["panel"])
        buttons.grid(row=8, column=0, columnspan=2, sticky="e", pady=(14, 0))

        def create():
            try:
                n = check_name(name.get().strip().lower())
                try:
                    w, h = int(width.get()), int(height.get())
                except ValueError:
                    raise MapError("Width and height must be whole numbers.") from None
                data = blank(n, w, h)
                if corners.get() or content.get() == "draft":
                    data.start, data.goal = default_endpoints(w, h)
                if content.get() == "draft":
                    style, density, seed = self._read_generator(vars_)
                    data.grid, _ = generate(w, h, style, density, seed, data.start, data.goal)
                self.ws.create(data)
            except (MapError, SaveError) as error:
                messagebox.showerror("Map not created", str(error), parent=win)
                return
            win.destroy()
            self.refresh_library()
            self.open_map(n)

        self.button(buttons, "Cancel", win.destroy).pack(side="right", padx=(6, 0))
        self.button(buttons, "Create", create, "primary").pack(side="right")
        win.bind("<Return>", lambda e: create())
        win.bind("<Escape>", lambda e: win.destroy())
        win.grab_set()
        win.wait_window()

    # ================================================================ import / export
    def _menu(self, button, entries):
        menu = tk.Menu(self.root, tearoff=False, bg=C["card"], fg=C["text"], activebackground=C["accent_bg"],
                       activeforeground=C["text"], font=self.font(10), bd=0)
        for text, cmd in entries:
            menu.add_command(label=text, command=cmd)
        menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height())

    def import_menu(self):
        if self.read_only:
            return
        self._menu(self.top_buttons["import"], [("CSV, JSON or ZIP files…", self.import_files),
                                                ("A whole folder…", self.import_folder)])

    def export_menu(self):
        self._menu(self.top_buttons["export"], [("This map to a folder…", self.export_current),
                                                ("Several maps as one ZIP…", self.export_zip)])

    def import_files(self):
        if self.read_only:
            return
        files = filedialog.askopenfilenames(parent=self.root, title="Choose map files",
                                            filetypes=[("Maps", "*.csv *.json *.zip"), ("All files", "*.*")])
        if files:
            self.import_paths([Path(f) for f in files])

    def import_folder(self):
        folder = filedialog.askdirectory(parent=self.root, title="Choose a folder with CSV (+ JSON) maps")
        if folder:
            self.import_paths([Path(folder)])

    def _drop_enter(self):
        self.drop_overlay.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.86, relheight=0.6)
        self.drop_overlay.lift()

    def _drop_leave(self):
        self.drop_overlay.place_forget()

    def _drop(self, paths):
        self.drop_overlay.place_forget()
        self.root.after(10, lambda: self.import_paths([Path(p) for p in paths]))

    def import_paths(self, paths):
        if self.read_only:
            return
        if not self._leave_current():
            return
        items = self.ws.read_sources(paths)
        if not items:
            messagebox.showinfo("Nothing to import", "No CSV map files were found there.", parent=self.root)
            return
        ImportDialog(self, items).run()

    def finish_import(self, report, quiet=False):
        lines = []
        if report.imported:
            lines.append("Imported: " + ", ".join(n for _, n in report.imported))
        if report.skipped:
            lines.append("Skipped (name already used): " + ", ".join(n for _, n in report.skipped))
        if report.failed:
            lines.append("Not imported:\n" + "\n".join(f"• {Path(s).name}: {e}" for s, e in report.failed))
        previous = self.name
        self.session, self.name = None, None
        target = report.imported[0][1] if report.imported else previous
        self.refresh_library()
        if target and self.ws.exists(target):
            self.open_map(target)
        else:
            self.open_first_or_welcome()
        if not quiet:
            (messagebox.showwarning if report.failed else messagebox.showinfo)(
                "Import finished", "\n\n".join(lines) or "Nothing was imported.", parent=self.root)

    def export_current(self):
        if not self.name or not self._leave_current():
            return
        folder = filedialog.askdirectory(parent=self.root, title=f"Export {self.name} to which folder?")
        if not folder:
            return
        destination = Path(folder)
        try:
            self.ws.export_pair(self.name, destination)
        except FileExistsError as error:
            if not messagebox.askyesno("Replace files?", f"{error}\n\nReplace them? The old files are kept next to them "
                                       "as .backup copies.\n\nAgree with your team before replacing shared maps.",
                                       parent=self.root):
                return
            try:
                self.ws.export_pair(self.name, destination, overwrite=True)
            except (SaveError, MapError, OSError) as error2:
                messagebox.showerror("Export failed", str(error2), parent=self.root)
                return
        except (SaveError, MapError, OSError) as error:
            messagebox.showerror("Export failed", str(error), parent=self.root)
            return
        self.set_status(f"Exported {self.name}.csv and {self.name}.json to {destination}", "ok")

    def export_zip(self):
        if not self._leave_current():
            return
        names = [i.name for i in self.ws.list_maps() if i.exists and not i.error]
        chooser = ChooseMaps(self, names, self.name)
        chosen = chooser.run()
        if not chosen:
            return
        target = filedialog.asksaveasfilename(parent=self.root, title="Save ZIP", defaultextension=".zip",
                                              initialfile="maps.zip", filetypes=[("ZIP archive", "*.zip")])
        if not target:
            return
        try:
            self.ws.export_zip(chosen, Path(target))
        except FileExistsError:
            if not messagebox.askyesno("Replace ZIP?", "A ZIP with that name already exists. Replace it?",
                                       parent=self.root):
                return
            try:
                self.ws.export_zip(chosen, Path(target), overwrite=True)
            except (SaveError, MapError, OSError) as error:
                messagebox.showerror("Export failed", str(error), parent=self.root)
                return
        except (SaveError, MapError, OSError) as error:
            messagebox.showerror("Export failed", str(error), parent=self.root)
            return
        self.set_status(f"Exported {len(chosen)} map(s) to {target}", "ok")

    # ================================================================ misc
    def folder_command(self) -> Optional[list]:
        """Command that opens the maps folder in the file manager (None on Windows, which uses os.startfile)."""
        folder = str(self.ws.grids)
        if sys.platform == "win32":
            return None
        if sys.platform == "darwin":
            return ["open", folder]
        for program in ("xdg-open", "gio", "kde-open5", "kde-open", "nautilus", "dolphin", "thunar", "nemo"):
            path = shutil.which(program)
            if path:
                return [path, "open", folder] if program == "gio" else [path, folder]
        return None

    @staticmethod
    def _desktop_env() -> dict:
        """Environment for launching desktop programs.

        The one-file Linux build changes LD_LIBRARY_PATH (and the Tcl/Tk paths) for itself. Passing
        those on can stop the file manager from starting, so the original values are restored.
        """
        env = dict(os.environ)
        if getattr(sys, "frozen", False):
            for key in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
                original = env.pop(key + "_ORIG", None)
                if original is not None:
                    env[key] = original
                else:
                    env.pop(key, None)
            for key in ("TCL_LIBRARY", "TK_LIBRARY", "TKDND_LIBRARY"):
                env.pop(key, None)
        return env

    def open_folder(self):
        folder = self.ws.grids
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            try:
                os.startfile(str(folder))
                self.set_status(f"Opened {folder}")
                return
            except OSError:
                return self._show_path()
        command = self.folder_command()
        if command is None:
            return self._show_path()
        try:
            process = subprocess.Popen(command, env=self._desktop_env(), stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError:
            return self._show_path()
        self.set_status(f"Opening {folder}")

        def check():
            code = process.poll()
            if code not in (None, 0):
                self._show_path()
        self.root.after(2500, check)

    def _show_path(self):
        """Fallback when no file manager could be opened: show the folder with a Copy button."""
        win, body = self._dialog("Your maps folder")
        self.label(body, "The file manager could not be opened automatically. Your maps are in:",
                   10, wraplength=460, justify="left").pack(anchor="w")
        value = tk.StringVar(value=str(self.ws.grids))
        entry = self._entry(body, value, 58)
        entry.configure(state="readonly", readonlybackground=C["card"])
        entry.pack(fill="x", pady=8)
        row = tk.Frame(body, bg=C["panel"])
        row.pack(anchor="e")

        def copy():
            self.root.clipboard_clear()
            self.root.clipboard_append(str(self.ws.grids))
            self.set_status("Folder path copied", "ok")
        self.button(row, "Close", win.destroy).pack(side="right", padx=(6, 0))
        self.button(row, "Copy path", copy, "primary").pack(side="right")
        win.bind("<Escape>", lambda e: win.destroy())

    def show_help(self):
        win, body = self._dialog(f"About {APP_NAME}")
        frame = tk.Frame(body, bg=C["card"])
        frame.pack(fill="both", expand=True)
        text = tk.Text(frame, width=86, height=min(26, max(12, (self.root.winfo_height() - 200) // 18)), bg=C["card"],
                       fg=C["text"], relief="flat", wrap="word", font=self.font(10), padx=12, pady=10,
                       highlightthickness=0)
        bar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        text.insert("1.0", HELP_TEXT.format(version=VERSION, folder=self.ws.grids,
                                            dnd="on" if self.dnd_ready else "not available on this system"))
        text.configure(state="disabled")
        text.pack(fill="both", expand=True)
        row = tk.Frame(body, bg=C["panel"])
        row.pack(fill="x", pady=(10, 0))

        def copy():
            self.root.clipboard_clear()
            self.root.clipboard_append(str(self.ws.grids))
            self.set_status("Folder path copied", "ok")
        self.button(row, "Close", win.destroy, "primary").pack(side="right")
        self.button(row, "Open maps folder", self.open_folder).pack(side="left")
        self.button(row, "Copy folder path", copy).pack(side="left", padx=6)
        win.bind("<Escape>", lambda e: win.destroy())

    def set_zoom(self, target, event=None):
        if not self.session:
            return
        target = max(MIN_CELL, min(MAX_CELL, int(target)))
        if target == self.zoom:
            return
        vx = event.x if event is not None else self.canvas.winfo_width() / 2
        vy = event.y if event is not None else self.canvas.winfo_height() / 2
        lx = (self.canvas.canvasx(vx) - PAD) / self.zoom
        ly = (self.canvas.canvasy(vy) - PAD) / self.zoom
        self.zoom = target
        self.render()
        d = self.session.data
        tw, th = 2 * PAD + d.width * target, 2 * PAD + d.height * target
        self.canvas.xview_moveto(max(0, PAD + lx * target - vx) / tw)
        self.canvas.yview_moveto(max(0, PAD + ly * target - vy) / th)

    def wheel_zoom(self, event, direction):
        self.set_zoom(self.zoom + 3 * direction, event)
        return "break"

    def fit(self):
        if not self.session:
            return
        self.root.update_idletasks()
        d = self.session.data
        size = min((self.canvas.winfo_width() - 2 * PAD) // d.width, (self.canvas.winfo_height() - 2 * PAD) // d.height)
        self.zoom = -1
        self.set_zoom(max(MIN_CELL, min(MAX_CELL, size)))
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)

    def close(self):
        if self.session and self.session.in_stroke:
            self.release()
        if self.unsaved and not self.retry_save():
            if not messagebox.askyesno("Close without saving?", f"{self.name} could not be saved. Close anyway?",
                                       parent=self.root):
                return
        self.root.destroy()


class ImportDialog:
    """Shows what will be imported, flags errors and name clashes, then imports on confirmation."""

    def __init__(self, studio: Studio, items):
        self.s, self.items = studio, items

    def run(self):
        s = self.s
        win, body = s._dialog("Import maps")
        ok = [i for i in self.items if i.data]
        clashes = [i for i in ok if s.ws.exists(i.name)]
        s.label(body, f"{len(ok)} map(s) ready, {len(self.items) - len(ok)} with problems. Nothing has been changed yet.",
                10, bold=True).pack(anchor="w")
        tree = ttk.Treeview(body, columns=("name", "size", "status"), show="headings", height=min(10, len(self.items)))
        for col, text, width in (("name", "Map name", 160), ("size", "Size", 70), ("status", "Status", 520)):
            tree.heading(col, text=text)
            tree.column(col, width=width, anchor="w")
        for item in self.items:
            if item.data:
                d = item.data
                status = "Ready" + ("" if item.has_json else " (no JSON: place Start/Goal after import)")
                if s.ws.exists(item.name):
                    status = "Name already in your library"
                tree.insert("", "end", values=(item.name, f"{d.width}×{d.height}", status))
            else:
                tree.insert("", "end", values=(item.name, "—", "✕ " + item.error.split(". ")[0]))
        tree.pack(fill="x", pady=10)
        choice = tk.StringVar(value="rename")
        if clashes:
            s.label(body, "When a map with the same name already exists:", 10).pack(anchor="w")
            for value, text in (("rename", "Keep both (import under a new name)"),
                                ("replace", "Replace mine (a backup copy is kept)"),
                                ("skip", "Skip it")):
                s._radio(body, text, choice, value).pack(anchor="w")
        s.label(body, "The original files are only read, never changed.", 9, C["muted"]).pack(anchor="w", pady=(8, 0))
        buttons = tk.Frame(body, bg=C["panel"])
        buttons.pack(anchor="e", pady=(12, 0))

        def go():
            decisions = {i.source: choice.get() for i in clashes}
            win.destroy()
            s.finish_import(s.ws.apply_import(self.items, decisions))

        s.button(buttons, "Cancel", win.destroy).pack(side="right", padx=(6, 0))
        b = s.button(buttons, f"Import {len(ok)} map(s)", go, "primary")
        b.pack(side="right")
        if not ok:
            b.configure(state="disabled")
        win.bind("<Escape>", lambda e: win.destroy())
        win.grab_set()
        win.wait_window()


class ChooseMaps:
    def __init__(self, studio: Studio, names, current):
        self.s, self.names, self.current, self.result = studio, names, current, []

    def run(self):
        s = self.s
        win, body = s._dialog("Export maps as ZIP")
        s.label(body, "Choose the maps to include:", 10, bold=True).pack(anchor="w", pady=(0, 8))
        vars_ = {}
        for name in self.names:
            var = tk.BooleanVar(value=name in BUILTIN_SIZES or name == self.current)
            s._check(body, name, var).pack(anchor="w")
            vars_[name] = var
        buttons = tk.Frame(body, bg=C["panel"])
        buttons.pack(anchor="e", pady=(12, 0))

        def ok():
            self.result = [n for n, v in vars_.items() if v.get()]
            win.destroy()

        s.button(buttons, "Cancel", win.destroy).pack(side="right", padx=(6, 0))
        s.button(buttons, "Choose file…", ok, "primary").pack(side="right")
        win.grab_set()
        win.wait_window()
        return self.result


HELP_TEXT = """Maps Studio {version}

A small editor for occupancy-grid maps used in route-planning experiments.

DRAWING
  1 Wall · 2 Erase · 3 Start · 4 Goal        Right-click always erases
  Drag to paint lines. Click Start or Goal again with its own tool to remove it.
  Ctrl+Z undo · Ctrl+Y redo · Ctrl+S retry a failed save
  Ctrl + mouse wheel or Ctrl +/− to zoom · F fit · T route preview on/off
  Ctrl+N new map · Ctrl+O import files · F1 this help

FILES
  <name>.csv   one row per line, 0 = free, 1 = wall, no header.  grid[y][x]
  <name>.json  {{"width": W, "height": H, "start": [x+0.5, y+0.5], "goal": [x+0.5, y+0.5]}}
  Every edit is saved straight away. Imports accept CSV files saved from Excel
  (commas, semicolons or tabs). Drag and drop: {dnd}.

YOUR MAPS ARE STORED IN
  {folder}
  The library starts empty: import your maps (drag and drop or Import) or create new ones.
  Backups of each map (taken before the first save of a session) are in .maps_studio/backups.
  Importing never changes the original files. Exporting never replaces files without asking.

MEDIUM CHANGED
  Created as an exact copy of Medium. It is add-only: you can add walls (shown in orange),
  but Medium's walls, Start and Goal are locked. Choose the new obstacle yourself.

ROUTE PREVIEW
  The blue line is a breadth-first search over 8 neighbours with no corner cutting. It shows
  that Start and Goal are connected and counts grid moves. It is NOT A*, not the shortest
  Euclidean route, not the continuous optimum and not the group's evaluator.

ABOUT
  An AI-assisted preparation tool. It contains no assessed coursework algorithms.
"""
