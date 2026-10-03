#!/usr/bin/env python3
"""Prepare/apply the bounded R6Q Adapter and idle job-runner release.

Never stops Workers, replaces catalogs, edits Home data or resets job status.
All expected-input receipts and backups remain in the private release root.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import time
import urllib.request
from urllib.parse import urlsplit

PROJECT = Path(__file__).resolve().parents[2]
SERVICE = 'browser-platform-environment-job.service'
BINARY = Path('/home/sshUser/.local/lib/browser-platform/profile-adapter')
UNIT = Path('/home/sshUser/.config/systemd/user') / SERVICE


def read(p):
    return json.loads(p.read_bytes())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p, v):
    p.write_text(json.dumps(v, indent=2) + '\n')
    p.chmod(0o600)


def run(args):
    return subprocess.check_output(list(map(str, args)), text=True, stderr=subprocess.PIPE, timeout=90)


def replace(source, target, mode):
    temporary = target.with_name(target.name + '.r6q-new')
    with temporary.open('xb') as stream:
        os.fchmod(stream.fileno(), mode)
        stream.write(source.read_bytes())
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)


def files(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and '.build' not in p.parts}


def production_containers():
    ids = run(['docker', 'ps', '-aq']).split()
    values = json.loads(run(['docker', 'inspect', *ids]))
    return {v['Name']: {'id': v['Id'], 'started': v['State']['StartedAt'], 'status': v['State']['Status']}
            for v in values if v['Name'].lstrip('/') in ('sealskin', 'profile-relay-personal') or v['Name'].startswith(('/bp-home-', '/bp-guard-', '/bp-relay-'))}


def spool_files(spool):
    return {str(p.relative_to(spool)): sha(p) for directory in ('queue', 'status', 'templates', 'fingerprint-cache', 'artifacts')
            for p in sorted((spool / directory).rglob('*')) if p.is_file()}


def idle(spool):
    for request in (spool / 'queue').glob('job-*.json'):
        status = spool / 'status' / request.name
        assert status.exists() and read(status).get('status') in ('accepted', 'failed'), 'JOB_RUNNER_NOT_IDLE'


def ready(cfg):
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request('http://' + cfg['listen_address'] + '/readyz', headers={'Host': urlsplit(cfg['public_base_url']).netloc})
            with urllib.request.urlopen(req, timeout=3) as r:
                if r.status == 200:
                    return
        except OSError:
            pass
        time.sleep(.4)
    raise RuntimeError('ADAPTER_NOT_READY')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--apply', action='store_true')
    a = p.parse_args()
    os.umask(0o077)
    root = a.root.resolve()
    assert root.name == 'r6q-engine-neutral-20261001' and 'runtime' in root.parts
    config = PROJECT / 'infra/sealskin/adapter-config.json'
    cfg = read(config)
    def path(value):
        q = Path(value)
        return q if q.is_absolute() else config.parent / q
    spool = path(cfg['environment_job_spool'])
    protected = [config, path(cfg['profile_directory']), path(cfg['environment_catalog']), path(cfg['template_catalog']), path(cfg['access']['users_file'])]
    if cfg.get('network_profile_catalog'):
        protected.append(path(cfg['network_profile_catalog']))
    final_source = root / 'final-adapter-source'
    runner_source = root / 'final-runner-source'
    assert files(final_source) == read(root / 'final-adapter-manifest.json')
    assert files(runner_source) == read(root / 'final-runner-manifest.json')
    candidate = root / 'final-profile-adapter'
    target_unit = root / 'final-environment-job.service'
    if not a.apply:
        assert not (root / 'deployment-inputs.json').exists()
        assert sha(BINARY) == read(PROJECT / 'infra/sealskin/runtime/r6p-templates-20261001/deployment.json')['adapter_sha256']
        idle(spool)
        # Preserve the old service hardening/settings and explicit addon path.
        original = UNIT.read_text()
        old_args = shlex.split(next(line[10:] for line in original.splitlines() if line.startswith('ExecStart=')))
        addon = old_args[old_args.index('--clipboard-addon') + 1]
        if addon.startswith('%h/'):
            addon = str(Path.home() / addon[3:])
        image = read(root / 'integration-final/environment-catalog.json')['artifacts'][0]['image']
        assert image == 'sha256:9a128663eb05d1b7a64a9519b597b745ba2b9be76af7b6649755a2a50d168306'
        origin = cfg['sealskin']['public_session_base_url']
        parsed = urlsplit(origin)
        assert parsed.scheme == 'https' and parsed.hostname and not parsed.query and not parsed.username
        args = ['/usr/bin/python3', str(runner_source / 'infra/camoufox/environment-job.py'), 'run', '--spool', str(spool),
                '--catalog', str(path(cfg['environment_catalog'])), '--template-catalog', str(path(cfg['template_catalog'])),
                '--browser-template-id', 'camoufox-linux-v152', '--image', image, '--session-origin', origin,
                '--username', cfg['sealskin']['username'], '--clipboard-addon', addon, '--watch', '10']
        # These pinned deployment paths contain no systemd specifiers/whitespace.
        assert all(not any(c in value for c in '%\n\r\t ') for value in args)
        lines = [('ExecStart=' + ' '.join(args)) if line.startswith('ExecStart=') else
                 ('WorkingDirectory=' + str(runner_source / 'infra/camoufox')) if line.startswith('WorkingDirectory=') else line
                 for line in original.splitlines()]
        target_unit.write_text('\n'.join(lines) + '\n')
        write(root / 'deployment-inputs.json', {'files': {str(q): sha(q) for q in protected + [BINARY, UNIT]},
              'spool': spool_files(spool), 'candidate_sha256': sha(candidate), 'unit_sha256': sha(target_unit), 'image': image})
        print('PREPARED minimal Adapter and idle runner release; no production changes')
        return
    assert not (root / 'deployment.json').exists()
    for name in ('desktop-final/result.json', 'publication-recovery/result.json', 'ui-final/result.json'):
        assert read(root / name)['result'] == 'PASS', name
    entries = read(root / 'integration-final/environment-catalog.json')['artifacts']
    assert len(entries) == 2
    for entry in entries:
        app = entry['application']['provider_config']
        report_path = Path(next(m['Source'] for m in app['docker_overrides']['mounts'] if m['Target'].endswith('/acceptance.json')))
        report = read(report_path)
        assert report['status'] == 'pass' and report['phase'] == 'all' and report['results']['homeReplay']['recreationsPerHome'] >= 10
    expected = read(root / 'deployment-inputs.json')
    assert sha(candidate) == expected['candidate_sha256'] and sha(target_unit) == expected['unit_sha256']
    for name, digest in expected['files'].items():
        assert sha(Path(name)) == digest, 'DEPLOYMENT_INPUT_CHANGED'
    assert spool_files(spool) == expected['spool']
    idle(spool)
    before = production_containers()
    backup = root / 'deployment-backup'
    backup.mkdir(mode=0o700)
    shutil.copy2(BINARY, backup / BINARY.name)
    shutil.copy2(UNIT, backup / UNIT.name)
    write(root / 'deployment-before.json', {'containers': before, 'protected': {str(q): sha(q) for q in protected}})
    stopped = False
    changed = False
    try:
        run(['systemctl', '--user', 'stop', SERVICE])
        stopped = True
        idle(spool)
        assert spool_files(spool) == expected['spool']
        replace(candidate, BINARY, 0o755)
        changed = True
        replace(target_unit, UNIT, 0o644)
        run(['systemctl', '--user', 'daemon-reload'])
        run(['systemctl', '--user', 'restart', 'profile-adapter.service'])
        ready(cfg)
        run(['systemctl', '--user', 'start', SERVICE])
        stopped = False
        time.sleep(2)
        assert run(['systemctl', '--user', 'is-active', SERVICE]).strip() == 'active'
        assert production_containers() == before
        assert all(sha(q) == expected['files'][str(q)] for q in protected)
        assert spool_files(spool) == expected['spool']
    except BaseException:
        # Never downgrade an Adapter underneath a new queue/record or overwrite
        # independent maintenance. Keep the failure and reconcile if drifted.
        safe = all(sha(q) == expected['files'][str(q)] for q in protected) and spool_files(spool) == expected['spool']
        if changed and safe and sha(BINARY) == sha(candidate) and sha(UNIT) in (sha(target_unit), sha(backup / UNIT.name)):
            run(['systemctl', '--user', 'stop', SERVICE])
            replace(backup / BINARY.name, BINARY, 0o755)
            replace(backup / UNIT.name, UNIT, 0o644)
            run(['systemctl', '--user', 'daemon-reload'])
            run(['systemctl', '--user', 'restart', 'profile-adapter.service'])
            stopped = True
        elif changed:
            write(root / 'rollback-held.json', {'reason': 'input changed; preserve new jobs/config and reconcile'})
        if stopped:
            run(['systemctl', '--user', 'start', SERVICE])
        raise
    write(root / 'deployment.json', {'result': 'PASS', 'adapter_sha256': sha(BINARY), 'runner_image': expected['image'],
          'runner_manifest_sha256': sha(root / 'final-runner-manifest.json'), 'containers_preserved': True,
          'profiles_accounts_catalogs_preserved': True, 'old_spool_files_preserved': True,
          'scope': 'Adapter and idle job-runner only; no Worker or Home rebuild'})
    print('PASS R6Q deployed; existing containers, bindings, catalogs, accounts and job evidence preserved')


if __name__ == '__main__':
    main()
