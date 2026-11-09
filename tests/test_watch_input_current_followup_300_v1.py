# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import watch_input_current_followup_300_v1 as p


class FollowupTests(unittest.TestCase):
    def test_only_passing_replay_reaches_combined_producer(self):
        for passed in (False,True):
            with self.subTest(passed=passed),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);proof=root/'proof';proof.mkdir();out=root/'combined';out.mkdir()
                (proof/'summary.json').write_text(json.dumps(dict(numerical_origin_passed_for_reference_case=passed)))
                (out/'summary.json').write_text(json.dumps(dict(combined_loading_pilot_passed=False)))
                events=[]
                with patch.object(p,'ROOT',root),patch.object(p.replay,'run',return_value=proof) as replay,patch.object(p.combined,'prepare',return_value=out) as prepare,patch.object(p.combined,'run') as run:
                    p.followup(root/'trial',lambda status,**kw:events.append((status,kw)))
                replay.assert_called_once_with(root/'trial')
                if passed:
                    prepare.assert_called_once_with(proof);run.assert_called_once_with(out)
                    self.assertEqual([x[0] for x in events],['reference_replayed','combined_prepared','complete'])
                    self.assertFalse(events[-1][1]['combined_loading_pilot_passed'])
                else:
                    prepare.assert_not_called();run.assert_not_called()
                    self.assertEqual(events[-1][0],'reference_rejected')

    def test_replay_failure_never_prepares_or_runs_combined_case(self):
        with patch.object(p.replay,'run',side_effect=ValueError('native witness failed')),patch.object(p.combined,'prepare') as prepare,patch.object(p.combined,'run') as run:
            with self.assertRaisesRegex(ValueError,'native witness failed'):p.followup(Path('trial'),lambda *a,**kw:None)
        prepare.assert_not_called();run.assert_not_called()
