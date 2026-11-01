# SPDX-License-Identifier: GPL-3.0-only
from collections import Counter
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import layout_receiver_input_island as island
from layout import circuits,flatten

ROOT=Path(__file__).resolve().parents[1]


class ReceiverInputIsland(unittest.TestCase):
    def devices(self):
        source=island.tail.source_variant((ROOT/'analog/openlvds.spice').read_text(),True)
        return flatten(circuits(source),island.TOP)[1]

    def test_island_reorders_exact_fingers_without_changing_any_device(self):
        devices=self.devices();before=json.dumps(devices,sort_keys=True)
        actual=island.place(devices)
        self.assertEqual(json.dumps(devices,sort_keys=True),before)
        self.assertEqual(Counter(json.dumps(d,sort_keys=True) for d in actual),
                         Counter(json.dumps(d,sort_keys=True) for d in devices))
        names=[island.logical(d) for d in actual];anchor=names.index('XPCB')
        expected=Counter({n:2 for n in island.MIRRORS})+Counter({n:1 for n in island.LOADS})
        self.assertEqual(Counter(names[anchor-18:anchor]),expected)
        members=set(island.MIRRORS+island.LOADS)
        self.assertEqual([d for d in actual if island.logical(d) not in members],
                         [d for d in island.tail.place_monitor(devices) if island.logical(d) not in members])
        self.assertEqual(island.place(actual),actual)

    def test_missing_mirror_finger_or_resistor_and_wrong_hierarchy_are_refused(self):
        devices=self.devices()
        for name in ['XNML','XRLPPA']:
            index=next(i for i,d in enumerate(devices) if island.logical(d)==name)
            with self.assertRaisesRegex(ValueError,'finger coverage'):island.place(devices[:index]+devices[index+1:])
        with self.assertRaisesRegex(ValueError,'hierarchy'):island.logical(dict(name='other__XNML_F0'))

    def test_cached_geometry_is_immutable_and_partial_geometry_never_redraws(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);identity={'placement':'fixture'}
            self.assertIsNone(island.cached(out,identity,'source'))
            (out/'candidate.spice').write_text('source')
            with self.assertRaisesRegex(ValueError,'Incomplete'):island.cached(out,identity,'source')
            report=dict(identity=identity,passed=True)
            (out/'summary.json').write_text(json.dumps(report))
            files={island.TOP+s for s in ['.gds','.sch.spice','.lvs.log','.drc.txt','.drc_count.txt']}|{'summary.json','candidate.spice'}
            for name in files-{'summary.json','candidate.spice'}:(out/name).write_text('fixture')
            (out/'physical_cache.json').write_text(json.dumps(dict(files={n:island.digest(out/n) for n in files})))
            self.assertEqual(island.cached(out,identity,'source'),report)
            (out/(island.TOP+'.gds')).write_text('changed')
            with self.assertRaisesRegex(ValueError,'evidence changed'):island.cached(out,identity,'source')


if __name__=='__main__':unittest.main()
