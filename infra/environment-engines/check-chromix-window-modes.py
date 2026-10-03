#!/usr/bin/env python3
"""Check geometry and real input while reusing an isolated accepted Chromix Home."""
import argparse
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

HERE=Path(__file__).resolve().parent


def module(name,path):
    source=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(source);source.loader.exec_module(value)
    return value


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifact',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();os.umask(0o077)
    qa=module('window_mode_qa',HERE/'acceptance.py')
    sys.path.insert(0,str(qa.PROJECT/'infra/camoufox'))
    runner=module('window_mode_runner',qa.PROJECT/'infra/camoufox/environment-job.py')
    import native_jobs
    path=a.artifact.resolve();spec=json.loads(path.read_bytes())
    report=native_jobs.accepted(path.with_name('acceptance.json'),path,spec['runtimeImageDigest'])
    assert '/chromix-' in spec['schemaVersion'] and spec['screen']=={'width':1920,'height':1080,'dpr':1}
    root=a.output.resolve();assert 'runtime' in root.parts;root.mkdir(mode=0o700)
    accepted=path.parent/'native-qa';home=root/'home'
    shutil.copytree(accepted/'home-A',home,symlinks=True)
    shutil.copytree(accepted/'qa-source',root/'qa-source');shutil.copy2(accepted/'autostart',root/'autostart')
    material=Path(tempfile.mkdtemp(prefix='geometry-display-',dir='/dev/shm'))
    auth=[str(uuid.uuid4()) for _ in range(3)];sid,user,password=auth;salt=os.urandom(16)
    qa.write(material/'binding.json',{'version':1,'session_id':sid,'uid':os.getuid()})
    (material/'basic.htpasswd').write_text(user+':{SSHA}'+base64.b64encode(hashlib.sha1(password.encode()+salt).digest()+salt).decode()+'\n')
    (material/'master-token').write_text('')
    def stable(value):
        return {k:v for k,v in value.items() if k not in ('screen','window','deviceScaleFactor')}
    baseline=stable(report['observations'][0]['observed']);results=[]
    try:
        with runner.Fixture('job-'+uuid.uuid4().hex[:16],spec['runtimeImageDigest']) as fixture:
            for index,(name,width,height) in enumerate([('full',1920,1080),('small',1000,800),('wide',1920,800),('tall',1000,1080),('auto',1280,720),('full-again',1920,1080)],start=20):
                value=copy.deepcopy(spec);value['window']={'width':width,'height':height}
                if name=='auto':value['screen']={'width':width,'height':height,'mode':'auto','dpr':'system'}
                artifact=path if name.startswith('full') else root/(name+'.json')
                if artifact!=path:qa.write(artifact,value)
                observed=qa.run_one(value,artifact,home,root,fixture.networks['internal'],'A',index,auth,material,
                                    verify_input=True,accepted_entrypoint=artifact==path)
                assert stable(observed['observed'])==baseline, 'NON_DISPLAY_DRIFT'
                results.append({'mode':name,**observed});qa.write(root/'observations.json',results)
                print(name,'PASS',flush=True)
        qa.write(root/'result.json',{'result':'PASS','cases':len(results),'same_home':True,'input':True,'storage':True,'non_display_stable':True})
    finally:
        if not qa.docker('ps','-aq','--filter','label=io.browser-platform.qa=native-generation').stdout.strip():shutil.rmtree(material)


if __name__=='__main__':main()
