# Windows 10/11 test checklist

The uploaded v2.0.0 `.exe` is an x64 Windows executable generated under Wine. That proves a Windows-format binary exists, **not** that it is verified on native Windows. For a release matching the patched v2.0.1 source, build it in GitHub Actions on `windows-latest`.

## Steps on a Windows PC

1. Download the **Windows ZIP** from your GitHub Actions build or Release page. Verify its SHA-256 from the same run/release.
2. Extract the entire ZIP first. Double-click `MapsStudio.exe`. Do not execute it while viewing the ZIP. Confirm it opens without Python installed.
3. Check that the first-launch library is empty, not a blank crash. Import your six Easy/Medium/Hard `.csv`/`.json` files from a **copied** team folder, using the Import menu.
4. Check dimensions **20x20**, **40x40**, **60x60**; obstacle counts **61**, **256**, **623**; BFS previews **25**, **53**, **91** grid moves.
5. Open Easy. Draw one wall in a safe free cell, undo, redo, close, reopen. Confirm changes persist **only** in `%LOCALAPPDATA%\Maps Studio\grids`.
6. Export Easy into a **temporary folder**. Verify the CSV/JSON files appear. Try exporting over those files and check the confirmation prompt.
7. Import using Explorer drag-and-drop. If drag-and-drop fails, note that Import menu remains available; capture the error.
8. Confirm UI, buttons, labels, cursor, mouse wheel/zoom, Help, Open folder, and dialogs at 1366x768 and normal Windows display scaling.
9. Open a second program instance. Confirm it is read-only; close it and continue editing the first.
10. Try duplicating Medium as Medium Changed. Confirm only new walls can be added, and Start/Goal plus original walls are protected.

## Report

Record Windows version, display scaling, package SHA-256, whether built by Actions, checklist result, and screenshots of any failure. If a test fails, keep the repository release marked **pre-release** until fixed.

Do not bypass your institution's security policy or disable antivirus. If SmartScreen or antivirus blocks the file, check provenance and work with the device owner/IT rather than ignoring a warning.
