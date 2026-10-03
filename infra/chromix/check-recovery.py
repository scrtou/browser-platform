#!/usr/bin/env python3
"""QA browser close refusal and activation of an independently decrypted Home."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

HERE=Path(__file__).resolve().parent

def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

e=module('chromix_recovery_entry',HERE/'check-entry.py');m=e.m


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--age-dir',type=Path,required=True);p.add_argument('--resume-refusal',action='store_true');args=p.parse_args();os.umask(0o077)
 qa=args.root.resolve();assert qa.name=='qa' and any(scope in qa.parts for scope in ('r6l-chromix-20261001','r6n-auto-20261001'))
 out=qa.parent/'recovery-results';out.mkdir(mode=0o700,exist_ok=args.resume_refusal)
 client=m.network.SecureClient(qa);b=e.migration.Browser(qa);b.login()
 def launch():
  status,_,raw=b.request('GET','/browser/'+m.PROFILE+'/');assert status==200
  fields={k.decode():v.decode() for k,v in re.findall(rb'name="(csrf|launch_plan)" value="([^"]+)"',raw)}
  status,location,_=b.request('POST','/browser/'+m.PROFILE+'/start',fields);assert status in (302,303);e.handoff(qa,location)
  status,snapshot=client.call('GET','/api/profile-runtime/'+m.HOME);assert status==200 and len(snapshot['workers'])==1
  worker=snapshot['workers'][0]['instance_id'];m.workercheck.wait(lambda:m.workercheck.evaluate(worker,'document.body.innerText.includes("network-lifecycle-qa")') is True)
  return worker,snapshot
 def stop():return subprocess.run([str(qa/'bin/profile-adapter'),'-config',str(qa/'adapter-config.json'),'-stop-profile',m.PROFILE],capture_output=True,text=True)
 if args.resume_refusal:
  after=m.read(out/'refused-runtime.json');worker=after['workers'][0]['instance_id']
 else:
  worker,before=launch()
  # A real input event gives the page sticky activation required for beforeunload.
  for kind in ('mousePressed','mouseReleased'):
   m.workercheck.cdp_command(worker,'Input.dispatchMouseEvent',{'type':kind,'x':50,'y':50,'button':'left','clickCount':1})
  assert m.workercheck.evaluate(worker,"window.onbeforeunload=e=>{e.preventDefault();e.returnValue='';};true") is True
  started=time.monotonic();refused=stop();elapsed=time.monotonic()-started
  (out/'refused-stop.log').write_text(refused.stdout+refused.stderr)
  status,after=client.call('GET','/api/profile-runtime/'+m.HOME);m.write(out/'refused-runtime.json',after)
  assert refused.returncode!=0 and elapsed>=10 and status==200
  assert after['workers'][0]['instance_id']==worker and {x['id'] for x in after['resources']}=={x['id'] for x in before['resources']}
 m.network.docker('exec','--user','1000',worker,'xdotool','key','Escape')
 assert m.workercheck.evaluate(worker,'window.onbeforeunload=null;true') is True
 home=qa/'storage/network-qa'/m.HOME
 old_identity=m.read(home/'.chromix/identity.json')
 marker='restored-'+str(time.time_ns())
 expression="""(async()=>{localStorage.setItem('r6l-recovery',MARKER);document.cookie='r6l_recovery='+MARKER+'; Path=/; Max-Age=86400; Secure; SameSite=Lax';let db=await new Promise((ok,fail)=>{let r=indexedDB.open('r6l-recovery',1);r.onupgradeneeded=()=>r.result.createObjectStore('v');r.onsuccess=()=>ok(r.result);r.onerror=()=>fail(r.error)});await new Promise((ok,fail)=>{let t=db.transaction('v','readwrite');t.objectStore('v').put(MARKER,'v');t.oncomplete=ok;t.onerror=()=>fail(t.error)});db.close();return true})()""".replace('MARKER',json.dumps(marker))
 assert m.workercheck.evaluate(worker,expression) is True
 stopped=stop();(out/'normal-stop.log').write_text(stopped.stdout+stopped.stderr);assert stopped.returncode==0
 status,snapshot=client.call('GET','/api/profile-runtime/'+m.HOME);assert status==200 and not any(snapshot[k] for k in ('workers','records','resources'))
 e.migration.HOME=m.HOME
 archive_hash,receipt_hash=e.migration.backup(qa,'chromix-encrypted-home',args.age_dir.resolve())
 backup=qa.parent/'chromix-encrypted-home';restored=backup/'restored-home'
 # Restore permissions from encrypted tar metadata, never from the source Home.
 import tarfile,tempfile
 with tempfile.TemporaryDirectory(prefix='chromix-mode-',dir=out) as raw:
  tarpath=Path(raw)/'home.tar'
  result=subprocess.run([str(args.age_dir.resolve()/'age'),'-d','-i',str(backup/'identity.txt'),'-o',str(tarpath),str(backup/'home.tar.age')],capture_output=True);assert result.returncode==0
  with tarfile.open(tarpath) as archive:
   for member in archive:
    dest=restored/member.name
    assert member.isfile() and dest.resolve().is_relative_to(restored)
    dest.chmod(member.mode & 0o777)
 retained=qa.parent/'chromix-source-retained';home.rename(retained);restored.rename(home)
 m.write(out/'activation.json',{'archive_sha256':archive_hash,'receipt_sha256':receipt_hash,'original_path_retired':True,'scope':'one isolated QA Home; not control-root or independent-host recovery'})
 worker2,_=launch();assert worker2!=worker
 expression="""(async()=>{let db=await new Promise((ok,fail)=>{let r=indexedDB.open('r6l-recovery',1);r.onsuccess=()=>ok(r.result);r.onerror=()=>fail(r.error)});let idb=await new Promise((ok,fail)=>{let r=db.transaction('v').objectStore('v').get('v');r.onsuccess=()=>ok(r.result);r.onerror=()=>fail(r.error)});db.close();return {local:localStorage.getItem('r6l-recovery'),cookie:(document.cookie.split('; ').find(x=>x.startsWith('r6l_recovery='))||'').slice(13),idb}})()"""
 value=m.workercheck.evaluate(worker2,expression);m.write(out/'restored-stores.json',value);assert value==dict(local=marker,cookie=marker,idb=marker)
 assert old_identity==m.read(home/'.chromix/identity.json')
 final=stop();(out/'final-stop.log').write_text(final.stdout+final.stderr);assert final.returncode==0
 m.write(out/'result.json',{'result':'PASS','close_refusal_keeps_worker_home_resources':True,'cancel_and_retry':True,'encrypted_home_independent_restore':True,'source_retired_before_activation':True,'new_worker_three_stores_equal':True,'seed_equal':True,'final_stop':True,'scope':'isolated selected Home recovery; no full control-root or independent-host claim'})
 print('PASS close refusal, retained resources, normal retry and encrypted Home recovery')


if __name__=='__main__':main()
