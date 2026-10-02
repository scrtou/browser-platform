#!/usr/bin/env python3
"""Authenticated stopped-business snapshots from explicit private path plans.

The caller owns quiescence and records it in checkpoint.json. This tool never
stops services, activates identities, overwrites an existing restore, or follows
archived symlinks. Decryption completes in tmpfs before extraction begins.
"""
import argparse
import hashlib
import gzip
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile

FORMAT = 'browser-platform/consistent-business-backup/v1'


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def safe_name(name):
    p = PurePosixPath(name)
    require(name and not p.is_absolute() and '..' not in p.parts and str(p) == name
            and name != '.' and not any(c in name for c in '\n\r\0'), 'unsafe archive name')
    return p


def inventory(plan):
    entries, paths, excluded = {}, {}, {}
    for prefix, value in sorted(plan.items()):
        safe_name(prefix)
        root = Path(value)
        require(root.is_absolute() and root.resolve() == root and not root.is_symlink(), 'unsafe source root')
        nodes = [root]
        if root.is_dir():
            for parent, directories, files in os.walk(root, followlinks=False):
                nodes.extend(Path(parent) / name for name in sorted(directories + files))
        for node in nodes:
            suffix = node.relative_to(root).as_posix()
            name = prefix if suffix == '.' else prefix + '/' + suffix
            safe_name(name)
            require(name not in entries and name not in excluded, 'duplicate archive entry')
            before = node.lstat()
            if stat.S_ISSOCK(before.st_mode) and re.fullmatch(r'storage/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+/\.XDG/wayland-[0-9]{1,10}', name):
                excluded[name] = 'stopped-wayland-runtime-socket'
                continue
            row = {'mode': stat.S_IMODE(before.st_mode), 'uid': before.st_uid, 'gid': before.st_gid}
            if stat.S_ISREG(before.st_mode):
                row.update(kind='file', size=before.st_size, sha256=digest(node))
                after = node.stat()
                require((before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns), 'source changed while hashing')
            elif stat.S_ISDIR(before.st_mode):
                row['kind'] = 'directory'
            elif stat.S_ISLNK(before.st_mode):
                # The full job spool includes stopped native QA Homes, whose
                # font caches use links. Preserve their text without following.
                require(prefix in {'storage', 'jobs'} or prefix.startswith('assets/'), 'unexpected source symlink')
                row.update(kind='symlink', target=os.readlink(node))
            else:
                raise ValueError('unsupported special source node')
            entries[name], paths[name] = row, node
    return entries, paths, excluded


def create(args):
    plan = json.loads(args.plan.read_text())
    checkpoint = json.loads(args.checkpoint.read_text())
    require(checkpoint.get('result') == 'QUIESCED' and checkpoint.get('all_profiles_stopped') is True
            and checkpoint.get('writers_stopped') is True, 'quiescent checkpoint required')
    require(args.output.parent.is_dir() and args.output.parent.stat().st_mode & 0o077 == 0
            and not os.path.lexists(args.output) and not os.path.lexists(args.receipt)
            and args.receipt.parent.is_dir() and args.receipt.parent.stat().st_mode & 0o077 == 0,
            'new private output and receipt required')
    entries, paths, excluded = inventory(plan)
    require('MANIFEST.json' not in entries, 'reserved manifest name')
    manifest = {'format': FORMAT, 'checkpoint': checkpoint, 'entries': entries, 'excluded_runtime_nodes': excluded}
    raw = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    tmp = args.output.with_name(args.output.name + '.partial')
    with tmp.open('xb') as output, tempfile.TemporaryFile() as errors:
        p = subprocess.Popen([str(args.age), '-r', args.recipient], stdin=subprocess.PIPE, stdout=output, stderr=errors)
        try:
            with gzip.GzipFile(fileobj=p.stdin, mode='wb', compresslevel=1, mtime=0) as zipped, tarfile.open(fileobj=zipped, mode='w|', format=tarfile.PAX_FORMAT) as archive:
                for name, row in entries.items():
                    info = tarfile.TarInfo(name)
                    info.mode, info.uid, info.gid = row['mode'], row['uid'], row['gid']
                    if row['kind'] == 'directory':
                        info.type = tarfile.DIRTYPE
                    elif row['kind'] == 'symlink':
                        info.type, info.linkname = tarfile.SYMTYPE, row['target']
                    else:
                        info.size = row['size']
                    if row['kind'] == 'file':
                        with paths[name].open('rb') as source:
                            archive.addfile(info, source)
                    else:
                        archive.addfile(info)
                info = tarfile.TarInfo('MANIFEST.json'); info.size = len(raw); info.mode = 0o600
                archive.addfile(info, io.BytesIO(raw))
            p.stdin.close()
            require(p.wait() == 0, 'age encryption failed')
            output.flush(); os.fsync(output.fileno())
        except BaseException:
            p.kill(); p.wait()
            raise
    after, _, after_excluded = inventory(plan)
    require(after == entries and after_excluded == excluded, 'source changed during capture; partial retained')
    os.replace(tmp, args.output)
    receipt = {'result': 'PASS', 'format': FORMAT, 'archive_sha256': digest(args.output),
               'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'archive_bytes': args.output.stat().st_size,
               'entries': len(entries), 'file_bytes': sum(v.get('size', 0) for v in entries.values()),
               'excluded_runtime_nodes': excluded, 'checkpoint': checkpoint}
    args.receipt.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({k: receipt[k] for k in ['result', 'entries', 'archive_bytes', 'archive_sha256']}))


