# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import dll_storage_compensation as comp


class DllStorageCompensation(unittest.TestCase):
    def source(self):
        return ('.subckt unrelated A B VSS\n'
                'XRES A B VSS sky130_fd_pr__res_high_po_0p35 w=.35 l=1.25\n.ends unrelated\n'
                '.subckt openlvds_dll_analog CLK CTRL VSS\n'
                '* Preserve original active and passive network bytes.\n'
                'XKEEP CTRL CLK VSS VSS sky130_fd_pr__nfet_01v8 w=2 l=1\n'+
                ''.join(f'XCC{i}_{suffix} CTRL VSS {comp.MODEL} w={size} l={size}\n'
                        for i in range(2) for suffix, size in [('0', 30), ('1', 10)])+
                '.ends openlvds_dll_analog\n')

    def test_only_twelve_added_storage_capacitors_change_source_bytes(self):
        source = self.source(); result = comp.transform(source)
        added = [line for line in result.splitlines(keepends=True)
                 if line.startswith(tuple(f'XCC{i}_' for i in range(2, 8)))]
        self.assertEqual(len(added), 12)
        for line in added:
            result = result.replace(line, '')
        self.assertEqual(result, source)
        devices = comp.circuits(comp.transform(source))[comp.TOP][1]
        caps = [d for d in devices if d[2] == comp.MODEL]
        self.assertEqual(len(caps), 16)
        self.assertEqual(sum(float(d[3]['w'])*float(d[3]['l']) for d in caps), 8000)

    def test_unknown_storage_geometry_and_repeated_application_are_refused(self):
        source = self.source()
        for bad in [source.replace('w=30 l=30', 'w=29 l=29', 1),
                    source.replace('XCC1_1 CTRL VSS', 'XCC1_1 OTHER VSS'),
                    comp.transform(source)]:
            with self.assertRaisesRegex(ValueError, 'original four'):
                comp.transform(bad)


if __name__ == '__main__':
    unittest.main()
