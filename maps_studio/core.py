"""Map model, validation, connectivity preview, draft generators and editing rules.

Nothing in this module touches the file system or Tkinter, so all of it is unit-tested directly.

Coordinates: a cell is (x, y); the grid is a list of rows, so a cell's value is grid[y][x].
CSV: one row per line, 0 = free, 1 = blocked, no header.
JSON: Start/Goal are stored as cell centres [x + 0.5, y + 0.5].
"""
from __future__ import annotations

import csv
import io
import math
import random
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

Cell = tuple[int, int]
Grid = list[list[int]]

# The four coursework maps keep their agreed sizes; any other name may use any size in range.
BUILTIN_SIZES: dict[str, tuple[int, int]] = {
    "easy": (20, 20),
    "medium": (40, 40),
    "hard": (60, 60),
    "medium_changed": (40, 40),
}
BUILTIN_ORDER = ["easy", "medium", "hard", "medium_changed"]
CHANGED_NAME = "medium_changed"
CHANGED_BASE = "medium"
MIN_SIDE, MAX_SIDE = 3, 200
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


class MapError(ValueError):
    """A map file or an edit request is invalid. The message is shown to the user as written."""


# --------------------------------------------------------------------------- names

def sanitize_name(stem: str) -> str:
    """Turn a file stem such as 'My Map (v2)' into a safe library name such as 'my_map_v2'."""
    name = re.sub(r"[^a-z0-9_-]+", "_", stem.strip().lower()).strip("_-")
    return name[:40] or "map"


def check_name(name: str) -> str:
    if not NAME_RE.match(name):
        raise MapError(
            f"'{name}' is not a valid map name. Use 1–40 lowercase letters, digits, '-' or '_', "
            "starting with a letter or digit."
        )
    return name


def check_size(name: str, width: int, height: int) -> None:
    if name in BUILTIN_SIZES and BUILTIN_SIZES[name] != (width, height):
        w, h = BUILTIN_SIZES[name]
        raise MapError(f"'{name}' must be {w}×{h}, but this grid is {width}×{height}.")
    if not (MIN_SIDE <= width <= MAX_SIDE and MIN_SIDE <= height <= MAX_SIDE):
        raise MapError(f"Map sides must be between {MIN_SIDE} and {MAX_SIDE} cells (got {width}×{height}).")


# --------------------------------------------------------------------------- CSV

def parse_grid_text(text: str) -> Grid:
    """Parse CSV text into a grid. Accepts a UTF-8 BOM, CRLF or LF, ',' ';' or tab, and blank lines."""
    text = text.lstrip("﻿")
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise MapError("The CSV file is empty.")
    delimiter = max((",", ";", "\t"), key=lambda d: lines[0].count(d))
    grid: Grid = []
    for number, row in enumerate(csv.reader(lines, delimiter=delimiter), start=1):
        cells = [value.strip() for value in row]
        if cells and cells[-1] == "":          # tolerate one trailing delimiter
            cells = cells[:-1]
        bad = [value for value in cells if value not in ("0", "1")]
        if bad:
            raise MapError(f"CSV line {number} contains '{bad[0]}'. Only 0 (free) and 1 (wall) are allowed, with no header.")
        grid.append([int(value) for value in cells])
    width = len(grid[0])
    for number, row in enumerate(grid, start=1):
        if len(row) != width:
            raise MapError(f"CSV line {number} has {len(row)} cells but line 1 has {width}. Every row must be the same length.")
    return grid


def grid_to_csv_text(grid: Grid) -> str:
    """CSV text with CRLF line endings, matching the files the team already shares."""
    buffer = io.StringIO()
    csv.writer(buffer).writerows(grid)
    return buffer.getvalue()


# --------------------------------------------------------------------------- JSON metadata

def _point(value, key: str, grid: Grid) -> Optional[Cell]:
    if value is None:
        return None
    if (not isinstance(value, list) or len(value) != 2
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in value)):
        raise MapError(f"'{key}' must be null or a cell centre such as [1.5, 2.5].")
    # JSON permits NaN/Infinity in some parsers. Reject them as user errors instead of
    # allowing round(nan) / round(inf) to crash map import or the editor window.
    if not all(math.isfinite(v) for v in value):
        raise MapError(f"'{key}' must contain finite cell-centre coordinates.")
    x, y = value[0] - 0.5, value[1] - 0.5
    if abs(x - round(x)) > 1e-6 or abs(y - round(y)) > 1e-6:
        raise MapError(f"'{key}' {value} is not a cell centre; it should end in .5, for example [1.5, 2.5].")
    x, y = int(round(x)), int(round(y))
    height, width = len(grid), len(grid[0])
    if not (0 <= x < width and 0 <= y < height):
        raise MapError(f"'{key}' {value} is outside the {width}×{height} map.")
    if grid[y][x] == 1:
        raise MapError(f"'{key}' {value} is on a wall cell ({x}, {y}).")
    return (x, y)


