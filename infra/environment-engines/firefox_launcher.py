#!/usr/bin/env python3
"""Launch the fixed native Firefox with an isolated persistent profile."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit
from native_artifact import decode,verify,require

BROWSER=Path('/usr/lib/firefox/firefox')

def arguments(spec,directory,url):
    target=urlsplit(url)
    require(url=='about:blank' or target.scheme in ('https','http') and target.hostname and not target.username and not target.password,'FIREFOX_URL_INVALID')
    return [str(BROWSER),'--no-remote','--profile',str(directory/'profile'),'--width',str(spec['window']['width']),'--height',str(spec['window']['height']),url]

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['verify','launch']);p.add_argument('url',nargs='?',default='about:blank');a=p.parse_args()
    try:
        raw=Path('/run/browser-platform/environment.json').read_bytes();spec=decode(raw);verify(spec,'firefox',raw,os.environ)
        lock=decode(Path('/usr/local/lib/browser-platform/firefox-lock.json').read_bytes())
        for name,digest in lock['files'].items():
            with Path(name).open('rb') as f:require(hashlib.file_digest(f,'sha256').hexdigest()==digest,'FIREFOX_BINARY_DRIFT')
        if a.action=='verify':
            if spec['schemaVersion']=='browser-platform/firefox-environment/v3' and os.getuid()==0:
                from display_config import configure
                configure('firefox',spec['screen'].get('mode')=='auto')
            print('FIREFOX_ENVIRONMENT_VERIFIED');return 0
        require(os.getuid()!=0,'FIREFOX_USER_INVALID')
        home=Path('/config');directory=home/'.firefox';directory.mkdir(mode=0o700,exist_ok=True)
        require(not directory.is_symlink() and directory.stat().st_uid==os.getuid() and directory.stat().st_mode&0o077==0,'FIREFOX_HOME_INVALID')
        fd=os.open(directory/'worker.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            profile=directory/'profile';profile.mkdir(mode=0o700,exist_ok=True)
            require(not profile.is_symlink(),'FIREFOX_HOME_INVALID')
            return subprocess.run(arguments(spec,directory,a.url),env=dict(os.environ,HOME='/config',MOZ_ENABLE_WAYLAND='0')).returncode
        finally:os.close(fd)
    except (ValueError,OSError,KeyError,TypeError) as e:
        print(str(e) if isinstance(e,ValueError) else 'FIREFOX_START_REJECTED',file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
