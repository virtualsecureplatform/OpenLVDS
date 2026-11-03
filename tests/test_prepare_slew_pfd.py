from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import prepare_slew_pfd as preparation


class PreparedSlewPFD(unittest.TestCase):
    def test_failed_source_expansion_and_unknown_parent_cannot_create_physical_source(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); parent = root / 'build/diagnostics/dll_slew_expansion/example'; parent.mkdir(parents=True)
            with patch.object(preparation, 'ROOT', root):
                with self.assertRaises(ValueError): preparation.gate(root / 'other')
                with patch.object(preparation.expansion, 'verify', return_value={'ranked_survivors': []}):
                    with self.assertRaisesRegex(ValueError, 'analog fallback'): preparation.gate(parent)
                with patch.object(preparation.expansion, 'verify', return_value={'ranked_survivors': ['clkbuf_4'], 'candidates': []}):
                    with self.assertRaisesRegex(ValueError, 'worst-PVT'): preparation.gate(parent)

    def fixture(self, root):
        original = preparation.ROOT
        for name in ['sky130/experiments/lvds_pfd_area_fast_reset.v', 'sky130/pfd_blackboxes.v',
                     'constraints/pfd.sdc', 'thirdparties/OpenPLL/sky130/sky130_fd_sc_hd_pll_blackbox.v',
                     'scripts/prepare_slew_pfd.py', 'scripts/pfd_slew_policy.py',
                     'scripts/pfd_fast_reset_policy.py', 'scripts/physical_policy.py']:
            dest = root / name; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(original / name, dest)
        return root / 'build/diagnostics/dll_slew_expansion/example'

    def test_preparation_is_immutable_and_keeps_worst_pvt_without_claiming_physical_admission(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); parent = self.fixture(root)
            with patch.object(preparation, 'ROOT', root), patch.object(preparation, 'gate', return_value=('nor4_inv4', ['fs', 25], {'identity': {'inputs': {}, 'code': {}}}, [])):
                out = preparation.prepare(parent); m = preparation.bound(out)
                self.assertEqual(m['identity']['coverage_recipe'], dict(version='dll-slew-repair-v1', worst_screened_pvt=['fs', 25]))
                self.assertFalse(m['qualified_phy']); self.assertFalse(m['physical_admission'])
                before = (out / 'manifest.json').read_bytes()
                self.assertEqual(preparation.prepare(parent), out)
                self.assertEqual((out / 'manifest.json').read_bytes(), before)
                (out / 'lvds_pfd.v').write_text((out / 'lvds_pfd.v').read_text().replace('.CLK(ref_conditioned)', '.CLK(REF)'))
                with self.assertRaises(ValueError): preparation.bound(out)
                with self.assertRaises(ValueError): preparation.prepare(parent)

    def test_rehashed_constraint_or_blackbox_changes_and_false_promotion_are_rejected(self):
        for mutation in ('pfd.sdc', 'pfd_blackboxes.v', 'promotion'):
            with tempfile.TemporaryDirectory() as d:
                root = Path(d); parent = self.fixture(root)
                with patch.object(preparation, 'ROOT', root), patch.object(preparation, 'gate', return_value=('clkbuf_4', ['ss', 40], {'identity': {'inputs': {}, 'code': {}}}, [])):
                    out = preparation.prepare(parent); m = json.loads((out / 'manifest.json').read_text())
                    if mutation == 'promotion': m['qualified_phy'] = True
                    else:
                        (out / mutation).write_text('changed\n'); m['files'][mutation] = preparation.sha(out / mutation)
                    (out / 'manifest.json').write_text(json.dumps(m))
                    with self.assertRaises(ValueError): preparation.bound(out)
