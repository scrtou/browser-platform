#!/usr/bin/env python3
"""Observe real creation-time logging for one isolated QA generation."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import subprocess
import threading
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('dynamic', HERE / 'check-dynamic-upstream.py')
dynamic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dynamic)
EXPECTED = {'Type': 'json-file', 'Config': {'max-size': '10m', 'max-file': '3', 'compress': 'true'}}


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    check = dynamic.Check(args.root)
    out = check.qa.parent / 'logging'
    out.mkdir(mode=0o700)
    scope = hashlib.sha256(str(check.qa / 'config/.config/sealskin/sessions.yml').encode()).hexdigest()
    # --since covers creation even if the events client subscribes late.
    since = str(int(time.time()))
    observations, failures = [], []
    event_errors = (out / 'events-stderr.log').open('wb')
    process = subprocess.Popen(['docker', 'events', '--since', since, '--filter', 'type=container',
        '--filter', 'event=create', '--filter', 'label=io.browser-platform.scope=' + scope,
        '--format', '{{.Actor.ID}}'], stdout=subprocess.PIPE, stderr=event_errors, bufsize=0)
    done = threading.Event()
    def collect():
        while not done.is_set():
            if not select.select([process.stdout], [], [], 1)[0]:
                continue
            identifier = process.stdout.readline().decode("ascii").strip()
            if not identifier:
                break
            try:
                value = json.loads(dynamic.network.docker('inspect', identifier).stdout)[0]
                labels = value['Config']['Labels']
                assert labels.get('io.browser-platform.scope') == scope
                observations.append({'id': identifier, 'role': labels.get('io.browser-platform.role', 'worker'),
                                     'logging': value['HostConfig']['LogConfig']})
            except Exception as exc:
                failures.append(type(exc).__name__)
    thread = threading.Thread(target=collect)
    thread.start()
    passed = False
    try:
        check.launch('a')
        check.flow('a', 'A').close()
        check.bypass('a')
        dynamic.network.wait(lambda: len(observations) >= 4 or failures, 'creation log observations', seconds=10)
        assert process.poll() is None, 'Docker event stream exited; see private stderr'
        assert not failures, 'Could not inspect a QA creation before removal'
        assert {row['role'] for row in observations} == {'relay', 'guard', 'probe', 'worker'}
        assert all(row['logging'] == EXPECTED for row in observations)
        passed = True
    finally:
        done.set()
        process.terminate()
        process.wait(timeout=5)
        thread.join(timeout=5)
        event_errors.close()
        dynamic.write(out / 'created.json', observations)
        dynamic.write(out / 'observer-errors.json', failures)
        check.stop_all()
        dynamic.write(out / 'summary.json', {'result': 'PASS' if passed else 'FAIL', 'roles': [v['role'] for v in observations],
                                            'generations_and_fixtures_removed': True})
    print('PASS actual Worker/Relay/Guard/probe logging and lifecycle cleanup')


if __name__ == '__main__':
    main()
