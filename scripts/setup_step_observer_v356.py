#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build a separate pinned ngspice42 observer; never replace the qualified engine.

Every added source region is removable to recover the package source exactly.
No solver expression, iteration limit, tolerance or model equation is changed.
The resulting executable is for performance diagnosis only. Its logging-off
and logging-on waveforms still require comparison with the production runtime.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[1]
VERSION='pinned-ngspice42-removable-step-observer-v356.1'
ARCHIVES={
    'ngspice_42+ds.orig.tar.gz':'cae144ba1d28a56a867e09b9d7665fdf71182e568300e379803786fb0c3165b7',
    'ngspice_42+ds-3build1.debian.tar.xz':'dce5ec571f69f80bea74804eb4ad98e314e54c25a3cb86d121a8f1904a3be5c5'}
BEGIN='/* OPENLVDS_TRACE_BEGIN */'
END='/* OPENLVDS_TRACE_END */'
HEADER='''/* Diagnostic logging only. No simulator state is modified here. */
#ifndef OPENLVDS_STEP_TRACE_H
#define OPENLVDS_STEP_TRACE_H
#include <stdio.h>
#include <stdlib.h>
static int openlvds_trace_hit(double t)
{
    static int enabled = -1;
    static unsigned long count = 0;
    if (enabled < 0) enabled = getenv("OPENLVDS_STEP_TRACE") != NULL;
    if (!enabled || t < 0.0 || t > 200e-12 || count >= 50000) return 0;
    count++;
    return 1;
}
#endif
'''


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def added(text):return BEGIN+text+END


def strip(text):
    return re.sub(re.escape(BEGIN)+'.*?'+re.escape(END),'',text,flags=re.S)


def one(text,needle,code):
    if text.count(needle)!=1:raise ValueError('Pinned diagnostic insertion point changed')
    return text.replace(needle,added(code)+needle,1)


