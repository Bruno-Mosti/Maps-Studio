"""Regression coverage for share-ready UI/storage fixes introduced in 2.0.1."""
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from maps_studio.core import MapError, blank
from maps_studio.storage import SaveError, Workspace, decode_pair, encode_pair, ZIP_MAX_MEMBERS


class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ws = Workspace(self.root / 'profile')
        self.ws.ensure()
        self.ws.create(blank('test', 4, 4))

    def test_bad_nonfinite_coordinates_show_map_error(self):
        grid, meta = encode_pair(blank('demo', 4, 4))
        for token in ('NaN', 'Infinity', '-Infinity'):
            with self.subTest(token=token):
                bad_meta = f'{{"width":4,"height":4,"start":[{token},1.5],"goal":[3.5,3.5]}}'.encode()
                with self.assertRaisesRegex(MapError, 'finite'):
                    decode_pair('demo', grid, bad_meta)

    def test_boolean_grid_cells_rejected(self):
        d = blank('demo', 4, 4)
        d.grid[0][0] = True
        with self.assertRaisesRegex(MapError, 'Cells must be'):
            d.validate()

    def test_excess_zip_members_report_problem(self):
        z = self.root / 'too-many.zip'
        with zipfile.ZipFile(z, 'w') as archive:
            for i in range(ZIP_MAX_MEMBERS + 1):
                archive.writestr(f'file{i}.csv', b'0,0,0\n0,0,0\n0,0,0\n')
        items = self.ws.read_sources([z])
        self.assertEqual(len(items), 1)
        self.assertIn('more than', items[0].error)

    def test_corrupted_zip_member_does_not_crash_import(self):
        z = self.root / 'corrupt.zip'
        original = b'0,0,0\n0,0,0\n0,0,0\n'
        with zipfile.ZipFile(z, 'w', compression=zipfile.ZIP_STORED) as archive:
            archive.writestr('one.csv', original)
        content = z.read_bytes()
        index = content.index(original)
        z.write_bytes(content[:index] + b'9' + content[index+1:])
        items = self.ws.read_sources([z])
        self.assertEqual(len(items), 1)
        self.assertIn('could not be read', items[0].error)

    def test_partial_first_export_is_removed_on_failure(self):
        destination = self.root / 'out'
        destination.mkdir()
        real = os.replace
        calls = []
        def flaky(a, b):
            calls.append(b)
            if len(calls) == 2:
                raise OSError('simulated disk failure')
            return real(a, b)
        with mock.patch('maps_studio.storage.os.replace', side_effect=flaky):
            with self.assertRaisesRegex(SaveError, 'simulated disk failure'):
                self.ws.export_pair('test', destination)
        self.assertFalse((destination / 'test.csv').exists())
        self.assertFalse((destination / 'test.json').exists())

    def test_zip_export_will_not_replace_without_consent(self):
        output = self.root / 'maps.zip'
        output.write_bytes(b'old content')
        with self.assertRaises(FileExistsError):
            self.ws.export_zip(['test'], output)
        self.assertEqual(output.read_bytes(), b'old content')
        self.ws.export_zip(['test'], output, overwrite=True)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(set(archive.namelist()), {'maps/test.csv', 'maps/test.json'})

if __name__ == '__main__':
    unittest.main()
