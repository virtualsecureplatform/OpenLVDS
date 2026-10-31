# SPDX-License-Identifier: GPL-3.0-only
import copy
import fcntl
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import rx_candidate_aperture as candidate


class CandidateApertureCoverage(unittest.TestCase):
    def requirements(self):return json.loads((candidate.ROOT/'requirements.json').read_text())

    def test_complete_matrix_preserves_original_load_windows_and_margin(self):
        req=self.requirements();conditions=candidate.capture.conditions(req)
        manifest=dict(identity=dict(model=dict(netlist_sha256='native'),code={},candidate_code={},simulator_provenance='pinned'))
        results=[dict(spec=s,passed=True,bound_ps=120 if s['kind']=='setup' else 80) for s in conditions]
        table=candidate.table(manifest,results,req,'manifest')
        self.assertTrue(table['passed']);self.assertEqual(table['conditions'],480)
        self.assertEqual((table['clock_mhz'],table['load_ff'],table['guard_ps'],table['resolution_ps']),(410,20,20,5))
        self.assertEqual(table['additional_link_margin_ps'],200)
        self.assertEqual(table['bounds']['ss_0'],dict(setup_ps=120,hold_ps=80))
        self.assertFalse(table['qualified_phy'])
        for changed in [results[:-1],results[:-1]+[results[0]]]:
            with self.assertRaisesRegex(ValueError,'480 distinct'):candidate.table(manifest,changed,req,'manifest')
        failed=copy.deepcopy(results);failed[0]['passed']=False
        self.assertFalse(candidate.table(manifest,failed,req,'manifest')['passed'])

    def test_full_stage_rejects_missing_or_partial_seed_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'manifest.json').write_text('{}')
            for passed,cases in [(False,{}),(True,{})]:
                (root/'seed_summary.json').write_text(json.dumps(dict(passed=passed,cases=cases,manifest_sha256=candidate.sha(root/'manifest.json'))))
                with self.assertRaises(ValueError):candidate.check_seeds(root,{})

    def test_all_twelve_loaded_seeds_are_rechecked_against_waveforms(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'manifest.json').write_text('{}');cases={}
            for spec in candidate.seed_conditions():
                name=candidate.capture.condition_id(spec);folder=root/name/'point_800p000000';folder.mkdir(parents=True)
                (folder/'summary.json').write_text('{}');cases[name]=candidate.sha(folder/'summary.json')
            (root/'seed_summary.json').write_text(json.dumps(dict(passed=True,cases=cases,manifest_sha256=candidate.sha(root/'manifest.json'))))
            with patch.object(candidate,'verify_witness') as verify:
                candidate.check_seeds(root,{})
                self.assertEqual(verify.call_count,12)
                self.assertTrue(all(c.args[-2:]==(800.,True) for c in verify.call_args_list))
                path=next(root.glob('*/point_800p000000/summary.json'));path.write_text('changed')
                with self.assertRaisesRegex(ValueError,'seed evidence changed'):candidate.check_seeds(root,{})


