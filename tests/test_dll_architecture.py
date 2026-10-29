# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dll_design as design
from layout import circuits,flatten
from spice_scope import closure_hash
from dll_campaign import closure,bias_reference_count
from dll_measurements import read_wave,average

ROOT=Path(__file__).resolve().parents[1]
class DLLArchitecture(unittest.TestCase):
    base=(ROOT/'analog/openlvds.spice').read_text()
    monitor=(ROOT/'analog/experiments/phase_area.spice').read_text()
    def test_ota_really_removes_the_pump_and_replica(self):
        for name in design.OTA_VARIANTS:
            source=design.candidate_source(self.base,name,self.monitor);defs=circuits(source)
            ports,rows=defs['openlvds_dll_analog'];instances={r[0] for r in rows}
            self.assertEqual(ports,design.ANALOG_PORTS)
            self.assertTrue({'XAREA','XOTA','XON','XOP','XRP1'}<=instances)
            self.assertTrue({'XVCOPY','XCPU','XCPD','XCUDUMP','XCDDUMP'}.isdisjoint(instances))
            flat=design.native_block(source,'openlvds_dll_analog')
            self.assertNotIn('openlvds_dll_analog__VCOPY',flat)
            self.assertEqual(defs['openlvds_dll_core'][0],circuits(self.base)['openlvds_dll_core'][0])
            self.assertEqual(defs['lvds_pfd'][0],design.PFD_PORTS)
            self.assertEqual(closure_hash(source,'openlvds_dll_core'),closure_hash(closure(source,['openlvds_dll_core']),'openlvds_dll_core'))
    def test_charge_pump_path_keeps_main_and_dump_branches(self):
        for name in design.CP_VARIANTS:
            defs=circuits(design.candidate_source(self.base,name,self.monitor))
            rows={r[0]:r for r in defs['openlvds_dll_analog'][1]}
            self.assertTrue({'XVCOPY','XCPU','XCPD','XCUDUMP','XCDDUMP'}<=set(rows))
            self.assertNotIn('XOTA',rows)
            self.assertEqual(rows['XVCOPY'][1],['CTRL','VCOPY','NC','VDDD','VSS'])
            ports,devices=flatten(defs,'openlvds_dll_analog')
            for d in devices:
                if 'fet_' in d['model']:self.assertLessEqual(float(d['params']['w']),8)
    def test_ota_output_devices_use_digital_rails(self):
        defs=circuits(design.ota_block(4));rows={r[0]:r for r in defs['lvds_phase_ota'][1]}
        self.assertEqual(rows['XPO'][1][2:],['VDDD','VDDD'])
        self.assertEqual(rows['XNO'][1][2:],['VSS','VSS'])
        self.assertEqual(rows['XPL'][1][1],'DF')
        self.assertEqual(rows['XPR'][1][1],'UF')
    def test_standalone_dll_fixture_cannot_duplicate_wrapper_bias(self):
        lib=""".subckt lvds_bias PB NB VP VN
.ends lvds_bias
.subckt wrapper PB NB VP VN
XB PB NB VP VN lvds_bias
.ends wrapper
"""
        self.assertEqual(bias_reference_count('XD PB NB VP VN wrapper',lib),1)
        self.assertEqual(bias_reference_count('XD PB NB VP VN wrapper\nXB PB NB VP VN lvds_bias',lib),2)

    def test_time_average_is_not_sample_count_weighted(self):
        self.assertAlmostEqual(average(np.array([0.,1.,10.]),np.array([0.,1.,1.])),.95)

if __name__=='__main__':unittest.main()
