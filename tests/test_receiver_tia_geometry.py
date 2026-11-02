# SPDX-License-Identifier: GPL-3.0-only
from collections import Counter
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_tia_restore as factory
import layout_receiver_tia_restore as physical
import probe_receiver_tia_restore as probe
from layout import circuits,flatten,primitive_key,schematic_text


class FeedbackInverterGeometry(unittest.TestCase):
    def design(self,variant):
        return flatten(circuits(factory.source_variant((physical.ROOT/'analog/openlvds.spice').read_text(),variant)),factory.TOP)

    def test_every_feedback_segment_is_local_and_reference_stays_folded(self):
        for variant,count in [('tia_r2',77),('tia_r4',79)]:
            ports,devices=self.design(variant);geometry=physical.geometry
            self.assertEqual(len(devices),count);self.assertEqual(len(ports),9)
            for d in devices:
                if '__XRFB' in d['name']:self.assertTrue(geometry.critical(d))
                if '__XTRACK__' in d['name']:self.assertFalse(geometry.critical(d))
            ordered=geometry.ordered(devices)
            self.assertEqual(Counter(d['name'] for d in ordered),Counter(d['name'] for d in devices))
            ranks=[geometry.stage(d) for d in ordered if geometry.critical(d)]
            self.assertEqual(ranks,sorted(ranks))
            for leaf in geometry.LOCAL_BUSES:
                connected=[d for d in devices if any(n.endswith('__'+leaf) for n in d['nodes'])]
                self.assertTrue(connected);self.assertTrue(all(geometry.critical(d) for d in connected))

    def test_exact_circuit_and_four_below_row_buses(self):
        pins=dict(D=('metal1',-1.,7.),G=('metal1',0.,4.),S=('metal1',1.,7.),B=('metal1',-2.,1.),R1=('metal1',-1.,4.),R2=('metal1',1.,4.))
        for variant in physical.clocks.VARIANTS:
            ports,devices=self.design(variant);library={}
            for d in devices:
                key=primitive_key(d)
                if key not in library:library[key]=('cell_'+str(len(library)),dict(bbox=[-3.,-2.,3.,9.],ports=pins))
            with tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp);geometry=physical.geometry;info=geometry.draw_macro(out,factory.TOP,ports,devices,library)
                parse=lambda text:Counter(line for line in text.splitlines() if line.startswith('X'))
                self.assertEqual(parse((out/(factory.TOP+'.sch.spice')).read_text()),parse(schematic_text(factory.TOP,ports,devices)))
                self.assertEqual(set(info['ports']),set(ports))
                mag=(out/(factory.TOP+'.mag')).read_text();labels={m[5]:int(m[2])*geometry.GRID for m in re.finditer(r'^rlabel metal3 (\d+) (\d+) (\d+) (\d+) 0 (\S+)$',mag,re.M)}
                ys=[labels[factory.TOP+'__'+leaf] for leaf in geometry.LOCAL_BUSES]
                for a,b in zip(ys,ys[1:]):self.assertAlmostEqual(b-a,1.2)
                self.assertEqual(len(re.findall(r'^use ',mag,re.M)),len(devices))
                self.assertEqual(len(re.findall(r'^port ',mag,re.M)),9)

    def test_only_declared_feedback_family_can_select_profile(self):
        with self.assertRaises(ValueError):physical.geometry.ordered(self.design('control')[1])
        for old in ['control','matched_t8_r7','track_t16_r7','decision_pair_w32']:
            with self.assertRaises(ValueError):physical.profile(old)

    def test_native_requires_every_feedback_probe_and_restores_profile(self):
        model=' '.join('openlvds_receiver_core__'+n for n in ['NL','NR','PL','PR','NT','PT','FB1','FB2','FB3'])
        n=probe.native;before=n.PROFILE,n.CODE,n.source_gate,n.source_variant,n.replay_deck,n.lease
        self.assertEqual(len(probe.observation_nodes('tia_r2',model)),7)
        self.assertEqual(len(probe.observation_nodes('tia_r4',model)),9)
        with self.assertRaises(ValueError):probe.observation_nodes('tia_r4',model.replace('openlvds_receiver_core__FB3',''))
        with self.assertRaises(RuntimeError):
            with probe.profile('tia_r2',model) as nodes:
                n.validate_profile(physical.profile('tia_r2'))
                with self.assertRaises(ValueError):n.validate_profile(physical.profile('tia_r4'))
                changed=n.replay_deck('.tran 5p 80n 0 1p\n.print tran V(RXCLOCK)\n',1)
                for node in nodes:self.assertIn('V('+node+')',changed)
                self.assertEqual(n.replay_deck(changed,1),changed)
                raise RuntimeError('injected')
        self.assertEqual((n.PROFILE,n.CODE,n.source_gate,n.source_variant,n.replay_deck,n.lease),before)
