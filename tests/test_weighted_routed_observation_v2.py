# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from weighted_routed_observation_v2 import observations


def fixture():
    rows=['.subckt bank IN OUT VPWR VGND'];ext=[]
    selections=[('coarse',i,[f'coarse_buffer{i}.X',f'forward{i}.B',f'turn{i}.A_N',f'pass{i}.B']) for i in range(15)]
    selections += [(kind,i,pins) for i in range(5) for kind,pins in [
        ('fine',[f'fine_buffer{i}.X',f'fine_inverse{i}.A',f'fine{i}.EN']),
        ('fine_b',[f'fine_inverse{i}.Y',f'fine{i}.ENB'])]]
    for kind,bit,pins in selections:
        base=f'route_{kind}_{bit}'
        ext += [f'node "{base}" 0 0']+[f'equiv "{base}" "{p}"' for p in pins]
        rows += [f'Ra_{base} {base} {base}.n0 1',f'Rb_{base} {base}.n0 {base}.t0 2',f'C_{base} {base}.t0 VGND 1f']
    rows += ['Xn OUT route_fine_0.t0 VGND VGND sky130_fd_pr__nfet_01v8 w=1 l=.15',
             'Xp VPWR route_fine_b_0.t0 OUT VPWR sky130_fd_pr__pfet_01v8_hvt w=1 l=.15',
             'Xd OUT VGND sky130_fd_pr__diode_pw2nd_05v5 area=1',
             'Xc OUT VGND sky130_fd_pr__cap_mim_m3_1 w=4 l=4','.ends bank']
    return '\n'.join(rows)+'\n','\n'.join(ext)+'\n'


class RoutedObservationsTests(unittest.TestCase):
    def test_canonical_names_can_differ_from_native_pins_and_every_distributed_node_survives(self):
        text,ext=fixture();r=observations(text,ext,'bank')
        self.assertEqual(len(r['controls']),25)
        for c in r['controls']:
            b=c['canonical_net'];self.assertEqual(set(c['nodes']),{'XD:'+b,'XD:'+b+'.n0','XD:'+b+'.t0'})
        self.assertEqual(r['devices'][0]['terminals'],['OUT','XD:route_fine_0.t0','0','0'])
        self.assertEqual(r['devices'][1]['terminals'],['VDD','XD:route_fine_b_0.t0','OUT','VDD'])
        self.assertEqual(sum(r['primitive_counts'].values()),4)

    def test_missing_pin_alias_or_disconnected_or_shorted_control_is_rejected(self):
        text,ext=fixture()
        bad_alias=ext.replace('equiv "route_fine_0" "fine0.EN"','equiv "other" "fine0.EN"')
        missing=ext.replace('equiv "route_fine_0" "fine0.EN"\n','')
        disconnected=text.replace('Rb_route_fine_0 route_fine_0.n0 route_fine_0.t0 2\n','')
        shorted=text.replace('.ends bank','Rshort route_fine_0 route_fine_b_0 1\n.ends bank')
        for net,aliases in [(text,bad_alias),(text,missing),(disconnected,ext),(shorted,ext)]:
            with self.assertRaises(ValueError):observations(net,aliases,'bank')

    def test_unknown_native_device_cannot_escape_terminal_coverage(self):
        text,ext=fixture()
        for bad in [text.replace('sky130_fd_pr__nfet_01v8','unknown_mos'),
                    text.replace('Xn OUT route_fine_0.t0 VGND VGND','Xn OUT route_fine_0.t0 VGND')]:
            with self.assertRaises(ValueError):observations(bad,ext,'bank')


if __name__=='__main__':unittest.main()
