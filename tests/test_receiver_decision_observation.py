# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from receiver_decision_observation import observed_deck, intervention
from receiver_fast_restore_experiment import source_variant as clamped_source
from receiver_unclamped_restore_experiment import source_variant as unclamped_source


class DecisionObservation(unittest.TestCase):
    def test_only_print_columns_and_include_binding_change(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / 'parent'
            root = Path(directory) / 'observed'
            parent.mkdir()
            source = (ROOT / 'analog/openlvds.spice').read_text()
            (parent / 'source.spice').write_text(clamped_source(source))
            deck = (f'.include "{parent}/source.spice"\n'
                    'XR P N Q VREF IREF VDDIO VDDD 0 openlvds_receiver\n'
                    '.tran 10p 144n 0 50p\n.print tran V(P) V(N) V(Q)\n.end\n')
            result = observed_deck(deck, parent, root)
            extra = ' V(XR:XCORE:CL) V(XR:XCORE:CT) V(XR:XCORE:NBC)'
            self.assertEqual(result.replace(extra, '').replace(str(root), str(parent)), deck)
            self.assertEqual(intervention(clamped_source(source)), unclamped_source(source))

    def test_missing_and_ambiguous_observation_rows_rejected(self):
        for deck in ['.end\n', '.print tran V(P)\n.print tran V(N)\n.end\n']:
            with self.assertRaises(ValueError):
                observed_deck(deck, Path('/parent'), Path('/observed'))


if __name__ == '__main__':
    unittest.main()
