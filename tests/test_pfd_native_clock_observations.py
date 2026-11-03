from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import pfd_native_clock_observations as observation


class NativePFDClockObservations(unittest.TestCase):
    def fixture(self):
        definition='''UNITS DISTANCE MICRONS 1000 ;
COMPONENTS 2 ;
- ref_ff sky130_fd_sc_hd__dfrtp_4 + PLACED ( 1000 1000 ) N ;
- fb_ff sky130_fd_sc_hd__dfrtp_4 + PLACED ( 1000 3000 ) FS ;
END COMPONENTS
PINS 2 ;
- REF + NET REF + DIRECTION INPUT + PORT + LAYER met3 ( -300 -300 ) ( 300 300 ) + PLACED ( 300 1000 ) N ;
- FB + NET FB + DIRECTION INPUT + PORT + LAYER met3 ( -300 -300 ) ( 300 300 ) + PLACED ( 300 3000 ) N ;
END PINS
'''
        lef='MACRO sky130_fd_sc_hd__dfrtp_4\n ORIGIN 0 0 ;\n SIZE 1 BY 1 ;\nEND sky130_fd_sc_hd__dfrtp_4\n'
        ext='port "REF" 1 0 140 120 260 m3\nport "FB" 2 0 540 120 660 m3\nequiv "ref_conditioned" "ref_ff.CLK"\nequiv "fb_conditioned" "fb_ff.CLK"\n'
        res='';native=''
        for i,(side,y) in enumerate([('ref',220),('fb',620)]):
            for j,kind in enumerate(('nfet','pfet')):
                model='sky130_fd_pr__'+kind+'_01v8';box=f'220 {y+20*j} 221 {y+20*j+1}'
                ext+=f'device msubckt {model} {box} l=30 w=100 "BODY" "{side}_conditioned" 1 0 "D" 1 0 "S" 1 0\n'
                node=f'{side}_conditioned.t{j+3}'
                res+=f'device msubckt {model} {box} "BODY.t0" "{node}" 1 0 "D.t0" 1 0 "S.t0" 1 0\n'
                native+=f'X{i}{j} D {node} S BODY {model} w=1 l=.15\n'
        return definition,lef,ext,res,native

    def test_observes_every_actual_receiving_cmos_gate_separately(self):
        result=observation.derive(*self.fixture())
        self.assertEqual(result['coordinate_scale_dbu_per_grid'],[5,1])
        for side in ('REF','FB'):
            group=result['observations'][side+'_FF_CLK']
            self.assertEqual(len(group['native_nodes']),2);self.assertEqual(len(group['mos_gates']),2)
            self.assertTrue(all('.t' in n for n in group['native_nodes']))
        self.assertFalse(result['route_matching_verified']);self.assertFalse(result['physical_admission'])
        probes=observation.probes(result,'XP:XPHYS:')
        self.assertEqual(len(probes),4);self.assertTrue(all(v.startswith('XP:XPHYS:') for v in probes.values()))
        with self.assertRaises(ValueError):observation.probes(result,'guessed_prefix')

    def test_wrong_scale_pin_shape_or_routing_layer_are_rejected(self):
        definition,lef,ext,res,native=self.fixture()
        for changed in [ext.replace('0 140 120 260','0 140 121 260'),ext.replace('m3','m2'),ext.replace('0 540 120 660','0 541 120 661')]:
            with self.assertRaises(ValueError):observation.derive(definition,lef,changed,res,native)

    def test_pad_substitution_lost_native_branch_or_cross_clock_short_fails(self):
        definition,lef,ext,res,native=self.fixture()
        with self.assertRaises(ValueError):observation.derive(definition,lef,ext,res,native.replace('ref_conditioned.t3','REF'))
        with self.assertRaises(ValueError):observation.derive(definition,lef,ext,res.replace('ref_conditioned.t3','REF'),native)
        with self.assertRaises(ValueError):observation.derive(definition,lef,ext,res.replace('ref_conditioned.t3','fb_conditioned.t3'),native)

    def test_missing_or_ambiguous_device_geometry_and_incomplete_input_pair_fail(self):
        definition,lef,ext,res,native=self.fixture()
        for changed in [res.replace('220 220 221 221','221 220 222 221'),res+res.splitlines()[0]+'\n']:
            with self.assertRaises(ValueError):observation.derive(definition,lef,ext,changed,native)
        ext='\n'.join(l for l in ext.splitlines() if not ('pfet' in l and 'ref_conditioned' in l))
        with self.assertRaises(ValueError):observation.derive(definition,lef,ext,res,native)

    def test_wrong_pin_equivalence_or_clock_load_outside_receiving_cell_fails(self):
        definition,lef,ext,res,native=self.fixture()
        with self.assertRaises(ValueError):observation.derive(definition,lef,ext.replace('ref_ff.CLK','other.CLK'),res,native)
        ext=ext.replace('220 220 221 221','900 220 901 221')
        with self.assertRaises(ValueError):observation.derive(definition,lef,ext,res,native)

    def test_changed_cell_master_origin_or_unsupported_orientation_fails(self):
        definition,lef,ext,res,native=self.fixture()
        with self.assertRaises(ValueError):observation.derive(definition.replace('dfrtp_4','dfrtp_1'),lef,ext,res,native)
        with self.assertRaises(ValueError):observation.derive(definition,lef.replace('ORIGIN 0 0','ORIGIN 1 0'),ext,res,native)
        with self.assertRaises(ValueError):observation.derive(definition.replace('1000 1000 ) N','1000 1000 ) E'),lef,ext,res,native)
