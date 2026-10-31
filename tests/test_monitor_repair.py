# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from dll_design import candidate_source
from layout import circuits,flatten
from layout_dll_candidate import partition
from repair_dll_monitor import repaired_source,loaded_block

ROOT=Path(__file__).resolve().parents[1]


class MonitorRepair(unittest.TestCase):
    def source(self):
        return candidate_source((ROOT/'analog/openlvds.spice').read_text(),'ota_w8_c4',
                                (ROOT/'analog/experiments/phase_area.spice').read_text())

    def test_resistor_ratios_and_nominal_averaging_time_constant_are_preserved(self):
        source=self.source();before=circuits(source);after=circuits(repaired_source(source))
        old={row[0]:row for row in before['lvds_phase_area'][1]}
        new={row[0]:row for row in after['lvds_phase_area'][1]}
        for name,row in old.items():
            if row[2]=='sky130_fd_pr__res_high_po_0p35':
                self.assertEqual(float(new[name][3]['l'])*4,float(row[3]['l']))
                self.assertEqual(row[1],new[name][1])
        for cap,resistor in [('XCU','XRU'),('XCD','XRD')]:
            old_area=float(old[cap][3]['w'])*float(old[cap][3]['l'])
            area=sum(float(row[3]['w'])*float(row[3]['l']) for name,row in new.items() if name.startswith(cap+'_'))
            self.assertEqual(area,4*old_area)
            self.assertEqual(float(new[resistor][3]['l'])*area,float(old[resistor][3]['l'])*old_area)
        self.assertEqual(before['lvds_phase_ota'],after['lvds_phase_ota'])
        self.assertEqual(before['openlvds_dll_analog'],after['openlvds_dll_analog'])

    def test_current_scaling_preserves_comparator_ratios_and_logic_load(self):
        source=self.source();before=circuits(source);after=circuits(repaired_source(source))
        old={row[0]:row for row in before['lvds_area_compare'][1]}
        for name,nodes,model,params in after['lvds_area_compare'][1]:
            factor=4 if name in ['XTAIL','XP','XM','XNL','XNR'] else 1
            if 'w' in params:self.assertEqual(float(params['w']),float(old[name][3]['w'])*factor)
            self.assertEqual(nodes,old[name][1]);self.assertEqual(model,old[name][2])

    def test_replicated_filter_capacitors_stay_in_the_control_island(self):
        ports,devices=flatten(circuits(repaired_source(self.source())),'openlvds_dll_analog')
        core,quiet,_,_,shared=partition(devices,ports)
        self.assertEqual(sum('__XAREA__XCU_' in d['name'] or '__XAREA__XCD_' in d['name'] for d in core),8)
        self.assertFalse(any('__XAREA__XCU_' in d['name'] or '__XAREA__XCD_' in d['name'] for d in quiet))
        self.assertTrue({'CLK','PH0','PH90','UP','DN'}.isdisjoint(shared))

    def test_captured_loading_maps_wire_segments_without_adding_false_shorts(self):
        source='.subckt openlvds_dll_analog A B VSS\nXR A B VSS sky130_fd_pr__res_high_po_0p35 w=.35 l=8.5\n.ends openlvds_dll_analog\n'
        caps='C0 dll_control_island.A.t1 dll_monitor_island.B.t2 10f\nC1 A.t0 ghost 20f\nC2 ghost_a ghost_b 30f\nC3 A.t0 A.t1 1f\n'
        text,info=loaded_block(source,caps)
        self.assertEqual(info['counts'],dict(both_mapped=2,one_grounded=1,unmapped=1,same_node=1))
        self.assertAlmostEqual(info['capacitances_f']['a'],30e-15)
        self.assertAlmostEqual(info['capacitances_f']['b'],10e-15)
        self.assertEqual(sum(line.startswith('CPROXY') for line in text.splitlines()),2)
