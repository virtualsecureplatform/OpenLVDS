# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from diagnose_native_dll_loop import raw_prefix,analyze,interval


class NativeLoopDiagnosis(unittest.TestCase):
    def test_raw_prefix_keeps_complete_rows_without_claiming_finalization(self):
        header=b'Flags: real\nNo. Variables: 2\nNo. Points: 0\nVariables:\n0 time time\n1 v(ctrl) voltage\nBinary:\n'
        data=np.array([[0,1.8],[1e-9,1.7],[2e-9,1.6]],dtype='<f8')
        names,wave,description=raw_prefix(header+data.tobytes()+b'abc')
        self.assertEqual(names,['time','v(ctrl)']);np.testing.assert_equal(wave,data)
        self.assertFalse(description['raw_finalized']);self.assertEqual(description['trailing_bytes_ignored'],3)
        _,_,final=raw_prefix(header.replace(b'Points: 0',b'Points: 3')+data.tobytes())
        self.assertTrue(final['raw_finalized'])

    def test_nonfinite_or_nonmonotonic_partial_rows_are_rejected(self):
        header=b'Flags: real\nNo. Variables: 2\nNo. Points: 0\nVariables:\n0 time time\n1 v(ctrl) voltage\nBinary:\n'
        for data in [np.array([[0,1],[1e-9,np.nan]],dtype='<f8'),np.array([[0,1],[0,1]],dtype='<f8')]:
            with self.assertRaisesRegex(ValueError,'Invalid native trace'):raw_prefix(header+data.tobytes())

    def test_interval_mean_weights_actual_time(self):
        result=interval(np.array([0.,.01,1.]),np.array([0.,0.,1.]),0.,1.)
        self.assertAlmostEqual(result['mean_v'],.495)

    def synthetic(self,slow=True):
        t=np.arange(0,302e-9,1e-12);period=2.5e-9
        ctrl=1.34+(0.04*np.cos(2*np.pi*t/400e-9) if slow else .015*np.sin(2*np.pi*t/period))
        clk=1.8*(np.sin(2*np.pi*(t-.2e-9)/period)>0)
        pd=1.8*(np.sin(2*np.pi*(t-.2e-9-period/2)/period)>0)
        delay=20e-12-1e-9*(ctrl-1.34)
        fb=1.8*(np.sin(2*np.pi*(t-.2e-9-period/2-delay)/period)>0)
        names=['time','v(ctrl)','v(up)','v(dn)','v(ph0)','v(pd_ref)','v(ph180)']
        wave=np.column_stack([t,ctrl,np.full(len(t),.35),np.full(len(t),.35),clk,pd,fb])
        task=dict(spec=dict(start_ns=20,end_ns=290),aliases={n:n for n in ['CTRL','UP','DN','PH0','PD_REF','PH180']})
        return names,wave,task

    def test_slow_control_movement_is_separated_from_clock_ripple(self):
        result=analyze(*self.synthetic())
        self.assertTrue(result['observed_control_limit_exceeded'])
        self.assertGreater(result['cycle_mean_range_mv'],40)
        self.assertLess(result['cycle_ripple_max_mv'],2)
        self.assertTrue(result['delay_gain_fit']['usable'])
        self.assertAlmostEqual(result['delay_gain_fit']['inferred_delay_gain_s_per_v']/-1e-9,1,delta=.03)
        self.assertFalse(result['qualified_phy']);self.assertIsNone(result['qualification_verdict'])

    def test_fast_ripple_is_not_mislabeled_as_slow_settling(self):
        result=analyze(*self.synthetic(False))
        self.assertTrue(result['observed_control_limit_exceeded'])
        self.assertGreater(result['cycle_ripple_max_mv'],29)
        self.assertLess(result['cycle_mean_range_mv'],.05)
        self.assertFalse(result['delay_gain_fit']['usable'])
