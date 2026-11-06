# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import json
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import analyze_regular_regenerated_stages_v300 as p

class RegularStageTests(unittest.TestCase):
    def fixture(self,history=False):
        t=np.arange(0,21000,.5)
        def train(delays):return sum(.9*(np.tanh((t-1000-2400*k-delays[k])/20)-np.tanh((t-2200-2400*k-delays[k])/20)) for k in range(8))
        shifts=[0,100,250,450,550];changes=[0,0,20,15,16]
        signals={n:train([delay+(changes[k] if history else 0)]+[delay]*7) for k,(n,delay) in enumerate(zip(p.NODES,shifts))}
        for n in p.INVERTED:signals[n]=1.8-signals[n]
        return t,signals,dict(rise=[566 if history else 550]+[550]*7,fall=[566 if history else 550]+[550]*7)

    def test_four_native_stages_use_both_inversions_and_reproduce_complete_totals(self):
        t,signals,reference=self.fixture();r=p.decompose(t,signals,reference)
        for edge in ('rise','fall'):
            for stage,expected in zip(p.STAGES,(100,150,200,100)):
                np.testing.assert_allclose(r[edge]['stage_delays_ps'][stage],[expected]*8,atol=1e-6)
            self.assertLess(r[edge]['maximum_sum_residual_ps'],1e-6)

    def test_signed_first_last_history_changes_telescope_without_averaging(self):
        t,signals,reference=self.fixture(True);r=p.decompose(t,signals,reference)
        for edge in ('rise','fall'):
            np.testing.assert_allclose(list(r[edge]['first_minus_last_stage_ps'].values()),[0,20,-5,1],atol=1e-6)
            self.assertAlmostEqual(r[edge]['first_minus_last_total_ps'],16,places=6)
            self.assertLess(r[edge]['history_sum_residual_ps'],1e-6)

    def test_missing_internal_edge_or_changed_recorded_history_is_rejected(self):
        t,s,r=self.fixture();s['restored_b']=np.full_like(t,1.8)
        with self.assertRaisesRegex(ValueError,'eight matched'):p.decompose(t,s,r)
        t,s,r=self.fixture();r['rise'][0]+=1
        with self.assertRaisesRegex(ValueError,'reproduce'):p.decompose(t,s,r)

    def test_nonfinite_nonmonotonic_missing_startup_or_wrong_initial_polarity_is_rejected(self):
        t,s,r=self.fixture()
        with self.assertRaises(ValueError):p.decompose(t[1:],{k:v[1:] for k,v in s.items()},r)
        with self.assertRaises(ValueError):p.decompose(t[::-1],{k:v[::-1] for k,v in s.items()},r)
        s['restored_b']=1.8-s['restored_b']
        with self.assertRaisesRegex(ValueError,'polarity'):p.decompose(t,s,r)
        t,s,r=self.fixture();s['fine_node'][5]=np.nan
        with self.assertRaises(ValueError):p.decompose(t,s,r)

    def test_completed_native_receipt_replays_all_eight_edges_and_bound_inputs(self):
        folder=p.ROOT/'build/diagnostics/regular_regenerated_stages_v300/7fdc7c6bbf871949'
        if not folder.exists():self.skipTest('Completed regular-pair native receipt required')
        manifest=json.loads((folder/'manifest.json').read_text())
        result=json.loads((folder/'summary.json').read_text())
        self.assertFalse(result['shared_wire_rc_qualified'])
        self.assertFalse(result['electrical_qualification_passed'])
        self.assertFalse(result['qualified_phy'])
        for name,digest in manifest['identity']['inputs'].items():
            self.assertEqual(p.sha(p.ROOT/name),digest,name)
        self.assertEqual(len(result['rows']),1)
        row=result['rows'][0]
        self.assertEqual(row['native_mos'],1529)
        self.assertEqual(row['programming_gates'],173)
        self.assertTrue(row['all_original_native_metrics_reproduced'])
        self.assertTrue(row['recorded_gates']['current_clock_interface_screen_passed'])
        case=p.ROOT/row['case']
        columns,w=p.validate(case/'bench.raw',{'v(in)','v(xd.selected)','v(xd.fine_node)','v(xd.restored_b)','v(out)'},25e-9)
        names=('v(in)','v(xd.selected)','v(xd.fine_node)','v(xd.restored_b)','v(out)')
        signals={n:w[:,columns.index(column)] for n,column in zip(p.NODES,names)}
        reference=json.loads((case/'summary.json').read_text())['result']['edge_delays_ps']
        replay=p.decompose(w[:,columns.index('time')]*1e12,signals,reference)
        self.assertEqual(replay,row['decomposition'])
        self.assertAlmostEqual(replay['rise']['first_minus_last_total_ps'],16.054667747196163)
        self.assertAlmostEqual(replay['rise']['first_minus_last_stage_ps']['selected_to_fine_node'],15.058011546847865)

if __name__=='__main__':unittest.main()
