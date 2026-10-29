# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from dll_design import candidate_source
from layout import circuits,flatten
from layout_dll_candidate import partition
from physical_policy import pfd_area_paths_retained

ROOT=Path(__file__).resolve().parents[1]
class DLLPhysical(unittest.TestCase):
    def test_monitor_split_keeps_fast_signals_in_control_island(self):
        base=(ROOT/'analog/openlvds.spice').read_text();monitor=(ROOT/'analog/experiments/phase_area.spice').read_text()
        for name in ['ota_w4_c8','cp_b2_c4']:
            source=candidate_source(base,name,monitor)
            ports,devices=flatten(circuits(source),'openlvds_dll_analog')
            core,quiet,cp,qp,shared=partition(devices,ports)
            self.assertEqual(len(core)+len(quiet),len(devices))
            self.assertTrue(set(cp)&set(qp)==set(shared))
            self.assertTrue({'CLK','PH0','PH90','UP','DN'}.isdisjoint(shared))
            self.assertIn('openlvds_dll_analog__UF',shared)
            self.assertIn('openlvds_dll_analog__DF',shared)
            self.assertEqual(sum(d['name'].endswith('__XRU') for d in core),1)
            self.assertTrue(all('__XAREA__' in d['name'] for d in quiet))
    def test_area_pfd_rejects_clock_and_output_bypasses(self):
        source=(ROOT/'sky130/experiments/lvds_pfd_area.v').read_text()
        self.assertTrue(pfd_area_paths_retained(source))
        for old,new in [('.CLK(REF)','.CLK(FB)'),('.RESET_B(clear_b)','.RESET_B(RESET_N)'),('buf_8 dn_drive','buf_4 dn_drive'),
                        ('.A(UP),.B(DN)','.A(raw_up),.B(raw_dn)')]:
            self.assertFalse(pfd_area_paths_retained(source.replace(old,new)))

if __name__=='__main__':unittest.main()
