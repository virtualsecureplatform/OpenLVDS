# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import phy_candidate
from spice_scope import closure_hash


class CandidateEvidence(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.bundle=self.root/'build/diagnostics/phy_candidate/example';self.bundle.mkdir(parents=True)
        self.q=self.root/'build/diagnostics/dll_qualification/example';self.q.mkdir(parents=True)
        (self.q/'manifest.json').write_text('{}')
        (self.root/'scripts').mkdir();(self.root/'scripts/stage_phy_candidate.py').write_text('producer')
        (self.root/'requirements.json').write_text('{}')
        self.library=b'.subckt DUT A B\nR0 A B 1\n.ends DUT\n'
        for mode in ['full','fast']:(self.bundle/(mode+'.spice')).write_bytes(self.library)
        info=dict(inputs={'DUT':'model'},digital_models={},physical_reports={},
                  scopes={'DUT':closure_hash(self.library,'DUT')})
        self.identity=dict(qualification=str(self.q.relative_to(self.root)),
            qualification_manifest_sha256=phy_candidate.digest(self.q/'manifest.json'),
            producer_sha256=phy_candidate.digest(self.root/'scripts/stage_phy_candidate.py'),
            requirements_sha256=phy_candidate.digest(self.root/'requirements.json'),full=info,fast=info,
            full_sha256=hashlib.sha256(self.library).hexdigest(),fast_sha256=hashlib.sha256(self.library).hexdigest())
        self.write()
        self.addCleanup(patch.stopall)
        patch.object(phy_candidate,'ROOT',self.root).start()
        patch.object(phy_candidate,'validate').start()

    def write(self):
        (self.bundle/'manifest.json').write_text(json.dumps({'identity':self.identity}))

    def test_load_exact_and_approximate_without_active_pointers(self):
        for mode in [False,True]:
            self.assertEqual(phy_candidate.load(self.bundle,mode),(self.library,{'DUT':'model'},{}))

    def test_modified_library_and_scope_are_rejected(self):
        (self.bundle/'full.spice').write_bytes(self.library+b'\n')
        with self.assertRaisesRegex(ValueError,'library'):phy_candidate.load(self.bundle)
        (self.bundle/'full.spice').write_bytes(self.library)
        self.identity['full']['scopes']['DUT']='different';self.write()
        with self.assertRaisesRegex(ValueError,'scope'):phy_candidate.load(self.bundle)

    def test_changed_source_manifest_is_rejected(self):
        (self.q/'manifest.json').write_text('{"changed":true}')
        with self.assertRaisesRegex(ValueError,'DLL manifest'):phy_candidate.load(self.bundle)

    def test_external_bundle_path_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'outside'):phy_candidate.load(self.q)

    def phase_fixture(self):
        library=b'.subckt openlvds_dll A B\nR0 A B 1\n.ends openlvds_dll\n'
        (self.bundle/'full.spice').write_bytes(library);(self.q/'full.spice').write_bytes(library)
        self.folder=self.q/'loop_tt_25';self.folder.mkdir()
        (self.folder/'bench.cir').write_text('native deck')
        (self.folder/'bench.cir.prn').write_text('native waveform')
        measured=dict(passed=True,quarter_phase_min_ps=610,quarter_phase_max_ps=635)
        task=dict(id='loop_tt_25',fast_rc=False,deck_sha256=phy_candidate.digest(self.folder/'bench.cir'),
            spec=dict(kind='loop',process='tt',temperature=25,mhz=400,duty=.5))
        (self.q/'manifest.json').write_text(json.dumps({'tasks':[task]}))
        (self.folder/'summary.json').write_text(json.dumps(dict(passed=True,metrics=measured,
            deck_sha256=task['deck_sha256'],waveform_sha256=phy_candidate.digest(self.folder/'bench.cir.prn'))))
        patch.object(phy_candidate,'load').start()
        patch.object(phy_candidate,'evaluate',return_value=measured).start()

    def test_phase_partition_uses_matching_native_case(self):
        self.phase_fixture()
        result=phy_candidate.phase(self.bundle,'tt',25,400,.5)
        self.assertEqual(result['quarter_phase_min_ps'],610)
        for p,t,f,d in [('ff',25,400,.5),('tt',25,410,.5),('tt',25,400,.55)]:
            with self.assertRaisesRegex(ValueError,'Missing'):
                phy_candidate.phase(self.bundle,p,t,f,d)

    def test_phase_partition_rejects_changed_native_waveform(self):
        self.phase_fixture();(self.folder/'bench.cir.prn').write_text('changed')
        with self.assertRaisesRegex(ValueError,'evidence'):
            phy_candidate.phase(self.bundle,'tt',25,400,.5)
