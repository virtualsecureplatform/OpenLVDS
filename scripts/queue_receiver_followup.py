#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Prepare and run receiver follow-ups after a source-to-native continuation passes."""
import argparse
import ast
import fcntl
import json
from pathlib import Path
import subprocess
import time

from continue_receiver_candidate import admitted, digest

ROOT = Path(__file__).resolve().parents[1]


def artifact(value, kind, root=ROOT):
    path = Path(value)
    if path.is_relative_to('/work/OpenLVDS'):
        path = root / path.relative_to('/work/OpenLVDS')
    path = (root / path).resolve()
    if not path.is_relative_to(root / 'build/diagnostics' / kind):
        raise ValueError('Unexpected receiver artifact: ' + str(value))
    return path


def completed_native(state, owner_active, root=ROOT):
    """An active owner or incomplete state never releases downstream work."""
    if owner_active:
        return None
    if state.get('status') != 'native_replay_passed':
        raise ValueError('Native receiver continuation did not pass')
    layout = artifact(state['layout'], 'receiver_layout', root)
    replay = artifact(state['replay'], 'receiver_replay', root)
    capture = json.loads((replay / 'manifest.json').read_text())['identity']
    if capture['layout'] != str(layout.relative_to(root)):
        raise ValueError('Native replay selects a different receiver layout')
    admitted(json.loads((replay / 'summary.json').read_text()))
    return layout, replay


def producer_names(root=ROOT, profile='baseline'):
    if profile not in ['baseline', 'unclamped_tail_headroom']:
        raise ValueError('Unknown receiver follow-up profile')
    names = {'queue_receiver_followup.py', 'continue_receiver_candidate.py'}
    producers = ['qualify_receiver_components.py', 'probe_receiver_candidate_link.py']
    if profile == 'unclamped_tail_headroom':
        names.update(['qualify_unclamped_receiver.py', 'continue_receiver_unclamped_candidate.py'])
        # The selector imports all three verifiers, and preparation captures the
        # chosen verifier's complete scientific producer set.
        producers += ['probe_receiver_unclamped_restore_candidate.py',
                      'probe_receiver_lvt_restore_candidate.py',
                      'probe_receiver_tail_headroom_candidate.py']
    for name in producers:
        tree = ast.parse((root / 'scripts' / name).read_text())
        value = next(ast.literal_eval(node.value) for node in tree.body
                     if isinstance(node, ast.Assign) and any(
                         isinstance(t, ast.Name) and t.id == 'CODE' for t in node.targets))
        names.update(value)
    return names


def preparation_commands(profile, layout, replay, link):
    if profile == 'baseline':
        return ([ 'scripts/qualify_receiver_components.py', 'prepare', str(layout), str(replay)],
                ['scripts/probe_receiver_candidate_link.py', 'prepare', str(link), str(replay)],
                'scripts/continue_receiver_candidate.py')
    if profile == 'unclamped_tail_headroom':
        return (['scripts/qualify_unclamped_receiver.py', 'prepare-components', str(layout), '--replay', str(replay)],
                ['scripts/qualify_unclamped_receiver.py', 'prepare-link', str(link), '--replay', str(replay)],
                'scripts/continue_receiver_unclamped_candidate.py')
    raise ValueError('Unknown receiver follow-up profile')


