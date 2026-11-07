"""Check real counter escape masks and deliberate different-net contacts."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import plan_counter_buffer_escapes_v328 as planner


class NativeBufferEscapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.identity=json.loads((planner.PARENT/'manifest.json').read_text())['identity']
        cls.proposed=planner.routes(cls.identity)

    def test_actual_masks_and_global_bus_shapes_have_no_foreign_contacts(self):
        self.assertEqual(planner.different_net_overlaps(self.proposed['shapes']),[])
        report=planner.native_mask_check(self.identity,self.proposed)
        self.assertEqual(report['native_component_instances'],22)
        self.assertEqual(report['foreign_native_m4_m5_contacts'],0)
        self.assertGreater(report['buffer_shape_native_layer_checks'],100)

    def test_old_same_row_escapes_reproduce_eight_different_net_contacts(self):
        shapes=[];i=self.identity;cells={c['name']:c for c in i['cells']}
        for net,ends in i['plan']['points'].items():
            for end in ends:
                if end['cell'] not in planner.ROLES or end['pin'] not in ('A','X'):continue
                c=cells[end['cell']];port=i['macros'][c['model']]['row']['ports'][end['pin']]
                pos=i['plan']['placements'][end['cell']];a=(pos['x']+port['x_um'],pos['y']+port['y_um'])
                shapes.append(dict(net=net,layer='metal4',rect=planner.rect(a,(end['x'],a[1]),.3)))
        self.assertEqual(len(planner.different_net_overlaps(shapes)),8)

    def test_input_route_into_native_interstage_wire_is_rejected(self):
        i=self.identity;p=i['plan']['placements']['request_driver'];bad=deepcopy(self.proposed)
        bad['buffer_shapes'].append(dict(net='REQUEST',layer='metal4',cell='request_driver',
            kind='injected_internal_short',rect=[p['x']+13.8,p['y']+22.7,p['x']+14.3,p['y']+23.1]))
        with self.assertRaisesRegex(ValueError,'foreign native metal4'):
            planner.native_mask_check(i,bad)

    def test_output_route_into_global_rclk_bus_is_rejected(self):
        shapes=deepcopy(self.proposed['shapes'])
        bus=next(s for s in shapes if s['kind']=='global_bus' and s['net']=='RCLK')
        bad=dict(bus,net='request_i',kind='injected_global_bus_short');shapes.append(bad)
        self.assertTrue(planner.different_net_overlaps(shapes))


if __name__=='__main__':
    unittest.main()
