#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Render a completed recorded placement with the native KLayout viewer.

Visualization of an unrouted feasibility snapshot, not a new qualification.
Read-only source artifact; PNG and rendering receipt go in build/reports.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import klayout.db as db
import klayout.lay as lay

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def render(parent):
    m=json.loads((parent/'manifest.json').read_text());i=m['identity'];r=json.loads((parent/'summary.json').read_text())
    if (parent.parent!=ROOT/'build/diagnostics/balanced_placement_v129'
        or parent.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or i['version']!='measured-balanced-gangs-real-master-placement-feasibility-v129.1'
        or json.loads((parent/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False)
        or not r['placement_feasibility_passed'] or r['placement_geometry']['drc_count']!='0'
        or any(sha(parent/n)!=h for n,h in r['files'].items())):
        raise ValueError('Require an unchanged completed recorded placement')
    actual={w[0]:[float(v)/1000 for v in w[4:]] for line in (parent/'boxes.tsv').read_text().splitlines() if (w:=line.split('\t'))}
    if actual!=i['plan']['boxes']:raise ValueError('Recorded OpenDB boxes differ from rendering plan')
    file=parent/(i['graph']['top']+'.gds')
    out=ROOT/'build/reports/balanced_placement_v130'/parent.name;out.mkdir(parents=True,exist_ok=False)
    image=out/('unrouted_'+i['profile']+'.png');view=lay.LayoutView();view.load_layout(str(file),0)
    layer=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/klayout/tech/sky130A.lyp'
    if layer.is_file():view.load_layer_props(str(layer))
    view.add_missing_layers();view.max_hier();view.set_config('background-color','#ffffff');view.set_config('grid-visible','false')
    view.zoom_box(db.DBox(*i['plan']['die']));view.save_image(str(image),1800,600)
    report=dict(source=str(parent.relative_to(ROOT)),source_manifest_sha256=sha(parent/'manifest.json'),source_summary_sha256=sha(parent/'summary.json'),
                gds_sha256=sha(file),profile=i['profile'],die_um=i['plan']['die'],instances=len(actual),image=str(image.relative_to(ROOT)),image_sha256=sha(image),
                renderer_sha256=sha(Path(__file__)),klayout_version=db.__version__,layer_properties_sha256=sha(layer) if layer.is_file() else None,
                scope='Native mask rendering of recorded unrouted placement feasibility; routing, native bank LVS/joint RC and electrical/PHY admission remain pending',qualified_phy=False)
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(image,flush=True)
    return image


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args();render(a.artifact.resolve())
