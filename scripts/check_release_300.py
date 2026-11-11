#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fail-closed 300 MHz release inventory, independent of legacy OTA release."""
import argparse
import json
from pathlib import Path
from xyce_profile_300 import ROOT, sha
import clocking_profile_300


def local(root, name):
    p = (root / name).resolve()
    if not p.is_relative_to(root.resolve()) or not p.is_file():
        raise ValueError('Missing or external release evidence: ' + name)
    return p


def check(root=ROOT, policy=None):
    policy = policy or json.loads((root / 'qualification_300.json').read_text())
    contract = local(root, policy['contract'])
    binding = sha(contract)
    required = json.loads((root / 'qualification_300.json').read_text())
    if policy != required or policy['schema'] != 'openlvds-qualification-300-v1':
        raise ValueError('Qualification policy changed')
    legacy_gates = json.loads(contract.read_text())['clocking']['release_gates']
    if not set(legacy_gates) <= set(policy['gates']) or len(set(policy['gates'])) != len(policy['gates']):
        raise ValueError('Required release coverage omitted or duplicated')
    candidate_path = root / 'build/release_300/candidate.json'
    candidate_errors = []
    candidate_hash = None
    try:
        candidate = json.loads(candidate_path.read_text())
        candidate_hash = sha(candidate_path)
        requirements = json.loads(contract.read_text())['requirements']
        if candidate['contract_sha256'] != binding or candidate['pdk_version'] != requirements['pdk_version']:
            raise ValueError('Frozen candidate contract or PDK mismatch')
        if candidate['views_sha256'] != sha(root / 'build/release_300/views.json'):
            raise ValueError('Published view manifest differs from frozen candidate')
        if not candidate.get('source_files') or not candidate.get('tool_receipts'):
            raise ValueError('Frozen candidate lacks implementation sources/tool receipts')
        for name, digest in {**candidate['source_files'], **candidate['tool_receipts']}.items():
            if sha(local(root, name)) != digest:
                raise ValueError('Frozen candidate input changed: ' + name)
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        candidate_errors.append(str(exc))
    rows = []
    for gate in policy['gates']:
        entry = policy['evidence'].get(gate)
        state, error = 'missing', None
        try:
            if entry:
                receipt = json.loads(local(root, entry['path']).read_text())
                if sha(local(root, entry['path'])) != entry['sha256']:
                    raise ValueError('Receipt hash mismatch')
                if receipt['gate'] != gate or receipt['contract_sha256'] != binding:
                    raise ValueError('Evidence gate or contract mismatch')
                state = receipt['state']
                if state not in policy['states']:
                    raise ValueError('Unknown evidence state')
                if state == 'pass':
                    if candidate_errors or receipt.get('candidate_sha256') != candidate_hash:
                        raise ValueError('Evidence does not bind the current frozen candidate')
                    if receipt.get('complete') is not True or not receipt.get('files') or not receipt.get('checks'):
                        raise ValueError('Passing evidence lacks complete files/checks')
                    if not all(v is True for v in receipt['checks'].values()):
                        raise ValueError('Passing evidence contains failed checks')
                    for name, digest in receipt['files'].items():
                        if sha(local(root, name)) != digest:
                            raise ValueError('Evidence input changed: ' + name)
        except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
            state, error = 'fail', str(exc)
        rows.append(dict(gate=gate, state=state, error=error))
    views = []
    manifest = root / 'build/release_300/views.json'
    published = json.loads(manifest.read_text()) if manifest.exists() else {}
    for macro in policy['macros']:
        for view in policy['release_views']:
            error = None
            try:
                item = published[macro][view]
                entries = item if isinstance(item, list) else [item]
                if not entries:
                    raise ValueError('Empty view')
                for entry in entries:
                    if sha(local(root, entry['path'])) != entry['sha256']:
                        raise ValueError('View hash mismatch')
                if view == 'liberty':
                    requirements = json.loads(contract.read_text())['requirements']
                    expected = {(p, t) for p in requirements['process_corners'] for t in requirements['temperatures_c']}
                    points = [(entry['process'], entry['temperature_c']) for entry in entries]
                    if len(points) != 15 or set(points) != expected or len({entry['path'] for entry in entries}) != 15:
                        raise ValueError('Require distinct Liberty views for all 15 PVT points')
            except (KeyError, ValueError, TypeError, OSError) as exc:
                error = str(exc)
            views.append(dict(macro=macro, view=view, present_and_hashed=error is None, error=error))
    return dict(schema='openlvds-release-check-300-v1', contract_sha256=binding,
                candidate_sha256=candidate_hash, candidate_errors=candidate_errors, gates=rows, views=views,
                qualified_phy=not candidate_errors and all(r['state'] == 'pass' for r in rows) and all(v['present_and_hashed'] for v in views),
                scope='Public SKY130A macro handoff; host/foundry acceptance is external')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inventory', action='store_true', help='Report current missing gates without release success')
    a = p.parse_args()
    clocking_profile_300.load()
    result = check()
    print(json.dumps(result, indent=2))
    return 0 if a.inventory or result['qualified_phy'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
