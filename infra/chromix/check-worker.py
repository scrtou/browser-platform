#!/usr/bin/env python3
"""Bounded isolated real /init, authenticated display, X11 and storage QA.

Only r6l-chromix-labelled resources and newly created private directories.
Does not substitute for controller/Guard/Relay integration acceptance.
"""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[1]


def docker(*args,check=True):
    return subprocess.run(['docker',*map(str,args)],capture_output=True,text=True,check=check)


def write(p,v):
    p.write_text(json.dumps(v,indent=2)+'\n');p.chmod(0o600)


def wait(fn,seconds=60):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        try:
            value=fn()
            if value:return value
        except (subprocess.CalledProcessError,ValueError,KeyError,OSError):pass
        time.sleep(.3)
    raise RuntimeError('CHROMIX_QA_TIMEOUT')


def evaluate(name,expression):
    source=(PROJECT/'infra/firefox-proxy/check-bidi.py').read_text().split('class BiDi:',1)[0]
    source+='''
import urllib.request
from urllib.parse import urlsplit
targets=json.load(urllib.request.urlopen('http://127.0.0.1:9222/json'))
target=next(t for t in targets if t['type']=='page')
w=WebSocket('127.0.0.1',9222,urlsplit(target['webSocketDebuggerUrl']).path)
w.send_json({'id':1,'method':'Runtime.evaluate','params':{'expression':EXPRESSION,'awaitPromise':True,'returnByValue':True}})
while True:
 result=w.receive_json()
 if result.get('id')==1:
  assert 'exceptionDetails' not in result['result'],result
  print(json.dumps(result['result']['result'].get('value')));break
w.socket.close()
'''.replace('EXPRESSION',repr(expression))
    return json.loads(docker('exec',name,'python3','-c',source).stdout)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--font-check',choices=['present','missing'])
    parser.add_argument('--native-screen-probe',action='store_true',
                        help='Diagnostic X11 resize with explicit seeds; not production acceptance')
    parser.add_argument('--auto-resolution',action='store_true',
                        help='Exercise candidate launcher auto contract and X11 resize')
    parser.add_argument('--client-resize',action='store_true')
    parser.add_argument('--system-dpi', action='store_true')
    parser.add_argument('--dpi-probe', choices=['fixed', 'native'], help='Diagnostic only: compare runtime system DPI response')
    args=parser.parse_args();os.umask(0o077)
    root=args.output.resolve();root.mkdir(mode=0o700)
    assert 'runtime' in root.parts
    home=root/'home';home.mkdir(mode=0o700)
    spec={'schemaVersion':'browser-platform/chromix-environment/v1','id':'chromix-qa','revision':1,'browserVersion':'154.0.8037.57','locale':'en-US','timezone':'UTC','screen':{'width':1280,'height':720,'dpr':1}}
    if args.auto_resolution:
        assert not args.native_screen_probe
        spec['screen']['mode']='auto'
    if args.system_dpi:
        assert args.auto_resolution and args.dpi_probe != 'native'
        spec['schemaVersion']='browser-platform/chromix-environment/v2'
        spec['screen']['dpr']='system'
    assert not args.client_resize or args.auto_resolution
    write(root/'environment.json',spec)
    artifact_hash=hashlib.sha256((root/'environment.json').read_bytes()).hexdigest()
    autostart=root/'autostart';autostart.write_text('#!/bin/sh\nexec python3 /opt/chromix-qa/qa-browser.py\n');autostart.chmod(0o755)
    material=Path(tempfile.mkdtemp(prefix='r6l-display-',dir='/dev/shm'))
    sid,user,password=[str(uuid.uuid4()) for _ in range(3)]
    write(material/'binding.json',{'version':1,'session_id':sid,'uid':os.getuid()})
    salt=os.urandom(16)
    (material/'basic.htpasswd').write_text(user+':{SSHA}'+base64.b64encode(hashlib.sha1(password.encode()+salt).digest()+salt).decode()+'\n')
    (material/'master-token').write_text('')
    name='r6l-chromix-worker-'+uuid.uuid4().hex[:8]
    write(root/'resources.json',{'name':name,'display':str(material),'image':args.image})
    command=['run','-d','--name',name,'--label','io.browser-platform.qa=r6l-chromix','--network','none','--memory','1200m','--cpus','1.5','--pids-limit','512','--shm-size','256m','--cap-drop','NET_ADMIN','--cap-drop','NET_RAW','--security-opt','no-new-privileges','--security-opt','seccomp='+str(HERE/'seccomp.json'),'--tmpfs','/run/browser-platform-display:rw,nosuid,nodev,noexec,mode=0755,size=1m']
    for src,dst in [(home,'/config'),(root/'environment.json','/run/browser-platform/environment.json'),(material,'/run/browser-platform-session-input'),(autostart,'/defaults/autostart'),(HERE/'qa-browser.py','/opt/chromix-qa/qa-browser.py')]:
        command+=['--mount',f'type=bind,src={src},dst={dst}'+('' if src==home else ',readonly')]
    if args.client_resize:
        for src,dst in [(root,'/qa-output'),(HERE/'check-auto-client.py','/opt/chromix-qa/client.py'),(PROJECT/'infra/firefox-proxy/check-bidi.py','/opt/chromix-qa/check-bidi.py')]:
            command+=['--mount',f'type=bind,src={src},dst={dst}'+('' if src==root else ',readonly')]
    env={'PUID':str(os.getuid()),'PGID':str(os.getgid()),'SUBFOLDER':'/'+sid+'/','TZ':'UTC','PIXELFLUX_WAYLAND':'false','SELKIES_MANUAL_WIDTH':'1280','SELKIES_MANUAL_HEIGHT':'720','BROWSER_PLATFORM_ENVIRONMENT_ID':'chromix-qa','BROWSER_PLATFORM_ARTIFACT_SHA256':artifact_hash,'SELKIES_ALLOWED_ORIGINS':'https://entry.r5d.test:29443'}
    if args.native_screen_probe:
        env['CHROMIX_QA_NATIVE_SCREEN']='1'
        env.pop('SELKIES_MANUAL_WIDTH')
        env.pop('SELKIES_MANUAL_HEIGHT')
        env['MAX_RES']='3840x2160'
        command+=['--entrypoint','/init']
    if args.auto_resolution:
        env.pop('SELKIES_MANUAL_WIDTH')
        env.pop('SELKIES_MANUAL_HEIGHT')
        env['MAX_RES']='3840x2160'
    if args.dpi_probe == 'native':
        env['CHROMIX_QA_NATIVE_DPI']='1'
    if args.client_resize:
        env['SELKIES_ALLOWED_ORIGINS']='http://127.0.0.1:3000'
    for k,v in env.items():command+=['-e',k+'='+v]
    docker(*command,args.image)
    # Failures retain the exact QA instance and logs for diagnosis.
    try:
        observation=wait(lambda:evaluate(name,"JSON.stringify({ua:navigator.userAgent,platform:navigator.platform,locale:navigator.language,timeZone:Intl.DateTimeFormat().resolvedOptions().timeZone,screen:[screen.width,screen.height,devicePixelRatio]})"))
        write(root/'observation.json',json.loads(observation))
        code='''import base64,http.client,json
c=http.client.HTTPConnection('127.0.0.1',3000,timeout=10)
c.request('GET',PATH);r=c.getresponse();r.read();assert r.status==401
c.request('GET',PATH,headers={'Authorization':'Basic '+base64.b64encode(AUTH.encode()).decode()});r=c.getresponse();body=r.read();assert r.status==200 and b'<html' in body.lower();print('PASS')
'''.replace('PATH',repr('/'+sid+'/')).replace('AUTH',repr(user+':'+password))
        # Credentials stay in stdin, never in process arguments.
        result=subprocess.run(['docker','exec','-i',name,'python3','-'],input=code,capture_output=True,text=True)
        (root/'display-check.log').write_text(result.stdout+result.stderr);assert result.returncode==0
        if args.dpi_probe:
            check_dpi(name, root, args.dpi_probe)
        if args.font_check:
            check_fonts(name,root,args.font_check)
        if args.native_screen_probe or args.auto_resolution:
            check_native_screen(name,root)
        if args.client_resize:
            result=subprocess.run(['docker','exec','-i','--user',str(os.getuid()),name,'/opt/camoufox-python/bin/python','/opt/chromix-qa/client.py'],input=json.dumps({'user':user,'password':password,'sid':sid,'system_dpi':args.system_dpi}),capture_output=True,text=True,timeout=150)
            (root/'client-resize.log').write_text(result.stdout+result.stderr)
            assert result.returncode==0, 'CHROMIX_CLIENT_RESIZE_FAILED'
        stop=docker('exec','--user',str(os.getuid()),name,'python3','/usr/local/lib/browser-platform/browser-shutdown.py','--timeout','12',check=False)
        (root/'normal-stop.log').write_text(stop.stdout+stop.stderr);assert stop.returncode==0
        logs=docker('logs',name,check=False)
        (root/'worker.log').write_text(logs.stdout+logs.stderr)
        docker('stop','-t','30',name);docker('rm','-v',name)
        import shutil
        shutil.rmtree(material)
        write(root/'result.json',{'result':'PASS','scope':'isolated /init, X11, authenticated display, exact launcher and normal close; no controller/network/storage recovery acceptance yet','image':args.image,'observation':json.loads(observation),'qa_removed':True,'auto_resolution':args.auto_resolution,'client_resize':args.client_resize,'diagnostic_launcher_bypass':args.native_screen_probe or args.dpi_probe == 'native', 'dpi_probe':args.dpi_probe, 'system_dpi':args.system_dpi})
        print('PASS standalone X11, display authentication and normal close')
    finally:
        logs=docker('logs',name,check=False)
        if logs.returncode == 0:
            (root/'worker.log').write_text(logs.stdout+logs.stderr)




