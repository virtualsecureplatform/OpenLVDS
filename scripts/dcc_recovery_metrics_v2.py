# SPDX-License-Identifier: GPL-3.0-only
"""Preserve untimed metrics explicitly; never turn nonfinite values into zero."""
import math

PHYSICAL_KEYS=['route__drc_errors','magic__drc_error__count','klayout__drc_error__count',
    'design__lvs_error__count','antenna__violating__nets','antenna__violating__pins']


def physical_clean(metrics):
    return all(type(metrics.get(k)) in [int,float] and math.isfinite(metrics[k]) and metrics[k]==0 for k in PHYSICAL_KEYS)


def explicit_metrics(value,path='',nonfinite=None):
    if nonfinite is None:nonfinite={}
    if isinstance(value,float) and not math.isfinite(value):
        label='NaN' if math.isnan(value) else ('Infinity' if value>0 else '-Infinity')
        nonfinite[path]=label
        return dict(nonfinite=label),nonfinite
    if isinstance(value,dict):
        result={}
        for key,item in value.items():result[key],_=explicit_metrics(item,path+'/'+str(key),nonfinite)
        return result,nonfinite
    if isinstance(value,list):
        result=[]
        for index,item in enumerate(value):
            converted,_=explicit_metrics(item,path+'/'+str(index),nonfinite);result.append(converted)
        return result,nonfinite
    return value,nonfinite
