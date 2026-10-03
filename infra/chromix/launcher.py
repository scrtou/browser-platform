#!/usr/bin/env python3
"""Launch one pinned, managed X11 Chromix profile; reject arbitrary flags."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

BROWSER = Path('/opt/chromix/chrome')
LOCK = Path('/opt/chromix/release.lock.json')
SCHEMA = 'browser-platform/chromix-environment/v1'


def require(value, code):
    if not value:
        raise ValueError(code)


def verify_fonts(lock_path=Path('/opt/chromix/fonts.lock.json')):
    lock = decode(lock_path.read_bytes())
    for name, expected in lock['files'].items():
        path = Path(name)
        require(path.is_file() and not path.is_symlink(), 'CHROMIX_FONT_MISSING')
        with path.open('rb') as stream:
            require(hashlib.file_digest(stream, 'sha256').hexdigest() == expected, 'CHROMIX_FONT_MISMATCH')


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'CHROMIX_DUPLICATE_FIELD')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def validate(spec, version):
    if spec.get('schemaVersion') in ('browser-platform/chromix-environment/v3','browser-platform/chromix-environment/v4'):
        from native_artifact import validate as validate_custom
        validate_custom(spec,'chromix');require(spec['browserVersion']==version,'CHROMIX_VERSION_MISMATCH');return
    require(set(spec) == {'schemaVersion','id','revision','browserVersion','locale','timezone','screen'}, 'CHROMIX_SPEC_FIELDS')
    require(spec['schemaVersion'] in (SCHEMA, 'browser-platform/chromix-environment/v2') and spec['browserVersion'] == version, 'CHROMIX_VERSION_MISMATCH')
    require(isinstance(spec['id'],str) and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,95}',spec['id']), 'CHROMIX_SPEC_ID')
    require(type(spec['revision']) is int and spec['revision'] > 0, 'CHROMIX_SPEC_REVISION')
    require(isinstance(spec['locale'],str) and re.fullmatch(r'[a-z]{2,3}(?:-[A-Z]{2})?',spec['locale']), 'CHROMIX_LOCALE_INVALID')
    require(isinstance(spec['timezone'],str) and len(spec['timezone']) < 128, 'CHROMIX_TIMEZONE_INVALID')
    ZoneInfo(spec['timezone'])
    screen = spec['screen']
    require(isinstance(screen,dict) and (set(screen) == {'width','height','dpr'} or
            set(screen) == {'mode','width','height','dpr'} and screen['mode'] == 'auto'), 'CHROMIX_SCREEN_INVALID')
    require(type(screen['width']) is int and 640 <= screen['width'] <= 3840 and type(screen['height']) is int and 480 <= screen['height'] <= 2160, 'CHROMIX_SCREEN_INVALID')
    if spec['schemaVersion'] == SCHEMA:
        require(type(screen['dpr']) is int and screen['dpr'] == 1, 'CHROMIX_SCREEN_INVALID')
    else:
        require(screen.get('mode') == 'auto' and screen['dpr'] == 'system', 'CHROMIX_SCREEN_INVALID')


def identity(home):
    """Keep the exclusive descriptor alive until the browser process exits."""
    require(home.is_dir() and not home.is_symlink() and home.stat().st_uid == os.getuid(), 'CHROMIX_HOME_INVALID')
    directory = home / '.chromix'
    directory.mkdir(mode=0o700,exist_ok=True)
    require(not directory.is_symlink() and directory.stat().st_uid == os.getuid() and directory.stat().st_mode & 0o077 == 0, 'CHROMIX_HOME_INVALID')
    descriptor = os.open(directory/'worker.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
        path = directory/'identity.json'
        if path.exists() or path.is_symlink():
            require(path.is_file() and not path.is_symlink() and path.stat().st_mode & 0o077 == 0 and path.stat().st_nlink == 1, 'CHROMIX_IDENTITY_INVALID')
            value = decode(path.read_bytes())
            require(set(value) == {'schemaVersion','seed'} and value['schemaVersion'] == 1 and type(value['seed']) is int and 0 < value['seed'] < 2**64, 'CHROMIX_IDENTITY_INVALID')
        else:
            value = {'schemaVersion':1,'seed':secrets.randbelow(2**64-1)+1}
            temp = directory/('identity-'+secrets.token_hex(8)+'.tmp')
            fd = os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'w') as stream:
                json.dump(value,stream);stream.flush();os.fsync(stream.fileno())
            os.replace(temp,path)
        return descriptor, value['seed'], directory
    except BaseException:
        os.close(descriptor)
        raise


def maximize_window(spec):
    # Chromium constrains restored windows to one pixel below the work area.
    # A fixed window covering the screen must use the WM's maximized geometry.
    screen = spec['screen']
    return screen.get('mode') == 'auto' or (
        spec.get('schemaVersion') == 'browser-platform/chromix-environment/v4'
        and all(spec['window'][key] == screen[key] for key in ('width', 'height')))


def arguments(spec, seed, directory, url):
    target = urlsplit(url)
    require(url == 'about:blank' or target.scheme in {'http','https'} and target.hostname and target.username is None and target.password is None, 'CHROMIX_URL_INVALID')
    screen = spec['screen']
    persona = ['--fingerprint='+str(seed),
               '--fingerprint-screen-width='+str(screen['width']),
               '--fingerprint-screen-height='+str(screen['height'])]
    if screen.get('mode') == 'auto' or spec.get('schemaVersion') in ('browser-platform/chromix-environment/v3','browser-platform/chromix-environment/v4'):
        # Public --fingerprint injects a fixed screen even when size flags are
        # absent. Pin its explicit seeds/scalar defaults, use native display.
        # This is a separate environment revision, never a CSS preference.
        persona = ['--uxr-fingerprint-seed='+str(seed),
                   '--uxr-canvas-seed='+str(seed), '--uxr-audio-seed='+str(seed),
                   '--fingerprint-gpu-backend=native',
                   '--fingerprint-hardware-concurrency=8',
                   '--fingerprint-device-memory=8', '--fingerprint-storage-quota=102400']
    custom = spec.get('schemaVersion') in ('browser-platform/chromix-environment/v3','browser-platform/chromix-environment/v4')
    return [str(BROWSER), '--ozone-platform=x11', '--disable-setuid-sandbox',
            '--no-first-run','--no-default-browser-check','--disable-background-networking',
            '--disable-component-update','--disable-sync','--disable-breakpad',
            '--password-store=basic','--use-mock-keychain',
            '--proxy-server=socks5://profile-relay:1080','--proxy-bypass-list=<-loopback>',
            '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE profile-relay',
            '--force-webrtc-ip-handling-policy=disable_non_proxied_udp',
            *persona,'--fingerprint-platform=linux',
            *([] if custom else ['--fingerprint-locale='+spec['locale']]),'--fingerprint-timezone='+spec['timezone'],
            '--lang='+spec['locale'],
            *(['--accept-lang='+','.join(spec['languages']), '--deny-permission-prompts'] if custom else []),
            *(['--disable-font-subpixel-positioning'] if spec.get('schemaVersion') == 'browser-platform/chromix-environment/v4' else []),
            *([] if screen['dpr'] == 'system' else ['--force-device-scale-factor=1']),
            '--window-size='+str(spec.get('window',screen)['width'])+','+str(spec.get('window',screen)['height']),
            '--user-data-dir='+str(directory/'profile'),url]


def verify_display(spec, env):
    if spec['screen'].get('mode') == 'auto':
        require(all(not env.get(k) for k in ('SELKIES_MANUAL_WIDTH','SELKIES_MANUAL_HEIGHT')),
                'CHROMIX_DISPLAY_DRIFT')
        require(env.get('MAX_RES') == '3840x2160', 'CHROMIX_DISPLAY_DRIFT')
    else:
        for key,expected in [('SELKIES_MANUAL_WIDTH',spec['screen']['width']),('SELKIES_MANUAL_HEIGHT',spec['screen']['height'])]:
            require(env.get(key) == str(expected),'CHROMIX_DISPLAY_DRIFT')


def configure_languages(directory,languages):
    """Update only language preferences while the Home lock excludes the browser."""
    profile=directory/'profile';profile.mkdir(mode=0o700,exist_ok=True)
    require(not profile.is_symlink(),'CHROMIX_HOME_INVALID')
    default=profile/'Default';default.mkdir(mode=0o700,exist_ok=True)
    require(not default.is_symlink(),'CHROMIX_HOME_INVALID')
    path=default/'Preferences';require(not path.is_symlink(),'CHROMIX_HOME_INVALID')
    value=decode(path.read_bytes()) if path.exists() else {}
    require(isinstance(value,dict),'CHROMIX_PROFILE_INVALID')
    intl=value.setdefault('intl',{});require(isinstance(intl,dict),'CHROMIX_PROFILE_INVALID')
    intl['accept_languages']=','.join(languages);intl['selected_languages']=','.join(languages)
    temporary=default/('Preferences-'+secrets.token_hex(8)+'.tmp')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump(value,f);f.flush();os.fsync(f.fileno())
    os.replace(temporary,path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['verify','launch'])
    parser.add_argument('url',nargs='?',default='about:blank')
    args = parser.parse_args()
    try:
        require(args.action == 'verify' or os.getuid() != 0,'CHROMIX_USER_INVALID')
        lock = decode(LOCK.read_bytes())
        artifact = Path('/run/browser-platform/environment.json')
        raw = artifact.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == os.environ.get('BROWSER_PLATFORM_ARTIFACT_SHA256'),'CHROMIX_ARTIFACT_MISMATCH')
        spec = decode(raw);validate(spec,lock['version'])
        if spec.get('schemaVersion') in ('browser-platform/chromix-environment/v3','browser-platform/chromix-environment/v4'):
            from native_artifact import verify
            verify(spec,'chromix',raw,os.environ)
        require(os.environ.get('BROWSER_PLATFORM_ENVIRONMENT_ID') == spec['id'],'CHROMIX_ENVIRONMENT_MISMATCH')
        require(os.environ.get('PIXELFLUX_WAYLAND','false').lower() == 'false','CHROMIX_X11_REQUIRED')
        require(os.environ.get('TZ') == spec['timezone'],'CHROMIX_TIMEZONE_DRIFT')
        verify_display(spec, os.environ)
        with BROWSER.open('rb') as stream:
            require(hashlib.file_digest(stream,'sha256').hexdigest() == lock['executables']['chromix/chrome']['sha256'],'CHROMIX_BINARY_MISMATCH')
        verify_fonts()
        if args.action == 'verify':
            if spec.get('schemaVersion')=='browser-platform/chromix-environment/v4' and os.getuid()==0:
                from display_config import configure
                configure('chromium',maximize_window(spec))
            print('CHROMIX_ENVIRONMENT_VERIFIED');return 0
        fd,seed,directory = identity(Path('/config'))
        try:
            if spec.get('schemaVersion') in ('browser-platform/chromix-environment/v3','browser-platform/chromix-environment/v4'):
                configure_languages(directory,spec['languages'])
            env = dict(os.environ,HOME='/config',TZ=spec['timezone'])
            # Packaged fonts are fixed; no user-provided library/config injection.
            template=Path('/opt/chromix/fonts/fonts.conf.template')
            if template.exists():
                cache=directory/'font-cache';cache.mkdir(exist_ok=True)
                config=directory/'fonts.conf'
                config.write_text(template.read_text().replace('@FONTS_DIR@','/opt/chromix/fonts').replace('@CACHE_DIR@',str(cache)))
                env['FONTCONFIG_FILE']=str(config)
            return subprocess.run(arguments(spec,spec.get('seed',seed),directory,args.url),env=env).returncode
        finally:
            os.close(fd)
    except (ValueError,OSError,KeyError,TypeError) as error:
        code=str(error) if isinstance(error,ValueError) and str(error).startswith('CHROMIX_') else 'CHROMIX_START_REJECTED'
        print(code,file=sys.stderr);return 1


if __name__ == '__main__':
    raise SystemExit(main())
