#!/usr/bin/env python3
"""Normally close only a recorded native-generation QA instance, preserving Home."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
p=argparse.ArgumentParser();p.add_argument('--resource',type=Path,required=True);a=p.parse_args()
assert 'runtime' in a.resource.resolve().parts
value=json.loads(a.resource.read_bytes());name=value['container'];assert name.startswith('bp-native-qa-')
item=json.loads(subprocess.check_output(['docker','inspect',name]))[0]
assert item['Config']['Labels']['io.browser-platform.qa']=='native-generation'
assert any(m['Source']==value['home'] and m['Destination']=='/config' for m in item['Mounts'])
material=Path(next(m['Source'] for m in item['Mounts'] if m['Destination']=='/run/browser-platform-session-input'))
assert material.parent==Path('/dev/shm') and material.name.startswith('native-display-')
subprocess.run(['docker','exec','--user','1000',name,'python3','/usr/local/lib/browser-platform/browser-shutdown.py','--timeout','15'],check=True,capture_output=True)
subprocess.run(['docker','stop','-t','30',name],check=True,capture_output=True)
subprocess.run(['docker','rm','-v',name],check=True,capture_output=True)
for key,network in item['NetworkSettings']['Networks'].items():
 if key.startswith('bp-envjob-'):subprocess.run(['docker','network','rm',key],capture_output=True)
shutil.rmtree(material)
print('QA normally closed; Home and evidence retained')
