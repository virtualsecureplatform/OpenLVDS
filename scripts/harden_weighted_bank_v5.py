#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Bring the verified full bank through PDN, I/O and detailed placement only."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import normalize_weighted_bank_frames_v3 as frames
import weighted_bank_flow_v3 as source
import harden_dcdl_bank_direct_v2 as old
import build_compound_drivers_v3 as geometry
import harden_weighted_bank_v4 as prior
import weighted_bank_power_access_v2 as access

ROOT=frames.ROOT
sha=frames.sha
atomic=old.atomic
VERSION='full-weighted-bank-existing-m3-power-placement-bringup-v2.4'
CONTEXT='weighted_bank_bringup_v2'
STOP_AT='OpenROAD.DetailedPlacement'


def checked_parent(parent):
    m=frames.bound(parent);i=m['identity'];receipt=ROOT/i['parent']
    assembly=ROOT/json.loads((receipt/'manifest.json').read_text())['identity']['parent']
    am=json.loads((assembly/'manifest.json').read_text());macros=json.loads((parent/'macros.json').read_text())
    spec=source.parse((assembly/'bank.spice').read_text(),am['identity']['orders'])
    files=[p for p in parent.rglob('*') if p.is_file()]
    files += [Path(n) if Path(n).is_absolute() else ROOT/n for n in i['inputs']]
    files += [assembly/n for n in ['manifest.json','summary.json','bank.spice']]
    return am,macros,spec,files


def configuration(macros,die,places,rtl,blackboxes):
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';tt=str(pdk/'libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib')
    return dict(DESIGN_NAME='openlvds_weighted_bank_physical_v2',VERILOG_FILES=[str(rtl)],EXTRA_VERILOG_MODELS=[str(blackboxes)],
        VERILOG_DEFINES=['USE_POWER_PINS'],MACROS=macros,MANUAL_GLOBAL_PLACEMENTS=places,
        CLOCK_PORT=None,CLOCK_PERIOD=2.439024,IO_PIN_PLACEMENT_MODE='matching',
        PNR_SDC_FILE=str(ROOT/'constraints/v2/weighted_bank.sdc'),SIGNOFF_SDC_FILE=str(ROOT/'constraints/v2/weighted_bank.sdc'),
        PDN_CFG=str(ROOT/'constraints/v2/weighted_bank_pdn_v2.tcl'),
        PDN_MACRO_CONNECTIONS=['(forward.*|turn.*|pass.*|merge.*|fine_buffer.*|fine_inverse.*) VPWR VGND VPWR VGND',
                               'fine[0-4] VPWR VGND VDD VSS'],
        FP_SIZING='absolute',DIE_AREA=die,BOTTOM_MARGIN_MULT=1,FP_MACRO_HORIZONTAL_HALO=6,FP_MACRO_VERTICAL_HALO=1.5,
        FP_CORE_UTIL=20,PL_TARGET_DENSITY_PCT=75,VDD_NETS=['VPWR'],GND_NETS=['VGND'],PAD_LIBS=None,DECAP_CELLS=[],
        ENDCAP_CELL='sky130_fd_sc_hd__tapvpwrvgnd_1',LIB={'nom_':[tt],'*_tt_025C_1v80':[tt]},
        STA_CORNERS=['nom_tt_025C_1v80','min_tt_025C_1v80','max_tt_025C_1v80'],SYNTH_ELABORATE_ONLY=True,
        SYNTH_HIERARCHY_MODE='flatten',EXTRA_EXCLUDED_CELLS=['sky130_fd_sc_hd__clkdlybuf*'],
        RUN_CTS=False,RUN_POST_CTS_RESIZER_TIMING=False,DESIGN_REPAIR_BUFFER_INPUT_PORTS=False,DESIGN_REPAIR_BUFFER_OUTPUT_PORTS=False,
        RUN_POST_GRT_DESIGN_REPAIR=False,RUN_POST_GRT_RESIZER_TIMING=False,RUN_MCSTA=False,RUN_EQY=False,
        LINTER_DISABLE_WARNINGS_BLACKBOX=['UNDRIVEN','UNUSEDSIGNAL','PINMISSING','TIMESCALEMOD'],meta=dict(flow='Classic'))


