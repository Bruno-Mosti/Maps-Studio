# Contributing

- Keep map rules in `maps_studio/core.py` (no file or UI code there), file handling in
  `maps_studio/storage.py`, and the window in `maps_studio/ui.py`.
- Add or update a test for every change, then run `python3 -m pytest -q`
  (`xvfb-run -a python3 -m pytest -q` on a Linux machine with no screen).
- Do not commit real project maps. The app ships empty and tests generate their own maps.
- Do not add route-planning algorithms (A*, ACO, PSO, ABC, DFO, optimum calculations) to this app.
  Those are assessed coursework and live in each member's own code.
- Note user-facing changes in `CHANGELOG.md`.
