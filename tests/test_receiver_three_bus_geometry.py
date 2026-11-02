# SPDX-License-Identifier: GPL-3.0-only
import math
from pathlib import Path
import re
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import layout_receiver_gain_balance as baseline
import layout_receiver_gain_balance_three_bus as local
import probe_receiver_gain_balance_three_bus as probe
from layout import primitive_key


class ThreeBusGeometry(unittest.TestCase):
    def draw(self,tmp):
        source=baseline.clocks.source_variant((baseline.ROOT/'analog/openlvds.spice').read_text(),True,'decision_pair_w32')
        ports,devices=baseline.physical.flatten(baseline.physical.circuits(source),baseline.TOP)
        library={}
        pins=dict(D=('metal1',-1.,7.),G=('metal1',0.,4.),S=('metal1',1.,7.),B=('metal1',-2.,1.),
                  R1=('metal1',-1.,4.),R2=('metal1',1.,4.))
        for device in devices:
            key=primitive_key(device)
            if key not in library:library[key]=('cell_'+str(len(library)),dict(bbox=[-3.,-2.,3.,9.],ports=pins))
        old=tmp/'old';new=tmp/'new';old.mkdir();new.mkdir()
        before=baseline.geometry.draw_macro(old,baseline.TOP,ports,devices,library)
        after=local.geometry.draw_macro(new,local.TOP,ports,devices,library)
        return old,new,before,after,devices

    def test_device_schematic_placements_and_public_ports_are_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            old,new,before,after,devices=self.draw(Path(tmp))
            self.assertEqual(len(devices),80)
            self.assertEqual(before,after)
            self.assertEqual((old/(baseline.TOP+'.sch.spice')).read_bytes(),(new/(local.TOP+'.sch.spice')).read_bytes())
            placed=lambda text:[s for s in text.splitlines() if s.startswith(('use ','transform ','box '))]
            self.assertEqual(placed((old/(baseline.TOP+'.mag')).read_text()),placed((new/(local.TOP+'.mag')).read_text()))

    def test_only_three_internal_labels_move_into_the_existing_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            old,new,before,after,devices=self.draw(Path(tmp))
            labels=lambda folder:{m[5]:(int(m[1]),int(m[2])) for m in re.finditer(
                r'^rlabel metal3 (\d+) (\d+) (\d+) (\d+) 0 (\S+)$',(folder/(local.TOP+'.mag')).read_text(),re.M)}
            a,b=labels(old),labels(new)
            changed={n for n in a if a[n]!=b[n]}
            self.assertEqual(changed,{local.TOP+'__'+n for n in local.geometry.LOCAL_BUSES})
            rows=math.ceil(sum(not local.geometry.critical(d) for d in devices)/4)
            row_base=8.+rows*(11.+10.)
            for leaf in local.geometry.LOCAL_BUSES:
                y=b[local.TOP+'__'+leaf][1]*local.geometry.GRID
                self.assertLess(y,row_base)
                self.assertGreaterEqual(y,row_base-4.000001)

    def test_all_existing_critical_classifications_and_boost_segments_are_retained(self):
        source=baseline.clocks.source_variant((baseline.ROOT/'analog/openlvds.spice').read_text(),True,'decision_pair_w32')
        _,devices=baseline.physical.flatten(baseline.physical.circuits(source),baseline.TOP)
        self.assertEqual([baseline.geometry.critical(d) for d in devices],[local.geometry.critical(d) for d in devices])
        self.assertTrue(all(local.geometry.critical(d) for d in devices if '__XRBC' in d['name']))

    def test_route_profile_is_distinct_and_rejected_source_variant_cannot_select_it(self):
        self.assertNotEqual(local.profile('decision_pair_w32'),baseline.profile('decision_pair_w32'))
        with self.assertRaises(ValueError):local.profile('restore_p4_n8')

    def test_native_profile_cannot_borrow_original_route_and_restores_on_failure(self):
        model=' '.join('openlvds_receiver_core__'+n for n in ['NL','NR','PL','PR','NT','PT'])
        n=probe.native;previous=n.PROFILE,n.CODE,n.source_gate,n.source_variant,n.replay_deck,n.lease
        with self.assertRaises(RuntimeError):
            with probe.profile('decision_pair_w32',model):
                n.validate_profile(local.profile('decision_pair_w32'))
                with self.assertRaises(ValueError):n.validate_profile(baseline.profile('decision_pair_w32'))
                self.assertIn('receiver_three_bus_geometry.py',n.CODE)
                raise RuntimeError('injected')
        self.assertEqual((n.PROFILE,n.CODE,n.source_gate,n.source_variant,n.replay_deck,n.lease),previous)


if __name__=='__main__':
    unittest.main()
