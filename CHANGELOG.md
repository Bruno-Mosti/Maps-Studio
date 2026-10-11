# Changelog

## 2.0.1 — Maps Studio branding

- Renamed the MP project and application to **Maps Studio**.
- Kept the existing map editor behaviour, CSV/JSON format, and supplied network logo.
- Build files, documentation and native release names follow the new brand.
- Saved maps from the earlier application remain untouched; import them into the new local library if needed.

---


## 2.0.1 - 2026-10-11

### Fixed
- Malformed JSON coordinates (NaN or Infinity) now produce a useful validation error instead of crashing import.
- Broken ZIP entries and archives with too many files are rejected gracefully.
- Directory/file imports reject oversized maps before loading them into memory.
- Failed folder exports clean up newly created partial CSV/JSON pairs while restoring backed-up originals.
- ZIP export refuses replacing an existing ZIP without explicit confirmation.
- The editor header uses shorter BFS-preview text and a full explanatory tooltip to avoid clipping.
- The first-run screen no longer shows an unreadably long application-data path.
- Added regression tests covering these cases; 78 tests now run.
- Made project metadata installable with explicit version/build configuration.


## 2.0.0 - 2026-10-11

### Added
- Open source under the MIT licence, with third-party notices.
- The app starts with an empty library and a welcome screen; maps are added by drag and drop,
  Import or New map. No project maps are bundled.
- Open folder works in the Windows `.exe` and the Linux binary (the one-file Linux build no longer
  passes its private library path to the file manager), with a Copy path fallback.
- Drag and drop: drop CSV, JSON or ZIP files, or a whole folder, onto the window to import them.
- Import preview that lists every map, its size and any problem before anything is written, with a
  choice for name clashes (keep both, replace with a backup, or skip).
- Imports accept CSV files saved from Excel (UTF-8 BOM, commas, semicolons or tabs) and CSV files
  without a JSON file.
- New map dialog: any name and any size from 3×3 to 200×200, empty or generated.
- Three draft generators (scattered cells, wall segments, rooms and doors), reproducible by seed and
  always connected from Start to Goal.
- Map library that lists every map in your folder, plus Duplicate and Remove (to a trash folder).
- Export several maps as one ZIP.
- Medium Changed is add-only: Medium's walls, Start and Goal are locked, added walls show in orange,
  and the app warns if Medium has been edited since the copy was made.
- Single-window lock: a second Maps Studio window opens read-only instead of overwriting edits.
- Help window (F1), tooltips, cursor coordinates, grid-line toggle, keyboard shortcuts 1–4, Ctrl+N, Ctrl+O.
- `--smoke-test` and `--data-dir` command-line options; GitHub Actions for tests, Windows and Linux
  builds, a .deb package and tagged releases with SHA-256 checksums.

### Changed
- Code split into `core` (rules, no files), `storage` (files) and `ui` (Tkinter), with 72 automated tests.
- The window now fits 1366×768 screens: the zoom bar and status line are always visible.

### Fixed
- A failed save was reported in a dialog but treated as successful, so Export could copy stale files.
  Saves now raise an error, the title shows "NOT SAVED" and Ctrl+S retries.
- The CSV and JSON files were written one after the other with no recovery. A save interrupted between
  them is now rolled back to the last complete pair the next time the map opens.
- Import copied files pair by pair and could stop half-way; everything is now validated before any
  file is written, and each map is saved with the same recovery protection.
- Editor backups were only ever taken once per map (the first version); now a backup is taken before
  the first save of every session and the last 20 are kept.
- CSV files with a UTF-8 BOM (Excel) failed to load.
- Medium Changed used the *current* Medium to decide which walls were protected, so editing Medium
  later unlocked walls in Medium Changed.

## 1.0.0 - 2026-10-11
- First team edition: wall/erase/Start/Goal editing, undo, zoom, connectivity preview, folder import,
  single-map export, private copies in the user data folder.
