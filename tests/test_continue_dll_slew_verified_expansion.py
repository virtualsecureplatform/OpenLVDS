from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import continue_dll_slew_verified_expansion as followup


class RetainedScreenHandoff(unittest.TestCase):
    def active(self):
        return dict(MainPID='12',InvocationID='same',LoadState='loaded',RemainAfterExit='yes',ActiveState='active',SubState='running')

    def test_retained_success_and_original_live_owner_are_recognized(self):
        live=self.active();saved=deepcopy(live)
        self.assertFalse(followup.terminal(saved,live))
        done=dict(live,MainPID='0',SubState='exited',Result='success',ExecMainStatus='0')
        self.assertTrue(followup.terminal(saved,done))

    def test_collected_transient_restarted_failed_or_nonretained_owners_never_dispatch(self):
        live=self.active();done=dict(live,MainPID='0',SubState='exited',Result='success',ExecMainStatus='0')
        for now in [dict(done,LoadState='not-found'),dict(done,RemainAfterExit='no'),dict(done,InvocationID='new'),
                    dict(live,MainPID='13'),dict(done,ActiveState='inactive'),dict(done,SubState='dead'),
                    dict(done,Result='exit-code'),dict(done,ExecMainStatus='1')]:
            with self.subTest(now=now),self.assertRaises(ValueError):followup.terminal(live,now)

    def test_preparation_rejects_the_original_nonretained_service_policy(self):
        parent=followup.ROOT/'build/diagnostics/dll_slew_screen/example'
        live=dict(self.active(),RemainAfterExit='no',ExecStart='screen_dll_slew_frontends.py example')
        with patch.object(followup,'owner',return_value=live),self.assertRaisesRegex(ValueError,'RemainAfterExit=yes'):
            followup.prepare(parent,'unit')

    def test_existing_handoff_never_restarts(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);(out/'manifest.json').write_text('{"identity":{}}');(out/'state.json').write_text('{}')
            with patch.object(followup.subprocess,'run') as run,self.assertRaisesRegex(ValueError,'no retry'):followup.run(out)
            run.assert_not_called()
