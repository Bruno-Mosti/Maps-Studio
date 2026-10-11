Maps Studio 2.0.1 - QUICK START
=====================================

WINDOWS
  1. Extract the ZIP (right-click > Extract All). Do not run it from inside the ZIP.
  2. Double-click MapsStudio.exe.
  3. If Windows SmartScreen says "Windows protected your PC", the app is simply not
     code-signed. Click "More info" > "Run anyway" only if you got it from the team's
     GitHub Releases page.

LINUX
  Portable:  tar -xzf MapsStudio-Linux-x64.tar.gz
             ./MapsStudio/MapsStudio
  Ubuntu / Kubuntu installer:
             sudo apt install ./maps-studio_2.0.1_all.deb
             then open "Maps Studio" from the application menu.

FIRST START
  The library is empty. Drag your easy/medium/hard .csv and .json files (or the folder
  that holds them) onto the window, or click Import. Your original files are only read.

USING IT
  - Pick a map on the left. Tools: 1 Wall, 2 Erase, 3 Start, 4 Goal. Right-click erases.
  - Every edit saves straight away. Ctrl+Z undo, Ctrl+Y redo.
  - Import: drag CSV/JSON/ZIP files or a folder onto the window, or use Import.
    The original files are only read, never changed.
  - New map: any size from 3 to 200, empty or a generated draft.
  - Export: one map to a folder, or several maps as a ZIP. Nothing is replaced
    without asking, and replaced files are kept as .backup copies.
  - Help (F1) shows every shortcut and where your maps are stored.

YOUR MAPS LIVE IN
  Windows: %LOCALAPPDATA%\Maps Studio\grids
  Linux:   ~/.local/share/Maps Studio/grids
  "Open folder" opens it; Help (F1) shows the path with a Copy button.
  Updating the app never touches this folder.

FILE FORMAT
  name.csv   one row per line, 0 = free, 1 = wall, no header. grid[y][x]
  name.json  {"width": W, "height": H, "start": [x+0.5, y+0.5], "goal": [x+0.5, y+0.5]}

IMPORTANT
  The blue route is a connectivity preview (fewest grid moves). It is NOT A*, not the
  exact optimum and not the group's evaluator. This is an AI-assisted preparation tool.
