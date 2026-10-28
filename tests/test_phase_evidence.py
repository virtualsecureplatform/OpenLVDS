# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys,json,tempfile,unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from phase_evidence import case_valid,valid,digest
from spice_scope import closure_hash
from verify_phase_detector import response_cases

class PhaseEvidence(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.folder=self.root/'build/phase_detector/extracted/current/tt_25_150ps_r100_f100';self.folder.mkdir(parents=True)
        self.lib=b'.subckt openlvds_dll A B\nX1 A B leaf\n.ends openlvds_dll\n'
        self.scope=closure_hash(self.lib,'openlvds_dll');self.producer=b'phase producer fixture';self.inputs={'lvds_pfd':'physical-hash'}
        time=np.linspace(0,160e-9,32001);self.wave=np.zeros((len(time),8));self.wave[:,0]=np.arange(len(time));self.wave[:,1]=time
        for col,offset in [(2,0),(3,150e-12)]:
            phase=np.mod(time-5e-9-offset,2.5e-9)
            self.wave[:,col]=1.8*np.minimum(np.clip(phase/100e-12,0,1),np.clip(1-(phase-1.25e-9)/100e-12,0,1))
        self.wave[:,7]=1.8
        (self.folder/'library.spice').write_bytes(self.lib);(self.folder/'producer.py').write_bytes(self.producer);(self.folder/'bench.cir').write_text('.lib \"/pinned/sky130.lib.spice\" tt\n.options device temp=25\nVD VDDD 0 1.8\nVA VDDIO 0 3.3\nIB PB 0 35u\n')
        np.savetxt(self.folder/'bench.cir.prn',self.wave)
        self.result=dict(passed=True,corner='tt',temperature_c=25,offset_ps=150,reference_slew_ps=100,feedback_slew_ps=100,measurement_window_ns=[120,160],requirements_sha256='req',simulator='ngspice',simulator_provenance='engine',files={name:digest((self.folder/name).read_bytes()) for name in ['library.spice','producer.py','bench.cir','bench.cir.prn']})
    def check_case(self):return case_valid(self.folder,self.result,('tt',25,150,100,100),self.scope,'req','ngspice','engine',digest(self.producer))
    def test_current_response_passes(self):self.assertTrue(self.check_case())
    def test_stuck_low_cannot_be_blessed_by_a_pass_label_and_updated_hash(self):
        self.wave[:,7]=0;np.savetxt(self.folder/'bench.cir.prn',self.wave);self.result['files']['bench.cir.prn']=digest((self.folder/'bench.cir.prn').read_bytes());self.assertFalse(self.check_case())
    def test_wrong_slew_label_is_rejected(self):
        self.result['reference_slew_ps']=200;self.assertFalse(self.check_case())
    def test_modified_circuit_and_engine_are_rejected(self):
        self.result['simulator_provenance']='other';self.assertFalse(self.check_case());self.result['simulator_provenance']='engine'
        (self.folder/'library.spice').write_bytes(self.lib+b'* modified');self.assertFalse(self.check_case())
    def test_relabeling_corner_without_changing_the_deck_is_rejected(self):
        self.result['corner']='ss'
        self.assertFalse(case_valid(self.folder,self.result,('ss',25,150,100,100),self.scope,'req','ngspice','engine',digest(self.producer)))
    def test_actual_clock_slew_must_match_the_label(self):
        time=self.wave[:,1]
        for col,offset in [(2,0),(3,150e-12)]:
            phase=np.mod(time-5e-9-offset,2.5e-9)
            self.wave[:,col]=1.8*np.minimum(np.clip(phase/200e-12,0,1),np.clip(1-(phase-1.25e-9)/200e-12,0,1))
        np.savetxt(self.folder/'bench.cir.prn',self.wave);self.result['files']['bench.cir.prn']=digest((self.folder/'bench.cir.prn').read_bytes())
        self.assertFalse(self.check_case())
    def test_wrong_supply_cannot_be_relabelled_as_nominal(self):
        p=self.folder/'bench.cir';p.write_text(p.read_text().replace('VD VDDD 0 1.8','VD VDDD 0 1.7'))
        self.result['files']['bench.cir']=digest(p.read_bytes());self.assertFalse(self.check_case())
    def publish(self,report):
        p=self.folder.parent/'summary.json';p.write_text(json.dumps(report));return dict(report=str(p.relative_to(self.root)),sha256=digest(p.read_bytes()))
    def report(self):
        p=self.root/'scripts/verify_phase_detector.py';p.parent.mkdir(exist_ok=True);p.write_bytes(self.producer)
        return dict(passed=True,extracted=True,corners=True,slew_corners=False,cases={f'{c}_{t}_{o}ps_r{sr}_f{sf}':dict(extraction_inputs=self.inputs) for c,t,o,sr,sf in response_cases(corners=True)})
    def check_report(self,pointer):return valid(self.root,pointer,self.lib,self.inputs,'req','ngspice','engine','corners')
    def test_complete_matrix_is_required_even_if_aggregate_passes(self):
        report=self.report()
        with patch('phase_evidence.case_valid',return_value=True):
            self.assertTrue(self.check_report(self.publish(report)))
            report['cases'].pop(next(iter(report['cases'])));self.assertFalse(self.check_report(self.publish(report)))
    def test_schematic_or_stale_extraction_cannot_satisfy_release(self):
        report=self.report();report['extracted']=False
        self.assertFalse(self.check_report(self.publish(report)));report['extracted']=True
        next(iter(report['cases'].values()))['extraction_inputs']={}
        with patch('phase_evidence.case_valid',return_value=True):self.assertFalse(self.check_report(self.publish(report)))
    def test_report_path_cannot_escape_extracted_artifacts(self):
        self.assertFalse(self.check_report(dict(report='scripts/verify_phase_detector.py',sha256=digest(self.producer))))

if __name__=='__main__':unittest.main()
