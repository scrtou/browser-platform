#!/usr/bin/env python3
"""Prepare append-only UI scaling revision, with explicit incremental evidence.

R6N network/lifecycle evidence is inherited, never represented as a new run.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess

BASE='sha256:e7e71db14431fa944b0593b5160104ecf61565b756e82cbeaf86f075b6b0af29'
ID='chromix-154-en-us-utc-scaling-r1'
def read(p): return json.loads(p.read_bytes())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v): p.write_text(json.dumps(v,indent=2)+'\n');p.chmod(0o600)
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['root','environment-catalog','template-catalog','worker']:p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args();os.umask(0o077)
    r=a.root.resolve();assert r.name=='r6o-scaling-20261001' and 'runtime' in r.parts
    build=read(r/'build/receipt.json');image=build['image'];assert build['base']==BASE
    worker=read(a.worker/'result.json');client=read(a.worker/'client-resize.json');scaling=read(a.worker/'client-scaling.json')
    assert worker['result']=='PASS' and worker['qa_removed'] and worker['image']==image and worker['system_dpi'] and not worker['diagnostic_launcher_bypass']
    assert len(client['samples'])==7 and all(x['click_and_type'] for x in client['samples']) and not client['page_errors']
    assert len(scaling['samples'])==5 and all(x['click_and_type'] and x['remote']['dpr']==x['dpi']/96 for x in scaling['samples'])
    objs=json.loads(subprocess.check_output(['docker','image','inspect',BASE,image]));old,new=objs
    assert new['RootFS']['Layers'][:len(old['RootFS']['Layers'])]==old['RootFS']['Layers']
    assert new['Config']['Labels']['io.browser-platform.chromix-scaling-version']=='1'
    env=read(a.environment_catalog);templates=read(a.template_catalog)
    source=next(x for x in env['artifacts'] if x['id']=='chromix-154-en-us-utc-auto-r1');assert source['image']==BASE
    assert not any(x['id']==ID for x in env['artifacts'])
    out=r/'catalog-release';out.mkdir(mode=0o700)
    spec={'schemaVersion':'browser-platform/chromix-environment/v2','id':ID,'revision':1,'browserVersion':'154.0.8037.57','locale':'en-US','timezone':'UTC','screen':{'width':1280,'height':720,'dpr':'system','mode':'auto'}}
    write(out/'environment.json',spec)
    acceptance={'schemaVersion':'browser-platform/chromix-acceptance/v1','status':'pass','phase':'ui-scaling-incremental','artifactSHA256':sha(out/'environment.json'),'runtimeImageDigest':image,'baseImageDigest':BASE,'baseAcceptanceSHA256':source['acceptance_sha256'],'scope':'Real isolated authenticated Selkies WebSocket UI Scaling 100/150/200 percent, reset, resize, clicks/input, fresh client DPR 1/2, resolution cap, normal close. R6N network, entry, management lifecycle and recovery evidence inherited on unchanged base layers; not rerun for this revision. No target Mac, WebRTC or multi-client concurrency claim.','evidence':{n:sha(a.worker/n) for n in ['result.json','client-resize.json','client-scaling.json']}}
    write(out/'acceptance.json',acceptance)
    entry=copy.deepcopy(source);entry.update(id=ID,sha256=sha(out/'environment.json'),acceptance_sha256=sha(out/'acceptance.json'),image=image,template_revision=4,screen='auto@system')
    provider=entry['application']['provider_config'];provider['image']=image
    values={'BROWSER_PLATFORM_ENVIRONMENT_ID':ID,'BROWSER_PLATFORM_ARTIFACT_SHA256':entry['sha256'],'BROWSER_PLATFORM_ACCEPTANCE_SHA256':entry['acceptance_sha256'],'BROWSER_PLATFORM_RUNTIME_IMAGE_DIGEST':image}
    provider['env']=[x for x in provider['env'] if x['name'] not in values]+[{'name':k,'value':v} for k,v in values.items()]
    for mount in provider['docker_overrides']['mounts']:
        if mount['Target'] in ['/run/browser-platform/environment.json','/run/browser-platform/acceptance.json']:mount['Source']=str(out/Path(mount['Target']).name)
    env['artifacts'].append(entry)
    display={'id':'chromix-x11-scaling-r1','revision':1,'status':'accepted','label':'自动分辨率 + UI 缩放（DPR 随缩放变化）','display_server':'x11','transport':'selkies','screen':'auto@system','scaling':'auto'}
    templates['display_templates'].append(display);templates['compatibility'].append({'browser_template_id':entry['browser_template_id'],'environment_artifact_id':ID,'display_template_id':display['id'],'status':'accepted'})
    write(out/'environment-catalog.json',env);write(out/'template-catalog.json',templates)
    write(out/'inputs.json',{'environment_catalog_before':sha(a.environment_catalog),'template_catalog_before':sha(a.template_catalog),'image':image,'incremental_gate':'passed'})
    print('SCALING_CATALOG_CANDIDATE_READY')
if __name__=='__main__':main()
