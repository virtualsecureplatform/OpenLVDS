# SPDX-License-Identifier: GPL-3.0-only
from collections import Counter
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_differential_restore as factory
import receiver_differential_restore_geometry as geometry
import layout_receiver_differential_restore as physical
import probe_receiver_differential_restore as probe
from layout import circuits,flatten,primitive_key,schematic_text


class DifferentialGeometry(unittest.TestCase):
    def design(self,variant):
        source=factory.source_variant((physical.ROOT/'analog/openlvds.spice').read_text(),variant)
        return flatten(circuits(source),factory.TOP)

    def test_functional_amplifier_reference_and_resistor_devices_are_all_local(self):
        for variant,count in [('track_t8_r7',87),('track_t16_r7',90)]:
            ports,devices=self.design(variant)
            self.assertEqual(len(devices),count); self.assertEqual(len(ports),9)
            critical=[d for d in devices if any(n.endswith('__'+s) for n in d['nodes'] for s in geometry.FUNCTIONAL_NETS)]
            self.assertGreaterEqual(len(critical),18)
            self.assertTrue(all(geometry.critical(d) for d in critical))
            ordered=geometry.ordered(devices)
            self.assertEqual(Counter(d['name'] for d in ordered),Counter(d['name'] for d in devices))
            stages=[geometry.stage(d) for d in ordered if geometry.critical(d)]
            self.assertEqual(stages,sorted(stages))
            for leaf in geometry.LOCAL_BUSES:
                connected=[d for d in devices if any(n.endswith('__'+leaf) for n in d['nodes'])]
                self.assertTrue(connected);self.assertTrue(all(geometry.critical(d) for d in connected))

    def test_new_geometry_keeps_exact_flattened_circuit_and_all_public_ports(self):
        pins=dict(D=('metal1',-1.,7.),G=('metal1',0.,4.),S=('metal1',1.,7.),B=('metal1',-2.,1.),
                  R1=('metal1',-1.,4.),R2=('metal1',1.,4.))
        for variant in physical.clocks.VARIANTS:
            ports,devices=self.design(variant); library={}
            for d in devices:
                key=primitive_key(d)
                if key not in library:library[key]=('cell_'+str(len(library)),dict(bbox=[-3.,-2.,3.,9.],ports=pins))
            with tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp);info=geometry.draw_macro(out,factory.TOP,ports,devices,library)
                self.assertEqual(set(info['ports']),set(ports))
                # Device order can change; normalized flattened connectivity cannot.
                parse=lambda text:Counter(line for line in text.splitlines() if line.startswith('X'))
                self.assertEqual(parse((out/(factory.TOP+'.sch.spice')).read_text()),parse(schematic_text(factory.TOP,ports,devices)))
                mag=(out/(factory.TOP+'.mag')).read_text()
                self.assertEqual(len(re.findall(r'^use ',mag,re.M)),len(devices))
                self.assertEqual(len(re.findall(r'^port ',mag,re.M)),9)

    def test_control_and_old_source_family_cannot_select_new_geometry(self):
        with self.assertRaises(ValueError):geometry.ordered(self.design('control')[1])
        for variant in ['control','decision_pair_w32','restore_p4_n8']:
            with self.assertRaises(ValueError):physical.profile(variant)

    def test_old_source_clock_family_cannot_admit_new_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); matrix=root/'build/diagnostics/receiver_differential_restore_matrix/matrix'
            clock=root/'build/diagnostics/receiver_clamp/old';clock.mkdir(parents=True)
            (clock/'manifest.json').write_text(json.dumps(dict(identity=dict(
                gain_balance_variant='decision_pair_w32',static_screen=str(matrix.relative_to(root))),tasks=[])))
            with patch.object(physical,'ROOT',root), patch.object(physical.clocks,'static_gate',return_value={}), patch.object(physical.clocks,'run') as run:
                with self.assertRaisesRegex(ValueError,'Complete all three'):
                    physical.source_gate(matrix,clock,'track_t8_r7')
                run.assert_not_called()

    def test_native_profile_requires_functional_nodes_and_restores_after_failure(self):
        model=' '.join('openlvds_receiver_core__'+n for n in ['NL','NR','PL','PR','NT','PT','AMP_CT','AMP_L','AMP_OUT','CO_TRACK'])
        n=probe.native;before=n.PROFILE,n.CODE,n.source_gate,n.source_variant,n.replay_deck,n.lease
        with self.assertRaises(ValueError):probe.observation_nodes(model.replace('openlvds_receiver_core__AMP_OUT',''))
        with self.assertRaises(RuntimeError):
            with probe.profile('track_t8_r7',model) as nodes:
                self.assertEqual(len(nodes),10)
                n.validate_profile(physical.profile('track_t8_r7'))
                with self.assertRaises(ValueError):n.validate_profile(physical.profile('track_t16_r7'))
                deck='.TRAN 5p 80n 0 1p\n.print tran V(RXCLOCK)\n'
                changed=n.replay_deck(deck,1)
                for node in nodes:self.assertIn('V('+node+')',changed)
                self.assertEqual(n.replay_deck(changed,1),changed)
                self.assertIn('receiver_differential_restore_geometry.py',n.CODE)
                raise RuntimeError('injected')
        self.assertEqual((n.PROFILE,n.CODE,n.source_gate,n.source_variant,n.replay_deck,n.lease),before)
