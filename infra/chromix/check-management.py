#!/usr/bin/env python3
"""Exercise actual Chromix catalog selection and creation through authenticated UI."""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import parse_qs,urlsplit

HERE=Path(__file__).resolve().parent

def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

e=module('chromix_entry',HERE/'check-entry.py');m=e.m


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--catalog',type=Path,required=True);p.add_argument('--verify-only',action='store_true');p.add_argument('--auto-resolution',action='store_true');args=p.parse_args();qa=args.root.resolve();catalog=args.catalog.resolve()
 assert qa.name=='qa' and any(scope in qa.parts for scope in ('r6l-chromix-20261001','r6n-auto-20261001'))
 out=qa.parent/'management-results'
 if args.verify_only:
  return verify(qa,catalog,out,args.auto_resolution)
 out.mkdir(mode=0o700)
 (qa/'config/.config/sealskin').chmod(0o700)
 stage=module('chromix_stage',m.ROOT/'infra/sealskin/checks/stage-entry-auth.py');stage.stop_process(qa,'adapter',qa/'bin/profile-adapter')
 cfg=m.read(qa/'adapter-config.json');cfg.update(profile_directory=str(qa/'profiles.json'),environment_catalog=str(catalog/'environment-catalog.json'),template_catalog=str(catalog/'template-catalog.json'))
 direct=m.read(m.ROOT/'infra/sealskin/adapter-config.json')['direct_template'];direct['owner']='network-qa';cfg['direct_template']=direct
 m.write(qa/'profiles.json',{'version':1,'revision':1,'browsers':[{**cfg['profiles'][0],'revision':1,'status':'ready','updated_at':datetime.now(timezone.utc).isoformat()}]})
 m.write(qa/'adapter-config.json',cfg)
 allow=m.read(qa/'allow.json');allow['readonly_sources'] += [str(catalog/n) for n in ('environment.json','acceptance.json')];m.write(qa/'allow.json',allow)
 stage.start_adapter(qa,qa/'bin/profile-adapter')
 verify(qa,catalog,out,args.auto_resolution)


def verify(qa,catalog,out,auto_resolution=False):
 b=e.migration.Browser(qa);b.login();status,_,raw=b.request('GET','/manage/templates');assert status==200 and b'chromix' in raw
 m.write(out/'templates.json',json.loads(raw))
 account=m.read(qa/'access/account.json')
 fields={'csrf':b.csrf(),'label':'Chromix QA managed creation','start_url':'https://example.com/','browser_template_id':'chromix-linux-154','environment_artifact_id':'chromix-154-en-us-utc-1280-r1','display_template_id':'chromix-x11-1280-r1','network_selection':'direct','idempotency_key':'r6l-create-chromix-qa-1','accounts':account['username']}
 if auto_resolution:fields.update(environment_artifact_id='chromix-154-en-us-utc-auto-r1',display_template_id='chromix-x11-auto-r1')
 status,location,_=b.request('POST','/manage/browsers',fields);m.write(out/'create-response.json',{'status':status,'notice':parse_qs(urlsplit(location).query).get('notice')});assert status==303 and 'created' in location
 directory=m.read(qa/'profiles.json');record=next(r for r in directory['browsers'] if r.get('label')==fields['label']);m.write(out/'created-record.json',record)
 if auto_resolution:assert record['resolution_mode']=='auto'
 b.login()  # Account grant revision changed when the new Profile was assigned.
 if auto_resolution:
  status,_,page=b.request('GET','/manage/');assert status==200
  assert b'value="chromix-154-en-us-utc-auto-r1" selected' in page
  assert b'value="chromix-x11-auto-r1" selected' in page

 profile=record['id'];home=record['home_name'];assert home!=m.HOME and record['browser_template_id']=='chromix-linux-154'
 status,location,raw=b.request('GET','/browser/'+profile+'/');assert status in (200,302,303)
 if status==200:
  launch={k.decode():v.decode() for k,v in re.findall(rb'name="(csrf|launch_plan)" value="([^"]+)"',raw)};assert len(launch)==2
  status,location,_=b.request('POST','/browser/'+profile+'/start',launch);assert status in (302,303)
 e.handoff(qa,location)
 def healthy():
  result=subprocess.run([str(qa/'bin/profile-adapter'),'-config',str(qa/'adapter-config.json'),'-probe-profile',profile],capture_output=True,text=True)
  if result.returncode==0 and json.loads(result.stdout)['overall']=='healthy':
   (out/'health-final.json').write_text(result.stdout);return True
  return False
 m.workercheck.wait(healthy)
 # The final catalog's app must not expose the QA-only debugging transport.
 client=m.network.SecureClient(qa);status,runtime=client.call('GET','/api/profile-runtime/'+home);assert status==200 and len(runtime['workers'])==1
 worker=runtime['workers'][0]['instance_id'];m.write(out/'runtime.json',runtime)
 check=m.network.docker('exec',worker,'python3','-c',"from pathlib import Path; assert not any(a.startswith(b'--remote-debugging') for p in Path('/proc').glob('[0-9]*/cmdline') if p.exists() for a in p.read_bytes().split(b'\\0'))",check=False);assert check.returncode==0
 result=subprocess.run([str(qa/'bin/profile-adapter'),'-config',str(qa/'adapter-config.json'),'-stop-profile',profile],capture_output=True,text=True);(out/'stop.log').write_text(result.stdout+result.stderr);assert result.returncode==0
 m.write(out/'result.json',{'result':'PASS','catalog_selection':True,'recent_auth_creation':True,'independent_home':True,'authenticated_session':True,'fresh_health':'healthy','no_debug_endpoint':True,'normal_stop':True,'profile':profile,'home':home,'artifact_sha256':hashlib.sha256((catalog/'environment.json').read_bytes()).hexdigest()})
 print('PASS real template listing, browser creation, independent Home, Session display and healthy production-style Worker')


if __name__=='__main__':main()
