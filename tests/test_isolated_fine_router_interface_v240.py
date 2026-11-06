# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
from copy import deepcopy
import json
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
try:
    import klayout.db
except ImportError:
    CAD=False
else:
    CAD=True

@unittest.skipUnless(CAD,'KLayout required by placement binder')
class IsolatedRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import prepare_isolated_fine_routing_interface_v240 as producer
        import isolated_fine_bank_physical_v239 as design
        cls.producer=producer
        base=producer.placement.BASE;views=producer.placement.VIEWS
        old=json.loads((base/'manifest.json').read_text())['identity']
        records={**old['records'],**json.loads((views/'summary.json').read_text())['cells']}
        g=design.graph(old['graph']);cls.i=dict(graph=g,plan=design.placement(old['plan'],g,records))

    def test_fine_bus_and_selected_driver_are_separate(self):
        c=self.producer.contract(self.i)
        bus=c['buses'][0]
        self.assertEqual(bus['net'],'fine_node')
        self.assertEqual(bus['proxy'],'__fixed_bus_fine_node')
        self.assertEqual(len(bus['terminals']),32)
        self.assertIn(('u_fine_regenerate','A'),bus['terminals'])
        self.assertNotIn(('u_fine_isolate','A'),bus['terminals'])
        self.assertIn('selected',c['regular_wire_nets'])
        self.assertIn('fine_node',c['regular_wire_nets'])
        self.assertEqual(len(c['root_outputs']),8)
        with tempfile.TemporaryDirectory() as tmp:
            text=self.producer.adapter(Path(tmp),Path(tmp),c)
            self.assertIn('__fixed_bus_fine_node',text)
            self.assertNotIn('__fixed_bus_selected',text)
            self.assertEqual(text.count('$term disconnect'),95) # 94 fixed rails + one nonrouting-pin loop

    def test_driver_input_bypassing_isolation_is_rejected(self):
        i=deepcopy(self.i)
        next(c for c in i['plan']['cells'] if c['name']=='u_fine_isolate')['pins']['A']='fine_node'
        with self.assertRaisesRegex(ValueError,'eight roots and one driver'):
            self.producer.contract(i)

    def test_fine_unit_on_selected_bus_is_rejected(self):
        i=deepcopy(self.i)
        next(c for c in i['plan']['cells'] if c['name']=='u_fine_unit0')['pins']['A']='selected'
        with self.assertRaisesRegex(ValueError,'terminal differs'):
            self.producer.contract(i)

if __name__=='__main__':unittest.main()
