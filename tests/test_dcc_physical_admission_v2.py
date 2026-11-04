# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import itertools
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import harden_dcc_v2 as physical

class SourceAdmissionTests(unittest.TestCase):
    def test_complete_cached_witnesses_required_and_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);parent=root/'build/diagnostics/source';parent.mkdir(parents=True)
            tasks=[];rows=[];files={}
            specs=itertools.product(['tt','ff','ss','fs','sf'],[0,25,40],[390,400,410],[20,250],[0,-140,140])
            for i,(p,t,f,s,e) in enumerate(specs):
                task=dict(id=str(i),spec=dict(process=p,temperature=t,mhz=f,slew_ps=s,phase_error_ps=e,drive=1,buffers=0,output_cell='inv_4',reset_drive=1))
                tasks.append(task);folder=parent/str(i);folder.mkdir()
                row=dict(task=task,error=None,result=dict(event_integrity_passed=True,pulse_generator_integrity_passed=True,symmetric_timing_passed=True if e==0 else None))
                rows.append(row)
                for n in physical.consumer.reader.REQUIRED|{'summary.json'}:
                    path=folder/n;path.write_text('fixture');files[str(path.relative_to(root))]=physical.sha(path)
            for n,value in [('manifest.json',dict(tasks=tasks)),('summary.json',dict(rows=rows)),('state.json',dict(status='source_screen_complete',cases=270))]:
                path=parent/n;path.write_text(json.dumps(value));files[str(path.relative_to(root))]=physical.sha(path)
            identity=dict(artifact=str(parent.relative_to(root)),manifest_sha256=physical.sha(parent/'manifest.json'),
                summary_sha256=physical.sha(parent/'summary.json'),consumer_sha256=physical.sha(Path(physical.consumer.__file__)))
            receipt=root/'build/diagnostics/dcc_clock_hold_pvt_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]/'summary.json'
            receipt.parent.mkdir(parents=True)
            report=dict(artifact=identity['artifact'],consumer_sha256=identity['consumer_sha256'],cases=270,numerical_errors=0,
                source_only=True,qualified_phy=False,candidates=[dict(topology=[1,'clock_hold','inv_4'],cases=270,pvt_count=15,source_screen_passed=True)],witness_files=files)
            receipt.write_text(json.dumps(report))
            with patch.object(physical,'ROOT',root),patch.object(physical.source,'bound',return_value=dict(tasks=tasks)):
                self.assertEqual(physical.source_admission(parent),receipt)
                raw=parent/'0/bench.raw';raw.write_text('changed')
                with self.assertRaisesRegex(ValueError,'witnesses changed'):physical.source_admission(parent)
                raw.write_text('fixture')
                del report['witness_files'][str(raw.relative_to(root))];receipt.write_text(json.dumps(report))
                with self.assertRaisesRegex(ValueError,'witness coverage'):physical.source_admission(parent)
                report['candidates'][0]['pvt_count']=14;receipt.write_text(json.dumps(report))
                with self.assertRaisesRegex(ValueError,'source qualification'):physical.source_admission(parent)
