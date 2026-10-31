# SPDX-License-Identifier: GPL-3.0-only
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dll_native_evidence as native
from staged_release import proof_binding


class NativeReleaseCoverage(unittest.TestCase):
    def test_release_requires_clock_extremes_all_pvt_and_asymmetric_stuck_faults(self):
        req=json.loads((native.ROOT/'requirements.json').read_text())
        cases=native.required_cases(req)
        for spec in [dict(kind='loop',process='ss',temperature=0,mhz=410,duty=.55),
                     dict(kind='loop',process='ff',temperature=0,mhz=390,duty=.45),
                     dict(kind='loop',process='sf',temperature=40,mhz=400,duty=.5),
                     dict(kind='logic',process='fs',temperature=25,up=0,dn=1.8),
                     dict(kind='phase',process='ss',temperature=40,mhz=400,offset_ps=-150,reference_slew_ps=20,feedback_slew_ps=200)]:
            self.assertIn(native.signature(spec),cases)
        self.assertNotIn(native.signature(dict(kind='loop',process='ss',temperature=0,mhz=420,duty=.55)),cases)

    def test_missing_duplicate_and_charge_pump_cases_cannot_pass_coverage(self):
        task=dict(id='loop',fast_rc=False,spec=dict(kind='loop',architecture='averaged_pfd_ota'))
        manifest=dict(tasks=[task],identity={})
        expected={native.signature(task['spec'])}
        with patch.object(native,'required_cases',return_value=expected):
            self.assertEqual(set(native.check_coverage(manifest,{})),{'loop'})
            for tasks in [[],[task,copy.deepcopy(task)]]:
                with self.assertRaisesRegex(ValueError,'coverage'):native.check_coverage(dict(manifest,tasks=tasks),{})
            changed=copy.deepcopy(task);changed['spec']['architecture']='charge_pump'
            with self.assertRaisesRegex(ValueError,'OTA architecture'):native.check_coverage(dict(manifest,tasks=[changed]),{})

    def test_logic_fixture_cannot_accept_stuck_quiet(self):
        task=dict(id='stuck',fast_rc=False,spec=dict(kind='logic',expected=False))
        with patch.object(native,'required_cases',return_value={native.signature(task['spec'])}):
            with self.assertRaisesRegex(ValueError,'require a fault'):
                native.check_coverage(dict(tasks=[task],identity={}),{})


class ReleaseProofBinding(unittest.TestCase):
    def test_proof_from_other_candidate_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'another native DLL candidate'):
            proof_binding(Path('/candidate_b/recovery/hash/summary.json'),Path('/candidate_a'))

    def test_proofs_must_share_the_selected_model_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            q=Path(directory).resolve();folder=q/'readiness/hash';folder.mkdir(parents=True)
            report=folder/'summary.json';model=q/'stability/hash/summary.json';recovery=q/'recovery/hash/summary.json'
            (folder/'manifest.json').write_text(json.dumps(dict(identity=dict(stability=str(model),recovery=str(recovery)))))
            proof_binding(report,q,model,recovery)
            with self.assertRaisesRegex(ValueError,'another stability'):
                proof_binding(report,q,q/'stability/other/summary.json',recovery)
            with self.assertRaisesRegex(ValueError,'another recovery'):
                proof_binding(report,q,model,q/'recovery/other/summary.json')


