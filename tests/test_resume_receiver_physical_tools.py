# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import resume_receiver_physical_tools as recovery


class PhysicalToolsRecovery(unittest.TestCase):
    def test_only_tools_python_is_replaced_and_scientific_arguments_are_unchanged(self):
        args=[str(recovery.ROOT/'scripts/env.sh'),'--tools','--ngspice','python3','scripts/layout_receiver_soft_common_mode.py','reference','--variant','rail_pullup_2r']
        actual=recovery.invocation(args)
        self.assertEqual(actual[:3],args[:3]);self.assertEqual(actual[3],'/usr/bin/python3')
        self.assertEqual(actual[4:],args[4:]);self.assertEqual(args[3],'python3')
        base=[str(recovery.ROOT/'scripts/env.sh'),'--ngspice','python3','script.py']
        self.assertIs(recovery.invocation(base),base)

    def test_subprocess_binding_is_restored_after_failure(self):
        old=recovery.controller.subprocess.run
        with self.assertRaises(RuntimeError):
            with recovery.python_profile():
                self.assertIsNot(recovery.controller.subprocess.run,old)
                raise RuntimeError('injected')
        self.assertIs(recovery.controller.subprocess.run,old)

    def test_unrelated_failure_cannot_trigger_recovery_or_mutate_old_state(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(recovery,'ROOT',Path(tmp)):
            prior=Path(tmp)/'build/diagnostics/receiver_physical_followup/failed';prior.mkdir(parents=True)
            (prior/'manifest.json').write_text('{}');state=prior/'state.json'
            state.write_text(json.dumps(dict(status='held_for_diagnosis',error='electrical failure')))
            before=state.read_bytes()
            with self.assertRaisesRegex(ValueError,'specific pre-geometry'):
                recovery.prepare(prior)
            self.assertEqual(state.read_bytes(),before)


if __name__=='__main__':
    unittest.main()
