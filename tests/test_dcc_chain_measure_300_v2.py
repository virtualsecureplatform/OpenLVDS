# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcc_chain_measure_300_v2 as p
import test_dcc_chain_measure_300_v1 as waves


class PulseHoldTests(unittest.TestCase):
    def fixture(self,*,repeat=False,release=False,unarmed=False):
        t=np.arange(0,40001,dtype=float);period=1e6/310;source=[2100+k*period for k in range(8)]
        helper=waves.DccEventTests()
        clock=helper.wave(t,[(v,up) for x in source for v,up in ((x,True),(x+period*.6,False))])
        pulse_edges=[(v,up) for x in source for v,up in ((x+100,True),(x+300,False))]
        if repeat:pulse_edges.extend([(source[0]+500,True),(source[0]+650,False)]);pulse_edges.sort()
        pulse=helper.wave(t,pulse_edges)
        reset=helper.wave(t,[(v,up) for x in source for v,up in ((x+200,False),(x+period*.6+100,True))],1.8)
        if release:reset[(t>source[0]+500)&(t<source[0]+1000)]=1.8
        if unarmed:reset[(t>=source[0]-40)&(t<=source[0]-20)]=0
        return t,clock,pulse,reset,dict(cycles=8)

    def test_all_eight_events_include_first_hold_and_rearm(self):
        r=p.pulse_generator(*self.fixture())
        self.assertTrue(r['pulse_generator_integrity_passed']);self.assertEqual(len(r['events']),8)
        self.assertTrue(all(e['held_interval_samples']>0 for e in r['events']))

    def test_first_event_retrigger_early_release_and_unarmed_rejected(self):
        for change in (dict(repeat=True),dict(release=True),dict(unarmed=True)):
            with self.subTest(change=change):
                r=p.pulse_generator(*self.fixture(**change));self.assertFalse(r['pulse_generator_integrity_passed'])
                if 'release' in change:self.assertFalse(r['events'][0]['reset_held_until_fall'])
                if 'unarmed' in change:self.assertFalse(r['events'][0]['rearmed_before_edge'])


class CombinedPulseBinaryTests(unittest.TestCase):
    def test_internal_hold_failure_overrides_correct_output_transport(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);obs,s=waves.CombinedBinaryTests().fixture(folder)
            names,w=p.validate(folder/'bench.raw',set(),40e-9)
            values={n:np.array(w[:,k]) for k,n in enumerate(names)};t=values['time']*1e12
            helper=waves.DccEventTests()
            for k in ('0','1'):
                for channel,node in zip(('a','b'),obs['dcc'][k]['input_nodes']):
                    v=values['v('+node.lower()+')'];rise=p.crossings(t,v,.9,True);fall=p.crossings(t,v,.9,False)
                    values[f'v(xdc{k}.{channel})']=helper.wave(t,[(time,up) for x in rise for time,up in ((x+100,True),(x+300,False))])
                    reset=helper.wave(t,sorted([(x+200,False) for x in rise]+[(x+100,True) for x in fall]),1.8)
                    values[f'v(xdc{k}.{channel}reset)']=reset
            del w
            def write():
                names=list(values);data=np.column_stack(list(values.values()))
                header=('Title: synthetic combined internal pulse reader test\nFlags: real\n'
                    f'No. Variables: {len(names)}\nNo. Points: {len(t)}\nVariables:\n'
                    +''.join(f'\t{k}\t{n}\t'+('time' if k==0 else 'voltage')+'\n' for k,n in enumerate(names))+'Binary:\n')
                (folder/'bench.raw').write_bytes(header.encode()+data.astype('<f8').tobytes())
            write();r=p.measure(folder,obs,s)
            self.assertTrue(r['combined_loading_transport_passed'])
            self.assertTrue(all(len(g['events'])==8 for d in r['dcc'].values() for g in d['pulse_generators'].values()))
            values['v(xdc0.areset)'][(t>2600)&(t<3000)]=1.8;write()
            # The output waveform is unchanged; the internal reset fault must
            # nevertheless reject the combined transport screen.
            self.assertTrue(p.previous.measure(folder,obs,s)['combined_loading_transport_passed'])
            r=p.measure(folder,obs,s)
            self.assertFalse(r['combined_loading_transport_passed'])
            self.assertFalse(r['dcc']['0']['pulse_generator_integrity_passed'])
