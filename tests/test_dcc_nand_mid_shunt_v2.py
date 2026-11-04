# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcc_nand_mid_shunt_v2 as circuit
import measure_dcc_native_events_v2 as analysis
import test_dcc_native_rc_v2 as fixture


class StaticGateShuntTests(unittest.TestCase):
    def library(self):
        result=''
        for model,ports,nodes in [('nand2_1','A B VGND VNB VPB VPWR Y','Y A internal VGND'),
                                  ('nand2_8','A B VGND VNB VPB VPWR Y','Y B internal VGND'),
                                  ('inv_1','A VGND VNB VPB VPWR Y','Y A VGND VGND')]:
            result+=f'.subckt sky130_fd_sc_hd__{model} {ports}\nX0 {nodes} sky130_fd_pr__nfet_01v8 w=.64 l=.15\n.ends\n'
        return result

    def test_real_mim_on_each_private_node_preserves_every_native_transistor(self):
        library=self.library();original=circuit.unshunted.source(1,library);text,nodes=circuit.source(1,library)
        self.assertEqual(len(nodes),27);self.assertEqual(len(circuit.devices(text)),31)
        retained='\n'.join(line for line in text.splitlines() if not line.startswith('XSTACKCAP'))+'\n'
        self.assertEqual(retained.replace(circuit.NAME,circuit.unshunted.NAME),original)
        for i,node in enumerate(nodes):self.assertIn(f'XSTACKCAP{i} {node} VGND {circuit.CAP} w=2 l=2',text)
        self.assertTrue(all('__' in n for n in nodes))

    def test_parser_excludes_only_declared_passive_models_and_rejects_bad_devices(self):
        text,_=circuit.source(1,self.library())
        with self.assertRaisesRegex(ValueError,'Unknown native'):circuit.devices(text+'Xbad a b imaginary w=2 l=2\n')
        with self.assertRaisesRegex(ValueError,'MIM port'):circuit.devices(text+f'Xbad a b c {circuit.CAP} w=2 l=2\n')
        with self.assertRaisesRegex(ValueError,'MOS port'):circuit.devices(text+'Xbad a b c sky130_fd_pr__nfet_01v8 w=2 l=2\n')

    def test_reusable_event_analyzer_checks_polarity_and_all_internal_terminals(self):
        f=fixture.NativeDccPilotTests();device=dict(name='Xtest__X0',model='sky130_fd_pr__nfet_01v8',nodes=['clock_out','phase0','VGND','VGND'])
        for options,passed in [({},True),({'complement':True},False),({'missing':True},False)]:
            with patch.object(analysis,'read_raw',return_value=f.wave(**options)):
                result=analysis.measure(Path('/fixture'),f.spec,[device],'Test scope')
            self.assertEqual(result['pilot_passed'],passed);self.assertFalse(result['qualified_phy'])
        names,w=f.wave();internal=np.zeros(len(w));internal[100]=2.1
        device=dict(device,nodes=['internal','phase0','VGND','VGND'])
        with patch.object(analysis,'read_raw',return_value=([*names,'v(xd.internal)'],np.column_stack([w,internal]))):
            result=analysis.measure(Path('/fixture'),f.spec,[device],'Test scope')
        self.assertTrue(result['event_integrity_passed']);self.assertFalse(result['terminal_screen_passed'])
        self.assertEqual(result['terminal_peak_location']['device'],'Xtest__X0')
        self.assertAlmostEqual(result['terminal_abs_peak_v'],2.1)


if __name__=='__main__':unittest.main()
