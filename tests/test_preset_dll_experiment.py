# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from dll_design import candidate_source
from dll_campaign import text_block
from layout import circuits
from preset_dll_experiment import preset_source
from repair_dll_monitor import repaired_source
from screen_fast_reset_dll import candidate_source as fast_reset

ROOT = Path(__file__).resolve().parents[1]


class PassivePreset(unittest.TestCase):
    def source(self):
        original = candidate_source((ROOT/'analog/openlvds.spice').read_text(), 'ota_w8_c4',
                                    (ROOT/'analog/experiments/phase_area.spice').read_text())
        return fast_reset(repaired_source(original))

    def test_only_preset_rows_change_and_no_ports_are_added(self):
        before = self.source(); after = preset_source(before)
        b = circuits(before); a = circuits(after)
        self.assertEqual(set(a), set(b))
        for name in b:
            if name != 'openlvds_dll_analog':
                self.assertEqual(text_block(after, name), text_block(before, name))
        self.assertEqual(a['openlvds_dll_analog'][0], b['openlvds_dll_analog'][0])
        old = {r[0]: r for r in b['openlvds_dll_analog'][1]}
        new = {r[0]: r for r in a['openlvds_dll_analog'][1]}
        self.assertEqual(set(new)-set(old), {'XRPDIV'})
        self.assertEqual(set(old)-set(new), set())
        for label in old:
            if label != 'XRP1': self.assertEqual(old[label], new[label])
        self.assertEqual(new['XRP0'][1], ['VDDD', 'PRE', 'VSS'])
        self.assertEqual(new['XRP1'][1], ['PRE', 'PREDIV', 'VSS'])
        self.assertEqual(new['XRPDIV'][1], ['PREDIV', 'VSS', 'VSS'])
        for label in ['XRP0', 'XRP1', 'XRPDIV']:
            self.assertEqual(new[label][2], 'sky130_fd_pr__res_high_po_0p35')
            self.assertEqual({k: float(v) for k,v in new[label][3].items()}, {'w': .35, 'l': 1.25})

    def test_unknown_topology_or_dimensions_rejected(self):
        source = self.source()
        for altered in [source.replace('XRP1 VDDD PRE', 'XRP1 VDDD OTHER'),
                        source.replace('XRP1 VDDD PRE VSS sky130_fd_pr__res_high_po_0p35 w=.35 l=1.25',
                                       'XRP1 VDDD PRE VSS sky130_fd_pr__res_high_po_0p35 w=.35 l=2.5')]:
            with self.assertRaisesRegex(ValueError, 'Unexpected preset'): preset_source(altered)

    def test_second_application_rejected(self):
        with self.assertRaises(ValueError): preset_source(preset_source(self.source()))


if __name__ == '__main__': unittest.main()
