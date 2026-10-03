#!/usr/bin/env python3
"""Bounded resource sampling of two owned QA browsers; never stress the host to OOM."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import threading
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('dynamic', HERE / 'check-dynamic-upstream.py')
dynamic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dynamic)


def host():
    memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    vfs = os.statvfs(HERE)
    return {'available_bytes': int(memory['MemAvailable'].split()[0]) * 1024,
            'total_bytes': int(memory['MemTotal'].split()[0]) * 1024,
            'swap_free_bytes': int(memory['SwapFree'].split()[0]) * 1024,
            'disk_available_bytes': vfs.f_bavail * vfs.f_frsize,
            'load': list(os.getloadavg()), 'at': time.time()}


def resources(ids):
    values = json.loads(dynamic.network.docker('inspect', *ids).stdout) if ids else []
    result = {}
    for value in values:
        pid = value['State']['Pid']
        record = {'image': value['Image'], 'started_at': value['State']['StartedAt'],
                  'oom_killed': value['State']['OOMKilled'], 'name': value['Name'],
                  'limits': {k: value['HostConfig'][k] for k in ('Memory', 'MemorySwap', 'NanoCpus', 'PidsLimit', 'ShmSize')}}
        if pid:
            rows = Path(f'/proc/{pid}/cgroup').read_text().splitlines()
            row = next(line for line in rows if line.startswith('0::'))
            root = Path('/sys/fs/cgroup') / row.split('::', 1)[1].lstrip('/')
            for name in ('memory.current', 'memory.peak', 'memory.events', 'memory.swap.current',
                         'cpu.stat', 'cpu.max', 'pids.current', 'pids.peak', 'pids.events'):
                path = root / name
                if path.exists():
                    record[name] = path.read_text().strip()
        result[value['Id']] = record
    return result


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    check = dynamic.Check(args.root)
    out = check.qa.parent / 'capacity'
    out.mkdir(mode=0o700)
    scope = hashlib.sha256(str(check.qa / 'config/.config/sealskin/sessions.yml').encode()).hexdigest()
    samples, errors = [], []
    stop = threading.Event()
    phase = ['baseline']

    def collect():
        while not stop.is_set():
            try:
                ids = dynamic.network.docker('ps', '-q', '--filter', 'label=io.browser-platform.scope=' + scope).stdout.split()
                current = host()
                samples.append({'phase': phase[0], 'host': current, 'containers': resources([check.controller_id] + ids)})
                if current['available_bytes'] < 768 * 1024**2:
                    errors.append('HOST_MEMORY_RESERVE_BELOW_768_MIB')
                    return
            except Exception as exc:
                errors.append(type(exc).__name__)
                return
            stop.wait(1)

    thread = threading.Thread(target=collect)
    thread.start()
    passed = False
    try:
        assert host()['available_bytes'] >= 1536 * 1024**2, 'Insufficient reserve for first QA browser'
        time.sleep(5)
        for suffix in ('a', 'b'):
            assert not errors
            assert host()['available_bytes'] >= 1536 * 1024**2, 'Insufficient reserve for additional QA browser'
            phase[0] = 'launch-' + suffix
            begin = time.monotonic()
            snapshot = check.launch(suffix)
            worker = snapshot['workers'][0]['instance_id']
            info = json.loads(dynamic.network.docker('inspect', worker).stdout)[0]
            limits = info['HostConfig']
            assert limits['Memory'] == 1024**3 and limits['NanoCpus'] == 10**9 and limits['PidsLimit'] == 512 and limits['ShmSize'] == 256 * 1024**2
            def browser_ready():
                names = dynamic.network.docker('top', worker, '-eo', 'pid,comm').stdout
                (out / ('processes-' + suffix + '.txt')).write_text(names)
                return any(name in names.lower() for name in ('firefox', 'camoufox'))
            dynamic.network.wait(browser_ready, 'actual browser process', seconds=45)
            dynamic.write(out / ('launch-' + suffix + '.json'), {'seconds': time.monotonic() - begin, 'worker': worker, 'limits': {k: limits[k] for k in ('Memory', 'MemorySwap', 'NanoCpus', 'PidsLimit', 'ShmSize')}})
            phase[0] = 'one-browser' if suffix == 'a' else 'two-browsers'
            flows = [check.flow(s, 'A') for s in ('a', 'b') if s <= suffix]
            for _ in range(20):
                assert not errors
                for flow in flows:
                    flow.get('A')
                time.sleep(2)
            check.close_flows()
            check.bypass(suffix)
        assert not errors
        # A final sample proves counters are readable before cleanup removes cgroups.
        phase[0] = 'final'
        time.sleep(2)
        assert not errors
        for sample in samples:
            for value in sample['containers'].values():
                assert not value['oom_killed']
                counters = dict(row.split() for row in value.get('memory.events', '').splitlines())
                assert int(counters.get('oom_kill', 0)) == 0
        passed = True
    finally:
        stop.set()
        thread.join(timeout=10)
        dynamic.write(out / 'samples.json', samples)
        dynamic.write(out / 'sampling-errors.json', errors)
        check.stop_all()
        dynamic.write(out / 'summary.json', {'result': 'PASS' if passed else 'FAIL', 'samples': len(samples),
            'scope': 'two isolated real browser startup/idle processes with bounded Worker HTTPS; no interactive video, arbitrary websites or production capacity guarantee',
            'generations_cleaned': True})
    print('PASS bounded two-browser capacity sampling')


if __name__ == '__main__':
    main()
