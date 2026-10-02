#!/usr/bin/env python3
"""Normal desktop replay for a custom Chromix/Firefox artifact in isolated QA."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[1]

def docker(*args,check=True,input=None,timeout=90):
    r=subprocess.run(['docker',*map(str,args)],input=input,text=True,capture_output=True,timeout=timeout)
    if check and r.returncode:raise RuntimeError('NATIVE_QA_DOCKER_'+args[0]+': '+r.stderr[-300:])
    return r

def write(path,value):
    path.write_text(json.dumps(value,indent=2)+'\n');path.chmod(0o600)

def normalize(value):
    if 'spec' not in value:return value
    spec=value['spec'];screen=spec['screen'];return {**spec,'schemaVersion':value['schemaVersion'],'runtimeImageDigest':value['runtimeImageDigest'],'screen':({'width':screen['width'],'height':screen['height'],'mode':'auto','dpr':'system'} if screen.get('mode')=='auto' else {'width':screen['width'],'height':screen['height'],'dpr':1})}

def invariant(observed,auto):
    return {k:v for k,v in observed.items() if not auto or k not in ('screen','window','deviceScaleFactor')}

def environment(spec,sha):
    value= {'PUID':str(os.getuid()),'PGID':str(os.getgid()),'BROWSER_PLATFORM_ENVIRONMENT_ID':spec['id'],
            'BROWSER_PLATFORM_ARTIFACT_SHA256':sha,'BROWSER_PLATFORM_RUNTIME_IMAGE_DIGEST':spec['runtimeImageDigest'],
            'BROWSER_PLATFORM_LOCALE':spec['locale'],'BROWSER_PLATFORM_LANGUAGES':','.join(spec['languages']),
            'LANG':spec['locale'].replace('-','_')+'.UTF-8','TZ':spec['timezone'],'PIXELFLUX_WAYLAND':'false',
            'SELKIES_MANUAL_WIDTH':str(spec['screen']['width']),'SELKIES_MANUAL_HEIGHT':str(spec['screen']['height']),
            'SELKIES_ALLOWED_ORIGINS':'https://entry.native-qa.test'}
    if spec['screen'].get('mode')=='auto':
        value.pop('SELKIES_MANUAL_WIDTH');value.pop('SELKIES_MANUAL_HEIGHT');value.update(BROWSER_PLATFORM_DISPLAY_MODE='auto',MAX_RES='3840x2160',SELKIES_MANUAL_RESOLUTION='false')
    if '/camoufox-' in spec['schemaVersion']:value['SELKIES_MANUAL_RESOLUTION']='false' if spec['screen'].get('mode')=='auto' else 'true'
    return value

def run_one(spec,artifact,home,root,network,role,iteration,auth,material,client_browsers=None,verify_input=False,accepted_entrypoint=False):
    engine='camoufox' if '/camoufox-' in spec['schemaVersion'] else 'chromix' if '/chromix-' in spec['schemaVersion'] else 'firefox'
    name='bp-native-qa-'+uuid.uuid4().hex[:10];sid,user,password=auth
    cmd=['run','-d','--name',name,'--label','io.browser-platform.qa=native-generation','--network',network,
         '--memory','1536m','--cpus','1.5','--pids-limit','512','--shm-size','256m','--cap-drop','NET_ADMIN','--cap-drop','NET_RAW',
         '--security-opt','no-new-privileges:true','--tmpfs','/run/browser-platform-display:rw,nosuid,nodev,noexec,mode=0755,size=1m']
    if engine=='chromix':cmd+=['--security-opt','seccomp='+str(PROJECT/'infra/chromix/seccomp.json')]
    for source,target,readonly in [(home,'/config',False),(artifact,'/run/browser-platform/environment.json',True),(material,'/run/browser-platform-session-input',True),(root/'autostart','/defaults/autostart',True),(root/'qa-source','/qa',True)]:
        cmd+=['--mount',f'type=bind,src={source},dst={target}'+(',readonly' if readonly else '')]
    env=environment(spec,hashlib.sha256(artifact.read_bytes()).hexdigest());env['SUBFOLDER']='/'+sid+'/'
    if accepted_entrypoint:
        report=artifact.with_name('acceptance.json')
        env['BROWSER_PLATFORM_ACCEPTANCE_SHA256']=hashlib.sha256(report.read_bytes()).hexdigest()
        cmd+=['--mount',f'type=bind,src={report},dst=/run/browser-platform/acceptance.json,readonly']
    for k,v in env.items():cmd+=['-e',k+'='+v]
    write(root/(role+'-'+str(iteration)+'-resource.json'),{'container':name,'home':str(home)})
    candidate=engine=='camoufox' and not accepted_entrypoint
    if candidate:cmd+=['--entrypoint','/opt/camoufox-python/bin/python']
    docker(*cmd,spec['runtimeImageDigest'],*(['/qa/qa-entrypoint.py'] if candidate else []))
    success=False
    try:
        deadline=time.monotonic()+75
        while time.monotonic()<deadline:
            r=docker('exec',name,'python3','-c','import socket; s=socket.create_connection(("127.0.0.1",9222),1);s.close()',check=False)
            if r.returncode==0:break
            time.sleep(.5)
        else:raise RuntimeError('NATIVE_QA_BROWSER_TIMEOUT')
        result=docker('exec',name,'python3','/qa/probe.py','--role',role,'--iteration',iteration,check=False,timeout=90)
        (root/(role+'-'+str(iteration)+'-probe.log')).write_text(result.stdout+result.stderr)
        if result.returncode:raise RuntimeError('NATIVE_QA_PROBE_FAILED')
        observed=json.loads(result.stdout)
        if iteration==0 or verify_input:
            code='''import base64,http.client
c=http.client.HTTPConnection('127.0.0.1',3000,timeout=10)
c.request('GET',PATH);r=c.getresponse();r.read();assert r.status==401
c.request('GET',PATH,headers={'Authorization':'Basic '+base64.b64encode(AUTH.encode()).decode()});r=c.getresponse();r.read();assert r.status==200
'''.replace('PATH',repr('/'+sid+'/')).replace('AUTH',repr(user+':'+password))
            docker('exec','-i',name,'python3','-',input=code)
            def x(*args):return docker('exec','--user',str(os.getuid()),'-e','DISPLAY=:1',name,*args).stdout
            pos=dict(v.split('=',1) for v in x('xdotool','getactivewindow','getwindowgeometry','--shell').splitlines() if '=' in v)
            dx=int(pos['X']);dy=int(pos['Y'])+int(pos['HEIGHT'])-observed['geometry']['inner'][1]
            write(root/(role+'-'+str(iteration)+'-input.json'),{'window':pos,'geometry':observed['geometry'],'offset':[dx,dy]})
            for i,(px,py) in enumerate(observed['geometry']['points']):
                x('xdotool','mousemove',str(dx+px),str(dy+py),'click','1')
                deadline=time.monotonic()+3
                while time.monotonic()<deadline:
                    if x('xdotool','getactivewindow','getwindowname').startswith('hit'+str(i)):break
                    time.sleep(.05)
                else:raise AssertionError('NATIVE_QA_CLICK_FAILED_'+str(i))
            x('xdotool','mousemove',str(dx+120),str(dy+112),'click','1');x('xdotool','type','--clearmodifiers','native-input')
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                if x('xdotool','getactivewindow','getwindowname').startswith('typed:native-input'):break
                time.sleep(.05)
            else:raise AssertionError('NATIVE_QA_TYPED_INPUT_FAILED')
        if iteration==0 or verify_input:
            from screenshot import png
            shot=subprocess.run(['docker','exec','--user',str(os.getuid()),'-e','DISPLAY=:1',name,'xwd','-root','-silent'],capture_output=True,check=True)
            (root/(role+'-desktop.png')).write_bytes(png(shot.stdout))
        if spec['screen'].get('mode')=='auto' and role=='A' and iteration==0:
            # Keep synthetic client decoding/input outside the worker's CPU and
            # memory budget. Shared loopback is only for QA display/BiDi access;
            # the worker keeps its original limits and isolated proxy network.
            client_output=root/'dynamic-client';client_output.mkdir(mode=0o700,exist_ok=True)
            client=docker('run','--rm','-i','--name',name+'-client','--label','io.browser-platform.qa=native-client',
                '--network','container:'+name,'--user',str(os.getuid())+':'+str(os.getgid()),
                '--memory','3g','--cpus','2','--pids-limit','512','--shm-size','512m',
                '--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=1g','--cap-drop','ALL',
                '--security-opt','no-new-privileges:true','-e','PLAYWRIGHT_BROWSERS_PATH=/client-browsers',
                '--mount',f'type=bind,src={root}/qa-source,dst=/qa,readonly',
                '--mount',f'type=bind,src={client_output},dst=/qa-output',
                '--mount',f"type=bind,src={client_browsers or PROJECT/'infra/camoufox/.build/playwright-client-browsers'},dst=/client-browsers,readonly",
                '--entrypoint','/opt/camoufox-python/bin/python',spec['runtimeImageDigest'],'/qa/client-probe.py',
                input=json.dumps({'user':user,'password':password,'sid':sid,'engine':engine,'system_dpi':True}),check=False,timeout=240)
            (root/'dynamic-client.log').write_text(client.stdout+client.stderr)
            assert client.returncode==0,'DYNAMIC_CLIENT_FAILED'
        stop=docker('exec','--user',str(os.getuid()),name,'python3','/usr/local/lib/browser-platform/browser-shutdown.py','--timeout','12',check=False)
        (root/(role+'-'+str(iteration)+'-stop.log')).write_text(stop.stdout+stop.stderr)
        assert stop.returncode==0,'NATIVE_QA_NORMAL_STOP_FAILED'
        success=True
        return observed
    finally:
        client_name=name+'-client'
        if docker('inspect','--type','container',client_name,check=False).returncode==0:
            # A timed-out client CLI can leave its container running. Close that
            # synthetic client before releasing the worker's network namespace.
            docker('stop','-t','10',client_name)
            docker('rm','-v',client_name,check=False)
        logs=docker('logs',name,check=False);(root/(role+'-'+str(iteration)+'-worker.log')).write_text(logs.stdout+logs.stderr)
        if not success:
            # Preserve evidence, but release QA resources whenever a normal
            # browser close succeeds. Refusal retains the instance and Home.
            close=docker('exec','--user',str(os.getuid()),name,'python3','/usr/local/lib/browser-platform/browser-shutdown.py','--timeout','12',check=False)
            (root/(role+'-'+str(iteration)+'-failure-close.log')).write_text(close.stdout+close.stderr)
            success=close.returncode==0
        if success:
            docker('stop','-t','30',name);docker('rm','-v',name)
        # Failures keep the instance and Home for diagnosis and normal closure.

def main():
    p=argparse.ArgumentParser();p.add_argument('--artifact',required=True,type=Path);p.add_argument('--network',required=True);p.add_argument('--output',required=True,type=Path);p.add_argument('--recreations',type=int,default=10);p.add_argument('--client-browsers',type=Path);a=p.parse_args();os.umask(0o077)
    root=a.output.resolve().parent/'native-qa';root.mkdir(mode=0o700)
    spec=normalize(json.loads(a.artifact.read_bytes()));auto=spec['screen'].get('mode')=='auto';material=Path(tempfile.mkdtemp(prefix='native-display-',dir='/dev/shm'))
    sid,user,password=[str(uuid.uuid4()) for _ in range(3)]
    write(material/'binding.json',{'version':1,'session_id':sid,'uid':os.getuid()});salt=os.urandom(16)
    (material/'basic.htpasswd').write_text(user+':{SSHA}'+base64.b64encode(hashlib.sha1(password.encode()+salt).digest()+salt).decode()+'\n');(material/'master-token').write_text('')
    (root/'autostart').write_text('#!/bin/sh\nexec /opt/camoufox-python/bin/python /qa/qa-browser.py\n');(root/'autostart').chmod(0o755)
    source=root/'qa-source';source.mkdir()
    for f in ['probe.py','qa-browser.py','qa-entrypoint.py','browser_client.py','check-dynamic-client.py','client-probe.py']:shutil.copy2(HERE/f,source/f)
    shutil.copy2(PROJECT/'infra/firefox-proxy/check-bidi.py',source/'check_bidi.py')
    for f in ['storage.js','observe.js']:shutil.copy2(PROJECT/'infra/camoufox/tests'/f,source/f)
    report={'schemaVersion':'browser-platform/native-acceptance/v1','status':'running','phase':'all','artifactSHA256':hashlib.sha256(a.artifact.read_bytes()).hexdigest(),'runtimeImageDigest':spec['runtimeImageDigest'],'recreationsPerHome':a.recreations,'observations':[]}
    try:
        baseline=None
        for role in ['A','B']:
            home=root/('home-'+role);home.mkdir(mode=0o700)
            for iteration in range(a.recreations+1):
                observed=run_one(spec,a.artifact.resolve(),home,root,a.network,role,iteration,(sid,user,password),material,a.client_browsers)
                if baseline is None:baseline=invariant(observed['observed'],auto)
                assert invariant(observed['observed'],auto)==baseline,('NATIVE_FINGERPRINT_DRIFT',[k for k in baseline if baseline[k]!=observed['observed'].get(k)])
                report['observations'].append(observed);write(a.output,report)
                print(role,iteration,'PASS',flush=True)
        restored=root/'restored-A';shutil.copytree(root/'home-A',restored,symlinks=True)
        r=run_one(spec,a.artifact.resolve(),restored,root,a.network,'A',a.recreations+1,(sid,user,password),material,a.client_browsers)
        assert invariant(r['observed'],auto)==baseline
        report.update(status='pass',offlineBackupRestore='pass',normalDesktopInput=True,displayAuthentication=True)
        if auto:report['dynamicDisplay']='pass'
        shutil.rmtree(material)
    except BaseException as e:
        report.update(status='failed',error=str(e));raise
    finally:
        write(a.output,report)
        names=docker('ps','-a','--filter','label=io.browser-platform.qa=native-generation','--format','{{.Names}}').stdout.splitlines()
        if not names and material.exists():shutil.rmtree(material)
if __name__=='__main__':main()
