#!/usr/bin/env python3
"""Bounded R6S release: shared defaults, Adapter and idle runner; preserve Homes."""
import argparse
import copy
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import time
from types import SimpleNamespace

PROJECT=Path(__file__).resolve().parents[2]
s=importlib.util.spec_from_file_location('bounded',PROJECT/'infra/camoufox/deploy-engine-neutral-templates.py')
b=importlib.util.module_from_spec(s);s.loader.exec_module(b)
BASELINE='7e9f7ec24483012105c9e327e86cd5b525eb30fa28273b342e7e64c96978cc02'

def validate_reports(root):
    entries=b.read(root/'integration-3/environment-catalog.json')['artifacts']
    assert len(entries)==6
    for entry in entries:
        mounts=entry['application']['provider_config']['docker_overrides']['mounts']
        artifact=Path(next(m['Source'] for m in mounts if m['Target'].endswith('/environment.json')))
        report=Path(next(m['Source'] for m in mounts if m['Target'].endswith('/acceptance.json')))
        value=b.read(report)
        assert value['status']=='pass' and value['phase']=='all'
        assert value['artifactSHA256']==entry['sha256']==b.sha(artifact) and b.sha(report)==entry['acceptance_sha256']
        assert value['runtimeImageDigest']==entry['image']
        if value['schemaVersion']=='browser-platform/native-acceptance/v1':
            assert value['recreationsPerHome']>=10 and len(value['observations'])>=22 and value['offlineBackupRestore']=='pass'
            if entry['screen']=='auto@system':assert value['dynamicDisplay']=='pass'
        else:
            v=value['results']['homeReplay'];assert v['recreationsPerHome']>=10 and v['observationsStable'] and v['storageRestored'] and v['offlineBackupRestore']=='pass'
        assert b.read(root/'native-targets.json')['targets'][entry['browser_template_id']]['image']==entry['image']
        assert b.run(['docker','image','inspect',entry['image'],'--format','{{.Id}}']).strip()==entry['image']
    return entries

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True,type=Path);p.add_argument('--apply',action='store_true');a=p.parse_args();os.umask(0o077)
    root=a.root.resolve();assert root.name=='r6s-shared-display-20261001'
    config=PROJECT/'infra/sealskin/adapter-config.json';cfg=b.read(config)
    def path(v):
        q=Path(v);return q if q.is_absolute() else config.parent/q
    spool=path(cfg['environment_job_spool']);ec=path(cfg['environment_catalog']);tc=path(cfg['template_catalog'])
    protected=[config,path(cfg['profile_directory']),path(cfg['access']['users_file'])]
    if cfg.get('network_profile_catalog'):protected.append(path(cfg['network_profile_catalog']))
    for kind in ('adapter','runner'):assert b.files(root/('final-'+kind+'-source'))==b.read(root/('final-'+kind+'-manifest.json'))
    candidate=root/'final-profile-adapter';unit=root/'final-environment-job.service';targets=root/'native-targets.json'
    source=root/'final-runner-source/infra/camoufox';sys.path.insert(0,str(source))
    s=importlib.util.spec_from_file_location('release_runner',source/'environment-job.py');runner=importlib.util.module_from_spec(s);s.loader.exec_module(runner)
    import native_jobs
    if not a.apply:
        assert not (root/'deployment-inputs.json').exists();assert b.sha(b.BINARY)==BASELINE;b.idle(spool)
        assert not list((spool/'fingerprint-cache').rglob('environment.json')) and not list((spool/'fingerprint-cache').rglob('device.json')),'NEW_PRODUCTION_CACHE_REQUIRES_REVIEW'
        entries=validate_reports(root)
        original=b.UNIT.read_text();args=shlex.split(next(x[10:] for x in original.splitlines() if x.startswith('ExecStart=')))
        args[1]=str(source/'environment-job.py')
        args[args.index('--native-targets')+1]=str(targets)
        args[args.index('--image')+1]=b.read(targets)['targets']['camoufox-linux-v152']['image']
        cache=PROJECT/'infra/camoufox/.build/playwright-client-browsers';assert (cache/'chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell').is_file()
        args+=['--client-browsers',str(cache)]
        assert all(not any(c in v for c in '%\n\r\t ') for v in args)
        unit.write_text('\n'.join('ExecStart='+' '.join(args) if x.startswith('ExecStart=') else 'WorkingDirectory='+str(source) if x.startswith('WorkingDirectory=') else x for x in original.splitlines())+'\n')
        release=root/'default-combinations';release.mkdir(mode=0o700)
        qa=root/'integration-3';envs=b.read(ec);templates=b.read(tc)
        production_args=SimpleNamespace(username=cfg['sealskin']['username'],session_origin=cfg['sealskin']['public_session_base_url'],clipboard_addon=Path(args[args.index('--clipboard-addon')+1]),store='SealSkin Apps',template='Default',browser_template_id='camoufox-linux-v152')
        defaults=[]
        for entry in entries:
            out=release/entry['id'];out.mkdir(mode=0o700)
            for name in ('environment.json','acceptance.json'):
                src=Path(next(m['Source'] for m in entry['application']['provider_config']['docker_overrides']['mounts'] if m['Target'].endswith('/'+name)));shutil.copy2(src,out/name)
            artifact=b.read(out/'environment.json');value=copy.deepcopy(entry)
            if entry['browser_engine']=='camoufox' and entry['screen']!='auto@system':
                definition=runner.build_template(runner.load_prepare(),artifact_path=out/'environment.json',report_path=out/'acceptance.json',artifact=artifact,image=entry['image'],args=production_args,verify=True)
            else:definition=native_jobs.definition(out/'environment.json',out/'acceptance.json',native_jobs.runtime_spec(artifact),entry['browser_engine'],production_args)
            value['application']=definition;value.pop('job_id',None);value['source']='frozen';defaults.append(value)
            assert not any(v['id']==value['id'] for v in envs['artifacts']);envs['artifacts'].append(value)
        incoming=b.read(qa/'template-catalog.json')
        for field,keys in [('display_templates',('id',)),('compatibility',('browser_template_id','environment_artifact_id','display_template_id'))]:
            for item in incoming[field]:
                old=next((v for v in templates[field] if all(v[k]==item[k] for k in keys)),None)
                assert old is None or old==item
                if old is None:templates[field].append(item)
        b.write(release/'environments.json',{'version':1,'artifacts':defaults})
        b.write(root/'candidate-environment-catalog.json',envs);b.write(root/'candidate-template-catalog.json',templates)
        # Failed and superseded QA sources remain evidence, not production defaults.
        requests=[b.read(qa/'jobs/queue'/(entry['job_id']+'.json')) for entry in entries]
        fingerprints={request['templates']['fingerprint_id'] for request in requests}
        displays={request['templates']['display_id'] for request in requests}
        for kind,ids in [('fingerprints',fingerprints),('displays',displays)]:
            destination=release/'templates'/kind;destination.mkdir(mode=0o700,parents=True)
            for ident in sorted(ids):
                src=qa/'jobs/templates'/kind/(ident+'.json')
                assert src.is_file() and not src.is_symlink(),'DEFAULT_SOURCE_MISSING'
                shutil.copy2(src,destination/src.name)
        registry=b.read(targets)['targets'];cache_root=release/'fingerprint-cache';cache_root.mkdir(mode=0o700)
        for source_cache in (qa/'jobs/fingerprint-cache').glob('*/*'):
            if source_cache.parent.name not in fingerprints:continue
            receipt=source_cache/('device.json' if (source_cache/'device.json').exists() else 'receipt.json')
            value=b.read(receipt)
            if value.get('image') not in {v['image'] for v in registry.values()}:continue
            destination=cache_root/source_cache.parent.name/source_cache.name
            destination.parent.mkdir(mode=0o700,exist_ok=True);shutil.copytree(source_cache,destination)

        additions={}
        for name in ('templates','fingerprint-cache'):
            for f in (release/name).rglob('*'):
                if not f.is_file():continue
                rel=str(f.relative_to(release));dest=spool/rel
                assert not dest.exists() or b.sha(dest)==b.sha(f),'DEFAULT_SOURCE_CONFLICT'
                if not dest.exists():additions[rel]=b.sha(f)
        b.write(root/'deployment-inputs.json',{'files':{str(q):b.sha(q) for q in protected+[ec,tc,b.BINARY,b.UNIT,targets]},'spool':b.spool_files(spool),'additions':additions,'release':b.files(release),'candidate_sha256':b.sha(candidate),'unit_sha256':b.sha(unit),'environment_catalog_sha256':b.sha(root/'candidate-environment-catalog.json'),'template_catalog_sha256':b.sha(root/'candidate-template-catalog.json'),'client_cache':b.files(cache)})
        print('PREPARED six accepted defaults and bounded R6S release; production unchanged');return
    assert not (root/'deployment.json').exists()
    for name in ('verification.json','publication-recovery/result.json','runner-rejections/result.json','display-switch/result.json','ui-empty/result.json','ui-populated/result.json','ui-create/result.json','negative-camoufox/result.json','negative-chromix/result.json','negative-firefox/result.json'):
        assert b.read(root/name)['result']=='PASS',name
    assert b.read(root/'camoufox-auto-unit-2.json')['status']=='pass'
    expected=b.read(root/'deployment-inputs.json');verified=b.read(root/'verification.json')
    assert verified['adapter_sha256']==b.sha(candidate)==expected['candidate_sha256'] and verified['runner_manifest_sha256']==b.sha(root/'final-runner-manifest.json')
    assert b.sha(unit)==expected['unit_sha256'];assert b.files(root/'default-combinations')==expected['release']
    assert b.files(PROJECT/'infra/camoufox/.build/playwright-client-browsers')==expected['client_cache']
    for kind in ('environment','template'):assert b.sha(root/('candidate-'+kind+'-catalog.json'))==expected[kind+'_catalog_sha256']
    validate_reports(root)
    for name,digest in expected['files'].items():assert b.sha(Path(name))==digest,'DEPLOYMENT_INPUT_CHANGED'
    assert b.spool_files(spool)==expected['spool'];b.idle(spool)
    before=b.production_containers();backup=root/'deployment-backup';backup.mkdir(mode=0o700)
    for q in (b.BINARY,b.UNIT,ec,tc):shutil.copy2(q,backup/q.name)
    b.write(root/'deployment-before.json',{'containers':before})
    changed=False;added=[];stopped=False
    wanted_spool={**expected['spool'],**expected['additions']}
    try:
        b.run(['systemctl','--user','stop',b.SERVICE]);stopped=True;b.idle(spool)
        b.run(['systemctl','--user','stop','profile-adapter.service'])
        assert b.spool_files(spool)==expected['spool']
        for name,digest in expected['files'].items():assert b.sha(Path(name))==digest
        # Both writers are idle; the catalog lock also protects against maintenance.
        with tc.with_name(tc.name+'.lock').open('a+b') as lock:
            os.fchmod(lock.fileno(),0o600);fcntl.flock(lock,fcntl.LOCK_EX)
            changed=True
            for rel,digest in expected['additions'].items():
                dst=spool/rel;dst.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
                with dst.open('xb') as f:os.fchmod(f.fileno(),0o600);f.write((root/'default-combinations'/rel).read_bytes());f.flush();os.fsync(f.fileno())
                added.append(rel);assert b.sha(dst)==digest
            b.replace(root/'candidate-environment-catalog.json',ec,0o600);b.replace(root/'candidate-template-catalog.json',tc,0o600)
            b.replace(candidate,b.BINARY,0o755);b.replace(unit,b.UNIT,0o644)
        b.run(['systemctl','--user','daemon-reload']);b.run(['systemctl','--user','start','profile-adapter.service']);b.ready(cfg)
        b.run(['systemctl','--user','start',b.SERVICE]);stopped=False;time.sleep(2)
        assert b.run(['systemctl','--user','is-active',b.SERVICE]).strip()=='active'
        assert b.production_containers()==before
        assert all(b.sha(q)==expected['files'][str(q)] for q in protected)
        assert b.spool_files(spool)==wanted_spool
        assert b.sha(ec)==expected['environment_catalog_sha256'] and b.sha(tc)==expected['template_catalog_sha256']
    except BaseException:
        current=b.spool_files(spool)
        safe=all(b.sha(q)==expected['files'][str(q)] for q in protected) and current=={**expected['spool'],**{rel:expected['additions'][rel] for rel in added}}
        safe=safe and all(b.sha(q) in (expected['files'][str(q)],expected[key]) for q,key in [(ec,'environment_catalog_sha256'),(tc,'template_catalog_sha256')])
        if changed and safe:
            b.run(['systemctl','--user','stop',b.SERVICE]);b.run(['systemctl','--user','stop','profile-adapter.service'])
            for src,dst,mode in [(backup/b.BINARY.name,b.BINARY,0o755),(backup/b.UNIT.name,b.UNIT,0o644),(backup/ec.name,ec,0o600),(backup/tc.name,tc,0o600)]:b.replace(src,dst,mode)
            for rel in added:(spool/rel).unlink()
            b.run(['systemctl','--user','daemon-reload'])
        elif changed:b.write(root/'rollback-held.json',{'reason':'new operation/config/catalog detected; preserve and reconcile'})
        b.run(['systemctl','--user','start','profile-adapter.service']);b.run(['systemctl','--user','start',b.SERVICE]);raise
    b.write(root/'deployment.json',{'result':'PASS','adapter_sha256':b.sha(b.BINARY),'runner_manifest_sha256':b.sha(root/'final-runner-manifest.json'),'containers_preserved':True,'profiles_accounts_preserved':True,'old_catalog_entries_preserved':True,'old_spool_files_preserved':True,'default_combinations':6,'scope':'Adapter, idle runner and six accepted defaults; no production Home/Worker migration'})
    print('PASS R6S deployed; six defaults available, production Homes/Workers preserved')

if __name__=='__main__':main()
