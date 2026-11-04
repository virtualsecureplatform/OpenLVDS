# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcdl_cap_bank_v2 as bank
import probe_digital_dcdl_cap_v2 as probe

class CapBankTests(unittest.TestCase):
    def test_all_thermometer_endpoints_and_off_discharge(self):
        for code in (0,1,16,31):
            text,devices=bank.circuit('mim2x2',0,code)
            self.assertEqual(len(devices),93)
            self.assertNotIn('sky130_fd_sc_hd__einvp',text)
            for i in range(31):
                n,p,clear=devices[3*i:3*i+3]
                self.assertEqual(n['terminals'][1],'VDD' if i<code else 'VSS')
                self.assertEqual(p['terminals'][1],'VSS' if i<code else 'VDD')
                self.assertEqual(clear['terminals'][1],p['terminals'][1])
                self.assertEqual(clear['terminals'][2:],['VSS','VSS'])

    def test_each_capacitor_node_is_stress_checked(self):
        _,devices=bank.circuit('mim2x2',0,31)
        names=['v(vdd)','v(xd.r0)']+[f'v(xd.cap{i})' for i in range(31)]
        wave=np.ones((3,len(names)))*1.8
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'0';folder.mkdir()
            (root/'manifest.json').write_text(json.dumps(dict(tasks=[dict(id='0',devices=devices)])))
            with patch.object(probe,'original_measure',return_value=dict(qualified_phy=False)), \
                 patch.object(probe.h,'read_raw',return_value=(names,wave)):
                good=probe.measure(folder)
                self.assertTrue(good['custom_mos_stress_passed'])
                self.assertEqual(len(good['custom_mos_stress']),93)
                for i in range(31):
                    wave[:,2+i]=2.1
                    bad=probe.measure(folder)
                    self.assertFalse(bad['custom_mos_stress_passed'])
                    self.assertFalse(bad['custom_mos_stress'][3*i]['passed'])
                    wave[:,2+i]=1.8

    def test_unknown_geometry_and_invalid_codes_rejected(self):
        with self.assertRaises(ValueError):bank.circuit('undeclared',0,0)
        for c,f in [(-1,0),(16,0),(0,32)]:
            with self.assertRaises(ValueError):bank.circuit('mim2x2',c,f)
