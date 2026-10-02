#!/usr/bin/env python3
"""Isolated real Selkies + candidate Gateway persistence QA. No production writes."""
import argparse,base64,hashlib,importlib.util,json,os,shutil,subprocess,tempfile,time,uuid
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[3]
SID='2d3aaeda-bf75-4a4e-b31d-44dd999a713f'
CLIENT='sha256:819a225630907a72466a2c67e23cc6261e0efcd790744948dd13183f3f4bd0ac'
def run(args,**kw):return subprocess.run(list(map(str,args)),check=True,text=True,capture_output=True,**kw)
def docker(*args,**kw):return run(['docker',*args],**kw)
def write(p,x):p.write_text(json.dumps(x,indent=2)+'\n');p.chmod(0o600)
def main():
 p=argparse.ArgumentParser();p.add_argument('--engine',choices=['legacy','camoufox','firefox','chromix'],required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True);a=p.parse_args();os.umask(0o077)
 root=a.output.resolve();assert '/runtime/r6ar-display-persistence-' in str(root);root.mkdir(mode=0o700)
 network='bp-r6ar-'+uuid.uuid4().hex[:8];worker=network+'-worker';client=network+'-client';process=None
 material=Path(tempfile.mkdtemp(prefix='r6ar-display-',dir='/dev/shm'));user,password=str(uuid.uuid4()),str(uuid.uuid4())
 write(material/'binding.json',{'version':1,'session_id':SID,'uid':os.getuid()});salt=os.urandom(16)
 (material/'basic.htpasswd').write_text(user+':{SSHA}'+base64.b64encode(hashlib.sha1(password.encode()+salt).digest()+salt).decode()+'\n');(material/'master-token').touch()
 source=root/'qa';source.mkdir();out=root/'client';out.mkdir();home=root/'home';home.mkdir()
 native=PROJECT/'infra/environment-engines'
 for f in ['qa-browser.py','qa-entrypoint.py','browser_client.py']:shutil.copy2(native/f,source/f)
 shutil.copy2(PROJECT/'infra/firefox-proxy/check-bidi.py',source/'check_bidi.py')
 shutil.copy2(Path(__file__).with_name('display-persistence-client.py'),source/'client.py')
 path=source/'qa-browser.py';path.write_text(path.read_text().replace('https://example.com/','about:blank'))
 autostart=root/'autostart';autostart.write_text('#!/bin/sh\nexec /opt/camoufox-python/bin/python /qa/qa-browser.py\n');autostart.chmod(0o755)
 docker('network','create','--internal','--label','io.browser-platform.qa=r6ar-display',network)
 gateway=json.loads(docker('network','inspect',network).stdout)[0]['IPAM']['Config'][0]['Gateway'];worker_ip=gateway.rsplit('.',1)[0]+'.10';origin='https://'+worker_ip+':29443'
 env={'PUID':str(os.getuid()),'PGID':str(os.getgid()),'SUBFOLDER':'/'+SID+'/','SELKIES_ALLOWED_ORIGINS':origin}
 mounts=[(home,'/config',False),(source,'/qa',True),(material,'/run/browser-platform-session-input',True),(autostart,'/defaults/autostart',True)]
 if a.engine=='legacy':
  image='sha256:895907b7cecf793db5b5b108e9a9ac371d0d381833e729d0b5cc16f8eee8e356'
  env.update(PIXELFLUX_WAYLAND='true',SELKIES_MANUAL_RESOLUTION='false',MAX_RES='3840x2160')
  (home/'qa-profile').mkdir();autostart.write_text('#!/bin/sh\nexec firefox --no-remote --profile /config/qa-profile --remote-debugging-port 9222 --new-window about:blank\n')
  mounts.append((autostart,'/defaults/autostart_wayland',True))
 else:
  ids={'camoufox':'env-custom-6b606b8041851493-artifact-1','firefox':'env-custom-edee032e99019517','chromix':'chromix-154-en-us-utc-scaling-r1'}
  record=next(x for x in json.loads((PROJECT/'infra/sealskin/config/browser-platform/environment-catalog.json').read_text())['artifacts'] if x['id']==ids[a.engine]);image=record['image']
  for m in record['application']['provider_config']['docker_overrides']['mounts']:
   if m['Target'] in ['/run/browser-platform/environment.json','/run/browser-platform/acceptance.json']:mounts.append((Path(m['Source']),m['Target'],True))
  env.update({x['name']:x['value'] for x in record['application']['provider_config']['env']});env['SELKIES_ALLOWED_ORIGINS']=origin
 cmd=['run','-d','--name',worker,'--label','io.browser-platform.qa=r6ar-display','--network',network,'--ip',worker_ip,'--memory','1536m','--cpus','1.5','--pids-limit','512','--shm-size','256m','--cap-drop','NET_ADMIN','--cap-drop','NET_RAW','--security-opt','no-new-privileges:true','--tmpfs','/run/browser-platform-display:rw,nosuid,nodev,noexec,mode=0755,size=1m']
 if a.engine=='chromix':cmd+=['--security-opt','seccomp='+str(PROJECT/'infra/chromix/seccomp.json')]
 for src,dst,ro in mounts:cmd+=['--mount',f'type=bind,src={src},dst={dst}'+(',readonly' if ro else '')]
 for k,v in env.items():cmd+=['-e',k+'='+v]
 write(root/'resources.json',{'network':network,'worker':worker,'client':client,'image':image,'client_image':CLIENT})
 success=False
 try:
  docker(*cmd,image)
  for _ in range(150):
   check=subprocess.run(['docker','exec',worker,'python3','-c','import socket;socket.create_connection(("127.0.0.1",9222),1).close()'],capture_output=True)
   if check.returncode==0:break
   time.sleep(.5)
  else:raise RuntimeError('QA_BROWSER_NOT_READY')
  ip=json.loads(docker('inspect',worker).stdout)[0]['NetworkSettings']['Networks'][network]['IPAddress']
  write(root/'fixture.json',{'Worker':'http://'+ip+':3000','Listen':worker_ip+':29443','User':user,'Password':password,'Mode':a.engine})
  for phase in ['save','restart']:
   for name in ['ready.json','stop']:(root/name).unlink(missing_ok=True)
   log=(root/(phase+'-fixture.log')).open('w');process=subprocess.Popen(['docker','run','--rm','--name',network+'-gateway','--network','container:'+worker,'--user',str(os.getuid()),'--read-only','--tmpfs','/tmp:rw,mode=1777,size=32m','--cap-drop','ALL','--security-opt','no-new-privileges:true','--entrypoint','/fixture-test','--mount',f'type=bind,src={root},dst={root}','--mount',f'type=bind,src={a.fixture.resolve()},dst=/fixture-test,readonly','-e','BP_DISPLAY_FIXTURE='+str(root),CLIENT,'-test.run=^TestUIScalingBrowserFixture$','-test.v','-test.timeout=13m'],stdout=log,stderr=subprocess.STDOUT)
   for _ in range(100):
    if (root/'ready.json').exists():break
    if process.poll() is not None:raise RuntimeError('FIXTURE_START_FAILED')
    time.sleep(.1)
   else:raise RuntimeError('FIXTURE_NOT_READY')
   config={**json.loads((root/'ready.json').read_text()),'engine':'firefox' if a.engine=='legacy' else a.engine,'phase':phase};write(root/'client-input.json',config)
   c=['run','--rm','--name',client,'--network','container:'+worker,'--user',str(os.getuid()),'--read-only','--tmpfs',f'/config:rw,uid={os.getuid()},gid={os.getgid()},mode=0700,size=32m','--tmpfs','/tmp:rw,mode=1777,size=256m','--cap-drop','ALL','--security-opt','no-new-privileges:true','--memory','1024m','--cpus','1','--shm-size','128m','--entrypoint','/opt/camoufox-python/bin/python','--mount',f'type=bind,src={source},dst=/qa,readonly','--mount',f'type=bind,src={out},dst=/qa-output','--mount',f'type=bind,src={root}/client-input.json,dst=/qa-input.json,readonly',CLIENT,'/qa/client.py']
   result=subprocess.run(['docker',*c],capture_output=True,text=True,timeout=240);(root/(phase+'-client.log')).write_text(result.stdout+result.stderr)
   assert result.returncode==0,'REAL_CLIENT_FAILED_'+phase
   (root/'stop').touch();assert process.wait(timeout=15)==0;process=None;log.close()
  success=True
 finally:
  if process is not None:(root/'stop').touch();process.wait(timeout=20)
  logs=subprocess.run(['docker','logs',worker],capture_output=True,text=True);(root/'worker.log').write_text(logs.stdout+logs.stderr)
  # Only task-created disposable QA instances; preserve their Home/evidence.
  subprocess.run(['docker','rm','-f',client],capture_output=True)
  docker('stop','-t','30',worker,timeout=45);docker('rm','-v',worker)
  docker('network','rm',network);shutil.rmtree(material)
  assert subprocess.run(['docker','inspect',worker],capture_output=True).returncode != 0
  assert subprocess.run(['docker','inspect',client],capture_output=True).returncode != 0
  write(root/'result.json',{'result':'PASS' if success else 'FAIL','engine':a.engine,'image':image,'qa_retired':True})
 if success:print('PASS',a.engine,'shared scaling real display, reconnect and Gateway restart')
if __name__=='__main__':main()
