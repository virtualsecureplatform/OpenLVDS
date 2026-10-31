# SPDX-License-Identifier: GPL-3.0-only
import fcntl
import hashlib
import json
import os
from unittest.mock import patch
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import verify_component_evidence as receipt


class ComponentReceipt(unittest.TestCase):
    def fixture(self,folder):
        source=b'.subckt openlvds_driver D P N\nR1 D P 100\nR2 N 0 100\n.ends openlvds_driver\n'
        files={'source.spice':source,'bench.cir':b'fixture','bench.cir.prn':b'completed trace','runner.py':b'producer'}
        for name,data in files.items():(folder/name).write_bytes(data)
        h=lambda name:receipt.digest(folder/name)
        report=dict(passed=True,requirements_sha256='requirements',simulator='ngspice',simulator_provenance='simulator',
            source_sha256=h('source.spice'),deck_sha256=h('bench.cir'),waveform_sha256=h('bench.cir.prn'),
            runner_sha256=h('runner.py'),analysis_runner_sha256=h('runner.py'),extraction_inputs={},
            startup='solved fixed-supply DC operating point',dc_output=dict(passed=True))
        (folder/'summary.json').write_text(json.dumps(report))
        return source,h('runner.py')

    def check(self,folder,source,analysis):
        return receipt.check_case(folder,'driver',source,{},analysis,'requirements','ngspice','simulator')

    def test_exact_case_names_cover_ninety_distinct_proofs(self):
        req=dict(process_corners=['tt','ff','ss','fs','sf'],temperatures_c=[0,25,40])
        cases=receipt.cases(req)
        self.assertEqual(len(cases),90);self.assertEqual(len(set(cases)),90)
        self.assertEqual(sum(test=='receiver' for _,test,_,_ in cases),30)
        self.assertEqual(sum(test=='receiver_rate' for _,test,_,_ in cases),30)

    def test_history_does_not_hide_current_pass_or_corrupt_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);source,analysis=self.fixture(folder)
            history=folder/'history';history.mkdir();(history/'old_summary.json').write_text('{"passed": false}')
            self.assertTrue(self.check(folder,source,analysis)['passed'])
            (folder/'bench.cir.prn').write_text('modified trace')
            result=self.check(folder,source,analysis)
            self.assertFalse(result['passed']);self.assertFalse(result['checks']['bench.cir.prn'])

    def test_active_case_is_never_read_as_a_completed_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);source,analysis=self.fixture(folder)
            with (folder/'.run.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                result=self.check(folder,source,analysis)
                self.assertEqual(result['status'],'running');self.assertFalse(result['passed'])
            self.assertTrue(self.check(folder,source,analysis)['passed'])

    def test_stale_analysis_scope_and_dc_failure_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);source,analysis=self.fixture(folder)
            self.assertFalse(self.check(folder,source,'changed producer')['passed'])
            self.assertFalse(self.check(folder,source.replace(b'100',b'101'),analysis)['passed'])
            report=json.loads((folder/'summary.json').read_text());report['dc_output']['passed']=False
            (folder/'summary.json').write_text(json.dumps(report))
            self.assertFalse(self.check(folder,source,analysis)['passed'])

    def test_shared_reader_lock_works_with_nfs_descriptor_rules(self):
        original=fcntl.flock
        def nfs_lock(handle,operation):
            if operation & fcntl.LOCK_SH:
                access=fcntl.fcntl(handle.fileno(),fcntl.F_GETFL)&os.O_ACCMODE
                self.assertNotEqual(access,os.O_WRONLY,'NFS shared locks need a readable descriptor')
            return original(handle,operation)
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);source,analysis=self.fixture(folder)
            with patch.object(receipt.fcntl,'flock',side_effect=nfs_lock):
                self.assertTrue(self.check(folder,source,analysis)['passed'])
