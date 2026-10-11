"""Optional drag-and-drop support.

Plain Tkinter cannot receive files dragged from the desktop. If the small 'tkinterdnd2' package is
available (it is bundled in the release builds), the window accepts dropped files and folders.
Without it, everything still works through the Import menu.
"""
from __future__ import annotations

import tkinter as tk


def make_root() -> tuple[tk.Tk, bool]:
    try:
        from tkinterdnd2 import TkinterDnD
        return TkinterDnD.Tk(), True
    except Exception:          # package missing, or its Tcl extension failed to load on this system
        return tk.Tk(), False


def enable_drop(widgets, on_enter, on_leave, on_drop) -> bool:
    try:
        from tkinterdnd2 import DND_FILES
    except Exception:
        return False
    for widget in widgets:
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<DropEnter>>", lambda e: (on_enter(), e.action)[1])
            widget.dnd_bind("<<DropLeave>>", lambda e: (on_leave(), e.action)[1])
            widget.dnd_bind("<<Drop>>", lambda e, w=widget: (on_drop(w.tk.splitlist(e.data)), e.action)[1])
        except Exception:
            return False
    return True
