# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from screen_dll import variant_source
from layout import circuits,flatten

class DLLCandidates(unittest.TestCase):
    source=(Path(__file__).resolve().parents[1]/'analog/openlvds.spice').read_text()
    def test_variants_preserve_bias_and_public_interface(self):
        original=circuits(self.source)
        for variant in ['mirror2','input2','both2','both4','restore4','restore2']:
            defs=circuits(variant_source(self.source,variant))
            self.assertEqual(defs['openlvds_dll_analog'][0],original['openlvds_dll_analog'][0])
            old={x[0]:x for x in original['lvds_ctrl_buffer'][1]}
            new={x[0]:x for x in defs['lvds_ctrl_buffer'][1]}
            for name in ['XPT','XCC']:
                self.assertEqual({k:float(v) for k,v in new[name][3].items()},
                                 {k:float(v) for k,v in old[name][3].items()})
            _,devices=flatten(defs,'openlvds_dll_analog')
            for d in devices:
                if 'fet_' in d['model']:self.assertLessEqual(float(d['params']['w']),8)
    def test_nmos_candidate_uses_existing_nc_bias_without_new_macro_ports(self):
        text=variant_source(self.source,'nmos');defs=circuits(text)
        self.assertEqual(defs['lvds_ctrl_buffer'][0],['IN','OUT','NC','VDDD','VSS'])
        instance=next(x for x in defs['openlvds_dll_analog'][1] if x[0]=='XVCOPY')
        self.assertEqual(instance[1],['CTRL','VCOPY','NC','VDDD','VSS'])
        self.assertEqual(defs['openlvds_dll_analog'][0],circuits(self.source)['openlvds_dll_analog'][0])
        flatten(defs,'openlvds_dll_analog')

    def test_mirror_only_variant_preserves_input_capacitance_geometry(self):
        defs=circuits(variant_source(self.source,'mirror2'))
        d={x[0]:x[3] for x in defs['lvds_ctrl_buffer'][1]}
        self.assertEqual(float(d['XPP']['w']),64)
        self.assertEqual(float(d['XPP']['l']),1)
        self.assertEqual(float(d['XNL']['w']),64)
        self.assertEqual(float(d['XNL']['l']),2)

if __name__=='__main__':unittest.main()
