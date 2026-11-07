# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_supply_current_centering_v362 as p


class SupplyCenteringTests(unittest.TestCase):
    def test_mna_voltage_constraint_is_invariant_while_source_current_translates(self):
        # Independent modified-nodal equations, not a SKY130 qualification.
        # Unknowns are supply voltage, loaded internal voltage, source current.
        for r1,r2,r3 in ((100.,300.,500.),(.001,1e6,20.),(1e6,1e9,1e9)):
            a=np.array([[1/r1+1/r2,-1/r1,1.],[-1/r1,1/r1+1/r3,0.],[1.,0.,0.]])
            old=np.linalg.solve(a,np.array([0.,0.,1.8]))
            new=np.linalg.solve(a,np.array([-p.OFFSET_A,0.,1.8]))
            np.testing.assert_allclose(new[:2],old[:2],rtol=0,atol=1e-10)
            self.assertAlmostEqual(new[2]+p.OFFSET_A,old[2],places=12)

    def test_only_bench_current_and_declared_diagnostic_stop_change(self):
        original=(p.PARENT/'1/bench.cir').read_text()
        for variant in p.VARIANTS:
            new=p.fixture(original,variant)
            self.assertEqual(new.count(p.CARD),1)
            body=new.split('\n',1)[1].replace(p.CARD+'\n','',1)
            if variant.startswith('quiet_'):body=body.replace('.tran 2p 200p 0 2p','.tran 2p 25n 0 2p',1)
            self.assertEqual(body,original.split('\n',1)[1])
            self.assertIn('VDD VDD 0 1.8',new)
            self.assertIn('.options timeint method=gear reltol=1e-4 abstol=1e-12',new)

    def test_feedback_nonideal_supply_or_duplicate_offset_is_rejected(self):
        original=(p.PARENT/'1/bench.cir').read_text()
        for bad in (original.replace('VDD VDD 0 1.8','VDD OTHER 0 1.8'),
                    original.replace('.end','Bfeedback N 0 V=I(VDD)\n.end',1),
                    original.replace('.end','Ffeedback N 0 VDD 1\n.end',1),original+p.CARD+'\n'):
            with self.assertRaises(ValueError):p.fixture(bad,'active_production')

    def test_active_run_requires_both_parities_and_an_observed_quiet_step_reduction(self):
        self.assertTrue(p.allowed('quiet_production',[]))
        self.assertFalse(p.allowed('quiet_observer',[dict(result=None)]))
        q=dict(result=dict(quiet_parity_passed=True,fewer_than_half_original_steps=True))
        self.assertTrue(p.allowed('quiet_observer',[q]))
        self.assertTrue(p.allowed('active_production',[q,dict(result=dict(quiet_parity_passed=True))]))
        self.assertFalse(p.allowed('active_production',[dict(result=dict(quiet_parity_passed=True)),dict(result=dict(quiet_parity_passed=True))]))
        self.assertFalse(p.allowed('active_production',[q,dict(result=None)]))

    def test_comparison_keeps_vector_identity_and_detects_voltage_error(self):
        names=['time','v(a)','v(b)'];old=np.array([[0.,0.,1.8],[1.,1.8,0.]])
        other=old[:,[0,2,1]].copy();other[1,2]+=.0005
        r=p.wave_difference(names,old,['time','v(b)','v(a)'],other)
        self.assertEqual(r['worst_vector'],'v(a)');self.assertAlmostEqual(r['maximum_all_vector_error_v'],.0005)
        with self.assertRaises(ValueError):p.wave_difference(names,old,['time','v(a)'],other[:,:2])


if __name__=='__main__':unittest.main()
