#!/usr/bin/env python3
"""Prepare the pinned two-file managed-startup delta; change no live service."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Expanded R7G1 controller source')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    lock = json.loads((here / 'managed-startup-budget.json').read_text())
    patch = here / 'managed-startup-budget.patch'
    if digest(patch) != lock['patch_sha256']:
        raise ValueError('STARTUP_PATCH_CHANGED')
    actual = subprocess.check_output(['docker', 'image', 'inspect', lock['base_tag'], '--format', '{{.Id}}'], text=True).strip()
    if actual != lock['base_image']:
        raise ValueError('STARTUP_BASE_IMAGE_CHANGED')
    for name, row in lock['files'].items():
        if digest(args.source / name) != row['before']:
            raise ValueError('STARTUP_BASE_SOURCE_CHANGED: ' + name)
    if args.output.exists() or args.output.is_symlink():
        raise ValueError('NEW_OUTPUT_REQUIRED')
    with tempfile.TemporaryDirectory(prefix='bp-managed-startup-') as temporary:
        root = Path(temporary)
        source = root / 'server'
        shutil.copytree(args.source, source, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        subprocess.run(['git', 'apply', '--check', str(patch)], cwd=root, check=True)
        subprocess.run(['git', 'apply', str(patch)], cwd=root, check=True)
        for name, row in lock['files'].items():
            if digest(source / name) != row['after']:
                raise ValueError('STARTUP_OUTPUT_CHANGED: ' + name)
        args.output.mkdir(parents=True)
        shutil.copytree(source, args.output / 'source')
        for name in lock['files']:
            target = args.output / 'payload' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / name, target)
    (args.output / 'Dockerfile').write_text(
        'FROM ' + lock['base_tag'] + '\n'
        'COPY --chmod=644 payload/app/launch.py /usr/lib/python3.14/site-packages/app/launch.py\n'
        'COPY --chmod=644 payload/app/providers/docker_provider.py /usr/lib/python3.14/site-packages/app/providers/docker_provider.py\n'
        'LABEL io.browser-platform.managed-startup-budget="1"\n')
    (args.output / 'manifest.json').write_text(json.dumps(lock, indent=2) + '\n')
    print('Prepared pinned managed-startup delta; live services unchanged')


if __name__ == '__main__':
    main()
