# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_measured_gang_fine_v127 as p


class MeasuredGangFineDiagnosticTests(unittest.TestCase):
    def test_fixture_retains_full_time_controls_and_every_new_native_terminal(self):
        spec=dict(p.zero.spec(),profile='b2',coarse=0,fine=31)
        nodes=['XD:Xgroup_compound0:X0:d','XD:Xgroup_compound0:X0:g','XD:Xgroup_compound0:X0:s','XD:Xgroup_compound0:X0:b']
        obs=dict(devices=[dict(terminals=nodes)],controls=[dict(node='XD:en1_0')])
        i=dict(spec=spec,ports=['IN','OUT','VPWR','VGND'],model='/model.lib',observations=obs)
        text=p.fixture(Path('/fixture'),i)
        self.assertIn('.tran 2p 20n 0 2p\n',text)
        self.assertIn('.include "/fixture/bank.spice"',text)
        self.assertIn('VE0 E0 0 1.8',text);self.assertIn('VE30 E30 0 1.8',text)
        for node in [*nodes,'XD:en1_0']:self.assertIn('V('+node+')',text)
        self.assertIn('XD IN OUT VDD 0 '+p.circuit.name('b2'),text)

    def test_failed_or_wrong_fine_parent_is_rejected_before_building_child_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            case=Path(tmp)/'0';case.mkdir()
            for error,fine in [('failed',31),(None,30)]:
                spec=dict(p.zero.spec(),profile='b2',coarse=0,fine=fine);task=dict(id='0',spec=spec)
                row=dict(task=task,spec=spec,error=error,result=dict(static_native_screen_passed=True,output_slew_domain_passed=True))
                (case/'summary.json').write_text(json.dumps(row))
                with patch.object(p.parent_producer,'bound',return_value=dict(identity={},tasks=[task])),patch.object(p.circuit,'transform_existing') as build:
                    with self.assertRaisesRegex(ValueError,'complete safe'):p.prepare(case)
                    build.assert_not_called()


if __name__=='__main__':unittest.main()