def check_dpi(name, root, mode):
    rows=[]
    for dpi in (96, 144, 192, 96):
        code="import asyncio; from selkies.selkies import set_dpi; assert asyncio.run(set_dpi("+str(dpi)+"))"
        result=docker('exec','--user',str(os.getuid()),'-e','HOME=/config','-e','DISPLAY=:1',name,'/lsiopy/bin/python', '-c',code,check=False)
        (root/('dpi-'+str(dpi)+'.log')).write_text(result.stdout+result.stderr)
        assert result.returncode == 0, 'DPI_APPLY_FAILED'
        time.sleep(2)
        observed=evaluate(name,'({screen:[screen.width,screen.height],dpr:devicePixelRatio,outer:[outerWidth,outerHeight],inner:[innerWidth,innerHeight]})')
        rows.append({'dpi':dpi,'observed':observed})
    write(root/'dpi-probe.json',{'mode':mode,'rows':rows,'scope':'diagnostic set_dpi, not UI acceptance'})


def cdp_command(name,method,params):
    source=(PROJECT/'infra/firefox-proxy/check-bidi.py').read_text().split('class BiDi:',1)[0]
    source+='''
import urllib.request
from urllib.parse import urlsplit
target=next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9222/json')) if t['type']=='page')
w=WebSocket('127.0.0.1',9222,urlsplit(target['webSocketDebuggerUrl']).path)
def call(i,method,params):
 w.send_json({'id':i,'method':method,'params':params})
 while True:
  r=w.receive_json()
  if r.get('id')==i:
   assert 'error' not in r,r
   return r['result']
params=PARAMS
if METHOD=='CSS.getPlatformFontsForNode':
 call(10,'DOM.enable',{})
 call(11,'CSS.enable',{})
 doc=call(12,'DOM.getDocument',{})['root']['nodeId']
 node=call(13,'DOM.querySelector',{'nodeId':doc,'selector':params.pop('selector')})['nodeId']
 params={'nodeId':node}
w.send_json({'id':1,'method':METHOD,'params':params})
while True:
 result=w.receive_json()
 if result.get('id')==1:
  assert 'error' not in result,result
  print(json.dumps(result['result']));break
w.socket.close()
'''.replace('METHOD',repr(method)).replace('PARAMS',repr(params))
    return json.loads(docker('exec',name,'python3','-c',source).stdout)


