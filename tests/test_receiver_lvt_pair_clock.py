# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_lvt_pair_clock as clock


class LowThresholdPairClock(unittest.TestCase):
    def test_profile_uses_exact_declared_factory_and_restores_on_failure(self):
        factory,gate=clock.clock.factory,clock.clock.static_gate
        with self.assertRaisesRegex(ValueError,'expected failure'):
            with clock.clock_profile():
                self.assertIs(clock.clock.factory.source_variant,clock.factory.source_variant)
                self.assertIs(clock.clock.factory.experiment,clock.engine)
                self.assertIs(clock.clock.static_gate,clock.static_gate)
                raise ValueError('expected failure')
        self.assertIs(clock.clock.factory,factory);self.assertIs(clock.clock.static_gate,gate)

    def test_incomplete_dc_cannot_prepare_or_run_uncached_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);screen=root/'build/diagnostics/receiver_lvt_pair_matrix/incomplete';screen.mkdir(parents=True)
            (screen/'manifest.json').write_text(json.dumps(dict(identity=dict(children=[dict(root='missing')]*15))))
            with patch.object(clock,'ROOT',root),patch.object(clock.engine,'prepare') as prepare,patch.object(clock.dc,'run') as run:
                with self.assertRaisesRegex(ValueError,'Complete all fifteen'):clock.prepare(root/'parent',screen)
                prepare.assert_not_called();run.assert_not_called()

    def test_prepare_restores_original_source_factory_and_code_even_if_builder_fails(self):
        code,factory=clock.engine.CODE,clock.engine.source_variant
        def build(parent):
            self.assertIs(clock.engine.source_variant,clock.factory.source_variant)
            self.assertIn(clock.NAME,clock.engine.CODE)
            self.assertIn('receiver_decision_load_clock.py',clock.engine.CODE)
            raise ValueError('fixture held')
        with patch.object(clock,'static_gate',return_value={}),patch.object(clock.engine,'prepare',side_effect=build):
            with self.assertRaisesRegex(ValueError,'fixture held'):clock.prepare(Path('parent'),Path('screen'))
        self.assertIs(clock.engine.CODE,code);self.assertIs(clock.engine.source_variant,factory)


if __name__=='__main__':unittest.main()
