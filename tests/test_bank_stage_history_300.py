# SPDX-License-Identifier: GPL-3.0-only
import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import bank_stage_history_300 as p
from regenerated_bank_periodic_measure_v67 import timing

class StageHistoryTests(unittest.TestCase):
    def fixture(self):
        t=np.arange(40001,dtype=float);period=1e6/310;points=[(0,0)]
        for k in range(8):
            a=2000+k*period;b=a+.6*period
            points += [(a,0),(a+200,1.8),(b,1.8),(b+200,0)]
        wave=np.interp(t,*zip(*points));v={}
        for n,delay in zip(p.NODES,(0,300,400,650,750)):
            values=np.interp(t-delay,t,wave)
            v[n]=1.8-values if n in ('XD:selected','XD:fine_node') else values
        s=dict(cycles=8,frequency_mhz=310,duty=.6,coarse=0,fine=31)
        return t,v,s,timing(t,v['IN'],v['OUT'],s)
    def test_fixed_polarity_causal_stage_sum(self):
        t,v,s,r=self.fixture();out=p.stages(t,v,s,r)
        for edge in out.values():
            self.assertLess(edge['maximum_stage_sum_residual_ps'],1e-6)
            self.assertTrue(np.allclose(edge['total_delays_ps'],750))
    def test_missing_or_noncausal_stage_is_rejected(self):
        t,v,s,r=self.fixture();v['XD:pre_out']=np.interp(t+500,t,v['IN'])
        with self.assertRaises(ValueError):p.stages(t,v,s,r)
        t,v,s,r=self.fixture();v['OUT'][t>24000]=0
        with self.assertRaises(ValueError):p.stages(t,v,s,r)
    def test_outer_metric_and_startup_cannot_be_substituted(self):
        t,v,s,r=self.fixture();r['edge_delays_ps']['rise'][0]+=1
        with self.assertRaises(ValueError):p.stages(t,v,s,r)
        t,v,s,r=self.fixture()
        with self.assertRaises(ValueError):p.stages(t[5000:],{k:a[5000:] for k,a in v.items()},s,r)
