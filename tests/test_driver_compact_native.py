# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_driver_compact_native as native


class CompactNativePilotGate(unittest.TestCase):
    def test_public_fixture_keeps_full_stimulus_accuracy_load_and_currents(self):
        deck='''.include "/old/source.spice"
VD D 0 PWL(0n 0 10n 1.8)
RT P N 100
CP P 0 2p
CN N 0 2p
.tran 1p 80n 0 1p
.print tran V(D) V(P) V(N) V(XD:XCORE:DP)
.save i(VIO) i(VDIG)
.end
'''
        out=native.fixture(deck,Path('/old'),Path('/new'))
        self.assertEqual(out,deck.replace('/old/source.spice','/new/source.spice').replace(
            '.print tran V(D) V(P) V(N) V(XD:XCORE:DP)', '.print tran V(D) V(P) V(N)'))
        for changed in [deck.replace('80n','40n'),deck.replace('0 1p','0 5p'),deck.replace(' i(VDIG)','')]:
            with self.assertRaises(ValueError): native.fixture(changed,Path('/old'),Path('/new'))

    def test_failed_extraction_never_launches_physical_or_scientific_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            ident={}
            name=hashlib.sha256(json.dumps(ident,sort_keys=True).encode()).hexdigest()[:16]
            parent=root/'build/diagnostics/driver_compact_extraction'/name
            parent.mkdir(parents=True)
            (parent/'summary.json').write_text(json.dumps(dict(identity=ident,passed=False)))
            with patch.object(native,'ROOT',root),patch.object(native,'engine',return_value='ngspice'),patch.object(native.physical,'run') as run:
                with self.assertRaises(ValueError): native.prepare(parent)
                run.assert_not_called()
