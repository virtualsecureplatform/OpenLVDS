# SPDX-License-Identifier: GPL-3.0-only
"""Replay native clock/BAD edges through the actual RTL readiness controller."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import numpy as np
from dll_measurements import edges,column,loop

ROOT=Path(__file__).resolve().parents[1]


def backend():
    paths=[shutil.which(tool) for tool in ['iverilog','vvp']]
    if not all(paths):raise ValueError('Icarus and vvp are required; use scripts/env.sh')
    return {name:hashlib.sha256(Path(path).read_bytes()).hexdigest() for name,path in zip(['iverilog','vvp'],paths)}


def input_events(wave,header,recovery=False):
    """1 fs event resolution; retain short BAD pulses between reference edges."""
    t=wave[:,1];timeline={0:{'clk':0,'bad':int(column(wave,header,'BAD')[0]>=.9),'ready':0,'reset':0}}
    def add(at,signal,value):timeline.setdefault(int(round(at/1e-15)),{})[signal]=value
    for signal,node in [('clk','CLK'),('bad','BAD')]:
        values=column(wave,header,node)
        for rising in [True,False]:
            for at in edges(t,values,rising=rising):add(at,signal,int(rising))
    rises=edges(t,column(wave,header,'CLK'))
    if len(rises)<2:raise ValueError('Native replay lacks a reference clock')
    add(2.02e-9,'reset',1)
    # Ready arrives just after the first reference edge. The 32nd admitted
    # clock enables the PFD at 85 ns; the native fixture includes 200 ps transport.
    add(rises[0]+.1e-9,'ready',1)
    if recovery:
        add(2210e-9,'ready',0);add(2300.1e-9,'ready',1)
    state=dict(clk=0,bad=0,ready=0,reset=0);events=[];previous=0
    for at,changes in sorted(timeline.items()):
        state.update(changes)
        bits=''.join(str(state[name]) for name in ['reset','ready','bad','clk'])
        events.append((at-previous,bits));previous=at
    return events


def clocked_health(wave,header,times):
    t=wave[:,1];reference=edges(t,column(wave,header,'CLK'))
    nodes={name:edges(t,column(wave,header,name)) for name in ['PH0','PH90','PD_REF','PH180']}
    feedback=[];quarter=[];bad=[];healthy=True
    for at in times:
        prior=reference[reference<at-1e-15]
        if len(prior)<8:healthy=False;continue
        period=float(np.median(np.diff(prior[-8:])))
        before={name:value[value<=at] for name,value in nodes.items()}
        if any(len(value)<2 or at-value[-1]>1.5*period or value[-1]-value[-2]>1.5*period for value in before.values()):
            healthy=False;continue
        q=before['PH90'][-1];p=before['PH0'][before['PH0']<q]
        if not len(p):healthy=False;continue
        quarter.append(abs((q-p[-1])-period/4)*1e12)
        pd=before['PD_REF'][-1];feedback.append(float(np.min(abs(nodes['PH180']-pd)))*1e12)
        bad.append(float(np.interp(at,t,column(wave,header,'BAD'))))
    return dict(passed=bool(healthy and feedback and quarter and max(feedback)<100 and max(quarter)<100 and max(bad)<.36),
        feedback_error_max_ps=max(feedback) if feedback else None,
        quarter_phase_error_max_ps=max(quarter) if quarter else None,phase_bad_max_v=max(bad) if bad else None)


def replay(wave,header,out,recovery=False):
    out=out.resolve()
    out.mkdir(parents=True,exist_ok=True)
    (out/'stimulus.txt').write_text(''.join(f'{dt} {bits}\n' for dt,bits in input_events(wave,header,recovery)))
    bench='''`timescale 1fs/1fs
module native_readiness;
  reg clk=0, phase_bad=0, reset_n=1, clock_ready=1;
  wire pd_enable,locked;
  integer fd,rc;
  reg [3:0] bits;
  longint unsigned dt;
  openlvds_dll_control dut(clk,reset_n,clock_ready,phase_bad,pd_enable,locked);
  always @(posedge clk or negedge reset_n or negedge clock_ready) begin
    #1;
    $display("ROW %.0f %b %b %b %b %b",$realtime,clk,reset_n,clock_ready,pd_enable,locked);
  end
  initial begin
    // Establish the reset expression, then explicitly assert it at startup.
    #1;
    fd=$fopen("stimulus.txt","r");
    if (!fd) $fatal(1,"Missing native replay stimulus");
    while (!$feof(fd)) begin
      rc=$fscanf(fd,"%d %b",dt,bits);
      if (rc==2) begin #(dt); {reset_n,clock_ready,phase_bad,clk}=bits; end
      else if (!$feof(fd)) $fatal(1,"Invalid native replay stimulus");
    end
    #100; $finish;
  end
endmodule
'''
    (out/'bench.v').write_text(bench);backend()
    compile=subprocess.run(['iverilog','-g2012','-s','native_readiness','-o',str(out/'replay.vvp'),
        str(ROOT/'rtl/openlvds_dll_control.v'),str(out/'bench.v')],capture_output=True,text=True)
    (out/'compile.log').write_text(compile.stdout+compile.stderr);compile.check_returncode()
    run=subprocess.run(['vvp',str(out/'replay.vvp')],cwd=out,capture_output=True,text=True)
    (out/'replay.log').write_text(run.stdout+run.stderr);run.check_returncode()
    return analyze(wave,header,run.stdout,recovery)


def analyze(wave,header,log,recovery=False):
    rows=[line.split()[1:] for line in log.splitlines() if line.startswith('ROW ')]
    if not rows or any(any(bit not in ['0','1'] for bit in row[1:]) for row in rows):
        raise ValueError('Undefined RTL output during native readiness replay')
    data=np.array([[float(row[0])*1e-15,*map(int,row[1:])] for row in rows])
    # Columns: time, clock, reset, ready, detector enable, lock.
    valid=(data[:,1]==1)&(data[:,2]==1)&(data[:,3]==1)
    locked=(data[:,5]==1)&valid
    assertions=np.flatnonzero((data[:,5]==1)&np.r_[True,data[:-1,5]==0])
    qualification=[]
    for index in assertions:
        at=data[index,0];prior=edges(wave[:,1],column(wave,header,'CLK'));prior=prior[prior<at]
        mhz=1e-6/float(np.median(np.diff(prior[-8:])))
        measured=loop(wave,header,mhz,'averaged_pfd_ota',at*1e9-100,at*1e9)
        keep=(wave[:,1]>=at-100e-9)&(wave[:,1]<=at)
        plates=[column(wave,header,name[2:-1])[keep] for name in header
                if name=='V(CTRL)' or name.startswith('V(CTRL_CAP_')]
        storage=bool(plates and all(len(v)>1 and np.min(v)>=0 and np.max(v)<=1.95 and np.ptp(v)<.02 for v in plates))
        qualification.append(dict(at_ns=at*1e9,passed=bool(measured['passed'] and storage),metrics=measured,all_storage_plates_passed=storage))
    health=clocked_health(wave,header,data[locked,0])
    reset_clear=bool(np.all(data[(data[:,2]==0)|(data[:,3]==0),5]==0))
    enabled=data[(data[:,4]==1)&np.r_[True,data[:-1,4]==0],0]
    expected=np.array([85e-9,2380e-9] if recovery else [85e-9])
    enable_error=float(np.max(abs(enabled-expected))*1e12) if len(enabled)==len(expected) else None
    recovered=True
    if recovery:
        recovered=bool(any(q['at_ns']<2200 for q in qualification) and any(q['at_ns']>2300 for q in qualification) and
            np.any((data[:,0]>=2210e-9)&(data[:,0]<2300e-9)&(data[:,5]==0)))
    return dict(passed=bool(qualification and all(q['passed'] for q in qualification) and health['passed'] and
        reset_clear and recovered and enable_error is not None and enable_error<1),
        assertions=qualification,locked_clock_samples=int(np.sum(locked)),clocked_health=health,
        readiness_reset_clears_lock=reset_clear,clock_loss_requalified=recovered,detector_enable_edge_error_ps=enable_error,
        scope='Actual RTL replay of native clock/BAD; fixed 200 ps detector-enable transport partition, no metastability claim')
