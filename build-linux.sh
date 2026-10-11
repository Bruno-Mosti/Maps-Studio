#!/usr/bin/env bash
# Build the self-contained Linux executable: dist/MapsStudio
set -euo pipefail
cd "$(dirname "$0")"
python3 -c 'import tkinter' || { echo "Install Tkinter first:  sudo apt install python3-tk"; exit 1; }
python3 -m pip install -r requirements-build.txt
python3 -m PyInstaller --clean --noconfirm MapsStudio.spec
chmod +x dist/MapsStudio
echo "Built dist/MapsStudio"
