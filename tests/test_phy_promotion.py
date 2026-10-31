# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import promote_phy_candidate as promotion


class SealedPHYRelease(unittest.TestCase):
    def test_extra_missing_or_duplicate_lef_pins_are_rejected(self):
        text='MACRO dll\n  PIN CLK\n  PIN VSS\nEND dll\n'
        promotion.check_lef_interface('dll',text,['CLK','VSS'])
        for changed in [text.replace('  PIN VSS\n',''),text.replace('END dll','  PIN ERR\nEND dll'),
                        text.replace('END dll','  PIN CLK\nEND dll')]:
            with self.assertRaisesRegex(ValueError,'LEF interface'):
                promotion.check_lef_interface('dll',changed,['CLK','VSS'])

    def test_sealing_preserves_binary_bytes_and_rejects_a_changed_existing_package(self):
        with tempfile.TemporaryDirectory() as directory:
            data=b'\x00exact tested library\xff\n';files={'electrical/full.spice':dict(data=data,source='source',sha256=promotion.digest(data))}
            root=Path(directory);target,stamp=promotion.seal(files,{'fixture':'unit test'},root)
            self.assertEqual((target/'electrical/full.spice').read_bytes(),data)
            self.assertEqual(promotion.seal(files,{'fixture':'unit test'},root),(target,stamp))
            self.assertFalse((root/'current.json').exists())
            (target/'electrical/full.spice').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'release file changed'):
                promotion.seal(files,{'fixture':'unit test'},root)

    def test_failed_copy_never_publishes_a_package_or_pointer(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);files={'electrical/full.spice':dict(data=b'actual',source='source',sha256='wrong')}
            with self.assertRaisesRegex(ValueError,'copy changed'):promotion.seal(files,{},root)
            self.assertEqual(list((root/'packages').iterdir()),[])
            self.assertFalse((root/'current.json').exists())

    def test_failed_gate_does_not_replace_the_previous_current_pointer(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);bundle=root/'build/diagnostics/phy_candidate/rejected';(bundle/'release').mkdir(parents=True)
            (bundle/'release/status.json').write_text('{"passed":false,"checks":[]}')
            release=root/'build/release';release.mkdir();pointer=release/'current.json';pointer.write_bytes(b'previous pointer')
            with patch.object(promotion,'ROOT',root):
                with self.assertRaisesRegex(ValueError,'passing staged release'):promotion.promote(bundle)
            self.assertEqual(pointer.read_bytes(),b'previous pointer')
            self.assertFalse((release/'packages').exists())

    def test_empty_or_partly_failed_checklists_cannot_qualify(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);bundle=root/'bundle'
            with patch.object(promotion,'ROOT',root):
                for checks in [[],[{'passed':False}],[{'passed':True},{'passed':False}]]:
                    with self.assertRaisesRegex(ValueError,'passing staged release'):
                        promotion.report_arguments(bundle,dict(passed=True,checks=checks))

    def test_saved_success_cannot_bypass_mandatory_reanalysis(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);bundle=root/'build/diagnostics/phy_candidate/fixture';(bundle/'release').mkdir(parents=True)
            (bundle/'release/status.json').write_text('{"passed":true}')
            release=root/'build/release';release.mkdir();pointer=release/'current.json';pointer.write_bytes(b'previous pointer')
            with patch.object(promotion,'ROOT',root),patch.object(promotion,'report_arguments',return_value=[]),\
                 patch.object(promotion.subprocess,'run',side_effect=RuntimeError('mandatory reanalysis failed')) as recheck:
                with self.assertRaisesRegex(RuntimeError,'mandatory reanalysis'):promotion.promote(bundle)
                recheck.assert_called_once()
            self.assertEqual(pointer.read_bytes(),b'previous pointer')
            self.assertFalse((release/'packages').exists())
