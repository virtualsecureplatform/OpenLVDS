# SPDX-License-Identifier: GPL-3.0-only
import sys,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import bounded_pin_replay as pins
import replay_selected_receiver_bounded as bounded

class BoundedPins(unittest.TestCase):
    def test_linear_curves_keep_endpoints_and_crossings_without_dense_breakpoints(self):
        t=np.linspace(0,1e-9,1001);v=np.column_stack([1+t*1e9,np.full(len(t),1.5),2-t*1e9,np.full(len(t),1.5)])
        indices,proof=pins.simplify(t,v)
        self.assertEqual([indices[0],indices[-1]],[0,1000]);self.assertLessEqual(len(indices),6);self.assertLess(max(proof['maximum_pin_error_v'].values()),1e-12)
        self.assertEqual(proof['differential_crossings']['data_rising']['count'],1)
        self.assertEqual(proof['differential_crossings']['clock_falling']['count'],1)

    def test_curved_pin_waveforms_are_bounded_at_every_original_knot(self):
        t=np.linspace(0,10e-9,20001);v=np.column_stack([1.2+.2*np.sin(t*1e9),1.2-.2*np.sin(t*1e9),1.2+.2*np.cos(t*1e9),1.2-.2*np.cos(t*1e9)])
        indices,proof=pins.simplify(t,v)
        self.assertLess(len(indices),len(t))
        for i in range(4):self.assertLessEqual(np.max(abs(np.interp(t,t[indices],v[indices,i])-v[:,i])),pins.TOLERANCE_V*(1+1e-8))
        self.assertTrue(all(c['maximum_error_ps']==0 for c in proof['differential_crossings'].values()))

    def test_nonfinite_duplicate_times_and_sub_femtosecond_vertices_are_refused(self):
        v=np.array([[1.,1.2,1.3,1.2],[1.3,1.2,1.3,1.2],[1.,1.2,1.3,1.2]])
        for t in [np.array([0.,0.,1e-9]),np.array([0.,float('nan'),1e-9]),np.array([0.,.5e-15,1e-9])]:
            with self.assertRaises(ValueError):pins.simplify(t,v)

    def test_only_physical_receiver_vectors_are_printed(self):
        with patch.object(bounded,'BASE_FIXTURE',return_value='.print tran V(TXDATA) V(RXDATA)\n.end\n'):
            text=bounded.fixture('parent',Path('/out'),1)
        self.assertNotIn('V(TXDATA)',text);self.assertIn('V(RXDATA)',text)

    def test_unused_observations_are_restored_afterward_and_profile_bindings_restore(self):
        names=bounded.replay.NAMES;head={'INDEX':0,'TIME':1,**{'V('+n+')':i+2 for i,n in enumerate(names)}}
        reference=np.zeros((2,20));reference[:,1]=[0,1e-9]
        for i in range(2,20):reference[:,i]=[i,i+2]
        child=np.zeros((3,11));child[:,1]=[0,.5e-9,1e-9];child[:,6]=[0,.2,1.8]
        childhead={'INDEX':0,'TIME':1,**{'V('+n+')':i+2 for i,n in enumerate(names[:9])}}
        def read(path):return (reference,head) if Path(path)==Path('/parent/bench.cir.prn') else (child,childhead)
        previous=(bounded.replay.recorded_sources,bounded.replay.fixture,bounded.replay.read_wave,bounded.replay.CODE)
        with patch.object(bounded,'BASE_READ',side_effect=read):
            with bounded.profile(Path('/parent')):
                actual,headers=bounded.replay.read_wave(Path('/child/bench.cir.prn'))
                np.testing.assert_array_equal(actual[:,:11],child)
                self.assertEqual(actual[1,headers['V(TXREADY)']],12.)
                self.assertIn(bounded.NAME,bounded.replay.CODE)
        self.assertEqual((bounded.replay.recorded_sources,bounded.replay.fixture,bounded.replay.read_wave,bounded.replay.CODE),previous)

if __name__=='__main__':unittest.main()
