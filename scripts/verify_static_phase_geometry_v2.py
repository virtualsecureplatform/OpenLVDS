#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Reaudit independent DRC and installed partial-antenna reports for one GDS."""
import argparse
import hashlib
import json
from pathlib import Path
import check_static_phase_klayout_v2 as drc
import check_static_phase_antenna_v2 as antenna

ROOT=drc.ROOT
sha=drc.sha
VERSION='independent-whole-counter-geometry-and-partial-antenna-audit-v2.1'


def same_gds(k,a):
    if k['parent']!=a['parent'] or k['gds']!=a['gds']:raise ValueError('Geometry reports cover different physical counters')


def retained(out,status):
    state=json.loads((out/'state.json').read_text());result=json.loads((out/'summary.json').read_text())
    if state['status']!=status or not state['passed'] or not result['passed'] or result['error'] is not None or result['qualified_phy']:
        raise ValueError('Require complete positive unqualified physical checks')
    if any(sha(out/n)!=h for n,h in result['files'].items()):raise ValueError('Retained physical report changed')
    return result,[out/n for n in ['manifest.json','summary.json','state.json',*result['files']]]


def verify(klayout,partial):
    km=drc.bound(klayout);am=antenna.bound(partial);ki=km['identity'];ai=am['identity'];same_gds(ki,ai)
    kr,kfiles=retained(klayout,'independent_drc_complete');ar,afiles=retained(partial,'partial_antenna_complete')
    measured=drc.parse_report(klayout/'report.lyrdb',ki['top'])
    if any(kr[k]!=v for k,v in measured.items()) or measured['violation_count']!=0:raise ValueError('Independent DRC reparse differs')
    flags=dict(input=str(ROOT/ki['gds']),top_cell=ki['top'],report=str(klayout/'report.lyrdb'),**ki['options'])
    args=[ki['tool']['path'],'-b','-zz','-r',ki['runset']]
    for k,v in flags.items():args += ['-rd',k+'='+v]
    if json.loads((klayout/'command.json').read_text())!=args:raise ValueError('Recorded DRC command differs from bound rules')
    log=(klayout/'console.log').read_text()
    for flag in ['feol','beol','floating_met','offgrid']:
        if flag+': true' not in log:raise ValueError('Missing enabled rule confirmation')
    measured=antenna.parse_result(partial/'result.txt',partial/(antenna.FLAT+'.ext'))
    if any(ar[k]!=v for k,v in measured.items()) or not measured['installed_partial_antenna_passed']:raise ValueError('Partial antenna reparse differs')
    log=(partial/'antenna.log').read_text()
    for marker in ['OPENLVDS_PARTIAL_ANTENNA_BEGIN','Running antenna checks.','antennacheck finished.','OPENLVDS_PARTIAL_ANTENNA_RESULT 0']:
        if marker not in log:raise ValueError('Missing actual partial antenna execution')
    if (partial/'antenna.feedback').read_text().strip():raise ValueError('Nonempty partial antenna feedback')
    drc.bound(klayout);antenna.bound(partial)
    code=[Path(__file__),Path(drc.__file__),Path(antenna.__file__)]
    identity=dict(version=VERSION,parent=ki['parent'],klayout=str(klayout.relative_to(ROOT)),partial_antenna=str(partial.relative_to(ROOT)),
        inputs={str(p.relative_to(ROOT)):sha(p) for p in kfiles+afiles+code})
    out=ROOT/'build/diagnostics/static_phase_geometry_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    if any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Physical evidence changed during audit')
    out.mkdir(parents=True,exist_ok=False)
    result=dict(identity=identity,klayout_violation_count=kr['violation_count'],native_mos_count=ar['native_mos_count'],
        installed_partial_antenna_feedback_count=ar['feedback_count'],passed=True,qualified_phy=False,
        scope='Reparsed same-GDS installed full macro DRC and Magic partial antenna only; no die seal/density, cumulative/diode-diffusion foundry antenna, electrical, full-PVT or PHY admission')
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--klayout',type=Path,required=True);p.add_argument('--partial-antenna',type=Path,required=True);a=p.parse_args();print(verify(a.klayout.resolve(),a.partial_antenna.resolve()),flush=True)
