#!/usr/bin/env python3
"""Disposable early engine probe; zero recreations never passes the release gate."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import uuid
p=argparse.ArgumentParser();p.add_argument('--engine',choices=['camoufox','chromix','firefox'],required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--auto',action='store_true');p.add_argument('--small-window',action='store_true');a=p.parse_args()
root=a.output.resolve();assert 'runtime' in root.parts;root.mkdir(mode=0o700)
image=json.loads(a.build.read_bytes())[a.engine]['image']
spec={'schemaVersion':'browser-platform/'+a.engine+'-environment/'+('v3' if a.engine=='chromix' else 'v2'),'id':'native-qa-'+a.engine,'revision':1,'browserVersion':'154.0.8037.57' if a.engine=='chromix' else '155.0.1','locale':'zh-CN','languages':['zh-CN','en-US','en'],'timezone':'Asia/Taipei','screen':{'width':1280,'height':900,'dpr':1},'window':{'width':1280,'height':900},'runtimeImageDigest':image}
if a.engine=='chromix':spec['seed']=123456789
if a.small_window:
    from artifact import SCHEMAS
    spec['schemaVersion']=SCHEMAS[a.engine];spec['window']={'width':1000,'height':800}
if a.auto:
    from artifact import SCHEMAS
    spec['schemaVersion']=SCHEMAS.get(a.engine,'browser-platform/camoufox-environment/v2')
    spec['screen']={'width':1280,'height':720,'dpr':'system','mode':'auto'};spec['window']={'width':1280,'height':720}
if a.engine=='camoufox':
    project=Path(__file__).resolve().parents[2];sys.path.insert(0,str(project/'infra/camoufox'))
    from template_sources import compose
    candidate=next((project/'infra/sealskin/runtime/r6q-engine-neutral-20261001/integration-final/jobs/artifacts').glob('*/environment.json'))
    base=json.loads(candidate.read_bytes());base['runtimeImageDigest']=image;base['runtime']=json.loads(subprocess.check_output(['docker','run','--rm','--network','none','--entrypoint','/opt/camoufox-python/bin/python',image,'-c','import sys,json;sys.path.insert(0,"/usr/local/lib/browser-platform");import environment;print(json.dumps(environment.runtime_metadata()))']));target=base['spec'].copy();target.update(id='env-custom-native-camoufox',screen={'width':1280,'height':720,'mode':'auto','dprMode':'system'},window={'width':1280,'height':720});target['requiredCapabilities']=[{'fixed-screen':'auto-screen','fixed-dpr':'system-dpr'}.get(x,x) for x in target['requiredCapabilities']];spec=compose(base,target,image)
(root/'environment.json').write_text(json.dumps(spec,indent=2)+'\n');(root/'environment.json').chmod(0o600)
project=Path(__file__).resolve().parents[2];sys.path.insert(0,str(project/'infra/camoufox'))
s=importlib.util.spec_from_file_location('runner',project/'infra/camoufox/environment-job.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
with m.Fixture('job-'+uuid.uuid4().hex[:16],image) as fixture:
    with (root/'run.log').open('w') as log:r=subprocess.run([sys.executable,str(Path(__file__).with_name('acceptance.py')),'--artifact',str(root/'environment.json'),'--network',fixture.networks['internal'],'--output',str(root/'acceptance.json'),'--recreations','0'],stdout=log,stderr=subprocess.STDOUT)
print('diagnostic exit',r.returncode)
