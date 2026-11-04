#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently bind a component RC model and rerun its topology audit.

The first extraction producer put a scope description in its scope-hash field.
Retain that original output; this receipt binds the actual schematic hash and
the exact same GDS/netlist bytes. No timing or array certificate is supplied.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import extract_mim_switch_unit_v2 as producer
from reduce_rc import number

ROOT=producer.ROOT
NAME=producer.NAME
sha=producer.sha
LEGACY_SCOPE='Isolated five-device unit prototype; no array or PHY admission'


def port_wire_capacitance(text,ports):
    """Lumped interconnect-cap upper bound, excluding MOS and intentional MIM.

    Each coupling capacitor is counted in full at both connected conductors.
    This is a diagnostic loading bound, not a reduced transient timing model.
    """
    parents={}
    def root(n):
        n=n.lower();parents.setdefault(n,n)
        if parents[n]!=n:parents[n]=root(parents[n])
        return parents[n]
    lines=[line.split() for line in text.splitlines()]
    for words in lines:
        if len(words)==4 and words[0].lower().startswith('r'):
            parents[root(words[2])]=root(words[1])
    mapping={}
    for port in ports:
        node=root(port)
        if node in mapping:raise ValueError('RC shorts distinct unit ports')
        mapping[node]=port
    result={p:0. for p in ports}
    for words in lines:
        if len(words)==4 and words[0].lower().startswith('c'):
            a,b=root(words[1]),root(words[2]);value=number(words[3])
            if value<0:raise ValueError('Negative extracted capacitance')
            if a==b:continue
            for node in [a,b]:
                if node in mapping:result[mapping[node]]+=value
    return result


def verify(out):
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        m,_=producer.bound(out);state=json.loads((out/'state.json').read_text())
        summary=json.loads((out/'summary.json').read_text());info=summary['extraction']
        parent=ROOT/m['identity']['parent']
        if state['status']!='unit_rc_complete' or not summary['passed'] or not summary['rc_topology_passed']:
            raise ValueError('Unit extraction/topology is not complete and passing')
        text=producer.checked_netlist(info)
        if info['gds_sha256']!=sha(parent/(NAME+'.gds')) or info['source_sha256']!=sha(parent/'manifest.json'):
            raise ValueError('Unit GDS/source provenance changed')
        scope=sha(parent/(NAME+'.sch.spice'))
        if info['source_scope_sha256'] not in [scope,LEGACY_SCOPE]:raise ValueError('Unexpected source scope field')
        normalized=dict(info,source_scope_sha256=scope)
        collapsed=producer.collapse(text)
        if collapsed!=(out/'wire_collapsed.spice').read_text():raise ValueError('Collapsed audit input changed')
        files={str(p.relative_to(ROOT)):sha(p) for p in [out/'manifest.json',out/'summary.json',out/'state.json',
            out/'extraction.json',ROOT/info['netlist'],ROOT/info['raw_netlist'],parent/(NAME+'.gds'),
            parent/(NAME+'.sch.spice'),parent/(NAME+'.drc_count.txt'),parent/(NAME+'.lvs.log')]}
        identity=dict(artifact=str(out.relative_to(ROOT)),witnesses=files,scope_sha256=scope,
            code={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),Path(producer.__file__),ROOT/'scripts/reduce_rc.py']})
        receipt=ROOT/'build/diagnostics/mim_switch_unit_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
        receipt.mkdir(parents=True,exist_ok=False)
        (receipt/'wire_collapsed.spice').write_text(collapsed)
        setup=producer.strict_setup(receipt/'setup.tcl',Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl')
        log=receipt/'lvs.log'
        process=subprocess.run(['netgen','-batch','lvs',f'{receipt/"wire_collapsed.spice"} {NAME}',
            f'{parent/(NAME+".sch.spice")} {NAME}',str(setup),str(log)],cwd=receipt,capture_output=True,text=True)
        (receipt/'console.log').write_text(process.stdout+process.stderr)
        passed=producer.clean_match(log.read_text() if log.exists() else '',process.returncode)
        producer.bound(out)
        if any(sha(ROOT/n)!=v for n,v in files.items()):raise ValueError('Unit witness changed during audit')
        result=dict(identity=identity,verified_model=normalized,rc_topology_passed=passed,
            retained_producer_scope_field=info['source_scope_sha256'],scope_metadata_normalized=info['source_scope_sha256']!=scope,
            interconnect_port_cap_upper_bound_f=port_wire_capacitance(text,info['ports']),
            qualified_phy=False,electrical_qualification_passed=False,
            scope='Independent isolated component RC/topology and interconnect loading only; no array or timing admission')
        (receipt/'summary.json').write_text(json.dumps(result,indent=2)+'\n');return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args()
    print(verify(a.artifact.resolve()),flush=True)
