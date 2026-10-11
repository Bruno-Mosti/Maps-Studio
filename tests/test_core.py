"""Tests for maps_studio.core. Expected values are worked out by hand, not copied from the code."""
import unittest

from maps_studio.core import (EditSession, MapData, MapError, blank, check_size, generate, grid_to_csv_text,
                            line_cells, metadata_dict, parse_grid_text, parse_metadata, route_preview,
                            sanitize_name)


def moves(grid, start, goal):
    path = route_preview(grid, start, goal)
    return None if path is None else len(path) - 1


class ParseGridTests(unittest.TestCase):
    def test_plain_crlf(self):
        self.assertEqual(parse_grid_text("0,1,0\r\n1,0,0\r\n0,0,0\r\n"), [[0, 1, 0], [1, 0, 0], [0, 0, 0]])

    def test_excel_bom_semicolons_spaces_blank_lines(self):
        text = "﻿0; 1 ;0\n\n1;0;0\n0;0;0\n\n"
        self.assertEqual(parse_grid_text(text), [[0, 1, 0], [1, 0, 0], [0, 0, 0]])

    def test_tabs_and_trailing_delimiter(self):
        self.assertEqual(parse_grid_text("0\t1\t\n1\t0\t\n"), [[0, 1], [1, 0]])

    def test_rejects_other_values_with_line_number(self):
        with self.assertRaisesRegex(MapError, "line 2 contains '2'"):
            parse_grid_text("0,0\n0,2\n")

    def test_rejects_header(self):
        with self.assertRaisesRegex(MapError, "line 1"):
            parse_grid_text("x,y\n0,0\n")

    def test_rejects_ragged_rows(self):
        with self.assertRaisesRegex(MapError, "line 2 has 2 cells"):
            parse_grid_text("0,0,0\n0,0\n")

    def test_rejects_empty(self):
        with self.assertRaises(MapError):
            parse_grid_text("\n\n")

    def test_round_trip_uses_crlf(self):
        grid = [[0, 1], [1, 0]]
        text = grid_to_csv_text(grid)
        self.assertEqual(text, "0,1\r\n1,0\r\n")
        self.assertEqual(parse_grid_text(text), grid)


class MetadataTests(unittest.TestCase):
    grid = [[0, 0, 0], [0, 1, 0], [0, 0, 0]]

    def test_cell_centres(self):
        start, goal, extra = parse_metadata({"width": 3, "height": 3, "start": [0.5, 0.5], "goal": [2.5, 2.5],
                                             "note": "kept"}, self.grid)
        self.assertEqual((start, goal, extra), ((0, 0), (2, 2), {"note": "kept"}))

    def test_null_points_allowed(self):
        self.assertEqual(parse_metadata({"start": None, "goal": None}, self.grid)[:2], (None, None))

    def test_rejects_whole_numbers(self):
        with self.assertRaisesRegex(MapError, "not a cell centre"):
            parse_metadata({"start": [1, 1]}, self.grid)

    def test_rejects_wall_outside_bool_and_same_cell(self):
        for meta in ({"start": [1.5, 1.5]}, {"goal": [3.5, 0.5]}, {"start": [True, 0.5]},
                     {"start": [0.5, 0.5], "goal": [0.5, 0.5]}):
            with self.assertRaises(MapError):
                parse_metadata(meta, self.grid)

    def test_rejects_dimension_mismatch(self):
        with self.assertRaisesRegex(MapError, "width = 4"):
            parse_metadata({"width": 4}, self.grid)

    def test_metadata_dict_order_and_centres(self):
        meta = metadata_dict(self.grid, (0, 0), (2, 2), {"note": 1})
        self.assertEqual(list(meta), ["width", "height", "start", "goal", "note"])
        self.assertEqual(meta["start"], [0.5, 0.5])


class NameAndSizeTests(unittest.TestCase):
    def test_sanitize(self):
        self.assertEqual(sanitize_name("My Map (v2)"), "my_map_v2")
        self.assertEqual(sanitize_name("   "), "map")

    def test_builtin_sizes_enforced(self):
        check_size("easy", 20, 20)
        with self.assertRaisesRegex(MapError, "must be 20×20"):
            check_size("easy", 40, 40)

    def test_custom_size_limits(self):
        check_size("lab", 3, 200)
        with self.assertRaises(MapError):
            check_size("lab", 2, 10)


class RoutePreviewTests(unittest.TestCase):
    def test_empty_grid_diagonal_moves(self):
        self.assertEqual(moves([[0] * 5 for _ in range(5)], (0, 0), (4, 4)), 4)

    def test_rectangular_grid(self):
        self.assertEqual(moves([[0] * 7 for _ in range(3)], (0, 0), (6, 2)), 6)

    def test_centre_wall_forces_edge_route(self):
        # The diagonal past the centre wall would cut its corner, so the route must hug the edge.
        self.assertEqual(moves([[0, 0, 0], [0, 1, 0], [0, 0, 0]], (0, 0), (2, 2)), 4)

    def test_corner_cutting_rejected(self):
        self.assertIsNone(route_preview([[0, 1], [1, 0]], (0, 0), (1, 1)))

    def test_narrow_gap(self):
        grid = [[0, 1, 0],
                [0, 1, 0],
                [0, 0, 0]]
        # Both diagonals beside the wall's end would cut its corner, so the route walks round it.
        self.assertEqual(route_preview(grid, (0, 0), (2, 0)),
                         [(0, 0), (0, 1), (0, 2), (1, 2), (2, 2), (2, 1), (2, 0)])

    def test_blocked(self):
        self.assertIsNone(route_preview([[0, 1, 0], [0, 1, 0], [0, 1, 0]], (0, 0), (2, 2)))

    def test_missing_or_walled_endpoints(self):
        self.assertIsNone(route_preview([[0, 0]], None, (1, 0)))
        self.assertIsNone(route_preview([[0, 1]], (0, 0), (1, 0)))


