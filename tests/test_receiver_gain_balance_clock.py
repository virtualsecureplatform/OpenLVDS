# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_gain_balance_clock as clock


class GainBalanceClock(unittest.TestCase):
    def test_reference_is_exact_admitted_n8_and_candidates_match_dc(self):
        source = (clock.ROOT/'analog/openlvds.spice').read_text()
        for variant in clock.VARIANTS:
            self.assertEqual(clock.source_variant(source, True, variant),
                clock.dc.transform(clock.original.source_variant(source, True), variant))
            self.assertEqual(clock.source_variant(source, False, variant),
                clock.parent_clock.source_variant(source, True, 'restore_lvt_n8'))
        with self.assertRaises(ValueError):
            clock.source_variant(source, True, 'restore_lvt_n8')

    def test_missing_dc_report_cannot_launch_simulation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); screen = root/'build/diagnostics/receiver_gain_balance_matrix/incomplete'
            screen.mkdir(parents=True)
            req = dict(process_corners=['tt','ff','ss','fs','sf'], temperatures_c=[0,25,40])
            (root/'requirements.json').write_text(json.dumps(req))
            children = [dict(process=p, temperature=t, case=f'schematic_receiver_{p}_{t}', root='missing')
                for p in req['process_corners'] for t in req['temperatures_c']]
            (screen/'manifest.json').write_text(json.dumps(dict(identity=dict(children=children))))
            (screen/'summary.json').write_text('{}')
            with patch.object(clock, 'ROOT', root), patch.object(clock.matrix, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'Complete all fifteen'):
                    clock.static_gate(screen, 'restore_p4_n8')
                run.assert_not_called()

    def test_profile_restores_after_failure(self):
        previous = clock.clock.factory, clock.clock.static_gate
        with self.assertRaises(RuntimeError):
            with clock.profile('decision_pair_w32'):
                source = (clock.ROOT/'analog/openlvds.spice').read_text()
                self.assertEqual(clock.clock.factory.source_variant(source, False),
                                 clock.source_variant(source, False, 'decision_pair_w32'))
                raise RuntimeError('injected')
        self.assertEqual((clock.clock.factory, clock.clock.static_gate), previous)


class ReferenceAdoption(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.old = self.base/'parent/clamped_captured'; self.old.mkdir(parents=True)
        self.root = self.base/'new'; self.new = self.root/'unclamped_captured'; self.new.mkdir(parents=True)
        self.patch = patch.object(clock, 'ROOT', self.base); self.patch.start(); self.addCleanup(self.patch.stop)
        self.aliases = {'decision': 'CO'}
        self.write(self.old.parent/'manifest.json', dict(tasks=[dict(id='clamped_captured',
            clamped=True, aliases=self.aliases, files={})]))
        self.write(self.root/'manifest.json', dict(tasks=[dict(id='unclamped_captured',
            clamped=False, aliases=self.aliases)]))
        for folder in [self.old, self.new]:
            (folder/'candidate.spice').write_text('identical source')
            (folder/'library.spice').write_text('identical library')
            (folder/'bench.cir').write_text(f'.include "{folder}/library.spice"\n.TRAN 5p 80n 0 1p\n')
        (self.old/'bench.cir.prn').write_text('completed reference waveform')
        self.report = dict(task='clamped_captured', qualified_phy=False,
            manifest_sha256=clock.dc.sha(self.old.parent/'manifest.json'),
            waveform_sha256=clock.dc.sha(self.old/'bench.cir.prn'),
            receiver_transport=dict(missing_output_edges=0,
                pulses=[dict(output_edges_in_next_input_period=1) for _ in range(47)]))
        self.write(self.old/'summary.json', self.report)

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value))

    def test_only_exact_reference_can_be_adopted_and_verified(self):
        clock.adopt_reference(self.old, self.new, self.root)
        self.assertEqual((self.new/'bench.cir.prn').read_bytes(), (self.old/'bench.cir.prn').read_bytes())
        expected = dict(self.report, task='unclamped_captured', manifest_sha256=clock.dc.sha(self.root/'manifest.json'))
        self.assertEqual(json.loads((self.new/'summary.json').read_text()), expected)
        self.assertFalse((self.root/'clamped_captured').exists())
        clock.adopt_reference(self.old, self.new, self.root, create=False)

    def test_candidate_task_cannot_be_filled(self):
        self.write(self.root/'manifest.json', dict(tasks=[dict(id='unclamped_captured', clamped=True)]))
        with self.assertRaisesRegex(ValueError, 'modified candidate'):
            clock.adopt_reference(self.old, self.new, self.root)
        self.assertFalse((self.new/'bench.cir.prn').exists())

    def test_changed_library_or_deck_prevents_copy(self):
        original = (self.new/'library.spice').read_text()
        (self.new/'library.spice').write_text('changed circuit')
        with self.assertRaisesRegex(ValueError, 'circuit/library'):
            clock.adopt_reference(self.old, self.new, self.root)
        (self.new/'library.spice').write_text(original)
        with (self.new/'bench.cir').open('a') as f:
            f.write('VEXTRA supply 0 1.9\n')
        with self.assertRaisesRegex(ValueError, 'stimulus or numerical'):
            clock.adopt_reference(self.old, self.new, self.root)
        self.assertFalse((self.new/'bench.cir.prn').exists())

    def test_failed_or_repeated_reference_edges_prevent_copy(self):
        self.report['receiver_transport']['pulses'][0]['output_edges_in_next_input_period'] = 2
        self.write(self.old/'summary.json', self.report)
        with self.assertRaisesRegex(ValueError, 'completed passing'):
            clock.adopt_reference(self.old, self.new, self.root)
        self.assertFalse((self.new/'bench.cir.prn').exists())

    def test_existing_waveform_and_receipt_are_immutable(self):
        clock.adopt_reference(self.old, self.new, self.root)
        (self.new/'bench.cir.prn').write_text('partial waveform retained')
        with self.assertRaisesRegex(ValueError, 'waveform changed'):
            clock.adopt_reference(self.old, self.new, self.root)
        self.assertEqual((self.new/'bench.cir.prn').read_text(), 'partial waveform retained')

    def test_verification_cannot_create_missing_waveform(self):
        with self.assertRaisesRegex(ValueError, 'waveform is missing'):
            clock.adopt_reference(self.old, self.new, self.root, create=False)
        self.assertFalse((self.new/'bench.cir.prn').exists())


if __name__ == '__main__':
    unittest.main()
