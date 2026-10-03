#!/usr/bin/env python3
"""Use the reviewed X11 close protocol with exact Chromix process identities."""
import fcntl
import importlib.util
import os
from pathlib import Path

spec=importlib.util.spec_from_file_location('x11_shutdown',Path(__file__).with_name('x11_shutdown.py'))
x11=importlib.util.module_from_spec(spec);spec.loader.exec_module(x11)


def browsers():
    active,launching={},False
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            if path.stat().st_uid != os.getuid():
                continue
            args=(path/'cmdline').read_bytes().split(b'\0')
            if b'/usr/local/lib/browser-platform/chromix-launcher.py' in args and b'launch' in args:
                launching=True
            if (path/'comm').read_text().strip() != 'chrome':
                continue
            if any(a.startswith(b'--type=') for a in args):
                continue
            if os.readlink(path/'exe') != '/opt/chromix/chrome':
                raise RuntimeError('BROWSER_IDENTITY_UNCONFIRMED')
            status=(path/'stat').read_text().rsplit(')',1)[1].split()
            if status[0] not in {'Z','X'}:
                active[int(path.name)]=status[19]
        except (FileNotFoundError,ProcessLookupError):
            continue
    return active,launching


def home_released():
    try:
        descriptor=os.open('/config/.chromix/worker.lock',os.O_RDWR|os.O_NOFOLLOW)
    except FileNotFoundError:
        return True
    try:
        fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        return False
    finally:
        os.close(descriptor)


x11.browsers=browsers
x11.home_released=home_released
if __name__ == '__main__':
    if os.environ.get('PIXELFLUX_WAYLAND','false').lower() != 'false':
        raise SystemExit('CHROMIX_X11_REQUIRED')
    raise SystemExit(x11.main())
