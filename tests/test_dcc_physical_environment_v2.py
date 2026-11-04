# SPDX-License-Identifier: GPL-3.0-only
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import harden_dcc_v2 as physical


class PhysicalEnvironmentTests(unittest.TestCase):
    def test_layout_entrypoint_imports_without_scientific_site_packages(self):
        result=subprocess.run([sys.executable,'-S',str(physical.ROOT/'scripts/harden_dcc_v2.py'),'--help'],
            capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('campaign',result.stdout)

    def test_source_gate_uses_scientific_python_without_foreign_package_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);receipt=root/'build/diagnostics/dcc_clock_hold_pvt_verification_v2/hash/summary.json'
            receipt.parent.mkdir(parents=True);receipt.write_text('fixture')
            with patch.object(physical,'ROOT',root),patch.dict(os.environ,PYTHONPATH='/foreign',PYTHONHOME='/foreign'),\
                 patch.object(physical.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(dict(receipt=str(receipt))),'')) as run:
                self.assertEqual(physical.source_admission(root/'parent'),receipt)
                args,kwargs=run.call_args
                self.assertEqual(args[0][:2],['/usr/bin/python3',str(root/'scripts/dcc_source_admission_v2.py')])
                self.assertNotIn('PYTHONPATH',kwargs['env']);self.assertNotIn('PYTHONHOME',kwargs['env'])

    def test_scientific_failure_cannot_start_layout_or_use_an_unrelated_receipt(self):
        for completed in [subprocess.CompletedProcess([],1,'','Changed witness'),
                          subprocess.CompletedProcess([],0,json.dumps(dict(receipt='/unrelated/summary.json')),'')]:
            with patch.object(physical.subprocess,'run',return_value=completed):
                with self.assertRaises(ValueError):physical.source_admission(physical.ROOT/'parent')
