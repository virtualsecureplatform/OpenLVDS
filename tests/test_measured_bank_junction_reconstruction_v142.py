# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic full-census tests for repair boundaries, never PHY evidence."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import measured_bank_junction_reconstruction_v142 as p
import test_measured_bank_fine_partition_v139 as fixture


class MeasuredBankJunctionReconstructionTests(unittest.TestCase):
    def measurements(self):return fixture.MeasuredFinePartitionTests().measurements()

    def bank(self,profile='b2'):
        text=fixture.MeasuredFinePartitionTests().bank().replace('w=.42 l=.15','w=.42 l=.15 ad=.1218 as=.1218 pd=1.42 ps=1.42').replace('w=.84 l=.15','w=.84 l=.15 ad=.2436 as=.2436 pd=2.26 ps=2.26')
        count=(1453 if profile=='b2' else 1773)-155
        extras=[f'XD{k} NODE E0 VGND VGND sky130_fd_pr__nfet_01v8_lvt w=.65 l=.15 ad=.08775 as=.08775 pd=.92 ps=.92' for k in range(count)]
        extras += [f'XextraC{k} NODE VGND {p.fine.MIM} w=2 l=2' for k in range(11)]
        return text.replace('.ends bank','\n'.join(extras+['Rwire NODE rwire 1.25 $ keep','Cwire rwire VGND 2f $ keep','.ends bank']))

    def test_both_full_censuses_repair_only_capacitors_and_are_idempotent(self):
        for profile,count in [('b2',1453),('b3',1773)]:
            text=self.bank(profile).replace('ad=0 as=0','ad=0 as=99',1)
            corrected,r=p.reconstruct(text,'bank',self.measurements(),profile)
            self.assertEqual((r['identified_capacitor_mos'],r['corrected_devices'],r['corrected_fields']),(62,62,248))
            self.assertEqual(r['native_census']['native_mos'],count)
            self.assertEqual(p.signature(text,'bank'),p.signature(corrected,'bank'))
            self.assertEqual(p.passive_lines(text),p.passive_lines(corrected))
            self.assertTrue(r['all_noncapacitor_devices_and_parameters_unchanged'])
            self.assertEqual(r['passive_record_count'],2);self.assertFalse(r['joint_rc_qualified']);self.assertFalse(r['qualified_phy'])
            again,proof=p.reconstruct(corrected,'bank',self.measurements(),profile)
            self.assertEqual(again,corrected);self.assertEqual(proof['corrected_devices'],0)

    def test_multiline_cards_and_inline_comments_preserve_every_other_byte(self):
        text=self.bank().replace('XCN0 VGND q0 VGND VGND '+p.fine.N+' w=1.26 l=.15 ad=0 as=0 pd=0 ps=0',
             'XCN0 VGND q0 VGND VGND '+p.fine.N+' w=1.26 l=.15 $ ad=comment\n+ ad=0 as=99\n+ pd=0 ps=0')
        corrected,r=p.reconstruct(text,'bank',self.measurements(),'b2')
        self.assertIn('$ ad=comment\n+ ad=.3654 as=.3654\n+ pd=3.1 ps=3.1',corrected)
        for line in text.splitlines(keepends=True):
            if line.lstrip().startswith(('XD','XextraC','Rwire','Cwire')):self.assertIn(line,corrected)
        self.assertEqual(r['corrected_devices'],62)

    def test_missing_measurement_asymmetry_negative_fields_and_ambiguous_tokens_refuse(self):
        text=self.bank();asymmetric=deepcopy(self.measurements());asymmetric[0]['actual']['params']['ad']='.4'
        cases=[(text,self.measurements()[:1]),(text,asymmetric),(text.replace('ad=0','ad=-1',1),self.measurements()),
               (text.replace('ad=0','ad=0 ad=0',1),self.measurements())]
        for source,rows in cases:
            with self.subTest(source=source[:30]),self.assertRaises(ValueError):p.reconstruct(source,'bank',rows,'b2')

    def test_wrong_census_hierarchy_or_fine_topology_cannot_be_repaired(self):
        text=self.bank()
        for source in [text.replace('w=1.26','w=1.25',1),text.replace('.ends bank','.ends bank\n.subckt second A B\n.ends second'),
                       '\n'.join(line for line in text.splitlines() if not line.startswith('XD0 '))]:
            with self.subTest(source=source[:30]),self.assertRaises(ValueError):p.reconstruct(source,'bank',self.measurements(),'b2')
        with self.assertRaisesRegex(ValueError,'census'):p.reconstruct(text,'bank',self.measurements(),'b3')


if __name__=='__main__':unittest.main()
