#!/usr/bin/env python3
"""Resume each native engine after interrupted and failed catalog publication."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
from unittest.mock import patch

p=argparse.ArgumentParser();p.add_argument('--integration',type=Path,required=True);p.add_argument('--runner',type=Path,required=True);p.add_argument('--targets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();os.umask(0o077)
root=a.output.resolve();assert 'runtime' in root.parts;root.mkdir(mode=0o700)
sys.path.insert(0,str(a.runner.resolve().parent));spec=importlib.util.spec_from_file_location('recovery_runner',a.runner);runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
import native_jobs
original=a.integration.resolve();cases=[]
entries=json.loads((original/'environment-catalog.json').read_bytes())['artifacts']
for engine in ('camoufox','chromix','firefox'):
    selected=[entry for entry in entries if entry['browser_engine']==engine and entry['screen']=='auto@system']
    assert len(selected)==1
    request=json.loads((original/'jobs/queue'/(selected[0]['job_id']+'.json')).read_bytes())
    job=request['job_id'];env=request['spec']['id']
    assert json.loads((original/'jobs/status'/(job+'.json')).read_bytes())['status']=='accepted'
    for case in ('interrupt','failed-publish'):
        out=root/(engine+'-'+case);out.mkdir(mode=0o700);spool=runner.Spool(out/'jobs')
        for directory in ('templates','fingerprint-cache'):shutil.copytree(original/'jobs'/directory,spool.root/directory)
        artifact=spool.root/'artifacts'/env;artifact.mkdir(mode=0o700)
        for name in ('environment.json','acceptance.json'):shutil.copy2(original/'jobs/artifacts'/env/name,artifact/name)
        shutil.copy2(original/'jobs/queue'/(job+'.json'),spool.root/'queue'/(job+'.json'))
        catalog=json.loads((original/'template-catalog.json').read_bytes());catalog['display_templates']=[];catalog['compatibility']=[]
        runner.write_private(out/'template-catalog.json',runner.encode(catalog))
        args=SimpleNamespace(image='',recreations=10,min_free_mib=0,catalog=out/'environment-catalog.json',template_catalog=out/'template-catalog.json',native_targets=a.targets.resolve(),session_origin='https://entry.r6r.test',username='r6r-qa',clipboard_addon=None,store='SealSkin Apps',template='Default',browser_template_id='camoufox-linux-v152',verify_in_image=True)
        before={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in artifact.glob('*.json')}
        error=KeyboardInterrupt if case=='interrupt' else OSError('injected publication error')
        with patch.object(native_jobs,'publish_compatibility',side_effect=error):
            if case=='interrupt':
                try:runner.run_next(spool,args,runner.load_prepare())
                except KeyboardInterrupt:pass
                else:raise AssertionError('interruption missed')
            else:assert runner.run_next(spool,args,runner.load_prepare())=='failed'
        partial=args.catalog.read_bytes();assert not json.loads(args.template_catalog.read_bytes())['compatibility']
        if case=='failed-publish':args.retry_job=job
        assert runner.run_next(spool,args,runner.load_prepare())=='accepted'
        assert args.catalog.read_bytes()==partial
        assert before=={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in artifact.glob('*.json')}
        assert len(json.loads(args.template_catalog.read_bytes())['compatibility'])==1
        cases.append({'engine':engine,'case':case,'result':'PASS','artifact_report_preserved':True})
runner.write_private(root/'result.json',runner.encode({'result':'PASS','cases':cases}));print('PASS six automatic publication recovery cases')