def authenticated_archive(args, target=None):
    require(args.scratch_root.resolve().is_relative_to('/dev/shm'), 'tmpfs scratch required')
    require(args.archive.is_file() and not args.archive.is_symlink(), 'regular archive required')
    receipt = json.loads(args.receipt.read_text())
    require(digest(args.archive) == receipt['archive_sha256'], 'archive checksum mismatch')
    if target is not None:
        require(not os.path.lexists(target) and target.parent.resolve() == target.parent, 'fresh restore path required')
    with tempfile.TemporaryDirectory(prefix='business-backup-', dir=args.scratch_root) as scratch:
        compressed = Path(scratch) / 'authenticated.tar.gz'
        with compressed.open('xb') as output:
            p = subprocess.run([str(args.age), '-d', '-i', str(args.identity), str(args.archive)], stdout=output, stderr=subprocess.PIPE)
        require(p.returncode == 0, 'age authentication failed')
        with tarfile.open(compressed, 'r:gz') as archive:
            members = archive.getmembers()
            names = [m.name for m in members]
            require(len(set(names)) == len(names) and 'MANIFEST.json' in names, 'duplicate/missing manifest')
            for member in members:
                safe_name(member.name)
                require(member.isfile() or member.isdir() or member.issym(), 'unsafe archive type')
            manifest_member = archive.getmember('MANIFEST.json')
            require(manifest_member.isfile() and manifest_member.size <= 64 * 1024 * 1024, 'invalid manifest')
            raw = archive.extractfile(manifest_member).read()
            require(hashlib.sha256(raw).hexdigest() == receipt['manifest_sha256'], 'manifest pin mismatch')
            manifest = json.loads(raw)
            require(manifest['format'] == FORMAT and manifest['checkpoint'] == receipt['checkpoint'], 'checkpoint mismatch')
            expected = manifest['entries']
            require(set(names) == set(expected) | {'MANIFEST.json'}, 'archive file-set mismatch')
            by_name = {m.name: m for m in members}
            for name, row in expected.items():
                path = safe_name(name); member = by_name[name]
                for parent in path.parents:
                    if str(parent) in expected:
                        require(expected[str(parent)]['kind'] == 'directory', 'archive symlink ancestor')
                require(member.mode == row['mode'] and member.uid == row['uid'] and member.gid == row['gid'], 'metadata mismatch')
                if row['kind'] == 'file':
                    require(member.isfile() and member.size == row['size'], 'file type/size mismatch')
                    h = hashlib.sha256()
                    with archive.extractfile(member) as stream:
                        for block in iter(lambda: stream.read(1024 * 1024), b''):
                            h.update(block)
                    require(h.hexdigest() == row['sha256'], 'file hash mismatch')
                elif row['kind'] == 'directory':
                    require(member.isdir(), 'directory mismatch')
                else:
                    require(row['kind'] == 'symlink' and member.issym() and member.linkname == row['target'], 'link mismatch')
            if target is not None:
                target.mkdir(mode=0o700)
                for name, row in expected.items():
                    dest = target / name
                    if row['kind'] == 'directory':
                        dest.mkdir(parents=True, exist_ok=True, mode=0o700)
                    elif row['kind'] == 'file':
                        dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                        with dest.open('xb') as out, archive.extractfile(by_name[name]) as source:
                            shutil.copyfileobj(source, out)
                for name, row in expected.items():
                    if row['kind'] == 'symlink':
                        dest = target / name; dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700); dest.symlink_to(row['target'])
                for name, row in sorted(expected.items(), key=lambda x: -len(PurePosixPath(x[0]).parts)):
                    dest = target / name
                    if os.getuid() == 0:
                        os.chown(dest, row['uid'], row['gid'], follow_symlinks=False)
                    if row['kind'] != 'symlink':
                        dest.chmod(row['mode'])
                (target / 'MANIFEST.json').write_bytes(raw)
                (target / 'RECOVERY_PENDING').write_text('Offline checkpoint. Review current revocations/accounts, rebind paths and isolate networking before activation.\n')
    print(json.dumps({'result': 'PASS', 'entries': len(expected), 'restored': target is not None, 'activated': False}))


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    create_parser = sub.add_parser('create')
    for key in ['plan', 'checkpoint', 'output', 'receipt', 'age']:
        create_parser.add_argument('--' + key, type=Path, required=True)
    create_parser.add_argument('--recipient', required=True)
    for name in ['verify', 'restore']:
        child = sub.add_parser(name)
        for key in ['archive', 'identity', 'receipt', 'scratch-root', 'age']:
            child.add_argument('--' + key, type=Path, required=True)
        if name == 'restore':
            child.add_argument('--target', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'create':
        create(args)
    else:
        authenticated_archive(args, getattr(args, 'target', None))


if __name__ == '__main__':
    main()
