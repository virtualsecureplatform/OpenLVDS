#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Export an unadmitted constant native-code ROM from a common-sequence proposal."""
import argparse
import hashlib
import json
from pathlib import Path
import common_delay_sequence_v296 as selector
from clocking_v2 import Delay,common_legal_codes

ROOT=selector.ROOT


def parameters(selection):
    p=selection['policy'];expected=selector.policy(p['mode'],p['coarse_count'],p['fine_count'])
    if p!=expected or selection.get('common_sequence_found') is not True:raise ValueError('Require a common interval-sequence proposal under current policy')
    if any(selection.get(k) is not False for k in ('native_characterization_verified','updates_qualified','legal_code_table_admitted','electrical_qualification_passed','qualified_phy')):
        raise ValueError('Proposal exporter cannot issue or consume native admission claims')
    codes=selection['codes'];native_count=p['coarse_count']*p['fine_count']
    if len(codes)<2 or len(set(codes))!=len(codes) or any(type(c) is not int or not 0<=c<native_count for c in codes):raise ValueError('Invalid or duplicated raw codes')
    curves=selection['selected_curves'];names={f'{corner}/{edge}' for corner in selector.PVT for edge in ('rise','fall')}
    if set(curves)!=names:raise ValueError('Require all thirty selected PVT/edge curves')
    tables={name:[Delay(**d) for d in rows] for name,rows in curves.items()}
    if list(common_legal_codes(tables,20))!=codes:raise ValueError('ROM ordering differs from measured interval ordering')
    for table in tables.values():
        covered=(table[0].hi_ps<=p['quarter_min_ps'] and table[-1].lo_ps>=p['quarter_max_ps'] if p['mode']=='tx'
            else table[-1].lo_ps-table[0].hi_ps>=p['rx_span_ps'])
        if not covered:raise ValueError('Proposed ROM cannot meet the required conservative range')
    width=max(1,(native_count-1).bit_length());index_width=max(1,(len(codes)-1).bit_length())
    packed=sum(code<<(k*width) for k,code in enumerate(codes));bits=len(codes)*width
    return dict(CODE_WIDTH=index_width,RAW_WIDTH=width,CODE_COUNT=len(codes),NATIVE_CODE_COUNT=native_count,TABLE_MODEL_ADMITTED=0,
        COARSE_COUNT=p['coarse_count'],FINE_COUNT=p['fine_count'],
        RAW_CODES=f"{bits}'h{packed:0{(bits+3)//4}x}",packed_integer=packed,codes=codes)


def export(proposal,out):
    body=proposal.read_bytes();selection=json.loads(body);p=parameters(selection)
    paths=[proposal,Path(__file__),Path(selector.__file__),ROOT/'scripts/clocking_v2.py',ROOT/'clocking_v2.json',ROOT/'requirements.json']
    out.mkdir(parents=True,exist_ok=False)
    text='// Unqualified proposal; native characterization and release remain required.\n'
    text+=',\n'.join('.'+name+'('+str(p[name])+')' for name in ('CODE_WIDTH','RAW_WIDTH','CODE_COUNT','NATIVE_CODE_COUNT','TABLE_MODEL_ADMITTED','RAW_CODES'))+'\n'
    (out/'parameters.vh').write_text(text)
    report=dict(parameters={k:v for k,v in p.items() if k!='packed_integer'},policy=selection['policy'],
        inputs={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
        parameters_sha256=hashlib.sha256(text.encode()).hexdigest(),native_characterization_verified=False,
        legal_code_table_admitted=False,qualified_phy=False,
        scope='Static legal-index to native-code proposal only; no native, update, ROM physical or PHY admission')
    if proposal.read_bytes()!=body:raise ValueError('Proposal changed during export; retain partial output')
    (out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('proposal',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();print(export(a.proposal.resolve(),a.output.resolve()))
