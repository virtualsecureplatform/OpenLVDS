# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import verify_digital_clocking_v2 as evidence

class SourceEvidenceTests(unittest.TestCase):
    def test_binary_export_agreement_and_tampering(self):
        names=['time','v(q)','v(xd.qt)']
        raw=np.array([[0.,0.,1.8],[1e-12,.1,1.7],[2e-12,1.5,.3]])
        exported=np.column_stack([np.arange(3),raw])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'bench.cir.prn'
            def save(data):np.savetxt(path,data,header='Index TIME V(Q) V(XD:QT)',comments='',fmt='%.17g')
            with patch.object(evidence.base,'read_raw',return_value=(names,raw)):
                save(exported);evidence.export_matches_raw(root)
                for row,column in [(1,1),(1,2),(2,3),(1,0)]:
                    bad=exported.copy();bad[row,column]+=.001;save(bad)
                    with self.assertRaises(ValueError):evidence.export_matches_raw(root)
                save(exported[:-1])
                with self.assertRaises(ValueError):evidence.export_matches_raw(root)
