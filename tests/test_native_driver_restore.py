# SPDX-License-Identifier: GPL-3.0-only
from contextlib import nullcontext
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_native_driver_restore as probe


class NativeDriverRestoration(unittest.TestCase):
    def model(self):
        return '.subckt openlvds_driver_core '+ ' '.join(probe.PORTS)+'\n'+ '\n'.join(
            f'R{i} openlvds_driver_core__{node} VSS 1k' for i,node in enumerate(
                ['XLS__AD','XLS__AB','XLS__L','XLS__R','DP','DN']))+'\n.ends openlvds_driver_core\n'

    def test_fixture_changes_only_include_observations_and_stricter_maximum_step(self):
        deck=('.include "/parent/library.spice"\nVIO VDDIO 0 3.3\n'
              '.nodeset V(XCT:openlvds_driver_core__SINK)=1.36\n'
              '.tran 20p 188.049n 0 100p\n.print tran V(CLK0)\n.end\n')
        actual,probes=probe.fixture(deck,Path('/parent'),Path('/new'),self.model())
        self.assertEqual(len(probes),12)
        restored=actual.replace(' '+' '.join('V('+node+')' for node in probes.values()),'')
        restored=restored.replace('/new/library.spice','/parent/library.spice').replace(
            '.tran 20p 188.049n 0 20p','.tran 20p 188.049n 0 100p')
        self.assertEqual(restored,deck)
        with self.assertRaises(ValueError):probe.fixture(deck.replace('0 100p','0 50p'),Path('/parent'),Path('/new'),self.model())

    def test_missing_or_swapped_physical_variants_cannot_prepare(self):
        with self.assertRaises(ValueError):probe.physical_models({'source_control':Path('/missing')})
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'analog').mkdir();(root/'analog/openlvds.spice').write_text('* source')
            folders={name:root/'build/diagnostics/driver_layout'/name for name in probe.CASES}
            for name,folder in folders.items():
                folder.mkdir(parents=True)
                (folder/'summary.json').write_text(json.dumps(dict(passed=True,identity=dict(variant='wrong'))))
                (folder/'extraction.json').write_text('{}')
            with patch.object(probe,'ROOT',root),patch.object(probe,'source_variant',return_value='* source'),\
                 patch.object(probe,'audited') as audit:
                with self.assertRaisesRegex(ValueError,'declared variant'):probe.physical_models(folders)
                audit.assert_not_called()

    def test_parallel_controls_complete_independently_and_failure_receipt_is_terminal(self):
        for fail in [False,True]:
            with self.subTest(fail=fail),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);parent=root/'parent';parent.mkdir();(parent/'library.spice').write_text('parent')
                (parent/'bench.cir').write_text('original deck')
                out=root/'build/diagnostics/driver_native_restore/test';out.mkdir(parents=True)
                models={case:'model '+case for case in probe.CASES};tasks=[]
                for case in probe.CASES:
                    folder=out/case;folder.mkdir();(folder/'library.spice').write_text(models[case]);(folder/'bench.cir').write_text('bound deck')
                    tasks.append(dict(id=case,stop_seconds=188.049e-9,observation_nodes={},
                        files={name:probe.digest(folder/name) for name in ['library.spice','bench.cir']}))
                identity=dict(parent='parent',parallel_jobs=2,maximum_step_ps=20,code={},inputs={},simulator_provenance={},
                    parent_config=dict(training_ns=50,bits=32,mhz=410),layouts={name:'layout/'+name for name in probe.CASES})
                (out/'manifest.json').write_text(json.dumps(dict(identity=identity,tasks=tasks)))
                barrier=threading.Barrier(2);other_started=threading.Event();started=[]
                def simulate(args,**kwargs):
                    folder=Path(args[0]).parent;started.append(folder.name);barrier.wait(timeout=5)
                    if folder.name=='source_control':
                        if not other_started.wait(timeout=5):raise AssertionError('Other native control did not start')
                    else:other_started.set()
                    if fail and folder.name=='source_control':return subprocess.CompletedProcess(args,7,'','test numerical failure')
                    (folder/'bench.cir.prn').write_text('waveform '+folder.name)
                    return subprocess.CompletedProcess(args,0,'','')
                wave=np.array([[0,0,1.8,1.4,1.05,1.4,1.05,1.8],
                    [1,60e-9,1.8,1.4,1.05,1.4,1.05,1.8],
                    [2,120e-9,1.8,1.4,1.05,1.4,1.05,1.8],
                    [3,188.049e-9,1.8,1.4,1.05,1.4,1.05,1.8]])
                headers={name:i+2 for i,name in enumerate(['V(CLK0)','V(CP)','V(CN)','V(RCP)','V(RCN)','V(TXCLOCK)'])}
                with patch.object(probe,'ROOT',root),patch.object(probe,'provenance',return_value={}),\
                     patch.object(probe,'physical_models',return_value=(models,[],set())),\
                     patch.object(probe,'overlay',side_effect=lambda baseline,model,*args:model),\
                     patch.object(probe,'fixture',return_value=('bound deck',{})),\
                     patch.object(probe,'command',side_effect=lambda log,deck:[str(deck)]),\
                     patch.object(probe,'slot',side_effect=lambda:nullcontext()) as slots,\
                     patch.object(probe.subprocess,'run',side_effect=simulate),\
                     patch.object(probe,'read_wave',return_value=(wave,headers)),\
                     patch.object(probe,'edge_times',return_value=np.linspace(60e-9,100e-9,16)),\
                     patch.object(probe,'analyze',return_value=dict(passed=True,setup_margin_ps=200,hold_margin_ps=200)):
                    if fail:
                        with self.assertRaises(subprocess.CalledProcessError):probe.run(out)
                    else:probe.run(out)
                    self.assertEqual(slots.call_count,2)
                self.assertCountEqual(started,probe.CASES)
                self.assertTrue((out/'restore_64_24/summary.json').exists())
                if fail:
                    self.assertEqual(json.loads((out/'source_control/execution.json').read_text())['status'],'held_for_diagnosis')
                    self.assertFalse((out/'summary.json').exists())
                else:
                    report=json.loads((out/'summary.json').read_text())
                    self.assertTrue(report['native_driver_only']);self.assertFalse(report['qualified_phy'])
                    self.assertEqual([s['task'] for s in report['results']],probe.CASES)


if __name__=='__main__':unittest.main()