class GeneratorTests(unittest.TestCase):
    def test_reproducible_connected_and_endpoints_free(self):
        for style in ("scatter", "segments", "rooms"):
            a, seed_a = generate(30, 20, style, 0.2, 42, (1, 1), (28, 18))
            b, seed_b = generate(30, 20, style, 0.2, 42, (1, 1), (28, 18))
            self.assertEqual((a, seed_a), (b, seed_b), style)
            self.assertEqual((len(a), len(a[0])), (20, 30))
            self.assertEqual(a[1][1] + a[18][28], 0)
            self.assertIsNotNone(route_preview(a, (1, 1), (28, 18)), style)

    def test_scatter_density_exact(self):
        grid, _ = generate(20, 20, "scatter", 0.15, 7, (0, 0), (19, 19))
        self.assertEqual(sum(map(sum, grid)), 60)

    def test_rooms_never_exceeds_target(self):
        grid, _ = generate(40, 40, "rooms", 0.10, 3, (1, 1), (38, 38))
        self.assertLessEqual(sum(map(sum, grid)), 160)

    def test_large_dense_maps_are_always_connected(self):
        for style in ("scatter", "segments", "rooms"):
            grid, _ = generate(200, 200, style, 0.40, 1, (1, 1), (198, 198))
            self.assertIsNotNone(route_preview(grid, (1, 1), (198, 198)), style)

    def test_carve_opens_fewest_walls(self):
        from maps_studio.core import _carve
        grid = [[0, 1, 0],
                [0, 1, 0],
                [0, 1, 0]]
        _carve(grid, (0, 1), (2, 1))
        self.assertEqual(sum(map(sum, grid)), 2)              # exactly one wall opened
        self.assertIsNotNone(route_preview(grid, (0, 1), (2, 1)))

    def test_bad_inputs(self):
        with self.assertRaises(MapError):
            generate(10, 10, "scatter", 0.9, 1, (0, 0), (9, 9))
        with self.assertRaises(MapError):
            generate(10, 10, "spiral", 0.2, 1, (0, 0), (9, 9))
        with self.assertRaises(MapError):
            generate(10, 10, "scatter", 0.2, 1, None, (9, 9))


class EditSessionTests(unittest.TestCase):
    def session(self, base=None):
        data = blank("lab", 4, 4)
        data.grid[0][3] = 1
        data.start, data.goal = (0, 0), (3, 3)
        return EditSession(data, base)

    def test_wall_erase_and_markers(self):
        s = self.session()
        self.assertTrue(s.apply((1, 1), "wall"))
        self.assertFalse(s.apply((0, 0), "wall"))              # never on Start
        self.assertFalse(s.apply((1, 1), "start"))             # never on a wall
        self.assertTrue(s.apply((2, 0), "start"))
        self.assertEqual(s.data.start, (2, 0))
        self.assertTrue(s.apply((3, 3), "erase"))              # erasing Goal removes it
        self.assertIsNone(s.data.goal)
        self.assertTrue(s.toggle_marker((2, 0), "start"))
        self.assertIsNone(s.data.start)

    def test_strokes_undo_redo(self):
        s = self.session()
        s.begin()
        for cell in [(1, 1), (1, 2)]:
            s.apply(cell, "wall")
        self.assertTrue(s.end())
        self.assertTrue(s.undo())
        self.assertEqual(s.data.grid[1][1] + s.data.grid[2][1], 0)
        self.assertTrue(s.redo())
        self.assertEqual(s.data.grid[1][1] + s.data.grid[2][1], 2)
        s.begin()
        self.assertFalse(s.end())                               # empty stroke is not an undo step

    def test_add_only_session(self):
        s = self.session(base=[[0, 0, 0, 1]] + [[0] * 4 for _ in range(3)])
        self.assertFalse(s.apply((3, 0), "erase"))             # base wall is protected
        self.assertFalse(s.apply((1, 0), "start"))             # endpoints locked
        self.assertFalse(s.apply((0, 0), "erase"))
        self.assertTrue(s.apply((2, 2), "wall"))
        self.assertEqual(s.added_walls(), [(2, 2)])
        self.assertTrue(s.apply((2, 2), "erase"))              # added walls can be removed
        s.apply((1, 1), "wall")
        s.clear()                                              # clear keeps the base and the markers
        self.assertEqual(s.data.grid[0][3], 1)
        self.assertEqual(s.added_walls(), [])
        self.assertEqual((s.data.start, s.data.goal), ((0, 0), (3, 3)))
        with self.assertRaises(MapError):
            s.replace_grid([[0] * 4 for _ in range(4)])

    def test_line_cells_no_gaps(self):
        self.assertEqual(line_cells((0, 0), (3, 0)), [(1, 0), (2, 0), (3, 0)])
        self.assertEqual(len(line_cells((0, 0), (5, 2))), 5)


class MapDataTests(unittest.TestCase):
    def test_validate(self):
        data = MapData("easy", [[0] * 20 for _ in range(20)], (0, 0), (19, 19))
        data.validate()
        data.grid[0][0] = 1
        with self.assertRaises(MapError):
            data.validate()


if __name__ == "__main__":
    unittest.main()
