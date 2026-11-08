# SPDX-License-Identifier: GPL-3.0-only
"""Require replayed fresh range failure before the one-factor P80/MIM4 trial."""
import hashlib,json
from pathlib import Path
import native_bank_300_v1 as baseline
import native_bank_300_v2 as single
ROOT=baseline.ROOT
BASE=ROOT/'build/diagnostics/native_bank_300_v1/b3f726547e6143f8'
SINGLE=ROOT/'build/diagnostics/native_bank_300_v2/2d31edbabe113146'


def receipt(path,parent,numbers):
    m=json.loads((path/'manifest.json').read_text());i=m['identity'];r=json.loads((path/'summary.json').read_text())
    if (path.parent!=ROOT/'build/diagnostics/bank_native_replay_300'
            or path.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['version']!='independent-fresh-bank-native-metrology-300-v1'
            or i['parent']!=str(parent.relative_to(ROOT)) or i['cases']!=numbers
            or json.loads((path/'state.json').read_text())!=dict(status='complete',cases=len(numbers),qualified_phy=False)
            or r['all_selected_native_metrics_reproduced'] is not True or r['parameters_changed'] is not False
            or r['whole_bank_admitted'] is not False or r['qualified_phy'] is not False
            or len(r['rows'])!=len(numbers)):
        raise ValueError('Require exact completed independent native receipt')
    for n,row in zip(numbers,r['rows']):
        if (row['case']!=str((parent/n).relative_to(ROOT)) or row['task']['id']!=n
                or any(row.get(k) is not True for k in ('all_original_metrics_reproduced',
                    'independent_timing_reproduced','independent_terminal_envelope_reproduced',
                    'independent_control_and_gate_settling_reproduced'))):
            raise ValueError('Independent native metrics or case coverage changed')
        required={str((parent/n/f).relative_to(ROOT)) for f in ('bench.raw','bench.cir','summary.json')}
        if not required<=i['inputs'].keys():raise ValueError('Independent native case is not fully bound')
    paths=[path/n for n in ('manifest.json','summary.json','state.json')]
    return {**i['inputs'],**{str(p.relative_to(ROOT)):baseline.sha(p) for p in paths}}


def decision(zero,fine60,fine40,coarse,failed_pair):
    if (zero['zero_code_quarter_passed'] is not True or zero['current_clock_interface_screen_passed'] is not True
            or any(r['current_clock_interface_screen_passed'] is not True for r in (fine60,fine40,coarse))):
        raise ValueError('Require passing restored-bank timing points before range-only repair')
    overlap={e:min(v for r in (fine60,fine40) for v in r['edge_delays_ps'][e])-max(coarse['edge_delays_ps'][e]) for e in ('rise','fall')}
    if any(v>=0 for v in overlap.values()):raise ValueError('Require both observed restored-bank overlap failures')
    if len(failed_pair)!=2 or any(r['repeated_delay_screen_passed'] is not False
            or r['period_screen_passed'] is not False or r['current_clock_interface_screen_passed'] is not False
            or r['repeated_delay_span_ps']['rise']<=20 or r['maximum_period_error_ps']<=20 for r in failed_pair):
        raise ValueError('Require both original/centered single-driver history and period failures')
    return dict(selected_variant='p80_c4',conservative_baseline_overlap_ps=overlap,
                single_driver_rising_history_ps=[r['repeated_delay_span_ps']['rise'] for r in failed_pair],
                reason='Keep passing strong driver; change only the nonlinear fine capacitance to four qualified switched-MIM cells per enable',
                qualified_phy=False)


def require(proofs,full=True):
    if len(proofs)!=3:raise ValueError('Supply zero, range and single-driver replay receipts in order')
    inputs={}
    for path,parent,numbers in zip(proofs,(BASE,BASE,SINGLE),(['2'],['1','3','4'],['1'])):
        for name,digest in receipt(path,parent,numbers).items():
            if name in inputs and inputs[name]!=digest:raise ValueError('Conflicting independent evidence')
            inputs[name]=digest
    for name,digest in inputs.items():
        if (full or Path(name).suffix!='.raw') and baseline.sha(ROOT/name)!=digest:
            raise ValueError('Independent evidence changed: '+name)
    rows={k:json.loads((BASE/str(k)/'summary.json').read_text())['result'] for k in (1,2,3,4)}
    pair=[]
    for n in ('0','1'):
        folder=SINGLE/n;stored=json.loads((folder/'summary.json').read_text())
        if stored['error'] is not None:raise ValueError('Single-driver failure is not a completed native result')
        for name,digest in stored['files'].items():
            key=str((folder/name).relative_to(ROOT));inputs[key]=digest
            if (full or Path(name).suffix!='.raw') and baseline.sha(folder/name)!=digest:
                raise ValueError('Original single-driver evidence changed')
        inputs[str((folder/'summary.json').relative_to(ROOT))]=baseline.sha(folder/'summary.json');pair.append(stored['result'])
    return decision(rows[2],rows[1],rows[3],rows[4],pair),inputs
