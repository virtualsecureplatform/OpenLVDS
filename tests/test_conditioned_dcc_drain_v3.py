# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import drain_superseded_clocking_v3 as drain


class SupersededJointDrainTests(unittest.TestCase):
    def test_new_allowlist_cannot_signal_the_replacement_or_an_unverified_pid(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);base=root/'build/diagnostics';base.mkdir(parents=True)
            evidence=base/'evidence.json';evidence.write_text('{}')
            artifact=base/'conditioned_dcc_v2'/'old'
            with patch.object(drain,'ROOT',root),patch.object(drain,'proc',return_value=None),patch.object(drain.os,'kill') as kill:
                with self.assertRaisesRegex(ValueError,'explicitly allowed'):
                    drain.begin(123,artifact,'probe_conditioned_dcc_v3.py','A concrete superseded circuit reason',[evidence])
                with self.assertRaisesRegex(ValueError,'identity mismatch'):
                    drain.begin(123,artifact,'probe_conditioned_dcc_v2.py','A concrete superseded circuit reason',[evidence])
                kill.assert_not_called()


if __name__=='__main__':unittest.main()
