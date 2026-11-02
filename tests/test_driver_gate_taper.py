# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import driver_gate_taper as taper
from driver_current_variant import source_variant
from layout import circuits


class RealDriverGateTapers(unittest.TestCase):
    def source(self):return source_variant((Path(__file__).resolve().parents[1]/'analog/openlvds.spice').read_text())

    def test_only_driver_converter_binding_and_new_helpers_change(self):
        source=self.source();before=circuits(source)
        for variant in taper.VARIANTS:
            changed=taper.transform(source,variant);after=circuits(changed)
            for name,definition in before.items():
                if name!=taper.TOP:self.assertEqual(after[name],definition)
            rows={r[0]:r for r in before[taper.TOP][1]};newrows={r[0]:r for r in after[taper.TOP][1]}
            self.assertEqual(rows.keys(),newrows.keys())
            for name,row in rows.items():
                if name!='XLS':self.assertEqual(newrows[name],row)
            self.assertEqual(newrows['XLS'][1],rows['XLS'][1])

    def test_parallel_units_provide_three_stages_with_original_polarity(self):
        for variant,counts in taper.VARIANTS.items():
            defs=circuits(taper.transform(self.source(),variant));rows=defs[taper.SHIFT+'_'+variant][1]
            for branch,inn,out in [(0,'L','Q'),(1,'R','QB')]:
                chain=[inn,f'G{branch}_0',f'G{branch}_1',out]
                for stage,count in enumerate(counts):
                    selected=[r for r in rows if r[0].startswith(f'XB{branch}_S{stage}_')]
                    self.assertEqual(len(selected),count)
                    for row in selected:self.assertEqual(row[1:],([chain[stage],chain[stage+1],'VDDIO','VSS'],taper.UNIT,{}))
            self.assertEqual(defs[taper.UNIT][1][0][2],'sky130_fd_pr__pfet_g5v0d10v5')
            self.assertEqual(defs[taper.UNIT][1][1][2],'sky130_fd_pr__nfet_g5v0d10v5')

    def test_unsupported_original_or_duplicate_driver_cannot_be_transformed(self):
        source=self.source()
        for text,variant in [(source,'unknown'),(source.replace('XIT10 TOP PB','XREMOVED TOP PB'),'taper_16_32_64'),(taper.transform(source,'taper_16_32_64'),'taper_16_64_128')]:
            with self.assertRaises(ValueError):taper.transform(text,variant)


if __name__=='__main__':unittest.main()
