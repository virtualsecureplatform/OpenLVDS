# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import link_evidence as evidence
from simulate_link import pwl


class LinkEvidence(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.root=Path(folder.name);self.library=b'captured circuit'
        self.req=dict(injected_jitter_pp_ps=100)
        self.case=dict(name='nominal',config=dict(bits=64,dll_phase=True,settled_start=True))
        self.aperture=dict(qualified=True,setup_ps=120,hold_ps=90,table='fixture/table.json',table_sha256='fixture')
        config=dict(bits=64,process='tt',temperature=25,mhz=400,duty=.5,skew_ps=0,
            eye_shift_ps=0,clock_source='ideal',dll_phase=True,settled_start=True,
            jitter_pp_ps=100,diagnostic=False,fast_rc=False,simulator='fixture',training_ns=None,rx_aperture=self.aperture)
        self.c0=[(0,0),(5,1.8)];self.c90=[(0,0),(5.625,1.8)]
        scope='measured DLL characterization'
        files={'scripts/simulate_link.py':b'current runner','requirements.json':json.dumps(self.req).encode(),
               'analog/openlvds.spice':b'current analog source'}
        for name,data in files.items():
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        clock=(pwl(self.c0)+pwl(self.c90)).encode()
        fingerprint=evidence.digest(self.library+files['requirements.json']+json.dumps(config,sort_keys=True).encode()+
            files['scripts/simulate_link.py']+b'fixture provenance'+clock+scope.encode())
        self.out=self.root/'build/link/nominal'/fingerprint[:12];self.out.mkdir(parents=True)
        self.summary=dict(passed=True,diagnostic=False,config=config,word_errors=0,
            rx_aperture=self.aperture,
            capture_aperture_slew_passed=True,
            electrical_passed=True,sampling_margin_passed=True,checked_bits=64,
            actual_clock_mhz=400,training_ns=640,clock_partition=scope,
            simulator='fixture',simulator_provenance='fixture provenance',network='full distributed RC',
            clock_waveform_sha256=evidence.digest(clock),fingerprint=fingerprint,
            output=str(self.out.relative_to(self.root)))
        for filename,data,key in [('runner.py',files['scripts/simulate_link.py'],'runner_sha256'),
                ('requirements.json',files['requirements.json'],'requirements_sha256'),
                ('analog_source.spice',files['analog/openlvds.spice'],'source_sha256'),
                ('library.spice',self.library,'library_sha256'),('bench.cir',b'deck','deck_sha256'),
                ('bench.cir.prn',b'waveform','waveform_sha256')]:
            (self.out/filename).write_bytes(data);self.summary[key]=evidence.digest(data)
        (self.out/'rx_aperture.json').write_text(json.dumps(self.aperture))
        for target,value in [('ROOT',self.root),('engine',lambda:'fixture'),
                ('provenance',lambda:'fixture provenance'),
                ('aperture_matches',lambda *_:True),
                ('clocks',lambda *_:(self.c0,self.c90,[],2.5,scope))]:
            patcher=patch.object(evidence,target,value);patcher.start();self.addCleanup(patcher.stop)

    def matches(self):return evidence.matches(self.summary,self.case,self.req,self.library)

    def test_complete_current_case_is_accepted(self):
        self.assertEqual(self.matches(),(True,''))

    def test_nominal_result_cannot_cover_another_skew(self):
        self.case['name']='timing_400_0.5_100';self.case['config']['skew_ps']=100
        self.assertFalse(self.matches()[0])

    def test_changed_waveform_and_runner_are_rejected(self):
        (self.out/'bench.cir.prn').write_bytes(b'edited waveform')
        self.assertFalse(self.matches()[0])
        (self.out/'bench.cir.prn').write_bytes(b'waveform')
        (self.root/'scripts/simulate_link.py').write_bytes(b'new analyzer')
        self.assertFalse(self.matches()[0])

    def test_changed_clock_characterization_is_rejected(self):
        with patch.object(evidence,'clocks',return_value=(self.c0,self.c90,[],2.5,'new DLL phase')):
            self.assertFalse(self.matches()[0])

    def test_short_training_or_diagnostic_cannot_release(self):
        self.summary['training_ns']=50
        self.assertFalse(self.matches()[0])
        self.summary['training_ns']=640;self.summary['diagnostic']=True
        self.assertFalse(self.matches()[0])

    def test_changed_circuit_is_rejected(self):
        self.library=b'new circuit'
        self.assertFalse(self.matches()[0])

    def test_missing_or_stale_capture_aperture_cannot_release(self):
        with patch.object(evidence,'aperture_matches',return_value=False):
            self.assertFalse(self.matches()[0])
        self.summary['capture_aperture_slew_passed']=False
        self.assertFalse(self.matches()[0])
        self.summary['capture_aperture_slew_passed']=True
        self.summary.pop('rx_aperture')
        self.assertFalse(self.matches()[0])


if __name__=='__main__':unittest.main()


class SelectedRXAperture(unittest.TestCase):
    def test_bundle_checks_its_exact_rx_model_and_reanalyzes_the_complete_table(self):
        config=dict(bundle='build/diagnostics/phy_candidate/selected',process='ss',temperature=40)
        record=dict(model_sha256='selected-exact-rx',table='build/characterization/rx_aperture/selected/table.json')
        models=dict(openlvds_ddr_rx=dict(netlist_sha256='selected-exact-rx'))
        with patch('phy_candidate.load',return_value=(b'library',{},models)) as load,patch('rx_aperture_evidence.read_table',return_value=record) as read:
            self.assertTrue(evidence.aperture_valid(record,config))
            self.assertEqual(read.call_args.args[1:],('selected-exact-rx','ss',40))
            self.assertEqual(load.call_args.args,(evidence.ROOT/config['bundle'],))
            read.reset_mock()
            self.assertFalse(evidence.aperture_valid(dict(record,model_sha256='preceding-rx'),config))
            read.assert_not_called()