class ArchitectureSourceBinding(unittest.TestCase):
    def fixture(self,root):
        screen=root/'build/diagnostics/dll_architecture/screen';(screen/'inputs/scripts').mkdir(parents=True)
        layout=root/'build/diagnostics/dll_layout/layout';layout.mkdir(parents=True)
        (layout/'candidate.spice').write_text('exact source\n');(screen/'inputs/ota_w8_c4.spice').write_text('exact source\n')
        scripts=root/'scripts';scripts.mkdir();producer=scripts/'screen_repaired_dll.py';producer.write_text('producer version one\n')
        archive=screen/'inputs/scripts/screen_repaired_dll.py';archive.write_bytes(producer.read_bytes())
        library=('.subckt lvds_pfd REF FB RESET_N PD_ENABLE UP DN VDDD VSS\nC1 UP VSS 2f\n.ends lvds_pfd\n'
                 '.subckt lvds_bias IREF NB VDDIO VSS\nC2 IREF VSS 3f\n.ends lvds_bias\n')
        tasks=[]
        for name in ['ss_0','tt_25','ff_0']:
            folder=screen/name;folder.mkdir();(folder/'library.spice').write_text(library)
            tasks.append(dict(id=name,spec=dict(variant='ota_w8_c4',kind='loop'),
                              files={'library.spice':native.digest(folder/'library.spice')}))
        (screen/'manifest.json').write_text(json.dumps(dict(identity=dict(producer_code={producer.name:native.digest(producer)}),tasks=tasks)))
        q=root/'build/diagnostics/dll_qualification/native';q.mkdir(parents=True)
        (q/'full.spice').write_text(library)
        manifest=dict(identity=dict(screen=str(screen.relative_to(root)),screen_manifest_sha256=native.digest(screen/'manifest.json'),
            full_library_sha256=native.digest(q/'full.spice'),variant='ota_w8_c4',
            full_models=dict(layout=str(layout.relative_to(root)),source_sha256=native.digest(layout/'candidate.spice'))))
        return q,manifest,screen,producer,archive

    def test_changed_screened_source_cannot_qualify_the_physical_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();q,m,screen,_,_=self.fixture(root)
            with patch.object(native,'ROOT',root):
                native.architecture_sources(q,m)
                (screen/'inputs/ota_w8_c4.spice').write_text('different source\n')
                with self.assertRaisesRegex(ValueError,'differs from the physical'):
                    native.architecture_sources(q,m)

    def test_native_pfd_and_bias_must_match_the_actual_screened_circuits(self):
        for token in ['C1 UP VSS 2f','C2 IREF VSS 3f']:
            with self.subTest(circuit=token),tempfile.TemporaryDirectory() as directory:
                root=Path(directory).resolve();q,m,_,_,_=self.fixture(root)
                path=q/'full.spice';path.write_text(path.read_text().replace(token,token[:-2]+'9f'))
                m['identity']['full_library_sha256']=native.digest(path)
                with patch.object(native,'ROOT',root):
                    with self.assertRaisesRegex(ValueError,'differs from the native'):
                        native.architecture_sources(q,m)

    def test_unchanged_top_adapter_cannot_hide_a_different_physical_detector(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();q,m,screen,_,_=self.fixture(root)
            original=(q/'full.spice').read_text();start=original.index('.subckt lvds_bias')
            tail=original[start:]
            detector=('.subckt lvds_pfd REF FB RESET_N PD_ENABLE UP DN VDDD VSS\n'
                      'XPHY UP DN lvds_pfd_physical\n.ends lvds_pfd\n'
                      '.subckt lvds_pfd_physical UP DN\nCLOAD UP DN 2f\n.ends lvds_pfd_physical\n')
            (q/'full.spice').write_text(detector+tail);m['identity']['full_library_sha256']=native.digest(q/'full.spice')
            saved=json.loads((screen/'manifest.json').read_text())
            for task in saved['tasks']:
                path=screen/task['id']/'library.spice';path.write_text(detector.replace('CLOAD UP DN 2f','CLOAD UP DN 3f')+tail)
                task['files']['library.spice']=native.digest(path)
            (screen/'manifest.json').write_text(json.dumps(saved));m['identity']['screen_manifest_sha256']=native.digest(screen/'manifest.json')
            with patch.object(native,'ROOT',root):
                with self.assertRaisesRegex(ValueError,'native lvds_pfd'):
                    native.architecture_sources(q,m)

    def test_current_producer_and_archived_copy_must_both_match(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();q,m,_,producer,archive=self.fixture(root);original=producer.read_bytes()
            with patch.object(native,'ROOT',root):
                for target in [producer,archive]:
                    target.write_text('changed producer\n')
                    with self.assertRaisesRegex(ValueError,'producer or its archive changed'):
                        native.architecture_sources(q,m)
                    target.write_bytes(original)
                native.architecture_sources(q,m)
