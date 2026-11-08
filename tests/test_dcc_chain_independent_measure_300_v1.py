# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcc_chain_independent_measure_300_v1 as independent
import test_dcc_chain_measure_300_v2 as fixtures
from replay_bank_300_v2 import same


class IndependentCombinedBinaryTests(fixtures.CombinedPulseBinaryTests):
    def test_internal_hold_failure_overrides_correct_output_transport(self):
        original=fixtures.p.measure
        def compare(*args,**kwargs):
            expected=original(*args,**kwargs)
            witness=independent.measure(*args,**kwargs)
            self.assertTrue(same(expected,witness))
            return expected
        # Reuse the full binary fixture and its internal-fault mutation. This
        # wrapper observes both real readers; neither algorithm is substituted.
        with patch.object(fixtures.p,'measure',side_effect=compare):
            super().test_internal_hold_failure_overrides_correct_output_transport()
