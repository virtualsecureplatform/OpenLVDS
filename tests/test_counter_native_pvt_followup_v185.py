# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_counter_native_pvt_followup_v185 as p


class NativeCounterPvtAdmission(unittest.TestCase):
    def test_failed_partial_or_different_component_pilot_cannot_admit_sweep(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(p,'ROOT',Path(directory)):
            root=Path(directory);artifact=root/'build/diagnostics'/p.SOURCE_CONTEXT/'0123456789abcdef';artifact.mkdir(parents=True);component=root/'component'
            rows=[dict(error=None,result=dict(hypothesis_point_checks_passed=True,storage_component_physical_rc_qualified=True,setter_guard_geometry_qualified=True)) for _ in range(6)]
            (artifact/'state.json').write_text(json.dumps(dict(status='complete',cases=6,errors=0,qualified_phy=False)))
            (artifact/'manifest.json').write_text(json.dumps(dict(identity=dict(component='component'))))
            (artifact/'summary.json').write_text(json.dumps(dict(rows=rows)));self.assertEqual(p.require_source(artifact,component)['rows'],rows)
            with self.assertRaises(ValueError):p.require_source(artifact,root/'wrong_component')
            for key in ('hypothesis_point_checks_passed','storage_component_physical_rc_qualified','setter_guard_geometry_qualified'):
                changed=deepcopy(rows);changed[0]['result'][key]=False;(artifact/'summary.json').write_text(json.dumps(dict(rows=changed)))
                with self.subTest(key=key),self.assertRaises(ValueError):p.require_source(artifact,component)
            (artifact/'summary.json').write_text(json.dumps(dict(rows=rows[:-1])))
            with self.assertRaises(ValueError):p.require_source(artifact,component)


if __name__=='__main__':unittest.main()
