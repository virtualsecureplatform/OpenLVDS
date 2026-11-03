# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from dll_campaign import text_block
from probe_driver_cmfb_lead import lead_block, transform


class CompensationLeadNetwork(unittest.TestCase):
    def block(self, reversed_plates=False):
        plates = 'VSS SINK' if reversed_plates else 'SINK VSS'
        caps = [f'XC{i} {plates} sky130_fd_pr__cap_mim_m3_1 w=29 l=29' for i in range(6)]
        return '\n'.join(['.subckt cmfb SINK VSS',
            'XM SINK G VSS VSS sky130_fd_pr__nfet_g5v0d10v5 w=8 l=1 ad=2.32',
            'XR SINK G VSS sky130_fd_pr__res_high_po_0p35 w=.35 l=60',
            'XOTHER SINK VSS sky130_fd_pr__cap_mim_m3_1 w=36 l=36',
            *caps, '.ends cmfb'])

    def test_one_direct_five_series_preserves_devices_and_cap_geometry(self):
        for reverse in [False, True]:
            with self.subTest(reverse=reverse):
                original = self.block(reverse)
                changed = lead_block(original)
                caps = [l.split() for l in changed.splitlines()
                    if l.split() and l.split()[0] in {f'XC{i}' for i in range(6)}]
                self.assertEqual(len(caps), 6)
                self.assertEqual(sum('SINK' in c[1:3] for c in caps), 1)
                self.assertEqual(sum('CMFB_LEAD_C' in c[1:3] for c in caps), 5)
                self.assertTrue(all('VSS' in c[1:3] and c[3:] ==
                    ['sky130_fd_pr__cap_mim_m3_1', 'w=29', 'l=29'] for c in caps))
                for line in original.splitlines():
                    if line.startswith(('XM ', 'XR ', 'XOTHER ')):
                        self.assertIn(line, changed.splitlines())
                self.assertIn('XCMFB_RZ0 SINK CMFB_LEAD_C VSS '
                    'sky130_fd_pr__res_high_po_0p35 w=0.35 l=1.25', changed.splitlines())

    def test_transform_preserves_other_subcircuits(self):
        other = '.subckt unrelated P N\nR0 P N 100\n.ends unrelated'
        model = self.block() + '\n' + other
        changed = transform(model, 'cmfb')
        self.assertEqual(text_block(changed, 'unrelated'), text_block(model, 'unrelated'))

    def test_rejects_ambiguous_or_previously_modified_network(self):
        original = self.block()
        invalid = [original.replace('XC5 ', '*XC5 '),
            original.replace('XC5 SINK VSS', 'XC5 OTHER VSS'),
            original.replace('XC5 SINK VSS', 'XC5 SINK OTHER'),
            original.replace('XC5 SINK VSS', 'XC5 VSS VSS'),
            original.replace('XC5 SINK VSS sky130_fd_pr__cap_mim_m3_1 w=29 l=29',
                'XC5 SINK VSS sky130_fd_pr__cap_mim_m3_1 w=29 l=29.01'),
            lead_block(original)]
        for block in invalid:
            with self.subTest(block=block):
                with self.assertRaises(ValueError):
                    lead_block(block)
