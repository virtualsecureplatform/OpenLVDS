# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import stability_evidence as evidence


class Evidence(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.q=self.root/'build/diagnostics/dll_qualification/candidate'
        self.folder=self.q/'stability_screen/identity';self.folder.mkdir(parents=True)
        (self.q/'manifest.json').write_text('captured candidate manifest')
        (self.q/'full.spice').write_text('captured native model')
        code={}
        for name in evidence.PRODUCERS:
            path=self.root/'scripts'/name;path.parent.mkdir(exist_ok=True);path.write_text('captured '+name);code[name]=evidence.digest(path)
        self.inputs={'analog':'native hash'}
        manifest=dict(code=code,full_inputs=self.inputs,qualification_manifest_sha256=evidence.digest(self.q/'manifest.json'),library_sha256=evidence.digest(self.q/'full.spice'))
        (self.folder/'manifest.json').write_text(json.dumps(manifest))
        results=[]
        for corner in ['ss_0','tt_25','ff_0']:
            source={};files={}
            for i in range(6):
                p=self.q/f'{corner}_source_{i}';p.write_text('operating-point evidence');source[p.name]=evidence.digest(p)
            for name in evidence.MEASUREMENTS:
                p=self.folder/corner/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('native measurement');files[name]=evidence.digest(p)
            results.append(dict(corner=corner,passed=True,source_reports=source,files=files,
                models=[dict(passed=True,model_valid=True,phase_margin_min_deg=80,gain_margin_min_db=12)]*3,
                transient_validation=[dict(target_mhz=f,passed=True,amplitude_relative_error=.1,settling_relative_error=.1) for f in [390,410]]))
        self.report=dict(passed=True,full_inputs=self.inputs,manifest_sha256=evidence.digest(self.folder/'manifest.json'),
            producer_sha256=code['measure_dll_stability.py'],simulator_provenance='fixture',results=results,phase_margin_min_deg=80,gain_margin_min_db=12)
        p=patch.object(evidence,'ROOT',self.root);p.start();self.addCleanup(p.stop)
        p=patch('spice_engine.provenance',return_value='fixture');p.start();self.addCleanup(p.stop)

    def read(self,inputs=None):
        path=self.folder/'summary.json';path.write_text(json.dumps(self.report))
        return evidence.verified(path,self.inputs if inputs is None else inputs)

    def test_complete_current_measurement_is_accepted(self):
        self.assertTrue(self.read()['passed'])

    def test_pass_flag_cannot_cover_another_circuit_or_missing_model(self):
        with self.assertRaises(ValueError):self.read({'analog':'changed'})
        self.report['results'][0]['models']=[]
        with self.assertRaises(ValueError):self.read()

    def test_changed_measurement_and_model_disagreement_are_rejected(self):
        p=self.folder/'ss_0/instrument.spice';old=p.read_text();p.write_text('changed')
        with self.assertRaises(ValueError):self.read()
        p.write_text(old);self.report['results'][0]['transient_validation'][0]['settling_relative_error']=.4
        with self.assertRaises(ValueError):self.read()
