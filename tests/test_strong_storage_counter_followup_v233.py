# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_strong_storage_counter_followup_v233 as p


class StrongStoragePhysicalHandoff(unittest.TestCase):
    def test_fresh_rc_requires_every_physical_gate_and_exact_source_family(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'build/diagnostics'/p.PHYSICAL/('a'*16);source.mkdir(parents=True)
            state=dict(status='complete',passed=True,qualified_phy=False)
            report=dict(compact_counter_physical_passed=True,same_phase_logic=True,strong_native_storage_and_request=True,request_drivers=2,physical=dict(passed=True,drc_count='0',lvs_passed=True,macro_count=22,native_master_witness={k:True for k in ('all_shared_native_masters_identical','all_integrated_native_masters_preserved','integrated_macro_placements_verified')}))
            def save(s,r):
                (source/'state.json').write_text(json.dumps(s));(source/'summary.json').write_text(json.dumps(r))
            save(state,report)
            with patch.object(p,'ROOT',root):
                self.assertEqual(p.require_source(source),report)
                for key,value in [('drc_count','2'),('lvs_passed',False),('macro_count',20)]:
                    bad=deepcopy(report);bad['physical'][key]=value;save(state,bad)
                    with self.subTest(key=key),self.assertRaises(ValueError):p.require_source(source)
                for key in report['physical']['native_master_witness']:
                    bad=deepcopy(report);bad['physical']['native_master_witness'][key]=False;save(state,bad)
                    with self.subTest(key=key),self.assertRaises(ValueError):p.require_source(source)
                save(dict(state,status='routing'),report)
                with self.assertRaises(ValueError):p.require_source(source)
                save(state,report)
                with self.assertRaises(ValueError):p.require_source(source.parent/'other')


if __name__=='__main__':unittest.main()
