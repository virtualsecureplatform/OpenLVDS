# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import diagnose_counter_routes_v227 as p


class CounterDiagnosticSourceBinding(unittest.TestCase):
    def test_only_declared_counter_routes_and_complete_native_inventory_are_accepted(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(p,'ROOT',Path(directory)):
            def case(version,context,count=510,error='Sticky arm rising-event count'):
                identity=dict(version=version,devices=[{}]*count);digest=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
                parent=Path(directory)/'build/diagnostics'/context/digest;folder=parent/'0';folder.mkdir(parents=True,exist_ok=True);task=dict(id='0')
                (parent/'manifest.json').write_text(json.dumps(dict(identity=identity,tasks=[task])))
                (folder/'summary.json').write_text(json.dumps(dict(task=task,error=error,files={})));return folder
            for version,context in p.SOURCE_VERSIONS.items():
                with self.subTest(version=version),self.assertRaisesRegex(ValueError,'Missing completed'):
                    p.diagnose(case(version,context))
                with self.assertRaisesRegex(ValueError,'Require completed'):
                    p.diagnose(case(version,context+'_other'))
                with self.assertRaisesRegex(ValueError,'Require completed'):
                    p.diagnose(case(version,context,509))
                with self.assertRaisesRegex(ValueError,'Require completed'):
                    p.diagnose(case(version,context,error='Timestep too small'))
            with self.assertRaisesRegex(ValueError,'Require completed'):
                p.diagnose(case('unknown','other'))


if __name__=='__main__':unittest.main()
