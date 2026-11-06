#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Follow one exact live zero-code producer into a gated tapered-bank experiment."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time
import run_regular_regenerated_physical_v284 as original

ROOT = original.ROOT
sha = original.sha
CONTEXT = 'tapered_regenerated_bank_v310'


def ready(info, invocation, completed):
    if not invocation or re.fullmatch('[0-9a-f]{32}', invocation) is None:
        raise ValueError('Require exact original producer invocation')
    return original.owner_mode(info, invocation, completed) == 'complete'


def run(unit, source, drivers, out):
    out.mkdir(parents=True, exist_ok=False)
    invocation = original.chain.unit_info(unit).get('InvocationID')
    ready(original.chain.unit_info(unit), invocation, (source / '0/summary.json').exists())
    code = ('import sys,json;from pathlib import Path;sys.path.insert(0,"scripts");'
            'import probe_tapered_regenerated_bank_v310 as p;'
            'print(json.dumps(sorted({str(Path(m.__file__).resolve().relative_to(p.ROOT)) '
            'for m in list(sys.modules.values()) if getattr(m,"__file__",None) '
            'and Path(m.__file__).resolve().parent==p.ROOT/"scripts"})))')
    discovery = subprocess.run([str(ROOT / 'scripts/env.sh'), '--tools', '--ngspice',
                                'build/tools/exact-rc-venv/bin/python', '-c', code],
                               cwd=ROOT, capture_output=True, text=True, check=True)
    files = [Path(__file__), Path(original.__file__),
             ROOT / 'scripts/run_strong_storage_counter_followup_v235.py',
             ROOT / 'scripts/run_unguarded_bank_chain_v177.py',
             *[ROOT / name for name in json.loads(discovery.stdout)],
             source / 'manifest.json', source / 'bank.spice',
             *[drivers / name for name in ('manifest.json', 'summary.json', 'state.json')]]
    inputs = {str(path.relative_to(ROOT)): sha(path) for path in set(files)}
    artifacts = dict(source=str(source.relative_to(ROOT)), drivers=str(drivers.relative_to(ROOT)))

    def save(status, **extra):
        temporary = out / 'state.tmp'
        temporary.write_text(json.dumps(dict(status=status, producer_unit=unit,
            producer_invocation=invocation, inputs=inputs, artifacts=artifacts,
            qualified_phy=False, **extra), indent=2) + '\n')
        temporary.replace(out / 'state.json')

    def unchanged():
        if any(sha(ROOT / name) != digest for name, digest in inputs.items()):
            raise ValueError('Captured tapered-bank continuation source changed')

    def execute(action, artifact, logname, extra=()):
        unchanged()
        command = [str(ROOT / 'scripts/env.sh'), '--tools', '--ngspice',
                   'build/tools/exact-rc-venv/bin/python',
                   'scripts/probe_tapered_regenerated_bank_v310.py', action,
                   str(artifact.relative_to(ROOT)), *extra]
        with (out / logname).open('x') as log:
            subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
        unchanged()
        return (out / logname).read_text()

    save('waiting_for_complete_native_zero')
    try:
        while True:
            unchanged()
            info = original.chain.unit_info(unit)
            if ready(info, invocation, (source / '0/summary.json').exists()):
                break
            time.sleep(10)
        save('preparing_tapered_bank')
        text = execute('prepare', source, 'prepare.log', ('--drivers', str(drivers.relative_to(ROOT))))
        artifact = original.chain.artifact_from_log(text, CONTEXT)
        if artifact is None:
            raise ValueError('Missing explicit prepared tapered-bank native artifact')
        artifacts['pilot'] = str(artifact.relative_to(ROOT))
        save('running_tapered_bank')
        execute('run', artifact, 'run.log')
        state = json.loads((artifact / 'state.json').read_text())
        report = json.loads((artifact / 'summary.json').read_text())
        if state != dict(status='complete', cases=8, errors=0, qualified_phy=False) or report['comparison'] is None:
            raise ValueError('Tapered native cases incomplete or errored; retain all evidence')
        candidates = [v for v, r in report['comparison']['variants'].items()
                      if r['component_hypothesis_passed']]
        save('component_characterization_complete', passing_component_variants=candidates,
             electrical_qualification_passed=False,
             scope='Native component experiment only; shared-wire RC, routed timing, PVT, DLL and PHY remain unqualified')
    except Exception as error:
        save('failed', error=str(error))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--producer-unit', required=True)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--drivers', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    run(args.producer_unit, args.source.resolve(), args.drivers.resolve(), args.output.resolve())
