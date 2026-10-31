#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Publish an immutable local PHY release after repeating all staged release gates."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

from phy_candidate import load

ROOT=Path(__file__).resolve().parents[1]
PROOFS={'stability':'stability','recovery':'recovery','readiness':'readiness',
        'ota_operating_points':'ota-operating-points'}


def digest(data):return hashlib.sha256(data).hexdigest()


def check_lef_interface(name,text,ports):
    pins=re.findall(r'(?m)^\s*PIN\s+(\S+)\s*$',text)
    if (re.findall(r'(?m)^\s*MACRO\s+(\S+)\s*$',text)!=[name] or
        len(pins)!=len(set(pins)) or set(pins)!=set(ports)):
        raise ValueError('Release LEF interface differs from extracted ports: '+name)



def check_powered_netlist(name,powered,logical,ports):
    """Bind the delivered power-aware cell netlist to the audited logic netlist."""
    rails={'VPWR':'VPWR','VGND':'VGND','VPB':'VPWR','VNB':'VGND'}
    def parse(text):
        text=re.sub(r'/\*.*?\*/|//[^\n]*','',text,flags=re.S)
        modules=re.findall(r'\bmodule\s+(\w+)\s*\((.*?)\);',text,re.S)
        if len(modules)!=1 or modules[0][0]!=name:raise ValueError('Release netlist module differs: '+name)
        header=[p.strip().lstrip('\\') for p in modules[0][1].split(',')]
        interface={};declared=[]
        for direction,hi,lo,body in re.findall(r'(?m)^\s*(input|output|inout)\s+(?:wire\s+)?(?:\[\s*(\d+)\s*:\s*(\d+)\s*\]\s*)?([^;]+);',text):
            for part in body.split(','):
                net=part.strip().lstrip('\\');declared.append(net)
                bits=[f'{net}[{i}]' for i in range(min(int(hi),int(lo)),max(int(hi),int(lo))+1)] if hi else [net]
                for bit in bits:
                    if bit in interface:raise ValueError('Duplicate release netlist terminal: '+name)
                    interface[bit]=direction
        if len(header)!=len(set(header)) or len(declared)!=len(set(declared)) or set(header)!=set(declared):
            raise ValueError('Release netlist terminal declarations differ: '+name)
        cells={}
        for kind,instance,body in re.findall(r'(?m)^\s*(\w+)\s+([^\s(]+)\s*\((.*?)\);',text,re.S):
            if kind=='module':continue
            if not kind.startswith(('sky130_fd_sc_hd__','sky130_ef_sc_hd__')) or instance in cells:
                raise ValueError('Unsupported or duplicate release cell: '+name)
            pairs=re.findall(r'\.(\w+)\s*\(\s*([^()\s]+)\s*\)',body)
            remainder=re.sub(r'\.\w+\s*\(\s*[^()\s]+\s*\)','',body)
            if remainder.strip(' \r\n\t,') or len(pairs)!=len(dict(pairs)):
                raise ValueError('Unsupported release cell terminals: '+name)
            cells[instance]=(kind,dict(pairs))
        assigns=sorted(re.sub(r'\s+','',row) for row in re.findall(r'(?m)^\s*assign\s+([^;]+);',text))
        wires=sorted(re.sub(r'\s+','',row) for row in re.findall(r'(?m)^\s*wire\s+([^;]+);',text))
        if not cells:raise ValueError('Empty release cell netlist: '+name)
        return interface,cells,assigns,wires
    pi,pc,pa,pw=parse(powered);li,lc,la,lw=parse(logical)
    if (set(pi)!=set(ports) or any(pi.get(p)!='inout' for p in ['VPWR','VGND']) or
            {p:d for p,d in pi.items() if p not in ['VPWR','VGND']}!=li):
        raise ValueError('Release powered netlist interface differs from extracted ports: '+name)
    stripped={}
    for instance,(kind,pins) in pc.items():
        required={p:n for p,n in rails.items() if p in ['VPWR','VGND']} if kind=='sky130_fd_sc_hd__tapvpwrvgnd_1' else rails
        if set(pins)&set(rails)!=set(required) or any(pins.get(pin)!=net for pin,net in required.items()):
            raise ValueError('Release cell power connection differs: '+name)
        stripped[instance]=(kind,{p:n for p,n in pins.items() if p not in rails})
    if stripped!=lc or pa!=la or pw!=lw:
        raise ValueError('Release powered cell connectivity differs from audited logic: '+name)


