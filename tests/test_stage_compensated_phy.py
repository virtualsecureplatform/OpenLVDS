# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import stage_compensated_phy as stage
from dll_campaign import text_block
from spice_scope import closure_hash


class CompensatedPHYStaging(unittest.TestCase):
    def model(self):
        body = '''.subckt openlvds_driver_core D P N VR PB NB VA VD VS
RS SINK VS 1
RT TOP VA 1
RP DP D 1
RN DN D 1
.ends openlvds_driver_core
'''
        return body + '\n'.join('.subckt '+n+' A B\nR0 A B 1\n.ends '+n for n in
            sorted(stage.BLOCKS - {'openlvds_driver_core'} | {'openlvds_dll'}))

    def observations(self):
        return {n: {'native_node': n} for n in ['SINK', 'TOP', 'DP', 'DN']}

    def selection(self, lib):
        exact = {n: dict(netlist_sha256=n) for n in stage.BLOCKS}
        return dict(exact_models=exact, digital_models={n: exact[n] for n in stage.DIGITAL},
            inputs={n: exact[n]['netlist_sha256'] for n in stage.BLOCKS},
            scopes={n: closure_hash(lib, n) for n in stage.BLOCKS | {'openlvds_dll'}},
            driver_nodesets=stage.driver_nodesets(lib, self.observations()),
            dll_verification=dict(passed=True, case_reports={str(n): 'sha' for n in range(336)},
                                  comparisons=[{'passed': True} for _ in range(10)]))

    def test_nodesets_use_actual_retained_conductors_and_reject_old_aliases(self):
        lib = self.model(); guesses = stage.driver_nodesets(lib, self.observations())
        self.assertEqual(len(guesses), 8)
        self.assertEqual(guesses['XDT:SINK'], 1.36)
        self.assertEqual(guesses['XCT:DP'], 0)
        wrong = self.observations(); wrong['SINK']['native_node'] = 'openlvds_driver_core__SINK'
        with self.assertRaisesRegex(ValueError, 'Missing voltage probe'):
            stage.driver_nodesets(lib, wrong)
        wrong['SINK']['native_node'] = 'TOP'
        with self.assertRaisesRegex(ValueError, 'merged'):
            stage.driver_nodesets(lib, wrong)

    def test_block_coverage_digital_metadata_and_closures_cannot_drift(self):
        lib = self.model(); selected = self.selection(lib)
        stage.validate_selection(selected, lib)
        for mutate in [lambda s: s['exact_models'].pop('lvds_bias'),
                       lambda s: s['digital_models'].pop('openlvds_ddr_rx'),
                       lambda s: s['inputs'].update(lvds_bias='other'),
                       lambda s: s['driver_nodesets'].pop('XDT:SINK')]:
            bad = deepcopy(selected); mutate(bad)
            with self.assertRaises(ValueError): stage.validate_selection(bad, lib)
        with self.assertRaisesRegex(ValueError, 'closure changed'):
            stage.validate_selection(selected, lib.replace('RS SINK VS 1', 'RS SINK VS 2'))

    def test_incomplete_dll_verification_cannot_be_hidden_by_pass_flag(self):
        selected = self.selection(self.model()); selected['dll_verification']['case_reports'].pop('0')
        with self.assertRaisesRegex(ValueError, 'complete native DLL'):
            stage.validate_selection(selected, self.model())

    def test_failed_coupled_payload_cannot_reach_dll_or_create_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); restoration = root / 'build/diagnostics' / stage.restored.NAMESPACE / 'r'
            with patch.object(stage, 'ROOT', root), patch.object(stage.restored, 'verify',
                    return_value={'payload_restored': False}), patch.object(stage, 'dll_gate') as dll:
                with self.assertRaisesRegex(ValueError, 'Restore complete ordered payload'):
                    stage.prepare(restoration, root/'build/diagnostics/dll_qualification/q',
                                  root/'build/diagnostics/tx', root/'build/diagnostics/rx')
                dll.assert_not_called()
            self.assertFalse((root/'build/diagnostics'/stage.NAMESPACE).exists())

    def test_partial_dll_is_rejected_without_invoking_scientific_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            q = Path(tmp)
            (q/'manifest.json').write_text(json.dumps({'tasks': [{'id': str(n)} for n in range(336)]}))
            with patch.object(stage.integration, 'dll_context'), patch.object(stage.dll_native_evidence, 'verify') as verify:
                with self.assertRaisesRegex(ValueError, 'Complete all 336'):
                    stage.dll_gate(q)
                verify.assert_not_called()

    def bundle(self, root):
        lib = self.model(); selected = self.selection(lib)
        (root/'scripts').mkdir(); (root/'requirements.json').write_text('{}')
        selected['code'] = {}
        for n in stage.CODE:
            p = root/'scripts'/n; p.write_text('pinned code'); selected['code'][n] = stage.sha(p)
        selected['proofs'] = {}
        for name in stage.BLOCKS:
            p = root/(name+'.spice'); p.write_text(text_block(lib, name)+'\n')
            ports = p.read_text().splitlines()[0].split()[2:]
            info = dict(passed=True, ports_verified=True, ports=ports,
                        netlist=p.name, netlist_sha256=stage.sha(p))
            selected['exact_models'][name] = info; selected['inputs'][name] = info['netlist_sha256']
            selected['proofs'][p.name] = stage.sha(p)
            if name in stage.DIGITAL: selected['digital_models'][name] = info
        i = dict(schema=1, selection=selected, simulator=stage.provenance(),
            requirements_sha256=stage.sha(root/'requirements.json'),
            library_sha256=hashlib.sha256(lib.encode()).hexdigest(),
            paths=dict(restoration='build/diagnostics/'+stage.restored.NAMESPACE+'/r',
                       qualification='build/diagnostics/dll_qualification/q',
                       tx='build/diagnostics/tx', rx='build/diagnostics/rx'))
        out = root/'build/diagnostics'/stage.NAMESPACE/hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
        out.mkdir(parents=True); (out/'full.spice').write_text(lib)
        (out/'manifest.json').write_text(json.dumps(dict(identity=i, **stage.FLAGS)))
        return out

    def test_loader_rejects_changed_evidence_library_scope_and_approximate_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = self.bundle(root)
            with patch.object(stage, 'ROOT', root), patch('spice_library.ROOT', root):
                self.assertEqual(stage.load(out)[0].decode(), self.model())
                with self.assertRaisesRegex(ValueError, 'exact-RC only'): stage.load(out, True)
                p = root/'lvds_bias.spice'; before = p.read_text(); p.write_text(before+'* changed\n')
                with self.assertRaisesRegex(ValueError, 'evidence changed'): stage.load(out)
                p.write_text(before)
                (out/'full.spice').write_text(self.model()+'* changed\n')
                with self.assertRaisesRegex(ValueError, 'library changed'): stage.load(out)
                (out/'full.spice').write_text(self.model())
                m = json.loads((out/'manifest.json').read_text()); m['qualified'] = True
                (out/'manifest.json').write_text(json.dumps(m))
                with self.assertRaisesRegex(ValueError, 'diagnostic scope'): stage.load(out)


if __name__ == '__main__':
    unittest.main()
