#!/usr/bin/env python3
"""Add full desktop evidence for accepted fixed Camoufox artifacts in isolated QA."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--qa',type=Path,required=True)
    p.add_argument('--runner',type=Path,required=True)
    p.add_argument('--client-browsers',type=Path,required=True)
    p.add_argument('--environment-id',action='append',help='Accepted fixed artifacts in this QA part; package still requires all four')
    a=p.parse_args();os.umask(0o077)
    qa=a.qa.resolve();runner=a.runner.resolve()
    if 'runtime' not in qa.parts or 'r6aw-protected-builtins-20261002' not in qa.parts:
        raise ValueError('BUILTIN_QA_SCOPE')
    sys.path.insert(0,str(runner.parent))
    spec=importlib.util.spec_from_file_location('builtin_desktop_runner',runner)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    # Accepted fixed artifacts are immutable; the supplement writes a separate
    # report/Home root. A dedicated lock avoids blocking unrelated queued jobs.
    with (qa/'.desktop-acceptance.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        catalog=json.loads((qa/'environment-catalog.json').read_bytes())
        rows=[v for v in catalog['artifacts'] if v['browser_engine']=='camoufox' and v['screen']=='1920x1080@1']
        if a.environment_id:
            selected=set(a.environment_id)
            if len(selected)!=len(a.environment_id):raise ValueError('BUILTIN_DESKTOP_DUPLICATE_SELECTION')
            rows=[v for v in rows if v['id'] in selected]
            if {v['id'] for v in rows}!=selected:raise ValueError('BUILTIN_DESKTOP_SELECTION_MISSING')
        elif len(rows)!=4:raise ValueError('BUILTIN_FIXED_CAMOUFOX_FOUR_REQUIRED')
        for row in rows:
            status=json.loads((qa/'jobs/status'/(row['job_id']+'.json')).read_bytes())
            if status['status']!='accepted':raise ValueError('BUILTIN_JOB_NOT_ACCEPTED')
            artifact=qa/'jobs/artifacts'/row['id']/'environment.json'
            report=artifact.with_name('desktop-acceptance.json')
            if hashlib.sha256(artifact.read_bytes()).hexdigest()!=row['sha256']:
                raise ValueError('BUILTIN_ARTIFACT_DIGEST')
            if not report.exists():
                with module.Fixture(row['job_id']+'-desktop',row['image']) as active:
                    with (qa/'jobs/evidence'/row['job_id']/'desktop-acceptance.log').open('x') as log:
                        subprocess.run([sys.executable,str(runner.parents[1]/'environment-engines/acceptance.py'),
                            '--artifact',str(artifact),'--network',active.networks['internal'],
                            '--output',str(report),'--recreations','10','--client-browsers',str(a.client_browsers.resolve())],
                            stdout=log,stderr=subprocess.STDOUT,timeout=3600,check=True)
            value=json.loads(report.read_bytes())
            if (value.get('status')!='pass' or value.get('phase')!='all'
                    or value.get('schemaVersion')!='browser-platform/native-acceptance/v1'
                    or value.get('artifactSHA256')!=row['sha256'] or value.get('runtimeImageDigest')!=row['image']
                    or value.get('recreationsPerHome',0)<10 or len(value.get('observations',[]))<22
                    or value.get('offlineBackupRestore')!='pass' or value.get('normalDesktopInput') is not True
                    or value.get('displayAuthentication') is not True):
                raise ValueError('BUILTIN_DESKTOP_ACCEPTANCE_FAILED')
            print('PASS fixed Camoufox desktop '+row['id'],flush=True)
    print(f'PASS {len(rows)} fixed Camoufox full desktop reports',flush=True)

if __name__=='__main__':main()
