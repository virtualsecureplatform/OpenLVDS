# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_decision_load_experiment as experiment
import receiver_decision_load_static as static
from layout import circuits

ROOT=Path(__file__).resolve().parents[1]


class ReceiverDecisionLoad(unittest.TestCase):
    def test_only_two_pmos_widths_change_from_the_matched_unclamped_control(self):
        original=(ROOT/'analog/openlvds.spice').read_text()
        control=experiment.source_variant(original,False);candidate=experiment.source_variant(original,True)
        a=circuits(control);b=circuits(candidate)
        for name in a:
            if name!=experiment.TOP:self.assertEqual(a[name],b[name])
        x={r[0]:r for r in a[experiment.TOP][1]};y={r[0]:r for r in b[experiment.TOP][1]}
        self.assertEqual(a[experiment.TOP][0],b[experiment.TOP][0]);self.assertEqual(set(x),set(y))
        for name,row in x.items():
            if name in ['XCD','XCM']:
                self.assertEqual(y[name],(row[0],row[1],row[2],dict(row[3],w='32')))
            else:self.assertEqual(y[name],row)
        self.assertEqual(y['XCT'][3]['w'],'64')
        self.assertEqual(y['XC0'][3]['w'],'8');self.assertEqual(y['XC1'][3]['w'],'8')
        self.assertFalse(any(n.startswith('XCLAMP') for n in y))
        with self.assertRaises(ValueError):experiment.strengthen_loads(candidate)
        with self.assertRaises(ValueError):experiment.strengthen_loads(control.replace('w=64 l=0.5','w=16 l=0.5'))

    def test_static_deck_changes_only_binding_and_declared_unloaded_probes(self):
        with tempfile.TemporaryDirectory() as temp:
            parent=Path(temp);source=experiment.source_variant((ROOT/'analog/openlvds.spice').read_text(),False)
            (parent/'source.spice').write_text(source)
            deck=f'Title\n.include "{parent}/source.spice"\nXR P N Q VREF IREF VDDIO VDDD 0 openlvds_receiver\nCQ Q 0 100f\n.tran 10p 144n 0 50p\n.print tran V(P) V(N) V(Q) V(XR:XCORE:PP) V(XR:XCORE:PN) V(XR:XCORE:CO)\n.end\n'
            result=static.observed(deck,parent,Path('/new'))
            restored=result.replace('/new/source.spice',str(parent/'source.spice'))
            for node in ['CL','CT','NBC']:restored=restored.replace(' V(XR:XCORE:'+node+')','')
            self.assertEqual(restored,deck)
            with self.assertRaisesRegex(ValueError,'observation command'):static.observed(deck.replace('.end\n','.print tran V(P)\n.end\n'),parent,Path('/new'))

    def wave(self):
        wave=np.zeros((1441,11));wave[:,1]=np.linspace(0,144e-9,1441)
        wave[:,4]=(np.floor(wave[:,1]/12e-9).astype(int)%2)*1.8
        headers={'INDEX':0,'TIME':1,'V(P)':2,'V(N)':3,'V(Q)':4,'V(XR:XCORE:PP)':5,
                 'V(XR:XCORE:PN)':6,'V(XR:XCORE:CO)':7,'V(XR:XCORE:CL)':8,'V(XR:XCORE:CT)':9,'V(XR:XCORE:NBC)':10}
        return wave,headers

    def test_every_original_static_sample_is_required(self):
        wave,headers=self.wave();result=static.measured(wave,headers,True)
        self.assertTrue(result['metrics']['passed']);self.assertEqual(len(result['samples']),12)
        i=np.argmin(abs(wave[:,1]-130e-9));wave[i-1:i+2,4]=1.8
        self.assertFalse(static.measured(wave,headers,True)['metrics']['passed'])

    def test_short_nonfinite_nonmonotonic_or_missing_observations_hold(self):
        wave,headers=self.wave()
        for invalid in [wave[:801],wave[::-1],np.where(wave==0,np.nan,wave)]:
            with self.assertRaisesRegex(ValueError,'Incomplete'):static.measured(invalid,headers,True)
        with self.assertRaisesRegex(ValueError,'observations'):
            static.measured(wave,{k:v for k,v in headers.items() if 'NBC' not in k},True)


if __name__=='__main__':unittest.main()
