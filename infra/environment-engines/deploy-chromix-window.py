#!/usr/bin/env python3
"""Bounded R6Z1 deployment: idle runner, Chromix target and additive cache only."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import uuid
from datetime import datetime, timezone

PROJECT=Path(__file__).resolve().parents[2]
ROOT=PROJECT/'infra/sealskin/runtime/r6z1-chromix-window-20261001'
OLD_JOB='job-956e4202f308337c'


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


prior=module('protected_r6y',ROOT.parent/'r6y-management-delete-20261001/deploy.py')
b=prior.d
cfg=b.read(PROJECT/'infra/sealskin/adapter-config.json')
spool=Path(cfg['environment_job_spool'])
if not spool.is_absolute():spool=PROJECT/'infra/sealskin'/spool


def snapshot():
    value=prior.snapshot();value['adapter_sha256']=b.sha(b.BINARY);return value


def verify_candidate():
    assert b.files(ROOT/'runner-source')==b.read(ROOT/'runner-manifest.json')
    previous=ROOT.parent/'r6s-shared-display-20261001'
    old=b.read(previous/'final-runner-manifest.json');new=b.read(ROOT/'runner-manifest.json')
    assert set(old)==set(new)
    assert {k for k in old if old[k]!=new[k]}==set(b.read(ROOT/'runner-delta.json'))
    assert set(b.read(ROOT/'runner-delta.json'))=={'infra/camoufox/native_jobs.py','infra/chromix/launcher.py','infra/environment-engines/test_engines.py','infra/environment-engines/README.md'}
    targets=b.read(ROOT/'native-targets.json');expected=b.read(previous/'native-targets.json')
    image=b.read(ROOT/'build/builds.json')['chromix']['image']
    assert b.sha(ROOT/'runner-source/infra/chromix/launcher.py')==b.read(ROOT/'build/builds.json')['chromix']['inputs']['launcher.py']
    expected['targets']['chromix-linux-154']['image']=image;assert targets==expected
    assert b.run(['docker','image','inspect',image,'--format','{{.Id}}']).strip()==image
    for file in ('engines-tests.log','chromix-tests.log','frozen-engines-tests.log','job-tests.log','template-tests.log'):
        log=(ROOT/file).read_text();assert '\nOK\n' in log and '\nFAILED ' not in log,file
    report=b.read(ROOT/'fullscreen/acceptance.json')
    assert report['status']=='pass' and report['phase']=='all' and len(report['observations'])>=22 and report['recreationsPerHome']>=10
    assert report['offlineBackupRestore']=='pass' and report['normalDesktopInput'] and report['displayAuthentication']
    assert report['runtimeImageDigest']==image and report['artifactSHA256']==b.sha(ROOT/'fullscreen/environment.json')
    for observation in report['observations']:
        actual=observation['observed'];assert actual['window']['outerWidth']==1920 and actual['window']['outerHeight']==1080
    automatic=b.read(ROOT/'auto/acceptance.json');assert automatic['status']=='pass' and automatic['dynamicDisplay']=='pass'
    for name in ('window-modes','publication','negative'):
        assert b.read(ROOT/name/'result.json')['result']=='PASS',name
    receipt=b.read(ROOT/'cache-upgrade/receipt.json')
    assert receipt['new_image']==image
    for row in receipt['entries']:
        assert b.sha(spool/row['original'])==row['original_sha256']
        assert b.sha(spool/row['source'])==row['source_sha256']
        variant=b.read(ROOT/'cache-upgrade'/row['path']);old=b.read(spool/row['original'])
        assert variant=={**old,'image':image}
        assert b.sha(ROOT/'cache-upgrade'/row['path'])==row['sha256']
    return receipt


def prepare():
    receipt=verify_candidate();b.idle(spool)
    assert not (ROOT/'deployment-inputs.json').exists()
    original=b.UNIT.read_text();lines=original.splitlines()
    args=shlex.split(next(line[10:] for line in lines if line.startswith('ExecStart=')))
    args[1]=str(ROOT/'runner-source/infra/camoufox/environment-job.py')
    args[args.index('--native-targets')+1]=str(ROOT/'native-targets.json')
    expected='\n'.join('ExecStart='+' '.join(args) if line.startswith('ExecStart=') else 'WorkingDirectory='+str(ROOT/'runner-source/infra/camoufox') if line.startswith('WorkingDirectory=') else line for line in lines)+'\n'
    assert (ROOT/'environment-job.service').read_text()==expected
    before=snapshot()
    assert before['adapter_sha256']=='f8b255e6ff2184f97b2cff515e41b4bab7c26365afaaf5f5308c0dcbb696118c'
    for row in receipt['entries']:assert not (spool/row['path']).exists()
    b.write(ROOT/'deployment-inputs.json',{'snapshot':before,'unit_sha256':b.sha(ROOT/'environment-job.service'),
        'targets_sha256':b.sha(ROOT/'native-targets.json'),'manifest_sha256':b.sha(ROOT/'runner-manifest.json'),
        'cache_receipt_sha256':b.sha(ROOT/'cache-upgrade/receipt.json')})
    print('PREPARED: protected state recorded; runner/Chromix/cache only')


def apply():
    receipt=verify_candidate();expected=b.read(ROOT/'deployment-inputs.json')
    assert not (ROOT/'deployment.json').exists()
    for file,key in [('environment-job.service','unit_sha256'),('native-targets.json','targets_sha256'),('runner-manifest.json','manifest_sha256'),('cache-upgrade/receipt.json','cache_receipt_sha256')]:
        assert b.sha(ROOT/file)==expected[key]
    assert snapshot()==expected['snapshot']
    added={};stopped=False;changed=False
    backup=ROOT/'environment-job-before.service';assert not backup.exists();shutil.copy2(b.UNIT,backup)
    # Holding the runner lock prevents a queued request starting between idle
    # verification and service stop. Never interrupt a running acceptance.
    with (spool/'.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        b.idle(spool)
        try:
            b.run(['systemctl','--user','stop',b.SERVICE]);stopped=True
            assert snapshot()==expected['snapshot']
            for row in receipt['entries']:
                dst=spool/row['path'];dst.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                with dst.open('xb') as stream:
                    os.fchmod(stream.fileno(),0o600);stream.write((ROOT/'cache-upgrade'/row['path']).read_bytes());stream.flush();os.fsync(stream.fileno())
                added[row['path']]=row['sha256']
            b.replace(ROOT/'environment-job.service',b.UNIT,0o644);changed=True
            b.run(['systemctl','--user','daemon-reload'])
            after=snapshot();wanted=json.loads(json.dumps(expected['snapshot']))
            wanted['files'][str(b.UNIT)]=expected['unit_sha256'];wanted['spool'].update(added)
            assert after==wanted,'PROTECTED_STATE_CHANGED'
            b.write(ROOT/'deployment-after.json',after)
        except BaseException:
            if changed:b.replace(backup,b.UNIT,0o644);b.run(['systemctl','--user','daemon-reload'])
            # Added immutable cache variants are harmless to the old runner;
            # retain receipts rather than deleting any concurrent user state.
            b.write(ROOT/'deployment-failed.json',{'added':added,'unit_restored':changed})
            raise
        finally:
            if stopped:b.run(['systemctl','--user','start',b.SERVICE])
    assert b.run(['systemctl','--user','is-active',b.SERVICE]).strip()=='active'
    b.ready(cfg)
    b.write(ROOT/'deployment.json',{'result':'PASS','image':receipt['new_image'],'cache_variants':len(added),
        'runner_manifest_sha256':expected['manifest_sha256'],'adapter_controller_workers_sessions_preserved':True,
        'old_spool_catalogs_preserved':True,'scope':'idle runner, Chromix image target, additive same-seed cache'})
    print('PASS deployed; existing browsers and original job preserved')


def enqueue():
    assert b.read(ROOT/'deployment.json')['result']=='PASS'
    assert b.sha(b.UNIT)==b.sha(ROOT/'environment-job.service')
    marker=ROOT/'replacement-request.json'
    with (spool/'.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert b.read(spool/'status'/(OLD_JOB+'.json'))['status']=='failed'
        original=b.read(spool/'queue'/(OLD_JOB+'.json'))
        if marker.exists():
            request=b.read(marker)
        else:
            request=json.loads(json.dumps(original));suffix=uuid.uuid4().hex[:16]
            request['job_id']='job-'+suffix;request['spec']['id']='env-custom-'+suffix
            request['requested_at']=datetime.now(timezone.utc).isoformat();b.write(marker,request)
        for kind in ('fingerprint','display'):
            ident=request['templates'][kind+'_id']
            source_kind='fingerprints' if kind=='fingerprint' else 'displays'
            deletion=hashlib.sha256(json.dumps([source_kind,ident],separators=(',',':')).encode()).hexdigest()+'.json'
            assert not (spool/'templates/deleted'/deletion).exists(),'SOURCE_DELETED'
            source=spool/'templates'/source_kind/(ident+'.json')
            assert b.sha(source)==request['templates'][kind+'_sha256']
        # Preserve all original requirement fields, changing only job identity/time.
        check=json.loads(json.dumps(request));check['job_id']=original['job_id'];check['spec']['id']=original['spec']['id'];check['requested_at']=original['requested_at'];assert check==original
        dest=spool/'queue'/(request['job_id']+'.json')
        if dest.exists():assert b.read(dest)==request
        else:
            temporary=dest.with_suffix('.new')
            with temporary.open('xb') as stream:
                os.fchmod(stream.fileno(),0o600);stream.write(marker.read_bytes());stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,dest)
    print('Queued replacement',request['job_id'],'with unchanged source templates and requirements')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group();g.add_argument('--apply',action='store_true');g.add_argument('--enqueue-replacement',action='store_true');a=p.parse_args();os.umask(0o077)
    if a.apply:apply()
    elif a.enqueue_replacement:enqueue()
    else:prepare()
