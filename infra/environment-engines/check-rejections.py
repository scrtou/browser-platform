#!/usr/bin/env python3
"""Retained artifacts/reports survive failed acceptance and source/target drift."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

p=argparse.ArgumentParser();p.add_argument('--recovery',type=Path,required=True);p.add_argument('--runner',type=Path,required=True);p.add_argument('--targets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();os.umask(0o077)
root=a.output.resolve();assert 'runtime' in root.parts;root.mkdir(mode=0o700)
sys.path.insert(0,str(a.runner.resolve().parent));s=importlib.util.spec_from_file_location('runner',a.runner);runner=importlib.util.module_from_spec(s);s.loader.exec_module(runner)
results=[]
for engine in ('camoufox','chromix','firefox'):
    for case in ('failed-report','source-drift','target-drift','cached-image-drift','catalog-conflict'):
        out=root/(engine+'-'+case);out.mkdir(mode=0o700);original=a.recovery/(engine+'-interrupt')
        shutil.copytree(original/'jobs',out/'jobs');shutil.copy2(original/'template-catalog.json',out/'template-catalog.json')
        request=next((out/'jobs/queue').glob('*.json'));req=json.loads(request.read_bytes());job=req['job_id'];artifact=out/'jobs/artifacts'/req['spec']['id']
        if case=='failed-report':
            v=json.loads((artifact/'acceptance.json').read_bytes());v['status']='failed';runner.write_private(artifact/'acceptance.json',runner.encode(v))
        if case=='source-drift':
            f=out/'jobs/templates/fingerprints'/(req['templates']['fingerprint_id']+'.json');v=json.loads(f.read_bytes());v['timezone']='Asia/Tokyo';runner.write_private(f,runner.encode(v))
        if case=='target-drift':
            f=out/'template-catalog.json';v=json.loads(f.read_bytes());next(b for b in v['browser_templates'] if b['id']==req['generation']['browser_template_id'])['revision']+=1;runner.write_private(f,runner.encode(v))
        if case=='cached-image-drift':
            for f in (out/'jobs/fingerprint-cache').rglob('*.json'):
                v=json.loads(f.read_bytes())
                if 'image' in v:v['image']='sha256:'+'0'*64;runner.write_private(f,runner.encode(v))
        if case=='catalog-conflict':
            runner.write_private(out/'environment-catalog.json',runner.encode({'version':1,'artifacts':[{'id':json.loads((artifact/'environment.json').read_bytes())['id'],'sha256':'different'}]}))
        catalog_before=(out/'environment-catalog.json').read_bytes() if (out/'environment-catalog.json').exists() else None
        before={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in artifact.glob('*.json')}
        runner.write_private(out/'jobs/status'/(job+'.json'),runner.encode({'version':1,'job_id':job,'status':'failed','phase':'failed'}))
        args=SimpleNamespace(image='',recreations=10,min_free_mib=0,catalog=out/'environment-catalog.json',template_catalog=out/'template-catalog.json',native_targets=a.targets.resolve(),retry_job=job,session_origin='https://entry.r6r.test',username='r6r-qa',clipboard_addon=None,store='SealSkin Apps',template='Default',browser_template_id='camoufox-linux-v152',verify_in_image=True)
        assert runner.run_next(runner.Spool(out/'jobs'),args,runner.load_prepare())=='failed'
        assert (args.catalog.read_bytes() if args.catalog.exists() else None)==catalog_before
        assert before=={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in artifact.glob('*.json')}
        results.append({'engine':engine,'case':case,'result':'PASS','artifact_report_preserved':True})
runner.write_private(root/'result.json',runner.encode({'result':'PASS','cases':results}));print('PASS fifteen runner rejections with evidence preservation')