def parse_metadata(meta, grid: Grid) -> tuple[Optional[Cell], Optional[Cell], dict]:
    """Return (start, goal, extra_keys). Width/height in the JSON must agree with the CSV if present."""
    if not isinstance(meta, dict):
        raise MapError("The JSON file must contain an object such as {\"width\": 20, ...}.")
    height, width = len(grid), len(grid[0])
    for key, actual in (("width", width), ("height", height)):
        if key in meta and meta[key] != actual:
            raise MapError(f"JSON says {key} = {meta[key]}, but the CSV has {key} {actual}.")
    start = _point(meta.get("start"), "start", grid)
    goal = _point(meta.get("goal"), "goal", grid)
    if start is not None and start == goal:
        raise MapError("Start and Goal are on the same cell.")
    extra = {k: v for k, v in meta.items() if k not in ("width", "height", "start", "goal")}
    return start, goal, extra


def metadata_dict(grid: Grid, start: Optional[Cell], goal: Optional[Cell], extra: Optional[dict] = None) -> dict:
    meta = {
        "width": len(grid[0]),
        "height": len(grid),
        "start": None if start is None else [start[0] + 0.5, start[1] + 0.5],
        "goal": None if goal is None else [goal[0] + 0.5, goal[1] + 0.5],
    }
    for key, value in (extra or {}).items():
        meta.setdefault(key, value)
    return meta


# --------------------------------------------------------------------------- model

@dataclass
class MapData:
    name: str
    grid: Grid
    start: Optional[Cell] = None
    goal: Optional[Cell] = None
    extra: dict = field(default_factory=dict)

    @property
    def width(self) -> int:
        return len(self.grid[0])

    @property
    def height(self) -> int:
        return len(self.grid)

    @property
    def walls(self) -> int:
        return sum(map(sum, self.grid))

    def copy(self, name: Optional[str] = None) -> "MapData":
        return MapData(name or self.name, [row[:] for row in self.grid], self.start, self.goal, dict(self.extra))

    def validate(self) -> None:
        check_name(self.name)
        if not self.grid or not self.grid[0]:
            raise MapError("The map has no cells.")
        check_size(self.name, self.width, self.height)
        if any(len(row) != self.width for row in self.grid):
            raise MapError("Every row must have the same number of cells.")
        if any(type(value) is not int or value not in (0, 1) for row in self.grid for value in row):
            raise MapError("Cells must be 0 or 1.")
        parse_metadata(metadata_dict(self.grid, self.start, self.goal), self.grid)


def blank(name: str, width: int, height: int) -> MapData:
    check_name(name)
    check_size(name, width, height)
    return MapData(name, [[0] * width for _ in range(height)])


def default_endpoints(width: int, height: int) -> tuple[Cell, Cell]:
    """Opposite corners, one cell in from the border."""
    return (min(1, width - 1), min(1, height - 1)), (max(0, width - 2), max(0, height - 2))


# --------------------------------------------------------------------------- connectivity preview

STEPS = [(dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dx or dy]


def route_preview(grid: Grid, start: Optional[Cell], goal: Optional[Cell]) -> Optional[list[Cell]]:
    """Breadth-first search over 8 neighbours with no diagonal corner cutting.

    Returns one path with the fewest MOVES (a diagonal counts as one move), or None.
    It checks connectivity only. It is NOT A*, NOT a shortest Euclidean route and NOT the
    continuous optimum or the group's evaluator.
    """
    if start is None or goal is None:
        return None
    height, width = len(grid), len(grid[0])
    for x, y in (start, goal):
        if not (0 <= x < width and 0 <= y < height) or grid[y][x]:
            return None
    parent: dict[Cell, Optional[Cell]] = {start: None}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        if current == goal:
            path = []
            while current is not None:
                path.append(current)
                current = parent[current]
            return path[::-1]
        x, y = current
        for dx, dy in STEPS:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height) or grid[ny][nx] or (nx, ny) in parent:
                continue
            if dx and dy and (grid[y][nx] or grid[ny][x]):
                continue
            parent[(nx, ny)] = current
            queue.append((nx, ny))
    return None


# --------------------------------------------------------------------------- draft generators

