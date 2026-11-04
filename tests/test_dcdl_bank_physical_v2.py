# SPDX-License-Identifier: GPL-3.0-only
import json
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import harden_dcdl_bank_v2 as physical


class WholeBankPhysicalTests(unittest.TestCase):
    def fixture(self):
        rows=[]
        for c in physical.bank.instances():
            pins=dict(c['pins'])
            if c['model'].startswith(physical.bank.native.SC):pins.update(VPWR='VPWR',VPB='VPWR',VGND='VGND',VNB='VGND')
            rows += [(c['name'],c['model'],p,n) for p,n in pins.items()]
        ports=['IN','OUT','VPWR','VGND',*physical.bank.native.controls(16,32)]
        return rows,ports

    def test_all_original_delay_control_and_power_connections_are_required(self):
        rows,ports=self.fixture();self.assertTrue(physical.connections_pass(rows,ports))
        broken=[(i,m,p,'wrong' if i=='merge0' and p=='A' else n) for i,m,p,n in rows]
        self.assertFalse(physical.connections_pass(broken,ports))
        missing=[r for r in rows if not(r[0]=='fine_unit0' and r[2]=='VSS')]
        self.assertFalse(physical.connections_pass(missing,ports))
        self.assertFalse(physical.connections_pass(rows,ports[:-1]))

    def test_constant_clones_are_allowed_but_unrequested_delay_buffers_are_not(self):
        rows,ports=self.fixture();sc=physical.bank.native.SC
        rows=[(i,m,p,'high_clone' if i=='merge15' and p=='B' else n) for i,m,p,n in rows]
        rows += [('tie_clone',sc+'conb_1','HI','high_clone'),('tie_clone',sc+'conb_1','LO','unused_low')]
        self.assertTrue(physical.connections_pass(rows,ports))
        self.assertFalse(physical.connections_pass(rows+[('repair',sc+'buf_1','A','IN')],ports))

    def test_nonfinite_sta_metrics_remain_visible_without_invalid_json(self):
        clean,paths=physical.sanitize(dict(a=0,b=dict(delay=math.inf),c=[-math.inf,math.nan]))
        self.assertEqual(paths,['/b/delay','/c/0','/c/1']);self.assertEqual(clean,dict(a=0,b=dict(delay=None),c=[None,None]))
        json.dumps(clean,allow_nan=False)

    def test_committed_physical_view_is_exactly_the_native_generator(self):
        self.assertEqual((physical.ROOT/'sky130/v2'/f'{physical.bank.name()}.v').read_text(),physical.bank.verilog())
        self.assertEqual((physical.ROOT/'sky130/v2/dcdl_mim_bank_blackboxes_v2.v').read_text(),physical.bank.blackboxes())


if __name__=='__main__':unittest.main()
