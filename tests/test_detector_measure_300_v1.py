# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import detector_measure_300_v1 as p
from replay_bank_300_v2 import same


class DetectorMeasurementTests(unittest.TestCase):
    def fixture(self):
        s=dict(p.waveform.specifications()[0],reference_slew_ps=20,feedback_slew_ps=250,offset_ps=0,positive_offset=1)
        t=np.arange(62001,dtype=float);values={'time':t*1e-12}
        def fixed(n,v):values['v('+n+')']=np.full(len(t),v,dtype=float)
        for phase in ('R','F'):values['v('+phase.lower()+')']=p.waveform.evaluate(t,s,phase)
        for n,phase,delay in (('rfast','R',200),('ffast','F',200),('rth','R',300),('fth','F',310)):
            values['v('+n+')']=p.waveform.evaluate(t-delay,s,phase)
        for n,v in (('qa',0),('qb',1.8),('pos',1.8),('sw',0),('vdd',1.8),('vddio',3.3),('xf.vcm',.9)):fixed(n,v)
        tags=np.zeros(len(t))
        for k in range(4):tags[(t>=21000+k*10000)&(t<=27000+k*10000)]=1.8
        for n in ('xd.ha','xd.hb'):values['v('+n+')']=tags.copy()
        task=dict(spec=s,devices=[dict(name='XF:XTEST',model='sky130_fd_pr__nfet_01v8',terminals=['RFAST','VDD','0','0'])])
        return list(values),np.column_stack(list(values.values())),task

    def write(self,path,names,w):
        header='Title: synthetic detector fixture\nPlotname: Transient Analysis\nFlags: real\n'
        header+=f'No. Variables: {len(names)}\nNo. Points: {len(w)}\nVariables:\n'
        header+=''.join(f'\t{k}\t{n}\t'+('time' if n=='time' else 'voltage')+'\n' for k,n in enumerate(names))+'Binary:\n'
        path.write_bytes(header.encode()+np.asarray(w,dtype='<f8').tobytes())

    def check(self,names,w,task,passed):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);self.write(path/'bench.raw',names,w)
            a=p.measure(path,task);b=p.measure(path,task,True)
            self.assertTrue(same(a,b));self.assertEqual(a['source_point_passed'],passed)
            self.assertFalse(a['qualified_phy']);self.assertFalse(a['full_native_stress_qualified'])
            return a

    def test_complete_native_binary_both_readers_and_four_decisions(self):
        names,w,task=self.fixture();r=self.check(names,w,task,True)
        self.assertEqual(r['votes'],[1]*4);self.assertEqual(r['input']['F']['measured_10_90_ps'],250)

    def test_internal_tag_failure_and_dc_custom_stress_cannot_hide(self):
        names,w,task=self.fixture();bad=w.copy();bad[26000,names.index('v(xd.ha)')]=0
        self.assertFalse(self.check(names,bad,task,False)['tags_retained_and_cleared_passed'])
        bad=w.copy();bad[0,names.index('v(rfast)')]=2.1
        self.assertFalse(self.check(names,bad,task,False)['native_stress_passed'])
        bad=w.copy();bad[:,names.index('v(qa)')]=1.8;bad[:,names.index('v(qb)')]=0
        self.assertFalse(self.check(names,bad,task,False)['all_four_decisions_passed'])

    def test_wrong_true_slew_missing_startup_tail_and_nonfinite_rejected(self):
        names,w,task=self.fixture()
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            bad=w.copy();wrong=dict(task['spec'],feedback_slew_ps=20)
            bad[:,names.index('v(f)')]=p.waveform.evaluate(w[:,0]*1e12,wrong,'F')
            for b in (bad,w[:-1],np.where(np.arange(w.shape[0])[:,None]==0,np.nan,w)):
                self.write(folder/'bench.raw',names,b)
                for independent in (False,True):
                    with self.assertRaises(ValueError):p.measure(folder,task,independent)
            bad=w.copy();bad[:23000,names.index('v(r)')]=0;self.write(folder/'bench.raw',names,bad)
            with self.assertRaisesRegex(ValueError,'input (event|epoch)'):p.measure(folder,task)
