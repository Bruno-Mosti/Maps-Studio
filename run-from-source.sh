#!/usr/bin/env bash
# Run Maps Studio from the source code (needs Python 3.10+ and python3-tk).
cd "$(dirname "$0")"
exec python3 MapsStudio.py "$@"
