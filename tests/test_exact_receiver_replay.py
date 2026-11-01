# SPDX-License-Identifier: GPL-3.0-only
import json
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import replay_selected_receiver_exact as exact
from dll_campaign import text_block
from exact_rc_candidate import parse, static_signature

LIBRARY = '''.subckt openlvds_ddr_rx A B VSS
X1 A gate VSS VSS sky130_fd_pr__nfet_01v8 w=8 l=1
C0 center VSS 1p
R0 A n0 1
R1 B n0 2
R2 center n0 3
.ends openlvds_ddr_rx
.subckt other A B
Rother A B 17
.ends other
'''


class ExactReceiverReplay(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('scipy'), 'Use build/tools/exact-rc-venv/bin/python')
    def test_independent_witness_and_other_circuits_are_preserved(self):
        with patch.object(exact, 'math_runtime', return_value={}):
            reduced, proof = exact.reduce_library(LIBRARY)
        self.assertTrue(proof['admittance_witness']['passed'])
        self.assertEqual(proof['algebraic_nodes_eliminated'], 1)
        self.assertTrue(proof['transient_equivalence_pending'])
        self.assertFalse(proof['qualified_phy'])
        self.assertEqual(text_block(LIBRARY, 'other'), text_block(reduced, 'other'))
        self.assertEqual(static_signature(parse(text_block(LIBRARY, exact.TOP))),
                         static_signature(parse(text_block(reduced, exact.TOP))))

    @unittest.skipUnless(importlib.util.find_spec('scipy'), 'Use build/tools/exact-rc-venv/bin/python')
    def test_certification_rejects_a_changed_capacitor(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(exact, 'math_runtime', return_value={}):
            root = Path(tmp); parent = root/'parent'; child = root/'child'
            parent.mkdir(); child.mkdir()
            (parent/'library.spice').write_text(LIBRARY)
            reduced, _ = exact.reduce_library(LIBRARY)
            (child/'library.spice').write_text(reduced.replace('1p', '2p'))
            (child/'manifest.json').write_text(json.dumps(dict(identity=dict(parent='parent'))))
            with patch.object(exact.replay, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'differs from certified'):
                    exact.certify(child, None, None)

    def test_profile_restores_bindings_on_an_exception(self):
        import numpy as np
        original = exact.replay.overlay, exact.replay.CODE, exact.replay.read_wave
        with patch.object(exact.bounded, 'BASE_READ', return_value=(np.zeros((2, 20)), {})):
            with self.assertRaisesRegex(RuntimeError, 'intentional'):
                with exact.profile(Path('/parent')):
                    self.assertIn(exact.NAME, exact.replay.CODE)
                    raise RuntimeError('intentional')
        self.assertEqual(original, (exact.replay.overlay, exact.replay.CODE, exact.replay.read_wave))


if __name__ == '__main__':
    unittest.main()
