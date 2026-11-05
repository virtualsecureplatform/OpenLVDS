# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import build_regular_clock_inverter_v11 as design


class RegularInverterIsolationTests(unittest.TestCase):
    def flat(self, hvt=False):
        model = design.HVT if hvt else design.REGULAR
        text = '.subckt flat A Y VGND VPWR\n'
        for i in range(8):
            text += f'XP{i} Y A VPWR VPWR {model} w=1 l=.15 ad=.135 as=.26 pd=1.27 ps=2.52\n'
            text += f'XN{i} Y A VGND VGND sky130_fd_pr__nfet_01v8 w=.65 l=.15 ad=.08775 as=.169 pd=.92 ps=1.82\n'
        return text+'XC Y VGND sky130_fd_pr__cap_mim_m3_1 w=4 l=4\n.ends\n'

    def test_signature_allows_only_pmos_flavor_and_source_drain_reordering(self):
        before = self.flat(True); after = self.flat()
        self.assertEqual(design.native_signature(before, True), design.native_signature(after))
        flipped = after.replace('XP0 Y A VPWR VPWR', 'XP0 VPWR A Y VPWR', 1)
        flipped = flipped.replace('ad=.135 as=.26 pd=1.27 ps=2.52', 'ad=.26 as=.135 pd=2.52 ps=1.27', 1)
        self.assertEqual(design.native_signature(after), design.native_signature(flipped))

    def test_changed_junction_gate_body_or_missing_finger_cannot_pass_signature(self):
        after = self.flat(); baseline = design.native_signature(after)
        for broken in (after.replace('ad=.135', 'ad=.134', 1),
                       after.replace('XP0 Y A VPWR VPWR', 'XP0 Y A VGND VPWR', 1),
                       after.replace('XP0 Y A VPWR VPWR', 'XP0 Y Y VPWR VPWR', 1),
                       after.replace('XP0 Y A VPWR VPWR', 'XP0 Y A VPWR VGND', 1)):
            self.assertNotEqual(baseline, design.native_signature(broken))
        with self.assertRaises(ValueError):
            design.native_signature('\n'.join(s for s in after.splitlines() if not s.startswith('XP0 ')))
        with self.assertRaises(ValueError):
            design.native_signature(after.replace(' ps=2.52', '', 1))

    def test_source_changes_models_and_names_without_changing_connections_or_capacitor(self):
        source = self.flat(True).replace('.subckt flat', '.subckt sky130_fd_sc_hd__inv_8')
        source += f'.subckt {design.OLD} A Y VPWR VGND\nXgate A Y VGND VPWR sky130_fd_sc_hd__inv_8\n.ends {design.OLD}\n'
        changed = design.schematic(source)
        expected = source.replace(design.HVT, design.REGULAR).replace('sky130_fd_sc_hd__inv_8', 'openlvds_inv_8_regular_core_v11').replace(design.OLD, design.NAME)
        self.assertEqual(changed, expected)
        for broken in (source.replace(design.HVT, design.REGULAR, 1), source.replace('w=4 l=4', 'w=3 l=4')):
            with self.assertRaises(ValueError):
                design.schematic(broken)


if __name__ == '__main__':
    unittest.main()
