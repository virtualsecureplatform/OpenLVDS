# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import qualify_driver_output_shape_source as source


class ShapedDriverSourceMatrix(unittest.TestCase):
    def req(self):return json.loads((Path(__file__).resolve().parents[1]/'requirements.json').read_text())

    def test_full_both_polarity_pvt_coverage_and_duplicate_rejection(self):
        req=self.req();rows=source.cases(req)
        self.assertEqual(len(rows),30);self.assertEqual(len({(r['process'],r['temperature']) for r in rows}),15)
        for process in req['process_corners']:
            for temp in req['temperatures_c']:self.assertEqual({r['op'] for r in rows if r['process']==process and r['temperature']==temp},set(source.shape.CASES))
        for changed in [dict(req,temperatures_c=[25]),dict(req,temperatures_c=[0,25,25])]:
            with self.assertRaises(ValueError):source.cases(changed)

    def test_fixture_changes_only_pvt_and_include(self):
        deck='Source\n.lib "/pdk/sky130.lib.spice" tt\n.include "/old/source.spice"\n.options device temp=25\nVIO VDDIO 0 3.3\nVDIG VDDD 0 1.8\nVREF VREF 0 1.2\nIREF IREF 0 35u\nRT P N 100\nCP P 0 2p\nCN N 0 2p\n.tran 1p 80n 0 1p\n.end\n'
        actual=source.fixture(deck,Path('/old'),Path('/new'),dict(process='ss',temperature=40))
        self.assertEqual(actual,deck.replace('" tt','" ss').replace('temp=25','temp=40').replace('/old/','/new/'))
        with self.assertRaises(ValueError):source.fixture(deck.replace('VDDD 0 1.8','VDDD 0 1.7'),Path('/old'),Path('/new'),dict(process='ss',temperature=40))

    def test_pair_requires_both_calibrations_and_all_reference_checks(self):
        rows=[dict(task=op,returncode=0,metrics=dict(common_mode_pp_v=.12,rising_output_edges=22),initial_dc=dict(differential_v=sign*.34,common_mode_v=1.25,differential_pp_v=0,common_mode_pp_v=0)) for op,sign in zip(source.shape.CASES,[-1,1])]
        waveforms={op:dict(within_reference=True) for op in source.shape.CASES};req=self.req()
        self.assertTrue(source.pair_checks(rows,waveforms,req));self.assertFalse(source.pair_checks(rows[:1],waveforms,req))
        for group,key,value in [('metrics','common_mode_pp_v',.151),('metrics','rising_output_edges',21),('initial_dc','common_mode_v',1.5),('initial_dc','differential_v',.249),('initial_dc','common_mode_pp_v',.01)]:
            changed=json.loads(json.dumps(rows));changed[1][group][key]=value;self.assertFalse(source.pair_checks(changed,waveforms,req))
        self.assertFalse(source.pair_checks(rows,dict(waveforms,positive_op=dict(within_reference=False)),req))

    def test_incomplete_nominal_producer_is_never_invoked_by_admission(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(source,'ROOT',Path(tmp)),patch.object(source,'provenance',return_value='engine'):
            i=dict(inputs={},code={},simulator='engine');name=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            parent=Path(tmp)/'build/diagnostics/driver_output_shape'/name;parent.mkdir(parents=True)
            (parent/'manifest.json').write_text(json.dumps(dict(identity=i,tasks=[])))
            with patch.object(source.shape.pilot,'measure',side_effect=AssertionError('Unfinished nominal case invoked')):
                with self.assertRaisesRegex(ValueError,'Complete both shaping'):source.pilot_ready(parent)


if __name__=='__main__':unittest.main()
