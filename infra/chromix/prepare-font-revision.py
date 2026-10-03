#!/usr/bin/env python3
"""Prepare a CJK-only revision from an installed R6L catalog and differential QA.

Does not publish catalogs or modify a live browser. Old evidence remains scoped
 to the base image; this revision adds font rendering and standalone Worker QA.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess

BASE='sha256:cd521d91037af114833f9df994e3242c4d6078859212909c586b412da660a3ae'
HERE=Path(__file__).resolve().parent

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n');p.chmod(0o600)
def inspect(image):return json.loads(subprocess.check_output(['docker','image','inspect',image],text=True))[0]

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--environment-catalog',type=Path,required=True);p.add_argument('--template-catalog',type=Path,required=True)
 p.add_argument('--qa',type=Path,required=True);p.add_argument('--image',required=True);p.add_argument('--output',type=Path,required=True)
 a=p.parse_args();os.umask(0o077)
 worker=read(a.qa/'result.json');fonts=read(a.qa/'fonts-result.json')
 assert worker['result']=='PASS' and worker['qa_removed'] and worker['image']==a.image
 assert fonts['result']=='PASS' and fonts['expected']=='present' and fonts['input_value_preserved']
 old_image,new_image=inspect(BASE),inspect(a.image)
 assert new_image['RootFS']['Layers'][:len(old_image['RootFS']['Layers'])]==old_image['RootFS']['Layers']
 assert new_image['Config']['Labels']['io.browser-platform.chromix-font-revision']=='cjk-r2'
 environments=read(a.environment_catalog);templates=read(a.template_catalog)
 source=next(x for x in environments['artifacts'] if x['id']=='chromix-154-en-us-utc-1280-r1')
 assert source['image']==BASE and source['status']=='accepted'
 entry=copy.deepcopy(source);old_mounts=source['application']['provider_config']['docker_overrides']['mounts']
 old_spec=read(Path(next(m['Source'] for m in old_mounts if m['Target']=='/run/browser-platform/environment.json')))
 spec=copy.deepcopy(old_spec);spec.update(id='chromix-154-en-us-utc-1280-cjk-r2',revision=2)
 assert not any(x['id']==spec['id'] for x in environments['artifacts'])
 out=a.output.resolve();out.mkdir(mode=0o700)
 write(out/'environment.json',spec)
 receipt={'schemaVersion':'browser-platform/chromix-acceptance/v1','status':'pass','phase':'font-delta','artifactSHA256':sha(out/'environment.json'),'runtimeImageDigest':a.image,'baseImageDigest':BASE,'baseAcceptanceSHA256':source['acceptance_sha256'],'fontLockSHA256':sha(HERE/'fonts.lock.json'),'scope':'CJK font configuration only: real X11 simplified/traditional/mixed text and inserted input, exact font attribution, display authentication and graceful stop. Network and storage integration evidence inherited from unchanged base, not rerun; target client and existing Home migration pending.','evidence':{n:sha(a.qa/n) for n in ['result.json','fonts-result.json','cjk-rendering.png']}}
 write(out/'acceptance.json',receipt)
 entry.update(id=spec['id'],sha256=sha(out/'environment.json'),acceptance_sha256=sha(out/'acceptance.json'),image=a.image,template_revision=2)
 provider=entry['application']['provider_config'];provider['image']=a.image
 values={'BROWSER_PLATFORM_ENVIRONMENT_ID':spec['id'],'BROWSER_PLATFORM_ARTIFACT_SHA256':entry['sha256'],'BROWSER_PLATFORM_ACCEPTANCE_SHA256':entry['acceptance_sha256'],'BROWSER_PLATFORM_RUNTIME_IMAGE_DIGEST':a.image}
 for v in provider['env']:
  if v['name'] in values:v['value']=values[v['name']]
 for mount in provider['docker_overrides']['mounts']:
  if mount['Target'] in ['/run/browser-platform/environment.json','/run/browser-platform/acceptance.json']:mount['Source']=str(out/Path(mount['Target']).name)
 environments['artifacts'].insert(0,entry)
 combo=copy.deepcopy(next(c for c in templates['compatibility'] if c['environment_artifact_id']==source['id']));combo['environment_artifact_id']=spec['id'];templates['compatibility'].insert(0,combo)
 write(out/'environment-catalog.candidate.json',environments);write(out/'template-catalog.candidate.json',templates)
 write(out/'inputs.json',{'environment_catalog_before':sha(a.environment_catalog),'template_catalog_before':sha(a.template_catalog),'base':BASE,'image':a.image,'font_lock':sha(HERE/'fonts.lock.json')})
 print('PASS CJK catalog candidate prepared; production catalogs unchanged')

if __name__=='__main__':main()
