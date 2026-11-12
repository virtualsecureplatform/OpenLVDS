#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Harden DDR logic; keep physical failures visible in the evidence manifest."""
import argparse
import fcntl
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
from physical_policy import delay_cells_absent,pfd_paths_retained,tx_cells_retained,pfd_area_paths_retained,tx_buffered_paths_retained

ROOT=Path(__file__).resolve().parents[1]

def harden_io_ref(tag):
    """Reference top built only from the published I/O macro views.

    The I/O macros have two supplies over one ground. LibreLane pairs each
    power net with a ground net, so the shared ground is listed once per pair.
    """
    release=ROOT/'build/release_io_300';views=json.loads((release/'views.json').read_text())
    digest=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
    out=ROOT/'build/physical/io_ref';out.mkdir(parents=True,exist_ok=True)
    lock=(out/'.run.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise RuntimeError('io-ref: physical flow is already running')
    design='openlvds_io_ref_top';sources=[ROOT/'examples/openlvds_io_ref_top.v'];sdc=ROOT/'constraints/io_ref_top.sdc'
    tt=str(Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib')
    # Floorplan: the macros abut the left and right core edges, so no
    # standard-cell row sliver is left beside a macro without a power strap or
    # well tap. Logic sits in the full-width band below and the gap between.
    candidate=json.loads((release/'candidate.json').read_text()) if (release/'candidate.json').exists() else None
    layout=json.loads((ROOT/'build/layout/current.json').read_text())['designs']
    size={m:(layout[m]['width_um'],layout[m]['height_um']) for m in ['openlvds_io_tx','openlvds_io_rx']}
    # Sized from the macros: a 190 um gap between them carries a power-strap
    # set and the logic, with a 180 um full-width row band below.
    import math
    band=200.;width=math.ceil((size['openlvds_io_tx'][0]+size['openlvds_io_rx'][0]+190)/10)*10
    height=math.ceil((max(v[1] for v in size.values())+band+25)/10)*10
    core=[20.,20.,20.+width,float(height)];die=[0,0,core[2]+20,core[3]+20]
    places=[('openlvds_io_tx','tx_macro',[core[0],band]),('openlvds_io_rx','rx_macro',[round(core[2]-size['openlvds_io_rx'][0],2),band])]
    macros={};used=[];lefs={}
    for macro,instance,location in places:
        view=views[macro]
        def path(kind):
            entry=view[kind]
            if digest(ROOT/entry['path'])!=entry['sha256']:raise ValueError(f'{macro}: published {kind} changed')
            used.append(ROOT/entry['path']);return str(ROOT/entry['path'])
        nominal=next(x for x in view['liberty'] if (x['process'],x['temperature_c'])==('tt',25))
        if digest(ROOT/nominal['path'])!=nominal['sha256']:raise ValueError(macro+': published Liberty changed')
        used.append(ROOT/nominal['path'])
        lefs[macro]=ROOT/view['lef']['path']
        macros[macro]=dict(instances={instance:dict(location=location,orientation='N')},gds=[path('gds')],lef=[path('lef')],
            vh=[path('verilog_blackbox')],spice=[path('cdl')],lib={'*':[str(ROOT/nominal['path'])]})
    config=dict(DESIGN_NAME=design,VERILOG_FILES=list(map(str,sources)),VERILOG_DEFINES=['USE_POWER_PINS'],
        CLOCK_PORT='clk',CLOCK_PERIOD=10.0,PNR_SDC_FILE=str(sdc),SIGNOFF_SDC_FILE=str(sdc),
        FP_SIZING='absolute',DIE_AREA=die,CORE_AREA=core,FP_CORE_UTIL=5,PL_TARGET_DENSITY_PCT=20,
        FP_MACRO_HORIZONTAL_HALO=10,FP_MACRO_VERTICAL_HALO=10,RT_MAX_LAYER='met5',
        VDD_NETS=['VDDD','VDDIO'],GND_NETS=['VSS','VSS'],PDN_CONNECT_MACROS_TO_GRID=True,
        PDN_MACRO_CONNECTIONS=['tx_macro VDDD VSS VDDD VSS','tx_macro VDDIO VSS VDDIO VSS',
                               'rx_macro VDDD VSS VDDD VSS','rx_macro VDDIO VSS VDDIO VSS'],
        MACROS=macros,PAD_LIBS=None,DECAP_CELLS=[],RUN_EQY=False,RUN_IRDROP_REPORT=False,
        LINTER_DISABLE_WARNINGS_BLACKBOX=['UNDRIVEN','UNUSEDSIGNAL','PINMISSING','TIMESCALEMOD'],
        meta=dict(flow='Classic'))
    config['LIB']={'nom_':[tt],'*_tt_025C_1v80':[tt]}
    config['STA_CORNERS']=['nom_tt_025C_1v80','min_tt_025C_1v80','max_tt_025C_1v80']
    # Top-level Magic DRC sees each macro as its LEF abstract. Magic derives the
    # resistor implant (RPM) from poly instead of reading it from GDS, so it
    # would re-flag the widened implant that the macro's own full Magic DRC
    # (with mask hints) and KLayout DRC already prove correct.
    abstract=out/'maglef';abstract.mkdir(exist_ok=True)
    script=abstract/'maglef.tcl'
    script.write_text('crashbackups disable\nlocking disable\n'+''.join(f'lef read {lef}\nload {macro}\nsave {abstract}/{macro}.mag\n' for macro,lef in lefs.items())+'quit -noprompt\n')
    rc=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/magic/sky130A.magicrc'
    with (abstract/'maglef.log').open('w') as log:
        made=subprocess.run(['magic','-dnull','-noconsole','-rcfile',str(rc),str(script)],cwd=abstract,stdout=log,stderr=subprocess.STDOUT)
    if made.returncode or not all((abstract/(m+'.mag')).exists() for m in lefs):raise RuntimeError('io-ref: could not create macro abstracts')
    config['MAGIC_DRC_MAGLEFS']=[str(abstract/(m+'.mag')) for m in lefs]
    cfg=out/'config.json';cfg.write_text(json.dumps(config,indent=2)+'\n')
    inputs=sources+[sdc,cfg,release/'views.json']+used
    captured={path:path.read_bytes() for path in inputs}
    stamp=hashlib.sha256(b''.join(captured.values())).hexdigest();tag=tag+'-'+stamp[:12]
    command=['python3','-m','librelane','--manual-pdk','--pdk-root',os.environ['PDK_ROOT'],
             '-p','sky130A','-s','sky130_fd_sc_hd','--condensed','--hide-progress-bar','--run-tag',tag,str(cfg)]
    with (out/'flow.log').open('w') as log:
        result=subprocess.run(command,cwd=out,stdout=log,stderr=subprocess.STDOUT)
    runs=out/'runs'/tag;metrics=runs/'final/metrics.json'
    data=json.loads(metrics.read_text()) if metrics.exists() else {}
    # Reuse the OpenPLL zero-violation and required-view policy for a macro top.
    check=subprocess.run([sys.executable,str(ROOT/'thirdparties/OpenPLL/scripts/check_librelane_signoff.py'),
        '--final-dir',str(runs/'final'),'--design-name',design,
        # The checker resolves sources against the OpenPLL checkout.
        '--source-file','../../examples/openlvds_io_ref_top.v','--source-file','../../constraints/io_ref_top.sdc'],
        cwd=ROOT,capture_output=True,text=True)
    failures=[line for line in (check.stdout+check.stderr).splitlines() if line.strip()] if check.returncode else []
    unchanged=all(path.read_bytes()==data_ for path,data_ in captured.items())
    summary=dict(passed=result.returncode==0 and check.returncode==0 and unchanged,returncode=result.returncode,
        run=str(runs.relative_to(ROOT)),metrics=data,source_sha256=stamp,inputs_unchanged=unchanged,
        views_sha256=digest(release/'views.json'),signoff_failures=failures,
        scope='Integration proof of the published views at a relaxed 100 MHz clock; not a link-rate result')
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('io-ref','PASS' if summary['passed'] else 'FAIL',str(out/'flow.log'),flush=True)
    for line in failures[:20]:print('  ',line)
    lock.close()
    return 0 if summary['passed'] else 1

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--design',choices=['tx','rx','pfd','both','io-ref'],default='both')
    p.add_argument('--tag',default='lab')
    p.add_argument('--pfd-source',type=Path,help='Isolated PFD candidate source')
    p.add_argument('--artifact-dir',type=Path,help='Isolated physical output directory; never changes active evidence')
    p.add_argument('--pfd-policy',choices=['legacy','pulse-area'],default='legacy')
    p.add_argument('--tx-core-source',type=Path)
    p.add_argument('--tx-ddr-source',type=Path)
    p.add_argument('--tx-buffer-strength',type=int,choices=[4,8])
    a=p.parse_args()
    if a.design=='io-ref':return harden_io_ref(a.tag)
    if (a.pfd_source or a.pfd_policy!='legacy') and a.design!='pfd':p.error('PFD candidate options require --design pfd')
    if (a.tx_core_source or a.tx_ddr_source or a.tx_buffer_strength) and a.design!='tx':p.error('TX candidate options require --design tx')
    if (a.tx_core_source or a.tx_ddr_source or a.tx_buffer_strength) and not (a.tx_core_source and a.tx_ddr_source and a.tx_buffer_strength and a.artifact_dir):p.error('Provide both TX sources, buffer strength, and artifact directory')
    if a.artifact_dir and a.design not in ['pfd','tx']:p.error('Isolated output requires a single PFD or TX design')
    if a.pfd_source and not a.artifact_dir:p.error('Candidate source requires --artifact-dir')
    if a.artifact_dir and not a.artifact_dir.resolve().is_relative_to(ROOT):p.error('Artifacts must reside in OpenLVDS')
    results={}
    for which in ['tx','rx'] if a.design=='both' else [a.design]:
        design={'tx':'openlvds_tx_core','rx':'openlvds_ddr_rx','pfd':'lvds_pfd'}[which]
        out=a.artifact_dir.resolve() if a.artifact_dir else ROOT/'build/physical'/which; out.mkdir(parents=True,exist_ok=True)
        lock=(out/'.run.lock').open('a')
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError(which+': physical flow is already running')
        previous=out/'summary.json'
        if previous.exists():
            old=json.loads(previous.read_text());history=out/'history'/old.get('source_sha256','unknown')[:16];history.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(previous,history/'summary.json')
            if (out/'flow.log').exists():shutil.copyfile(out/'flow.log',history/'flow.log')
        sources=[ROOT/'rtl/openlvds_reset.v', ROOT/f'rtl/{design}.v']
        if which=='tx':
            if a.tx_core_source:sources[1]=a.tx_core_source.resolve()
            sources.append(a.tx_ddr_source.resolve() if a.tx_ddr_source else ROOT/'rtl/openlvds_ddr_tx.v')
        config=dict(DESIGN_NAME=design,VERILOG_FILES=list(map(str,sources)),
            CLOCK_PORT='clk_400' if which=='tx' else 'clk',CLOCK_PERIOD=2.380952,
            PNR_SDC_FILE=str(ROOT/f'constraints/{which}.sdc'),
            SIGNOFF_SDC_FILE=str(ROOT/f'constraints/{which}.sdc'),
            FP_SIZING='absolute',DIE_AREA=[0,0,100,100],FP_CORE_UTIL=20,
            PL_TARGET_DENSITY_PCT=35,MAX_FANOUT_CONSTRAINT=4,
            VDD_NETS=['VPWR'],GND_NETS=['VGND'],
            RUN_POST_GRT_DESIGN_REPAIR=True,
            SYNTH_STRATEGY='DELAY 0',meta=dict(flow='Classic'))
        tt=str(Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib')
        config['LIB']={'nom_':[tt], '*_tt_025C_1v80':[tt]}
        config['STA_CORNERS']=['nom_tt_025C_1v80','min_tt_025C_1v80','max_tt_025C_1v80']
        config['PAD_LIBS']=None
        # Ordinary fillers maintain well/rail continuity without populating a
        # small lab macro with hundreds of unrequested MOS decap cells.
        config['DECAP_CELLS']=[]
        # OpenROAD can otherwise select intentional clock-delay cells as
        # general port buffers, distorting PFD pulses and DDR launch timing.
        config['EXTRA_EXCLUDED_CELLS']=['sky130_fd_sc_hd__clkdlybuf*']
        if which=='tx':
            if a.tx_buffer_strength:config['DESIGN_REPAIR_BUFFER_OUTPUT_PORTS']=False
            # Each small launch domain has only local clock loads. The DLL
            # drives these directly, avoiding an unnecessary two-level tree.
            config['RUN_CTS']=False
            config['RUN_POST_CTS_RESIZER_TIMING']=False
            config['RUN_POST_GRT_RESIZER_TIMING']=True
            config['DESIGN_REPAIR_BUFFER_INPUT_PORTS']=False
            config['VERILOG_DEFINES']=['OPENLVDS_SKY130_TX']
            config['EXTRA_VERILOG_MODELS']=[str(ROOT/'sky130/tx_blackboxes.v')]
        if which=='rx':
            # Six local clock loads are driven directly by the analog clock
            # receiver. Avoid an unnecessary two-level tree and its sampling skew.
            config['RUN_CTS']=False
            config['RUN_POST_CTS_RESIZER_TIMING']=False
            config['DESIGN_REPAIR_BUFFER_INPUT_PORTS']=False
            config['VERILOG_DEFINES']=['OPENLVDS_SKY130_RX']
            config['EXTRA_VERILOG_MODELS']=[str(ROOT/'sky130/rx_blackboxes.v')]
        if which=='pfd':
            sources=[a.pfd_source.resolve() if a.pfd_source else ROOT/'sky130/lvds_pfd.v']
            config.update(VERILOG_FILES=list(map(str,sources)),
                VERILOG_DEFINES=['USE_POWER_PINS'],CLOCK_PORT=None,
                SYNTH_ELABORATE_ONLY=True,SYNTH_HIERARCHY_MODE='flatten',
                EXTRA_VERILOG_MODELS=[str(ROOT/'thirdparties/OpenPLL/sky130/sky130_fd_sc_hd_pll_blackbox.v'),
                                      str(ROOT/'sky130/pfd_blackboxes.v')],
                RUN_CTS=False,RUN_POST_CTS_RESIZER_TIMING=False,
                DESIGN_REPAIR_BUFFER_INPUT_PORTS=False,
                DESIGN_REPAIR_BUFFER_OUTPUT_PORTS=False,
                RUN_POST_GRT_DESIGN_REPAIR=False,
                RUN_POST_GRT_RESIZER_TIMING=False,
                RUN_MCSTA=False,RUN_EQY=False,
                LINTER_DISABLE_WARNINGS_BLACKBOX=['UNDRIVEN','UNUSEDSIGNAL','PINMISSING','TIMESCALEMOD'])
        cfg=out/'config.json'; cfg.write_text(json.dumps(config,indent=2)+'\n')
        inputs=sources+([ROOT/'sky130/tx_blackboxes.v'] if which=='tx' else [ROOT/'sky130/pfd_blackboxes.v'] if which=='pfd' else [])+[ROOT/f'constraints/{which}.sdc',cfg]
        captured={path:path.read_bytes() for path in inputs}
        stamp=hashlib.sha256(b''.join(captured.values())).hexdigest()
        archive=out/'inputs'/stamp[:16];archive.mkdir(parents=True,exist_ok=True)
        for path,data in captured.items():(archive/path.name).write_bytes(data)
        tag=a.tag+'-'+stamp[:12]
        command=['python3','-m','librelane','--manual-pdk','--pdk-root',os.environ['PDK_ROOT'],
                 '-p','sky130A','-s','sky130_fd_sc_hd','--condensed','--hide-progress-bar',
                 '--run-tag',tag,str(cfg)]
        with (out/'flow.log').open('w') as log:
            result=subprocess.run(command,cwd=out,stdout=log,stderr=subprocess.STDOUT)
        runs=out/'runs'/tag
        metrics=runs/'final/metrics.json'
        data=json.loads(metrics.read_text()) if metrics.exists() else {}
        unchanged=all(path.read_bytes()==data for path,data in captured.items())
        netlist=runs/'final/nl'/f'{design}.nl.v'
        text=netlist.read_text() if netlist.exists() else ''
        no_delay=bool(text) and delay_cells_absent(text)
        if which=='pfd':interface=pfd_area_paths_retained(text) if a.pfd_policy=='pulse-area' else pfd_paths_retained(text)
        elif which=='tx':interface=tx_buffered_paths_retained(text,a.tx_buffer_strength) if a.tx_buffer_strength else tx_cells_retained(text)
        else:interface=True
        results[which]=dict(passed=result.returncode==0 and unchanged and no_delay and interface,returncode=result.returncode,
            run=str(runs.relative_to(ROOT)),metrics=data,
            source_sha256=stamp,inputs_unchanged=unchanged,
            delay_cells_absent=no_delay,interface_verified=interface,
            input_archive=str(archive.relative_to(ROOT)),pfd_policy=a.pfd_policy if which=='pfd' else None,tx_buffer_strength=a.tx_buffer_strength if which=='tx' else None)
        if not unchanged:results[which]['error']='Inputs changed during the physical flow; regenerate'
        (out/'summary.json').write_text(json.dumps(results[which],indent=2)+'\n')
        print(which,'PASS' if results[which]['passed'] else 'FAIL',str(out/'flow.log'),flush=True)
        lock.close()
    return 0 if all(x['passed'] for x in results.values()) else 1

if __name__=='__main__': sys.exit(main())