def instrument(name,original):
    """Add only observations, and prove literal recovery of the original file."""
    text=original;sites=0
    if name=='src/maths/ni/niiter.c':
        text=one(text,'            if (iterno > maxIter) {',
            '''            if (iterno > maxIter && openlvds_trace_hit(ckt->CKTtime))
                fprintf(stderr, "OLVDS_STEP kind=ni_limit t=%.17g dt=%.17g iter=%d noncon=%d device=%s node=%s\\n",
                    ckt->CKTtime, ckt->CKTdelta, iterno, ckt->CKTnoncon,
                    ckt->CKTtroubleElt ? ckt->CKTtroubleElt->GENname : "-",
                    ckt->CKTtroubleNode > 0 ? NODENAME(ckt, ckt->CKTtroubleNode) : "-");
''')
        needle='''            if (ckt->CKTnoncon == 0) {
                ckt->CKTstat->STATnumIter += iterno;'''
        text=one(text,needle,'''            if (ckt->CKTnoncon == 0 && openlvds_trace_hit(ckt->CKTtime))
                fprintf(stderr, "OLVDS_STEP kind=ni_success t=%.17g dt=%.17g iter=%d\\n",
                    ckt->CKTtime, ckt->CKTdelta, iterno);
''');sites=2
    elif name=='src/spicelib/analysis/dctran.c':
        text=one(text,'        if(converged != 0) {\n#ifndef CLUSTER',
            '''        if (converged != 0 && openlvds_trace_hit(ckt->CKTtime))
            fprintf(stderr, "OLVDS_STEP kind=noncon_reject t=%.17g dt=%.17g status=%d\\n",
                ckt->CKTtime, ckt->CKTdelta, converged);
''')
        needle='            if (newdelta > .9 * ckt->CKTdelta) {'
        text=one(text,needle,'''            if (openlvds_trace_hit(ckt->CKTtime))
                fprintf(stderr, "OLVDS_STEP kind=trunc_decision t=%.17g dt=%.17g proposed=%.17g order=%d reject=%d\\n",
                    ckt->CKTtime, ckt->CKTdelta, newdelta, ckt->CKTorder,
                    !(newdelta > .9 * ckt->CKTdelta));
''');sites=2
    elif name=='src/spicelib/analysis/ckttrunc.c':
        needle='\t    error = DEVices[i]->DEVtrunc (ckt->CKThead[i], ckt, &timetemp);'
        if text.count(needle)!=1:raise ValueError('Pinned per-type truncation call changed')
        code='''{ double openlvds_before = timetemp;
'''
        tail='''
            if (timetemp < openlvds_before && timetemp <= 2 * ckt->CKTdelta && openlvds_trace_hit(ckt->CKTtime))
                fprintf(stderr, "OLVDS_STEP kind=device_type t=%.17g dt=%.17g type=%s before=%.17g after=%.17g\\n",
                    ckt->CKTtime, ckt->CKTdelta, DEVices[i]->DEVpublic.name, openlvds_before, timetemp);
}
'''
        text=text.replace(needle,added(code)+needle+added(tail));sites=1
    elif name.endswith('trunc.c') and '/devices/' in name:
        # Native SKY130 digital fixtures use BSIM4 and MIM capacitance. Include
        # each retained BSIM4 generation rather than guessing model dispatch.
        if not re.search(r'/devices/(bsim4(?:v\d+)?|cap)/',name):return original,0
        prefix=re.search(r'(\w+)instance\s+\*here',text)
        if not prefix:raise ValueError('Pinned native instance declaration changed: '+name)
        member=prefix[1]+'name'
        pattern=r'CKTterr\(\s*here->(\w+)\s*,\s*ckt\s*,\s*timeStep\s*\);'
        def wrap(match):
            state=match[1]
            return added('{ double openlvds_before = *timeStep;\n')+match[0]+added('''
            if (*timeStep < openlvds_before && *timeStep <= 2 * ckt->CKTdelta && openlvds_trace_hit(ckt->CKTtime))
                fprintf(stderr, "OLVDS_STEP kind=charge_trunc t=%.17g dt=%.17g device=%s state='''+state+''' index=%d before=%.17g after=%.17g q0=%.17g q1=%.17g\\n",
                    ckt->CKTtime, ckt->CKTdelta, here->'''+member+''', here->'''+state+''',
                    openlvds_before, *timeStep, ckt->CKTstate0[here->'''+state+'''], ckt->CKTstate1[here->'''+state+''']);
}
''')
        text,sites=re.subn(pattern,wrap,text)
        if not sites:raise ValueError('Pinned native charge-truncation call changed: '+name)
    if sites:
        text=added('#include "ngspice/openlvds_step_trace.h"\n')+text
        if strip(text)!=original:raise ValueError('Observation changes original numerical source: '+name)
    return text,sites


def run(command,cwd,env=None):
    print('RUN '+json.dumps(command),flush=True)
    subprocess.run(command,cwd=cwd,env=env,check=True)


