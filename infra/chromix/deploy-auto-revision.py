#!/usr/bin/env python3
"""Apply reviewed R6N catalogs and minimal Adapter without rebuilding Workers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request
from urllib.parse import urlsplit

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def run(args):return subprocess.check_output(args,text=True,stderr=subprocess.PIPE,timeout=90)
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n');p.chmod(0o600)
def replace(source,target,mode):
 temp=target.with_name(target.name+'.r6n-new');assert not temp.exists()
 shutil.copyfile(source,temp);temp.chmod(mode);os.replace(temp,target)
def containers():
 ids=run(['docker','ps','-q']).split()
 return {v['Id']:v['State']['StartedAt'] for v in json.loads(run(['docker','inspect',*ids]))}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True,type=Path);a=p.parse_args();os.umask(0o077)
 r=a.root.resolve();assert r.name=='r6n-auto-20261001' and 'runtime' in r.parts
 assert not (r/'deployment.json').exists()
 repo=Path(__file__).resolve().parents[2];config=repo/'infra/sealskin/adapter-config.json';cfg=read(config)
 binary=Path('/home/sshUser/.local/lib/browser-platform/profile-adapter');directory=Path(cfg['profile_directory'])
 catalog=r/'catalog-release';inputs=read(catalog/'inputs.json')
 assert inputs['release_gate']=='passed' and read(catalog/'acceptance.json')['managementRecoveryReleaseGate']=='passed'
 expected=read(r/'deployment-inputs.json')
 for name,digest in expected['files'].items():assert sha(Path(name))==digest,name
 assert sha(binary)==read(repo/'infra/sealskin/runtime/r6m-display-20261001/deployment.json')['adapter_sha256']
 files=[(r/'profile-adapter',binary,0o755),(catalog/'environment-catalog.json',Path(cfg['environment_catalog']),0o600),(catalog/'template-catalog.json',Path(cfg['template_catalog']),0o600)]
 assert inputs['environment_catalog_before']==sha(files[1][1]) and inputs['template_catalog_before']==sha(files[2][1])
 for source,target,_ in files:
  assert target.is_file() and not target.is_symlink() and target.stat().st_uid==os.getuid()
  assert sha(source)==expected['candidates'][str(source)]
 # Exact append-only catalog diff: preserve all existing entries and order.
 old,new=read(files[1][1]),read(files[1][0]);assert new['artifacts'][:-1]==old['artifacts']
 old,new=read(files[2][1]),read(files[2][0]);assert new['browser_templates']==old['browser_templates'] and new['display_templates'][:-1]==old['display_templates'] and new['compatibility'][:-1]==old['compatibility']
 before=containers();profile_hash=sha(directory);backup=r/'deployment-backup';backup.mkdir(mode=0o700)
 for _,target,_ in files:shutil.copy2(target,backup/target.name)
 write(r/'deployment-before.json',{'containers':before,'profile_directory_sha256':profile_hash,'files':expected['files']})
 try:
  for source,target,mode in files:replace(source,target,mode)
  run(['systemctl','--user','restart','profile-adapter.service'])
  deadline=time.monotonic()+40
  while True:
   try:
    req=urllib.request.Request('http://'+cfg['listen_address']+'/readyz',headers={'Host':urlsplit(cfg['public_base_url']).netloc})
    with urllib.request.urlopen(req,timeout=3) as response:assert response.status==200
    break
   except Exception:
    if time.monotonic()>deadline:raise
    time.sleep(.5)
  assert run(['systemctl','--user','is-active','profile-adapter.service']).strip()=='active'
  assert containers()==before,'Worker/container state changed during deployment'
  assert sha(directory)==profile_hash,'User directory changed; preserve changes and inspect'
 except BaseException:
  # New resolution_mode can be present in records or history after a user write.
  # Never downgrade or overwrite a directory changed after our baseline.
  if sha(directory)!=profile_hash:
   write(r/'rollback-held.json',{'reason':'Profile directory changed; retain compatible binary and user changes'});raise
  if any(sha(target)!=sha(source) for source,target,_ in files):
   write(r/'rollback-held.json',{'reason':'Deployment targets changed; manual reconciliation required'});raise
  for _,target,mode in files:replace(backup/target.name,target,mode)
  run(['systemctl','--user','restart','profile-adapter.service'])
  write(r/'rollback.json',{'restored':True});raise
 write(r/'deployment.json',{'result':'PASS','adapter_sha256':sha(binary),'image':inputs['image'],'catalogs_appended':True,'containers_preserved':True,'profile_directory_preserved':True,'production_mode_switch':'not performed'})
 print('PASS automatic-resolution template deployed; existing Workers preserved')

if __name__=='__main__':main()