class SelectedSlotBudget(unittest.TestCase):
    def test_selected_wait_owns_one_of_the_existing_six_real_leases(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch.object(candidate,'ROOT',root),patch.object(candidate,'reserved_slots',return_value=0):
                with candidate.lease(1):
                    with (root/'build/diagnostics/spice_slots/1').open('a') as other:
                        with self.assertRaises(BlockingIOError):fcntl.flock(other,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with (root/'build/diagnostics/spice_slots/1').open('a') as other:
                    fcntl.flock(other,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with patch.object(candidate,'reserved_slots',return_value=4):
                with self.assertRaisesRegex(ValueError,'reserved'):
                    with candidate.lease(1):pass


class ConditionalExpansion(unittest.TestCase):
    def test_all_stage_stops_after_any_seed_failure(self):
        with patch.object(candidate,'run',return_value=1) as run:
            self.assertEqual(candidate.dispatch(Path('/candidate'),3,'all',1),1)
            run.assert_called_once_with(Path('/candidate'),1,'endpoints',1)

    def test_full_workers_use_shared_pool_only_after_seed_success(self):
        with patch.object(candidate,'run',return_value=0) as run:
            self.assertEqual(candidate.dispatch(Path('/candidate'),3,'all',1),0)
            self.assertEqual([c.args for c in run.call_args_list],[(Path('/candidate'),1,'endpoints',1),(Path('/candidate'),3,'full')])


class FailureStopsDispatch(unittest.TestCase):
    def test_priority_preserves_every_required_case(self):
        req=json.loads((candidate.ROOT/'requirements.json').read_text());original=candidate.capture.conditions(req)
        ordered=candidate.ordered_conditions(original)
        self.assertEqual(len(ordered),480)
        self.assertEqual({candidate.capture.condition_id(s) for s in ordered},{candidate.capture.condition_id(s) for s in original})
        self.assertEqual((ordered[0]['process'],ordered[0]['temperature'],ordered[0]['clock_slew_ps']),('ss',40,200))
        seeds=candidate.seed_conditions();self.assertEqual(len(seeds),12)
        self.assertTrue(any(s['process']=='ss' and s['temperature']==40 and s['polarity']=='fall' and s['clock_slew_ps']==200 for s in seeds))

    def test_failed_seed_holds_remaining_requests_without_running_spice(self):
        from contextlib import nullcontext
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'manifest.json').write_text('{}')
            def point(root,manifest,spec,distance):
                folder=root/candidate.capture.condition_id(spec)/'point_800p000000';folder.mkdir(parents=True)
                (folder/'summary.json').write_text('{"passed":false}')
                return False
            with patch.object(candidate,'validate'),patch.object(candidate,'lease',return_value=nullcontext()),patch.object(candidate.capture,'point',side_effect=point) as run:
                self.assertEqual(candidate.run(root,1,'endpoints'),1)
                self.assertEqual(run.call_count,1)
            report=json.loads((root/'seed_summary.json').read_text());self.assertFalse(report['passed'])
            self.assertEqual(len(report['cases']),1);self.assertEqual(len(report['held_cases']),11)
            self.assertFalse((root/'table.json').exists())


    def test_failed_boundary_never_writes_a_complete_table_for_held_cases(self):
        from contextlib import nullcontext
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);specs=candidate.seed_conditions()[:2]
            (root/'manifest.json').write_text(json.dumps(dict(conditions=specs)))
            def search(root,manifest,spec):return dict(spec=spec,passed=False,error='Aperture boundary is not bracketed')
            with patch.object(candidate,'validate'),patch.object(candidate,'check_seeds'),patch.object(candidate,'lease',return_value=nullcontext()),patch.object(candidate.capture,'search',side_effect=search) as search,patch.object(candidate,'table') as table:
                self.assertEqual(candidate.run(root,1,'full'),1)
                self.assertEqual(search.call_count,1);table.assert_not_called()
            report=json.loads((root/'incomplete_summary.json').read_text())
            self.assertEqual(report['completed_conditions'],1);self.assertEqual(len(report['held_cases']),1)
            self.assertFalse(report['qualified_phy']);self.assertFalse((root/'table.json').exists())
            self.assertEqual(json.loads((root/'state.json').read_text())['status'],'held_by_native_failure')


class EndpointBatchLease(unittest.TestCase):
    def test_selected_single_slot_covers_the_entire_endpoint_batch(self):
        from contextlib import contextmanager
        active=[]
        @contextmanager
        def lease(index):
            active.append(index)
            try:yield
            finally:active.pop()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'manifest.json').write_text('{}')
            def point(root,manifest,spec,distance):
                self.assertEqual(active,[2])
                folder=root/candidate.capture.condition_id(spec)/'point_800p000000';folder.mkdir(parents=True)
                (folder/'summary.json').write_text('{"passed":true}')
                return True
            with patch.object(candidate,'validate'),patch.object(candidate,'lease',side_effect=lease) as slot,patch.object(candidate.capture,'point',side_effect=point) as run:
                self.assertEqual(candidate.run(root,1,'endpoints',2),0)
                self.assertEqual(slot.call_count,1);self.assertEqual(run.call_count,12)
            self.assertEqual(active,[])