def build():
    archive_root=ROOT/'build/tools/ngspice-42-option-audit'
    for name,digest in ARCHIVES.items():
        if sha(archive_root/name)!=digest:raise ValueError('Pinned source archive changed: '+name)
    identity=dict(version=VERSION,archives=ARCHIVES,setup_sha256=sha(__file__),
        production_runtime_sha256=sha(ROOT/'build/tools/ngspice.json'),
        max_build_workers=2,diagnostic_only=True)
    out=ROOT/'build/tools/ngspice42-step-observer-v356'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);print(out,flush=True)
    (out/'identity.json').write_text(json.dumps(identity,indent=2)+'\n')
    with tarfile.open(archive_root/'ngspice_42+ds.orig.tar.gz') as tar:
        roots={Path(member.name).parts[0] for member in tar.getmembers()}
        if len(roots)!=1:raise ValueError('Unexpected source root')
        tar.extractall(out,filter='data')
    src=out/next(iter(roots))
    packaging=out/'packaging';packaging.mkdir()
    with tarfile.open(archive_root/'ngspice_42+ds-3build1.debian.tar.xz') as tar:tar.extractall(packaging,filter='data')
    for line in (packaging/'debian/patches/series').read_text().splitlines():
        if not line.strip() or line.startswith('#'):continue
        patch=(packaging/'debian/patches'/line.strip()).resolve()
        patch.relative_to(packaging)
        run(['patch','--batch','--fuzz=0','-p1','-i',str(patch)],src)
    changes=[]
    names=['src/maths/ni/niiter.c','src/spicelib/analysis/dctran.c','src/spicelib/analysis/ckttrunc.c']
    names += [str(p.relative_to(src)) for p in sorted((src/'src/spicelib/devices').glob('*/*trunc.c'))
              if re.search(r'/devices/(bsim4(?:v\d+)?|cap)/',str(p))]
    for name in names:
        path=src/name;original=path.read_text()
        if path.read_bytes()!=original.encode():raise ValueError('Noncanonical source encoding: '+name)
        modified,sites=instrument(name,original)
        if not sites:raise ValueError('Missing required diagnostic hook: '+name)
        path.write_text(modified)
        changes.append(dict(path=name,sites=sites,original_sha256=hashlib.sha256(original.encode()).hexdigest(),
            observed_sha256=sha(path),removable_to_exact_original=True))
    header=src/'src/include/ngspice/openlvds_step_trace.h';header.write_text(HEADER)
    (out/'source_observation_proof.json').write_text(json.dumps(dict(files=changes,
        observer_header_sha256=sha(header),all_original_numerical_source_recovered=True,
        source_math_changed=False,iteration_limits_changed=False,diagnostic_only=True),indent=2)+'\n')
    # Copy parser generators from the already pinned Apptainer environment;
    # nothing is installed into host or production runtime directories.
    helpers=out/'helpers';helpers.mkdir()
    code=('import shutil,sys;from pathlib import Path;d=Path(sys.argv[1]);'
          '(d/"bin").mkdir();'
          'shutil.copy2("/bin/bison",d/"bin/bison");'
          'shutil.copy2("/bin/flex",d/"bin/flex");'
          'shutil.copytree("/usr/share/bison",d/"share/bison")')
    run([str(ROOT/'scripts/env.sh'),'--tools','--ngspice','python3','-c',code,
         '/work/OpenLVDS/'+str(helpers.relative_to(ROOT))],ROOT)
    env=dict(os.environ,PATH=str(helpers/'bin')+os.pathsep+os.environ['PATH'],
             BISON_PKGDATADIR=str(helpers/'share/bison'),LC_ALL='C')
    run(['autoreconf','-fi'],src,env)
    obj=out/'objects';obj.mkdir()
    configure=[str(src/'configure'),'--without-x','--with-editline=no',
        '--enable-cider','--enable-klu','--enable-openmp','--enable-osdi','--enable-pss',
        '--enable-xspice','--enable-maintainer-mode','CFLAGS=-O2 -g']
    run(configure,obj,env);run(['make','-j2'],obj,env)
    binary=obj/'src/ngspice'
    if not binary.is_file():raise ValueError('Observer executable missing')
    info=subprocess.run([str(binary),'-n','-v'],capture_output=True,text=True,check=True)
    (out/'version.txt').write_text(info.stdout+info.stderr)
    if 'Compiled with KLU' not in info.stdout:raise ValueError('Observer lacks original KLU backend')
    if sha(ROOT/'build/tools/ngspice.json')!=identity['production_runtime_sha256']:
        raise ValueError('Production runtime descriptor changed during observer build')
    (out/'summary.json').write_text(json.dumps(dict(identity=identity,binary=str(binary.relative_to(ROOT)),
        binary_sha256=sha(binary),source_observation_proof_sha256=sha(out/'source_observation_proof.json'),
        configure=configure,compiler=subprocess.run(['cc','--version'],capture_output=True,text=True,check=True).stdout,
        ready_for_diagnostic_parity_only=True,production_runtime_replaced=False,qualified_phy=False),indent=2)+'\n')
    print(out/'summary.json',flush=True)
    return out


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    build()
