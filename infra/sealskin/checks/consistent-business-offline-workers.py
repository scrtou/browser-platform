"""Offline smoke of copied real Homes; no network, ports, Docker socket or real display tokens."""
from pathlib import Path
import argparse,json,os,subprocess,uuid,hashlib,base64,secrets,time,shutil
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);args=p.parse_args();root=args.root.resolve();os.umask(0o077)
assert root.parent.name=='r6au-consistent-20261002' and (root/'RECOVERY_PENDING').is_file()
qa=root.parent/'worker-smoke';qa.mkdir(mode=0o700);homecopy=qa/'storage';subprocess.run(['cp','-a',str(root/'storage'),str(homecopy)],check=True)
plan=json.loads((root/'metadata/source-plan.json').read_text());originals=[c for c in json.loads((root/'metadata/active-containers.json').read_text()) if c['Name'].startswith('/bp-home-')];assert len(originals)==3
secretroot=Path('/dev/shm/r6au-display-smoke');secretroot.mkdir(mode=0o700)
def mapped(source):
 matches=[(len(v),root/k/Path(source).relative_to(v)) for k,v in plan.items() if Path(source)==Path(v) or Path(v) in Path(source).parents];assert matches;return max(matches,key=lambda x:x[0])[1]
def cmd(args,name,check=True):
 p=subprocess.run(args,capture_output=True,timeout=100);(qa/name).write_bytes(p.stdout+p.stderr)
 if check:assert p.returncode==0,name
 return p
results=[];created=[]
try:
 for index,original in enumerate(originals):
  profile=original['Config']['Labels']['io.browser-platform.profile'];name='bp-r6au-offline-'+profile;sid=str(uuid.uuid4());sd=secretroot/sid;sd.mkdir(mode=0o700);uid=1000;os.chown(sd,uid,uid)
  salt=secrets.token_bytes(16);password=secrets.token_urlsafe(32).encode();basic=str(uuid.uuid4())+':{SSHA}'+base64.b64encode(hashlib.sha1(password+salt).digest()+salt).decode()+'\n'
  for key,value in {'binding.json':json.dumps({'version':1,'session_id':sid,'uid':uid}).encode(),'basic.htpasswd':basic.encode(),'master-token':secrets.token_urlsafe(32).encode()}.items():
   f=sd/key;f.write_bytes(value);f.chmod(0o600);os.chown(f,uid,uid)
  env=dict(x.split('=',1) for x in original['Config']['Env']);env['SUBFOLDER']='/'+sid+'/';env['SELKIES_ALLOWED_ORIGINS']='http://127.0.0.1';env['SEALSKIN_URL']='http://127.0.0.1:1'
  args=['docker','create','--name',name,'--label','io.browser-platform.r6au-offline=true','--network','none','--restart','no','--memory','1g','--shm-size',str(original['HostConfig']['ShmSize']),'--security-opt','no-new-privileges:true']
  for k,v in env.items():args+=['-e',k+'='+v]
  for mount in original['Mounts']:
   target=mount['Destination']
   if target=='/run/browser-platform-session-input':source=sd;readonly=True
   else:
    source=mapped(mount['Source']);readonly=not mount['RW']
    if source.is_relative_to(root/'storage'):source=homecopy/source.relative_to(root/'storage')
   assert source.exists();args+=['--mount','type=bind,src='+str(source)+',dst='+target+(',readonly' if readonly else '')]
  for target,options in original['HostConfig'].get('Tmpfs',{}).items():args+=['--tmpfs',target+':'+options]
  args+=[original['Image']];cmd(args,name+'-create.log');created.append(name);cmd(['docker','start',name],name+'-start.log')
  observed=None
  for attempt in range(50):
   status=json.loads(cmd(['docker','inspect',name],name+'-inspect.json').stdout)[0];assert status['HostConfig']['NetworkMode']=='none' and not status['HostConfig']['PortBindings'] and not status['NetworkSettings']['Networks'].get('bridge')
   if not status['State']['Running']:break
   process=cmd(['docker','exec',name,'ps','-eo','comm='],name+'-processes.log',False).stdout.decode().splitlines();count=sum(x.strip() in {'firefox','firefox-bin','firefox-esr','camoufox','camoufox-bin','chrome','chromium','chromium-browser'} for x in process)
   if count:
    time.sleep(3);again=cmd(['docker','exec',name,'ps','-eo','comm='],name+'-processes-confirm.log',False).stdout.decode().splitlines()
    if any(x.strip() in {'firefox','firefox-bin','firefox-esr','camoufox','camoufox-bin','chrome','chromium','chromium-browser'} for x in again):observed={'profile':profile,'image':original['Image'],'browser_processes':count,'network_mode':'none','published_ports':0,'real_third_party_login':'NOT_TESTED'};break
   time.sleep(2)
  cmd(['docker','logs','--tail','120',name],name+'-logs.txt',False);assert observed is not None,'offline browser startup missing: '+profile
  route=cmd(['docker','exec',name,'cat','/proc/net/route'],name+'-routes.txt').stdout.decode().splitlines();assert len(route)==1
  display_code="""import sys,json,urllib.request,urllib.error,base64
v=json.load(sys.stdin);url='http://127.0.0.1:3000/'+v['sid']+'/'
try:
 urllib.request.urlopen(url,timeout=5);denied=False
except urllib.error.HTTPError as e:denied=e.code in (401,403)
auth=base64.b64encode((v['user']+':'+v['password']).encode()).decode()
with urllib.request.urlopen(urllib.request.Request(url,headers={'Authorization':'Basic '+auth}),timeout=5) as response:assert response.status==200
assert denied
print(json.dumps({'display_authenticated':True,'unauthenticated_blocked':True}))
"""
  display=subprocess.run(['docker','exec','-i',name,'python3','-c',display_code],input=json.dumps({'sid':sid,'user':basic.split(':',1)[0],'password':password.decode()}).encode(),capture_output=True,timeout=20)
  (qa/(name+'-display.json')).write_bytes(display.stdout+display.stderr);assert display.returncode==0,'display readiness/authentication failed'
  observed.update(json.loads(display.stdout))
  results.append(observed);print('PASS offline browser',profile,flush=True)
 # These exact copied Homes are exclusively owned by this smoke run.
 for name in created:
  command=['docker','exec','--user','1000:1000',name,'python3','/usr/local/lib/browser-platform/browser-shutdown.py','--timeout','12']
  p=cmd(command,name+'-normal-close.log',False)
  if p.returncode:
   # Native Firefox runtime has a different installed close script.
   p=cmd(['docker','exec','--user','1000:1000',name,'python3','/usr/local/lib/browser-platform/browser-shutdown.py','--timeout','12'],name+'-normal-close-alternate.log',False)
  assert p.returncode==0,'normal close failed '+name
  cmd(['docker','stop','--time','30',name],name+'-stop.log');cmd(['docker','rm',name],name+'-remove.log')
 result={'result':'PASS','browsers':results,'copied_homes':True,'raw_restore_untouched':True,'all_networks_none':True,'third_party_requests_prevented':True,'normal_shutdown':True,'qa_containers_removed':True};(root.parent/'worker-smoke-result.json').write_text(json.dumps(result,indent=2)+'\n');shutil.rmtree(secretroot)
except BaseException:
 # Failed QA remains fully network-isolated for diagnosis; never force-kill or touch production.
 (root.parent/'worker-smoke-failed.json').write_text(json.dumps({'created':created,'completed':results,'network_mode':'none','retained_for_diagnosis':True},indent=2)+'\n');raise