def prepare(parent,failure,access_view):
    am,macros,spec,files=checked_parent(parent);ai=am['identity']
    vm=access.bound(access_view)
    if vm['identity']['parent']!=str(parent.relative_to(ROOT)):raise ValueError('Power view parent mismatch')
    macros=json.loads((access_view/'macros.json').read_text())
    files += [p for p in access_view.iterdir() if p.is_file()]+[Path(access.__file__),Path(access.lef.__file__)]
    fm=prior.bound(failure);fr=json.loads((failure/'summary.json').read_text())
    if (fm['identity']['parent']!=str(parent.relative_to(ROOT)) or fr['returncode']==0
        or 'PSM-0069' not in (failure/'flow.log').read_text()
        or not fr.get('placement_check',{}).get('interface_verified')):raise ValueError('Require retained disconnected PG failure with unchanged circuit')
    files += [failure/n for n in ['manifest.json','config.json','summary.json','state.json','flow.log']]
    files += [Path(prior.__file__)]
    die=list(ai['die']);die[2]+=35.
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';sc=pdk/'libs.ref/sky130_fd_sc_hd'
    lef=(sc/'lef/sky130_fd_sc_hd.lef').read_text();sizes={}
    for c in spec['cells']:
        if c['model'] in sizes:continue
        text=lef if c['model'].startswith(source.SC) else Path(macros[c['model']]['lef'][0]).read_text()
        sizes[c['model']]=geometry.lef_cell(text,c['model'])
    places=source.control_placements(spec,sizes,macros,die);boxes={}
    for c in spec['cells']:
        p=places.get(c['name'])
        if p is None:p=macros[c['model']]['instances'][c['name']]
        x,y=p['location'];size=sizes[c['model']];boxes[c['name']]=[x,y,x+size['width'],y+size['height']]
    old.assembly.no_overlaps(boxes,die)
    rtl=ROOT/'sky130/v2/weighted_bank_flow_v3.v';bb=ROOT/'sky130/v2/weighted_bank_flow_blackboxes_v3.v'
    pins={name:macro['pins'] for name,macro in ai['macros'].items()}
    for path,text in [(rtl,source.verilog(spec)),(bb,source.blackboxes(macros,ai['orders'],pins))]:
        if path.exists() and path.read_text()!=text:raise ValueError('Retain existing physical-flow source')
        if not path.exists():path.write_text(text)
    config=configuration(macros,die,places,rtl,bb)
    files += [Path(__file__),Path(source.__file__),Path(source.base.__file__),Path(frames.__file__),Path(old.__file__),Path(geometry.__file__),ROOT/'scripts/harden_dcc_v2.py',
              rtl,bb,ROOT/'constraints/v2/weighted_bank.sdc',ROOT/'constraints/v2/weighted_bank_pdn_v2.tcl']
    pdks=[sc/n for n in ['lef/sky130_fd_sc_hd.lef','gds/sky130_fd_sc_hd.gds','spice/sky130_fd_sc_hd.spice','lib/sky130_fd_sc_hd__tt_025C_1v80.lib']]
    pdks += [pdk/'libs.tech/magic/sky130A.magicrc',pdk/'libs.tech/netgen/sky130A_setup.tcl']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),failure=str(failure.relative_to(ROOT)),access_view=str(access_view.relative_to(ROOT)),right_margin_extension_um=35.,spec=spec,net_aliases=source.net_aliases(spec),configuration=config,stop_at=STOP_AT,
                  inputs={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):sha(p) for p in files},
                  pdk_files={str(p):sha(p) for p in pdks},tools=old.tool_identity())
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False));atomic(out/'config.json',config);return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or i['stop_at']!=STOP_AT
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(Path(n) if Path(n).is_absolute() else ROOT/n)!=h for n,h in i['inputs'].items())
        or any(sha(Path(n))!=h for n,h in i['pdk_files'].items()) or old.tool_identity()!=i['tools']
        or json.loads((out/'config.json').read_text())!=i['configuration'] or source.net_aliases(i['spec'])!=i['net_aliases']):raise ValueError('Weighted-bank bringup context changed')
    frames.bound(ROOT/i['parent']);prior.bound(ROOT/i['failure']);access.bound(ROOT/i['access_view']);return m


