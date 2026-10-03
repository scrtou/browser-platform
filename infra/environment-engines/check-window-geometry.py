#!/usr/bin/env python3
"""Replay a preserved specification in new isolated QA resources, never in place."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifact', type=Path, required=True)
    p.add_argument('--image', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--recreations', type=int, default=10)
    p.add_argument('--client-browsers', type=Path)
    a = p.parse_args()
    os.umask(0o077)
    root = a.output.resolve()
    assert 'runtime' in root.parts
    root.mkdir(mode=0o700)
    spec = json.loads(a.artifact.read_bytes())
    spec['runtimeImageDigest'] = a.image
    (root/'environment.json').write_text(json.dumps(spec, indent=2)+'\n')
    sys.path.insert(0, str(PROJECT/'infra/camoufox'))
    source = importlib.util.spec_from_file_location('geometry_runner', PROJECT/'infra/camoufox/environment-job.py')
    runner = importlib.util.module_from_spec(source)
    source.loader.exec_module(runner)
    with runner.Fixture('job-'+uuid.uuid4().hex[:16], a.image) as fixture:
        cmd = [sys.executable, str(HERE/'acceptance.py'), '--artifact', str(root/'environment.json'),
               '--network', fixture.networks['internal'], '--output', str(root/'acceptance.json'),
               '--recreations', str(a.recreations)]
        if a.client_browsers:
            cmd += ['--client-browsers', str(a.client_browsers.resolve())]
        with (root/'run.log').open('w') as log:
            result = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
    print('geometry replay exit', result.returncode)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
