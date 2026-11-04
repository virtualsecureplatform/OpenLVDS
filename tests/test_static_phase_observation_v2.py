# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import observe_static_phase_backend_v3 as observation
import diagnose_common_dcc_startup_v2 as diagnosis
from native_clock_components_v2 import definitions


class StaticCounterObservationTests(unittest.TestCase):
    def test_added_observation_ports_do_not_change_mask_geometry_or_native_source_body(self):
        text='magic\ntech sky130A\nmagscale 1 2\n<< metal5 >>\nrect 0 0 100 100\n<< labels >>\nrlabel metal5 0 0 0 0 0 CLK\nport 1 nsew\n<< end >>\n'
        points={n:dict(x_um=1,y_um=2) for n in observation.OBSERVATIONS}
        changed,_=observation.add_observations(text,points)
        self.assertEqual(changed.split('<< labels >>')[0],text.split('<< labels >>')[0])
        self.assertEqual(changed.count('rect '),1);self.assertEqual(changed.count('port '),6)
        original='.subckt '+observation.parent_build.NAME+' '+' '.join(observation.parent_build.PORTS)+'\nX0 A B Y gate w=1\n.ends '+observation.parent_build.NAME+'\n'
        annotated=observation.source(original)
        self.assertEqual(annotated.splitlines()[1],original.splitlines()[1])
        self.assertEqual(annotated.splitlines()[0].split()[2:],observation.PORTS)
        with self.assertRaises(ValueError):observation.source(original.replace(' CLK ',' notCLK '))

    def test_master_observers_follow_only_actual_resistor_connected_output_terminals(self):
        text='.subckt gate A B Y VPWR VGND\nR0 Y yd 2\nR1 Y yp 3\nX0 yd A mid VGND sky130_fd_pr__nfet_01v8 w=1 l=.15\nX1 mid B VGND VGND sky130_fd_pr__nfet_01v8 w=1 l=.15\nX2 yp B VPWR VPWR sky130_fd_pr__pfet_01v8 w=1 l=.15\nC0 mid Y 2f\n.ends\n'
        self.assertEqual(diagnosis.output_drains(definitions(text),'gate'),['yd','yp'])
        with self.assertRaises(ValueError):diagnosis.output_drains(definitions(text),'gate','missing')


if __name__=='__main__':unittest.main()
