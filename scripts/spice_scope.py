# SPDX-License-Identifier: GPL-3.0-only
"""Hash the exact instantiated subcircuit closure, ignoring unused definitions."""
import hashlib
import re

def closure_hash(library,top):
    text=library.decode() if isinstance(library,bytes) else library
    definitions={m[1].lower():m[0] for m in re.finditer(
        r'(?ims)^\.subckt[ \t]+(\S+)[ \t]+.*?^\.ends[^\n]*',text)}
    visited={}
    def visit(name):
        key=name.lower()
        if key in visited:return
        if key not in definitions:raise ValueError('Missing simulation root '+name)
        block=definitions[key];visited[key]=block
        for line in block.splitlines():
            words=line.split()
            if words and words[0].lower().startswith('x'):
                end=next((i for i,w in enumerate(words) if '=' in w),len(words))
                child=words[end-1].lower()
                if child in definitions:visit(child)
    visit(top)
    return hashlib.sha256('\n'.join(visited[k] for k in sorted(visited)).encode()).hexdigest()
