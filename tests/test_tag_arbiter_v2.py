# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_tag_arbiter_v2 as arbiter
ROOT=Path(__file__).resolve().parents[1]

class TaggedArbiterMeasurements(unittest.TestCase):
    def wave(self,missing=False,uncleared=False):
        t=np.arange(0,42001,10,dtype=float)
        names=['time']+['v('+n+')' for n in ['qa','qb','xd.a','xd.b','xd.ha','xd.hb']]
        w=np.zeros((len(t),len(names)));w[:,0]=t*1e-12;w[:,2]=1.8
        for i in range(4):
            start=i*10000
            w[(t>=start+2100)&(t<start+3350),3]=1.8
            w[(t>=start+2120)&(t<start+3370),4]=1.8
            w[(t>=start+2500)&(t<start+7500),5:7]=1.8
        if missing:w[(t>=5500)&(t<=6500),5]=0
        if uncleared:w[(t>=8500)&(t<=9500),5]=1.8
        return names,w
    def test_retained_isolated_tags_and_conditioned_edge_witnesses(self):
        with patch.object(arbiter.base,'read_raw',return_value=self.wave()):
            r=arbiter.measure(Path('/fixture'),dict(offset_ps=20,swap=0))
        self.assertEqual(r['correct_sign_fraction'],1)
        self.assertEqual(len(r['votes']),4)
        self.assertTrue(all(abs(d-20)<1e-6 for d in r['conditioned_feedback_minus_reference_ps']))
        self.assertFalse(r['detector_admitted'])
    def test_lost_tag_and_failed_clear_cannot_be_scored(self):
        for wave in [self.wave(missing=True),self.wave(uncleared=True)]:
            with patch.object(arbiter.base,'read_raw',return_value=wave):
                with self.assertRaises(ValueError):arbiter.measure(Path('/fixture'),dict(offset_ps=20,swap=0))
    @unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Use scripts/env.sh')
    def test_feedback_latches_hold_events_until_explicit_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'test.vvp'
            for name in ['openlvds_tag_arbiter_v2','openlvds_preconditioned_arbiter_v2']:
                bench=Path(tmp)/'bench.v'
                bench.write_text((ROOT/'tb/tb_tag_arbiter_v2.v').read_text().replace('openlvds_tag_arbiter_v2 dut',name+' dut'))
                compile_result=subprocess.run(['iverilog','-g2012','-s','tb_tag_arbiter_v2','-o',str(binary),
                    str(ROOT/'sky130/v2'/f'{name}.v'),str(bench)],capture_output=True,text=True)
                self.assertEqual(compile_result.returncode,0,compile_result.stdout+compile_result.stderr)
                result=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('PASS v2',result.stdout)
