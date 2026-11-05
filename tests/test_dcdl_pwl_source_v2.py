# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_dcdl_pwl_source_v2 as pilot


class NativeSourceIsolationTests(unittest.TestCase):
    def test_only_input_source_representation_and_title_change(self):
        out=Path('/prepared');spec=dict(process='ss',temperature=40,coarse=1,fine=0,load_ff=20,input_slew_ps=100)
        devices=[dict(terminals=['IN','XD:private','VDD','0'])]
        with patch.dict(pilot.baseline.os.environ,{'PDK_ROOT':'/pdk'}):
            old=pilot.baseline.fixture(out,spec,devices);new,certificate=pilot.fixture(out,spec,devices)
        original=re.findall(r'(?m)^BIN IN 0 [^\n]+$',old)
        replaced=re.sub(r'(?ms)^VIN IN 0 PWL\(\n.*?^\+ \)',original[0],new)
        replaced=replaced.replace('OpenLVDS '+pilot.VERSION,'OpenLVDS '+pilot.baseline.VERSION,1)
        self.assertEqual(replaced,old)
        self.assertIn('.tran 2p 20n 0 2p',new)
        self.assertLess(certificate['maximum_interpolation_bound_v'],50e-6)


if __name__=='__main__':unittest.main()
