#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Bind an integration LEF to the exact DRC/LVS-clean unit GDS and check OpenDB.

The original Magic view exposes contacts and capacitor plates as routing pins.
Restrict access to designated M3 rails and move all other routing geometry to
obstructions. Preserve GDS, origin, size and every routing-layer rectangle.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import build_mim_switch_unit_v3 as physical
import mim_switch_abstract_v2 as view

ROOT=physical.ROOT
NAME=physical.unit.NAME
sha=physical.sha
VERSION='fine-unit-integration-abstract-v2.1'


def build(parent):
    physical.bound(parent);report=json.loads((parent/'summary.json').read_text())
    if not report['unit_physical_passed'] or report['drc_count']!='0' or not report['lvs_passed']:
        raise ValueError('Require a DRC/LVS-clean physical unit')
    lef=parent/(NAME+'.lef');gds=parent/(NAME+'.gds')
    tech=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef'
    tool=shutil.which('openroad')
    if tool is None or not tech.is_file():raise ValueError('Use scripts/env.sh --tools python3')
    text,pins=view.abstract(lef.read_text(),report['ports'])
    paths=[Path(__file__),Path(view.__file__),Path(physical.__file__),parent/'manifest.json',parent/'summary.json',lef,gds]
    identity=dict(version=VERSION,inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
        tech_lef=str(tech),tech_lef_sha256=sha(tech),openroad=tool,openroad_sha256=sha(Path(tool)))
    out=ROOT/'build/diagnostics/mim_switch_unit_abstract_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(identity,indent=2)+'\n')
    abstract=out/(NAME+'.lef');abstract.write_text(text)
    tcl=out/'check.tcl'
    tcl.write_text(f'''read_lef {{{tech}}}
read_lef {{{abstract}}}
set db [ord::get_db]
set master [$db findMaster {NAME}]
if {{$master == "NULL"}} {{error "Fine unit master missing"}}
set f [open {{{out/'pins.tsv'}}} w]
foreach term [$master getMTerms] {{
    set layers {{}}
    foreach pin [$term getMPins] {{
        foreach shape [$pin getGeometry] {{lappend layers [[$shape getTechLayer] getName]}}
    }}
    puts $f "[$term getName]\t[$term getIoType]\t[$term getSigType]\t[join $layers ,]"
}}
close $f
exit
''')
    with (out/'openroad.log').open('w') as stream:
        process=subprocess.run([tool,'-no_init','-exit',str(tcl)],cwd=out,stdout=stream,stderr=subprocess.STDOUT)
    observed={}
    if (out/'pins.tsv').exists():
        for line in (out/'pins.tsv').read_text().splitlines():
            name,direction,usage,layers=line.split('\t');observed[name]=dict(direction=direction,use=usage,layers=layers.split(','))
    passed=process.returncode==0 and set(observed)==set(pins) and all(
        observed[n]==dict(direction=p['direction'],use=p['use'],layers=['met3']) for n,p in pins.items())
    physical.bound(parent)
    if any(sha(ROOT/n)!=v for n,v in identity['inputs'].items()):raise ValueError('Abstract source changed during validation')
    result=dict(identity=identity,passed=passed,returncode=process.returncode,pins=pins,observed=observed,
        lef=str(abstract.relative_to(ROOT)),lef_sha256=sha(abstract),gds=str(gds.relative_to(ROOT)),gds_sha256=sha(gds),
        qualified_phy=False,electrical_qualification_passed=False,
        scope='Integration abstraction and OpenDB port validation only; no array, timing or PHY admission')
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args()
    print(build(a.artifact.resolve()),flush=True)
