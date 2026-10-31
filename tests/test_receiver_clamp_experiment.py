# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from layout import circuits,flatten
from receiver_clamp_experiment import source_variant,TOP,MID
ROOT=Path(__file__).resolve().parents[1]


class ReceiverDecisionClamp(unittest.TestCase):
    def test_only_the_local_tracked_reference_and_two_resistors_are_added(self):
        source=(ROOT/'analog/openlvds.spice').read_text()
        before=circuits(source_variant(source,False));after=circuits(source_variant(source,True))
        self.assertEqual(set(before),set(after))
        for name in before:
            if name!=TOP:self.assertEqual(before[name],after[name])
        self.assertEqual(before[TOP][0],after[TOP][0])
        old={r[0]:r for r in before[TOP][1]};new={r[0]:r for r in after[TOP][1]}
        self.assertEqual(set(new)-set(old),{'XTRACK','XCLAMP0','XCLAMP1'})
        for name in old:self.assertEqual(old[name],new[name])
        self.assertEqual(new['XTRACK'][1:3],(['CO_TRACK','CO_TRACK','VDDD','VSS'],MID))
        for name in ['XCLAMP0','XCLAMP1']:
            self.assertEqual(new[name][1:],(['CO','CO_TRACK','VSS'],
                'sky130_fd_pr__res_high_po_0p35',dict(w='0.35',l='1.25')))

    def test_replica_has_same_inverter_ratio_and_no_extra_external_terminal(self):
        source=(ROOT/'analog/openlvds.spice').read_text();defs=circuits(source_variant(source,True))
        ports,devices=flatten(defs,TOP)
        self.assertEqual(ports,circuits(source)[TOP][0])
        first=[d for d in devices if '__XIB0__' in d['name']]
        reference=[d for d in devices if '__XTRACK__' in d['name']]
        for model in ['pfet','nfet']:
            w0=sum(float(d['params']['w']) for d in first if model in d['model'])
            wr=sum(float(d['params']['w']) for d in reference if model in d['model'])
            self.assertEqual(wr,2*w0)
        self.assertTrue(all(d['nodes'][0]==d['nodes'][1] for d in reference))
