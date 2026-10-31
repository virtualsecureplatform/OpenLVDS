# SPDX-License-Identifier: GPL-3.0-only
"""Additional native cases selected from the measured all-PVT loop models."""
import math

BASE_CORNERS={('ss',0),('tt',25),('ff',0)}


def limiting_corners(report):
    if not report.get('passed') or not report.get('all_pvt') or not report.get('results'):
        raise ValueError('Passing all-PVT measured stability evidence is required')
    phase=[];gain=[];settling=[]
    for result in report['results']:
        if not result.get('passed'):raise ValueError('Failed model corner')
        process,temp=result['corner'].rsplit('_',1);corner=(process,int(temp))
        if len(result['models'])!=3 or len(result['transient_validation'])!=2:
            raise ValueError('Incomplete corner model coverage')
        for model in result['models']:
            pm=model['phase_margin_min_deg'];gm=model['gain_margin_min_db']
            if not (model['passed'] and math.isfinite(pm) and math.isfinite(gm)):
                raise ValueError('Invalid measured loop margin')
            phase.append((pm,corner));gain.append((gm,corner))
        for step in result['transient_validation']:
            t90=step['predicted_t90_ns']
            if not step['passed'] or not math.isfinite(t90) or t90<=0:
                raise ValueError('Invalid model settling time')
            settling.append((t90,corner))
    return set([min(phase)[1],min(gain)[1],max(settling)[1]])


def recovery_cases(report):
    return [(p,t,target) for p,t in sorted(BASE_CORNERS|limiting_corners(report)) for target in [390,410,None]]
