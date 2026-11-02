#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fail the command unless both captured OpenPLL traces pass the current clock contract."""
import json
import check_openpll_contract as audit


def require():
    out=audit.verify()
    result=json.loads((out/'summary.json').read_text())
    rows=result.get('results',[])
    if (result.get('passed') is not True or len(rows)!=2 or {r.get('kind') for r in rows}!={'rtl','physical'} or
            any(r.get('metrics',{}).get('passed') is not True or r.get('legacy_metrics_verified') is not True for r in rows)):
        raise ValueError('Captured OpenPLL traces do not both pass the current frequency/duty contract')
    return out


if __name__=='__main__':print(require()/'summary.json',flush=True)
