# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from driver_restore_variant import source_variant
from driver_restore_experiment import fixture
from layout import circuits
from spice_scope import closure_hash

SOURCE = (Path(__file__).resolve().parents[1] / 'analog/openlvds.spice').read_text()


class DriverRestoration(unittest.TestCase):
    def test_only_private_converter_restoration_ratio_changes(self):
        after = source_variant(SOURCE)
        old, new = circuits(SOURCE), circuits(after)
        self.assertEqual(source_variant(SOURCE, False), SOURCE)
        for name, definition in old.items():
            if name != 'openlvds_driver_core':
                self.assertEqual(new[name], definition)
        self.assertEqual(old['openlvds_driver_core'][0], new['openlvds_driver_core'][0])
        for a, b in zip(old['openlvds_driver_core'][1], new['openlvds_driver_core'][1]):
            if a[0] == 'XLS':
                self.assertEqual(a[:2], b[:2])
                self.assertEqual(b[2], 'lvds_shift18_33_restore_64_24')
            else:
                self.assertEqual(a, b)
        helper = new['lvds_inv33_restore_64_24'][1]
        self.assertEqual([r[3] for r in helper], [dict(w='64', l='0.5'), dict(w='24', l='0.5')])
        self.assertEqual(sum(float(r[3]['w']) for r in helper), 88)
        old_shift = old['lvds_shift18_33'][1]
        new_shift = new['lvds_shift18_33_restore_64_24'][1]
        for a, b in zip(old_shift, new_shift):
            if a[0] in ['XB0', 'XB1']:
                self.assertEqual(a[:2], b[:2])
                self.assertEqual(b[2], 'lvds_inv33_restore_64_24')
            else:
                self.assertEqual(a, b)
        for top in ['openlvds_receiver_core', 'lvds_bias', 'openlvds_dll', 'openlvds_delay_line']:
            self.assertEqual(closure_hash(SOURCE, top), closure_hash(after, top))

    def test_repeated_or_unexpected_source_cannot_select_variant(self):
        for source in [source_variant(SOURCE), SOURCE.replace('w=48 l=0.5', 'w=49 l=0.5')]:
            with self.assertRaises(ValueError):
                source_variant(source)

    def test_fixture_retains_all_sources_and_transient_except_declared_observation_names(self):
        deck = '.include "/parent/library.spice"\nVDD VDD 0 3.3\n' + \
            '.nodeset V(XCT:openlvds_driver_core__SINK)=1.36\n' + \
            '.nodeset V(XDT:openlvds_driver_core__TOP)=2.42\n' + \
            '.nodeset V(XRX:other_native_node)=0\n.tran 20p 188.049n 0 100p\n.print tran V(CLK0)\n.end\n'
        modified, probes = fixture(deck, Path('/parent'), Path('/new'))
        self.assertEqual(len(probes), 4)
        restored = modified.replace(' ' + ' '.join('V(' + n + ')' for n in probes.values()), '')
        restored = restored.replace('/new/library.spice', '/parent/library.spice')
        restored = restored.replace('V(XCT:SINK)', 'V(XCT:openlvds_driver_core__SINK)')
        restored = restored.replace('V(XDT:TOP)', 'V(XDT:openlvds_driver_core__TOP)')
        self.assertEqual(restored, deck)


if __name__ == '__main__':
    unittest.main()
