# SPDX-License-Identifier: GPL-3.0-only
"""Protect isolation of native components and interpretation of quiet traces."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import diagnose_bank_static_cells_v353 as p


class StaticCellDiagnosisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text=(p.PARENT/'bank.spice').read_text()

    def test_all_truth_states_and_actual_component_inventory(self):
        specs=p.specifications()
        self.assertEqual([(s['a'],s['b']) for s in specs[:4]],[(0,0),(0,1),(1,0),(1,1)])
        self.assertEqual(len(specs),12)
        for spec in specs:
            _,_,devices,_=p.observations(self.text,spec)
            self.assertEqual(len(devices),{p.AND:12,p.bank.GROUP:32,p.bank.SMALL:18,
                                          p.bank.FINE:72,p.bank.COARSE:64}[spec['model']])
            self.assertTrue(all(d['limit_v']==1.95 for d in devices))

    def test_fixtures_keep_solver_and_native_circuit_with_explicit_static_scope(self):
        for spec in p.specifications():
            text=p.fixture(p.ROOT/'build/test-static-only/0',self.text,spec,'.lib "same-pdk" ss')
            self.assertIn('.options timeint method=gear reltol=1e-4 abstol=1e-12',text)
            self.assertIn('VDD VDD 0 1.8',text)
            self.assertIn('.options device temp=40',text)
            self.assertIn('.tran 2p 200p 0 2p',text)
            self.assertNotIn('UIC',text.upper())
            self.assertNotIn('.ic ',text)
            self.assertEqual(sum(line.startswith('XD ') for line in text.splitlines()),1)
            self.assertNotIn('BIN ',text)
            self.assertEqual('VB B ' in text,spec['model']==p.AND)

    def test_altered_cell_interface_and_unknown_state_are_rejected(self):
        changed=self.text.replace('.subckt '+p.AND+' A B VGND VNB VPB VPWR X',
                                  '.subckt '+p.AND+' B A VGND VNB VPB VPWR X',1)
        with self.assertRaises(ValueError):p.observations(changed,p.specifications()[0])
        with self.assertRaises(ValueError):p.observations(self.text,dict(model=p.AND,a=2,b=0))

    def test_tiny_step_and_internal_voltage_diagnosis_does_not_admit_bank(self):
        spec=p.specifications()[2]
        _,_,_,nodes=p.observations(self.text,spec)
        names=['time',*('v('+n.replace(':','.').lower()+')' for n in nodes)]
        wave=np.zeros((4,len(names)));wave[:,0]=[0.,1e-15,100e-12,200e-12]
        wave[:,names.index('v(vdd)')]=1.8
        wave[:,names.index('v(a)')]=1.8
        wave[:,names.index('v(xd.a_110_47#)')]=1.3366
        with tempfile.TemporaryDirectory() as directory,patch.object(p,'validate',return_value=(names,wave)):
            result=p.measure(Path(directory),self.text,spec)
        self.assertEqual(result['below_0_01ps_steps'],1)
        self.assertAlmostEqual(result['steps_ps']['minimum'],.001)
        self.assertEqual(result['records'],4)
        self.assertEqual(result['native_mos'],12)
        self.assertTrue(result['diagnostic_complete'])
        self.assertFalse(result['bank_timing_qualified'])
        self.assertFalse(result['qualified_phy'])
        node=next(n for n in result['node_ranges'] if n['node']=='v(xd.a_110_47#)')
        self.assertAlmostEqual(node['final_v'],1.3366)


if __name__=='__main__':unittest.main()
