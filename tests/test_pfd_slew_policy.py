from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import pfd_slew_policy as policy

ROOT = Path(__file__).resolve().parents[1]


class SlewPFDPolicy(unittest.TestCase):
    def setUp(self):
        self.base = (ROOT / 'sky130/experiments/lvds_pfd_area_fast_reset.v').read_text()

    def test_all_four_chains_preserve_the_core_and_public_interface(self):
        for variant in policy.VARIANTS:
            source = policy.source(self.base, variant)
            with self.subTest(variant=variant):
                self.assertTrue(policy.retained(source, variant))
                self.assertFalse(policy.pfd_fast_reset_paths_retained(source))
                for line in self.base.splitlines():
                    if '.CLK(' not in line and line.strip() != 'endmodule': self.assertIn(line, source)
                for name in policy.chains(variant):
                    self.assertRegex(source, r'\(\* keep="true", dont_touch="true" \*\)\s+sky130_fd_sc_hd__\w+\s+' + name)

    def test_bypass_cross_coupling_strength_changes_reset_and_extra_loads_fail(self):
        for variant in policy.VARIANTS:
            source = policy.source(self.base, variant)
            mutations = [source.replace('.CLK(ref_conditioned)', '.CLK(REF)'),
                         source.replace('.CLK(fb_conditioned)', '.CLK(ref_conditioned)'),
                         source.replace('.A2(raw_dn)', '.A2(DN)'),
                         source.replace('.D(logic1)', '.D(logic0)'),
                         source.replace('.A(raw_up),.X(UP)', '.A(raw_dn),.X(UP)'),
                         source.replace('endmodule', 'sky130_fd_sc_hd__buf_8 extra(.A(ref_conditioned),.X(unused));\nendmodule'),
                         source.replace('endmodule', 'assign FB = REF;\nendmodule'),
                         source.replace('endmodule', 'wire hidden = REF;\nendmodule'),
                         source.replace('endmodule', 'buf (fb_conditioned, REF);\nendmodule'),
                         source.replace('endmodule', 'other_cell extra(.A(REF));\nendmodule'),
                         source.replace('endmodule', 'sky130_fd_sc_hd__buf_8 extra(.A(UP),.X(unused));\nendmodule')]
            cell = variant if variant.startswith('clkbuf') else f'nor{variant[3]}_1'
            mutations.append(source.replace('sky130_fd_sc_hd__' + cell + ' ref_condition', 'sky130_fd_sc_hd__inv_4 ref_condition'))
            for i, mutation in enumerate(mutations):
                with self.subTest(variant=variant, mutation=i): self.assertFalse(policy.retained(mutation, variant))

    def test_every_nor_input_is_tied_to_the_same_external_clock(self):
        for variant in ('nor3_inv4', 'nor4_inv4'):
            source = policy.source(self.base, variant)
            for pin in 'ABCD'[:int(variant[3])]:
                with self.subTest(variant=variant, pin=pin):
                    self.assertFalse(policy.retained(source.replace('.' + pin + '(REF)', '.' + pin + '(FB)'), variant))
            self.assertFalse(policy.retained(source.replace('.A(ref_mid)', '.A(fb_mid)'), variant))

    def test_physical_fillers_split_ties_and_power_pins_are_supported(self):
        for variant in policy.VARIANTS:
            source = policy.source(self.base, variant)
            source = source.replace('.D(logic1)', '.D(separate_high)')
            source = source.replace('endmodule', 'sky130_fd_sc_hd__conb_1 extra_tie(.HI(separate_high));\n'
                                    'sky130_fd_sc_hd__fill_8 filler();\n'
                                    'sky130_fd_sc_hd__tapvpwrvgnd_1 tap();\nendmodule')
            source = re.sub(r'(sky130_fd_sc_hd__\w+\s+\w+)\(', r'\1(.VPWR(VPWR),.VGND(VGND),', source)
            self.assertTrue(policy.retained(source, variant))
            self.assertFalse(policy.retained(source.replace('.VPWR(VPWR)', '.VPWR(VGND)', 1), variant))
            self.assertFalse(policy.retained(source.replace('.CLK(ref_conditioned)', '.CLK(ref_conditioned),.CLK(FB)'), variant))

    def test_blackboxes_add_only_missing_frontend_types(self):
        existing = (ROOT / 'sky130/pfd_blackboxes.v').read_text()
        for variant in policy.VARIANTS:
            boxes = policy.blackboxes(variant)
            names = re.findall(r'\bmodule\s+(\w+)', boxes)
            self.assertEqual(len(names), 1)
            self.assertNotIn(names[0], existing)
            self.assertIn('output wire ' + ('X' if variant.startswith('clkbuf') else 'Y'), boxes)
        with self.assertRaises(ValueError): policy.source(self.base, 'buf_4')
        with self.assertRaises(ValueError): policy.blackboxes('x')
