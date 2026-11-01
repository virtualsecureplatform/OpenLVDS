#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run an immutable exact-RC selected-PHY bring-up fixture; no release admission."""
import argparse,copy,fcntl,hashlib,json,os,re,subprocess,sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from simulate_link import REQ,REQ_BYTES,word_stream,parallel_stimulus,instance,pwl,analyze
import simulate_link as original
import selected_phy
from selected_phy_phase import phase
from spice_engine import command as spice_command,engine,provenance
from rx_aperture_evidence import load as load_rx_aperture
from rx_candidate_aperture import lease
from receiver_static_diagnosis import capture_manifest
from dll_campaign import atomic
from spice_probes import ProbeNetwork
ROOT=Path(__file__).resolve().parents[1]
CODE=['simulate_selected_link.py','simulate_link.py','selected_phy.py','selected_phy_phase.py',
      'spice_engine.py','run_ngspice.py','rx_aperture_evidence.py','dll_case.py',
      'dll_measurements.py','spice_slots.py','rx_candidate_aperture.py','spice_probes.py','dll_campaign.py',
      'receiver_static_diagnosis.py']


def clocks(a,total):
    arguments=copy.copy(a);arguments.dll_phase=False
    c0,c90,rises,period,scope=original.clocks(arguments,total)
    if not a.dll_phase:return c0,c90,rises,period,scope
    duty=a.duty
    if a.clock_source!='ideal':
        trace=ROOT/'build/openpll'/('clock.csv' if a.clock_source=='openpll-rtl' else 'physical_clock.csv')
        duty=original.trace_duty(trace)
    evidence=phase(a.bundle,a.process,a.temperature,a.mhz,duty)
    mean=(evidence['quarter_phase_min_ps']+evidence['quarter_phase_max_ps'])/2000*(period/(1000/a.mhz))
    delta=mean-period/4
    c90=[c90[0]]+[(at+delta,v) for at,v in c90[1:]]
    evidence['replay_period_scale']=period/(1000/a.mhz)
    a.phase_evidence=evidence
    scope+='; selected full-RC DLL phase SHA256 '+evidence['evidence_sha256']
    return c0,c90,rises,period,scope


def store(path,data):
    if path.exists() and path.read_bytes()!=data:raise ValueError('Captured selected-link file changed: '+path.name)
    if not path.exists():path.write_bytes(data)


def existing(out):
    if (out/'summary.json').exists():
        cached=json.loads((out/'summary.json').read_text())
        if selected_phy.digest(out/'bench.cir.prn')!=cached['waveform_sha256']:raise ValueError('Selected link waveform changed')
        return cached
    if any((out/n).exists() for n in ['bench.raw','bench.cir.prn','ngspice.log','xyce.log']):
        raise ValueError('Incomplete selected link retained; use a fresh context')
    return None


