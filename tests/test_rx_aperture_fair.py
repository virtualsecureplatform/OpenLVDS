# SPDX-License-Identifier: GPL-3.0-only
import json,sys,tempfile,unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import continue_rx_aperture_fair as fair
SPEC=dict(process='ss',temperature=40,edge='rising',polarity='rise',clock_slew_ps=20,data_slew_ps=20,kind='setup')

class FairAperture(unittest.TestCase):
    def test_complete_boundary_reuses_only_remeasured_scientific_witnesses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/fair.campaign.capture.condition_id(SPEC);folder.mkdir()
            record=dict(passed=True,spec=SPEC,failed_ps=10,passed_ps=12.5,bound_ps=40,guard_ps=20,resolution_ps=2.5)
            (folder/'summary.json').write_text(json.dumps(record))
            with patch.object(fair,'verify_witness') as verify:
                self.assertEqual(fair.completed(root,{},SPEC),record);self.assertEqual(verify.call_count,3)
                self.assertEqual([c.args[-1] for c in verify.call_args_list],[False,True,True])
                record['guard_ps']=0;(folder/'summary.json').write_text(json.dumps(record))
                with self.assertRaisesRegex(ValueError,'boundary changed'):fair.completed(root,{},SPEC)

    def test_partial_points_are_not_restarted_and_cached_points_need_no_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);point=root/fair.campaign.capture.condition_id(SPEC)/'point_0p000000';point.mkdir(parents=True)
            (point/'bench.raw').write_bytes(b'partial');original=Mock(return_value=True)
            with patch.object(fair.spice_dispatch,'lease') as lease:
                with self.assertRaisesRegex(ValueError,'Partial aperture point'):fair.point_with_lease(root,{},SPEC,0,original,lambda:None)
                lease.assert_not_called();original.assert_not_called()
                (point/'summary.json').write_text('{}');self.assertTrue(fair.point_with_lease(root,{},SPEC,0,original,lambda:None));lease.assert_not_called()
            self.assertEqual((point/'bench.raw').read_bytes(),b'partial')

    def test_only_the_original_uncached_point_executes_inside_one_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=[]
            @contextmanager
            def lease(*args,**kwargs):
                state.append('acquired');yield 0;state.append('released')
            def original(*args):self.assertEqual(state,['acquired']);return True
            with patch.object(fair.spice_dispatch,'lease',side_effect=lease) as acquire:
                self.assertTrue(fair.point_with_lease(Path(tmp),{},SPEC,0,original,lambda:None));self.assertEqual(acquire.call_count,1)
            self.assertEqual(state,['acquired','released'])

if __name__=='__main__':unittest.main()
