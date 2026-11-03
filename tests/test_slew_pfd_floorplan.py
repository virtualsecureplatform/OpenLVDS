from copy import deepcopy
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import slew_pfd_floorplan as floorplan


class SlewPFDFloorplan(unittest.TestCase):
    def baseline(self):
        rows = '\n'.join(f'ROW ROW_{i} unithd 5520 {10880+i*2720} {"N" if i%2 == 0 else "FS"} DO 193 BY 1 STEP 460 0 ;' for i in range(20))
        pins = '\n'.join(f'- {name} + NET {name} + DIRECTION INPUT + USE SIGNAL\n + PORT + LAYER met3 ( -300 -300 ) ( 300 300 )\n + PLACED ( 300 {47940+i*1360} ) N ;' for i, name in enumerate(('REF', 'FB')))
        return 'VERSION 5.8 ;\nDESIGN lvds_pfd ;\nUNITS DISTANCE MICRONS 1000 ;\n' + rows + '\nCOMPONENTS 0 ;\nEND COMPONENTS\nPINS 2 ;\n' + pins + '\nEND PINS\nEND DESIGN\n'

    def final(self, target):
        masters = {name: p['master'] for p in target['pairs'] for name in (p['first'], p['second'])}
        masters.update(clear='sky130_fd_sc_hd__a22oi_4', reset_disable='sky130_fd_sc_hd__nand2_1')
        cells = []
        for name, entry in target['manual_global_placements'].items():
            x, y = (round(v*target['dbu_per_um']) for v in entry['location'])
            cells.append(f'- {name} {masters[name]} + PLACED ( {x} {y} ) {entry["orientation"]} ;')
        return target['pin_template'].replace('COMPONENTS 0 ;\nEND COMPONENTS', f'COMPONENTS {len(cells)} ;\n' + '\n'.join(cells) + '\nEND COMPONENTS')

    def test_all_variants_use_translated_legal_rows_and_equal_external_pin_shapes(self):
        for variant in ('clkbuf_4', 'clkbuf_8', 'nor3_inv4', 'nor4_inv4'):
            target = floorplan.plan(self.baseline(), variant)
            self.assertEqual(target['translation_dbu'], [0, 21760])
            for pair in target['pairs']:
                a, b = (target['manual_global_placements'][pair[n]] for n in ('first', 'second'))
                self.assertEqual(a['location'][0], b['location'][0]); self.assertAlmostEqual(b['location'][1]-a['location'][1], 21.76)
                self.assertEqual(a['orientation'], b['orientation'])
            report = floorplan.check(self.final(target), target)
            self.assertTrue(report['placement_matched'])
            self.assertFalse(report['route_matching_verified']); self.assertFalse(report['physical_admission'])

    def test_legalizer_movement_wrong_master_orientation_and_pin_changes_are_rejected(self):
        target = floorplan.plan(self.baseline(), 'nor4_inv4'); good = self.final(target)
        for name in ('fb_condition', 'fb_restore', 'fb_ff', 'dn_drive'):
            pattern = r'(- ' + name + r' \S+ \+ PLACED \( )(\d+)( \d+ \) \w+ ;)'
            bad = re.sub(pattern, lambda m: m[1]+str(int(m[2])+1)+m[3], good)
            self.assertNotEqual(bad, good); self.assertFalse(floorplan.check(bad, target)['placement_matched'])
        for bad in [good.replace('- fb_condition sky130_fd_sc_hd__nor4_1', '- fb_condition sky130_fd_sc_hd__nor3_1'),
                    re.sub(r'(- fb_ff[^;]+\) )N', r'\1FS', good),
                    good.replace('+ PLACED ( 300 55760 ) N', '+ PLACED ( 300 55761 ) N'),
                    good.replace('+ LAYER met3', '+ LAYER met2'),
                    re.sub(r'(?m)^- fb_ff[^\n]+\n', '', good)]:
            self.assertNotEqual(bad, good); self.assertFalse(floorplan.check(bad, target)['placement_matched'])

    def test_changed_units_irregular_or_narrow_rows_and_missing_pins_fail(self):
        base = self.baseline()
        for bad in [base.replace('UNITS DISTANCE MICRONS 1000 ;', ''),
                    base.replace('DO 193', 'DO 100'), base.replace(' 13600 FS ', ' 13601 FS '),
                    base.replace('- REF + NET REF', '- OTHER + NET OTHER'),
                    base.replace('ROW ROW_16 unithd 5520 54400 N', 'ROW ROW_16 unithd 5520 54400 FS')]:
            with self.assertRaises(ValueError): floorplan.plan(bad, 'clkbuf_4')
        target = floorplan.plan(base, 'clkbuf_4')
        with self.assertRaises(ValueError): floorplan.check(self.final(target).replace('MICRONS 1000', 'MICRONS 2000'), target)

    def test_configuration_preserves_named_cells_and_disables_topology_changing_repairs(self):
        target = floorplan.plan(self.baseline(), 'nor3_inv4')
        base = dict(DESIGN_NAME='lvds_pfd', SYNTH_ELABORATE_ONLY=True, DIE_AREA=[0,0,100,100])
        before = deepcopy(base)
        cfg = floorplan.configuration(base, target, source='candidate.v', blackboxes='blackboxes.v', shared_models='shared.v', sdc='pfd.sdc', template='pins.def')
        self.assertEqual(base, before)
        self.assertEqual(cfg['FP_TEMPLATE_MATCH_MODE'], 'strict')
        for name in target['manual_global_placements']: self.assertIn(name, cfg['RSZ_DONT_TOUCH_LIST'])
        for name in ['ref_mid', 'fb_mid', 'REF', 'FB']: self.assertIn(name, cfg['RSZ_DONT_TOUCH_LIST'])
        for name in ['RUN_CTS', 'RUN_POST_GPL_DESIGN_REPAIR', 'RUN_POST_GRT_DESIGN_REPAIR', 'DESIGN_REPAIR_BUFFER_INPUT_PORTS', 'DESIGN_REPAIR_BUFFER_OUTPUT_PORTS']:
            self.assertFalse(cfg[name])
        with self.assertRaises(ValueError): floorplan.configuration({}, target, source='a', blackboxes='b', shared_models='c', sdc='d', template='e')
