# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcc_chain_measure_300_v1 as p


class DccEventTests(unittest.TestCase):
    def wave(self,t,edges,initial=0):
        v=np.full(len(t),initial,dtype=float)
        for time,up in edges:
            v+=(1 if up else -1)*1.8*np.clip((t-time+50)/100,0,1)
        return v

    def fixture(self,*,spacing=1500,drop_first=False):
        t=np.arange(0,40001,dtype=float);period=1e6/310
        a=[2100+k*period for k in range(8)];b=[x+spacing for x in a]
        clocks=[self.wave(t,[(x,up) for start in v for x,up in ((start,True),(start+period*.4,False))]) for v in (a,b)]
        output=[(x+100,k%2==1) for k,x in enumerate(sorted(a+b))]
        if drop_first:output=output[2:]
        q=self.wave(t,output,1.8)
        return t,clocks,q,dict(cycles=8,frequency_mhz=310)

    def test_event_integrity_does_not_imply_half_cycle_accuracy(self):
        t,clocks,q,s=self.fixture()
        r=p.events(t,*clocks,q,s)
        self.assertTrue(r['one_transition_per_source_event_passed'])
        self.assertTrue(r['period_screen_passed']);self.assertTrue(r['output_slew_passed'])
        self.assertFalse(r['observed_mean_half_cycle_passed'])
        self.assertEqual(len(r['event_pair_checks']),16)
        np.testing.assert_allclose(r['event_latency_ps'],100,atol=1e-6)

    def test_balanced_events_and_missing_startup(self):
        t,clocks,q,s=self.fixture(spacing=1e6/310/2)
        self.assertTrue(p.events(t,*clocks,q,s)['observed_mean_half_cycle_passed'])
        t,clocks,q,s=self.fixture(drop_first=True)
        self.assertFalse(p.events(t,*clocks,q,s)['one_transition_per_source_event_passed'])
        q[0]=0
        self.assertFalse(p.events(t,*clocks,q,s)['startup_reset_output_high'])


class CombinedBinaryTests(unittest.TestCase):
    def fixture(self,folder,*,stress=False,bad_reset=False):
        import test_four_bank_native_measure_300_v1 as bankfixtures
        obs,s=bankfixtures.FourSectionMeasureTests().fixture(folder)
        names,w=p.validate(folder/'bench.raw',set(),40e-9)
        values={n:np.array(w[:,k]) for k,n in enumerate(names)};t=values['time']*1e12
        values['v(dcc_reset_n)']=1.8*np.clip((t-1000)/20,0,1)
        if bad_reset:values['v(dcc_reset_n)'][0]=.01
        values['v(dccstress)']=np.zeros(len(t))
        if stress:values['v(dccstress)'][0]=2.1
        dcc={};helper=DccEventTests()
        for k,(a,b) in enumerate((('IN','B1_OUT'),('OUT','B2_OUT'))):
            events=sorted(x for node in (a,b) for x in p.crossings(t,values['v('+node.lower()+')'],.9,True))
            output=f'DCC{k}_OUT';values['v('+output.lower()+')']=helper.wave(t,[(x+100,i%2==1) for i,x in enumerate(events)],1.8)
            dcc[str(k)]=dict(input_nodes=[a,b],output_node=output,
                devices=[dict(name=f'XDC{k}:M',terminals=[output,'dccstress','0','0'],limit_v=1.95)],
                passive_resistors=[dict(name=f'XDC{k}:R',terminals=['VDD','0'])])
        del w
        names=list(values);data=np.column_stack(list(values.values()))
        header=('Title: synthetic combined binary reader test\nFlags: real\n'
                f'No. Variables: {len(names)}\nNo. Points: {len(t)}\nVariables:\n'
                +''.join(f'\t{k}\t{n}\t'+('time' if k==0 else 'voltage')+'\n' for k,n in enumerate(names))+'Binary:\n')
        (folder/'bench.raw').write_bytes(header.encode()+data.astype('<f8').tobytes())
        return dict(sections=obs,dcc=dcc),s

    def test_full_combined_trace_and_startup_electrical_failures(self):
        import tempfile
        for changes in ({},dict(stress=True),dict(bad_reset=True)):
            with self.subTest(changes=changes),tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp);obs,s=self.fixture(folder,**changes);r=p.measure(folder,obs,s)
                self.assertEqual(r['combined_loading_transport_passed'],not bool(changes))
                self.assertTrue(r['chain']['four_section_transport_passed'])
                self.assertFalse(r['calibrated_phase_qualified']);self.assertFalse(r['qualified_phy'])
                if 'stress' in changes:self.assertFalse(r['dcc']['1']['terminal_screen_passed'])
                if 'bad_reset' in changes:self.assertGreater(r['maximum_reset_source_error_v'],1e-9)
