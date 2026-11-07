# SPDX-License-Identifier: GPL-3.0-only
"""Guard real shared wires, unchanged native loads and complete boundary coverage."""
from pathlib import Path
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
try:
    import probe_local_setter_shared_rc_v351 as p
except ModuleNotFoundError as error:
    if error.name not in ('klayout','numpy'):raise
    p=None


@unittest.skipIf(p is None,'requires project counter-physical Python with NumPy and KLayout')
class SharedShuntedCounterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_cells=(p.BASELINE/'cells.spice').read_text()
        cls.original_module=(p.BASELINE/'pair.spice').read_text()
        cls.old=json.loads((p.BASELINE/'manifest.json').read_text())['identity']
        rc=ROOT/'build/diagnostics/shunted_counter_rc_v350/b68f93094c2a579a'
        report=json.loads((rc/'summary.json').read_text())
        cls.block=(ROOT/report['extraction']['netlist']).read_text()
        cls.cells,cls.module=p.libraries(cls.original_cells,cls.original_module,cls.block)
        cls.devices=p.observations(cls.cells,cls.module,cls.old['devices'][p.VARIANT])

    def test_actual_rc_has_all_808_separated_native_maps_and_original_64_loads(self):
        self.assertEqual(len(self.devices),808)
        self.assertEqual(sum(d['name'].startswith('XD:XR:') for d in self.devices),744)
        before=p.native.definitions(self.original_module)[p.HARNESS][1]
        after=p.native.definitions(self.module)[p.HARNESS][1]
        self.assertEqual(after[1:],before[1:])
        self.assertEqual(after[0],['XR',*p.PORTS,p.rc.NAME])
        inventory=p.rc.physical.material.legacy.inventory
        _,expected=inventory.native_leaves(p.rc.collapse(self.original_cells+self.original_module),p.HARNESS)
        _,actual=inventory.native_leaves(p.rc.collapse(self.cells+self.module),p.HARNESS)
        proof=inventory.compare_parameters(expected,actual)
        self.assertTrue(proof['all_reference_supplied_junctions_preserved'])
        self.assertEqual(proof['native_primitives'],865)

    def test_omitted_actual_wire_or_internal_monitor_is_rejected(self):
        lines=self.block.splitlines(keepends=True)
        at=next(k for k,line in enumerate(lines) if line[:1].upper()=='R')
        with self.assertRaisesRegex(ValueError,'actual reduced shared wires'):
            p.libraries(self.original_cells,self.original_module,''.join(lines[:at]+lines[at+1:]))
        changed='\n'.join(' '.join('missing_low0' if w=='low0' else w for w in line.split())
                          for line in self.block.splitlines())
        with self.assertRaisesRegex(ValueError,'named monitors'):
            p.libraries(self.original_cells,self.original_module,changed)

    def test_all_twelve_specs_are_fresh_with_worst_hot_boundaries_first(self):
        specs=p.specifications();old=p.source.specifications()
        key=lambda s:json.dumps(s,sort_keys=True)
        self.assertEqual(sorted(map(key,specs)),sorted(map(key,old)))
        self.assertEqual(specs[:2],[old[11],old[6]])
        tasks=p.tasks(ROOT/'build/unused-v351-fixture-test',self.devices)
        self.assertEqual(len(tasks),12)
        self.assertTrue(all(t['mode']=='simulate' for t in tasks))
        self.assertEqual({s['duty'] for s in specs},{.4,.5,.6})

    def test_full_original_native_fixture_saves_every_actual_terminal(self):
        text=p.fixture(ROOT/'build/unused-v351-fixture-test',p.specifications()[0],self.devices)
        self.assertIn('.tran 1p 26n 0 1p',text)
        self.assertIn('VDD VDD 0 1.8',text)
        self.assertIn('20.99n 1.8 21.01n 0 22.99n 0 23.01n 1.8',text)
        printed={w[2:-1] for line in text.splitlines() if line.startswith('.print tran ')
                 for w in line.split()[2:] if w.startswith('V(') and w.endswith(')')}
        required={node for d in self.devices for node in d['terminals'] if node!='0'}
        self.assertEqual(sorted(required-printed),[])


if __name__=='__main__':unittest.main()
