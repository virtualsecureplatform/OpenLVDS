import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import extend_rx_aperture as extension


class ExtendedAperture(unittest.TestCase):
    def setUp(self):
        self.req = json.loads((extension.ROOT / 'requirements.json').read_text())
        self.spec = dict(process='ss', temperature=40, edge='rising', polarity='rise',
                         clock_slew_ps=250, data_slew_ps=250, kind='setup')
        self.manifest = dict(identity=dict(model=dict(ports='VGND VPWR clk data[0] data[1] reset_n serial valid'.split())))

    def test_original_matrix_is_retained_and_only_600_conditions_are_new(self):
        conditions = extension.conditions(self.req); fresh = extension.fresh_conditions(self.req)
        ids = lambda rows: {extension.capture.condition_id(s) for s in rows}
        self.assertEqual(len(conditions), 1080); self.assertEqual(len(ids(conditions)), 1080)
        self.assertEqual(len(fresh), 600)
        self.assertEqual(ids(conditions) - ids(fresh), ids(extension.capture.conditions(self.req)))
        for p in self.req['process_corners']:
            for t in self.req['temperatures_c']:
                self.assertEqual(sum(s['process'] == p and s['temperature'] == t for s in fresh), 40)

    def test_extended_deck_retains_publication_load_supply_and_native_fixture(self):
        with patch.dict(os.environ, PDK_ROOT='/pdk'):
            deck = extension.expected_deck(Path('/captured'), self.manifest, self.spec, 400)
        body, timing = extension.capture.fixture(self.spec, 400, self.manifest['identity']['model']['ports'])
        self.assertIn(body, deck); self.assertIn('C0 Q0 0 20f', deck)
        self.assertIn('VD VDDD 0 1.8', deck); self.assertIn('.options device temp=40', deck)
        self.assertIn(f'.tran 5p {timing["stop_ns"]:.12g}n 0 5p', deck)
        self.assertIn('.include "/captured/library.spice"', deck)

    def witness_fixture(self, root):
        folder = root / extension.capture.condition_id(self.spec) / 'point_400p000000'
        folder.mkdir(parents=True)
        (folder / 'bench.cir').write_text(extension.expected_deck(root, self.manifest, self.spec, 400))
        for n in ('summary.json', 'bench.raw', 'bench.cir.prn'): (folder / n).write_text('retained')
        _, timing = extension.capture.fixture(self.spec, 400, self.manifest['identity']['model']['ports'])
        raw = np.zeros((3, 6)); raw[:, 0] = np.array([0, .5, 1]) * timing['stop_ns'] * 1e-9
        wave = np.column_stack((np.arange(3), raw))
        names = ['time', 'v(clk)', 'v(d)', 'v(q0)', 'v(q1)', 'v(valid)']
        header = {n.upper(): i + 1 for i, n in enumerate(names) if n.startswith('v(')}
        return folder, raw, wave, names, header

    def test_witness_independently_checks_binary_export_and_binds_all_files(self):
        with tempfile.TemporaryDirectory() as name, patch.dict(os.environ, PDK_ROOT='/pdk'):
            root = Path(name); folder, raw, wave, names, header = self.witness_fixture(root)
            with patch.object(extension, 'ROOT', root), patch.object(extension.evidence, 'verify_witness') as verify, \
                 patch.object(extension, 'read_raw', return_value=(names, raw)), \
                 patch.object(extension.capture, 'read_wave', return_value=(wave, header)):
                files = extension.witness(root, self.manifest, self.spec, 400, True)
                verify.assert_called_once_with(root, self.manifest, self.spec, 400, True)
                self.assertEqual(len(files), 4)
                for path, digest in files.items(): self.assertEqual(extension.sha(root / path), digest)
                for mutation in ('voltage', 'time', 'count', 'finite'):
                    changed = raw.copy()
                    if mutation == 'voltage': changed[1, 1] = .1
                    if mutation == 'time': changed[1, 0] += 1e-12
                    if mutation == 'count': changed = changed[:-1]
                    if mutation == 'finite': changed[1, 1] = float('nan')
                    with patch.object(extension, 'read_raw', return_value=(names, changed)):
                        with self.assertRaises(ValueError): extension.witness(root, self.manifest, self.spec, 400, True)

    def test_changed_native_deck_cannot_pass_on_the_old_export(self):
        with tempfile.TemporaryDirectory() as name, patch.dict(os.environ, PDK_ROOT='/pdk'):
            root = Path(name); folder, *_ = self.witness_fixture(root)
            text = (folder / 'bench.cir').read_text()
            for changed in (text.replace('20f', '10f'), text.replace('.tran 5p', '.tran 20p'), text.replace('VD VDDD 0 1.8', 'VD VDDD 0 1.7')):
                (folder / 'bench.cir').write_text(changed)
                with patch.object(extension.evidence, 'verify_witness'):
                    with self.assertRaises(ValueError): extension.witness(root, self.manifest, self.spec, 400, True)

    def test_guard_and_real_bracket_witnesses_are_mandatory(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); folder = root / extension.capture.condition_id(self.spec); folder.mkdir()
            row = dict(spec=self.spec, passed=True, failed_ps=100, passed_ps=103.125,
                       bound_ps=130, resolution_ps=3.125, guard_ps=20)
            path = folder / 'summary.json'; path.write_text(json.dumps(row))
            with patch.object(extension, 'ROOT', root), patch.object(extension, 'witness', return_value={}) as witness:
                self.assertEqual(extension.boundary(root, self.manifest, self.spec)[0], row)
                self.assertEqual([c.args[-1] for c in witness.call_args_list], [False, True, True])
                for field, value in [('guard_ps', 0), ('resolution_ps', 5), ('bound_ps', 120), ('passed', False)]:
                    changed = dict(row); changed[field] = value; path.write_text(json.dumps(changed))
                    with self.assertRaises(ValueError): extension.boundary(root, self.manifest, self.spec)

    def test_parent_pass_flag_cannot_replace_complete_original_evidence(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); parent = root / 'parent'; parent.mkdir()
            (parent / 'manifest.json').write_text('{}')
            m = dict(identity=dict(parent='parent', model=dict(netlist_sha256='model')))
            with patch.object(extension, 'ROOT', root), patch.object(extension, 'validate', return_value=m), \
                 patch.object(extension.evidence, 'read_table', side_effect=ValueError('original matrix incomplete')), \
                 patch.object(extension, 'boundary') as boundary:
                with self.assertRaisesRegex(ValueError, 'original matrix incomplete'): extension.assemble(root / 'extension')
                boundary.assert_not_called()

    def test_assembled_table_retains_1080_witness_locations_and_worst_bounds(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); parent = root / 'parent'; out = root / 'extended'
            parent.mkdir(); out.mkdir()
            for path in (parent / 'manifest.json', parent / 'table.json', out / 'manifest.json'):
                path.write_text('{}')
            (out / 'requirements.json').write_text(json.dumps(self.req))
            m = dict(identity=dict(parent='parent', model=dict(netlist_sha256='same native circuit')),
                     conditions=extension.conditions(self.req))
            def boundary(source, manifest, spec):
                bound = (290 if 250 in (spec['clock_slew_ps'], spec['data_slew_ps']) else 270) if spec['kind'] == 'setup' else 110
                return dict(passed=True, spec=spec, bound_ps=bound), {}
            with patch.object(extension, 'ROOT', root), patch.object(extension, 'validate', return_value=m), \
                 patch.object(extension.evidence, 'read_table') as verify_parent, \
                 patch.object(extension.original, 'check_seeds'), patch.object(extension, 'boundary', side_effect=boundary) as checked:
                table = extension.assemble(out, write=False)
                self.assertEqual(checked.call_count, 1080); verify_parent.assert_called_once()
                self.assertEqual(sum(r['witness_root'] == 'parent' for r in table['results']), 480)
                self.assertEqual(sum(r['witness_root'] == 'extended' for r in table['results']), 600)
                self.assertEqual(len(table['bounds']), 15)
                self.assertTrue(all(b == dict(setup_ps=290, hold_ps=110) for b in table['bounds'].values()))
                self.assertEqual(table['input_slew_ps'], [20, 250]); self.assertFalse(table['qualified_phy'])
                self.assertFalse((out / 'table.json').exists())

    def test_reader_rejects_foreign_model_and_changed_table(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'table.json'; path.write_text(json.dumps(dict(passed=True)))
            with patch.object(extension, 'validate', return_value=dict(identity=dict(model=dict(netlist_sha256='native')))):
                with self.assertRaises(ValueError): extension.read_table(path, 'other', 'ss', 40)
                with patch.object(extension, 'assemble', return_value=dict(passed=False)):
                    with self.assertRaises(ValueError): extension.read_table(path, 'native', 'ss', 40)

    def test_prior_execution_never_restarts_points(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); (root / 'manifest.json').write_text('{}'); (root / 'state.json').write_text('{}')
            with patch.object(extension, 'validate', return_value={}), patch.object(extension.capture, 'search') as search:
                with self.assertRaisesRegex(ValueError, 'no retry'): extension.run(root)
                search.assert_not_called()
