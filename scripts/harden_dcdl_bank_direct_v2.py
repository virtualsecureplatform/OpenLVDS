#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Route the complete native MIM delay bank after six-macro OpenDB preflight.

Keep every native delay/control cell and require actual macro GDS/SPICE.
Routing/DRC/LVS do not admit delay range, legal-code ROM or whole-clock timing.
"""
import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import dcdl_mim_bank_direct_v2 as bank
import assemble_dcdl_bank_direct_inputs_v2 as assembly
from harden_dcc_v2 import tool_identity

ROOT=assembly.ROOT
VERSION='whole-native-mim-bank-direct-ports-route-v2.1'
sha=assembly.sha


def sanitize(value,path=''):
    bad=[]
    if isinstance(value,float) and not math.isfinite(value):return None,[path]
    if isinstance(value,dict):
        clean={}
        for k,v in value.items():clean[k],found=sanitize(v,path+'/'+str(k));bad+=found
        return clean,bad
    if isinstance(value,list):
        clean=[]
        for n,v in enumerate(value):
            item,found=sanitize(v,path+'/'+str(n));clean.append(item);bad+=found
        return clean,bad
    return value,bad


def atomic(path,value):
    temp=path.with_name(path.name+'.tmp');temp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');temp.replace(path)


def checked_parent(parent):
    m=json.loads((parent/'manifest.json').read_text());i=m['identity'];r=json.loads((parent/'summary.json').read_text())
    if (i['version']!=assembly.VERSION or parent.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or not r['passed'] or r['logical_instances']!=172 or r['macro_count']!=94 or r['route_complete']
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())):
        raise ValueError('Require immutable complete bank assembly preflight')
    macros=json.loads((parent/'macros.json').read_text())
    if {n:{k:v for k,v in macro.items() if k!='pins'} for n,macro in i['macros'].items()}!=macros:raise ValueError('Macro fragment differs from preflight')
    files=[parent/n for n in ['manifest.json','summary.json','macros.json','pins.tsv','boxes.tsv','macro_preflight.odb']]
    files += [ROOT/n for n in i['inputs']]
    for name,macro in macros.items():
        source=Path(macro['spice'][0])
        if not source.is_file():raise ValueError('Require actual macro source '+name)
        macro['spice']=[str(source)];files.append(source)
    return m,macros,files


def control_placements(widths):
    result={};x=9.2;y=116.96;row=0
    for cell in bank.instances():
        if not cell['model'].startswith(bank.native.SC):continue
        width=widths[cell['model']]
        if x+width>147.2:x=9.2;y+=2.72;row+=1
        if y+2.72>130.56:raise ValueError('Control placement strip exhausted')
        result[cell['name']]=dict(location=[round(x,3),round(y,3)],orientation='N' if row%2==0 else 'FS')
        x+=math.ceil(width/.46)*.46+.92
    if len(result)!=78:raise ValueError('Require every original control/tie cell')
    return result


def configuration(macros,die):
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';tt=str(pdk/'libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib')
    lef=(pdk/'libs.ref/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef').read_text()
    widths={c['model']:assembly.drivers.lef_cell(lef,c['model'])['width'] for c in bank.instances() if c['model'].startswith(bank.native.SC)}
    return dict(MANUAL_GLOBAL_PLACEMENTS=control_placements(widths),IO_PIN_PLACEMENT_MODE='random_equidistant',DESIGN_NAME=bank.name(),VERILOG_FILES=[str(ROOT/'sky130/v2'/f'{bank.name()}.v')],
        EXTRA_VERILOG_MODELS=[str(ROOT/'sky130/v2/dcdl_mim_bank_blackboxes_v2.v')],VERILOG_DEFINES=['USE_POWER_PINS'],
        MACROS=macros,CLOCK_PORT=None,CLOCK_PERIOD=2.439024,PNR_SDC_FILE=str(ROOT/'constraints/v2/dcdl_bank.sdc'),
        SIGNOFF_SDC_FILE=str(ROOT/'constraints/v2/dcdl_bank.sdc'),PDN_CFG=str(ROOT/'constraints/v2/dcdl_bank_pdn_v5.tcl'),
        PDN_MACRO_CONNECTIONS=['(input_buffer|output_buffer|forward.*|turn.*|pass.*|merge.*) VPWR VGND VPWR VGND',
            'fine_unit.* VPWR VGND VDD VSS'],
        FP_SIZING='absolute',DIE_AREA=die,BOTTOM_MARGIN_MULT=1,FP_MACRO_HORIZONTAL_HALO=6,FP_MACRO_VERTICAL_HALO=1.5,FP_CORE_UTIL=20,PL_TARGET_DENSITY_PCT=75,
        VDD_NETS=['VPWR'],GND_NETS=['VGND'],PAD_LIBS=None,DECAP_CELLS=[],ENDCAP_CELL='sky130_fd_sc_hd__tapvpwrvgnd_1',
        LIB={'nom_':[tt],'*_tt_025C_1v80':[tt]},STA_CORNERS=['nom_tt_025C_1v80','min_tt_025C_1v80','max_tt_025C_1v80'],
        SYNTH_ELABORATE_ONLY=True,SYNTH_HIERARCHY_MODE='flatten',EXTRA_EXCLUDED_CELLS=['sky130_fd_sc_hd__clkdlybuf*'],
        RUN_CTS=False,RUN_POST_CTS_RESIZER_TIMING=False,DESIGN_REPAIR_BUFFER_INPUT_PORTS=False,
        DESIGN_REPAIR_BUFFER_OUTPUT_PORTS=False,RUN_POST_GRT_DESIGN_REPAIR=False,RUN_POST_GRT_RESIZER_TIMING=False,
        RUN_MCSTA=False,RUN_EQY=False,LINTER_DISABLE_WARNINGS_BLACKBOX=['UNDRIVEN','UNUSEDSIGNAL','PINMISSING','TIMESCALEMOD'],
        meta=dict(flow='Classic'))


def prepare(parent):
    m,macros,files=checked_parent(parent)
    config=configuration(macros,m['identity']['die'])
    source=ROOT/'sky130/v2'/f'{bank.name()}.v';blackboxes=ROOT/'sky130/v2/dcdl_mim_bank_blackboxes_v2.v'
    if source.read_text()!=bank.verilog() or blackboxes.read_text()!=bank.blackboxes():raise ValueError('Bank RTL differs from exact retained generator')
    files += [Path(__file__),Path(bank.__file__),Path(bank.native.__file__),Path(bank.base.__file__),Path(assembly.__file__),ROOT/'scripts/harden_dcc_v2.py',
        source,blackboxes,ROOT/'constraints/v2/dcdl_bank.sdc',ROOT/'constraints/v2/dcdl_bank_pdn_v5.tcl']
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';sc=pdk/'libs.ref/sky130_fd_sc_hd'
    pdks=[sc/n for n in ['lef/sky130_fd_sc_hd.lef','gds/sky130_fd_sc_hd.gds','spice/sky130_fd_sc_hd.spice','lib/sky130_fd_sc_hd__tt_025C_1v80.lib']]
    pdks += [pdk/'libs.tech/magic/sky130A.magicrc',pdk/'libs.tech/netgen/sky130A_setup.tcl']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),configuration=config,tools=tool_identity(),
        inputs={str(p.relative_to(ROOT)):sha(p) for p in files},pdk_files={str(p):sha(p) for p in pdks})
    out=ROOT/'build/diagnostics/dcdl_bank_physical_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False));atomic(out/'config.json',config);return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (i['version']!=VERSION or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or tool_identity()!=i['tools'] or json.loads((out/'config.json').read_text())!=i['configuration']):raise ValueError('Whole-bank physical context changed')
    checked_parent(ROOT/i['parent']);return m


def connections_pass(rows,terms):
    """Allow actual constant cloning only, never substitution of delay cells."""
    cells={}
    for inst,model,pin,net in rows:
        if inst in cells and cells[inst]['model']!=model:return False
        cell=cells.setdefault(inst,dict(model=model,pins={}))
        if pin in cell['pins']:return False
        cell['pins'][pin]=net
    highs={c['pins'].get('HI') for c in cells.values() if c['model']==bank.native.SC+'conb_1'}-{None,''}
    lows={c['pins'].get('LO') for c in cells.values() if c['model']==bank.native.SC+'conb_1'}-{None,''}
    if not highs or not lows or highs&lows:return False
    expected=bank.instances();names={c['name'] for c in expected}
    for c in expected:
        if c['name'] not in cells:return False
        actual=cells[c['name']]
        if actual['model']!=c['model']:return False
        pins=dict(c['pins'])
        if c['model'].startswith(bank.native.SC):pins.update(VPWR='VPWR',VPB='VPWR',VGND='VGND',VNB='VGND')
        for pin,net in pins.items():
            observed=actual['pins'].get(pin)
            if net=='high':
                if observed not in highs:return False
            elif net=='low':
                if observed not in lows:return False
            elif observed!=net:return False
    for n,c in cells.items():
        if n in names:continue
        kind=c['model'].removeprefix(bank.native.SC)
        if not kind.startswith(('fill_','tapvpwrvgnd_','decap_','conb_','diode_')):return False
    return set(terms)=={'IN','OUT','VPWR','VGND',*bank.native.controls(16,32)}


def check_db(out,db):
    script=out/'check_final.tcl';dump=out/'connections.tsv';ports=out/'ports.txt'
    script.write_text(f'''read_db {{{db}}}
set block [ord::get_db_block]
set f [open {{{dump}}} w]
foreach inst [$block getInsts] {{
  foreach term [$inst getITerms] {{
    set net [$term getNet]
    set netname ""
    if {{$net != "NULL"}} {{set netname [$net getName]}}
    puts $f "[$inst getName]\t[[$inst getMaster] getName]\t[[$term getMTerm] getName]\t$netname"
  }}
}}
close $f
set f [open {{{ports}}} w]
foreach term [$block getBTerms] {{puts $f [$term getName]}}
close $f
exit
''')
    with (out/'check_final.log').open('w') as log:p=subprocess.run(['openroad','-no_init','-exit',str(script)],cwd=out,stdout=log,stderr=subprocess.STDOUT)
    if p.returncode or not dump.exists() or not ports.exists():return False
    rows=[line.split('\t') for line in dump.read_text().splitlines()]
    return all(len(r)==4 for r in rows) and connections_pass(rows,ports.read_text().splitlines())


def run(out):
    bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior whole-bank physical run')
        atomic(out/'state.json',dict(status='hardening',qualified_phy=False));tag='dcdl-bank-v2-'+out.name[:12]
        argv=['python3','-m','librelane','--manual-pdk','--pdk-root',os.environ['PDK_ROOT'],'-p','sky130A','-s','sky130_fd_sc_hd',
            '--condensed','--hide-progress-bar','--skip','OpenROAD.GlobalPlacementSkipIO','--skip','OpenROAD.GlobalPlacement','--skip','OpenROAD.RepairDesignPostGPL','--run-tag',tag,str(out/'config.json')]
        with (out/'flow.log').open('w') as log:p=subprocess.run(argv,cwd=out,stdout=log,stderr=subprocess.STDOUT)
        bound(out);folder=out/'runs'/tag;path=folder/'final/metrics.json';raw=json.loads(path.read_text()) if path.exists() else {}
        metrics,nonfinite=sanitize(raw);keys=['route__drc_errors','magic__drc_error__count','klayout__drc_error__count',
            'design__lvs_error__count','antenna__violating__nets','antenna__violating__pins']
        db=folder/'final/odb'/f'{bank.name()}.odb';interface=check_db(out,db) if db.exists() else False
        result=dict(returncode=p.returncode,run=str(folder.relative_to(ROOT)),metrics=metrics,nonfinite_metric_paths=nonfinite,
            raw_metrics_sha256=sha(path) if path.exists() else None,interface_verified=interface,
            physical_implementation_passed=bool(p.returncode==0 and interface and all(k in metrics and metrics[k]==0 for k in keys)),
            qualified_phy=False,electrical_qualification_passed=False,scope='Whole 172-instance delay-bank PNR/DRC/LVS only; fresh passive whole-bank RC, native range/ROM and full-clock timing remain required')
        atomic(out/'summary.json',result);atomic(out/'state.json',dict(status='physical_complete' if result['physical_implementation_passed'] else 'held_physical_failed',qualified_phy=False));return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:
        out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(json.dumps(run(out),indent=2,allow_nan=False),flush=True)
