#!/usr/bin/env python3
"""Prepare an automatic-resolution catalog from matching isolated evidence.

Never writes live catalogs. Pending management/recovery gate is QA-only.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess

BASE='sha256:19f20e6ec641f6240cdc238ae041fc16c93515c83b2da1943871026949d3a2e6'

def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n');p.chmod(0o600)
def inspect(image):return read_json_command(['docker','image','inspect',image])[0]
def read_json_command(cmd):return json.loads(subprocess.check_output(cmd,text=True))

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ['environment-catalog','template-catalog','worker','integration','output']:
  p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--image',required=True)
 p.add_argument('--owner')
 p.add_argument('--release',action='store_true')
 a=p.parse_args();os.umask(0o077)
 worker=read(a.worker/'result.json');client=read(a.worker/'client-resize.json')
 assert worker['result']=='PASS' and worker['qa_removed'] and worker['image']==a.image
 assert worker['auto_resolution'] and worker['client_resize'] and not worker['diagnostic_launcher_bypass']
 assert len(client['samples'])==7 and all(x['click_and_type'] for x in client['samples'][:4])
 assert all(x['remote']['dpr']==1 for x in client['samples']) and not client['page_errors']
 evidence={'worker':sha(a.worker/'result.json'),'client':sha(a.worker/'client-resize.json')}
 for name in ['chromix-results','chromix-results-proxy']:
  root=a.integration/name;r=read(root/'result.json')
  assert r['result']=='PASS' and r['image']==a.image and r['no_bypass'] and r['gateway_failure_no_bypass']
  assert r['normal_stop_new_generation_stores']==3 and r['seed_preserved'] and r['final_runtime_resources']==0
  assert read(root/'environment.json')['screen']['mode']=='auto'
  evidence[name]=sha(root/'result.json')
 entry_report=read(a.integration/'qa/access/result.json')
 assert entry_report['result']=='PASS' and entry_report['session_host_display_handoff'] and entry_report['normal_stop']
 evidence['entry']=sha(a.integration/'qa/access/result.json')
 old,new=inspect(BASE),inspect(a.image)
 assert new['RootFS']['Layers'][:len(old['RootFS']['Layers'])]==old['RootFS']['Layers']
 assert new['Config']['Labels']['io.browser-platform.chromix-auto-version']=='1'
 environments=read(a.environment_catalog);templates=read(a.template_catalog)
 source=next(e for e in environments['artifacts'] if e['id']=='chromix-154-en-us-utc-1280-cjk-r2')
 assert source['image']==BASE and source['status']=='accepted'
 entry=copy.deepcopy(source)
 spec={'schemaVersion':'browser-platform/chromix-environment/v1','id':'chromix-154-en-us-utc-auto-r1','revision':1,'browserVersion':'154.0.8037.57','locale':'en-US','timezone':'UTC','screen':{'width':1280,'height':720,'dpr':1,'mode':'auto'}}
 assert not any(e['id']==spec['id'] for e in environments['artifacts'])
 out=a.output.resolve();out.mkdir(mode=0o700)
 write(out/'environment.json',spec)
 if a.release:
  management=read(a.integration/'management-results/result.json');recovery=read(a.integration/'recovery-results/result.json')
  assert management['result']=='PASS' and management['artifact_sha256']==sha(out/'environment.json')
  assert management['no_debug_endpoint'] and management['independent_home'] and management['normal_stop']
  assert recovery['result']=='PASS' and recovery['close_refusal_keeps_worker_home_resources'] and recovery['new_worker_three_stores_equal'] and recovery['seed_equal'] and recovery['final_stop']
  evidence.update(management=sha(a.integration/'management-results/result.json'),recovery=sha(a.integration/'recovery-results/result.json'))
 receipt={'schemaVersion':'browser-platform/chromix-acceptance/v1','status':'pass','phase':'auto-resolution','artifactSHA256':sha(out/'environment.json'),'runtimeImageDigest':a.image,'baseImageDigest':BASE,'baseAcceptanceSHA256':source['acceptance_sha256'],'managementRecoveryReleaseGate':'passed' if a.release else 'pending','scope':'Chromix/X11 automatic native screen, explicit persistent seeds/default scalars and native GPU; real Selkies resize/click/input/reconnect/client DPR 1 and 2; DIRECT/authenticated proxy/no bypass/normal close and three stores. Not full fingerprint equivalence, Camoufox or target Mac acceptance.','evidence':evidence}
 write(out/'acceptance.json',receipt)
 entry.update(id=spec['id'],sha256=sha(out/'environment.json'),acceptance_sha256=sha(out/'acceptance.json'),image=a.image,template_revision=3,screen='auto@1')
 provider=entry['application']['provider_config'];provider['image']=a.image
 if a.owner:entry['application']['users']=[a.owner]
 values={'BROWSER_PLATFORM_ENVIRONMENT_ID':spec['id'],'BROWSER_PLATFORM_ARTIFACT_SHA256':entry['sha256'],'BROWSER_PLATFORM_ACCEPTANCE_SHA256':entry['acceptance_sha256'],'BROWSER_PLATFORM_RUNTIME_IMAGE_DIGEST':a.image,'MAX_RES':'3840x2160'}
 provider['env']=[v for v in provider['env'] if v['name'] not in set(values)|{'SELKIES_MANUAL_WIDTH','SELKIES_MANUAL_HEIGHT'}]+[{'name':k,'value':v} for k,v in values.items()]
 for mount in provider['docker_overrides']['mounts']:
  if mount['Target'] in ['/run/browser-platform/environment.json','/run/browser-platform/acceptance.json']:mount['Source']=str(out/Path(mount['Target']).name)
 environments['artifacts'].append(entry)
 display={'id':'chromix-x11-auto-r1','revision':1,'status':'accepted','label':'自动分辨率（屏幕随窗口变化）','display_server':'x11','transport':'selkies','screen':'auto@1','scaling':'auto'}
 templates['display_templates'].append(display)
 templates['compatibility'].append({'browser_template_id':entry['browser_template_id'],'environment_artifact_id':spec['id'],'display_template_id':display['id'],'status':'accepted'})
 write(out/'environment-catalog.json',environments);write(out/'template-catalog.json',templates)
 write(out/'inputs.json',{'environment_catalog_before':sha(a.environment_catalog),'template_catalog_before':sha(a.template_catalog),'image':a.image,'release_gate':receipt['managementRecoveryReleaseGate']})
 print('AUTO_CATALOG_CANDIDATE_READY',receipt['managementRecoveryReleaseGate'])

if __name__=='__main__':main()
