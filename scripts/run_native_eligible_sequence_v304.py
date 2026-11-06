#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Follow the exact full-range job into conservative universal code eligibility."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time
import run_regular_regenerated_full_range_v302 as source

ROOT=source.ROOT
chain=source.chain
sha=source.sha
CONTEXT='native_eligible_sequence_v303'
ALL_RAW_REJECTION='ValueError: Full-range native interval or common-order result does not reproduce'


def ready_campaign(state,coordinator):
    status=state.get('status')
    if status not in ('full_range_characterization_complete','failed'):
        raise ValueError('Full-range native campaign has not completed')
    if status=='failed':
        # Only the original blanket all-raw pass gate may hand off here.
        # Missing/corrupt traces, source changes and solver errors stay fatal.
        log=coordinator/'verify.log'
        if not log.is_file() or 'returned non-zero exit status' not in state.get('error',''):
            raise ValueError('Unsupported full-range failure; preserve it without recovery')
        with log.open('rb') as stream:
            stream.seek(max(0,log.stat().st_size-4096));last=stream.read().decode(errors='replace').splitlines()
        if not last or last[-1]!=ALL_RAW_REJECTION:
            raise ValueError('Full-range failure is not the original all-raw pass gate')
    relative=state.get('artifacts',{}).get('full_range','')
    if re.fullmatch(r'build/diagnostics/regular_regenerated_full_range_v301/[0-9a-f]{16}',relative) is None:
        raise ValueError('Require explicit original full-range native artifact')
    parent=ROOT/relative
    if json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=7680,consumed_cases=106,errors=0,qualified_phy=False):
        raise ValueError('Every original native case must complete without measurement errors')
    return parent


def run(unit,parent,out):
    out.mkdir(parents=True,exist_ok=False);state=json.loads((parent/'state.json').read_text())
    info=chain.unit_info(unit);invocation=info.get('InvocationID')
    complete=state.get('status') in ('full_range_characterization_complete','failed')
    if complete:ready_campaign(state,parent)
    source.sparse.source.owner_mode(info,invocation,complete);pinned=dict(state['inputs'])
    code="import sys,json;from pathlib import Path;sys.path.insert(0,'scripts');import select_native_eligible_sequence_v303 as p;print(json.dumps(sorted({str(Path(m.__file__).resolve().relative_to(p.ROOT)) for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==p.ROOT/'scripts'})))"
    discovery=subprocess.run([str(ROOT/'scripts/env.sh'),'--tools','--ngspice','build/tools/exact-rc-venv/bin/python','-c',code],cwd=ROOT,capture_output=True,text=True,check=True)
    files=[Path(__file__),Path(source.__file__),*[ROOT/n for n in json.loads(discovery.stdout)]]
    inputs=source.merge_inputs([pinned,{str(p.relative_to(ROOT)):sha(p) for p in files}])
    artifacts=dict(full_range_coordinator=str(parent.relative_to(ROOT)))
    def save(status,**extra):
        temp=out/'state.tmp';temp.write_text(json.dumps(dict(status=status,producer_unit=unit,producer_invocation=invocation,
            inputs=inputs,pinned_source_inputs=pinned,artifacts=artifacts,legal_code_table_admitted=False,qualified_phy=False,**extra),indent=2)+'\n');temp.replace(out/'state.json')
    def unchanged():
        if any(sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Captured native eligibility source changed')
        current=json.loads((parent/'state.json').read_text())
        if any(current['inputs'].get(n)!=h for n,h in pinned.items()):raise ValueError('Full-range coordinator input binding changed')
        return current
    save('waiting_for_complete_raw_characterization')
    try:
        while True:
            current=unchanged();complete=current.get('status') in ('full_range_characterization_complete','failed')
            if complete:campaign=ready_campaign(current,parent)
            mode=source.sparse.source.owner_mode(chain.unit_info(unit),invocation,complete)
            if mode=='complete':break
            time.sleep(10)
        inputs[str((parent/'state.json').relative_to(ROOT))]=sha(parent/'state.json')
        if (parent/'verify.log').exists():inputs[str((parent/'verify.log').relative_to(ROOT))]=sha(parent/'verify.log')
        artifacts['full_range']=str(campaign.relative_to(ROOT));save('verifying_native_eligibility')
        command=[str(ROOT/'scripts/env.sh'),'--tools','--ngspice','build/tools/exact-rc-venv/bin/python',
            'scripts/select_native_eligible_sequence_v303.py',str(campaign.relative_to(ROOT))]
        unchanged()
        with (out/'verify.log').open('x') as log:subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        unchanged();artifact=chain.artifact_from_log((out/'verify.log').read_text(),CONTEXT)
        if artifact is None:raise ValueError('Missing explicit native eligibility receipt')
        result=json.loads((artifact/'summary.json').read_text())
        if result.get('all_original_native_results_reproduced') is not True or result.get('complete_7680_measured_raw_results') is not True:
            raise ValueError('Native eligibility did not reproduce every original raw result')
        artifacts['eligibility']=str(artifact.relative_to(ROOT))
        save('native_eligibility_complete',eligible_codes=len(result['eligible_codes']),common_sequence_found=result['common_sequence_found'],
            scope='All raw results retained; only universally passing reference-clock codes proposed; clock variation, updates, physical ROM and PHY remain unqualified')
    except Exception as e:save('failed',error=str(e));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--producer-unit',required=True)
    p.add_argument('--source',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();run(a.producer_unit,a.source.resolve(),a.output.resolve())