def run(screen, link, unit, profile='baseline'):
    preparation_commands(profile, Path('layout'), Path('replay'), Path('link'))
    screen = artifact(str(screen), 'receiver_clamp')
    link = link.resolve()
    if not link.is_relative_to(ROOT / 'build/link'):
        raise ValueError('Use an original saved link reference')
    upstream = screen / 'native_continuation'
    upstream_manifest = json.loads((upstream / 'manifest.json').read_text())
    names = producer_names() if profile == 'baseline' else producer_names(profile=profile)
    files = [ROOT / 'scripts' / n for n in names | set(upstream_manifest['code'])]
    files += [upstream / 'manifest.json', screen / 'manifest.json', ROOT / 'requirements.json',
              ROOT / 'scripts/env.sh', link / 'summary.json', link / 'bench.cir',
              link / 'library.spice', link / 'bench.cir.prn']
    identity = dict(producer_unit=unit, screen=str(screen.relative_to(ROOT)),
                    link=str(link.relative_to(ROOT)),
                    inputs={str(p.relative_to(ROOT)): digest(p) for p in files})
    if profile != 'baseline':
        identity['receiver_profile'] = profile
    folder = screen / 'component_link_continuation'
    folder.mkdir(exist_ok=True)

    def save(status, **fields):
        temp = folder / 'state.json.tmp'
        temp.write_text(json.dumps(dict(status=status, qualified_phy=False, **fields), indent=2) + '\n')
        temp.replace(folder / 'state.json')

    def unchanged():
        if any(digest(ROOT / name) != stamp for name, stamp in identity['inputs'].items()):
            raise ValueError('Receiver follow-up queue inputs changed')

    def execute(label, command):
        unchanged()
        save(label)
        log = folder / (label + '.log')
        with log.open('w') as output:
            subprocess.run(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=True)
        unchanged()
        return log.read_text().strip().splitlines()[-1]

    with (folder / '.execution.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        capture = folder / 'manifest.json'
        if capture.exists() and json.loads(capture.read_text()) != identity:
            raise ValueError('Receiver follow-up queue identity changed')
        capture.write_text(json.dumps(identity, indent=2) + '\n')
        (folder / 'producer.py').write_bytes(Path(__file__).read_bytes())
        try:
            while True:
                unchanged()
                try:
                    owner = subprocess.run(['systemctl', '--user', 'show', unit, '-p', 'ActiveState', '--value'],
                                           capture_output=True, text=True, check=True).stdout.strip()
                except (OSError, subprocess.CalledProcessError):
                    save('retrying_native_owner_observation')
                    time.sleep(10)
                    continue
                state = json.loads((upstream / 'state.json').read_text())
                result = completed_native(state, owner in ['active', 'activating', 'deactivating'], ROOT)
                if result is not None:
                    layout, replay = result
                    break
                save('waiting_for_native_replay', owner_state=owner, native_state=state['status'])
                time.sleep(10)
            env = [str(ROOT / 'scripts/env.sh'), '--ngspice', 'python3']
            if profile != 'baseline':
                selected = json.loads((replay / 'manifest.json').read_text())['identity']
                if selected.get('clamp_variant') != profile:
                    raise ValueError('Native replay differs from the requested receiver profile')
            component_command, link_command, follower = preparation_commands(
                profile, layout.relative_to(ROOT), replay.relative_to(ROOT), link.relative_to(ROOT))
            components = artifact(execute('prepare_components', env + component_command), 'receiver_components')
            candidate_link = artifact(execute('prepare_link', env + link_command), 'receiver_candidate_link')
            execute('run_followup', ['/usr/bin/python3', follower,
                    str(replay), str(components), str(candidate_link), '--producer-unit', unit])
            reports = {}
            for name, path in [('components', components), ('link', candidate_link)]:
                report = path / 'summary.json'
                summary = json.loads(report.read_text())
                if summary['manifest_sha256'] != digest(path / 'manifest.json') or not summary['passed']:
                    raise ValueError('Receiver follow-up failed: ' + name)
                reports[name] = dict(report=str(report.relative_to(ROOT)), sha256=digest(report))
            save('diagnostics_passed', reports=reports,
                 next_gate='Complete DLL, aperture, headroom, RC and full-link release qualification')
        except Exception as error:
            save('held_for_diagnosis', error=str(error))
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('screen', type=Path)
    parser.add_argument('link', type=Path)
    parser.add_argument('--producer-unit', required=True)
    parser.add_argument('--receiver-profile', choices=['baseline', 'unclamped_tail_headroom'], default='baseline')
    args = parser.parse_args()
    run(args.screen.resolve(), args.link.resolve(), args.producer_unit, args.receiver_profile)
