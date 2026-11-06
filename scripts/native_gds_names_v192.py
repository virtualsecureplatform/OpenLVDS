# SPDX-License-Identifier: GPL-3.0-only
"""Exact directory-prefix canonicalization; masks, texts and placement unchanged."""
from collections import Counter
from pathlib import Path


def canonical_names(names,prefix,allowed):
    if not prefix.endswith('/') or not prefix.startswith('/work/OpenLVDS/'):raise ValueError('Require exact captured container directory prefix')
    result={}
    for name in names:
        target=name[len(prefix):] if name.startswith(prefix) else name
        if '/' in target or target not in allowed:raise ValueError('Unexpected GDS cell path or master '+name)
        result[name]=target
    if len(result)!=len(names) or len(set(result.values()))!=len(result) or set(result.values())!=set(allowed):raise ValueError('GDS name mapping is not an exact bijection')
    return result


def mag_names(text,mapping):
    rows=[];changes=0
    for line in text.splitlines(keepends=True):
        if line.startswith('use '):
            words=line.split()
            if len(words)!=3 or words[1] not in set(mapping)|set(mapping.values()):raise ValueError('Unexpected native MAG child reference')
            target=mapping.get(words[1],words[1])
            if target!=words[1]:
                line=line.replace(words[1],target,1);changes+=1
        rows.append(line)
    return ''.join(rows),changes


def inspect(paths,gds,prefix,top):
    import klayout.db as db
    allowed={top}
    for path in paths:
        lib=db.Layout();lib.read(path)
        if lib.dbu!=.001:raise ValueError('Native component GDS scale changed')
        allowed.update(c.name for c in lib.each_cell())
    lib=db.Layout();lib.read(gds)
    if lib.dbu!=.001:raise ValueError('Original integrated GDS scale changed')
    return canonical_names([c.name for c in lib.each_cell()],prefix,allowed)


def equivalent(before,after,mapping):
    import klayout.db as db
    a=db.Layout();a.read(before);b=db.Layout();b.read(after)
    if a.dbu!=.001 or b.dbu!=a.dbu or {c.name for c in a.each_cell()}!=set(mapping) or {c.name for c in b.each_cell()}!=set(mapping.values()):raise ValueError('Name-only GDS cell inventory changed')
    def geometry(lib,cell):
        result={}
        for i in lib.layer_indexes():
            shapes=cell.shapes(i)
            if not shapes.is_empty():result[(lib.get_info(i).layer,lib.get_info(i).datatype)]=db.Region(shapes).merged()
        return result
    def texts(lib,cell):
        return Counter((lib.get_info(i).layer,lib.get_info(i).datatype,s.text.string,s.text.trans.to_s()) for i in lib.layer_indexes() for s in cell.shapes(i).each() if s.is_text())
    def places(lib,cell,names):return Counter((names[lib.cell(i.cell_index).name],i.cplx_trans.to_s(),i.a.x,i.a.y,i.b.x,i.b.y,i.na,i.nb) for i in cell.each_inst())
    for cell in a.each_cell():
        other=b.cell(mapping[cell.name]);x=geometry(a,cell);y=geometry(b,other)
        if set(x)!=set(y) or any(not (x[k]^y[k]).is_empty() for k in x):raise ValueError('Name repair changed GDS masks '+cell.name)
        if texts(a,cell)!=texts(b,other):raise ValueError('Name repair changed GDS labels '+cell.name)
        if places(a,cell,mapping)!=places(b,other,{n:n for n in mapping.values()}):raise ValueError('Name repair changed GDS placement '+cell.name)
    return dict(exact_cell_name_bijection=True,all_masks_identical=True,all_labels_identical=True,all_child_and_root_placements_identical=True,
                cells=len(mapping),renamed_cells=sum(a!=b for a,b in mapping.items()),qualified_phy=False)


if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['inspect','verify']);p.add_argument('spec',type=Path);a=p.parse_args();s=json.loads(a.spec.read_text())
    print(json.dumps(inspect(s['components'],s['gds'],s['prefix'],s['top']) if a.action=='inspect' else equivalent(s['before'],s['after'],s['mapping'])))
