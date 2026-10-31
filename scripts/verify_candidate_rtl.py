#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run the complete functional regression on the staged 15/8-port DLL and buf_4 TX."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from dll_campaign import atomic
from layout import circuits
from phy_candidate import load
import verify_rtl

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def connections(text,instance):
    match=re.search(r'\b'+re.escape(instance)+r'\s*\((.*?)\);',text,re.S)
    if not match:raise ValueError('Missing DLL RTL instance '+instance)
    pairs=re.findall(r'\.(\w+)\s*\(\s*(\w+)\s*\)',match[1])
    if len(dict(pairs))!=len(pairs):raise ValueError('Duplicated DLL RTL terminal')
    return dict(pairs)


def check_assembly(source,rtl):
    definitions=circuits(source);ports,rows=definitions['openlvds_dll_core']
    instances={name:(nodes,model) for name,nodes,model,_ in rows}
    for label,instance in [('XA','analog'),('XPFD','phase_detector')]:
        nodes,model=instances[label];expected=dict(zip(definitions[model][0],nodes))
        expected={('VPWR' if pin=='VDDD' else 'VGND' if pin=='VSS' else pin):net
                  for pin,net in expected.items()} if label=='XPFD' else expected
        # SPICE and RTL use different local spellings for the same wire.
        expected={pin:('pd_ref' if net=='PD_REF' else net) for pin,net in expected.items()}
        if connections(rtl,instance)!=expected:raise ValueError('Candidate DLL RTL wiring differs from SPICE: '+instance)
    header=re.search(r'\bmodule openlvds_dll_core\s*\((.*?)\);',rtl,re.S)[1]
    actual=[part.split()[-1] for part in header.split(',')]
    if actual!=ports:raise ValueError('Candidate DLL public ports differ from SPICE')


def captured_sources(bundle):
    load(bundle);identity=json.loads((bundle/'manifest.json').read_text())['identity']
    q=json.loads((ROOT/identity['qualification']/'manifest.json').read_text());native=q['identity']['full_models']
    source=ROOT/native['layout']/'candidate.spice'
    core=ROOT/'rtl/experiments/openlvds_dll_core_area.v';check_assembly(source.read_text(),core.read_text())
    physical=json.loads((ROOT/identity['tx']/'summary.json').read_text());archive=ROOT/physical['input_archive']
    pfd=json.loads((ROOT/native['pfd']/'summary.json').read_text());pfd_archive=ROOT/pfd['input_archive']
    config=json.loads((pfd_archive/'config.json').read_text())
    pfd_source=pfd_archive/Path(config['VERILOG_FILES'][0]).name
    files={}
    for folder in ['rtl','models','tb']:
        for path in sorted((ROOT/folder).glob('*.v')):files[folder+'/'+path.name]=path
    for path in archive.glob('*.v'):
        if path.name.endswith('_blackboxes.v'):continue
        name='openlvds_tx_core.v' if re.search(r'\bmodule\s+openlvds_tx_core\b',path.read_text()) else path.name
        files['rtl/'+name]=path
    files['rtl/openlvds_dll_core.v']=core
    files['models/analog_functional.v']=ROOT/'models/analog_area_functional.v'
    # The alternate model is installed under the verifier's established name.
    files.pop('models/analog_area_functional.v',None)
    files['sky130/openlvds_analog.v']=ROOT/'sky130/experiments/openlvds_analog_area.v'
    for path in (ROOT/'sky130').glob('*_blackboxes.v'):files['sky130/'+path.name]=path
    files['physical_pfd.v']=pfd_source
    files['requirements.json']=ROOT/'requirements.json'
    files['scripts/verify_rtl.py']=ROOT/'scripts/verify_rtl.py'
    return files


def stamp(bundle,files,tools=None):
    if tools is None:
        tools={name:dict(path=str(Path(shutil.which(name) or '/missing/'+name).resolve())) for name in ['iverilog','vvp']}
        for info in tools.values():info['sha256']=digest(Path(info['path']))
    if set(tools)!={'iverilog','vvp'} or any(digest(Path(info['path']))!=info['sha256'] for info in tools.values()):
        raise ValueError('Candidate RTL tool binary changed')
    return dict(bundle_manifest_sha256=digest(bundle/'manifest.json'),producer_sha256=digest(Path(__file__)),
        sources={name:dict(path=str(path.relative_to(ROOT)),sha256=digest(path)) for name,path in files.items()},
        tools=tools)


def source_fingerprint(root):
    sources=sorted((root/'rtl').glob('*.v'))+[root/'tb/tb_link.v']
    dll=[root/'rtl/openlvds_dll_control.v',root/'tb/tb_dll_control.v']
    phy=sorted((root/'rtl').glob('*.v'))+[root/'models/analog_functional.v',root/'tb/tb_phy.v']
    return hashlib.sha256(b''.join(p.read_bytes() for p in sources+dll+phy)+
        (root/'models/sky130_tx_functional.v').read_bytes()+(root/'requirements.json').read_bytes()+
        (ROOT/'scripts/verify_rtl.py').read_bytes()).hexdigest()


