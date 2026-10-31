#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Inspect or use the exact libraries referenced by the local PHY release pointer."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from phy_candidate import load
from promote_phy_candidate import report_arguments

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def current():
    pointer=json.loads((ROOT/'build/release/current.json').read_text());root=(ROOT/pointer['package']).resolve()
    if not root.is_relative_to(ROOT/'build/release/packages') or digest(root/'release.json')!=pointer['manifest_sha256']:
        raise ValueError('Local release pointer or package manifest changed')
    manifest=json.loads((root/'release.json').read_text());identity=manifest['identity']
    if identity['producer_sha256']!=digest(ROOT/'scripts/promote_phy_candidate.py') or identity['bundle']!=pointer['bundle']:
        raise ValueError('Release producer or bundle pointer changed')
    for name,info in manifest['files'].items():
        file=(root/name).resolve()
        if not file.is_relative_to(root) or digest(file)!=info['sha256']:
            raise ValueError('Sealed release file changed: '+name)
    bundle=(ROOT/identity['bundle']).resolve()
    if not bundle.is_relative_to(ROOT/'build/diagnostics/phy_candidate') or digest(bundle/'manifest.json')!=identity['bundle_manifest_sha256']:
        raise ValueError('Released bundle manifest changed')
    report=json.loads((root/'evidence/release.json').read_text());report_arguments(bundle,report)
    if digest(root/'evidence/release.json')!=identity['report_sha256']:
        raise ValueError('Sealed release evidence changed')
    for fast in [False,True]:
        data,_,_=load(bundle,fast)
        if data!=(root/'electrical'/('fast.spice' if fast else 'full.spice')).read_bytes():
            raise ValueError('Released library differs from the tested bundle')
    return root,bundle,report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['inspect','check','link','regression'])
    args,extra=p.parse_known_args();root,bundle,report=current()
    if any(arg=='--bundle' or arg.startswith('--bundle=') for arg in extra):p.error('The release pointer selects the bundle')
    if args.action=='inspect':
        if extra:p.error('inspect takes no extra arguments')
        print(json.dumps(dict(package=str(root.relative_to(ROOT)),bundle=str(bundle.relative_to(ROOT)),
            full_library=str(root/'electrical/full.spice'),fast_library=str(root/'electrical/fast.spice'),
            macros=str(root/'macros'),sources=str(root/'source')),indent=2));return 0
    if args.action=='check':
        if extra:p.error('check uses the sealed proof selection')
        command=[sys.executable,str(ROOT/'scripts/check_release.py')]+report_arguments(bundle,report)
    else:
        script='simulate_link.py' if args.action=='link' else 'regression.py'
        command=[sys.executable,str(ROOT/'scripts'/script),'--bundle',str(bundle.relative_to(ROOT))]+extra
    return subprocess.run(command,cwd=ROOT).returncode


if __name__=='__main__':sys.exit(main())
