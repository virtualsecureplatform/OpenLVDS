# SPDX-License-Identifier: GPL-3.0-only
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import prepare_driver_cmfb_lead_native as native


class CompensatedNativeSourceSelection(unittest.TestCase):
    def test_original_geometric_selector_is_not_used(self):
        with patch.object(native.physical, 'source_ready') as verify:
            with self.assertRaisesRegex(ValueError, 'explicit compensated source'):
                native.selected_source({'identity': {'inputs': {
                    'build/diagnostics/driver_shape_source_verification/old/summary.json': 'old'}}}, 'source')
            verify.assert_not_called()

    def test_binds_actual_campaign_model_and_verification_source_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            campaign = root / 'campaign'
            folder = campaign / 'tt_25_negative_op'
            folder.mkdir(parents=True)
            (folder / 'source.spice').write_text('actual compensated schematic')
            digest = hashlib.sha256(b'actual compensated schematic').hexdigest()
            report = dict(identity=dict(source_readiness='readiness/summary.json', source='campaign'),
                source_sha256=digest)
            ready = {'source_sha256': digest}
            with patch.object(native, 'ROOT', root), patch.object(native.physical, 'source_ready',
                    return_value=(campaign, ready)):
                self.assertEqual(native.selected_source(report, 'actual compensated schematic'), (campaign, ready))
                with self.assertRaisesRegex(ValueError, 'circuit differ'):
                    native.selected_source(report, 'old geometric schematic')
                report['identity']['source'] = 'old-campaign'
                with self.assertRaisesRegex(ValueError, 'binding changed'):
                    native.selected_source(report, 'actual compensated schematic')
                report['identity']['source'] = 'campaign'
                with patch.dict(ready, source_sha256='changed'):
                    with self.assertRaisesRegex(ValueError, 'circuit differ'):
                        native.selected_source(report, 'actual compensated schematic')

    def model(self):
        return f'''.subckt {native.assembly.TOP} SINK VSS
XCM SINK VSS lvds_cmfb
.ends {native.assembly.TOP}
.subckt lvds_cmfb OUT VSS
XCMFB_RZ0 OUT CMFB_LEAD_C VSS sky130_fd_pr__res_high_po_0p35 w=.35 l=1.25
XC CMFB_LEAD_C VSS sky130_fd_pr__cap_mim_m3_1 w=29 l=29
.ends lvds_cmfb
'''

    def test_new_observation_uses_source_identified_resistor_plate(self):
        name = native.assembly.TOP + '__XCM__XCMFB_RZ0'
        placements = [dict(instance='I42', members=[name])]
        target = native.lead_target(self.model(), placements)['CMFB_LEAD_C']
        self.assertEqual(target['physical_pin'], 'I42.R2')
        self.assertEqual(target['source_net'], native.assembly.TOP + '__XCM__CMFB_LEAD_C')
        self.assertEqual(target['members'], [name])

    def test_ambiguous_or_changed_compensation_plate_is_rejected(self):
        name = native.assembly.TOP + '__XCM__XCMFB_RZ0'
        placement = dict(instance='I42', members=[name])
        for model, placements in [(self.model(), []), (self.model(), [placement, placement]),
                (self.model().replace('XCMFB_RZ0 OUT CMFB_LEAD_C', 'XCMFB_RZ0 CMFB_LEAD_C OUT'), [placement])]:
            with self.subTest(placements=placements):
                with self.assertRaisesRegex(ValueError, 'compensation resistor plate'):
                    native.lead_target(model, placements)

    def test_unpinned_engine_cannot_prepare_native_pilots(self):
        with patch.object(native.pilot, 'engine', return_value='xyce'), \
                patch.object(native.assembly, 'assemble') as assemble:
            with self.assertRaisesRegex(ValueError, 'pinned ngspice'):
                native.prepare(Path('/assembly'))
            assemble.assert_not_called()
