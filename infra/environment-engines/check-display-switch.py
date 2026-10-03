#!/usr/bin/env python3
"""Reuse an isolated, accepted Home across display A -> B -> A, then compare."""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid
qa_spec=importlib.util.spec_from_file_location('native_desktop_qa',Path(__file__).with_name('acceptance.py'))
qa=importlib.util.module_from_spec(qa_spec);qa_spec.loader.exec_module(qa)

p=argparse.ArgumentParser();p.add_argument('--integration',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();os.umask(0o077)
root=a.output.resolve();assert 'runtime' in root.parts;root.mkdir(mode=0o700)
sys.path.insert(0,str(qa.PROJECT/'infra/camoufox'))
s=importlib.util.spec_from_file_location('runner',qa.PROJECT/'infra/camoufox/environment-job.py');runner=importlib.util.module_from_spec(s);s.loader.exec_module(runner)
def invariant(o):
    v={k:x for k,x in o.items() if k not in ('screen','window')}
    v['screenDepth']={k:x for k,x in o['screen'].items() if k in ('colorDepth','pixelDepth')}
    return v
results=[]
entries=json.loads((a.integration/'environment-catalog.json').read_bytes())['artifacts']
for engine in ('camoufox','chromix','firefox'):
    paths=sorted([Path(next(m['Source'] for m in entry['application']['provider_config']['docker_overrides']['mounts'] if m['Target'].endswith('/environment.json'))) for entry in entries if entry['browser_engine']==engine],key=lambda f:qa.normalize(json.loads(f.read_bytes()))['screen'].get('mode')=='auto')
    assert len(paths)==2
    specs=[qa.normalize(json.loads(f.read_bytes())) for f in paths]
    reports=[json.loads(f.with_name('acceptance.json').read_bytes()) for f in paths]
    assert all(v['status']=='pass' for v in reports)
    auto=next(i for i,spec in enumerate(specs) if spec['screen'].get('mode')=='auto')
    baseline=invariant(reports[auto]['observations'][0]['observed'])
    assert specs[0].get('seed')==specs[1].get('seed')
    out=root/engine;out.mkdir(mode=0o700)
    accepted=paths[auto].parent/'native-qa';home=out/'home';shutil.copytree(accepted/'home-A',home,symlinks=True)
    shutil.copy2(accepted/'autostart',out/'autostart');shutil.copytree(accepted/'qa-source',out/'qa-source')
    material=Path(tempfile.mkdtemp(prefix='native-display-',dir='/dev/shm'));auth=[str(uuid.uuid4()) for _ in range(3)];sid,user,password=auth
    qa.write(material/'binding.json',{'version':1,'session_id':sid,'uid':os.getuid()});salt=os.urandom(16)
    (material/'basic.htpasswd').write_text(user+':{SSHA}'+base64.b64encode(hashlib.sha1(password.encode()+salt).digest()+salt).decode()+'\n');(material/'master-token').write_text('')
    try:
        with runner.Fixture('job-'+uuid.uuid4().hex[:16],specs[0]['runtimeImageDigest']) as fixture:
            observed=[]
            for iteration,index in enumerate((0,1,0),start=20):
                v=qa.run_one(specs[index],paths[index].resolve(),home,out,fixture.networks['internal'],'A',iteration,auth,material,verify_input=True,accepted_entrypoint=True)
                assert invariant(v['observed'])==baseline
                observed.append(v)
            qa.write(out/'observations.json',observed)
        results.append({'engine':engine,'result':'PASS','sequence':[s['screen'] for s in (specs[0],specs[1],specs[0])],'stores_preserved':True,'non_display_equal':True})
    finally:
        if not qa.docker('ps','-aq','--filter','label=io.browser-platform.qa=native-generation').stdout.strip():shutil.rmtree(material)
qa.write(root/'result.json',{'result':'PASS','cases':results});print('PASS three engines same-Home fixed -> auto -> fixed')
