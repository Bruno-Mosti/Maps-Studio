"""Start-up: command-line options, data folder, single-instance lock and the main window."""
from __future__ import annotations

import argparse
import sys
import tempfile
import traceback
from pathlib import Path

from . import APP_NAME, VERSION


def resource_dir() -> Path:
    """Folder holding assets/ (inside the PyInstaller bundle when frozen)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


def _windows_dpi_awareness() -> None:
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def _smoke(app, root) -> None:
    """Run the main paths without a person, then quit. CI runs this on the built Windows and Linux programs.

    It starts from the empty library, imports two generated maps from a folder, edits, undoes,
    creates Medium Changed, checks it is add-only, and exports a map back out byte for byte.
    """
    from .core import blank, default_endpoints, generate
    from .storage import encode_pair
    failures = []

    def step():
        try:
            ws = app.ws
            assert not ws.has_maps(), "library should start empty"
            source = Path(tempfile.mkdtemp(prefix="mapsstudio-smoke-src-"))
            for name, size in (("easy", 20), ("medium", 40)):
                data = blank(name, size, size)
                data.start, data.goal = default_endpoints(size, size)
                data.grid, _ = generate(size, size, "segments", 0.18, 5, data.start, data.goal)
                csv_bytes, json_bytes = encode_pair(data)
                (source / f"{name}.csv").write_bytes(csv_bytes)
                (source / f"{name}.json").write_bytes(json_bytes)
            report = ws.apply_import(ws.read_sources([source]), {})
            assert sorted(n for _, n in report.imported) == ["easy", "medium"], report
            app.finish_import(report, quiet=True)
            root.update()
            app.open_map("easy")
            root.update()
            d = app.session.data
            free = next((x, y) for y, row in enumerate(d.grid) for x, v in enumerate(row)
                        if not v and (x, y) not in (d.start, d.goal))
            before = d.walls
            app.session.begin()
            app.session.apply(free, "wall")
            assert app.session.end() and app.save()
            assert ws.load("easy").walls == before + 1
            app.undo()
            assert ws.load("easy").walls == before
            ws.make_changed()
            app.open_map("medium_changed")
            root.update()
            base = app.session.base
            wall = next((x, y) for y, row in enumerate(base) for x, v in enumerate(row) if v)
            assert app.session.add_only and not app.session.apply(wall, "erase")
            out = Path(tempfile.mkdtemp(prefix="mapsstudio-smoke-out-"))
            ws.export_pair("medium", out)
            assert (out / "medium.csv").read_bytes() == (source / "medium.csv").read_bytes()
            assert app.folder_command() is not None or sys.platform == "win32"
        except Exception:
            failures.append(traceback.format_exc())
        root.after(200, root.destroy)

    root.after(400, step)
    root.mainloop()
    if failures:
        print(failures[0], file=sys.stderr)
        raise SystemExit(1)
    print("smoke test passed")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="maps-studio", description=f"{APP_NAME} {VERSION}")
    parser.add_argument("--data-dir", type=Path, help="use this folder instead of the normal user data folder")
    parser.add_argument("--smoke-test", action="store_true",
                        help="import two generated maps, edit, undo, export, then exit (uses a temporary folder)")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)

    from .storage import InstanceLock, Workspace, user_data_dir
    if args.smoke_test and not args.data_dir:
        args.data_dir = Path(tempfile.mkdtemp(prefix="mapsstudio-smoke-"))
    root_dir = args.data_dir or user_data_dir()
    workspace = Workspace(root_dir)
    workspace.ensure()
    lock = InstanceLock(root_dir)
    read_only = not lock.acquire()

    _windows_dpi_awareness()
    from .dnd import make_root
    from .ui import Studio
    import tkinter as tk
    root, dnd = make_root()
    try:
        icon = resource_dir() / "assets" / "logo.png"
        if icon.is_file():
            root._icon = tk.PhotoImage(file=str(icon))
            root.iconphoto(True, root._icon)
    except tk.TclError:
        pass
    app = Studio(root, workspace, read_only=read_only, dnd=dnd)
    try:
        if args.smoke_test:
            if getattr(sys, "frozen", False) and not dnd:
                print("drag-and-drop support failed to load in this build", file=sys.stderr)
                raise SystemExit(2)
            _smoke(app, root)
        else:
            root.mainloop()
    finally:
        lock.release()
    return 0
