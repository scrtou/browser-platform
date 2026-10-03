#!/usr/bin/env python3
"""Check accepted display combinations on one disposable normal Camoufox Home.

Runs A -> B -> A without changing production Profiles; records real X11
geometry, corner clicks, text input, storage retention and display auth.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid

from environment import expected_environment


def docker(*args, input=None, check=True):
    r = subprocess.run(['docker', *map(str, args)], input=input, capture_output=True, text=True, timeout=90)
    if check and r.returncode:
        raise RuntimeError('QA_DOCKER_' + args[0])
    return r


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')
    path.chmod(0o600)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--catalog', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    root = a.output.resolve()
    assert 'runtime' in root.parts and any(name in root.parts for name in ('r6p-templates-20261001','r6q-engine-neutral-20261001'))
    root.mkdir(mode=0o700)
    home = root / 'qa-home'
    home.mkdir(mode=0o700)
    entries = json.loads(a.catalog.read_bytes())['artifacts']
    assert len(entries) == 2
    material = Path(tempfile.mkdtemp(prefix='r6p-display-', dir='/dev/shm'))
    sid, user, password = [str(uuid.uuid4()) for _ in range(3)]
    write(material / 'binding.json', {'version': 1, 'session_id': sid, 'uid': os.getuid()})
    salt = os.urandom(16)
    (material / 'basic.htpasswd').write_text(user + ':{SSHA}' + base64.b64encode(hashlib.sha1(password.encode() + salt).digest() + salt).decode() + '\n')
    (material / 'master-token').write_text('')
    rows = []
    try:
        for n, entry in enumerate([entries[0], entries[1], entries[0]]):
            app = entry['application']['provider_config']
            mounts = app['docker_overrides']['mounts']
            artifact_path = Path(next(m['Source'] for m in mounts if m['Target'].endswith('/environment.json')))
            artifact = json.loads(artifact_path.read_bytes())
            autostart = root / ('autostart-' + str(n))
            autostart.write_bytes(base64.b64decode(app['custom_autostart_script_b64']))
            autostart.chmod(0o755)
            name = 'r6p-desktop-' + uuid.uuid4().hex[:10]
            write(root / ('resource-' + str(n) + '.json'), {'name': name, 'display': str(material)})
            cmd = ['run', '-d', '--name', name, '--label', 'io.browser-platform.qa=r6p-desktop', '--network', 'none',
                   '--memory', '1536m', '--cpus', '1.5', '--pids-limit', '512', '--shm-size', '256m',
                   '--cap-drop', 'NET_ADMIN', '--cap-drop', 'NET_RAW', '--security-opt', 'no-new-privileges',
                   '--tmpfs', '/run/browser-platform-display:rw,nosuid,nodev,noexec,mode=0755,size=1m']
            for src, dst, ro in [(home, '/config', False), (material, '/run/browser-platform-session-input', True),
                                 (autostart, '/defaults/autostart', True)] + [(m['Source'], m['Target'], True) for m in mounts]:
                cmd += ['--mount', f'type=bind,src={src},dst={dst}' + (',readonly' if ro else '')]
            env = {v['name']: v['value'] for v in app['env']}
            env.update(PUID=str(os.getuid()), PGID=str(os.getgid()), SUBFOLDER='/' + sid + '/', SEALSKIN_URL='about:blank')
            for k, v in env.items():
                cmd += ['-e', k + '=' + v]
            docker(*cmd, app['image'])
            try:
                def x(*args, check=True):
                    return docker('exec', '--user', str(os.getuid()), '-e', 'DISPLAY=:1', name, *args, check=check)
                deadline = time.monotonic() + 70
                while time.monotonic() < deadline:
                    r = x('xdotool', 'getactivewindow', 'getwindowname', check=False)
                    if r.returncode == 0 and r.stdout.strip():
                        break
                    time.sleep(.5)
                else:
                    raise RuntimeError('QA_BROWSER_NOT_READY')
                fixture = '''<!doctype html><html><meta charset="utf-8"><title>R6P</title><body style="margin:0">
<input id="input" style="position:absolute;left:80px;top:100px;width:400px" oninput="document.title='typed:'+this.value">
<textarea id="proof" style="position:absolute;top:200px;width:700px;height:200px"></textarea>
<script>
const previous=localStorage.getItem('r6p-marker');localStorage.setItem('r6p-marker','preserved');
const buttons=[[20,20],[innerWidth-70,20],[innerWidth-70,innerHeight-60]].map(([x,y],i)=>{
 const b=document.createElement('button');b.textContent='hit'+i;b.style=`position:absolute;left:${x}px;top:${y}px;width:50px;height:40px`;
 b.onclick=()=>document.title='hit'+i;document.body.append(b);return [x+25,y+20];});
const value={screen:[screen.width,screen.height,devicePixelRatio],outer:[outerWidth,outerHeight],inner:[innerWidth,innerHeight],previous,buttons};
const f=document.querySelector('#proof');f.value=JSON.stringify(value);f.focus();f.select();document.title='R6P-READY';
</script></body></html>'''
                docker('exec', '-i', name, 'python3', '-c', "import sys;open('/tmp/r6p.html','w').write(sys.stdin.read())", input=fixture)
                x('xdotool', 'key', '--clearmodifiers', 'ctrl+l')
                x('xdotool', 'type', '--clearmodifiers', 'file:///tmp/r6p.html')
                x('xdotool', 'key', 'Return')
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    if x('xdotool', 'getactivewindow', 'getwindowname').stdout.startswith('R6P-READY'):
                        break
                    time.sleep(.3)
                else:
                    raise RuntimeError('QA_PAGE_NOT_READY')
                x('xdotool', 'key', '--clearmodifiers', 'ctrl+c')
                observed = json.loads(x('xclip', '-selection', 'clipboard', '-o').stdout)
                spec = artifact['spec']
                assert observed['screen'] == [spec['screen']['width'], spec['screen']['height'], 1]
                assert observed['outer'] == [spec['window']['width'], spec['window']['height']]
                reference = json.loads(artifact_path.with_name('acceptance.json').read_bytes())['results']['homeReplay']['observations'][0]['observed']
                assert observed['inner'] == [reference['window']['innerWidth'], reference['window']['innerHeight']]
                assert observed['previous'] == (None if n == 0 else 'preserved')
                geometry = x('xdotool', 'getactivewindow', 'getwindowgeometry', '--shell').stdout
                pos = dict(line.split('=', 1) for line in geometry.splitlines() if '=' in line)
                offset_x = int(pos['X'])
                offset_y = int(pos['Y']) + observed['outer'][1] - observed['inner'][1]
                for i, (cx, cy) in enumerate(observed['buttons']):
                    x('xdotool', 'mousemove', str(offset_x + cx), str(offset_y + cy), 'click', '1')
                    assert x('xdotool', 'getactivewindow', 'getwindowname').stdout.startswith('hit' + str(i))
                x('xdotool', 'mousemove', str(offset_x + 180), str(offset_y + 110), 'click', '1')
                x('xdotool', 'type', '--clearmodifiers', 'r6p-input')
                assert x('xdotool', 'getactivewindow', 'getwindowname').stdout.startswith('typed:r6p-input')
                auth_script = '''import base64,http.client,json,sys
v=json.load(sys.stdin);c=http.client.HTTPConnection('127.0.0.1',3000,timeout=10)
c.request('GET','/'+v['sid']+'/');r=c.getresponse();r.read();assert r.status==401
c.request('GET','/'+v['sid']+'/',headers={'Authorization':'Basic '+base64.b64encode((v['user']+':'+v['password']).encode()).decode()});r=c.getresponse();body=r.read();assert r.status==200 and b'<html' in body.lower()
'''
                docker('exec', '-i', name, 'python3', '-c', auth_script, input=json.dumps({'sid': sid, 'user': user, 'password': password}))
                rows.append({'artifact': entry['id'], 'observed': observed, 'corner_clicks': 3, 'input': True, 'display_auth': True})
                stop = x('python3', '/usr/local/lib/browser-platform/browser-shutdown.py', '--timeout', '12')
                (root / ('stop-' + str(n) + '.log')).write_text(stop.stdout + stop.stderr)
                docker('stop', '-t', '30', name)
                docker('rm', '-v', name)
            finally:
                logs = docker('logs', name, check=False)
                if logs.returncode == 0:
                    (root / ('worker-' + str(n) + '.log')).write_text(logs.stdout + logs.stderr)
        write(root / 'result.json', {'result': 'PASS', 'sequence': 'A-B-A', 'rows': rows, 'production_touched': False})
        shutil.rmtree(material)
        print('PASS three normal desktops, nine corner clicks, input, storage, authenticated display and rollback')
    except BaseException:
        write(root / 'retained.json', {'display': str(material), 'reason': 'QA failure; preserve for diagnosis'})
        raise


if __name__ == '__main__':
    main()