def budget(summary,phase_evidence):
    # Mean phase replay must not consume the measured phase range for free.
    uncertainty=(phase_evidence.get('quarter_phase_max_ps',0)-phase_evidence.get('quarter_phase_min_ps',0))*phase_evidence.get('replay_period_scale',1)
    for name in ['setup_margin_ps','hold_margin_ps']:
        raw=summary.get(name);summary['raw_'+name]=raw
        if raw is not None:summary[name]=raw-uncertainty
    summary['phase_uncertainty_budget_ps']=uncertainty
    return summary


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--bits',type=int,default=4096)
    p.add_argument('--process',choices=REQ['process_corners'],default='tt')
    p.add_argument('--temperature',type=int,choices=REQ['temperatures_c'],default=25)
    p.add_argument('--mhz',type=float,choices=REQ['clock_test_mhz'],default=400)
    p.add_argument('--duty',type=float,choices=REQ['clock_duty'],default=.5)
    p.add_argument('--skew-ps',type=float,default=0)
    p.add_argument('--eye-shift-ps',type=float,default=0)
    p.add_argument('--jitter-pp-ps',type=float,default=100)
    p.add_argument('--clock-source',choices=['ideal','openpll-rtl','openpll-physical'],default='ideal')
    p.add_argument('--fast-rc',action='store_true')
    p.add_argument('--bundle',required=True,help='Use an isolated staged PHY instead of active extraction pointers')
    p.add_argument('--diagnostic',action='store_true',required=True,help='Permit an unqualified approximation for bring-up; cannot release')
    p.add_argument('--aperture-table',help='Completed full-RC capture table; otherwise discover the latest current table')
    p.add_argument('--dll-phase',action='store_true')
    p.add_argument('--settled-start',action='store_true',help='Begin from solved fixed-supply DC bias; startup acquisition is checked separately')
    p.add_argument('--training-ns',type=float,help='Training before payload (default 256 cycles with settled-start, otherwise at least 800 ns)')
    p.add_argument('--prepare-only',action='store_true')
    p.add_argument('--wait-slot',type=int,choices=range(6))
    a=p.parse_args()
    if a.fast_rc:p.error('Selected link requires exact RC; no approximate view is certified')
    if a.clock_source!='ideal' and (a.mhz!=400 or a.duty!=.5):
        p.error('OpenPLL captures are the configured 400 MHz mode; duty comes from the recorded trace')
    if a.bits<32 or a.bits%2:p.error('Even bit count >= 32 required')
    source_path=Path(a.bundle)/'full.spice' if a.bundle else ROOT/'analog/openlvds.spice'
    source_bytes=source_path.read_bytes()
    runner_bytes=Path(__file__).read_bytes()
    simulator_stamp=provenance()
    if a.bundle:
        lib,inputs,models=selected_phy.load(a.bundle,a.fast_rc)
        a.bundle=str(Path(a.bundle).resolve().relative_to(ROOT))
    if source_path.read_bytes()!=source_bytes:p.error('Analog source changed while assembling the circuit')
    rx_model=models['openlvds_ddr_rx']
    try:
        aperture=load_rx_aperture(rx_model.get('exact_sha256',rx_model['netlist_sha256']),a.process,a.temperature,a.aperture_table)
    except (OSError,ValueError,KeyError,TypeError) as error:
        if not a.diagnostic or a.aperture_table:p.error(str(error))
        aperture=dict(qualified=False,setup_ps=200,hold_ps=80,qualification='legacy diagnostic estimate')
    code={n:selected_phy.digest(ROOT/'scripts'/n) for n in CODE}
    config=dict({k:v for k,v in vars(a).items() if k not in ['prepare_only','wait_slot']},simulator=engine(),rx_aperture=aperture,producer_code=code)
    if a.bundle:config['bundle_manifest_sha256']=hashlib.sha256((Path(a.bundle)/'manifest.json').read_bytes()).hexdigest()
    nominal_period=1000/a.mhz
    minimum_training=256*nominal_period
    training=a.training_ns if a.training_ns is not None else minimum_training if a.settled_start else max(800,minimum_training)
    if training<50:p.error('At least 50 ns training is required')
    if training<minimum_training:p.error('Selected PHY fixtures require at least 256 clock cycles of training')
    total=training+50+(a.bits/2+16)*nominal_period
    c0,c90,rises,period,scope=clocks(a,total)
    if a.training_ns is None:
        actual_training=256*period if a.settled_start else max(800,256*period)
        if actual_training!=training:
            training=actual_training
            total=training+50+(a.bits/2+16)*period
            c0,c90,rises,period,scope=clocks(a,total)
    if training<256*period:p.error('Selected PHY fixtures require 256 cycles at the actual clock frequency')
    config['phase_evidence']=getattr(a,'phase_evidence',{})
    clock_bytes=(pwl(c0)+pwl(c90)).encode()
    fingerprint=hashlib.sha256(lib+REQ_BYTES+json.dumps(config,sort_keys=True).encode()+runner_bytes+simulator_stamp.encode()+clock_bytes+scope.encode()).hexdigest()
    name=f'{a.process}_{a.temperature}_{a.mhz:g}m_d{a.duty:g}_s{a.skew_ps:g}_e{a.eye_shift_ps:g}_{a.clock_source}_{a.bits}'
    out=ROOT/'build/diagnostics/selected_link'/name/fingerprint[:12];out.mkdir(parents=True,exist_ok=True)
    lock=(out/'.run.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:p.error('This exact link case is already running')
    cached=existing(out)
    store(out/'runner.py',runner_bytes)
    store(out/'requirements.json',REQ_BYTES)
    store(out/'analog_source.spice',source_bytes)
    store(out/'library.spice',lib)
    capture_manifest(out/'rx_aperture.json',aperture)
    eligible=np.where(rises>=training)[0]
    if len(eligible)<a.bits/2+10:p.error('Clock waveform is too short')
    launch=rises[eligible[0]:eligible[0]+a.bits//2]
    words=word_stream(len(launch))
    data0,data1=parallel_stimulus(launch,words,rises[eligible[0]-1])
    txnodes={'VGND':'0','VPWR':'VDDD','clk_400':'CLK0','clk_90':'CLK90',
        'clock_ready':'VDDD','dll_locked':'VDDD','enable':'VDDD','reset_n':'RESET_N',
        'tx_data[0]':'D0','tx_data[1]':'D1','tx_ready':'TXREADY','tx_serial':'TXDATA','forwarded_clock':'TXCLOCK'}
    rxnodes={'VGND':'0','VPWR':'VDDD','clk':'RXCLOCK','reset_n':'RESET_N','serial':'RXDATA',
             'data[0]':'Q0','data[1]':'Q1','valid':'RXVALID'}
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    lines=[f'OpenLVDS extracted link {name}',f'.lib "{pdk}" {a.process}',
        f'.include "{out}/library.spice"',f'.options device temp={a.temperature}',
        '.options timeint method=gear reltol=1e-4 abstol=1e-12',
        'VIO VDDIO 0 PWL(0 0 1n 3.3)','VDIG VDDD 0 PWL(0 0 1n 1.8)',
        'VREF VREF 0 PWL(0 0 1n 1.2)','VRST RESET_N 0 PWL(0 0 2n 0 2.1n 1.8)',
        'IREF_TX IREF_TX 0 PWL(0 0 1n 35u)','IREF_RX IREF_RX 0 PWL(0 0 1n 35u)',
        'VCLK0 CLK0 0 '+pwl(c0),'VCLK90 CLK90 0 '+pwl(c90),
        'VD0 D0 0 '+pwl(data0),'VD1 D1 0 '+pwl(data1),
        instance('TX','openlvds_tx_core',txnodes,models),
        'XBT IREF_TX NBT VDDIO 0 lvds_bias','XBR IREF_RX NBR VDDIO 0 lvds_bias',
        'XDT TXDATA TP TN VREF IREF_TX NBT VDDIO VDDD 0 openlvds_driver_core',
        'XCT TXCLOCK CP CN VREF IREF_TX NBT VDDIO VDDD 0 openlvds_driver_core',
        'XDR RP RN RXDATA VREF IREF_RX NBR VDDIO VDDD 0 openlvds_receiver_core',
        'XCR RCP RCN RXCLOCK VREF IREF_RX NBR VDDIO VDDD 0 openlvds_receiver_core',
        instance('RX','openlvds_ddr_rx',rxnodes,models),'CQ0 Q0 0 20f','CQ1 Q1 0 20f']
    if a.settled_start:
        replacements={
            'VIO VDDIO 0 PWL(0 0 1n 3.3)':'VIO VDDIO 0 3.3',
            'VDIG VDDD 0 PWL(0 0 1n 1.8)':'VDIG VDDD 0 1.8',
            'VREF VREF 0 PWL(0 0 1n 1.2)':'VREF VREF 0 1.2',
            'IREF_TX IREF_TX 0 PWL(0 0 1n 35u)':'IREF_TX IREF_TX 0 35u',
            'IREF_RX IREF_RX 0 PWL(0 0 1n 35u)':'IREF_RX IREF_RX 0 35u'}
        lines=[replacements.get(line,line) for line in lines]
        # Guesses help Newton find the closed-loop DC solution. NODESET does
        # not clamp any node during the transient; these are not ideal biases.
        guesses={'IREF_TX':1.35,'IREF_RX':1.35,'NBT':1.35,'NBR':1.35,
                 'RXDATA':0,'RXCLOCK':0,'TP':1.075,'TN':1.425,'CP':1.075,'CN':1.425,
                 'RP':1.075,'RN':1.425,'RCP':1.075,'RCN':1.425}
        for inst in ['XDT','XCT']:
            for node,value in [('SINK',1.36),('TOP',2.42),('DP',0),('DN',3.3)]:
                guesses[inst+':openlvds_driver_core__'+node]=value
        lines.extend('.nodeset V('+n+')='+str(v) for n,v in guesses.items())
    for tag,pins,delay in [('D',('TP','TN','RP','RN'),1.2+a.skew_ps/1000),
                           ('C',('CP','CN','RCP','RCN'),1.2+a.eye_shift_ps/1000)]:
        if delay<=0:p.error('Channel propagation delay must remain positive')
        for leg,(tx,rx) in enumerate(zip(pins[:2],pins[2:])):
            base=f'{tag}{leg}'
            lines.extend([f'CP{base} {tx} 0 2p',f'LT{base} {tx} {base}A 1n',
                f'RT{base} {base}A {base}B 1',f'T{base} {base}B 0 {base}F 0 Z0=50 TD={delay:g}n',
                f'LR{base} {base}F {rx} 1n',f'CR{base} {rx} 0 2p'])
        lines.append(f'RTERM{tag} {tag}0F {tag}1F 100')
    lines.extend([f'.tran 20p {total:g}n 0 20p',
        '.print tran V(RP) V(RN) V(RCP) V(RCN) V(RXDATA) V(RXCLOCK) V(Q0) V(Q1) V(RXVALID) V(TXREADY) V(TP) V(TN) V(CP) V(CN) V(TXDATA) V(TXCLOCK) V(CLK0) V(CLK90)',
        '.end'])
    deck=out/'bench.cir';expected='\n'.join(lines)+'\n'
    if deck.exists() and deck.read_text()!=expected:raise ValueError('Selected link fixture changed')
    if not deck.exists():deck.write_text(expected)
    ProbeNetwork(lib.decode()).validate(expected,re.findall(r'V\(([^)]+)\)',lines[-2],re.I))
    physical=json.loads((Path(a.bundle)/'manifest.json').read_text())['identity']['selection']['physical_reports']
    captured=dict(config=config,fingerprint=fingerprint,source_sha256=hashlib.sha256(source_bytes).hexdigest(),
        library_sha256=hashlib.sha256(lib).hexdigest(),deck_sha256=selected_phy.digest(deck),physical_reports=physical,
        diagnostic=True,qualified_phy=False)
    capture_manifest(out/'manifest.json',captured)
    def unchanged():
        if (provenance()!=simulator_stamp or source_path.read_bytes()!=source_bytes or
            selected_phy.digest(Path(a.bundle)/'manifest.json')!=config['bundle_manifest_sha256'] or
            any(selected_phy.digest(ROOT/'scripts'/n)!=h for n,h in code.items()) or
            any(selected_phy.digest(ROOT/n)!=h for n,h in physical.items()) or
            (ROOT/'requirements.json').read_bytes()!=REQ_BYTES or selected_phy.digest(deck)!=captured['deck_sha256']):
            raise ValueError('Selected link scientific context changed')
    unchanged()
    if a.prepare_only:
        lock.close();print(json.dumps(dict(output=str(out),prepared=True,qualified_phy=False)),flush=True);return 0
    if cached is None:
        atomic(out/'execution.json',dict(status='waiting_for_slot',qualified_phy=False))
        with lease(a.wait_slot):
            unchanged();atomic(out/'execution.json',dict(status='running',qualified_phy=False))
            result=subprocess.run(spice_command(out/(engine()+'.log'),deck),cwd=out,capture_output=True,text=True)
        (out/'console.log').write_text(result.stdout+result.stderr)
    else:result=SimpleNamespace(returncode=0)
    unchanged()
    rows=[];prn=out/'bench.cir.prn'
    if prn.exists():
        for line in prn.read_text().splitlines():
            try:rows.append(list(map(float,line.split())))
            except ValueError:pass
    wave=np.array(rows)
    if (result.returncode or wave.ndim!=2 or len(wave)<2 or not np.isfinite(wave).all() or
        wave[0,1]>1e-15 or np.any(np.diff(wave[:,1])<=0) or wave[-1,1]<total*1e-9-1e-12):
        summary=dict(passed=False,error=engine()+' failed or transient incomplete',returncode=result.returncode)
    else:
        summary=analyze(wave,words,launch,period,1.2+a.skew_ps/1000,aperture)
        summary=budget(summary,config['phase_evidence'])
        if not a.eye_shift_ps:
            margins=[summary.get('setup_margin_ps'),summary.get('hold_margin_ps')]
            margin_ok=all(m is not None and m>=REQ['minimum_sampling_margin_ps'] for m in margins)
            summary['sampling_margin_passed']=margin_ok
            summary['passed']=summary['passed'] and margin_ok
    summary.update(config=config,rx_aperture=aperture,clock_partition=scope,network='TICER approximate RC' if a.fast_rc else 'full distributed RC',
        actual_clock_mhz=1000/period,injected_external_jitter_pp_ps=a.jitter_pp_ps,
        startup_model='solved DC operating point at fixed supplies' if a.settled_start else 'one-nanosecond supply ramp',
        simulator=engine(),simulator_provenance=simulator_stamp,training_ns=training,
        clock_waveform_sha256=hashlib.sha256(clock_bytes).hexdigest(),
        diagnostic=True,qualified_phy=False,inputs=inputs,fingerprint=fingerprint,
        source_sha256=hashlib.sha256(source_bytes).hexdigest(),
        requirements_sha256=hashlib.sha256(REQ_BYTES).hexdigest(),
        runner_sha256=hashlib.sha256(runner_bytes).hexdigest(),
        library_sha256=hashlib.sha256(lib).hexdigest(),
        deck_sha256=hashlib.sha256(deck.read_bytes()).hexdigest(),
        waveform_sha256=hashlib.sha256(prn.read_bytes()).hexdigest() if prn.exists() else None,
        output=str(out.relative_to(ROOT)))
    unchanged()
    if cached is not None and cached!=summary:raise ValueError('Selected link analysis differs from actual waveform')
    capture_manifest(out/'summary.json',summary)
    atomic(out/'execution.json',dict(status='completed',passed=summary['passed'],qualified_phy=False))
    lock.close()
    print(json.dumps(summary,indent=2))
    return 0 if summary['passed'] else 1

if __name__=='__main__':sys.exit(main())
