"""Interface tests. They need a display (on Linux CI: xvfb-run) and are skipped without one."""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]

try:
    import tkinter as tk
    HAVE_DISPLAY = sys.platform in ("win32", "darwin") or bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
except ImportError:        # Python built without Tk
    HAVE_DISPLAY = False


@unittest.skipUnless(HAVE_DISPLAY, "needs Tk and a display")
class StudioTests(unittest.TestCase):
    def setUp(self):
        from maps_studio import ui
        from maps_studio.storage import Workspace
        self.ui = ui
        self.tmp = Path(tempfile.mkdtemp())
        from tests.test_storage import make_team_folder
        self.ws = Workspace(self.tmp / "data")
        self.ws.ensure()
        self.ws.apply_import(self.ws.read_sources([make_team_folder(self.tmp / "team")]), {})
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = ui.Studio(self.root, self.ws)
        self.root.update()
        self._askyesno = ui.messagebox.askyesno
        ui.messagebox.askyesno = lambda *a, **k: True
        ui.messagebox.showerror = lambda *a, **k: None
        ui.messagebox.showinfo = lambda *a, **k: None

    def tearDown(self):
        self.ui.messagebox.askyesno = self._askyesno
        self.root.destroy()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def event_at(self, cell, button=1):
        z, pad = self.app.zoom, self.ui.PAD
        self.app.canvas.xview_moveto(0)
        self.app.canvas.yview_moveto(0)
        return SimpleNamespace(x=pad + cell[0] * z + z // 2, y=pad + cell[1] * z + z // 2, num=button)

    def free_cells(self, count):
        d = self.app.session.data
        cells = [(x, y) for y in range(d.height) for x in range(d.width)
                 if not d.grid[y][x] and (x, y) not in (d.start, d.goal)]
        return cells[:count]

    def test_paint_stroke_saves_and_undo_restores(self):
        self.app.open_map("easy")
        before = self.ws.load("easy").walls
        a, b = self.free_cells(2)
        self.app.press(self.event_at(a))
        self.app.drag(self.event_at(b))
        self.app.release()
        self.assertGreater(self.ws.load("easy").walls, before)
        self.app.undo()
        self.assertEqual(self.ws.load("easy").walls, before)

    def test_right_click_erases(self):
        self.app.open_map("easy")
        d = self.app.session.data
        wall = next((x, y) for y, row in enumerate(d.grid) for x, v in enumerate(row) if v)
        self.app.press(self.event_at(wall, button=3))
        self.app.release()
        self.assertEqual(self.ws.load("easy").grid[wall[1]][wall[0]], 0)

    def test_medium_changed_is_add_only(self):
        self.app.open_map("medium_changed")
        self.assertTrue(self.app.session.add_only)
        base = self.app.session.base
        wall = next((x, y) for y, row in enumerate(base) for x, v in enumerate(row) if v)
        self.app.choose_tool("erase")
        self.app.press(self.event_at(wall))
        self.app.release()
        self.assertEqual(self.ws.load("medium_changed").grid[wall[1]][wall[0]], 1)
        self.assertIn("add-only", self.app.status.get())

    def test_failed_save_is_visible(self):
        from maps_studio.storage import SaveError
        self.app.open_map("easy")
        self.ws.save = lambda data: (_ for _ in ()).throw(SaveError("disk full"))
        (cell,) = self.free_cells(1)
        self.app.press(self.event_at(cell))
        self.app.release()
        self.assertTrue(self.app.unsaved)
        self.assertIn("NOT SAVED", self.app.status.get())
        self.assertIn("NOT SAVED", self.app.title_label.cget("text"))

    def test_read_only_window_does_not_edit(self):
        self.root.destroy()
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = self.ui.Studio(self.root, self.ws, read_only=True)
        self.app.open_map("easy")
        before = (self.ws.grids / "easy.csv").read_bytes()
        (cell,) = self.free_cells(1)
        self.app.press(self.event_at(cell))
        self.app.release()
        self.assertEqual((self.ws.grids / "easy.csv").read_bytes(), before)

    def test_empty_library_shows_welcome(self):
        from maps_studio.storage import Workspace
        self.root.destroy()
        self.root = tk.Tk()
        self.root.withdraw()
        empty = Workspace(self.tmp / "empty")
        empty.ensure()
        self.app = self.ui.Studio(self.root, empty)
        self.root.update()
        self.assertIsNone(self.app.session)
        texts = [self.app.canvas.itemcget(i, "text") for i in self.app.canvas.find_all()
                 if self.app.canvas.type(i) == "text"]
        self.assertIn("No maps yet", texts)

    def test_folder_command_or_fallback(self):
        import sys
        command = self.app.folder_command()
        if sys.platform == "win32":
            self.assertIsNone(command)                 # Windows uses os.startfile
        elif command is not None:
            self.assertEqual(command[-1], str(self.ws.grids))
        env = self.app._desktop_env()
        self.assertIsInstance(env, dict)

    def test_frozen_linux_build_restores_library_path_for_file_manager(self):
        from unittest import mock
        env = {"LD_LIBRARY_PATH": "/tmaps_studio/_MEI123", "LD_LIBRARY_PATH_ORIG": "/usr/local/lib",
               "TCL_LIBRARY": "/tmaps_studio/_MEI123/tcl", "HOME": "/home/u"}
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.dict(os.environ, env, clear=True):
            out = self.app._desktop_env()
        self.assertEqual(out["LD_LIBRARY_PATH"], "/usr/local/lib")
        self.assertNotIn("TCL_LIBRARY", out)
        self.assertEqual(out["HOME"], "/home/u")
        env.pop("LD_LIBRARY_PATH_ORIG")
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.dict(os.environ, env, clear=True):
            self.assertNotIn("LD_LIBRARY_PATH", self.app._desktop_env())

    def test_buttons_disabled_without_a_map(self):
        self.app.session, self.app.name = None, None
        self.app.update_buttons()
        self.assertEqual(str(self.app.clear_btn["state"]), "disabled")
        self.app.open_map("easy")
        self.assertEqual(str(self.app.clear_btn["state"]), "normal")

    def test_import_paths_adds_map(self):
        src = self.tmp / "incoming"
        src.mkdir()
        (src / "Tiny.csv").write_text("0,0,0\n0,1,0\n0,0,0\n")
        report = self.ws.apply_import(self.ws.read_sources([src]), {})
        self.app.finish_import(report)
        self.assertEqual(self.app.name, "tiny")
        self.assertIn("tiny", self.app.lib_names)


if __name__ == "__main__":
    unittest.main()
