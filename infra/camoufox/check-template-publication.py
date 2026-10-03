#!/usr/bin/env python3
"""Resume two interrupted publications using copied, truly accepted QA artifacts."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--integration', type=Path, required=True)
    p.add_argument('--runner', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    root = a.output.resolve()
    assert 'runtime' in root.parts and any(name in root.parts for name in ('r6p-templates-20261001','r6q-engine-neutral-20261001'))
    root.mkdir(mode=0o700)
    sys.path.insert(0, str(a.runner.resolve().parent))
    spec = importlib.util.spec_from_file_location('r6p_runner', a.runner)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    original = a.integration.resolve()
    accepted = sorted((original / 'jobs/status').glob('*.json'))
    accepted = [f for f in accepted if json.loads(f.read_bytes())['status'] == 'accepted']
    request = json.loads((original / 'jobs/queue' / accepted[0].name).read_bytes())
    env_id = request['spec']['id']
    image = json.loads((original / 'jobs/artifacts' / env_id / 'environment.json').read_bytes())['runtimeImageDigest']
    results = []
    for case in ['interrupt', 'failed-publish']:
        out = root / case
        out.mkdir(mode=0o700)
        spool = runner.Spool(out / 'jobs')
        for directory in ['templates', 'fingerprint-cache']:
            shutil.copytree(original / 'jobs' / directory, spool.root / directory)
        shutil.copytree(original / 'jobs/artifacts' / env_id, spool.root / 'artifacts' / env_id)
        shutil.copy2(original / 'jobs/queue' / accepted[0].name, spool.root / 'queue' / accepted[0].name)
        catalog = json.loads((original / 'template-catalog.json').read_bytes())
        catalog['display_templates'], catalog['compatibility'] = [], []
        runner.write_private(out / 'template-catalog.json', runner.encode(catalog))
        args = SimpleNamespace(image=image, recreations=10, min_free_mib=2048, catalog=out / 'environment-catalog.json',
                               template_catalog=out / 'template-catalog.json', session_origin='https://entry.r6p.test',
                               username='r6p-qa', clipboard_addon=None, store='SealSkin Apps', template='Default',
                               browser_template_id='camoufox-linux-v152', verify_in_image=True)
        paths = list((spool.root / 'artifacts' / env_id).glob('*.json'))
        before = {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in paths}
        error = KeyboardInterrupt if case == 'interrupt' else OSError('simulated publication interruption')
        with patch.object(runner, 'publish_compatibility', side_effect=error):
            if case == 'interrupt':
                try:
                    runner.run_next(spool, args, runner.load_prepare())
                except KeyboardInterrupt:
                    pass
                else:
                    raise AssertionError('interruption not injected')
            else:
                assert runner.run_next(spool, args, runner.load_prepare()) == 'failed'
        partial = args.catalog.read_bytes()
        assert not json.loads(args.template_catalog.read_bytes())['compatibility']
        cmd = [sys.executable, str(a.runner.resolve()), 'run', '--spool', str(spool.root), '--catalog', str(args.catalog),
               '--template-catalog', str(args.template_catalog), '--browser-template-id', args.browser_template_id,
               '--image', image, '--session-origin', args.session_origin, '--username', args.username]
        if case == 'failed-publish':
            cmd += ['--retry-job', request['job_id']]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        (out / 'resume.log').write_text(result.stdout + result.stderr)
        assert result.returncode == 0 and spool.status(request['job_id'])['status'] == 'accepted'
        assert args.catalog.read_bytes() == partial
        assert {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in paths} == before
        assert len(json.loads(args.template_catalog.read_bytes())['compatibility']) == 1
        results.append({'case': case, 'result': 'PASS', 'artifact_report_bytes_preserved': True, 'image_verify': True})
    runner.write_private(root / 'result.json', runner.encode({'result': 'PASS', 'cases': results}))
    print('PASS interrupted and explicit failed-publication recovery with real accepted artifacts and image verify')


if __name__ == '__main__':
    main()