def check_db(out,db,spec,macros):
    script=out/'check_db.tcl'
    script.write_text(f'''read_db {{{db}}}
set block [ord::get_db_block]
set f [open {{{out/'connections.tsv'}}} w]
set g [open {{{out/'placements.tsv'}}} w]
foreach inst [$block getInsts] {{
  set b [$inst getBBox]
  puts $g "[$inst getName]\\t[[$inst getMaster] getName]\\t[$inst getPlacementStatus]\\t[$inst getOrient]\\t[$b xMin]\\t[$b yMin]\\t[$b xMax]\\t[$b yMax]"
  foreach term [$inst getITerms] {{
    set net [$term getNet]
    set netname ""
    if {{$net != "NULL"}} {{set netname [$net getName]}}
    puts $f "[$inst getName]\\t[[$inst getMaster] getName]\\t[[$term getMTerm] getName]\\t$netname"
  }}
}}
close $f
close $g
set f [open {{{out/'ports.tsv'}}} w]
foreach term [$block getBTerms] {{
  set count 0
  foreach pin [$term getBPins] {{incr count [llength [$pin getBoxes]]}}
  puts $f "[$term getName]\\t[$term getIoType]\\t[$term getSigType]\\t$count"
}}
close $f
check_placement -verbose
exit
''')
    with (out/'check_db.log').open('w') as log:p=subprocess.run(['openroad','-no_init','-exit',str(script)],cwd=out,stdout=log,stderr=subprocess.STDOUT)
    def rows(name):
        path=out/name
        return [line.split('\t') for line in path.read_text().splitlines()] if path.exists() else []
    terms=rows('ports.tsv');connections=rows('connections.tsv');placements={w[0]:w for w in rows('placements.tsv')}
    signal=[p for p in spec['ports'] if p not in ['VPWR','VGND']];physical_pins={w[0]:int(w[3]) for w in terms}
    unplaced=[c['name'] for c in spec['cells'] if c['name'] not in placements or placements[c['name']][2] not in ['PLACED','FIRM','LOCKED','COVER']]
    interface=source.connections_pass(connections,[w[0] for w in terms],spec) if all(len(w)==4 for w in connections) else False
    wanted_ports={n:('INOUT','POWER' if n=='VPWR' else 'GROUND') if n in ['VPWR','VGND'] else ('OUTPUT' if n=='OUT' else 'INPUT','SIGNAL') for n in spec['ports']}
    public={w[0]:tuple(w[1:3]) for w in terms};public_ok=public==wanted_ports
    moved=[]
    for model,macro in macros.items():
        size=geometry.lef_cell(Path(macro['lef'][0]).read_text(),model)
        for name,placement in macro['instances'].items():
            w=placements.get(name);x,y=placement['location'];expected=[x,y,x+size['width'],y+size['height']]
            if w is None or w[3]!='R0' or any(abs(int(a)/1000-b)>.001 for a,b in zip(w[4:],expected)):moved.append(name)
    return dict(returncode=p.returncode,interface_verified=interface,unplaced_original_cells=unplaced,
                public_interface_passed=public_ok,moved_or_rotated_macros=moved,
                all_signal_io_pins_placed=all(physical_pins.get(n,0)>0 for n in signal),signal_io_count=len(signal),
                passed=p.returncode==0 and interface and public_ok and not unplaced and not moved and all(physical_pins.get(n,0)>0 for n in signal),qualified_phy=False)


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior placement/PDN experiment')
        atomic(out/'state.json',dict(status='bringing_up',qualified_phy=False));tag='weighted-bank-'+out.name[:12]
        argv=[sys.executable,'-m','librelane','--manual-pdk','--pdk-root',os.environ['PDK_ROOT'],'-p','sky130A','-s','sky130_fd_sc_hd',
              '--condensed','--hide-progress-bar','--skip','OpenROAD.GlobalPlacementSkipIO','--skip','OpenROAD.GlobalPlacement',
              '--skip','OpenROAD.RepairDesignPostGPL','--to',STOP_AT,'--run-tag',tag,str(out/'config.json')]
        try:
            with (out/'flow.log').open('w') as log:p=subprocess.run(argv,cwd=out,stdout=log,stderr=subprocess.STDOUT)
            bound(out);folder=out/'runs'/tag;dbs=sorted(folder.rglob('*.odb'),key=lambda p:p.stat().st_mtime)
            check=check_db(out,dbs[-1],m['identity']['spec'],m['identity']['configuration']['MACROS']) if dbs else None
            states=list(folder.glob('*detailedplacement/state_out.json'))
            passed=p.returncode==0 and bool(states) and check is not None and check['passed']
            result=dict(returncode=p.returncode,target_step=STOP_AT,target_step_completed=bool(states),run=str(folder.relative_to(ROOT)),
                        database=str(dbs[-1].relative_to(ROOT)) if dbs else None,placement_check=check,placement_bringup_passed=passed,
                        physical_implementation_passed=False,route_complete=False,electrical_qualification_passed=False,qualified_phy=False,
                        scope='Full native candidate through PDN generation, I/O and detailed placement only; no signal routing, full DRC/LVS/antenna/RC, native timing, code ROM or PHY admission')
            atomic(out/'summary.json',result);atomic(out/'state.json',dict(status='placement_complete' if passed else 'held_bringup_failed',qualified_phy=False));return result
        except Exception as exc:
            atomic(out/'state.json',dict(status='bringup_exception',error=str(exc),qualified_phy=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);p.add_argument('--failure',type=Path);p.add_argument('--access-view',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:
        if a.failure is None or a.access_view is None:p.error('Provide the retained PG failure and native power-access view')
        out=prepare(out,a.failure.resolve(),a.access_view.resolve());print(out,flush=True)
    if a.action in ['run','campaign']:print(json.dumps(run(out),indent=2),flush=True)
