"""Workspace on disk: loading, crash-safe saving, backups, import, export and the instance lock.

Folder layout (inside the user's data directory, never inside the install folder):

    grids/<name>.csv, grids/<name>.json        the editable maps
    grids/.maps_studio/recovery/                 previous pair + journal while a save is in progress
    grids/.maps_studio/backups/<name>/           timestamped copies, taken before the first save of a session
    grids/.maps_studio/trash/                    maps removed from the library
    grids/.maps_studio/medium_changed.base.csv   the Medium grid that Medium Changed was copied from

Saving a CSV + JSON pair cannot be one atomic operation on ordinary file systems. Instead each save
keeps the previous pair and a journal until both new files are verified. If the app or computer
stops half-way, the next load finds the journal and restores the last complete pair.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from .core import (BUILTIN_ORDER, BUILTIN_SIZES, CHANGED_BASE, CHANGED_NAME, NAME_RE, MapData, MapError,
                   check_name, grid_to_csv_text, metadata_dict, parse_grid_text, parse_metadata, sanitize_name)

KEEP_BACKUPS = 20
ZIP_MEMBER_LIMIT = 5_000_000
ZIP_MAX_MEMBERS = 500


class SaveError(OSError):
    """Writing failed. The message says what happened and whether the previous version is intact."""


def user_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return base / "Maps Studio"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def _write_synced(path: Path, data: bytes) -> None:
    with open(path, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _copy(src: Path, dst: Path) -> None:
    """Copy a small file and flush it to disk (used for recovery copies, backups and export backups)."""
    _write_synced(Path(dst), Path(src).read_bytes())


def _temp_in(directory: Path, data: bytes, suffix: str) -> Path:
    fd, name = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise
    return Path(name)


def encode_pair(data: MapData) -> tuple[bytes, bytes]:
    data.validate()
    csv_bytes = grid_to_csv_text(data.grid).encode("utf-8")
    meta = metadata_dict(data.grid, data.start, data.goal, data.extra)
    json_bytes = (json.dumps(meta, indent=2) + "\n").encode("utf-8")
    return csv_bytes, json_bytes


def decode_pair(name: str, csv_bytes: bytes, json_bytes: Optional[bytes]) -> MapData:
    try:
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise MapError("The CSV file is not UTF-8 text.") from None
    grid = parse_grid_text(text)
    start = goal = None
    extra: dict = {}
    if json_bytes is not None:
        try:
            meta = json.loads(json_bytes.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise MapError(f"The JSON file could not be read: {error}") from None
        start, goal, extra = parse_metadata(meta, grid)
    data = MapData(name, grid, start, goal, extra)
    data.validate()
    return data


@dataclass
class MapInfo:
    name: str
    exists: bool
    width: int = 0
    height: int = 0
    error: str = ""


@dataclass
class ImportItem:
    source: str
    name: str
    data: Optional[MapData] = None
    error: str = ""
    has_json: bool = True


@dataclass
class ImportReport:
    imported: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    failed: list = field(default_factory=list)


class Workspace:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.grids = self.root / "grids"
        self.hidden = self.grids / ".maps-studio"
        self.recovery = self.hidden / "recovery"
        self.backups = self.hidden / "backups"
        self.trash = self.hidden / "trash"
        self._backed_up: set[str] = set()
        self.recovered: list[str] = []

    # ------------------------------------------------------------------ setup
    def ensure(self) -> None:
        """Create the folders. The library starts empty: maps are added by importing or creating them."""
        for folder in (self.grids, self.recovery, self.backups, self.trash):
            folder.mkdir(parents=True, exist_ok=True)
        for leftover in self.grids.glob(".tmp-*"):      # temp files from a save that was interrupted
            leftover.unlink(missing_ok=True)
        if sys.platform == "win32":                     # hide the app's own folder in Explorer, like on Linux
            try:
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(str(self.hidden), 0x2)
            except Exception:
                pass

    def has_maps(self) -> bool:
        return any(NAME_RE.match(p.stem) for p in self.grids.glob("*.csv")) if self.grids.is_dir() else False

    def paths(self, name: str) -> tuple[Path, Path]:
        return self.grids / f"{name}.csv", self.grids / f"{name}.json"

    def exists(self, name: str) -> bool:
        return self.paths(name)[0].exists()

    # ------------------------------------------------------------------ listing
    def list_maps(self) -> list[MapInfo]:
        names = set(BUILTIN_ORDER)
        if self.grids.is_dir():
            for path in self.grids.glob("*.csv"):
                if NAME_RE.match(path.stem):
                    names.add(path.stem)
        order = BUILTIN_ORDER + sorted(n for n in names if n not in BUILTIN_ORDER)
        result = []
        for name in order:
            if not self.exists(name):
                w, h = BUILTIN_SIZES.get(name, (0, 0))
                result.append(MapInfo(name, False, w, h))
                continue
            try:
                data = self.load(name)
                result.append(MapInfo(name, True, data.width, data.height))
            except (MapError, OSError) as error:
                result.append(MapInfo(name, True, error=str(error)))
        return result

    # ------------------------------------------------------------------ load / save
    def _journal(self, name: str) -> Path:
        return self.recovery / f"{name}.journal.json"

    def recover(self, name: str, rollback: bool = False) -> Optional[str]:
        """Finish or roll back a save that was interrupted. Returns a message if anything was done.

        If both files already match the journal, the save had completed and only the journal is removed.
        With rollback=True (used when a save fails while running) the previous pair is always restored.
        """
        journal = self._journal(name)
        if not journal.exists():
            return None
        csv_path, json_path = self.paths(name)
        try:
            record = json.loads(journal.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            record = {}
        try:
            done = not rollback and (csv_path.exists() and json_path.exists()
                    and sha256_file(csv_path) == record.get("csv") and sha256_file(json_path) == record.get("json"))
        except OSError:
            done = False
        if done:
            journal.unlink(missing_ok=True)
            return None
        prev_csv, prev_json = self.recovery / f"{name}.prev.csv", self.recovery / f"{name}.prev.json"
        if record.get("had_previous") and prev_csv.exists():
            _copy(prev_csv, csv_path)
            if record.get("had_json") and prev_json.exists():
                _copy(prev_json, json_path)
            else:
                json_path.unlink(missing_ok=True)
            message = f"{name}: an interrupted save was rolled back to the last complete version."
        else:
            csv_path.unlink(missing_ok=True)
            json_path.unlink(missing_ok=True)
            message = f"{name}: an interrupted first save was removed."
        journal.unlink(missing_ok=True)
        self.recovered.append(message)
        return message

    def load(self, name: str) -> MapData:
        check_name(name)
        self.recover(name)
        csv_path, json_path = self.paths(name)
        if not csv_path.exists():
            raise MapError(f"{name}.csv was not found.")
        json_bytes = json_path.read_bytes() if json_path.exists() else None
        return decode_pair(name, csv_path.read_bytes(), json_bytes)

    def backup(self, name: str, force: bool = False) -> Optional[Path]:
        """Copy the current pair into backups/<name>/ (once per session unless force)."""
        if name in self._backed_up and not force:
            return None
        csv_path, json_path = self.paths(name)
        if not csv_path.exists():
            return None          # nothing to back up yet; the first saved version is backed up next time
        folder = self.backups / name
        folder.mkdir(parents=True, exist_ok=True)
        stamp = _stamp()
        _copy(csv_path, folder / f"{stamp}.csv")
        if json_path.exists():
            _copy(json_path, folder / f"{stamp}.json")
        old = sorted(folder.glob("*.csv"))[:-KEEP_BACKUPS]
        for path in old:
            path.unlink(missing_ok=True)
            path.with_suffix(".json").unlink(missing_ok=True)
        self._backed_up.add(name)
        return folder / f"{stamp}.csv"

    def save(self, data: MapData) -> None:
        """Write both files or neither. Raises SaveError with a clear message on failure."""
        try:
            csv_bytes, json_bytes = encode_pair(data)
        except MapError as error:
            raise SaveError(f"Not saved: {error}") from None
        name = data.name
        csv_path, json_path = self.paths(name)
        journal = self._journal(name)
        prev_csv, prev_json = self.recovery / f"{name}.prev.csv", self.recovery / f"{name}.prev.json"
        temps: list[Path] = []
        had_previous, had_json = csv_path.exists(), json_path.exists()
        try:
            self.grids.mkdir(parents=True, exist_ok=True)
            self.recovery.mkdir(parents=True, exist_ok=True)
            self.recover(name)
            self.backup(name)
            temps = [_temp_in(self.grids, csv_bytes, ".csv"), _temp_in(self.grids, json_bytes, ".json")]
            if had_previous:
                _copy(csv_path, prev_csv)
                if had_json:
                    _copy(json_path, prev_json)
            # From here on, an interruption is repaired by recover() on the next load.
            _write_synced(journal, json.dumps({"csv": sha256_bytes(csv_bytes), "json": sha256_bytes(json_bytes),
                                               "had_previous": had_previous, "had_json": had_json}).encode())
            os.replace(temps[0], csv_path)
            os.replace(temps[1], json_path)
            temps = []
            if csv_path.read_bytes() != csv_bytes or json_path.read_bytes() != json_bytes:
                raise OSError("the files on disk do not match what was written")
            journal.unlink(missing_ok=True)
        except OSError as error:
            for temp in temps:
                temp.unlink(missing_ok=True)
            if not journal.exists():
                note = " Your previous version is unchanged." if had_previous else " Nothing was written."
            else:
                try:
                    message = self.recover(name, rollback=True)
                    if message in self.recovered:
                        self.recovered.remove(message)
                    note = " The previous version was restored." if had_previous else " Nothing was kept."
                except OSError:
                    note = " The previous version will be restored the next time this map is opened."
            raise SaveError(f"Could not save {name}: {error}.{note}") from None

    # ------------------------------------------------------------------ create / copy / remove
    def create(self, data: MapData) -> None:
        if self.exists(data.name) or self.paths(data.name)[1].exists():
            raise MapError(f"A map called '{data.name}' already exists.")
        self.save(data)

    def free_name(self, name: str) -> str:
        if not self.exists(name) and name not in BUILTIN_SIZES:
            return name
        for index in range(2, 1000):
            candidate = f"{name[:36]}_{index}"
            if not self.exists(candidate) and candidate not in BUILTIN_SIZES:
                return candidate
        raise MapError("Too many maps with this name.")

    def remove(self, name: str) -> Path:
        """Move a custom map into the trash folder. The four coursework maps cannot be removed here."""
        if name in BUILTIN_SIZES:
            raise MapError(f"'{name}' is one of the coursework maps and cannot be removed from the library.")
        folder = self.trash / f"{name}-{_stamp()}"
        folder.mkdir(parents=True)
        for path in self.paths(name):
            if path.exists():
                os.replace(path, folder / path.name)
        return folder

    # ------------------------------------------------------------------ Medium Changed
    @property
    def _base_path(self) -> Path:
        return self.hidden / f"{CHANGED_NAME}.base.csv"

    def make_changed(self) -> MapData:
        """Copy Medium to Medium Changed and remember the exact Medium grid it came from."""
        if self.exists(CHANGED_NAME) or self.paths(CHANGED_NAME)[1].exists():
            raise MapError("Medium Changed already exists, so it was not overwritten.")
        if not self.exists(CHANGED_BASE):
            raise MapError("Create Medium first.")
        medium = self.load(CHANGED_BASE)
        if medium.start is None or medium.goal is None:
            raise MapError("Place Medium's Start and Goal before copying it.")
        self.hidden.mkdir(parents=True, exist_ok=True)
        _write_synced(self._base_path, grid_to_csv_text(medium.grid).encode())
        copy = medium.copy(CHANGED_NAME)
        self.save(copy)
        return copy

    def changed_base(self) -> tuple[Optional[list], str]:
        """Return (base_grid, note). note is '' when everything matches."""
        if self._base_path.exists():
            base = parse_grid_text(self._base_path.read_text("utf-8"))
            note = ""
            if self.exists(CHANGED_BASE):
                current = self.load(CHANGED_BASE).grid
                if current != base:
                    note = ("Medium has been edited since Medium Changed was copied. "
                            "Medium Changed still protects the walls of the Medium it was copied from.")
            return base, note
        if not self.exists(CHANGED_BASE):
            return None, "Medium is missing, so Medium Changed has no base map to protect."
        base = self.load(CHANGED_BASE).grid
        if self.exists(CHANGED_NAME):
            changed = self.load(CHANGED_NAME).grid
            if any(b and not c for rb, rc in zip(base, changed) for b, c in zip(rb, rc)):
                return None, ("Medium Changed is missing some of Medium's walls, so it no longer matches Medium. "
                              "Editing is unrestricted until you recreate it from Medium.")
        _write_synced(self._base_path, grid_to_csv_text(base).encode())
        return base, ""

    # ------------------------------------------------------------------ import
    def read_sources(self, sources: Iterable[Path]) -> list[ImportItem]:
        """Read and validate everything first. Nothing is written by this method."""
        items: list[ImportItem] = []
        seen: set[tuple[str, str]] = set()

        def add(label: str, stem: str, csv_bytes: bytes, json_bytes: Optional[bytes]):
            key = (label, stem)
            if key in seen:
                return
            seen.add(key)
            name = sanitize_name(stem)
            try:
                data = decode_pair(name, csv_bytes, json_bytes)
                items.append(ImportItem(label, name, data, has_json=json_bytes is not None))
            except MapError as error:
                items.append(ImportItem(label, name, error=str(error)))

        for source in sources:
            source = Path(source)
            try:
                if source.is_dir():
                    for csv_path in sorted(source.glob("*.csv")):
                        jp = csv_path.with_suffix(".json")
                        if csv_path.stat().st_size > ZIP_MEMBER_LIMIT or (jp.is_file() and jp.stat().st_size > ZIP_MEMBER_LIMIT):
                            items.append(ImportItem(str(csv_path), sanitize_name(csv_path.stem),
                                                    error="Map file exceeds the 5 MB import limit."))
                            continue
                        add(str(csv_path), csv_path.stem, csv_path.read_bytes(), jp.read_bytes() if jp.is_file() else None)
                elif source.suffix.lower() == ".zip":
                    self._read_zip(source, add, items)
                elif source.suffix.lower() in (".csv", ".json"):
                    csv_path, jp = source.with_suffix(".csv"), source.with_suffix(".json")
                    if not csv_path.is_file():
                        items.append(ImportItem(str(source), sanitize_name(source.stem),
                                                error="No CSV with the same name was found next to this JSON file."))
                        continue
                    if csv_path.stat().st_size > ZIP_MEMBER_LIMIT or (jp.is_file() and jp.stat().st_size > ZIP_MEMBER_LIMIT):
                        items.append(ImportItem(str(csv_path), sanitize_name(csv_path.stem),
                                                error="Map file exceeds the 5 MB import limit."))
                        continue
                    add(str(csv_path), csv_path.stem, csv_path.read_bytes(), jp.read_bytes() if jp.is_file() else None)
                else:
                    items.append(ImportItem(str(source), sanitize_name(source.stem),
                                            error="Only .csv, .json, .zip files and folders can be imported."))
            except OSError as error:
                items.append(ImportItem(str(source), sanitize_name(source.stem), error=f"Could not read: {error}"))
        return items

    @staticmethod
    def _read_zip(path: Path, add, items: list) -> None:
        try:
            archive = zipfile.ZipFile(path)
        except zipfile.BadZipFile:
            items.append(ImportItem(str(path), sanitize_name(path.stem), error="This is not a valid ZIP file."))
            return
        with archive:
            all_members = [m for m in archive.infolist() if not m.is_dir()]
            if len(all_members) > ZIP_MAX_MEMBERS:
                items.append(ImportItem(str(path), sanitize_name(path.stem),
                                        error=f"ZIP contains more than {ZIP_MAX_MEMBERS} files; import a smaller archive."))
                return
            members = all_members
            by_name = {m.filename: m for m in members}
            for member in members:
                if not member.filename.lower().endswith(".csv") or "__MACOSX" in member.filename:
                    continue
                stem = Path(member.filename).stem
                label = f"{path.name}:{member.filename}"
                json_member = by_name.get(member.filename[:-4] + ".json")
                if member.file_size > ZIP_MEMBER_LIMIT or (json_member and json_member.file_size > ZIP_MEMBER_LIMIT):
                    items.append(ImportItem(label, sanitize_name(stem), error="File too large for a map (over 5 MB)."))
                    continue
                try:
                    csv_content = archive.read(member)
                    json_content = archive.read(json_member) if json_member else None
                except (OSError, zipfile.BadZipFile, RuntimeError, EOFError, ValueError) as error:
                    items.append(ImportItem(label, sanitize_name(stem),
                                            error=f"ZIP member could not be read: {error}"))
                    continue
                add(label, stem, csv_content, json_content)

    def apply_import(self, items: list[ImportItem], decisions: dict[str, str]) -> ImportReport:
        """decisions maps a source label to 'replace', 'rename' or 'skip' (for names already in use)."""
        report = ImportReport()
        for item in items:
            if item.data is None:
                report.failed.append((item.source, item.error))
                continue
            choice = decisions.get(item.source, "replace" if not self.exists(item.name) else "skip")
            if self.exists(item.name) and choice == "skip":
                report.skipped.append((item.source, item.name))
                continue
            data = item.data.copy()
            if self.exists(item.name) and choice == "rename":
                if item.name in BUILTIN_SIZES:
                    data.name = self.free_name(item.name + "_imported")
                else:
                    data.name = self.free_name(item.name)
            try:
                self.save(data)
                if data.name == CHANGED_NAME:
                    self._base_path.unlink(missing_ok=True)   # re-derived from Medium the next time it opens
                report.imported.append((item.source, data.name))
            except SaveError as error:
                report.failed.append((item.source, str(error)))
        return report

    # ------------------------------------------------------------------ export
    def export_pair(self, name: str, destination: Path, overwrite: bool = False) -> list[Path]:
        """Copy one map pair to a folder. Existing files there are backed up first, never silently replaced."""
        data = self.load(name)
        csv_bytes, json_bytes = encode_pair(data)
        destination = Path(destination)
        targets = [destination / f"{name}.csv", destination / f"{name}.json"]
        existing = [t for t in targets if t.exists()]
        if existing and not overwrite:
            raise FileExistsError(", ".join(t.name for t in existing) + " already exist in that folder.")
        stamp = _stamp()
        backups = []
        temps: list[Path] = []
        try:
            for target in existing:
                backup = target.with_name(f"{target.name}.backup-{stamp}")
                _copy(target, backup)
                backups.append((target, backup))
            temps = [_temp_in(destination, csv_bytes, ".csv"), _temp_in(destination, json_bytes, ".json")]
            os.replace(temps[0], targets[0])
            os.replace(temps[1], targets[1])
            temps = []
            if targets[0].read_bytes() != csv_bytes or targets[1].read_bytes() != json_bytes:
                raise OSError("the exported files do not match the map")
        except OSError as error:
            for temp in temps:
                temp.unlink(missing_ok=True)
            restored = True
            saved_old = {target for target, _ in backups}
            for target in targets:
                try:
                    if target in saved_old:
                        backup = next(backup for old, backup in backups if old == target)
                        _copy(backup, target)
                    else:
                        # No file existed here before exporting. Remove a partially
                        # installed new file rather than leaving half a CSV/JSON pair.
                        target.unlink(missing_ok=True)
                except OSError:
                    restored = False
            note = ("Previous destination state restored." if restored else
                    "Rollback was incomplete; check the .backup files before retrying.")
            raise SaveError(f"Export failed: {error}. {note}".strip()) from None
        return [b for _, b in backups]

    def export_zip(self, names: list[str], zip_path: Path, overwrite: bool = False) -> None:
        """Write maps into one ZIP, refusing accidental overwrites by default."""
        zip_path = Path(zip_path)
        if zip_path.exists() and not overwrite:
            raise FileExistsError(f"{zip_path.name} already exists.")
        fd, temp_name = tempfile.mkstemp(dir=zip_path.parent, prefix=".tmp-", suffix=".zip")
        os.close(fd)
        temp = Path(temp_name)
        try:
            with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name in names:
                    csv_bytes, json_bytes = encode_pair(self.load(name))
                    archive.writestr(f"maps/{name}.csv", csv_bytes)
                    archive.writestr(f"maps/{name}.json", json_bytes)
            os.replace(temp, zip_path)
        except (OSError, MapError) as error:
            temp.unlink(missing_ok=True)
            raise SaveError(f"ZIP export failed: {error}") from None


class InstanceLock:
    """Only one Maps Studio window may edit a workspace at a time. Released automatically if the app dies."""

    def __init__(self, root: Path):
        self.path = Path(root) / "studio.lock"
        self._handle = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+")
        try:
            if sys.platform == "win32":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt
                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self._handle.close()
        self._handle = None
