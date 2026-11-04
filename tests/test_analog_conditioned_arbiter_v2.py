# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_analog_conditioned_arbiter_v2 as analog

class AnalogArbiterMeasurements(unittest.TestCase):
    def fixture(self,folder,bad_ref=False,bad_stress=False):
        _,devices=analog.frontend.circuit('tail140_w20')
        spec=dict(offset_ps=20,swap=0)
        (folder.parent/'manifest.json').write_text(json.dumps(dict(tasks=[dict(id=folder.name,devices=devices)])))
        mapping={'REF':'R','FDB':'F','REF_FAST':'RFAST','FDB_FAST':'FFAST','VDDD':'VDD'}
        nodes={mapping.get(n,n) for d in devices for n in d['terminals'] if n!='0'}
        nodes|={'QA','QB','XD:ha','XD:hb','RFAST','FFAST','XF:VCM','XF:XREF:QO'}
        labels=sorted(nodes);names=['time']+['v('+n.replace(':','.').lower()+')' for n in labels]
        t=np.arange(0,242001,10,dtype=float);w=np.ones((len(t),len(names)))*.9;w[:,0]=t*1e-12
        def assign(n,value):w[:,names.index('v('+n.replace(':','.').lower()+')')]=value
        for n,v in [('VDD',1.8),('VDDIO',3.3),('PB',2.4),('QA',0),('QB',1.8),('XF:VCM',1.0 if bad_ref else .9)]:assign(n,v)
        for n in ['XD:ha','XD:hb','RFAST','FFAST']:assign(n,0)
        for cycle in range(4):
            start=200000+cycle*10000
            for n in ['XD:ha','XD:hb']:w[(t>=start+2500)&(t<start+7500),names.index('v('+n.replace(':','.').lower()+')')]=1.8
            for n,offset in [('RFAST',2500),('FFAST',2520)]:w[(t>=start+offset)&(t<start+offset+1250),names.index('v('+n.lower()+')')]=1.8
        if bad_stress:assign('XF:XREF:QO',2.1)
        return names,w,spec
    def run_fixture(self,bad_ref=False,bad_stress=False):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'0';folder.mkdir();names,w,spec=self.fixture(folder,bad_ref,bad_stress)
            with patch.object(analog.base,'read_raw',return_value=(names,w)):
                return analog.measure(folder,spec)
    def test_new_load_keeps_phase_reference_and_all_frontend_stress_gates(self):
        result=self.run_fixture()
        self.assertEqual(result['correct_sign_fraction'],1)
        self.assertTrue(result['frontend_stress_passed'])
        self.assertTrue(result['common_mode_passed'])
        self.assertFalse(result['detector_admitted'])
    def test_phase_sign_does_not_waive_reference_or_stress_failure(self):
        self.assertFalse(self.run_fixture(bad_ref=True)['common_mode_passed'])
        self.assertFalse(self.run_fixture(bad_stress=True)['frontend_stress_passed'])
