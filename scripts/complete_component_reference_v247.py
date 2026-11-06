# SPDX-License-Identifier: GPL-3.0-only
"""Complete schematic junction references from qualified native flat masters."""
import re
import native_bank_inventory_v51 as native
from build_compound_drivers_v3 import cell_definition


def complete(reference,extractions,orders):
    result=reference;proofs={}
    for model,text in extractions.items():
        old=cell_definition(reference,model)
        text=re.sub(r'\n[ \t]*\+[ \t]*',' ',text)
        ports,expected=native.native_leaves(reference,model)
        actual_ports,actual=native.native_leaves(text,model+'_flat')
        canonical=orders[model]
        if len(set(canonical))!=len(canonical) or set(actual_ports)!=set(ports) or set(ports)!=set(canonical):
            raise ValueError('Qualified native master pin names differ')
        proof=native.compare_parameters(expected,actual)
        flat=cell_definition(text,model+'_flat')
        flat=re.sub(r'(?m)^\.subckt '+re.escape(model)+r'_flat[^\n]*','.subckt '+model+' '+' '.join(canonical),flat,count=1)
        flat=re.sub(r'(?m)^\.ends(?:[ \t]+[^\n]+)?', '.ends '+model,flat,count=1)
        if native.native_leaves(flat,model)[1]!=actual:
            raise ValueError('Native flat master changed during top-name replacement')
        result=result.replace(old,flat,1)
        proofs[model]=dict(proof,source='qualified_native_flat_master',junction_values_inferred=False,
            original_schematic_ports=ports,qualified_native_ports=actual_ports,canonical_ports=canonical,
            master_header_order_normalized_by_names=True)
    for model in native.layout.circuits(reference):
        if model not in extractions and cell_definition(reference,model)!=cell_definition(result,model):
            raise ValueError('Unrelated component reference changed')
    defs=native.layout.circuits(result)
    if any(defs[model][0]!=order for model,order in orders.items()):
        raise ValueError('Native definition port order differs from emitted graph instance order')
    return result,proofs
