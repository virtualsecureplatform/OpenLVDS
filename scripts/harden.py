#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Harden DDR logic; keep physical failures visible in the evidence manifest."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from physical_policy import delay_cells_absent,pfd_paths_retained,tx_cells_retained,pfd_area_paths_retained,tx_buffered_paths_retained

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--design',choices=['tx','rx','pfd','both'],default='both')
    p.add_argument('--tag',default='lab')
    p.add_argument('--pfd-source',type=Path,help='Isolated PFD candidate source')
    p.add_argument('--artifact-dir',type=Path,help='Isolated physical output directory; never changes active evidence')
    p.add_argument('--pfd-policy',choices=['legacy','pulse-area'],default='legacy')
    p.add_argument('--tx-core-source',type=Path)
    p.add_argument('--tx-ddr-source',type=Path)
    p.add_argument('--tx-buffer-strength',type=int,choices=[4,8])
    a=p.parse_args()
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
