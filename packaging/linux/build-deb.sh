#!/usr/bin/env bash
# Build an Ubuntu/Kubuntu installer: dist/maps-studio_<version>_all.deb
# It installs the source app in /opt and uses the system's python3 + python3-tk.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VERSION="$(python3 -c "import sys; sys.path.insert(0, '$ROOT'); import maps_studio; print(maps_studio.VERSION)")"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
APP="$STAGE/opt/maps-studio"
mkdir -p "$APP/vendor" "$STAGE/usr/bin" "$STAGE/usr/share/applications" \
         "$STAGE/usr/share/icons/hicolor/256x256/apps" "$STAGE/DEBIAN"
cp -r "$ROOT/maps_studio" "$ROOT/assets" "$ROOT/MapsStudio.py" "$APP/"
find "$APP" -name "__pycache__" -prune -exec rm -rf {} +
# Drag-and-drop helper (MIT licence), bundled because Ubuntu has no apt package for it.
if [ -n "${MAPS_STUDIO_VENDOR_SOURCE:-}" ]; then
  # Offline packagers may point to an already verified copy of tkinterdnd2.
  cp -a "$MAPS_STUDIO_VENDOR_SOURCE"/. "$APP/vendor/"
else
  python3 -m pip install --quiet --no-deps --target "$APP/vendor" tkinterdnd2==0.4.2
fi
cat > "$STAGE/usr/bin/maps-studio" <<'LAUNCH'
#!/bin/sh
export PYTHONPATH="/opt/maps-studio/vendor${PYTHONPATH:+:$PYTHONPATH}"
exec python3 /opt/maps-studio/MapsStudio.py "$@"
LAUNCH
chmod 755 "$STAGE/usr/bin/maps-studio"
cat > "$STAGE/usr/share/applications/maps-studio.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Maps Studio
Comment=Draw and share grid maps for route-planning experiments
Exec=maps-studio
Icon=maps-studio
Terminal=false
Categories=Education;Development;
DESK
cp "$ROOT/assets/logo.png" "$STAGE/usr/share/icons/hicolor/256x256/apps/maps-studio.png"
SIZE="$(du -sk "$STAGE/opt" | cut -f1)"
cat > "$STAGE/DEBIAN/control" <<CTRL
Package: maps-studio
Version: $VERSION
Section: education
Priority: optional
Architecture: all
Installed-Size: $SIZE
Depends: python3 (>= 3.10), python3-tk
Maintainer: Maps Studio contributors <noreply@example.invalid>
Description: Grid map editor for COMP1827 route-planning experiments
 Draw, generate, import and export CSV/JSON occupancy-grid maps.
 AI-assisted preparation tool; contains no assessed coursework algorithms.
CTRL
cat > "$STAGE/DEBIAN/prerm" <<'PRERM'
#!/bin/sh
# Python may have written bytecode caches next to the app; remove them so the folder can be deleted.
find /opt/maps-studio -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
exit 0
PRERM
chmod 755 "$STAGE/DEBIAN/prerm"
find "$STAGE" -type d -exec chmod 755 {} +
mkdir -p "$ROOT/dist"
OUT="$ROOT/dist/maps-studio_${VERSION}_all.deb"
dpkg-deb --root-owner-group --build "$STAGE" "$OUT" >/dev/null
echo "Built $OUT"
