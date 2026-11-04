# SPDX-License-Identifier: GPL-3.0-only
"""Find one conservative legal raw-code path common to all supplied corners.

This is a reference/ROM-generation algorithm, not characterization admission.
The caller must supply measured conservative intervals and separately prove
complete PVT/physical/model coverage. Never reorder codes per process corner.
"""
from bisect import bisect_right
import math


def common_path(corners,start_code,minimum_span_ps,maximum_gap_ps=20,preferred_gap_ps=10):
    if (not corners or not math.isfinite(minimum_span_ps) or minimum_span_ps<=0
        or not 0<preferred_gap_ps<=maximum_gap_ps<=20):
        raise ValueError('Invalid common code-path policy')
    first=next(iter(corners.values()));codes=set(first)
    if start_code not in codes or len(codes)<2:raise ValueError('Missing start code or characterization')
    for table in corners.values():
        if set(table)!=codes or any(d.code!=code for code,d in table.items()):
            raise ValueError('Different raw-code coverage across corners')
    order=sorted(codes,key=lambda code:(first[code].lo_ps,first[code].hi_ps,code))
    low=[first[c].lo_ps for c in order]
    position={code:i for i,code in enumerate(order)}
    for limit in sorted(set([preferred_gap_ps,maximum_gap_ps])):
        paths={start_code:(start_code,)}
        for code in order[position[start_code]:]:
            if code not in paths:continue
            # Any legal edge has first-corner next.lo <= current.lo+limit.
            # This limits work to a local time neighborhood rather than N^2.
            end=bisect_right(low,first[code].lo_ps+limit)
            for nxt in order[position[code]+1:end]:
                if all(table[nxt].lo_ps>table[code].hi_ps and
                       table[nxt].hi_ps-table[code].lo_ps<=limit for table in corners.values()):
                    candidate=paths[code]+(nxt,)
                    old=paths.get(nxt)
                    if old is None or (len(candidate),candidate)<(len(old),old):paths[nxt]=candidate
        endpoints=[c for c in paths if all(t[c].lo_ps-t[start_code].hi_ps>=minimum_span_ps for t in corners.values())]
        if not endpoints:continue
        end=min(endpoints,key=lambda c:(len(paths[c]),paths[c]))
        path=paths[end]
        steps={p:max(t[b].hi_ps-t[a].lo_ps for a,b in zip(path,path[1:])) for p,t in corners.items()}
        return dict(codes=path,gap_limit_ps=limit,worst_step_ps=steps,
            span_lower_bound_ps={p:t[end].lo_ps-t[start_code].hi_ps for p,t in corners.items()},
            qualified_phy=False,characterization_admitted=False)
    raise ValueError('No common monotonic code path spans the requested delay range')