def verify(bundle):
    bundle=Path(bundle).resolve();pointer=json.loads((bundle/'rtl_validation/current.json').read_text())
    root=(ROOT/pointer['root']).resolve()
    if not root.is_relative_to(bundle/'rtl_validation'):raise ValueError('Candidate RTL evidence outside bundle')
    manifest=json.loads((root/'manifest.json').read_text());files=captured_sources(bundle)
    if manifest['identity']!=stamp(bundle,files,manifest['identity']['tools']):raise ValueError('Candidate RTL sources or tools changed')
    for name,info in manifest['identity']['sources'].items():
        if digest(root/name)!=info['sha256']:raise ValueError('Captured candidate RTL changed')
    report=json.loads((root/'summary.json').read_text());result=report['result']
    req=json.loads((root/'requirements.json').read_text())
    expected={f'{i}_{m}m_d{d:.2f}_s{s:+d}' for i,m,d,s in itertools.product(
        ['rtl','sky130'],req['clock_test_mhz'],req['clock_duty'],req['channel_skew_ps'])}
    cases=result['cases']
    if (digest(root/'summary.json')!=pointer['summary_sha256'] or not report['passed'] or
        report['manifest_sha256']!=digest(root/'manifest.json') or not result['passed'] or result['smoke'] or
        result['source_hash']!=source_fingerprint(root) or not result['dll_control_passed'] or
        not result['functional_phy_passed'] or not result['native_functional_phy_passed'] or
        len(cases)!=len(expected) or {c['case'] for c in cases}!=expected or
        min(result['native_total_bits'],result['rtl_total_bits'])<req['minimum_behavioral_bits']):
        raise ValueError('Complete candidate RTL regression has not passed')
    for case in cases:
        text=(root/'build/rtl'/(case['case']+'.log')).read_text();bits=re.search(r'PASS bits=(\d+) pairs=(\d+)',text)
        if not case['passed'] or not bits or case['bits']!=int(bits[1]) or case['pairs']!=int(bits[2]):
            raise ValueError('Candidate RTL case log differs from summary')
    for name,value in report['artifacts'].items():
        if not (root/name).resolve().is_relative_to(root) or digest(root/name)!=value:
            raise ValueError('Candidate RTL artifact changed')
    return root,report


def run(bundle):
    bundle=Path(bundle).resolve();files=captured_sources(bundle);identity=stamp(bundle,files)
    root=bundle/'rtl_validation'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True,exist_ok=True)
    for name,path in files.items():
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and target.read_bytes()!=path.read_bytes():raise ValueError('Captured RTL input changed')
        target.write_bytes(path.read_bytes())
    atomic(root/'manifest.json',dict(identity=identity))
    physical=(root/'physical_pfd.v').read_text();match=re.search(r'\bmodule\s+lvds_pfd\s*\(.*?\);',physical,re.S)
    if not match:raise ValueError('Missing captured native PFD interface')
    (root/'pfd_interface.v').write_text(match[0]+'\nendmodule\n')
    compile=subprocess.run(['iverilog','-g2012','-Wall','-DUSE_POWER_PINS','-s','openlvds_dll_core',
        '-o',str(root/'interfaces.vvp'),str(root/'rtl/openlvds_dll_core.v'),str(root/'pfd_interface.v'),
        str(root/'sky130/openlvds_analog.v')],capture_output=True,text=True)
    (root/'interfaces.log').write_text(compile.stdout+compile.stderr);compile.check_returncode()
    previous_root=verify_rtl.ROOT;previous_args=sys.argv
    try:
        verify_rtl.ROOT=root;sys.argv=[str(ROOT/'scripts/verify_rtl.py')];status=verify_rtl.main()
    finally:verify_rtl.ROOT=previous_root;sys.argv=previous_args
    if identity!=stamp(bundle,captured_sources(bundle)):raise ValueError('Candidate RTL inputs changed during regression')
    result=json.loads((root/'build/rtl/summary.json').read_text())
    artifacts={str(p.relative_to(root)):digest(p) for p in (root/'build/rtl').iterdir() if p.is_file()}
    artifacts.update({name:digest(root/name) for name in ['interfaces.log','interfaces.vvp','pfd_interface.v']})
    atomic(root/'summary.json',dict(passed=status==0 and result['passed'],manifest_sha256=digest(root/'manifest.json'),
        result=result,artifacts=artifacts,scope='Functional and interface qualification; native electrical gates remain separate'))
    if status:return status
    atomic(bundle/'rtl_validation/current.json',dict(root=str(root.relative_to(ROOT)),summary_sha256=digest(root/'summary.json')))
    verify(bundle);print(root/'summary.json',flush=True);return 0


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle',type=Path);a=p.parse_args();return run(a.bundle)


if __name__=='__main__':sys.exit(main())
