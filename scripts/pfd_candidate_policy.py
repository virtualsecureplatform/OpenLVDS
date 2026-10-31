# SPDX-License-Identifier: GPL-3.0-only
"""Select an explicit supported pulse-area PFD topology; never infer a fallback."""
import hashlib
from pathlib import Path
from physical_policy import pfd_area_paths_retained
from pfd_fast_reset_policy import pfd_fast_reset_paths_retained


def pfd_candidate_paths_retained(netlist, policy):
    if policy == 'pulse-area':
        return pfd_area_paths_retained(netlist)
    if policy == 'pulse-area-fast-reset':
        return pfd_fast_reset_paths_retained(netlist)
    return False


def policy_provenance(root):
    return {name: hashlib.sha256((Path(root) / 'scripts' / name).read_bytes()).hexdigest()
            for name in ['pfd_candidate_policy.py', 'pfd_fast_reset_policy.py', 'physical_policy.py']}
