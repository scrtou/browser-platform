#!/usr/bin/env python3
"""Bounded R6R release: Adapter, idle runner, append one Firefox target."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import time

PROJECT=Path(__file__).resolve().parents[2]
s=importlib.util.spec_from_file_location('bounded',PROJECT/'infra/camoufox/deploy-engine-neutral-templates.py')
b=importlib.util.module_from_spec(s);s.loader.exec_module(b)
TARGET={'id':'firefox-linux-155','revision':1,'status':'accepted','label':'Firefox 155','engine':'firefox','version':'155.0.1','os_family':'linux','platform':'Linux x86_64','user_agent_product':'Firefox','allow_new_browsers':True}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True,type=Path);p.add_argument('--apply',action='store_true');a=p.parse_args();os.umask(0o077)
    root=a.root.resolve();assert root.name=='r6r-multi-engine-20261001' and 'runtime' in root.parts
    config=PROJECT/'infra/sealskin/adapter-config.json';cfg=b.read(config)
    def path(v):
        q=Path(v);return q if q.is_absolute() else config.parent/q
    spool=path(cfg['environment_job_spool']);catalog=path(cfg['template_catalog'])
    protected=[config,path(cfg['profile_directory']),path(cfg['environment_catalog']),path(cfg['access']['users_file'])]
    if cfg.get('network_profile_catalog'):protected.append(path(cfg['network_profile_catalog']))
    for kind in ('adapter','runner'):
        assert b.files(root/('final-'+kind+'-source'))==b.read(root/('final-'+kind+'-manifest.json'))
    candidate=root/'final-profile-adapter';unit=root/'final-environment-job.service';targets=root/'native-targets.json'
    assert targets.stat().st_mode&0o077==0
    if not a.apply:
        assert not (root/'deployment-inputs.json').exists()
        assert b.sha(b.BINARY)=='ab60d3a58db9395c066ca0dfe4fadcc6fd4430f9c2eb3d9c1ff24571d14b276a'
        b.idle(spool)
        original=b.UNIT.read_text();old=shlex.split(next(x[10:] for x in original.splitlines() if x.startswith('ExecStart=')))
        assert '--native-targets' not in old
        old[1]=str(root/'final-runner-source/infra/camoufox/environment-job.py');old+=['--native-targets',str(targets)]
        assert all(not any(c in v for c in '%\n\r\t ') for v in old)
        unit.write_text('\n'.join('ExecStart='+' '.join(old) if x.startswith('ExecStart=') else 'WorkingDirectory='+str(root/'final-runner-source/infra/camoufox') if x.startswith('WorkingDirectory=') else x for x in original.splitlines())+'\n')
        value=b.read(catalog);assert not any(v['id']==TARGET['id'] for v in value['browser_templates'])
        value['browser_templates'].append(TARGET);b.write(root/'candidate-template-catalog.json',value)
        b.write(root/'deployment-inputs.json',{'files':{str(q):b.sha(q) for q in protected+[catalog,b.BINARY,b.UNIT,targets]},'spool':b.spool_files(spool),'candidate_sha256':b.sha(candidate),'unit_sha256':b.sha(unit),'catalog_sha256':b.sha(root/'candidate-template-catalog.json')})
        print('PREPARED R6R bounded release; production unchanged');return
    assert not (root/'deployment.json').exists()
    for name in ('verification.json','publication-recovery/result.json','runner-rejections/result.json','display-switch/result.json','ui-release/result.json','negative-chromix/result.json','negative-firefox/result.json'):
        assert b.read(root/name)['result']=='PASS',name
    verified=b.read(root/'verification.json')
    assert verified['adapter_sha256']==b.sha(candidate)
    assert verified['runner_manifest_sha256']==b.sha(root/'final-runner-manifest.json')
    assert b.read(root/'camoufox-unit.json')['status']=='pass'
    entries=b.read(root/'integration-accepted/environment-catalog.json')['artifacts'];assert len(entries)==4
    for entry in entries:
        report_path=Path(next(m['Source'] for m in entry['application']['provider_config']['docker_overrides']['mounts'] if m['Target'].endswith('/acceptance.json')))
        report=b.read(report_path)
        assert report['status']=='pass' and report['phase']=='all' and report['recreationsPerHome']>=10 and len(report['observations'])>=22
        assert report['artifactSHA256']==entry['sha256'] and b.sha(report_path)==entry['acceptance_sha256']
        assert b.read(targets)['targets'][entry['browser_template_id']]['image']==entry['image']
        assert b.run(['docker','image','inspect',entry['image'],'--format','{{.Id}}']).strip()==entry['image']
    expected=b.read(root/'deployment-inputs.json')
    assert b.sha(candidate)==expected['candidate_sha256'] and b.sha(unit)==expected['unit_sha256'] and b.sha(root/'candidate-template-catalog.json')==expected['catalog_sha256']
    for name,digest in expected['files'].items():assert b.sha(Path(name))==digest,'DEPLOYMENT_INPUT_CHANGED'
    assert b.spool_files(spool)==expected['spool'];b.idle(spool)
    before=b.production_containers();backup=root/'deployment-backup';backup.mkdir(mode=0o700)
    for q in (b.BINARY,b.UNIT,catalog):shutil.copy2(q,backup/q.name)
    b.write(root/'deployment-before.json',{'containers':before,'protected':{str(q):b.sha(q) for q in protected+[catalog]}})
    changed=False;stopped=False
    try:
        b.run(['systemctl','--user','stop',b.SERVICE]);stopped=True;b.idle(spool)
        assert b.spool_files(spool)==expected['spool']
        with catalog.with_name(catalog.name+'.lock').open('a+b') as lock:
            os.fchmod(lock.fileno(),0o600);fcntl.flock(lock,fcntl.LOCK_EX)
            assert b.sha(catalog)==expected['files'][str(catalog)]
            b.replace(candidate,b.BINARY,0o755);changed=True
            b.replace(unit,b.UNIT,0o644)
            b.replace(root/'candidate-template-catalog.json',catalog,0o600)
        b.run(['systemctl','--user','daemon-reload']);b.run(['systemctl','--user','restart','profile-adapter.service']);b.ready(cfg)
        b.run(['systemctl','--user','start',b.SERVICE]);stopped=False;time.sleep(2)
        assert b.run(['systemctl','--user','is-active',b.SERVICE]).strip()=='active'
        assert b.production_containers()==before
        assert all(b.sha(q)==expected['files'][str(q)] for q in protected)
        assert b.sha(catalog)==expected['catalog_sha256'] and b.spool_files(spool)==expected['spool']
    except BaseException:
        safe=all(b.sha(q)==expected['files'][str(q)] for q in protected) and b.spool_files(spool)==expected['spool'] and b.sha(catalog) in (expected['catalog_sha256'],expected['files'][str(catalog)])
        if changed and safe and b.sha(b.BINARY)==b.sha(candidate) and b.sha(b.UNIT) in (b.sha(unit),b.sha(backup/b.UNIT.name)):
            b.run(['systemctl','--user','stop',b.SERVICE]);stopped=True
            with catalog.with_name(catalog.name+'.lock').open('a+b') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                assert b.sha(catalog) in (expected['catalog_sha256'],expected['files'][str(catalog)])
                for src,dst,mode in [(backup/b.BINARY.name,b.BINARY,0o755),(backup/b.UNIT.name,b.UNIT,0o644),(backup/catalog.name,catalog,0o600)]:b.replace(src,dst,mode)
            b.run(['systemctl','--user','daemon-reload']);b.run(['systemctl','--user','restart','profile-adapter.service'])
        elif changed:b.write(root/'rollback-held.json',{'reason':'new job/config/catalog detected; preserve and reconcile'})
        if stopped:b.run(['systemctl','--user','start',b.SERVICE])
        raise
    b.write(root/'deployment.json',{'result':'PASS','adapter_sha256':b.sha(b.BINARY),'runner_manifest_sha256':b.sha(root/'final-runner-manifest.json'),'native_targets_sha256':b.sha(targets),'containers_preserved':True,'profiles_accounts_preserved':True,'old_catalog_entries_preserved':True,'old_spool_files_preserved':True,'scope':'Adapter and idle runner; append Firefox target only; no production Worker/Home changes'})
    print('PASS R6R deployed; production containers, Homes, profiles and old jobs preserved')

if __name__=='__main__':main()
