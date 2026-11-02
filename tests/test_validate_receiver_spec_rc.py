# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import validate_receiver_spec_rc as rc

ROOT=Path(__file__).resolve().parents[1]


class SpecificationReceiverRcAdmission(unittest.TestCase):
    def campaign(self,root):
        req=json.loads((ROOT/'requirements.json').read_text());(root/'requirements.json').write_text(json.dumps(req))
        out=root/'build/diagnostics/receiver_components/test';out.mkdir(parents=True)
        tasks=[]
        for view,test,process,temp in rc.qualification.components.cases(req):
            name=f'{view}_{test}_{process}_{temp}';folder=out/name;folder.mkdir()
            (folder/'bench.cir').write_text('Captured original deck')
            (folder/'source.spice').write_text('Captured original model')
            (folder/'bench.cir.prn').write_text('Captured completed waveform')
            tasks.append(dict(id=name,view=view,test=test,process=process,temperature=temp,
                files={n:rc.sha(folder/n) for n in ['bench.cir','source.spice']}))
        (out/'manifest.json').write_text(json.dumps(dict(identity={},tasks=tasks)))
        stamp=rc.sha(out/'manifest.json')
        for t in tasks:
            folder=out/t['id'];(folder/'summary.json').write_text(json.dumps(dict(passed=True,manifest_sha256=stamp,waveform_sha256=rc.sha(folder/'bench.cir.prn'))))
        (out/'summary.json').write_text(json.dumps(dict(passed=True,required=60,passed_cases=60,manifest_sha256=stamp)))
        (out/'spec_admission.json').write_text(json.dumps(dict(screen='spec-screen',proofs={})))
        return out,tasks

    def test_uses_new_cached_qualification_without_calling_legacy_transport_gate(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(rc,'ROOT',Path(tmp)):
            out,tasks=self.campaign(Path(tmp));before=(out/'summary.json').read_bytes()
            with patch.object(rc.qualification,'run') as recheck,patch.object(rc.original,'component_gate',side_effect=AssertionError('legacy gate called')):
                m,proof=rc.component_gate(out)
                recheck.assert_called_once_with(out,jobs=1)
            self.assertEqual(len(m['tasks']),60);self.assertEqual(proof['screen'],'spec-screen')
            self.assertEqual((out/'summary.json').read_bytes(),before)

    def test_missing_or_changed_completed_waveform_never_dispatches_a_component(self):
        for missing in [True,False]:
            with tempfile.TemporaryDirectory() as tmp,patch.object(rc,'ROOT',Path(tmp)):
                out,tasks=self.campaign(Path(tmp));wave=out/tasks[-1]['id']/'bench.cir.prn'
                if missing:wave.unlink()
                else:wave.write_text('Changed waveform')
                with patch.object(rc.qualification,'run') as recheck:
                    with self.assertRaises(ValueError):rc.component_gate(out)
                    recheck.assert_not_called()

    def test_aggregate_changed_by_cached_reanalysis_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(rc,'ROOT',Path(tmp)):
            out,_=self.campaign(Path(tmp))
            with patch.object(rc.qualification,'run',side_effect=lambda *a,**k:(out/'summary.json').write_text('{}')):
                with self.assertRaisesRegex(ValueError,'aggregate changed'):rc.component_gate(out)

    def test_missing_specification_admission_and_incomplete_coverage_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(rc,'ROOT',Path(tmp)):
            out,_=self.campaign(Path(tmp));(out/'spec_admission.json').unlink()
            with self.assertRaisesRegex(ValueError,'Complete all sixty'):rc.component_gate(out)
        with self.assertRaises(ValueError):rc.run(Path('/tmp/old-native-replay'))


if __name__=='__main__':unittest.main()
