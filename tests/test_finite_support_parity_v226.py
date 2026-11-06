# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import json
import tempfile
from unittest.mock import patch
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import verify_finite_support_parity_v226 as p


class CompleteNativeInputParity(unittest.TestCase):
    def test_all_four_case_pairs_are_required_and_clock_qualification_is_separate(self):
        rows=[dict(case=str(k),comparison=dict(native_waveform_parity_passed=True,same_all_original_gate_results=True)) for k in range(4)]
        r=p.assess(rows);self.assertTrue(r['full_four_case_waveform_parity_passed'])
        for key in ('bank_clock_interface_qualified','all_pvt_covered','electrical_qualification_passed','qualified_phy'):self.assertFalse(r[key])
        for count in (0,2,3):
            with self.assertRaises(ValueError):p.assess(rows[:count])
        bad=deepcopy(rows);bad[-1]['case']='0'
        with self.assertRaises(ValueError):p.assess(bad)
        bad=deepcopy(rows);bad[-1]['comparison']['native_waveform_parity_passed']=False
        self.assertFalse(p.assess(bad)['full_four_case_waveform_parity_passed'])
        self.assertTrue(p.assess(bad)['all_four_original_reference_cases_present'])
        bad=deepcopy(rows);bad[-1]['comparison']['same_all_original_gate_results']=False
        self.assertFalse(p.assess(bad)['full_four_case_waveform_parity_passed'])


    def test_incomplete_real_handoff_is_refused_before_creating_a_receipt(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(p,'ROOT',Path(directory)):
            root=Path(directory);candidate=root/'build/diagnostics'/p.replay.CONTEXT/('a'*16)
            source=root/'build/diagnostics'/p.replay.source.CONTEXT/('b'*16)
            candidate.mkdir(parents=True);source.mkdir(parents=True)
            (candidate/'manifest.json').write_text(json.dumps(dict(identity=dict(version=p.replay.VERSION,parent=str(source.relative_to(root))))))
            (source/'manifest.json').write_text(json.dumps(dict(tasks=[{}]*4)))
            with self.assertRaisesRegex(ValueError,'All four original and candidate native cases must be complete'):p.verify(candidate)
            self.assertFalse((root/'build/diagnostics'/p.CONTEXT).exists())


if __name__=='__main__':unittest.main()
