# SPDX-License-Identifier: GPL-3.0-only
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import layout_receiver_monitor_after as monitor
import receiver_layout_reference as reference
from layout import circuits,flatten

ROOT=Path(__file__).resolve().parents[1]


class ReceiverMonitorAfter(unittest.TestCase):
    def devices(self):
        source=reference.tail.source_variant((ROOT/'analog/openlvds.spice').read_text(),True)
        return flatten(circuits(source),reference.TOP)[1]

    def test_only_six_unloaded_monitor_fingers_move_after_all_functional_devices(self):
        devices=self.devices();original=copy.deepcopy(devices)
        actual=reference.reordered(devices,monitor.place)
        self.assertEqual(devices,original)
        self.assertEqual(len(actual),70)
        self.assertTrue(all('__XTRACK__' in d['name'] for d in actual[-6:]))
        self.assertTrue(all('__XTRACK__' not in d['name'] for d in actual[:-6]))
        admitted=reference.tail.place_monitor(devices)
        self.assertEqual(actual[:-6],[d for d in admitted if '__XTRACK__' not in d['name']])
        self.assertEqual(actual[-6:],[d for d in admitted if '__XTRACK__' in d['name']])
        self.assertEqual(monitor.place(actual),actual)
        self.assertEqual(reference.device_signature(actual),reference.device_signature(original))

    def test_connectivity_parameter_or_device_changes_are_refused_even_if_in_place(self):
        for kind in ['node','width','missing']:
            def transform(devices):
                if kind=='node':devices[0]['nodes'][0]='changed'
                elif kind=='width':devices[0]['params']['w']='999'
                else:devices.pop()
                return devices
            with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'Placement changed'):
                reference.reordered(self.devices(),transform)

    def test_missing_monitor_finger_is_refused(self):
        devices=self.devices();index=next(i for i,d in enumerate(devices) if '__XTRACK__' in d['name'])
        with self.assertRaisesRegex(ValueError,'monitor'):monitor.place(devices[:index]+devices[index+1:])

    def test_cache_checks_all_physical_files_and_preserves_partial_geometry(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);identity={'placement':'test'}
            self.assertIsNone(reference.cached(out,identity,'source'))
            (out/'candidate.spice').write_text('source')
            with self.assertRaisesRegex(ValueError,'Incomplete'):reference.cached(out,identity,'source')
            result=dict(identity=identity,passed=True);(out/'summary.json').write_text(json.dumps(result))
            files={reference.TOP+s for s in ['.gds','.sch.spice','.lvs.log','.drc.txt','.drc_count.txt']}|{'summary.json','candidate.spice'}
            for n in files-{'summary.json','candidate.spice'}:(out/n).write_text('fixture')
            (out/'physical_cache.json').write_text(json.dumps(dict(files={n:reference.digest(out/n) for n in files})))
            self.assertEqual(reference.cached(out,identity,'source'),result)
            (out/(reference.TOP+'.lvs.log')).write_text('changed')
            with self.assertRaisesRegex(ValueError,'evidence changed'):reference.cached(out,identity,'source')

    def test_placement_policy_cannot_override_circuit_or_source_admission(self):
        path=ROOT/'build/diagnostics/receiver_layout/unused'
        with patch.object(reference.physical,'build') as draw:
            for policy in [dict(placement='x',source_screen='other'),dict(placement=None),
                           dict(placement='x',decision_tail_scale=1)]:
                with self.assertRaisesRegex(ValueError,'admission metadata'):
                    reference.build(path,monitor.place,policy,[])
            draw.assert_not_called()


if __name__=='__main__':unittest.main()
