# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_driver_cmfb_lead as physical


class CompensatedPhysicalAdmission(unittest.TestCase):
    def original(self):
        mos = [f'XM{i} D G{i} VSS VSS sky130_fd_pr__nfet_g5v0d10v5 w=8 l=1' for i in range(302)]
        resistors = [f'XR{i} D VSS VSS sky130_fd_pr__res_high_po_0p35 w=.35 l=10.25' for i in range(12)]
        caps = [f'XC{i} OUT VSS sky130_fd_pr__cap_mim_m3_1 w=29 l=29' for i in range(6)]
        return '\n'.join([f'.subckt {physical.TOP} D VSS', *mos, *resistors,
            'XCM D VSS lvds_cmfb', f'.ends {physical.TOP}',
            '.subckt lvds_cmfb OUT VSS', *caps, '.ends lvds_cmfb'])

    def test_exact_compensation_adds_one_resistor_and_preserves_all_mos(self):
        original = self.original()
        candidate = physical.qualification.lead.transform(original, 'lvds_cmfb')
        ports, devices, groups = physical.checked_devices(original, candidate)
        self.assertEqual(len(devices), 321)
        self.assertEqual(sum(physical.banks.mos(d) for d in devices), 302)
        self.assertEqual(sum(not physical.banks.mos(d) for d in devices), 19)
        self.assertEqual(sum(g['nf'] for g in groups if physical.banks.mos(g)), 302)
        self.assertEqual(ports, ['D', 'VSS'])

    def test_extra_source_change_or_changed_mos_cannot_reuse_original_banks(self):
        original = self.original()
        candidate = physical.qualification.lead.transform(original, 'lvds_cmfb')
        changed = candidate.replace('XM0 D G0 VSS', 'XM0 D OTHER VSS')
        with self.assertRaisesRegex(ValueError, 'single admitted compensation'):
            physical.checked_devices(original, changed)
        with patch.object(physical.qualification.lead, 'transform', return_value=changed):
            with self.assertRaisesRegex(ValueError, 'MOS, terminal'):
                physical.checked_devices(original, changed)

    def test_passive_recipes_are_checked_independently_of_mos_topology(self):
        original = self.original()
        candidate = physical.qualification.lead.transform(original, 'lvds_cmfb')
        changed = candidate.replace('l=10.25', 'l=11.25', 1)
        with patch.object(physical.qualification.lead, 'transform', return_value=changed):
            with self.assertRaisesRegex(ValueError, 'all original passives'):
                physical.checked_devices(original, changed)

    def test_partial_source_cannot_invoke_magic(self):
        with patch.object(physical, 'source_ready', side_effect=ValueError('incomplete source')), \
                patch.object(physical, 'invoke_magic') as magic, patch.object(physical, 'tile_context') as tiles:
            with self.assertRaisesRegex(ValueError, 'incomplete source'):
                physical.build(Path('/receipt'), Path('/tiles'))
            magic.assert_not_called()
            tiles.assert_not_called()

    def test_pilot_receipt_cannot_be_used_as_full_source_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = dict(recipe=physical.qualification.NEW, source_waveform_ready=True,
                required_cases=6, required_pvt=3, physical_admission=False, qualified_phy=False)
            digest = hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()[:16]
            receipt = root / 'build/diagnostics/driver_cmfb_lead_source_verification' / digest / 'summary.json'
            receipt.parent.mkdir(parents=True)
            receipt.write_text(json.dumps(report))
            with patch.object(physical, 'ROOT', root), patch.object(physical.qualification, 'verify') as verify:
                with self.assertRaisesRegex(ValueError, 'all thirty'):
                    physical.source_ready(receipt)
                verify.assert_not_called()
