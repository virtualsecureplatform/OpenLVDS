# SPDX-License-Identifier: GPL-3.0-only
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from dll_design import candidate_source
from layout import circuits,flatten
from layout_dll_candidate import partition as outer
from layout_local_delay import partition

ROOT=Path(__file__).resolve().parents[1]


class LocalDelayPartition(unittest.TestCase):
    def fixture(self):
        source=candidate_source((ROOT/'analog/openlvds.spice').read_text(),'ota_w8_c4',
                                (ROOT/'analog/experiments/phase_area.spice').read_text())
        ports,devices=flatten(circuits(source),'openlvds_dll_analog')
        core,_,ports,_,_=outer(devices,ports)
        return core,ports

    def test_all_delay_internal_nodes_remain_local(self):
        devices,ports=self.fixture();groups,public,shared=partition(devices,ports)
        self.assertEqual(sum(map(len,groups.values())),len(devices))
        self.assertEqual(len({d['name'] for g in groups.values() for d in g}),len(devices))
        for name in ['delay0','delay1','delay2','delay3','replica']:
            self.assertEqual(len(groups[name]),30)
            self.assertTrue(set(public[name])<=set(ports)|{'openlvds_dll_analog__CTRL'})
        self.assertIn('openlvds_dll_analog__CTRL',shared)

    def test_missing_stage_is_rejected(self):
        devices,ports=self.fixture()
        devices=[d for d in devices if '__XL__X2__' not in d['name']]
        with self.assertRaisesRegex(ValueError,'five delay sections'):partition(devices,ports)

    def test_mismatched_section_device_geometry_is_rejected(self):
        devices,ports=self.fixture();devices=copy.deepcopy(devices)
        device=next(d for d in devices if '__XL__X3__' in d['name'])
        device['params']['w']=str(float(device['params']['w'])*2)
        with self.assertRaisesRegex(ValueError,'geometries differ'):partition(devices,ports)
