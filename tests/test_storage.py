"""Tests for maps_studio.storage: empty start, importing team maps, crash-safe saving, import, export, Medium Changed, lock."""
import json
import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from maps_studio.core import EditSession, MapError, blank, default_endpoints, generate, metadata_dict, route_preview
from maps_studio.storage import InstanceLock, SaveError, Workspace, encode_pair

def make_team_folder(folder: Path) -> Path:
    """Write three coursework-sized maps (easy 20, medium 40, hard 60) as CSV + JSON, like a shared folder."""
    folder.mkdir(parents=True, exist_ok=True)
    for name, size, seed in (("easy", 20, 1), ("medium", 40, 2), ("hard", 60, 3)):
        data = blank(name, size, size)
        data.start, data.goal = default_endpoints(size, size)
        data.grid, _ = generate(size, size, "segments", 0.17, seed, data.start, data.goal)
        csv_bytes, _ = encode_pair(data)
        (folder / f"{name}.csv").write_bytes(csv_bytes)
        # Indent 4, as some of the team's files use, to prove other JSON layouts are accepted.
        (folder / f"{name}.json").write_text(json.dumps(metadata_dict(data.grid, data.start, data.goal), indent=4))
    return folder


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.team = make_team_folder(self.tmp / "team")
        self.ws = Workspace(self.tmp / "data")
        self.ws.ensure()
        report = self.ws.apply_import(self.ws.read_sources([self.team]), {})
        assert len(report.imported) == 3, report

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class StartAndImportTests(unittest.TestCase):
    def test_library_starts_empty(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            ws = Workspace(tmp)
            ws.ensure()
            self.assertFalse(ws.has_maps())
            infos = ws.list_maps()
            self.assertEqual([i.name for i in infos], ["easy", "medium", "hard", "medium_changed"])
            self.assertFalse(any(i.exists for i in infos))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class ImportedTeamMapTests(Base):
    def test_csv_bytes_kept_and_json_values_kept(self):
        for name in ("easy", "medium", "hard"):
            self.assertEqual((self.ws.grids / f"{name}.csv").read_bytes(), (self.team / f"{name}.csv").read_bytes())
            self.assertEqual(json.loads((self.ws.grids / f"{name}.json").read_text()),
                             json.loads((self.team / f"{name}.json").read_text()))

    def test_sizes_and_connectivity(self):
        for name, size in (("easy", 20), ("medium", 40), ("hard", 60)):
            data = self.ws.load(name)
            self.assertEqual((data.width, data.height), (size, size))
            self.assertIsNotNone(route_preview(data.grid, data.start, data.goal))

    def test_listing(self):
        names = [info.name for info in self.ws.list_maps()]
        self.assertEqual(names[:4], ["easy", "medium", "hard", "medium_changed"])
        changed = [i for i in self.ws.list_maps() if i.name == "medium_changed"][0]
        self.assertFalse(changed.exists)


class SaveTests(Base):
    def test_round_trip_and_json_format(self):
        data = blank("lab", 6, 4)
        data.grid[1][2] = 1
        data.start, data.goal = (0, 0), (5, 3)
        self.ws.create(data)
        again = self.ws.load("lab")
        self.assertEqual((again.grid, again.start, again.goal), (data.grid, (0, 0), (5, 3)))
        meta = json.loads((self.ws.grids / "lab.json").read_text())
        self.assertEqual(meta, {"width": 6, "height": 4, "start": [0.5, 0.5], "goal": [5.5, 3.5]})

    def test_create_refuses_existing(self):
        with self.assertRaises(MapError):
            self.ws.create(blank("easy", 20, 20))

    def test_invalid_map_never_written(self):
        data = self.ws.load("easy")
        data.grid[data.start[1]][data.start[0]] = 1        # wall on Start
        before = (self.ws.grids / "easy.csv").read_bytes()
        with self.assertRaises(SaveError):
            self.ws.save(data)
        self.assertEqual((self.ws.grids / "easy.csv").read_bytes(), before)

    def test_failure_before_replacing_keeps_old_files(self):
        before = [p.read_bytes() for p in self.ws.paths("medium")]
        data = self.ws.load("medium")
        data.grid[10][10] = 1
        with mock.patch("maps_studio.storage.tempfile.mkstemp", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(SaveError, "disk full.*unchanged"):
                self.ws.save(data)
        self.assertEqual([p.read_bytes() for p in self.ws.paths("medium")], before)

    def test_failure_between_the_two_files_rolls_back(self):
        before = [p.read_bytes() for p in self.ws.paths("hard")]
        data = self.ws.load("hard")
        data.grid[0][0] = 1
        real = os.replace
        calls = []

        def flaky(src, dst):
            calls.append(dst)
            if len(calls) == 2:
                raise OSError("device removed")
            return real(src, dst)

        with mock.patch("maps_studio.storage.os.replace", side_effect=flaky):
            with self.assertRaisesRegex(SaveError, "restored"):
                self.ws.save(data)
        self.assertEqual([p.read_bytes() for p in self.ws.paths("hard")], before)

    def test_crash_mid_save_is_repaired_on_next_load(self):
        before = [p.read_bytes() for p in self.ws.paths("easy")]
        data = self.ws.load("easy")
        data.grid[10][10] = 1 - data.grid[10][10]
        data.start = next((x, y) for y, row in enumerate(data.grid) for x, v in enumerate(row)
                          if not v and (x, y) not in (data.start, data.goal))   # JSON changes too
        real = os.replace
        calls = []

        def crash(src, dst):
            calls.append(dst)
            if len(calls) == 2:
                raise KeyboardInterrupt  # stands in for the process being killed
            return real(src, dst)

        with mock.patch("maps_studio.storage.os.replace", side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                self.ws.save(data)
        self.assertNotEqual((self.ws.grids / "easy.csv").read_bytes(), before[0])   # half-written state
        fresh = Workspace(self.ws.root)
        fresh.load("easy")
        self.assertEqual([p.read_bytes() for p in fresh.paths("easy")], before)
        self.assertTrue(fresh.recovered)

    def test_crash_after_both_files_counts_as_saved(self):
        # Only the CSV changes here, so once the CSV is replaced the pair on disk IS the new version.
        data = self.ws.load("easy")
        data.grid[10][10] = 1 - data.grid[10][10]
        real = os.replace
        calls = []

        def crash(src, dst):
            calls.append(dst)
            if len(calls) == 2:
                raise KeyboardInterrupt
            return real(src, dst)

        with mock.patch("maps_studio.storage.os.replace", side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                self.ws.save(data)
        fresh = Workspace(self.ws.root)
        self.assertEqual(fresh.load("easy").grid, data.grid)
        self.assertFalse(fresh.recovered)

    def test_backups_taken_once_per_session(self):
        data = self.ws.load("easy")
        for value in (1, 0, 1):
            data.grid[9][9] = value
            self.ws.save(data)
        backups = list((self.ws.backups / "easy").glob("*.csv"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), (self.team / "easy.csv").read_bytes())


class ImportTests(Base):
    def write(self, folder, name, text, meta=None):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{name}.csv").write_text(text, encoding="utf-8")
        if meta is not None:
            (folder / f"{name}.json").write_text(json.dumps(meta))

    def test_folder_with_good_and_bad_maps(self):
        src = self.tmp / "shared"
        self.write(src, "Lab One", "0,0,0\n0,1,0\n0,0,0\n", {"start": [0.5, 0.5], "goal": [2.5, 2.5]})
        self.write(src, "broken", "0,0\n0,5\n")
        items = self.ws.read_sources([src])
        self.assertEqual({i.name: bool(i.data) for i in items}, {"lab_one": True, "broken": False})
        self.assertFalse(self.ws.exists("lab_one"))            # reading never writes
        report = self.ws.apply_import(items, {})
        self.assertEqual([n for _, n in report.imported], ["lab_one"])
        self.assertEqual(len(report.failed), 1)
        self.assertEqual(self.ws.load("lab_one").goal, (2, 2))
        self.assertTrue((src / "Lab One.csv").exists())        # source untouched

    def test_single_excel_csv_without_json(self):
        src = self.tmp / "dl"
        self.write(src, "excel", "﻿0;0;0;0\r\n0;1;1;0\r\n0;0;0;0\r\n")
        items = self.ws.read_sources([src / "excel.csv"])
        self.assertTrue(items[0].data and not items[0].has_json)
        self.ws.apply_import(items, {})
        data = self.ws.load("excel")
        self.assertEqual((data.width, data.height, data.start), (4, 3, None))

    def test_zip_import(self):
        archive = self.tmp / "maps.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("maps/tiny.csv", "0,0,0\n0,0,0\n0,0,0\n")
            z.writestr("maps/tiny.json", json.dumps({"start": [0.5, 0.5], "goal": [2.5, 0.5]}))
            z.writestr("__MACOSX/maps/._tiny.csv", "junk")
        items = self.ws.read_sources([archive])
        self.assertEqual([(i.name, i.data.goal) for i in items], [("tiny", (2, 0))])

    def test_builtin_name_with_wrong_size_rejected(self):
        src = self.tmp / "wrong"
        self.write(src, "easy", "0,0,0\n0,0,0\n0,0,0\n")
        items = self.ws.read_sources([src])
        self.assertIn("must be 20×20", items[0].error)

    def test_name_collision_decisions(self):
        src = self.tmp / "update"
        shutil.copytree(self.team, src)
        text = (src / "easy.csv").read_text().replace("0", "1", 1)
        (src / "easy.csv").write_text(text)
        items = [i for i in self.ws.read_sources([src]) if i.name == "easy"]
        label = items[0].source
        report = self.ws.apply_import(items, {label: "skip"})
        self.assertEqual(len(report.skipped), 1)
        report = self.ws.apply_import(items, {label: "rename"})
        self.assertEqual(report.imported[0][1], "easy_imported")
        report = self.ws.apply_import(items, {label: "replace"})
        self.assertEqual(report.imported[0][1], "easy")
        backups = list((self.ws.backups / "easy").glob("*.csv"))
        self.assertEqual(backups[0].read_bytes(), (self.team / "easy.csv").read_bytes())

    def test_unsupported_file(self):
        bad = self.tmp / "notes.txt"
        bad.write_text("hi")
        self.assertIn("Only .csv", self.ws.read_sources([bad])[0].error)


class ExportTests(Base):
    def test_export_refuses_then_backs_up(self):
        out = self.tmp / "onedrive"
        out.mkdir()
        self.ws.export_pair("easy", out)
        with self.assertRaises(FileExistsError):
            self.ws.export_pair("easy", out)
        backups = self.ws.export_pair("easy", out, overwrite=True)
        self.assertEqual(len(backups), 2)
        self.assertEqual((out / "easy.csv").read_bytes(), (self.team / "easy.csv").read_bytes())

    def test_failed_export_restores_destination(self):
        out = self.tmp / "dest"
        out.mkdir()
        (out / "easy.csv").write_text("old")
        (out / "easy.json").write_text("old")
        real = os.replace
        calls = []

        def flaky(src, dst):
            calls.append(dst)
            if len(calls) == 2:
                raise OSError("read-only")
            return real(src, dst)

        with mock.patch("maps_studio.storage.os.replace", side_effect=flaky):
            with self.assertRaises(SaveError):
                self.ws.export_pair("easy", out, overwrite=True)
        self.assertEqual((out / "easy.csv").read_text(), "old")
        self.assertEqual((out / "easy.json").read_text(), "old")

    def test_zip_export(self):
        target = self.tmp / "all.zip"
        self.ws.export_zip(["easy", "hard"], target)
        with zipfile.ZipFile(target) as z:
            self.assertEqual(sorted(z.namelist()), ["maps/easy.csv", "maps/easy.json", "maps/hard.csv", "maps/hard.json"])
            self.assertEqual(z.read("maps/hard.csv"), (self.team / "hard.csv").read_bytes())


class MediumChangedTests(Base):
    def test_copy_is_identical_and_base_recorded(self):
        self.ws.make_changed()
        self.assertEqual(self.ws.load("medium_changed").grid, self.ws.load("medium").grid)
        base, note = self.ws.changed_base()
        self.assertEqual((base, note), (self.ws.load("medium").grid, ""))
        with self.assertRaises(MapError):
            self.ws.make_changed()

    def test_divergence_detected_and_old_base_protected(self):
        self.ws.make_changed()
        original = self.ws.load("medium").grid
        medium = self.ws.load("medium")
        medium.grid[0][0] = 1 - medium.grid[0][0]
        self.ws.save(medium)
        base, note = self.ws.changed_base()
        self.assertEqual(base, original)
        self.assertIn("edited since", note)

    def test_add_only_editing_end_to_end(self):
        self.ws.make_changed()
        base, _ = self.ws.changed_base()
        session = EditSession(self.ws.load("medium_changed"), base)
        wall = next((x, y) for y, row in enumerate(base) for x, v in enumerate(row) if v)
        self.assertFalse(session.apply(wall, "erase"))
        free = next((x, y) for y, row in enumerate(base) for x, v in enumerate(row)
                    if not v and (x, y) not in (session.data.start, session.data.goal))
        self.assertTrue(session.apply(free, "wall"))
        self.ws.save(session.data)
        self.assertEqual(self.ws.load("medium_changed").walls, self.ws.load("medium").walls + 1)


class LibraryTests(Base):
    def test_remove_custom_only(self):
        self.ws.create(blank("scratch", 5, 5))
        folder = self.ws.remove("scratch")
        self.assertFalse(self.ws.exists("scratch"))
        self.assertTrue((folder / "scratch.csv").exists())
        with self.assertRaises(MapError):
            self.ws.remove("easy")

    def test_free_name(self):
        self.assertEqual(self.ws.free_name("easy"), "easy_2")
        self.assertEqual(self.ws.free_name("new"), "new")


class LockTests(unittest.TestCase):
    def test_second_lock_refused_until_released(self):
        folder = Path(tempfile.mkdtemp())
        try:
            first, second = InstanceLock(folder), InstanceLock(folder)
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            first.release()
            self.assertTrue(second.acquire())
            second.release()
        finally:
            shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
