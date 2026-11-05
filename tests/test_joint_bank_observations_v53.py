# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import joint_bank_observations_v53 as p


class ExtractedControlMappingTests(unittest.TestCase):
    def fixture(self):
        plan=dict(cells=[dict(name='u_gate',model='gate')],placements={'u_gate':[1.,2.]})
        mag='magic\nmagscale 1 2\nuse gate gate_99\ntransform 1 0 200 0 1 400\n'
        graph=dict(top='bank',ports=['A','B'],cells=[dict(name='u_gate',model='gate',pins=dict(A='A',B='B'))])
        ext='port "A" 1\nequiv "A" "gate_99.A"\nport "B" 2\nequiv "B" "gate_99.B"\n'
        rc='.subckt bank A B\nR1 gate_99.A.t0 gate_99.B.t0 1\n.ends bank\n'
        return plan,mag,graph,ext,rc

    def test_instance_identity_comes_from_geometry(self):
        plan,mag,*_=self.fixture()
        self.assertEqual(p.instances(mag,plan),{'u_gate':'gate_99'})
        self.assertEqual(p.instances(mag.replace('gate_99','gate_1'),plan),{'u_gate':'gate_1'})

    def test_wrong_instance_location_and_orientation_are_rejected(self):
        plan,mag,*_=self.fixture()
        with self.assertRaisesRegex(ValueError,'differs'):p.instances(mag.replace('200 0 1 400','201 0 1 400'),plan)
        with self.assertRaisesRegex(ValueError,'rotated'):p.instances(mag.replace('transform 1 0','transform -1 0'),plan)

    def test_missing_instance_and_wrong_magic_scale_are_rejected(self):
        plan,mag,*_=self.fixture()
        with self.assertRaisesRegex(ValueError,'Missing'):p.instances('magscale 1 2\n',plan)
        with self.assertRaisesRegex(ValueError,'scale'):p.instances(mag.replace('magscale 1 2','magscale 1 1'),plan)

    def test_resistor_short_between_distinct_logical_controls_is_rejected(self):
        plan,mag,g,ext,rc=self.fixture()
        with self.assertRaisesRegex(ValueError,'different logical nets'):p.mapping(mag,ext,rc,g,plan)

    def test_missing_pin_alias_is_never_inferred(self):
        plan,mag,g,ext,rc=self.fixture()
        with self.assertRaisesRegex(ValueError,'Missing native extraction alias'):
            p.mapping(mag,ext.replace('equiv "B" "gate_99.B"\n',''),rc,g,plan)

    def test_changed_public_port_order_is_rejected(self):
        plan,mag,g,ext,rc=self.fixture()
        with self.assertRaisesRegex(ValueError,'public order'):p.mapping(mag,ext,rc.replace('bank A B','bank B A'),g,plan)


if __name__=='__main__':unittest.main()
