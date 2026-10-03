#!/usr/bin/env python3
"""Private, read-only health monitoring. Never forwards backend text or URLs."""
import argparse
import datetime
import fcntl
import http.client
import json
import os
from pathlib import Path
import re
import socket
import stat
import tempfile
import time

MAX_FILE = 2 * 1024 * 1024


def read_private(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('PRIVATE_FILE_REQUIRED')
        raw = stream.read(MAX_FILE + 1)
        if len(raw) > MAX_FILE:
            raise ValueError('FILE_TOO_LARGE')
        return json.loads(raw)


def write_private(path, value):
    raw = (json.dumps(value, ensure_ascii=True, separators=(',', ':')) + '\n').encode()
    if len(raw) > MAX_FILE:
        raise ValueError('FILE_TOO_LARGE')
    fd, temporary = tempfile.mkstemp(prefix='.monitor-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class UnixHTTP(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__('localhost', timeout=5)
        self.path = path

    def connect(self):
        info = os.stat(self.path, follow_symlinks=False)
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('PRIVATE_SOCKET_REQUIRED')
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


def observe_profile(socket_path, profile, now):
    connection = UnixHTTP(socket_path)
    try:
        connection.request('GET', '/profiles/' + profile + '/health?cached=1')
        response = connection.getresponse()
        data = response.read(MAX_FILE + 1)
        if response.status != 200 or len(data) > MAX_FILE:
            return 'unavailable'
        report = json.loads(data)['health']
        expires = datetime.datetime.fromisoformat(report['expires_at'].replace('Z', '+00:00'))
        if report.get('stale') is not False or expires.timestamp() <= now:
            return 'stale'
        overall = report['overall']
        if overall == 'healthy':
            return overall
        if report.get('binding', {}).get('status') == 'stopped' and all(report.get('runtime', {}).get(k) == 0 for k in ('workers', 'records', 'resources')):
            return 'stopped'
        return 'unhealthy'
    except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException):
        return 'unavailable'
    finally:
        connection.close()


def resources(storage):
    memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    vfs = os.statvfs(storage)
    return {'available_memory_mib': int(memory['MemAvailable'].split()[0]) // 1024,
            'available_disk_mib': vfs.f_bavail * vfs.f_frsize // 1024**2}


def validate(config):
    if set(config) != {'socket', 'profiles', 'storage_path', 'state_directory', 'memory_min_mib',
                       'disk_min_mib', 'failure_samples', 'recovery_samples', 'retention_days', 'max_events'}:
        raise ValueError('CONFIG_FIELDS')
    profiles = config['profiles']
    if not isinstance(profiles, list) or not 1 <= len(profiles) <= 64 or len(set(profiles)) != len(profiles):
        raise ValueError('CONFIG_PROFILES')
    if not all(isinstance(p, str) and re.fullmatch('[a-z0-9][a-z0-9_-]{0,63}', p) for p in profiles):
        raise ValueError('CONFIG_PROFILE_ID')
    for key, maximum in [('memory_min_mib', 2**30), ('disk_min_mib', 2**40), ('failure_samples', 60),
                         ('recovery_samples', 60), ('retention_days', 365), ('max_events', 2000)]:
        if type(config[key]) is not int or not 1 <= config[key] <= maximum:
            raise ValueError('CONFIG_NUMBER')
    for key in ('socket', 'storage_path', 'state_directory'):
        if not isinstance(config[key], str) or not Path(config[key]).is_absolute():
            raise ValueError('CONFIG_PATH')
    return config


def advance(previous, signals, now, config):
    """One bounded durable document commits counters, transitions and retention."""
    states, events = {}, []
    if previous:
        if previous.get('version') != 1 or not isinstance(previous.get('signals'), dict) or not isinstance(previous.get('events'), list):
            raise ValueError('STATE_INVALID')
        events = [e for e in previous['events'] if isinstance(e, dict) and set(e) == {'at', 'signal', 'transition'}
                  and isinstance(e['at'], (int, float)) and now - config['retention_days'] * 86400 <= e['at'] <= now
                  and e['signal'] in signals and e['transition'] in ('firing', 'resolved')]
    for name, failed in signals.items():
        old = (previous or {}).get('signals', {}).get(name, {})
        active = old.get('active') is True
        old_count = old.get('count', 0)
        if type(old_count) is not int or not 0 <= old_count <= 60:
            raise ValueError('STATE_COUNT_INVALID')
        count = min(old_count + 1, 60) if old.get('failed') is failed else 1
        if failed and not active and count >= config['failure_samples']:
            active = True
            events.append({'at': now, 'signal': name, 'transition': 'firing'})
        elif not failed and active and count >= config['recovery_samples']:
            active = False
            events.append({'at': now, 'signal': name, 'transition': 'resolved'})
        states[name] = {'failed': failed, 'count': count, 'active': active}
    return {'version': 1, 'at': now, 'signals': states, 'events': events[-config['max_events']:]}


def run(config, now=None, observer=observe_profile, resource_reader=resources):
    validate(config)
    directory = Path(config['state_directory'])
    directory.mkdir(mode=0o700, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or directory.resolve() != directory:
        raise ValueError('PRIVATE_DIRECTORY_REQUIRED')
    fd = os.open(directory / 'monitor.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        info = os.fstat(lock.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('PRIVATE_LOCK_REQUIRED')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        now = time.time() if now is None else now
        path = directory / 'status.json'
        previous = read_private(path) if path.exists() else None
        profile_states = {p: observer(config['socket'], p, now) for p in config['profiles']}
        signals = {'profile:' + p: value not in ('healthy', 'stopped', 'dormant') for p, value in profile_states.items()}
        try:
            resource = resource_reader(config['storage_path'])
            for field in ('available_memory_mib', 'available_disk_mib'):
                if type(resource[field]) is not int or resource[field] < 0:
                    raise ValueError('RESOURCE_INVALID')
            signals['memory_low'] = resource['available_memory_mib'] < config['memory_min_mib']
            signals['disk_low'] = resource['available_disk_mib'] < config['disk_min_mib']
            signals['resource_unavailable'] = False
        except (OSError, ValueError, KeyError, TypeError):
            resource = {}
            signals.update(memory_low=False, disk_low=False, resource_unavailable=True)
            # Unknown resource readings must not resolve an existing low-resource alert.
            for key in ('memory_low', 'disk_low'):
                signals[key] = (previous or {}).get('signals', {}).get(key, {}).get('active') is True
        status = advance(previous, signals, now, config)
        status.update(profiles=profile_states, resources=resource)
        write_private(path, status)
        return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        status = run(read_private(args.config))
        print(json.dumps({'result': 'OK', 'active_alerts': sum(v['active'] for v in status['signals'].values())}))
    except Exception:
        # Backend errors and paths can contain secrets. Never interpolate them.
        print('{"result":"ERROR","code":"MONITOR_FAILED"}')
        raise SystemExit(1)


if __name__ == '__main__':
    main()
