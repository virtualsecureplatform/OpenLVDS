#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Full RTL regression of the matched output-buffer experiment, in an isolated snapshot."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import verify_rtl

ROOT=Path(__file__).resolve().parents[1]
def main():
    candidate=ROOT/'rtl/experiments/openlvds_ddr_tx_buffer4.v'
    files=list((ROOT/'rtl').glob('*.v'))+list((ROOT/'models').glob('*.v'))+list((ROOT/'tb').glob('*.v'))
    files += [ROOT/'requirements.json',ROOT/'scripts/verify_rtl.py',candidate,Path(__file__)]
    fingerprint=hashlib.sha256(b''.join(p.read_bytes() for p in files)).hexdigest()
    out=ROOT/'build/diagnostics/tx_buffer4'/fingerprint[:16];out.mkdir(parents=True,exist_ok=True)
    for p in files:
        if p==candidate or p==Path(__file__):continue
        target=out/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    # The module name is adapted only for the existing regression benches.
    adapted=candidate.read_text().replace('module openlvds_ddr_tx_buffer4 (','module openlvds_ddr_tx (')
    (out/'rtl/openlvds_ddr_tx.v').write_text(adapted)
    (out/'candidate.v').write_bytes(candidate.read_bytes())
    verify_rtl.ROOT=out
    sys.argv=[str(ROOT/'scripts/verify_rtl.py')]
    result=verify_rtl.main()
    summary=json.loads((out/'build/rtl/summary.json').read_text())
    summary.update(diagnostic=True,qualified=False,experiment='matched native buf_4 outputs',
        fingerprint=fingerprint,candidate_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),
        scope='Functional regression only; electrical/physical qualification remains required')
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(out,flush=True)
    return result

if __name__=='__main__':raise SystemExit(main())
