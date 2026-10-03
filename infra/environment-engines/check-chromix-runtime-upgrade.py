#!/usr/bin/env python3
"""Exercise upgraded cache and publication recovery using isolated spool copies."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
from unittest.mock import patch


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);a=p.parse_args();os.umask(0o077)
    root=a.root.resolve();out=root/'publication';out.mkdir(mode=0o700)
    project=Path(__file__).resolve().parents[2]
    original=project/'infra/sealskin/runtime/r6f-release-combination-2026-09-19/production-management-1/jobs'
    source=root/'runner-source/infra/camoufox/environment-job.py';sys.path.insert(0,str(source.parent))
    spec=importlib.util.spec_from_file_location('upgrade_runner',source);runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    import native_jobs
    request=json.loads((original/'queue/job-956e4202f308337c.json').read_bytes());job=request['job_id'];env=request['spec']['id']
    receipt=json.loads((root/'cache-upgrade/receipt.json').read_bytes());results=[]
    def unexpected(*args):raise AssertionError('UNEXPECTED_ACCEPTANCE_RERUN')
    for case in ('interrupt','failed-publish','failed-report'):
        work=out/case;work.mkdir(mode=0o700);spool=runner.Spool(work/'jobs')
        shutil.copytree(original/'templates',spool.root/'templates')
        for row in receipt['entries']:
            for src,rel in [(original/row['original'],row['original']),(root/'cache-upgrade'/row['path'],row['path'])]:
                dest=spool.root/rel;dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700);shutil.copy2(src,dest)
        artifact=spool.root/'artifacts'/env;artifact.mkdir(mode=0o700)
        for name in ('environment.json','acceptance.json'):shutil.copy2(root/'fullscreen'/name,artifact/name)
        runner.write_private(spool.root/'queue'/(job+'.json'),runner.encode(request))
        catalog=json.loads((project/'infra/sealskin/config/browser-platform/template-catalog.json').read_bytes())
        catalog['display_templates']=[];catalog['compatibility']=[]
        runner.write_private(work/'template-catalog.json',runner.encode(catalog))
        args=SimpleNamespace(image='',min_free_mib=0,recreations=10,native_targets=root/'native-targets.json',template_catalog=work/'template-catalog.json',catalog=work/'environment-catalog.json',session_origin='https://entry.geometry-qa.test',username='geometry-qa',clipboard_addon=None,store='SealSkin Apps',template='Default',browser_template_id='camoufox-linux-v152',verify_in_image=True)
        if case=='failed-report':
            report=json.loads((artifact/'acceptance.json').read_bytes());report['status']='failed'
            runner.write_private(artifact/'acceptance.json',runner.encode(report))
            before=(artifact/'acceptance.json').read_bytes()
            assert runner.run_next(spool,args,runner.load_prepare(),fixture=unexpected)=='failed'
            assert spool.status(job)['code']=='NATIVE_ACCEPTANCE_FAILED'
            assert not args.catalog.exists() and (artifact/'acceptance.json').read_bytes()==before
        else:
            before={f.name:native_jobs.sha(f) for f in artifact.glob('*.json')}
            error=KeyboardInterrupt if case=='interrupt' else OSError('injected publication failure')
            with patch.object(native_jobs,'publish_compatibility',side_effect=error):
                if case=='interrupt':
                    try:runner.run_next(spool,args,runner.load_prepare(),fixture=unexpected)
                    except KeyboardInterrupt:pass
                    else:raise AssertionError('MISSED_INTERRUPTION')
                else:assert runner.run_next(spool,args,runner.load_prepare(),fixture=unexpected)=='failed'
            partial=args.catalog.read_bytes()
            if case=='failed-publish':args.retry_job=job
            assert runner.run_next(spool,args,runner.load_prepare(),fixture=unexpected)=='accepted'
            assert args.catalog.read_bytes()==partial and len(json.loads(args.template_catalog.read_bytes())['compatibility'])==1
            assert before=={f.name:native_jobs.sha(f) for f in artifact.glob('*.json')}
        for row in receipt['entries']:assert native_jobs.sha(spool.root/row['original'])==row['original_sha256']
        results.append({'case':case,'result':'PASS','original_cache_preserved':True})
    runner.write_private(out/'result.json',runner.encode({'result':'PASS','cases':results}))
    print('PASS same-seed upgrade, two publication recoveries and failed-report rejection')


if __name__=='__main__':main()
