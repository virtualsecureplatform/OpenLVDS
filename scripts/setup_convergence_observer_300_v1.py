#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Separate ngspice42 convergence observer and diode-only diagnostic backport."""
import hashlib,json,os,re,shutil,subprocess
from pathlib import Path
import setup_step_observer_v356 as old
ROOT=old.ROOT
PARENT=ROOT/'build/tools/ngspice42-step-observer-v356/67d47f2680c332a2'
BEGIN='/* OPENLVDS_CONV_BEGIN */';END='/* OPENLVDS_CONV_END */'

def strip(text):
    return re.sub(re.escape(BEGIN)+'.*?'+re.escape(END),'',text,flags=re.S)

def instrument(text):
    needle='                ckt->CKTtroubleNode = i;'
    if text.count(needle)!=2:raise ValueError('Pinned convergence sites changed')
    code='''                if (openlvds_trace_hit(ckt->CKTtime))
                    fprintf(stderr, "OLVDS_CONV t=%.17g dt=%.17g node=%s type=%d old=%.17g new=%.17g delta=%.17g tolerance=%.17g ratio=%.17g\\n",
                        ckt->CKTtime, ckt->CKTdelta, CKTnodName(ckt,i), node->type,
                        old, new, fabs(new-old), tol, fabs(new-old)/tol);
'''
    result=BEGIN+'#include "ngspice/openlvds_step_trace.h"\n'+END+text.replace(needle,BEGIN+code+END+needle)
    if strip(result)!=text:raise ValueError('Numerical code changed')
    return result

def diode_patch(text):
    needle='deplchargeSW = czeroSW*here->DIOtF1+'
    if text.count(needle)!=1:raise ValueError('Pinned diode continuation changed')
    # Integral of the EXISTING lower-voltage branch at its own transition.
    # Diagnostic backport only; preserves all PDK parameters and C(V).
    expr='(here->DIOtJctSWPot*(1-pow(1-here->DIOtDepSWCap/here->DIOtJctSWPot,1-model->DIOgradingSWCoeff))/(1-model->DIOgradingSWCoeff))'
    return text.replace(needle,'deplchargeSW = czeroSW*'+expr+'+')

def build():
    parent=json.loads((PARENT/'summary.json').read_text())
    if old.sha(ROOT/parent['binary'])!=parent['binary_sha256']:raise ValueError('Retained observer changed')
    identity=dict(version='convergence-observer-300-v1',script_sha256=old.sha(__file__),
        parent_summary_sha256=old.sha(PARENT/'summary.json'),production_sha256=old.sha(ROOT/'build/tools/ngspice.json'),
        diagnostic_only=True,qualified_phy=False)
    out=ROOT/'build/tools/convergence-observer-300-v1'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);print(out,flush=True)
    (out/'identity.json').write_text(json.dumps(identity,indent=2)+'\n')
    source=Path(parent['configure'][0]).parent
    env=dict(os.environ,LC_ALL='C',PATH=str(PARENT/'helpers/bin')+os.pathsep+os.environ['PATH'],BISON_PKGDATADIR=str(PARENT/'helpers/share/bison'))
    results=[]
    for variant in ('observer','diode_patch'):
        folder=out/variant;folder.mkdir();src=folder/'source';shutil.copytree(source,src)
        path=src/'src/maths/ni/niconv.c';original=path.read_text();path.write_text(instrument(original))
        diode=src/'src/spicelib/devices/dio/dioload.c';before=diode.read_text()
        if variant=='diode_patch':diode.write_text(diode_patch(before))
        proof=dict(convergence_original_sha256=hashlib.sha256(original.encode()).hexdigest(),
            convergence_observed_sha256=old.sha(path),original_convergence_exactly_recoverable=strip(path.read_text())==original,
            diode_original_sha256=hashlib.sha256(before.encode()).hexdigest(),diode_sha256=old.sha(diode),
            standalone_diode_only_patch=variant=='diode_patch',mos_models_changed=False)
        (folder/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
        obj=folder/'objects';obj.mkdir()
        for command in ([str(src/'configure')]+parent['configure'][1:],['make','-j2']):
            with (folder/'build.log').open('a') as log:subprocess.run(command,cwd=obj,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        binary=obj/'src/ngspice'
        results.append(dict(variant=variant,binary=str(binary.relative_to(ROOT)),sha256=old.sha(binary),proof=proof))
    if old.sha(ROOT/'build/tools/ngspice.json')!=identity['production_sha256']:raise ValueError('Production changed')
    (out/'summary.json').write_text(json.dumps(dict(identity=identity,builds=results,qualified_phy=False),indent=2)+'\n')
    print(out/'summary.json',flush=True)
    return out
if __name__=='__main__':build()
