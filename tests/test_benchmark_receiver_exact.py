# SPDX-License-Identifier: GPL-3.0-only
import json
import tempfile
from unittest.mock import patch
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import benchmark_receiver_exact as benchmark
from exact_rc_candidate import parse,static_signature


class ExactReceiverBenchmark(unittest.TestCase):
    def test_both_polarities_and_extra_or_missing_edges_are_checked(self):
        t=np.linspace(0,80e-9,8001);v=.9+.8*np.sin(2*np.pi*400e6*t+.3)
        self.assertTrue(all(r['passed'] for r in benchmark.edges(t,v,t+5e-12,v)))
        self.assertFalse(all(r['passed'] for r in benchmark.edges(t,v,t+30e-12,v)))
        self.assertFalse(all(r['passed'] for r in benchmark.edges(t,v,t,np.full(len(t),1.8))))
        self.assertTrue(all(r['passed'] for r in benchmark.edges(t,np.zeros(len(t)),t,np.zeros(len(t)))))

    def test_complete_original_duration_is_required(self):
        wave=np.column_stack([np.arange(3),[0,40e-9,80e-9],[0,1,0]])
        benchmark.complete(wave)
        for changed in [wave[:2],wave[[0,0,2]],wave+np.nan]:
            with self.assertRaises(ValueError):benchmark.complete(changed)

    def test_resistor_substitution_preserves_all_devices_caps_and_unrelated_blocks(self):
        core='''.subckt openlvds_receiver_core INP INN Q VREF PB NB VDDIO VDDD VSS
R0 INP Q 1k
C0 Q VSS 1f
X0 Q INP VSS VSS sky130_fd_pr__nfet_01v8 w=1 l=.15
.ends openlvds_receiver_core
'''
        extra='''.subckt lvds_bias PB NB VDDIO VSS
R1 PB NB 1k
.ends lvds_bias
.subckt openlvds_ddr_rx D C Q VSS
R2 D Q 1k
.ends openlvds_ddr_rx
'''
        signature=static_signature(parse(core));candidate=core.replace('R0 INP Q 1k','R0 INP intermediate 500\nR1 intermediate Q 500')
        changed=benchmark.substitute(core+extra,candidate,signature)
        self.assertIn(extra,changed);self.assertIn('intermediate',changed)
        for bad in [candidate.replace('1f','2f'),candidate.replace('w=1','w=2'),candidate.replace('INN Q VREF','INN Q VREF EXTRA')]:
            with self.assertRaises(ValueError):benchmark.substitute(core+extra,bad,signature)

    def test_partial_output_cannot_be_retried_or_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(benchmark,'ROOT',Path(tmp)), patch.object(benchmark,'provenance',return_value={}), patch.object(benchmark,'lease') as lease, patch.object(benchmark.subprocess,'run') as run:
            root=Path(tmp)/'build/diagnostics/receiver_exact_benchmark/test';root.mkdir(parents=True)
            (root/'library.spice').write_text('preserved library')
            tasks=[]
            for case in benchmark.CASES:
                folder=root/case;folder.mkdir();(folder/'bench.cir').write_text('original fixture')
                tasks.append(dict(id=case,deck_sha256=benchmark.sha(folder/'bench.cir')))
            (root/'captured/bench.raw').write_bytes(b'partial numerical evidence')
            manifest=dict(identity=dict(priority=2,workers=1,no_outer_lease=True,code={},inputs={},simulator_provenance={},parent='unused'),tasks=tasks,library_sha256=benchmark.sha(root/'library.spice'))
            (root/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'Partial exact receiver'):benchmark.run(root)
            lease.assert_not_called();run.assert_not_called()
            self.assertEqual((root/'captured/bench.raw').read_bytes(),b'partial numerical evidence')
            self.assertEqual(json.loads((root/'state.json').read_text())['status'],'held_for_diagnosis')

    def test_simulator_runtime_must_be_complete_finite_and_unambiguous(self):
        self.assertEqual(benchmark.elapsed('Total elapsed time (seconds) = 10.25\n'),10.25)
        for text in ['', 'Total elapsed time (seconds) = 0', 'Total elapsed time (seconds) = 1e999', 'Total elapsed time (seconds) = 1\nTotal elapsed time (seconds) = 2']:
            with self.assertRaises(ValueError):benchmark.elapsed(text)


if __name__=='__main__':unittest.main()
