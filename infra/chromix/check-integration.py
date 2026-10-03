#!/usr/bin/env python3
"""Chromix on an isolated prepared controller: managed DIRECT, stores and stop."""
import argparse
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import uuid

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

network=module('chromix_network',ROOT/'infra/sealskin/lifecycle/check-network-live.py')
workercheck=module('chromix_worker',HERE/'check-worker.py')
work=module('chromix_work',ROOT/'infra/sealskin/checks/check-work-direct.py')
PROFILE='network-qa-chromix'
HOME='network-qa-home-chromix'
APP='network-qa-chromix-app'


def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def read(p):return json.loads(p.read_text())
def write(p,v):network.write_json(p,v)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True);parser.add_argument('--image',required=True);parser.add_argument('--output-name',default='chromix-results');parser.add_argument('--proxy',action='store_true');parser.add_argument('--auto-resolution',action='store_true');args=parser.parse_args();os.umask(0o077)
    qa=args.root.resolve();assert qa.name=='qa' and 'runtime' in qa.parts
    assert args.output_name.startswith('chromix-results') and '/' not in args.output_name
    output=qa.parent/args.output_name;output.mkdir(mode=0o700)
    assert read(qa/'adapter-config.json')['sealskin']['username']=='network-qa'
    controller=json.loads(network.docker('inspect',network.SERVER).stdout)[0]
    assert controller['Config']['Labels']['io.browser-platform.qa']=='network-20260913'
    assert any(m['Source']==str(qa/'storage') and m['Destination']=='/storage' for m in controller['Mounts'])
    client=network.SecureClient(qa);a=read(qa/'admin.json');admin=network.SecureClient(qa,username=a['username'],private=a['private_key'].encode(),public=a['server_public_key'].encode())
    status,current=client.call('GET','/api/profile-runtime/'+HOME)
    if status==200:
        assert not any(current[k] for k in ('records','workers','resources'))
    status,homes=client.call('GET','/api/homedirs');assert status==200
    if HOME not in homes['home_dirs']:
        status,_=client.call('POST','/api/homedirs',{'home_name':HOME});assert status==201
    images=read(qa/'images.json');image=args.image
    spec={'schemaVersion':'browser-platform/chromix-environment/v1','id':'chromix-qa','revision':1,'browserVersion':'154.0.8037.57','locale':'en-US','timezone':'UTC','screen':{'width':1280,'height':720,'dpr':1}}
    if args.auto_resolution:spec['screen']['mode']='auto'
    artifact=output/'environment.json';write(artifact,spec);artifact_sha=hashlib.sha256(artifact.read_bytes()).hexdigest()
    policy={'username':'network-qa','profile_id':PROFILE,'home_name':HOME,'application_id':APP,'mode':'direct','approved_resolver_id':'r6l-public-resolver-v1','approved_resolver_ip':'1.1.1.1','relay_image':images['relay'],'probe_image':images['probe'],'upstream_host':'','upstream_port':0,'username_file':'','username_sha256':'','password_file':'','password_sha256':'','probe_url':'https://example.com/','probe_ca_file':'','probe_ca_sha256':'','probe_timeout_seconds':10}
    if args.proxy:
        registry=read(qa/'config/.config/sealskin/profile-network-policies.json')
        policy=copy.deepcopy(registry['policies']['network-qa-socks-a-r1'])
        policy.update(profile_id=PROFILE,home_name=HOME,application_id=APP)
    url='https://probe.qa.invalid/' if args.proxy else 'https://example.com/'
    pid='r6l-'+('proxy-' if args.proxy else 'direct-')+uuid.uuid4().hex[:8];revision=digest(policy)
    registry=read(qa/'config/.config/sealskin/profile-network-policies.json');registry['policies'][pid]=policy;write(qa/'config/.config/sealskin/profile-network-policies.json',registry)
    allow=read(qa/'allow.json');allow['images'].append(image);allow['readonly_sources'] += [str(artifact),str(HERE/'qa-browser.py')];write(qa/'allow.json',allow)
    app=read(qa/'app-a.json');app.update(id=APP,name='Chromix QA',source_app_id=APP)
    env={'BROWSER_PLATFORM_ENVIRONMENT_ID':'chromix-qa','BROWSER_PLATFORM_ARTIFACT_SHA256':artifact_sha,'PIXELFLUX_WAYLAND':'false','TZ':'UTC','SELKIES_MANUAL_WIDTH':'1280','SELKIES_MANUAL_HEIGHT':'720','SELKIES_ALLOWED_ORIGINS':'https://entry.r5d.test:29443'}
    if args.auto_resolution:
        env.pop('SELKIES_MANUAL_WIDTH');env.pop('SELKIES_MANUAL_HEIGHT');env['MAX_RES']='3840x2160'
    if args.proxy:
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        cert=x509.load_pem_x509_certificate((qa/'mock-server.pem').read_bytes())
        spki=cert.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
        env['CHROMIX_QA_SPKI']=base64.b64encode(hashlib.sha256(spki).digest()).decode()
    provider=app['provider_config'];provider.update(image=image,autostart=True,network_policy_id=pid,network_policy_sha256=revision,env=[{'name':k,'value':v} for k,v in env.items()],custom_autostart_script_b64=base64.b64encode(b'#!/bin/sh\nexec python3 /opt/chromix-qa/qa-browser.py\n').decode())
    provider['docker_overrides']={'mem_limit':'1200m','nano_cpus':1500000000,'pids_limit':512,'shm_size':'256m','security_opt':['no-new-privileges:true','seccomp='+json.dumps(read(HERE/'seccomp.json'),separators=(',',':'))],'mounts':[{'Type':'bind','Source':str(src),'Target':dst,'ReadOnly':True} for src,dst in [(artifact,'/run/browser-platform/environment.json'),(HERE/'qa-browser.py','/opt/chromix-qa/qa-browser.py')]]}
    write(output/'app.json',app)
    status,apps=admin.call('GET','/api/admin/apps/installed');assert status==200
    existing=next((a for a in apps if a['id']==APP),None)
    if existing:
        assert existing['users']==['network-qa'] and existing['source']=='QA'
        status,value=admin.call('PUT','/api/admin/apps/installed/'+APP,app)
        write(output/'replace.json',{'status':status,'value':value});assert status==200
    else:
        result=subprocess.run([str(qa/'bin/sealskin-install-app'),'--admin-config',str(qa/'admin.json'),'--api-base-url','http://127.0.0.1:28110','--definition',str(output/'app.json')],capture_output=True,text=True);(output/'install.log').write_text(result.stdout+result.stderr);assert result.returncode==0

    def launch(label):
        req={'url':url,'application_id':APP,'home_name':HOME,'profile_id':PROFILE,'operation_id':uuid.uuid4().hex,'network_policy_id':pid,'network_policy_sha256':revision,'language':'en_US.UTF-8','timezone':'UTC','wayland_mode':False,'launch_in_room_mode':False}
        write(output/(label+'-request.json'),req)
        status,value=client.call('POST','/api/launch/url',req);write(output/(label+'-launch.json'),{'status':status,'value':value});assert status==200
        status,snapshot=client.call('GET','/api/profile-runtime/'+HOME);assert status==200 and len(snapshot['workers'])==1
        worker=snapshot['workers'][0]['instance_id'];write(output/(label+'-runtime.json'),snapshot)
        workercheck.wait(lambda:workercheck.evaluate(worker,'document.body.innerText.includes("network-lifecycle-qa")' if args.proxy else 'document.title==="Example Domain"') is True,seconds=90)
        return req,worker

    def stop(req):
        body={k:req[k] for k in ('profile_id','operation_id','application_id','network_policy_id','network_policy_sha256')};body['bootstrap_url']=req['url']
        status,value=client.call('POST','/api/profile-runtime/'+HOME+'/stop',body);write(output/'last-stop.json',{'status':status,'value':value});assert status==204
        status,snapshot=client.call('GET','/api/profile-runtime/'+HOME);assert status==200 and not any(snapshot[k] for k in ('records','workers','resources'))

    req,worker=launch('first')
    if args.auto_resolution:workercheck.check_native_screen(worker,output)
    status,health=client.call('GET','/api/profile-runtime/'+HOME+'/health?upstream=true');write(output/'health.json',health)
    assert status==200 and health['network']['mode']==('proxy_required' if args.proxy else 'direct') and health['network']['worker_namespace'] and health['network']['upstream']['status']=='pass'
    bypass=work.raw_bypass(network,worker);assert not any(bypass.values());write(output/'bypass.json',bypass)
    marker=uuid.uuid4().hex
    expression="""(async()=>{localStorage.setItem('r6l',MARKER);document.cookie='r6l='+MARKER+'; Path=/; Max-Age=86400; Secure; SameSite=Lax';let db=await new Promise((ok,fail)=>{let r=indexedDB.open('r6l',1);r.onupgradeneeded=()=>r.result.createObjectStore('v');r.onsuccess=()=>ok(r.result);r.onerror=()=>fail(r.error)});await new Promise((ok,fail)=>{let t=db.transaction('v','readwrite');t.objectStore('v').put(MARKER,'v');t.oncomplete=ok;t.onerror=()=>fail(t.error)});db.close();return true})()""".replace('MARKER',json.dumps(marker))
    assert workercheck.evaluate(worker,expression) is True
    ident=read(qa/'storage/network-qa'/HOME/'.chromix/identity.json');write(output/'identity-before.json',ident)
    stop(req)
    req2,worker2=launch('second');assert worker!=worker2
    expression="""(async()=>{let db=await new Promise((ok,fail)=>{let r=indexedDB.open('r6l',1);r.onsuccess=()=>ok(r.result);r.onerror=()=>fail(r.error)});let v=await new Promise((ok,fail)=>{let r=db.transaction('v').objectStore('v').get('v');r.onsuccess=()=>ok(r.result);r.onerror=()=>fail(r.error)});db.close();return {local:localStorage.getItem('r6l'),cookie:(document.cookie.split('; ').find(x=>x.startsWith('r6l='))||'').slice(4),idb:v}})()"""
    value=workercheck.evaluate(worker2,expression);write(output/'storage-after.json',value);assert value==dict(local=marker,cookie=marker,idb=marker)
    assert ident==read(qa/'storage/network-qa'/HOME/'.chromix/identity.json')
    status,snapshot=client.call('GET','/api/profile-runtime/'+HOME);relay=next(x['id'] for x in snapshot['resources'] if x['kind']=='relay')
    if args.proxy:
        write(qa/'upstream/upstream-mode.json',{'mode':'offline'})
    else:
        network.docker('stop','-t','5',relay)
    bypass=work.raw_bypass(network,worker2);assert not any(bypass.values());write(output/'gateway-failure-bypass.json',bypass)
    stop(req2)
    if args.proxy:
        write(qa/'upstream/upstream-mode.json',{})
    write(output/'result.json',{'result':'PASS','image':image,'public_https':not args.proxy,'managed_direct':not args.proxy,'authenticated_proxy_https':args.proxy,'no_bypass':True,'gateway_failure_no_bypass':True,'normal_stop_new_generation_stores':3,'seed_preserved':True,'final_runtime_resources':0,'scope':'isolated controller API; QA-only exact leaf SPKI for private HTTPS in proxy mode; authenticated entry pending'})
    print('PASS managed DIRECT, real HTTPS, three stores, stable seed, gateway failure and cleanup')


if __name__=='__main__':main()