STYLES = {
    "scatter": "Scattered cells",
    "segments": "Wall segments",
    "rooms": "Rooms and doors",
}


def _scatter(rng, w, h, target, protected):
    cells = [(x, y) for y in range(h) for x in range(w) if (x, y) not in protected]
    rng.shuffle(cells)
    grid = [[0] * w for _ in range(h)]
    for x, y in cells[:target]:
        grid[y][x] = 1
    return grid


def _segments(rng, w, h, target, protected):
    grid = [[0] * w for _ in range(h)]
    placed, tries, longest = 0, 0, max(3, min(w, h) // 5)
    while placed < target and tries < w * h * 30:
        tries += 1
        x, y = rng.randrange(w), rng.randrange(h)
        dx, dy = rng.choice(((1, 0), (0, 1)))
        for k in range(rng.randint(2, longest)):
            px, py = x + dx * k, y + dy * k
            if not (0 <= px < w and 0 <= py < h):
                break
            if (px, py) in protected or grid[py][px]:
                continue
            grid[py][px] = 1
            placed += 1
            if placed >= target:
                break
    return grid


def _rooms(rng, w, h, target, protected):
    """Recursive division: straight walls with 2-cell doors, then thinned to the target density."""
    grid = [[0] * w for _ in range(h)]
    min_room = max(4, min(w, h) // 6)

    def divide(x0, y0, x1, y1):            # inclusive bounds of an open chamber
        cw, ch = x1 - x0 + 1, y1 - y0 + 1
        if cw < 2 * min_room + 1 and ch < 2 * min_room + 1:
            return
        vertical = cw > ch if cw != ch else rng.random() < 0.5
        if vertical and cw >= 2 * min_room + 1:
            wx = rng.randint(x0 + min_room, x1 - min_room)
            door = rng.randint(y0, max(y0, y1 - 1))
            for y in range(y0, y1 + 1):
                if y not in (door, door + 1):
                    grid[y][wx] = 1
            divide(x0, y0, wx - 1, y1)
            divide(wx + 1, y0, x1, y1)
        elif ch >= 2 * min_room + 1:
            wy = rng.randint(y0 + min_room, y1 - min_room)
            door = rng.randint(x0, max(x0, x1 - 1))
            for x in range(x0, x1 + 1):
                if x not in (door, door + 1):
                    grid[wy][x] = 1
            divide(x0, y0, x1, wy - 1)
            divide(x0, wy + 1, x1, y1)

    divide(0, 0, w - 1, h - 1)
    for x, y in protected:
        grid[y][x] = 0
    walls = [(x, y) for y in range(h) for x in range(w) if grid[y][x]]
    rng.shuffle(walls)
    for x, y in walls[: max(0, len(walls) - target)]:
        grid[y][x] = 0
    return grid


def _carve(grid: Grid, start: Cell, goal: Cell) -> None:
    """Open the fewest walls needed to join Start and Goal (0-1 BFS over 4-neighbour moves).

    Straight moves never cut corners, so the opened corridor is always legal for the preview too.
    """
    height, width = len(grid), len(grid[0])
    cost = {start: 0}
    parent: dict[Cell, Optional[Cell]] = {start: None}
    queue = deque([start])
    while queue:
        x, y = cell = queue.popleft()
        if cell == goal:
            break
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            step = grid[ny][nx]
            if cost[cell] + step < cost.get((nx, ny), 1 << 30):
                cost[(nx, ny)] = cost[cell] + step
                parent[(nx, ny)] = cell
                (queue.append if step else queue.appendleft)((nx, ny))
    cell = goal
    while cell is not None:
        grid[cell[1]][cell[0]] = 0
        cell = parent[cell]


def generate(width: int, height: int, style: str, density: float, seed: int,
             start: Cell, goal: Cell, attempts: int = 25) -> tuple[Grid, int]:
    """Make a reproducible draft whose Start and Goal are connected.

    density is a fraction (0.03-0.45). Tries seed, seed + 1, ... for a layout that is connected as
    drawn. If none is, the first layout gets the fewest walls removed to join Start and Goal.
    Returns (grid, seed_used). Drafts are sketches to edit, not validated maps.
    """
    if style not in STYLES:
        raise MapError(f"Unknown generator style '{style}'.")
    if not 0.03 <= density <= 0.45:
        raise MapError("Obstacle density must be between 3% and 45%.")
    if start is None or goal is None or start == goal:
        raise MapError("Place Start and Goal on different cells before generating.")
    maker = {"scatter": _scatter, "segments": _segments, "rooms": _rooms}[style]
    target = round(width * height * density)
    protected = {start, goal}
    first = None
    for attempt in range(attempts):
        used = seed + attempt
        grid = maker(random.Random(f"{style}:{used}"), width, height, target, protected)
        if route_preview(grid, start, goal) is not None:
            return grid, used
        if first is None:
            first = grid
    _carve(first, start, goal)
    return first, seed


# --------------------------------------------------------------------------- editing rules

TOOLS = ("wall", "erase", "start", "goal")


class EditSession:
    """Applies edits to one map with undo/redo.

    If base_grid is given (Medium Changed), the session is ADD-ONLY: walls from the base cannot
    be erased, Start and Goal are locked, and Clear only removes the walls added since the copy.
    """

    HISTORY = 100

    def __init__(self, data: MapData, base_grid: Optional[Grid] = None):
        self.data = data
        self.base = base_grid
        self.undo_stack: list = []
        self.redo_stack: list = []
        self._before = None

    @property
    def add_only(self) -> bool:
        return self.base is not None

    def snapshot(self):
        return ([row[:] for row in self.data.grid], self.data.start, self.data.goal)

    def _restore(self, snap):
        self.data.grid = [row[:] for row in snap[0]]
        self.data.start, self.data.goal = snap[1], snap[2]

    # strokes group many cell edits into one undo step
    def begin(self):
        if self._before is None:
            self._before = self.snapshot()

    def end(self) -> bool:
        """Close the stroke. Returns True if anything changed (so the caller should save)."""
        before, self._before = self._before, None
        if before is None or before == self.snapshot():
            return False
        self.undo_stack.append(before)
        del self.undo_stack[:-self.HISTORY]
        self.redo_stack.clear()
        return True

    @property
    def in_stroke(self) -> bool:
        return self._before is not None

    def apply(self, cell: Cell, tool: str) -> bool:
        """Apply one tool to one cell. Returns True if the map changed."""
        d = self.data
        x, y = cell
        if not (0 <= x < d.width and 0 <= y < d.height):
            return False
        if tool == "wall":
            if cell in (d.start, d.goal) or d.grid[y][x]:
                return False
            d.grid[y][x] = 1
        elif tool == "erase":
            if cell in (d.start, d.goal):
                if self.add_only:
                    return False
                if cell == d.start:
                    d.start = None
                else:
                    d.goal = None
            elif d.grid[y][x]:
                if self.add_only and self.base[y][x]:
                    return False
                d.grid[y][x] = 0
            else:
                return False
        elif tool in ("start", "goal"):
            if self.add_only or d.grid[y][x]:
                return False
            other = d.goal if tool == "start" else d.start
            if cell == other:
                return False
            if getattr(d, tool) == cell:
                return False
            setattr(d, tool, cell)
        else:
            raise MapError(f"Unknown tool '{tool}'.")
        return True

    def toggle_marker(self, cell: Cell, tool: str) -> bool:
        """Clicking the existing Start (or Goal) with its own tool removes it."""
        if self.add_only or tool not in ("start", "goal") or getattr(self.data, tool) != cell:
            return False
        setattr(self.data, tool, None)
        return True

    def replace_grid(self, grid: Grid) -> None:
        if self.add_only:
            raise MapError("Medium Changed can only gain walls; it cannot be regenerated.")
        self.data.grid = [row[:] for row in grid]

    def clear(self) -> None:
        if self.add_only:
            self.data.grid = [row[:] for row in self.base]
        else:
            self.data.grid = [[0] * self.data.width for _ in range(self.data.height)]
            self.data.start = self.data.goal = None

    def undo(self) -> bool:
        if self.in_stroke or not self.undo_stack:
            return False
        self.redo_stack.append(self.snapshot())
        self._restore(self.undo_stack.pop())
        return True

    def redo(self) -> bool:
        if self.in_stroke or not self.redo_stack:
            return False
        self.undo_stack.append(self.snapshot())
        self._restore(self.redo_stack.pop())
        return True

    def added_walls(self) -> list[Cell]:
        if not self.add_only:
            return []
        return [(x, y) for y, row in enumerate(self.data.grid) for x, v in enumerate(row)
                if v and not self.base[y][x]]


def line_cells(a: Cell, b: Cell) -> list[Cell]:
    """Cells on a straight drag from a to b (excluding a), so fast drags do not skip cells."""
    (x0, y0), (x1, y1) = a, b
    steps = max(abs(x1 - x0), abs(y1 - y0))
    return [(round(x0 + (x1 - x0) * i / steps), round(y0 + (y1 - y0) * i / steps)) for i in range(1, steps + 1)]
