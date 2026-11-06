# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import json,re
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_strong_storage_counter_shared_rc_v232 as p


class StrongStorageCounterReplay(unittest.TestCase):
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

    def test_native_schematic_expansion_keeps_loads_and_all_612_terminal_probes(self):
        parent=p.ROOT/'build/diagnostics/counter_native_repairs_v183/15c6a8caf6163935';qualified=p.ROOT/'build/diagnostics/repaired_clock_counter_rc_v193/8c480900e695a872'
        if not (qualified/'summary.json').exists():self.skipTest('requires retained complete actual counter RC')
        import test_strong_storage_counter_v230 as design
        _,counter_cells,macros=design.StrongStorageCounterTopology().material()
        source=p.rc.physical.original.source(counter_cells,macros)
        import native_bank_inventory_v51 as inventory
        _,leaves=inventory.native_leaves(source,p.rc.NAME)
        rows=['.subckt '+p.rc.NAME+' '+' '.join(p.PORTS)]
        for d in leaves:
            nodes=[n.removeprefix('native____') for n in d['nodes']]
            rows.append(' '.join(['X'+d['name'],*nodes,d['model'],*[k+'='+v for k,v in d['params'].items()]]))
        block='\n'.join(rows+['.ends','']);oldcells=(parent/'cells.spice').read_text();oldmodule=(parent/'pair.spice').read_text()
        cells,module=p.libraries(oldcells,oldmodule,block);self.assertEqual(cells,oldcells+'\n'+block)
        previous=json.loads((parent/'manifest.json').read_text())['identity']['devices'];devices=p.observations(cells,module,previous);self.assertEqual(len(devices),612)
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

    def test_actual_fresh_distributed_rc_observes_all_612_mos_with_original_loads(self):
        qualified=p.ROOT/'build/diagnostics/strong_storage_counter_rc_v231/27f229d3dc27ee16'
        source=p.ROOT/'build/diagnostics/counter_native_repairs_v183/15c6a8caf6163935'
        if not (qualified/'summary.json').exists():self.skipTest('requires complete actual strong-storage distributed RC')
        report=json.loads((qualified/'summary.json').read_text());self.assertTrue(report['strong_storage_counter_shared_wire_rc_qualified'])
        path=p.ROOT/report['extraction']['netlist'];self.assertEqual(p.sha(path),report['extraction']['netlist_sha256'])
        cells,module=p.libraries((source/'cells.spice').read_text(),(source/'pair.spice').read_text(),path.read_text())
        previous=json.loads((source/'manifest.json').read_text())['identity']['devices'];devices=p.observations(cells,module,previous)
        self.assertEqual(len(devices),612);self.assertEqual(len([d for d in devices if d['name'].startswith('XD:XR:')]),548)
        deck=p.fixture(Path('/work/OpenLVDS/build/example'),p.specifications()[0],devices)
        for d in devices:
            for node in d['terminals']:
                if node!='0':self.assertIn('V('+node+')',deck)


if __name__=='__main__':unittest.main()
