#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check Xyce parsing and model-substitution warnings without running SPICE."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
BINARY=Path('/opt/xyce/bin/Xyce')


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def run(deck):
    if not deck.is_relative_to(ROOT/'build') or not BINARY.is_file():
        raise ValueError('Use a saved fixture in the established Xyce container')
    text=deck.read_text();inputs={str(deck.relative_to(ROOT)):digest(deck)}
    for path in re.findall(r'(?im)^\.include\s+"([^"]+)"',text):
        source=Path(path).resolve()
        if not source.is_relative_to(ROOT):raise ValueError('Unexpected library outside OpenLVDS')
        inputs[str(source.relative_to(ROOT))]=digest(source)
    version=subprocess.run([str(BINARY),'-v'],capture_output=True,text=True,check=True).stdout.strip()
    identity=dict(inputs=inputs,version=version,binary_sha256=digest(BINARY),
                  producer_sha256=digest(Path(__file__)),mode='syntax_only',
                  image_receipt_sha256=digest(ROOT/'build/apptainer/openlvds.sif.sha256'))
    root=ROOT/'build/diagnostics/xyce_compatibility'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True,exist_ok=True)
    # Retain every byte and absolute library binding from the captured fixture.
    saved=root/'bench.cir';saved.write_text(text)
    result=subprocess.run([str(BINARY),'-syntax',str(saved)],cwd=root,capture_output=True,text=True)
    output=result.stdout+result.stderr;(root/'console.log').write_text(output)
    if any(digest(ROOT/name)!=value for name,value in inputs.items()):raise ValueError('Parser input changed')
    versions=sorted(set(re.findall(r'version ([\d.]+) which is older than the oldest version supported in Xyce \(([\d.]+)\)',
                                  re.sub(r'\s+',' ',output))))
    report=dict(identity=identity,syntax_passed=result.returncode==0,returncode=result.returncode,
        model_version_substitutions=[dict(requested=a,used=b) for a,b in versions],
        log_sha256=digest(root/'console.log'),qualified_phy=False,qualification_verdict=None,
        scope='Parser-only capability check. No transient, speed, device-model equivalence or electrical qualification result.')
    (root/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(root/'summary.json',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('deck',type=Path);a=p.parse_args();run(a.deck.resolve())
