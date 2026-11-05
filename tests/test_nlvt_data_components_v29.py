# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import build_nlvt_data_components_v29 as physical


class LowVtPhysicalSignatureTests(unittest.TestCase):
    def native(self, profile, original=False):
        spec = physical.SPECS[profile]
        output = 'Y' if spec['mim'] else 'X'
        lines = [f'.subckt fixture A {output} VPWR VGND']
        nmodel = physical.REGULAR_N if original else physical.tg.N
        pmodel = physical.HVT_P if original and profile == 'bufpair' else physical.tg.P
        for model, count, body in [(nmodel, spec['n'], 'VGND'), (pmodel, spec['p'], 'VPWR')]:
            for index in range(count):
                lines.append(f'X{body}{index} {output} A {body} {body} {model} w=.65 l=.15 ad=.2 as=.3 pd=1 ps=2')
        if spec['mim']:
            lines.append(f'XC {output} VGND sky130_fd_pr__cap_mim_m3_1 w=3 l=3')
        return '\n'.join(lines+['.ends fixture', ''])

    def test_only_permitted_flavor_changes_normalize_to_same_native_geometry(self):
        for profile, spec in physical.SPECS.items():
            with self.subTest(profile=profile):
                self.assertEqual(physical.native_signature(self.native(profile, True), spec, True),
                                 physical.native_signature(self.native(profile), spec))
                with self.assertRaises(ValueError):
                    physical.native_signature(self.native(profile, True), spec)

    def test_wrong_body_junction_width_and_guard_are_rejected_or_differ(self):
        spec = physical.SPECS['inv3']; source = self.native('inv3')
        for before, after in [('A VGND VGND', 'A VGND VPWR'), ('w=3 l=3', 'w=4 l=3')]:
            with self.subTest(fault=before), self.assertRaises(ValueError):
                physical.native_signature(source.replace(before, after, 1), spec)
        signature = physical.native_signature(source, spec)
        for before, after in [('ad=.2', 'ad=.21'), ('w=.65', 'w=.66')]:
            with self.subTest(fault=before):
                self.assertNotEqual(signature, physical.native_signature(source.replace(before, after, 1), spec))

    def test_loss_of_native_device_is_rejected(self):
        for profile, spec in physical.SPECS.items():
            lines = self.native(profile).splitlines(); del lines[1]
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                physical.native_signature('\n'.join(lines), spec)


if __name__ == '__main__':
    unittest.main()
