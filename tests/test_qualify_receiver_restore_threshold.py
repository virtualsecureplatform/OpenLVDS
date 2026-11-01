# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import qualify_receiver_restore_threshold as qualify


class RestoreReceiverComponents(unittest.TestCase):
    def replay(self,root):
        r=root/'build/diagnostics/receiver_replay/test';r.mkdir(parents=True)
        i=qualify.native.physical.profile('restore_lvt_n4')
        i['code']={'probe_receiver_restore_threshold.py':qualify.sha(Path(qualify.native.__file__))}
        (r/'manifest.json').write_text(json.dumps(dict(identity=i)))
        return r

    def test_missing_native_case_cannot_prepare_or_dispatch_components(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(qualify,'ROOT',Path(tmp)):
            r=self.replay(Path(tmp))
            with patch.object(qualify.native,'run') as native_run,patch.object(qualify.components,'prepare') as prepare:
                with self.assertRaisesRegex(ValueError,'Complete both'):
                    qualify.run('prepare',Path(tmp)/'layout',r)
                native_run.assert_not_called();prepare.assert_not_called()

    def test_failed_native_transport_cannot_admit_component_simulation(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(qualify,'ROOT',Path(tmp)):
            r=self.replay(Path(tmp))
            for name in ['captured','sharp_control']:
                (r/name).mkdir();(r/name/'summary.json').write_text('{}')
            (r/'summary.json').write_text(json.dumps(dict(diagnostic_complete=True,native_clock_passed=False,
                manifest_sha256=qualify.sha(r/'manifest.json'))))
            with patch.object(qualify.native,'run'),patch.object(qualify.components,'prepare') as prepare:
                with self.assertRaisesRegex(ValueError,'clock admission failed'):
                    qualify.run('prepare',Path(tmp)/'layout',r)
                prepare.assert_not_called()

    def test_selector_and_resource_functions_restore_on_failure(self):
        old=qualify.components.CODE,qualify.replay_gate.recheck_replay,qualify.spice_slots.slot
        with patch.object(qualify,'selected',return_value={}):
            with self.assertRaises(RuntimeError):
                with qualify.selection(Path('replay')):
                    self.assertIn(qualify.NAME,qualify.components.CODE)
                    self.assertIs(qualify.replay_gate.recheck_replay,qualify.recheck)
                    self.assertIsNot(qualify.spice_slots.slot,old[2])
                    raise RuntimeError('injected')
        self.assertEqual((qualify.components.CODE,qualify.replay_gate.recheck_replay,qualify.spice_slots.slot),old)

    def test_partial_component_waveform_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(qualify,'ROOT',Path(tmp)):
            root=Path(tmp);a=root/'build/diagnostics/receiver_components/partial';a.mkdir(parents=True)
            (a/'manifest.json').write_text(json.dumps(dict(identity=dict(code={qualify.NAME:qualify.sha(Path(qualify.__file__))},replay='replay'),tasks=[dict(id='native_receiver_ss_40')])))
            folder=a/'native_receiver_ss_40';folder.mkdir();raw=folder/'bench.raw';raw.write_bytes(b'original partial')
            with patch.object(qualify.components,'run') as run:
                with self.assertRaisesRegex(ValueError,'Partial restorer-modified component output retained'):
                    qualify.run('run',a)
                run.assert_not_called()
            self.assertEqual(raw.read_bytes(),b'original partial')


if __name__=='__main__':
    unittest.main()
