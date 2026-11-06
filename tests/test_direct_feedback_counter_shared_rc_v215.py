# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import json,re
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_direct_feedback_counter_shared_rc_v215 as p


class DirectFeedbackCounterReplay(unittest.TestCase):
    def test_complete_endpoint_matrix_and_original_numeric_gates_required(self):
        specs=p.specifications();self.assertEqual(len(specs),12)
        self.assertEqual({(s['temperature'],s['duty'],s['stop_level']) for s in specs},{(t,d,l) for t in (0,40) for d in (.4,.5,.6) for l in (0,1)})
        self.assertEqual({s['process'] for s in specs},{'ss'});self.assertEqual({s['mhz'] for s in specs},{410})
        rows=[dict(task=dict(spec=s),error=None,result=dict(counter_feasibility_passed=True,minimum_clock_low_voltage_margin_v=.1,counter_shared_wire_rc_qualified=True)) for s in specs]
        self.assertTrue(p.assess(rows)['actual_shared_counter_timing_pilot_passed'])
        for value in (-.01,float('nan'),float('inf')):
            changed=deepcopy(rows);changed[0]['result']['minimum_clock_low_voltage_margin_v']=value
            self.assertFalse(p.assess(changed)['actual_shared_counter_timing_pilot_passed'])
        for key in ('counter_feasibility_passed','counter_shared_wire_rc_qualified'):
            changed=deepcopy(rows);changed[0]['result'][key]=False
            self.assertFalse(p.assess(changed)['actual_shared_counter_timing_pilot_passed'])
        self.assertIsNone(p.assess(rows[:-1]));changed=deepcopy(rows);changed[0]['task']['spec']=changed[1]['task']['spec']
        with self.assertRaises(ValueError):p.assess(changed)
        for key in ('all_pvt_covered','whole_clock_rc_qualified','hardware_warmup_qualified','electrical_qualification_passed','qualified_phy'):self.assertFalse(p.assess(rows)[key])

    def test_actual_rc_body_loads_and_all_510_native_terminal_probes_retained(self):
        parent=p.ROOT/'build/diagnostics/counter_native_repairs_v183/15c6a8caf6163935';qualified=p.ROOT/'build/diagnostics/repaired_clock_counter_rc_v193/8c480900e695a872'
        if not (qualified/'summary.json').exists():self.skipTest('requires retained complete actual counter RC')
        r=json.loads((qualified/'summary.json').read_text());block=(p.ROOT/r['extraction']['netlist']).read_text();oldcells=(parent/'cells.spice').read_text();oldmodule=(parent/'pair.spice').read_text()
        cells,module=p.libraries(oldcells,oldmodule,block);self.assertEqual(cells,oldcells+'\n'+block)
        previous=json.loads((parent/'manifest.json').read_text())['identity']['devices'];devices=p.observations(cells,module,previous);self.assertEqual(len(devices),510)
        rows=p.native.definitions(module)[p.HARNESS][1];self.assertEqual([w[0] for w in rows],['XR',*p.LOADS,'Cmask_load'])
        self.assertEqual(rows[0],['XR',*p.PORTS,p.rc.NAME])
        deck=p.fixture(Path('/work/OpenLVDS/build/example'),p.specifications()[0],devices)
        self.assertIn('.tran 1p 26n',deck)
        for n in p.MONITORS:self.assertIn('V(XD:XR:'+n+')',deck)
        for d in devices:
            for n in d['terminals']:
                if n!='0':self.assertIn('V('+n+')',deck)
        with self.assertRaisesRegex(ValueError,'monitor'):p.libraries(oldcells,oldmodule,re.sub(r'(?<!\S)low0(?!\S)','missing_low0',block))
        with self.assertRaises(ValueError):p.libraries(oldcells,oldmodule.replace('Cmask_load mask_load VGND 20f','Cmask_load mask_load VGND 10f'),block)


if __name__=='__main__':unittest.main()
