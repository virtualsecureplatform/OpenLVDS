# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_corrected_driver_soft_receiver as link


class CorrectedCoupledNativeLink(unittest.TestCase):
    def fixture(self):
        old=Path('/work/OpenLVDS/build/diagnostics/analog_link_pilot/old')
        new=Path('/work/OpenLVDS/build/diagnostics/corrected_native_link/new')
        probes=['V(X'+instance+':'+link.TOP+'__'+leaf+')' for instance in ['DR','CR'] for leaf in link.LEAVES]
        deck=('Coupled link\n.include "'+str(old)+'/library.spice"\nVCLK CLK 0 PWL(0 0 1n 1.8)\n'
            '.tran 20p 188.049n 0 20p\n.print tran V(RP) '+' '.join(probes)+'\n.end\n')
        nodes={leaf:'XRC:'+link.TOP+'__'+leaf+'.t1' for leaf in link.LEAVES}
        return old,new,deck,nodes

    def test_only_library_path_and_exact_native_probe_aliases_change(self):
        old,new,deck,nodes=self.fixture();changed=link.fixture(deck,old,new,nodes)
        restored=changed.replace(str(new),str(old))
        for instance in ['DR','CR']:
            for leaf in link.LEAVES:
                restored=restored.replace('V(X'+instance+':'+link.TOP+'__'+leaf+'.t1)',
                    'V(X'+instance+':'+link.TOP+'__'+leaf+')')
        self.assertEqual(restored,deck)

    def test_shortened_coarse_and_ambiguous_fixtures_are_refused(self):
        old,new,deck,nodes=self.fixture()
        for bad in [deck.replace('188.049n','100n'),deck.replace('0 20p','0 100p'),
                    deck.replace('V(RP)','V(RP) V(XDR:'+link.TOP+'__PP)')]:
            with self.assertRaises(ValueError):
                link.fixture(bad,old,new,nodes)

    def test_missing_native_admission_cannot_start_driver_or_link_job(self):
        with patch.object(link.receiver,'recheck',side_effect=ValueError('native held')),patch.object(link.driver,'run') as run:
            with self.assertRaisesRegex(ValueError,'native held'):
                link.prepare(Path('parent'),Path('replay'),Path('driver'))
            run.assert_not_called()

    def test_partial_coupled_trace_is_preserved_before_any_recheck_or_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'build/diagnostics/corrected_native_link/partial';out.mkdir(parents=True)
            (out/'manifest.json').write_text(json.dumps(dict(identity=dict(simulator_provenance='test',inputs={},code={}),files={})))
            raw=out/'bench.raw';raw.write_bytes(b'original incomplete coupled trace')
            with patch.object(link,'ROOT',root),patch.object(link,'provenance',return_value='test'),patch.object(link.receiver,'recheck') as check,patch.object(link.subprocess,'run') as launch:
                with self.assertRaisesRegex(ValueError,'Partial corrected native link retained'):
                    link.run(out)
                check.assert_not_called();launch.assert_not_called()
            self.assertEqual(raw.read_bytes(),b'original incomplete coupled trace')


if __name__=='__main__':
    unittest.main()
