#!/usr/bin/env python3
"""Verify and unpack the pinned Chromix release; never execute downloaded code."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import urllib.request
import zipfile


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def extract(archive, target, lock):
    if target.exists():
        raise ValueError('CHROMIX_TARGET_EXISTS')
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if sum(m.file_size for m in members) != lock['expandedBytes']:
            raise ValueError('CHROMIX_EXPANDED_SIZE_MISMATCH')
        names = set()
        for member in members:
            path = PurePosixPath(member.filename)
            mode = member.external_attr >> 16
            if (not path.parts or path.parts[0] != 'chromix' or path.is_absolute()
                    or '..' in path.parts or '\\' in member.filename or member.filename in names
                    or stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise ValueError('CHROMIX_ARCHIVE_MEMBER_INVALID')
            names.add(member.filename)
        for name in lock['executables']:
            if name not in names:
                raise ValueError('CHROMIX_EXECUTABLE_MISSING')
        target.mkdir(mode=0o700)
        try:
            for member in members:
                path = target / member.filename
                if member.is_dir():
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.open(member) as source, path.open('xb') as dest:
                        shutil.copyfileobj(source, dest)
                    path.chmod(0o755 if (member.external_attr >> 16) & 0o111 else 0o644)
            for directory in [p for p in target.rglob('*') if p.is_dir()]:
                directory.chmod(0o755)
            for name, expected in lock['executables'].items():
                path = target / name
                if path.stat().st_size != expected['size'] or sha(path) != expected['sha256']:
                    raise ValueError('CHROMIX_EXECUTABLE_MISMATCH')
        except BaseException:
            shutil.rmtree(target)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', type=Path, default=Path(__file__).with_name('release.lock.json'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--archive', type=Path, help='existing verified archive instead of downloading')
    args = parser.parse_args()
    os.umask(0o077)
    lock = json.loads(args.lock.read_text())
    target = args.output.resolve()
    if target.exists():
        parser.error('output already exists')
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Caller budgets the retained output plus one compressed archive.
    if shutil.disk_usage(target.parent).free < lock['expandedBytes'] + lock['archiveBytes'] + 128 * 2**20:
        parser.error('insufficient staging space')
    with tempfile.TemporaryDirectory(prefix='chromix-download-', dir=target.parent) as scratch:
        archive = args.archive or Path(scratch) / 'release.zip'
        if not args.archive:
            url = lock['archiveURL']
            if not url.startswith('https://github.com/xiaozhou26/Chromix/releases/download/'):
                parser.error('unexpected download origin')
            with urllib.request.urlopen(url, timeout=60) as source, archive.open('xb') as dest:
                total = 0
                while chunk := source.read(1024 * 1024):
                    total += len(chunk)
                    if total > lock['archiveBytes']:
                        raise ValueError('CHROMIX_ARCHIVE_TOO_LARGE')
                    dest.write(chunk)
        if archive.stat().st_size != lock['archiveBytes'] or sha(archive) != lock['archiveSHA256']:
            raise ValueError('CHROMIX_ARCHIVE_MISMATCH')
        extract(archive, target, lock)
    (target / 'verified-release.json').write_text(json.dumps(lock, indent=2) + '\n')
    print(json.dumps({'result':'CHROMIX_PACKAGE_VERIFIED','version':lock['version'],'archive_sha256':lock['archiveSHA256'],'runtime_tested':False}))


if __name__ == '__main__':
    main()
