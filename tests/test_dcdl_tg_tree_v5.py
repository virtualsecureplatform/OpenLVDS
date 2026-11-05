# SPDX-License-Identifier: GPL-3.0-only
from collections import Counter
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import dcdl_tg_tree_v5 as tg


class NativeTGTreeTests(unittest.TestCase):
    def test_all_coarse_words_activate_one_path_per_group_at_equal_depth(self):
        for coarse in (16, 32, 64, 128, 256):
            cells = tg.instances(coarse=coarse)
            depths = []
            for code in range(coarse):
                logic = {f'S{i}': (code >> i) & 1 for i in range(coarse.bit_length()-1)}
                logic.update({f'E{i}': 0 for i in range(31)})
                values = {f'tap{i}': (i, 0) for i in range(coarse)}
                active = Counter()
                for cell in cells:
                    p = cell['pins']; model = cell['model']; tag = cell['name']
                    if tag.startswith(('select_', 'decode', 'fine_buffer', 'fine_inverse')):
                        if model.endswith('buf_4') or model.endswith('buf_1'):
                            logic[p['X']] = logic[p['A']]
                        elif model.endswith('inv_4') or model.endswith('inv_1'):
                            logic[p['Y']] = 1-logic[p['A']]
                        elif model.endswith('and2_4'):
                            logic[p['X']] = logic[p['A']] & logic[p['B']]
                        else:
                            self.fail('Unknown static decoder primitive')
                    if tag.startswith('switch'):
                        self.assertEqual(logic[p['ENB']], 1-logic[p['EN']])
                        if logic[p['EN']]:
                            active[tag.rsplit('_', 1)[0]] += 1
                            tap, depth = values[p['A']]
                            values[p['Z']] = (tap, depth+1)
                self.assertEqual(set(active.values()), {1})
                self.assertEqual(len(active), sum(l['groups'] for l in tg.levels(coarse)))
                self.assertEqual(values['selected'][0], code)
                depths.append(values['selected'][1])
                for node, value in tg.control_targets(code, 0, coarse).items():
                    self.assertEqual(logic[node], value)
            self.assertEqual(set(depths), {len(tg.levels(coarse))})

    def test_tg_devices_include_both_channel_types_bodies_and_nonzero_junctions(self):
        for profile in tg.PROFILES:
            source = tg.tg_source(profile)
            definitions = tg.dimensions.native.definitions(source)
            ports, body = definitions[tg.tg_name(profile)]
            self.assertEqual(ports, ['A', 'Z', 'EN', 'ENB', 'VPWR', 'VGND'])
            self.assertEqual(len(body), 2)
            self.assertEqual(body[0][1:5], ['A', 'EN', 'Z', 'VGND'])
            self.assertEqual(body[1][1:5], ['Z', 'ENB', 'A', 'VPWR'])
            for words in body:
                params = dict(token.split('=') for token in words[6:])
                self.assertTrue(all(float(params[k]) > 0 for k in ('ad', 'as', 'pd', 'ps')))

    def test_fine_loading_is_separate_from_the_selector_and_polarity_is_preserved(self):
        for profile in tg.PROFILES:
            cells = tg.instances(profile)
            inv = [c for c in cells if c['model'] == tg.INVERTER]
            self.assertEqual({c['name'] for c in inv}, {'input_inverse', 'fine_driver'})
            driver = next(c for c in cells if c['name'] == 'fine_driver')
            fine = [c for c in cells if c['model'] == tg.FINE]
            self.assertEqual(len(fine), 31)
            self.assertTrue(all(c['pins']['NODE'] == driver['pins']['Y'] for c in fine))
            self.assertNotEqual(driver['pins']['A'], driver['pins']['Y'])
            self.assertEqual(driver['pins']['A'], 'selected')
            self.assertEqual(any(c['name'] == 'output_buffer' for c in cells), not profile.endswith('_direct'))
            self.assertEqual(next(c for c in cells if c['name'] == 'tail_load')['pins']['A'], 'tap15')

    def test_invalid_profiles_and_dimensions_are_rejected(self):
        for profile in ('unknown', ''):
            with self.assertRaises(ValueError):
                tg.instances(profile)
        for coarse, fine in ((8, 32), (16, 64)):
            with self.assertRaises(ValueError):
                tg.instances(coarse=coarse, fine_count=fine)


if __name__ == '__main__':
    unittest.main()