def report_arguments(bundle,report):
    from pfd_candidate_policy import policy_provenance
    if (not report.get('passed') or not report.get('checks') or
        any(c.get('passed') is not True for c in report['checks']) or
        report.get('bundle')!=str(bundle.relative_to(ROOT)) or
        report.get('bundle_manifest_sha256')!=digest((bundle/'manifest.json').read_bytes()) or
        report.get('checker_sha256')!=digest((ROOT/'scripts/check_release.py').read_bytes()) or
        report.get('staged_gate_sha256')!=digest((ROOT/'scripts/staged_release.py').read_bytes()) or
        report.get('native_gate_sha256')!=digest((ROOT/'scripts/dll_native_evidence.py').read_bytes()) or
        report.get('candidate_rtl_gate_sha256')!=digest((ROOT/'scripts/verify_candidate_rtl.py').read_bytes()) or
        report.get('pfd_policy_code')!=policy_provenance(ROOT) or
        set(report.get('proofs',{}))!=set(PROOFS)):
        raise ValueError('A complete, current, passing staged release report is required')
    args=['--bundle',str(bundle.relative_to(ROOT))]
    for name,flag in PROOFS.items():
        info=report['proofs'][name];path=(ROOT/info['path']).resolve()
        if not path.is_relative_to(ROOT) or digest(path.read_bytes())!=info['sha256']:
            raise ValueError('Release proof changed: '+name)
        args+=['--'+flag,str(path.relative_to(ROOT))]
    return args


def digital_artifacts(identity,native):
    selected=[('openlvds_tx_core',ROOT/identity['tx']),('lvds_pfd',ROOT/native['pfd']),
              ('openlvds_ddr_rx',ROOT/identity.get('rx','build/physical/rx'))]
    return [(name,physical,physical/'extraction.json' if name!='openlvds_ddr_rx' or identity.get('rx')
             else ROOT/'build/extracted/digital.json') for name,physical in selected]




def digital_netlist_inputs(name,run,ports):
    logical=run/'final/nl'/(name+'.nl.v');powered=run/'final/pnl'/(name+'.pnl.v')
    logical_data=logical.read_bytes();powered_data=powered.read_bytes()
    check_powered_netlist(name,powered_data.decode(),logical_data.decode(),ports)
    return {logical:digest(logical_data),powered:digest(powered_data)}


def check_netlists(bundle):
    """Inspect selected netlists without sealing or publishing a PHY release."""
    bundle=Path(bundle).resolve();load(bundle)
    manifest=json.loads((bundle/'manifest.json').read_text());identity=manifest['identity']
    q=json.loads((ROOT/identity['qualification']/'manifest.json').read_text())
    proofs=[]
    for name,physical,extraction in digital_artifacts(identity,q['identity']['full_models']):
        summary=json.loads((physical/'summary.json').read_text());run=ROOT/summary['run']
        info=json.loads(extraction.read_text())
        if name=='openlvds_ddr_rx' and not identity.get('rx'):info=info['designs'][name]
        checked=digital_netlist_inputs(name,run,info['ports'])
        if any(digest(p.read_bytes())!=value for p,value in checked.items()):raise ValueError('Digital handoff changed during preflight')
        proofs.append(dict(macro=name,ports=info['ports'],files={str(p.relative_to(ROOT)):value for p,value in checked.items()}))
    report=dict(passed=True,qualified_phy=False,scope='Selected digital netlist handoff only; no release publication',
        bundle_manifest_sha256=digest((bundle/'manifest.json').read_bytes()),
        producer_sha256=digest(Path(__file__).read_bytes()),macros=proofs)
    (bundle/'netlist_preflight.json').write_text(json.dumps(report,indent=2)+'\n')
    print(bundle/'netlist_preflight.json',flush=True)
    return report


