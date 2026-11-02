# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import isolate_tx_decap as isolation


class MappedDecapIsolation(unittest.TestCase):
    def fixture(self):
        raw=['.subckt openlvds_tx_core VGND VPWR','RRAIL VGND VGND.n1 214','CPLATE VPWR VGND 1f']
        ext=['port "tx_serial" 1 19880 9528 20000 9648 m3']
        definition=['UNITS DISTANCE MICRONS 1000 ;','- tx_serial + NET tx_serial + DIRECTION OUTPUT + USE SIGNAL',
                    '+ PORT + LAYER met3 ( -300 -300 ) ( 300 300 ) + PLACED ( 99700 47940 ) N ;']
        for i in range(56):
            definition += [f'- PHY_EDGE_ROW_{i}_Left_{i} sky130_fd_sc_hd__decap_3 + SOURCE DIST + FIXED ( {2000*i} 0 ) N ;']
            for j,(model,width,rail,gate) in enumerate([('nfet_01v8','.55','VGND','VPWR'),('pfet_01v8_hvt','.87','VPWR','VGND')]):
                d,g,s,b=f'{rail}.d{i}',f'{gate}.g{i}',f'{rail}.s{i}',f'{rail}.b{i}'
                raw += [f'X{i}_{j} {d} {g} {s} {b} sky130_fd_pr__{model} w=0{width} l=0.59']
                ext += [f'device msubckt sky130_fd_pr__{model} {400*i+10} 10 {400*i+11} 11 "{b}" "{g}" 236 0 "{s}" 110 0 "{d}" 110 1']
        raw += ['.ends openlvds_tx_core']
        lef='MACRO sky130_fd_sc_hd__decap_3\n SIZE 1.380 BY 2.720 ;\nEND sky130_fd_sc_hd__decap_3\n'
        cell='.subckt sky130_fd_sc_hd__decap_3 VGND VNB VPB VPWR\nX0 VPWR VGND VPWR VPB sky130_fd_pr__pfet_01v8_hvt w=870000u l=590000u\nX1 VGND VPWR VGND VNB sky130_fd_pr__nfet_01v8 w=550000u l=590000u\n.ends sky130_fd_sc_hd__decap_3\n'
        return '\n'.join(raw)+'\n','\n'.join(ext),'\n'.join(definition),lef,cell

    def test_every_device_maps_uniquely_and_all_wire_rc_is_preserved(self):
        args=self.fixture();mapped=isolation.mapped_devices(*args)
        self.assertEqual(len(mapped),112)
        result=isolation.remove_mapped(args[0],mapped)
        self.assertIn('RRAIL VGND VGND.n1 214',result)
        self.assertIn('CPLATE VPWR VGND 1f',result)
        self.assertFalse(any(l.startswith('X') for l in result.splitlines()))

    def test_missing_or_ambiguous_cell_and_mismatched_coordinates_are_rejected(self):
        raw,ext,definition,lef,cell=self.fixture()
        for changed in [definition.replace('PHY_EDGE_ROW_0_Left_0','OTHER'),definition.replace('( 2000 0 )','( 0 0 )'),definition.replace('99700 47940','99700 47945')]:
            with self.assertRaises(ValueError):isolation.mapped_devices(raw,ext,changed,lef,cell)

    def test_wrong_rail_or_pdk_model_cannot_be_removed(self):
        raw,ext,definition,lef,cell=self.fixture()
        with self.assertRaises(ValueError):isolation.mapped_devices(raw.replace('VPWR.g0','BAD.g0'),ext.replace('VPWR.g0','BAD.g0'),definition,lef,cell)
        with self.assertRaises(ValueError):isolation.mapped_devices(raw,ext,definition,lef,cell.replace('550000u','600000u'))
        mapped=isolation.mapped_devices(raw,ext,definition,lef,cell)
        with self.assertRaises(ValueError):isolation.remove_mapped(raw,mapped+[mapped[0]])


if __name__=='__main__':unittest.main()
