#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independent physical-graph reimport and actual JSON/SPICE corruptions."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import export_tg_bank_netlist_v42 as producer
from spice_library import checked_netlist

ROOT=producer.ROOT
sha=producer.sha
VERSION='independent-both2-physical-graph-native-equivalence-v43.1'
CONTEXT='tg_bank_netlist_verification_v43'


def reconstruct(i):
    parent=ROOT/i['parent']
    cells=(parent/'cells_both2.spice').read_text();bank=(parent/'bank_both2.spice').read_text()
    tail_report=json.loads((ROOT/i['tail_evidence']/'summary.json').read_text())
    tail=checked_netlist(tail_report['extraction'])
    g=producer.view.graph(cells,bank,tail);native,counts=producer.view.native_view(cells,bank,tail,g)
    if g!=i['graph'] or counts!=i['native_counts']:raise ValueError('Physical graph/native equivalence cannot regenerate')
    return g,native,counts


def corruptions(data):
    v=producer.view;result=[]
    def add(label,change):
        bad=deepcopy(data);change(bad['modules'][v.NAME]);result.append((label,bad))
    add('dropped_tail_cap',lambda m:m['cells'].pop('u_tail_termination'))
    add('dropped_tail_buffer',lambda m:m['cells'].pop('u_tail_load'))
    add('wrong_tail_attachment',lambda m:m['cells']['u_tail_termination']['connections'].update(A=m['netnames']['tap0']['bits']))
    add('wrong_tg_complement',lambda m:m['cells']['u_switch0_0_0']['connections'].update(ENB=m['cells']['u_switch0_0_0']['connections']['EN']))
    add('wrong_root_tg_input',lambda m:m['cells']['u_switch1_0_0']['connections'].update(A=m['netnames']['tap0']['bits']))
    add('wrong_fine_attachment',lambda m:m['cells']['u_fine_unit15']['connections'].update(A=m['netnames']['tap0']['bits']))
    add('wrong_native_body_tie',lambda m:m['cells']['u_select_buffer0']['connections'].update(VPB=m['netnames']['VGND']['bits']))
    add('shorted_data_driver_ground',lambda m:m['cells']['u_fine_driver']['connections'].update(VGND=m['netnames']['VPWR']['bits']))
    add('lost_preservation',lambda m:m['cells']['u_tail_load']['attributes'].pop('keep'))
    add('merged_select_wires',lambda m:m['netnames']['select1'].update(bits=m['netnames']['select0']['bits']))
    add('parameterized_tail_cell',lambda m:m['cells']['u_tail_termination'].update(parameters=dict(W=3)))
    bad=deepcopy(data);bad['modules'][v.TAIL]['attributes']['blackbox']='0';result.append(('replaced_tail_blackbox',bad))
    bad=deepcopy(data);bad['modules'][v.TG]['ports']['Z']['direction']='input';result.append(('changed_tg_direction',bad))
    return result


def native_corruptions(text):
    v=producer.view;cap=producer.view.cell_definition(text,v.TAIL)
    wrong=cap.replace('w=2','w=3',1)
    if wrong==cap:raise ValueError('Missing native tail geometry for negative control')
    result=[('wrong_native_tail_size',text.replace(cap,wrong,1))]
    model=v.SC+'buf_4';original=v.cell_definition(text,model);lines=original.splitlines();changed=False
    for index,line in enumerate(lines):
        w=line.split()
        if w and w[0].startswith('X') and any('pfet_' in token for token in w):
            if w[4]!='VPB':raise ValueError('Unexpected native standard-cell body terminal')
            w[4]='VNB';lines[index]=' '.join(w);changed=True;break
    if not changed:raise ValueError('Missing native PMOS for body-tie control')
    result.append(('wrong_native_spice_body',text.replace(original,'\n'.join(lines)+'\n',1)))
    return result


def verify(parent):
    i=producer.bound(parent);g,native,counts=reconstruct(i)
    paths=[parent/'manifest.json',parent/'summary.json',*[parent/n for n in json.loads((parent/'summary.json').read_text())['files']]]
    paths += [ROOT/n for n in i['inputs']]+[Path(__file__)]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
                  external_files=i['external_files'],yosys=i['yosys'])
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    if out.exists():bound(out);return out
    out.mkdir(parents=True)
    producer.source.helper.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    for name,text in [('bank.v',producer.view.verilog(g)),('cells.v',producer.view.blackboxes(g)),('bank.sch.spice',native)]:
        if text!=(parent/name).read_text():raise ValueError('Physical source does not regenerate exactly: '+name)
        producer.source.helper.write(out/name,text)
    producer.source.helper.write(out/'check.ys',(parent/'check.ys').read_text())
    p=subprocess.run([i['yosys']['path'],'-s','check.ys'],cwd=out,capture_output=True,text=True)
    producer.source.helper.write(out/'yosys.log',p.stdout+p.stderr);p.check_returncode()
    fresh=json.loads((out/'bank.json').read_text());result=producer.view.verify_json(fresh,g)
    if fresh!=json.loads((parent/'bank.json').read_text()) or result!=json.loads((parent/'summary.json').read_text())['result']:
        raise ValueError('Independent Yosys import differs from the native physical graph')
    controls=[]
    for label,bad in corruptions(fresh):
        path=out/(label+'.json');producer.source.helper.atomic(path,bad)
        try:producer.view.verify_json(bad,g)
        except ValueError as e:controls.append(dict(fault=label,rejected=True,reason=str(e)))
        else:raise ValueError('Physical graph corruption was accepted: '+label)
    reference=producer.view.signature(native,producer.view.NAME);native_controls=[]
    for label,bad in native_corruptions(native):
        producer.source.helper.write(out/(label+'.spice'),bad)
        if producer.view.signature(bad,producer.view.NAME)==reference:raise ValueError('Native primitive corruption was accepted: '+label)
        native_controls.append(dict(fault=label,rejected=True))
    producer.bound(parent)
    if any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Physical graph proof inputs changed')
    report=dict(result=result,native_counts=counts,negative_controls=controls,native_negative_controls=native_controls,
                all_negative_controls_rejected=True,qualified_phy=False,electrical_qualification_passed=False,
                routed_geometry_qualified=False,tail_cell_rc_applied_to_native_reference=False)
    report['files']={p.name:sha(p) for p in out.iterdir() if p.is_file()}
    producer.source.helper.atomic(out/'summary.json',report)
    bound(out);return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity'];r=json.loads((out/'summary.json').read_text())
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
            or any(sha(Path(n))!=h for n,h in i['external_files'].items())
            or any(sha(out/n)!=h for n,h in r['files'].items())
            or sha(Path(i['yosys']['path']))!=i['yosys']['sha256'] or not r['all_negative_controls_rejected']
            or r['qualified_phy'] or r['electrical_qualification_passed'] or r['routed_geometry_qualified']
            or r['tail_cell_rc_applied_to_native_reference']
            or len(r['negative_controls'])!=13 or len(r['native_negative_controls'])!=2
            or not all(c['rejected'] for c in r['negative_controls']+r['native_negative_controls'])):
        raise ValueError('Independent physical bank graph proof changed')
    pi=producer.bound(ROOT/i['parent']);g,native,counts=reconstruct(pi)
    if (producer.view.verify_json(json.loads((out/'bank.json').read_text()),g)!=r['result']
            or (out/'bank.sch.spice').read_text()!=native or r['native_counts']!=counts):
        raise ValueError('Independent physical graph/native source changed')
    return i


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path)
    a=p.parse_args();print(verify(a.artifact.resolve()),flush=True)