def check_fonts(name, root, expected):
    samples={'simplified':'中文输入测试，汉字显示正常。', 'traditional':'繁體中文測試，臺灣與香港。', 'mixed':'English 123 中文繁體'}
    html='<html><meta charset="utf-8"><body style="background:white;color:black;font:32px sans-serif">'+''.join('<p id="'+key+'" lang="'+('zh-TW' if key=='traditional' else 'zh-CN')+'">'+text+'</p>' for key,text in samples.items())+'<input id="input" style="font:32px sans-serif;width:900px"></body></html>'
    cdp_command(name,'Page.enable',{})
    frame=cdp_command(name,'Page.getFrameTree',{})['frameTree']['frame']['id']
    cdp_command(name,'Page.setDocumentContent',{'frameId':frame,'html':html})
    evaluate(name,"document.querySelector('#input').focus(); true")
    cdp_command(name,'Input.insertText',{'text':'中文輸入 English 123'})
    assert evaluate(name,"document.querySelector('#input').value")=='中文輸入 English 123'
    fonts={}
    for key in samples:
        fonts[key]=cdp_command(name,'CSS.getPlatformFontsForNode',{'selector':'#'+key})['fonts']
        has_cjk=any('CJK' in f['familyName'] and f['glyphCount']>0 for f in fonts[key])
        assert has_cjk==(expected=='present'),(key,fonts[key],expected)
    shot=cdp_command(name,'Page.captureScreenshot',{'format':'png'})
    (root/'cjk-rendering.png').write_bytes(base64.b64decode(shot['data']))
    write(root/'fonts-result.json',{'result':'PASS','expected':expected,'fonts':fonts,'input_value_preserved':True,'samples':samples})


def check_native_screen(name,root):
    """Invoke installed Selkies X11 backend and observe actual browser APIs."""
    rows=[]
    for width,height in [(1280,720),(1600,900),(800,600),(1280,720)]:
        source=('import asyncio; from selkies.display_utils import resize_display; '
                f'asyncio.run(resize_display("{width}x{height}"))')
        result=docker('exec','--user',str(os.getuid()),name,
                      '/lsiopy/bin/python3','-c',source)
        (root/f'resize-{width}-{height}.log').write_text(result.stdout+result.stderr)
        def observed():
            value=evaluate(name,'({screen:[screen.width,screen.height],avail:[screen.availWidth,screen.availHeight],outer:[outerWidth,outerHeight],inner:[innerWidth,innerHeight],dpr:devicePixelRatio,locale:navigator.language,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone,cpu:navigator.hardwareConcurrency})')
            return value if value['screen']==[width,height] else None
        value=wait(observed,10)
        assert value['dpr']==1 and value['locale']=='en-US' and value['timezone']=='UTC'
        rows.append(value)
        write(root/'native-screen-probe.json',{'scope':'X11 backend and browser observation; no frontend or persona-equivalence acceptance','samples':rows})


if __name__=='__main__':main()
