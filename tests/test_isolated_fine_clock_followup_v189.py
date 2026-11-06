# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_isolated_fine_clock_followup_v189 as p


class FineClockFollowerAdmission(unittest.TestCase):
    def test_partial_failed_or_contradictory_pilot_cannot_dispatch_clock_matrix(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(p,'ROOT',Path(directory)):
            source=Path(directory)/'build/diagnostics'/p.SOURCE_CONTEXT/'0123456789abcdef';source.mkdir(parents=True)
            variants=[dict(driver=d,fine_copies=n) for d in ('inv','nand','mixed') for n in (1,2)]
            tasks=[dict(id=str(k),spec=dict(v,case=k%4)) for k,v in enumerate(v for v in variants for _ in range(4))]
            rows=[dict(task=t,spec=t['spec'],error=None,result=dict(current_clock_interface_screen_passed=True)) for t in tasks]
            comparison=[dict(variant=v,component_hypothesis_passed=True) for v in variants]
            state=dict(status='complete',cases=24,errors=0,qualified_phy=False)
            (source/'manifest.json').write_text(json.dumps(dict(tasks=tasks)))
            def save(r,c,s=state):
                (source/'summary.json').write_text(json.dumps(dict(rows=r,comparison=c)));(source/'state.json').write_text(json.dumps(s))
            save(rows,comparison);self.assertEqual(p.require_source(source),variants)
            changed=deepcopy(rows);changed[0]['result']['current_clock_interface_screen_passed']=False;save(changed,comparison)
            with self.assertRaises(ValueError):p.require_source(source)
            changed=deepcopy(comparison)
            for r in changed:r['component_hypothesis_passed']=False
            save(rows,changed)
            with self.assertRaises(ValueError):p.require_source(source)
            save(rows[:-1],comparison)
            with self.assertRaises(ValueError):p.require_source(source)
            save(rows,comparison,dict(state,errors=1))
            with self.assertRaises(ValueError):p.require_source(source)


if __name__=='__main__':unittest.main()
