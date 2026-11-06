# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import export_proposed_code_rom_v297 as p
ROOT=p.ROOT

class ProposedRomExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        curves={corner:{edge:[p.Delay(code,100+5*code,100+5*code+.2) for code in range(256)] for edge in ('rise','fall')} for corner in p.selector.PVT}
        # Reverse two raw codes universally; legal indices must map back through a ROM.
        for record in curves.values():
            for table in record.values():
                a,b=table[15],table[16];table[15]=p.Delay(15,b.lo_ps,b.hi_ps);table[16]=p.Delay(16,a.lo_ps,a.hi_ps)
        cls.selection=p.selector.select(curves,'tx',16,16)

    def test_packed_native_codes_preserve_filtered_common_order_and_never_admit(self):
        r=p.parameters(self.selection)
        self.assertEqual(r['TABLE_MODEL_ADMITTED'],0)
        self.assertEqual(r['NATIVE_CODE_COUNT'],256)
        for k,code in enumerate(r['codes']):self.assertEqual((r['packed_integer']>>(k*r['RAW_WIDTH']))&((1<<r['RAW_WIDTH'])-1),code)
        self.assertLess(r['codes'].index(16),r['codes'].index(15))

    def test_changed_order_range_missing_curve_or_admission_claim_cannot_export(self):
        for fault in ('order','range','curve','admission'):
            s=deepcopy(self.selection)
            if fault=='order':s['codes'][2],s['codes'][3]=s['codes'][3],s['codes'][2]
            elif fault=='range':s['policy']['quarter_max_ps']-=10
            elif fault=='curve':s['selected_curves'].pop(next(iter(s['selected_curves'])))
            else:s['legal_code_table_admitted']=True
            with self.assertRaises(ValueError):p.parameters(s)

    def test_export_binds_sources_and_retains_previous_output(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            base=Path(tmp);proposal=base/'proposal.json';proposal.write_text(json.dumps(self.selection));out=base/'rom'
            p.export(proposal,out);r=json.loads((out/'manifest.json').read_text())
            self.assertFalse(r['legal_code_table_admitted']);self.assertFalse(r['qualified_phy'])
            self.assertIn('.TABLE_MODEL_ADMITTED(0)',(out/'parameters.vh').read_text())
            self.assertEqual(r['parameters_sha256'],p.hashlib.sha256((out/'parameters.vh').read_bytes()).hexdigest())
            with self.assertRaises(FileExistsError):p.export(proposal,out)

if __name__=='__main__':unittest.main()
