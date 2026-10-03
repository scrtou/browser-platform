#!/usr/bin/env python3
"""Apply the reviewed local Chromix Adapter/catalog update with guarded rollback.

Requires private frozen deployment-inputs.json and deployment-rollback backups.
Does not create a production browser or rebuild existing Workers.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(args):return subprocess.run(args,capture_output=True,text=True,check=True,timeout=90)
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n');p.chmod(0o600)


def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True);args=parser.parse_args();os.umask(0o077)
 root=args.root.resolve();assert root.name=='r6l-chromix-20261001' and 'runtime' in root.parts
 inputs=json.loads((root/'deployment-inputs.json').read_text());assert inputs['gate']=='passed'
 assert not (root/'deployment-result.json').exists()
 for path,expected in inputs['before'].items():assert sha(Path(path))==expected,path
 binary=Path('/home/sshUser/.local/lib/browser-platform/profile-adapter');config_path=Path(__file__).resolve().parents[1]/'sealskin/adapter-config.json';config=json.loads(config_path.read_text())
 files=[(root/'profile-adapter-final',binary,0o755,'adapter'),(root/'deploy-environment-catalog.json',Path(config['environment_catalog']),0o600,'environment_catalog'),(root/'deploy-template-catalog.json',Path(config['template_catalog']),0o600,'template_catalog')]
 for source,target,mode,key in files:
  assert source.is_file() and sha(source)==inputs['after'][key]
  assert target.is_file() and not target.is_symlink() and target.stat().st_uid==os.getuid()
 profiles=['personal','work','browser-29cbe71eb72b'];before={}
 for profile in profiles:before[profile]=json.loads(run([str(binary),'-config',str(config_path),'-inspect-profile',profile]).stdout)
 write(root/'production-before-deploy-2.json',before)
 try:
  for source,target,mode,_ in files:
   temp=target.with_name(target.name+'.r6l-new');assert not temp.exists();shutil.copyfile(source,temp);temp.chmod(mode);os.replace(temp,target)
  run(['systemctl','--user','restart','profile-adapter.service'])
  deadline=time.monotonic()+40
  while True:
   try:
    request=urllib.request.Request('http://'+config['listen_address']+'/readyz',headers={'Host':urlsplit(config['public_base_url']).netloc})
    with urllib.request.urlopen(request,timeout=3) as response:ready=response.status==200
   except (OSError,urllib.error.URLError):ready=False
   if ready:break
   assert time.monotonic()<deadline,'readiness timeout';time.sleep(.5)
  assert run(['systemctl','--user','is-active','profile-adapter.service']).stdout.strip()=='active'
  after={}
  for profile in profiles:
   after[profile]=json.loads(run([str(binary),'-config',str(config_path),'-inspect-profile',profile]).stdout)
   for key in ['status','session_id','operation_id','records','workers','resources','orphans']:assert before[profile].get(key)==after[profile].get(key),(profile,key)
  write(root/'production-after-deploy.json',after)
 except BaseException:
  for _,target,mode,_ in files:
   source=root/'deployment-rollback'/target.name;assert sha(source)==inputs['before'][str(target)]
   temp=target.with_name(target.name+'.r6l-rollback');shutil.copyfile(source,temp);temp.chmod(mode);os.replace(temp,target)
  run(['systemctl','--user','restart','profile-adapter.service'])
  write(root/('deployment-rollback-'+str(time.time_ns())+'.json'),{'rolled_back':True});raise
 write(root/'deployment-result.json',{'result':'PASS','adapter_sha256':sha(binary),'catalogs_appended':True,'service':'active','readiness_host':urlsplit(config['public_base_url']).netloc,'existing_profile_bindings_preserved':True,'new_production_chromix_home':'not created; user management action remains','controller_unchanged':True})
 print('PASS production Adapter/catalog update and preserved Profile bindings')


if __name__=='__main__':main()
