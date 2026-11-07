#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Extract and certify actual shared-wire RC of the passing shunted counter."""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
from pathlib import Path
import sys
import build_shunted_counter_v349 as physical
import build_parallel_output_cell_v111 as proof
import extract_native_flat_v4 as extractor
from audit_rc_comments_v2 import collapse

ROOT=physical.ROOT
NAME=physical.NAME
PORTS=physical.PORTS
VERSION='local-first-setter-23-macro-counter-gds-shared-rc-schur-proof-v350.1'
CONTEXT='shunted_counter_rc_v350'
EXPECTED={'sky130_fd_pr__nfet_01v8':358,'sky130_fd_pr__pfet_01v8_hvt':246,
          'sky130_fd_pr__pfet_01v8':140,'sky130_fd_pr__cap_mim_m3_1':51}
SCOPE=('Fresh actual local-first-setter 23-macro shunted counter GDS shared-wire distributed RC, '
       'native parameters/topology, passivity, exact reduction and independent '
       'terminal-current proof; no extracted transient, all-PVT, DLL or PHY admission')
sha=physical.sha
atomic=physical.atomic


def require_physical(state,report):
    p=report.get('physical',{});w=p.get('native_master_witness',{});n=p.get('native_parameters',{})
    if (state!=dict(status='complete',passed=True,qualified_phy=False)
            or report.get('counter_physical_passed') is not True
            or p.get('passed') is not True or p.get('drc_count')!='0' or p.get('lvs_passed') is not True
            or (p.get('native_macro_roles'),p.get('native_mos'),p.get('native_mim'))!=(23,744,51)
            or any(w.get(k) is not True for k in ('all_native_masks_and_electrical_labels_preserved',
                'native_hierarchy_preserved','integrated_macro_placements_verified'))
            or n.get('native_model_counts')!=EXPECTED or n.get('native_primitives')!=795
            or any(n.get(k) is not True for k in ('native_parameters_preserved',
                'all_native_model_dimensions_preserved','all_reference_supplied_junctions_preserved'))):
        raise ValueError('Require complete passing 23-macro shunted physical counter')


def census(text):
    ports,devices=physical.material.legacy.inventory.native_leaves(collapse(text),NAME+'_flat')
    counts=dict(Counter(d['model'] for d in devices))
    if ports!=PORTS or counts!=EXPECTED or len(devices)!=795:
        raise ValueError('Extracted physical counter native census or port order changed')
    return dict(ports=ports,native_model_counts=counts,native_primitives=len(devices))


def checked(parent):
    i=physical.bound(parent)['identity'];r=json.loads((parent/'summary.json').read_text())
    require_physical(json.loads((parent/'state.json').read_text()),r)
    if any(sha(parent/n)!=h for n,h in r['files'].items()):
        raise ValueError('Qualified shunted counter physical outputs changed')
    folder=parent/NAME;gds=folder/(NAME+'.gds')
    if (str(gds.relative_to(ROOT))!=r['physical']['gds']
            or sha(gds)!=r['physical']['gds_sha256']
            or sha(folder/(NAME+'.lef'))!=r['physical']['lef_sha256']):
        raise ValueError('Qualified whole-counter GDS/LEF changed')
    native=census((folder/(NAME+'.lvs.spice')).read_text())
    return i,r,gds,native


def prepare(parent):
    previous,report,gds,native=checked(parent)
    paths=[parent/n for n in ('manifest.json','summary.json','state.json',*report['files'])]
    paths += [ROOT/n for n in previous['inputs']]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
        if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),gds=str(gds.relative_to(ROOT)),
        ports={p:report['physical']['ports'][p] for p in PORTS},native_census=native,
        inputs={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):sha(p) for p in sorted(set(paths))},
        external_files=previous['external_files'],tools=previous['tools'],
        python_packages=previous['python_packages'],math_runtime=proof.math_proof.math_proof()['runtime'],scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or i['scope']!=SCOPE
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
            or any(sha(Path(n))!=h for n,h in i['external_files'].items())
            or physical.assembly.native.environment.tools()!=i['tools']
            or {n:physical.version(n) for n in i['python_packages']}!=i['python_packages']
            or proof.math_proof.math_proof()['runtime']!=i['math_runtime']):
        raise ValueError('Shunted counter shared-wire RC context changed')
    _,report,gds,native=checked(ROOT/i['parent'])
    if (i['gds']!=str(gds.relative_to(ROOT)) or i['native_census']!=native
            or list(i['ports'])!=PORTS or i['ports']!={p:report['physical']['ports'][p] for p in PORTS}):
        raise ValueError('Qualified counter extraction material changed')
    return i


def run(out):
    i=bound(out);parent=ROOT/i['parent']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial shared-wire extraction')
        atomic(out/'state.json',dict(status='extracting',qualified_phy=False))
        try:
            gds=ROOT/i['gds']
            digest=hashlib.sha256(gds.read_bytes()+Path(extractor.__file__).read_bytes()).hexdigest()[:16]
            if (ROOT/'build/extracted'/digest/NAME).exists():
                raise ValueError('Retain previous or partial actual-GDS counter extraction')
            reference=parent/NAME/(NAME+'.lvs.spice')
            info=extractor.extract(NAME,gds,sha(out/'manifest.json'),ports=i['ports'],source_scope=sha(reference))
            atomic(out/'extraction.json',info)
            if info.get('passed') is not True or info.get('ports_verified') is not True or info.get('ports')!=PORTS:
                raise ValueError('Actual shunted-counter RC extraction or public interface failed')
            target=out/'proof';target.mkdir()
            result=proof.certify(target,info,NAME,reference,795)
            if result['independent_terminal_current_witness']['runtime']!=i['math_runtime']:
                raise ValueError('Independent counter RC math runtime changed')
            bound(out)
            report=dict(extraction=info,rc_proof=result,native_census=i['native_census'],
                whole_counter_shared_wire_rc_qualified=True,counter_timing_qualified=False,
                all_pvt_covered=False,electrical_qualification_passed=False,qualified_phy=False,scope=SCOPE)
            report['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*')
                if p.is_file() and p.name not in ('state.json','.execution.lock')}
            report['extracted_files']={info[k]:sha(ROOT/info[k]) for k in ('raw_netlist','netlist')}
            atomic(out/'summary.json',report)
            atomic(out/'state.json',dict(status='complete',passed=True,qualified_phy=False))
        except Exception as error:
            atomic(out/'state.json',dict(status='failed',error=str(error),qualified_phy=False));raise
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','run','campaign'));parser.add_argument('artifact',type=Path)
    args=parser.parse_args();out=args.artifact.resolve()
    if args.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if args.action in ('run','campaign'):print(run(out),flush=True)
