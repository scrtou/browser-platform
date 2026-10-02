#!/usr/bin/env python3
"""Upgrade/rollback server programs with a pinned native browser and real Home.

This is a server-patch matrix, not a browser-major-version migration claim.
Only a prepared network-qa owner and its synthetic Home are accepted.
"""
import argparse,hashlib,importlib.util,json,os,shutil,subprocess,time,uuid
from pathlib import Path
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('protocols',HERE/'check-proxy-protocols.py');protocols=importlib.util.module_from_spec(s);s.loader.exec_module(protocols)
net=protocols.network
BASE_CONTROLLER='sha256:1d93d6b8a92e7d431a603d4f2778b92aa2e91e8943df25c73f49f9013ef8a40e'
CURRENT_CONTROLLER='sha256:33a6d2fcd00502f6df7b8e75a2b3eaa70c0e933077919cbdda5dbe77d5fb7b57'
BASE_RELAY='sha256:a785d443bf7ede16e0f4728bbcc552a17f6340e6a3fea2d01bd839776716888a'
CURRENT_RELAY='sha256:d57f441789051be7d7a3770d66211f680741a5b413ca8c5dcc765b8ec8bd286d'
BASE_ADAPTER='b9e9832d9c24ed9abf2a4f8fb1d236eb8ba4c2c99562869d8f806d232bfaf288'
CURRENT_ADAPTER='8fb90eb29208ccea7ba235c814b6669470af47ba6c026a5f53c03e9f2cf95393'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n');p.chmod(0o600)
def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--baseline-adapter',type=Path,required=True);p.add_argument('--current-adapter',type=Path,required=True);a=p.parse_args();os.umask(0o077)
 qa=a.root.resolve();assert qa.name=='qa' and qa.parent.parent.name.startswith('r6as-')
 assert sha(a.baseline_adapter)==BASE_ADAPTER and sha(a.current_adapter)==CURRENT_ADAPTER
 out=qa.parent/'program-upgrade';out.mkdir(mode=0o700);m=protocols.Matrix(qa,out/'protocol-state');m.stop()
 original_config=read(qa/'adapter-config.json');entry=read(qa.parent/'entry.json');engine=entry['browser_engine'];process=None;stage='prepare';rows=[]
 allow=read(qa/'allow.json')
 for key in ['images','guard_images']:allow[key]=sorted(set(allow[key]+[BASE_RELAY,CURRENT_RELAY]))
 write(qa/'allow.json',allow)
 def controller(image,label):
  assert image in [BASE_CONTROLLER,CURRENT_CONTROLLER]
  current=json.loads(net.docker('inspect','sealskin-network-qa').stdout)[0]
  assert current['Config']['Labels']['io.browser-platform.qa']=='network-20260913'
  mounts={v['Destination']:v for v in current['Mounts']}
  assert mounts['/config']['Source']==str(qa/'config') and mounts['/storage']['Source']==str(qa/'storage')
  assert set(mounts)<=set(['/config','/storage','/var/run/docker.sock','/run/browser-platform-session-secrets','/run/browser-platform-host/ipv4-fib-trie'])
  if image==BASE_CONTROLLER:
   assert all(not read(p).get('endpoint') for p in (qa/'config/.config/sealskin/profile-network-runtime').glob('*.json'))
  net.docker('stop','-t','10',current['Id']);net.docker('rm',current['Id'])
  cmd=['run','-d','--name','sealskin-network-qa','--label','io.browser-platform.qa=network-20260913','--network','browser-platform-network-qa','--memory','512m','--cpus','1.5','--pids-limit','256','-p','127.0.0.1:28110:8000']
  for e in ['PUID=1000','PGID=1000','TZ=Etc/UTC','HOST_URL=network.invalid']:cmd+=['-e',e]
  for v in mounts.values():assert v['Type']=='bind';cmd+=['-v',v['Source']+':'+v['Destination']+('' if v['RW'] else ':ro')]
  net.docker(*cmd,image);net.wait(lambda:net.request('POST','/api/handshake/initiate')[0]==200,'program matrix controller',seconds=90);m.refresh()
  write(out/(label+'-controller.json'),{'image':image,'home_unchanged':True})
 def stop_adapter():
  nonlocal process
  if process:
   process.terminate();assert process.wait(timeout=30)==0;process=None
 def adapter(binary,label):
  nonlocal process
  assert process is None
  dest=qa/'bin/profile-adapter';temp=dest.with_name('profile-adapter.new');shutil.copy2(binary,temp);temp.chmod(0o755);os.replace(temp,dest)
  log=(out/(label+'-adapter.log')).open('w');process=subprocess.Popen([str(dest),'-config',str(qa/'adapter-config.json')],stdout=log,stderr=subprocess.STDOUT)
  net.wait(lambda:net.request('GET','/healthz',port=29110)[0]==200,'program matrix Adapter',seconds=30);assert process.poll() is None
  assert sha(Path('/proc')/str(process.pid)/'exe')==sha(binary)
 def configure(relay,label):
  m.template['relay_image']=relay;m.configure('socks5','username_password',out/'protocol-state');m.stop()
  cfg=read(qa/'adapter-config.json');cfg['state_file']='program-upgrade-state.json';cfg['profiles']=[{'id':m.info['profile'],'application_id':m.request['application_id'],'home_name':m.info['home'],'start_url':'https://entry.leak.qa.test/test','network_policy_id':m.request['network_policy_id'],'network_policy_sha256':m.request['network_policy_sha256'],'language':entry['locale'].replace('-','_')+'.UTF-8','timezone':entry['timezone']}]
  write(qa/'adapter-config.json',cfg)
 def launch(label):
  cfg=read(qa/'adapter-config.json');status,headers,body=net.request('POST','/browser/'+m.info['profile']+'/start',b'',{'Origin':cfg['public_base_url']},port=29110)
  write(out/(label+'-entry.json'),{'status':status,'headers':headers,'body':body.decode()})
  assert status==303,'ACTUAL_ADAPTER_LAUNCH_FAILED'
  binding=read(qa/'program-upgrade-state.json')['bindings'][m.info['profile']];assert binding['status']=='running'
  m.request.update(operation_id=binding['operation_id'],url=binding['bootstrap_url'])
  stop={key:m.request[key] for key in ['application_id','profile_id','operation_id','network_policy_id','network_policy_sha256']};stop.update(bootstrap_url=binding['bootstrap_url'],session_id=binding['session_id']);write(qa/'browser-stop.json',stop);write(qa/'browser-launch.json',m.request)
  snapshot=m.snapshot();write(out/(label+'-generation.json'),snapshot);worker=snapshot['workers'][0]['instance_id'];m.info['instance_id']=worker;write(qa/'browser-worker.json',m.info)
  ns=importlib.util.spec_from_file_location('native_upgrade',HERE/'native-network-client.py');nm=importlib.util.module_from_spec(ns);ns.loader.exec_module(nm);m.control=nm.NativeDesktop(worker,engine)
  net.wait(lambda:net.docker('exec',worker,'python3','-c','import socket;socket.create_connection(("127.0.0.1",9222),1).close()',check=False).returncode==0,'upgrade browser',seconds=90)
  m.control.navigate('https://entry.leak.qa.test/test');return snapshot
 def stop():
  result=subprocess.run([str(qa/'bin/profile-adapter'),'-config',str(qa/'adapter-config.json'),'-stop-profile',m.info['profile']],text=True,capture_output=True,timeout=120)
  assert result.returncode==0,'NORMAL_ADAPTER_STOP_FAILED';assert not m.snapshot()['resources'];assert read(qa/'program-upgrade-state.json')['bindings'][m.info['profile']]['status']=='stopped'
 def stores(marker=None):
  action=('document.cookie="matrix='+marker+'; Max-Age=31536000; Secure; SameSite=Lax; Path=/";localStorage.setItem("matrix","'+marker+'");' if marker else '')
  expression='(async()=>{'+action+'const db=await new Promise((ok,no)=>{let r=indexedDB.open("r6as-upgrade",1);r.onupgradeneeded=()=>r.result.createObjectStore("values");r.onsuccess=()=>ok(r.result);r.onerror=()=>no(r.error)});'
  if marker:expression+='await new Promise((ok,no)=>{let t=db.transaction("values","readwrite");t.objectStore("values").put("'+marker+'","matrix");t.oncomplete=ok;t.onerror=no});'
  expression+='const value=await new Promise((ok,no)=>{let r=db.transaction("values").objectStore("values").get("matrix");r.onsuccess=()=>ok(r.result);r.onerror=no});db.close();return {cookie:document.cookie.split("; ").find(s=>s.startsWith("matrix="))?.split("=")[1],local:localStorage.getItem("matrix"),indexed:value}})()'
  return m.control.evaluate(expression)
 def identity():
  value=json.loads(net.docker('inspect',m.info['instance_id']).stdout)[0]
  return {'worker':value['Id'],'image':value['Image'],'started':value['State']['StartedAt'],'environment':m.control.evaluate('({ua:navigator.userAgent,platform:navigator.platform,language:navigator.language,languages:navigator.languages,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone,screen:[screen.width,screen.height],dpr:devicePixelRatio})')}
 try:
  controller(BASE_CONTROLLER,'baseline');configure(BASE_RELAY,'baseline');adapter(a.baseline_adapter,'baseline');launch('baseline')
  marker=uuid.uuid4().hex;expected={'cookie':marker,'local':marker,'indexed':marker};assert stores(marker)==expected;before=identity();assert before['image']==entry['image'];write(out/'baseline.json',before)
  stage='live-upgrade';stop_adapter();controller(CURRENT_CONTROLLER,'upgraded');adapter(a.current_adapter,'upgraded');launch('upgraded')
  assert identity()==before and stores()==expected;rows.append({'stage':'live-server-patch-upgrade','result':'PASS','same_worker_and_environment':True,'three_stores':True})
  stage='new-relay-generation';stop();stop_adapter();configure(CURRENT_RELAY,'new-generation');adapter(a.current_adapter,'new-generation');launch('new-generation')
  after=identity();assert after['worker']!=before['worker'] and after['environment']==before['environment'] and stores()==expected;rows.append({'stage':'current-new-relay-generation','result':'PASS','three_stores':True,'environment_preserved':True})
  stage='rollback';stop();stop_adapter();controller(BASE_CONTROLLER,'rollback');configure(BASE_RELAY,'rollback');adapter(a.baseline_adapter,'rollback');launch('rollback')
  assert stores()==expected and identity()['environment']==before['environment'];rows.append({'stage':'server-program-rollback','result':'PASS','three_stores':True,'environment_preserved':True})
  stop();stop_adapter();controller(CURRENT_CONTROLLER,'restore-current')
  shutil.copy2(a.current_adapter,qa/'bin/profile-adapter');write(qa/'adapter-config.json',original_config)
  write(out/'result.json',{'result':'PASS','engine':engine,'browser_image':entry['image'],'cases':rows,'scope':'fixed-browser server patch upgrade and program rollback; browser-major migration is separate'})
  print('PASS',engine,'server upgrade, new Relay generation and rollback')
 except BaseException:
  write(out/'failure.json',{'result':'FAIL','stage':stage,'cases':rows,'qa_retained':True});raise
 finally:stop_adapter()
if __name__=='__main__':main()
