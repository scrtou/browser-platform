#!/usr/bin/env python3
"""Check real QA HTTP admission with the candidate Adapter and real Workers."""
import argparse
import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import threading

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('lifecycle', HERE / 'check-lifecycle-live.py')
lifecycle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lifecycle)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    qa = args.root.resolve()
    drill = lifecycle.Drill(qa)
    assert not drill.qa_adapter_pids()
    config_path = qa / 'adapter-config.json'
    config = json.loads(config_path.read_text())
    requests = json.loads((qa.parent / 'dynamic/requests.json').read_text())
    for profile in config['profiles']:
        suffix = profile['id'][-1]
        profile['network_policy_sha256'] = requests[suffix]['network_policy_sha256']
    config['limits'] = {'max_active_profiles': 1, 'max_concurrent_launches': 1,
                        'min_free_disk_mib': 10**9, 'storage_path': str(qa / 'storage')}
    lifecycle.mod.write_json(config_path, config)
    out = qa.parent / 'admission'
    out.mkdir(mode=0o700)
    results = []
    def binding(profile):
        return drill.binding(profile) if (qa / 'adapter-state.json').exists() else None
    def stop_adapter():
        pids = drill.qa_adapter_pids()
        assert len(pids) == 1
        pid = pids[0]
        os.kill(pid, 15)
        lifecycle.mod.wait(lambda: not drill.qa_adapter_pids(), 'normal QA Adapter exit', seconds=20)
        record = qa / 'adapter-pid.json'
        assert json.loads(record.read_text())['pid'] == pid
        lifecycle.mod.write_json(out / ('adapter-exited-' + str(pid) + '.json'), {'pid': pid, 'owned_adapter_exited': True})
        record.unlink()
    try:
        drill.start_adapter(seconds=40)
        for suffix in ('a', 'b'):
            status, _, body = drill.start('network-qa-' + suffix)
            assert status == 503 and b'Capacity limit reached' in body
            assert binding('network-qa-' + suffix) is None
        results.append('disk_refused_without_binding')
        stop_adapter()
        config['limits']['min_free_disk_mib'] = 1024
        lifecycle.mod.write_json(config_path, config)
        drill.start_adapter(seconds=40)
        barrier = threading.Barrier(2)
        def launch(suffix):
            barrier.wait()
            status, _, _ = drill.start('network-qa-' + suffix)
            return suffix, status
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            replies = dict(pool.map(launch, ('a', 'b')))
        assert sorted(replies.values()) == [303, 503], replies
        winner = next(s for s, status in replies.items() if status == 303)
        loser = next(s for s, status in replies.items() if status == 503)
        assert binding('network-qa-' + loser) is None
        before = drill.snapshot('network-qa-home-' + winner)
        assert len(before['workers']) == 1
        assert drill.start('network-qa-' + winner)[0] == 303
        assert drill.snapshot('network-qa-home-' + winner)['workers'] == before['workers']
        results.append('simultaneous_http_one_admitted_one_503_existing_reused')
        assert drill.control('network-qa-' + winner, 'stop')[0] == 200
        assert drill.start('network-qa-' + loser)[0] == 303
        results.append('verified_stop_releases_capacity')
    finally:
        if drill.qa_adapter_pids():
            for suffix in ('a', 'b'):
                snapshot = drill.snapshot('network-qa-home-' + suffix)
                if snapshot['records'] or snapshot['workers'] or snapshot['resources']:
                    assert drill.control('network-qa-' + suffix, 'stop')[0] == 200
            stop_adapter()
    lifecycle.mod.write_json(out / 'summary.json', {'result': 'PASS', 'checks': results})
    print('PASS real HTTP capacity admission, reuse and release')


if __name__ == '__main__':
    main()