def payload(bundle):
    manifest=json.loads((bundle/'manifest.json').read_text());identity=manifest['identity']
    qualification=ROOT/identity['qualification'];q=json.loads((qualification/'manifest.json').read_text())
    native=q['identity']['full_models'];layout=ROOT/native['layout']
    files={}
    def add(name,path,expected=None):
        path=Path(path).resolve()
        if not path.is_relative_to(ROOT):raise ValueError('Release input outside OpenLVDS')
        data=path.read_bytes()
        if expected is not None and digest(data)!=expected:raise ValueError('Release input changed: '+str(path))
        if name in files:raise ValueError('Duplicate release file')
        files[name]=dict(data=data,source=str(path.relative_to(ROOT)),sha256=digest(data))
    for name in ['full.spice','fast.spice','manifest.json','rc_certificate.json']:
        add('electrical/'+name,bundle/name)
    add('evidence/release.json',bundle/'release/status.json')
    add('evidence/link_matrix.json',bundle/'regression/summary.json')
    for name in ['manifest.json','summary.json']:
        add('evidence/native_dll/'+name,qualification/name)
    report=json.loads((bundle/'release/status.json').read_text())
    for name,info in report['proofs'].items():
        add('evidence/'+name+'.json',ROOT/info['path'],info['sha256'])
    add('source/analog/openlvds.spice',layout/'candidate.spice',native['source_sha256'])
    add('source/requirements.json',ROOT/'requirements.json')
    from verify_candidate_rtl import verify as verify_rtl
    rtl,_=verify_rtl(bundle)
    for folder in ['rtl','models','sky130']:
        for path in sorted((rtl/folder).glob('*')):
            if path.is_file():add('source/'+folder+'/'+path.name,path)
    add('source/sky130/lvds_pfd.v',rtl/'physical_pfd.v')
    add('evidence/candidate_rtl.json',rtl/'summary.json')
    add('evidence/candidate_rtl_manifest.json',rtl/'manifest.json')
    for path in sorted((ROOT/'constraints').glob('*')):
        if path.is_file():add('source/constraints/'+path.name,path)
    analog=json.loads((ROOT/'build/layout/current.json').read_text())['designs']
    analog=dict(analog,openlvds_dll_analog=json.loads((layout/'summary.json').read_text())['designs']['openlvds_dll_analog'])
    analog_extract=json.loads((ROOT/'build/extracted/current.json').read_text())['designs']
    analog_extract=dict(analog_extract,openlvds_dll_analog=json.loads((layout/'extraction.json').read_text()))
    def macro(name,gds,lef,ports,expected_gds):
        check_lef_interface(name,lef.read_text(),ports)
        add('macros/'+name+'/'+name+'.gds',gds,expected_gds)
        add('macros/'+name+'/'+name+'.lef',lef)
    for name in ['lvds_bias','openlvds_driver_core','openlvds_receiver_core','openlvds_delay_line','openlvds_dll_analog']:
        info=analog_extract[name];gds=ROOT/analog[name]['gds']
        macro(name,gds,gds.with_suffix('.lef'),info['ports'],info['gds_sha256'])
    for name,physical,extraction in digital_artifacts(identity,native):
        summary=json.loads((physical/'summary.json').read_text());run=ROOT/summary['run']
        info=json.loads(extraction.read_text())
        if name=='openlvds_ddr_rx' and not identity.get('rx'):info=info['designs'][name]
        if info['gds_sha256']!=identity['full']['digital_models'][name]['gds_sha256']:
            raise ValueError('Packaged macro differs from the staged digital model: '+name)
        macro(name,run/'final/gds'/(name+'.gds'),run/'final/lef'/(name+'.lef'),info['ports'],info['gds_sha256'])
        for path,value in digital_netlist_inputs(name,run,info['ports']).items():
            add('macros/'+name+'/'+path.name,path,value)
        if 'input_archive' in summary:
            for path in sorted((ROOT/summary['input_archive']).iterdir()):
                if path.is_file():add('source/'+name+'/'+path.name,path)
    return files


