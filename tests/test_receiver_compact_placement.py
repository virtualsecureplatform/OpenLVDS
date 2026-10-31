# SPDX-License-Identifier: GPL-3.0-only
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from layout import circuits,flatten,primitive_key
from layout_receiver_gain_candidate import source_variant
from layout_receiver_compact_candidate import banks,ordered,TOP
ROOT=Path(__file__).resolve().parents[1]


class ReceiverCompactPlacement(unittest.TestCase):
    def test_real_candidate_preserves_all_devices_terminals_and_finger_banks(self):
        source=source_variant((ROOT/'analog/openlvds.spice').read_text())
        _,devices=flatten(circuits(source),TOP);before=copy.deepcopy(devices)
        library={primitive_key(d):('cell',dict(bbox=[-2,-4,2+float(d['params']['w']),4])) for d in devices}
        result,info=ordered(devices,library)
        self.assertEqual(devices,before)
        self.assertEqual(sorted(d['name'] for d in result),sorted(d['name'] for d in devices))
        self.assertEqual({d['name']:d for d in result},{d['name']:d for d in devices})
        for group in banks(devices):
            at=result.index(group[0]);self.assertEqual(result[at:at+len(group)],group)
        self.assertLess(info['objective_after_um'],info['objective_before_um'])
        again,again_info=ordered(devices,library)
        self.assertEqual(again,result);self.assertEqual(again_info,info)

    def test_duplicate_finger_identity_is_rejected(self):
        d=dict(name='X_F0',nodes=['a','b'],model='device',params={})
        with self.assertRaisesRegex(ValueError,'Duplicate'):banks([d,d.copy()])
