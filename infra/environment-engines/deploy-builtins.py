#!/usr/bin/env python3
"""Prepare/apply the bounded R6AW release after full real-matrix verification."""
import argparse
import fcntl
import importlib.util
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import urllib.request
from urllib.parse import urlsplit

PROJECT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('bounded_release',PROJECT/'infra/camoufox/deploy-engine-neutral-templates.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
from builtin_bundle import verify_bundle

BASELINE='6de8aba3400ab8e0c4dbe98db37d3dc7a9e4b625202d472756fde7a3177d91b2'

def snapshot(spool):
    return {str(p.relative_to(spool)):b.sha(p) for p in sorted(spool.rglob('*'))
            if p.is_file() and not p.is_symlink() and p.name!='.lock' and not p.name.endswith('.lock')}

def check_manifest(root,manifest):
    for name,digest in manifest.items():
        if b.sha(root/name)!=digest:raise ValueError('RELEASE_SOURCE_CHANGED')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True);parser.add_argument('--apply',action='store_true')
    parser.add_argument('--candidate',type=Path,help='Frozen source candidate within the R6AW evidence root')
    args=parser.parse_args();os.umask(0o077);root=args.root.resolve()
    if root.name!='r6aw-protected-builtins-20261002' or 'runtime' not in root.parts:raise ValueError('RELEASE_SCOPE')
    candidate=args.candidate.resolve() if args.candidate else root
    if not candidate.is_relative_to(root):raise ValueError('RELEASE_CANDIDATE_SCOPE')
    config=PROJECT/'infra/sealskin/adapter-config.json';cfg=b.read(config)
    def path(value):
        p=Path(value);return p if p.is_absolute() else config.parent/p
    spool=path(cfg['environment_job_spool']);ec=path(cfg['environment_catalog']);tc=path(cfg['template_catalog'])
    protected=[config,path(cfg['profile_directory']),path(cfg['state_file']),path(cfg['access']['users_file']),path(cfg['network_profile_catalog'])]
    bundle=root/'builtin-package';verify_bundle(bundle)
    binary=candidate/'profile-adapter';check_manifest(candidate,b.read(candidate/'candidate-manifest.json'))
    release=root/'release';install=release/'installed';unit=release/b.UNIT.name
    if not args.apply:
        if (root/'deployment-inputs.json').exists():raise ValueError('RELEASE_ALREADY_PREPARED')
        if b.sha(b.BINARY)!=BASELINE:raise ValueError('RELEASE_BASELINE_CHANGED')
        b.idle(spool)
        release.mkdir(mode=0o700)
        shutil.copytree(candidate/'runner-source',release/'runner-source',ignore=shutil.ignore_patterns('__pycache__','.build','*.pyc'))
        for name in ['builtin_bundle.py','package-builtins.py','prepare-builtin-install.py','check-fixed-camoufox-desktop.py','check-builtin-package.py','assemble-builtin-qa.py','deploy-builtins.py']:
            shutil.copy2(PROJECT/'infra/environment-engines'/name,release/'runner-source/infra/environment-engines'/name)
        shutil.copy2(candidate/'native-targets.json',release/'native-targets.json')
        original=b.UNIT.read_text();command=shlex.split(next(v[10:] for v in original.splitlines() if v.startswith('ExecStart=')))
        command[1]=str(release/'runner-source/infra/camoufox/environment-job.py')
        command[command.index('--native-targets')+1]=str(release/'native-targets.json')
        command[command.index('--image')+1]=b.read(release/'native-targets.json')['targets']['camoufox-linux-v152']['image']
        if any(any(c in value for c in '%\n\r\t ') for value in command):raise ValueError('RELEASE_UNIT_UNSAFE')
        unit.write_text('\n'.join('ExecStart='+' '.join(command) if line.startswith('ExecStart=') else
            'WorkingDirectory='+str(release/'runner-source/infra/camoufox') if line.startswith('WorkingDirectory=') else line for line in original.splitlines())+'\n')
        subprocess.run([sys.executable,str(release/'runner-source/infra/environment-engines/prepare-builtin-install.py'),
            '--bundle',str(bundle),'--output',str(install),'--username',cfg['sealskin']['username'],
            '--session-origin',cfg['sealskin']['public_session_base_url'],
            '--clipboard-addon',command[command.index('--clipboard-addon')+1],
            '--environment-catalog',str(ec),'--template-catalog',str(tc)],check=True)
        additions={}
        for kind in ('templates','fingerprint-cache'):
            for source in (install/kind).rglob('*'):
                if not source.is_file():continue
                rel=str(source.relative_to(install));dest=spool/rel
                if dest.is_symlink() or dest.exists() and b.sha(dest)!=b.sha(source):raise ValueError('RELEASE_SOURCE_CONFLICT')
                if not dest.exists():additions[rel]=b.sha(source)
        b.write(root/'deployment-inputs.json',{'files':{str(p):b.sha(p) for p in protected+[ec,tc,b.BINARY,b.UNIT]},
            'spool':snapshot(spool),'additions':additions,'release':b.files(release),'bundle':b.sha(bundle/'manifest.json'),
            'binary':b.sha(binary),'containers':b.production_containers(),
            'candidate_manifest_sha256':b.sha(candidate/'candidate-manifest.json')})
        print('PREPARED R6AW release; live files unchanged');return
    if (root/'deployment.json').exists():raise ValueError('RELEASE_ALREADY_APPLIED')
    inputs=b.read(root/'deployment-inputs.json')
    if b.sha(candidate/'candidate-manifest.json')!=inputs['candidate_manifest_sha256']:
        raise ValueError('RELEASE_CANDIDATE_CHANGED')
    package_check=b.read(root/'package-validation.json');install_check=b.read(root/'installation-validation.json')
    if (package_check.get('result')!='PASS' or package_check.get('bundle_manifest_sha256')!=inputs['bundle']
            or package_check.get('actual_combinations')!=24):raise ValueError('PACKAGE_VERIFICATION_REQUIRED')
    if (install_check.get('result')!='PASS' or install_check.get('visible_protected_combinations')!=24
            or install_check.get('candidate_environment_catalog_sha256')!=b.sha(install/'environment-catalog.json')
            or install_check.get('candidate_template_catalog_sha256')!=b.sha(install/'template-catalog.json')):
        raise ValueError('INSTALLATION_VERIFICATION_REQUIRED')
    if b.files(release)!=inputs['release'] or b.sha(binary)!=inputs['binary'] or b.sha(bundle/'manifest.json')!=inputs['bundle']:
        raise ValueError('RELEASE_MATERIAL_CHANGED')
    def preserved():
        return all(b.sha(p)==inputs['files'][str(p)] for p in protected)
    for name,digest in inputs['files'].items():
        if b.sha(Path(name))!=digest:raise ValueError('RELEASE_INPUT_CHANGED')
    if snapshot(spool)!=inputs['spool']:raise ValueError('RELEASE_JOBS_CHANGED')
    b.idle(spool)
    backup=root/'deployment-backup';backup.mkdir(mode=0o700)
    for p in (b.BINARY,b.UNIT,ec,tc):shutil.copy2(p,backup/p.name)
    changed=False;added=[]
    replacements=[(binary,b.BINARY,0o755),(unit,b.UNIT,0o644),(install/'environment-catalog.json',ec,0o600),(install/'template-catalog.json',tc,0o600)]
    try:
        b.run(['systemctl','--user','stop',b.SERVICE]);b.idle(spool)
        b.run(['systemctl','--user','stop','profile-adapter.service'])
        with (spool/'.lock').open('a+b') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if snapshot(spool)!=inputs['spool'] or not preserved():raise ValueError('RELEASE_INPUT_CHANGED')
            for name,digest in inputs['files'].items():
                if b.sha(Path(name))!=digest:raise ValueError('RELEASE_INPUT_CHANGED')
            changed=True
            for rel,digest in inputs['additions'].items():
                target=spool/rel;target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                with target.open('xb') as stream:
                    os.fchmod(stream.fileno(),0o600);stream.write((install/rel).read_bytes());stream.flush();os.fsync(stream.fileno())
                added.append(rel)
                if b.sha(target)!=digest:raise ValueError('RELEASE_COPY_CHANGED')
            for src,dst,mode in replacements:b.replace(src,dst,mode)
        b.run(['systemctl','--user','daemon-reload']);b.run(['systemctl','--user','start','profile-adapter.service']);b.ready(cfg)
        b.run(['systemctl','--user','start',b.SERVICE])
        if b.run(['systemctl','--user','is-active',b.SERVICE]).strip()!='active':raise ValueError('RUNNER_NOT_ACTIVE')
        pid=b.run(['systemctl','--user','show','profile-adapter.service','-p','MainPID','--value']).strip()
        if b.sha(Path('/proc')/pid/'exe')!=inputs['binary']:raise ValueError('ADAPTER_EXECUTABLE_CHANGED')
        if not preserved() or snapshot(spool)!={**inputs['spool'],**inputs['additions']}:raise ValueError('PROTECTED_STATE_CHANGED')
        if b.production_containers()!=inputs['containers']:raise ValueError('PRODUCTION_CONTAINERS_CHANGED')
        request=urllib.request.Request('http://'+cfg['listen_address']+'/auth/login',headers={'Host':urlsplit(cfg['public_base_url']).netloc})
        with urllib.request.urlopen(request,timeout=8) as response:
            html=response.read().decode()
            if response.status!=200 or '平台尚未初始化' not in html:raise ValueError('SETUP_STATE_CHANGED')
    except BaseException:
        b.run(['systemctl','--user','stop',b.SERVICE]);b.run(['systemctl','--user','stop','profile-adapter.service'])
        with (spool/'.lock').open('a+b') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            safe=preserved() and snapshot(spool)=={**inputs['spool'],**{k:inputs['additions'][k] for k in added}}
            safe=safe and all(b.sha(dst) in (inputs['files'][str(dst)],b.sha(src)) for src,dst,_ in replacements)
            if changed and safe:
                for _,dst,mode in replacements:b.replace(backup/dst.name,dst,mode)
                for rel in added:
                    if b.sha(spool/rel)!=inputs['additions'][rel]:raise ValueError('ROLLBACK_SOURCE_CHANGED')
                    (spool/rel).unlink()
                b.write(root/'rollback.json',{'result':'RESTORED','added_files_removed':len(added)})
            elif changed:b.write(root/'rollback-held.json',{'reason':'new protected state; retain and reconcile'})
        b.run(['systemctl','--user','daemon-reload']);b.run(['systemctl','--user','start','profile-adapter.service']);b.run(['systemctl','--user','start',b.SERVICE])
        raise
    b.write(root/'deployment.json',{'result':'PASS','adapter_sha256':inputs['binary'],'builtin_combinations':24,
        'protected_state_preserved':True,'production_containers_preserved':True,'setup_required':True,
        'added_files':inputs['additions'],'release_manifest':inputs['release']})
    print('PASS R6AW deployed; 24 built-ins installed; accounts, history and containers preserved')

if __name__=='__main__':main()
