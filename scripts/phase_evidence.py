# SPDX-License-Identifier: GPL-3.0-only
"""Validate current, complete extracted phase-fault response evidence."""
import hashlib
import json
import re
from pathlib import Path
import numpy as np
from spice_scope import closure_hash
from verify_phase_detector import metrics,response_cases


def digest(data):return hashlib.sha256(data).hexdigest()


def case_valid(folder,result,case,scope,requirements,simulator,stamp,producer):
    try:
        c,t,o,sr,sf=case
        expected=dict(corner=c,temperature_c=t,offset_ps=o,reference_slew_ps=sr,feedback_slew_ps=sf,
                      measurement_window_ns=[120,160],requirements_sha256=requirements,
                      simulator=simulator,simulator_provenance=stamp)
        if result.get('passed') is not True or any(result.get(k)!=v for k,v in expected.items()):return False
        files=result['files']
        for name in ['library.spice','producer.py','bench.cir','bench.cir.prn']:
            path=folder/name
            if not path.resolve().is_relative_to(folder.resolve()) or digest(path.read_bytes())!=files.get(name):return False
        deck=(folder/'bench.cir').read_text()
        corners=re.findall(r'(?im)^\.lib\s+"[^"\n]*/sky130\.lib\.spice"\s+(\w+)\s*$',deck)
        temperatures=re.findall(r'(?im)^\.options\s+device\s+temp=([-+0-9.eE]+)\s*$',deck)
        if corners!=[c] or len(temperatures)!=1 or float(temperatures[0])!=t:return False
        for source,nodes,value in [('VD','VDDD 0','1.8'),('VA','VDDIO 0','3.3'),('IB','PB 0','35u')]:
            if len(re.findall(r'(?im)^'+source+r'\s+'+nodes.replace(' ',r'\s+')+r'\s+'+re.escape(value)+r'\s*$',deck))!=1:return False
        if files['producer.py']!=producer or closure_hash((folder/'library.spice').read_bytes(),'openlvds_dll')!=scope:return False
        rows=[]
        for line in (folder/'bench.cir.prn').read_text().splitlines():
            try:rows.append(list(map(float,line.split())))
            except ValueError:pass
        wave=np.array(rows)
        if not metrics(wave,o,120e-9,160e-9)['passed']:return False
        # Confirm that a mislabeled frequency or slew cannot satisfy a case.
        for col,slew in [(2,sr),(3,sf)]:
            edges=[]
            for level in [.18,.9,1.62]:
                v=wave[:,col];time=wave[:,1];i=np.flatnonzero((v[:-1]<level)&(v[1:]>=level))
                edges.append(time[i]+(level-v[i])*(time[i+1]-time[i])/(v[i+1]-v[i]))
            lo,mid,hi=edges;mid=mid[(mid>121e-9)&(mid<159e-9)]
            if len(mid)<10 or np.max(abs(np.diff(mid)-2.5e-9))>5e-12:return False
            falls_v=wave[:,col];ix=np.flatnonzero((falls_v[:-1]>=.9)&(falls_v[1:]<.9))
            falls=time[ix]+(.9-falls_v[ix])*(time[ix+1]-time[ix])/(falls_v[ix+1]-falls_v[ix])
            for at in mid:
                after=falls[falls>at]
                if not len(after) or abs(after[0]-at-1.25e-9)>5e-12:return False
                lower=lo[lo<at];upper=hi[hi>at]
                if not len(lower) or not len(upper):return False
                if abs((upper[0]-lower[-1])*1e12-.8*slew)>5:return False
        return True
    except (OSError,ValueError,KeyError,TypeError,IndexError):return False


def valid(root,pointer,library,inputs,requirements,simulator,stamp,mode):
    try:
        if mode not in ['corners','slew']:return False
        folder=(root/pointer['report']).resolve()
        allowed=(root/'build/phase_detector/extracted').resolve()
        if not folder.is_relative_to(allowed) or folder.name!='summary.json':return False
        raw=folder.read_bytes()
        if digest(raw)!=pointer['sha256']:return False
        report=json.loads(raw)
        if report.get('passed') is not True or report.get('extracted') is not True:return False
        if report.get('corners') is not (mode=='corners') or report.get('slew_corners') is not (mode=='slew'):return False
        expected={f'{c}_{t}_{o}ps_r{sr}_f{sf}':(c,t,o,sr,sf) for c,t,o,sr,sf in response_cases(mode=='corners',mode=='slew')}
        if set(report['cases'])!=set(expected):return False
        scope=closure_hash(library,'openlvds_dll');producer=digest((root/'scripts/verify_phase_detector.py').read_bytes())
        for name,case in expected.items():
            if not (folder.parent/name).resolve().is_relative_to(allowed):return False
            result=report['cases'][name]
            if result.get('extraction_inputs')!=inputs:return False
            if not case_valid(folder.parent/name,result,case,scope,requirements,simulator,stamp,producer):return False
        return True
    except (OSError,ValueError,KeyError,TypeError):return False
