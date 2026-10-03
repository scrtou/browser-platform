#!/usr/bin/env python3
"""Actual installed Worker entrypoints must reject invalid custom artifacts."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid
from acceptance import environment,normalize
p=argparse.ArgumentParser();p.add_argument('--artifact',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();os.umask(0o077)
root=a.output.resolve();assert 'runtime' in root.parts;root.mkdir(mode=0o700)
base=json.loads(a.artifact.read_bytes());results=[]
camoufox='spec' in base
report=a.artifact.with_name('acceptance.json')
for case in ('sha','timezone','version','extra-flags','window','image','missing','display-mode','manual-size','report-sha'):
    value=copy.deepcopy(base);spec=value['spec'] if camoufox else value
    if case=='version':spec['browserVersion']='1'
    if case=='extra-flags':value['extraArgs']=['--no-sandbox']
    if case=='window':spec['window']['width']=spec['screen']['width']+1
    if case=='image':value['runtimeImageDigest']='latest'
    path=root/(case+'.json');path.write_text(json.dumps(value));path.chmod(0o600)
    env=environment(normalize(value),hashlib.sha256(path.read_bytes()).hexdigest())
    if case=='sha':env['BROWSER_PLATFORM_ARTIFACT_SHA256']='0'*64
    if case=='timezone':env['TZ']='Asia/Tokyo'
    env['BROWSER_PLATFORM_ACCEPTANCE_SHA256']=hashlib.sha256(report.read_bytes()).hexdigest()
    if case=='display-mode':env['BROWSER_PLATFORM_DISPLAY_MODE']='fixed'
    if case=='manual-size':env['SELKIES_MANUAL_WIDTH']='1280'
    if case=='report-sha':
        if not camoufox:continue
        env['BROWSER_PLATFORM_ACCEPTANCE_SHA256']='0'*64
    cmd=['docker','run','--rm','--network','none','--memory','512m','--cpus','1','--name','bp-native-negative-'+uuid.uuid4().hex[:8]]
    if case!='missing':cmd+=['--mount',f'type=bind,src={path},dst=/run/browser-platform/environment.json,readonly']
    cmd+=['--mount',f'type=bind,src={report.resolve()},dst=/run/browser-platform/acceptance.json,readonly']
    for k,v in env.items():cmd+=['-e',k+'='+v]
    result=subprocess.run(cmd+[base['runtimeImageDigest']],capture_output=True,text=True,timeout=45)
    (root/(case+'.log')).write_text(result.stdout+result.stderr)
    assert result.returncode!=0 and '[ls.io-init]' not in result.stdout,case
    results.append(case)
(root/'result.json').write_text(json.dumps({'result':'PASS','image':base['runtimeImageDigest'],'cases':results},indent=2)+'\n');print('PASS',len(results),'installed entrypoint rejections')
