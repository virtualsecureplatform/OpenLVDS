# SPDX-License-Identifier: GPL-3.0-only
import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import tempfile
from threading import Lock
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import qualify_scaled_receiver as qualifier


class ScaledReceiverSelection(unittest.TestCase):
    def test_partial_integration_trace_is_retained_for_diagnosis(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);qualifier.preserve_partial(root)
            raw=root/'bench.raw';raw.write_bytes(b'original partial trace')
            with self.assertRaisesRegex(ValueError,'Incomplete integration execution retained'):qualifier.preserve_partial(root)
            self.assertEqual(raw.read_bytes(),b'original partial trace')
            (root/'summary.json').write_text('{}');qualifier.preserve_partial(root)

    def fixture(self,root,complete=False):
        replay=root/'build/diagnostics/receiver_replay/scaled';replay.mkdir(parents=True)
        (replay/'manifest.json').write_text(json.dumps(dict(identity=copy.deepcopy(qualifier.native.PROFILE))))
        if complete:
            for name in ['captured','sharp_control']:
                folder=replay/name;folder.mkdir();(folder/'summary.json').write_text('{}')
            report=dict(diagnostic_complete=True,native_clock_passed=True,manifest_sha256=qualifier.native.digest(replay/'manifest.json'))
            (replay/'summary.json').write_text(json.dumps(report))
        return replay

    def test_profile_rejects_original_tail_and_pmos_only_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);replay=self.fixture(root)
            with patch.object(qualifier,'ROOT',root):
                qualifier.selected_replay(replay)
                manifest=json.loads((replay/'manifest.json').read_text());manifest['identity']['decision_input_width_um']=8
                (replay/'manifest.json').write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError,'exact uniformly scaled'):qualifier.selected_replay(replay)

    def test_selection_restores_every_factory_verifier_and_code_binding_on_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);replay=self.fixture(root)
            original=(qualifier.components.CODE,qualifier.link.CODE,qualifier.link.source_variant,qualifier.link.recheck_replay)
            with patch.object(qualifier,'ROOT',root),self.assertRaisesRegex(ValueError,'held'):
                with qualifier.selection(replay):
                    self.assertIs(qualifier.link.source_variant,qualifier.source_variant)
                    self.assertIs(qualifier.link.recheck_replay,qualifier.recheck)
                    self.assertIn(qualifier.NAME,qualifier.components.CODE)
                    raise ValueError('held')
            restored=(qualifier.components.CODE,qualifier.link.CODE,qualifier.link.source_variant,qualifier.link.recheck_replay)
            for before,after in zip(original,restored):self.assertIs(before,after)

    def test_missing_native_case_cannot_call_a_producer_or_launch_simulations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);replay=self.fixture(root)
            with patch.object(qualifier,'ROOT',root),patch.object(qualifier.native,'run') as run:
                with self.assertRaisesRegex(ValueError,'Complete both'):qualifier.recheck(replay)
                run.assert_not_called()

    def test_false_native_admission_cannot_be_promoted_by_a_successful_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);replay=self.fixture(root,True);report=json.loads((replay/'summary.json').read_text())
            report['native_clock_passed']=False;(replay/'summary.json').write_text(json.dumps(report))
            with patch.object(qualifier,'ROOT',root),patch.object(qualifier.native,'run') as run:
                with self.assertRaisesRegex(ValueError,'admission failed'):qualifier.recheck(replay)
                run.assert_called_once_with(replay)

    def test_component_and_link_cached_rechecks_serialize_the_real_file_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);replay=self.fixture(root,True);mutex=Lock();state=dict(active=0,maximum=0,calls=0)
            def run(path):
                with mutex:
                    state['active']+=1;state['maximum']=max(state['maximum'],state['active']);state['calls']+=1
                time.sleep(.03)
                with mutex:state['active']-=1
            with patch.object(qualifier,'ROOT',root),patch.object(qualifier.native,'run',side_effect=run):
                with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(qualifier.recheck,[replay,replay]))
            self.assertEqual(state,dict(active=0,maximum=1,calls=2))


if __name__=='__main__':unittest.main()
