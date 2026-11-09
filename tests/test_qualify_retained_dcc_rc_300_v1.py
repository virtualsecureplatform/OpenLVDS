# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import qualify_retained_dcc_rc_300_v1 as p


class RetainedDCCModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        info=__import__('json').loads((p.PARENT/'extraction.json').read_text())
        cls.text=p.collapse((p.ROOT/info['netlist']).read_text())
        cls.expected=p.leaves((p.PARENT/'rc_audit/reference.spice').read_text(),p.NAME)
        cls.actual=p.leaves(cls.text,p.NAME)

    def test_actual_mos_parameters_and_four_two_terminal_resistors(self):
        result=p.parameters(self.expected,self.actual)
        self.assertEqual(result['native_mos'],192);self.assertEqual(result['native_resistors'],4)
        self.assertTrue(result['mos']['all_native_model_dimensions_preserved'])
        self.assertEqual(len([d for d in self.actual if len(d['nodes'])==2]),4)

    def test_wrong_mos_width_and_native_resistor_length_rejected(self):
        bad=deepcopy(self.actual);next(d for d in bad if 'fet_' in d['model'])['params']['w']='0.123'
        with self.assertRaises(ValueError):p.parameters(self.expected,bad)
        bad=deepcopy(self.actual);next(d for d in bad if 'res_' in d['model'])['params']['l']='0.501'
        with self.assertRaisesRegex(ValueError,'resistor dimensions'):p.parameters(self.expected,bad)

    def test_unknown_primitive_or_added_substrate_terminal_refused(self):
        with self.assertRaisesRegex(ValueError,'Unknown native'):
            p.leaves(self.text.replace('sky130_fd_pr__res_generic_po','unknown_resistor'),p.NAME)
        with self.assertRaisesRegex(ValueError,'terminal count'):
            p.leaves(self.text.replace('sky130_fd_pr__res_generic_po','VGND sky130_fd_pr__res_generic_po',1),p.NAME)
