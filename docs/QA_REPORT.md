# Maps Studio code, UI and release audit — 11 October 2026

## Scope

Originally audited the COMP1827 Map Studio v2.0.0 source and older release files. Maps Studio is a rebrand of the reviewed v2.0.1 source. Version 2.0.1 source includes targeted fixes and new tests.

## Code quality

**Strengths:** distinct `core.py`/`storage.py`/`ui.py`, no assessed optimisation algorithm, data directory outside installation, explicit map validation, autosave/recovery journal, collision-free preview labelled as BFS, supported GitHub Actions workflows, MIT licence and third-party notices.

**Fixes in v2.0.1:** non-finite JSON input rejection; broken ZIP member handling and archive limits; too-large import rejection; folder export partial-file rollback; ZIP overwrite confirmation; improved small-window route label and simpler first-launch path text; explicit Python package metadata. Added regression tests.

**Remaining risks and limits:** A CSV/JSON pair is recoverable but not atomic as a pair across a sudden crash; the crash-safe journal applies to workspace saves, not arbitrary export-folder power loss. Imports are validated first but are not an all-or-nothing multi-map transaction. Multi-user simultaneous editing across a network is not locked. Large 200x200 grids may redraw more slowly. Final native Windows visual/drag-drop/UI inspection requires a real Windows machine.

## Verification performed in audit environment

- Original four uploaded release files matched `SHA256SUMS` (SHA-256).
- Original source passed 72 automated tests using `xvfb-run` on Linux.
- Updated 2.0.1 source passed **78 tests** plus **3 subtests** using a virtual display.
- Updated 2.0.1 source `python MapsStudio.py --smoke-test` **passed** using a virtual display.
- Static Python compilation passed.
- Previously uploaded Windows ZIP contained the old `COMP1827-MapStudio.exe`, built under Wine. An `MapsStudio.exe` release must be built on the Windows GitHub Actions runner and tested on native Windows.
- Previous uploaded `.deb` and Linux portable tarball were branded COMP1827 Map Studio, not Maps Studio. The rebranded Maps Studio package will be produced by GitHub Actions.
- The previous COMP1827-branded 2.0.1 `.deb` passed a virtual-display test; that does **not** verify a newly branded Maps Studio installer.
- New native Maps Studio Windows/Linux executables have **not** been built here. GitHub Actions is configured to build/test them; it must be run before distribution.

## UI observations from supplied screenshots

- The empty map library on first launch is intentional. Users should import their team's CSV/JSON pairs instead of overwriting packaged maps.
- Source screenshot showing a `Z:\tmp\claude-...` folder is from a temporary Wine/testing profile, not the expected normal `%LOCALAPPDATA%` location on native Windows.
- The screenshot with the system file manager behind the import preview is an overlapping windows screenshot, not proof of a modal stacking defect. Verify modal focus on native Windows.
- The previous long route-preview text and verbose storage path could be cramped; shortened in 2.0.1.

## Release rule

**Do not publish a final `v2.0.1` release until the native Windows and Linux GitHub build workflow succeeds and someone smoke-tests the Windows output on Windows.**

## Final naming change
Maps Studio is a naming-only rebrand of the previously tested v2.0.1 source. Native Windows builds from the renamed source still require Windows CI; renaming an old .exe does not change its embedded title or metadata.

## Maps Studio rebrand verification (11 October 2026)
- Renamed source: **78 pytest tests and 3 subtests passed** on Linux under Xvfb.
- `python MapsStudio.py --smoke-test` passed.
- New `maps-studio_2.0.1_all.deb` built using a previously downloaded copy of the same `tkinterdnd2==0.4.2` dependency, and its extracted app passed the GUI smoke test. This is not a live install test on a user's Kubuntu machine.
- **No rebranded Windows binary was compiled here.** Use the existing Windows binary you already tested while GitHub Actions builds `MapsStudio.exe` with the new name/icon/title.