def seal(files,identity,directory):
    """Write a complete package first; publishing the pointer is a separate step."""
    metadata=dict(identity=identity,files={name:{k:v for k,v in info.items() if k!='data'} for name,info in files.items()})
    encoded=(json.dumps(metadata,sort_keys=True,indent=2)+'\n').encode();stamp=digest(encoded)
    target=directory/'packages'/stamp[:16];target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        if (target/'release.json').read_bytes()!=encoded:raise ValueError('Existing release package changed')
        for name,info in files.items():
            if (target/name).read_bytes()!=info['data']:raise ValueError('Existing release file changed')
        return target,stamp
    temporary=Path(tempfile.mkdtemp(prefix='.preparing-',dir=target.parent))
    try:
        for name,info in files.items():
            destination=temporary/name
            if not destination.resolve().is_relative_to(temporary):raise ValueError('Invalid package path')
            destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(info['data'])
            if digest(destination.read_bytes())!=info['sha256']:raise ValueError('Release copy changed')
        (temporary/'release.json').write_bytes(encoded)
        temporary.rename(target)
    finally:
        if temporary.exists():shutil.rmtree(temporary)
    return target,stamp


def promote(bundle):
    bundle=Path(bundle).resolve()
    if not bundle.is_relative_to(ROOT/'build/diagnostics/phy_candidate'):raise ValueError('Use an isolated PHY bundle')
    directory=ROOT/'build/release';directory.mkdir(parents=True,exist_ok=True)
    with (directory/'.promotion.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        report=json.loads((bundle/'release/status.json').read_text())
        args=report_arguments(bundle,report)
        # Reanalysis is mandatory even if the saved pass flag and hashes agree.
        check=subprocess.run([sys.executable,str(ROOT/'scripts/check_release.py')]+args,cwd=ROOT,capture_output=True,text=True)
        (bundle/'release/promotion_recheck.log').write_text(check.stdout+check.stderr);check.check_returncode()
        report=json.loads((bundle/'release/status.json').read_text());report_arguments(bundle,report)
        full,_,_=load(bundle);fast,_,_=load(bundle,True);files=payload(bundle)
        if files['electrical/full.spice']['data']!=full or files['electrical/fast.spice']['data']!=fast:
            raise ValueError('Release libraries differ from the tested bundle')
        identity=dict(bundle=str(bundle.relative_to(ROOT)),bundle_manifest_sha256=digest((bundle/'manifest.json').read_bytes()),
            report_sha256=digest((bundle/'release/status.json').read_bytes()),producer_sha256=digest(Path(__file__).read_bytes()),
            scope='Local macro release; native evidence remains referenced in the OpenLVDS workspace')
        target,stamp=seal(files,identity,directory)
        # Recheck all captured sources before making the sealed package current.
        if any(digest((ROOT/info['source']).read_bytes())!=info['sha256'] for info in files.values()):
            raise ValueError('Release input changed during packaging')
        current=directory/'current.json'
        if current.exists():
            history=directory/'history';history.mkdir(exist_ok=True)
            (history/(str(time.time_ns())+'.json')).write_bytes(current.read_bytes())
        pointer=dict(package=str(target.relative_to(ROOT)),manifest_sha256=stamp,bundle=identity['bundle'])
        temp=current.with_suffix('.tmp');temp.write_text(json.dumps(pointer,indent=2)+'\n');temp.replace(current)
    print(current,flush=True);return current


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle',type=Path)
    p.add_argument('--check-netlists',action='store_true',help='Verify digital handoff files without publishing a release')
    a=p.parse_args()
    if a.check_netlists:check_netlists(a.bundle)
    else:promote(a.bundle)


if __name__=='__main__':main()
