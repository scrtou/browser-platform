#!/usr/bin/env python3
"""Prepare portable built-ins for one host; never replace live catalogs/services.

Run against a checksum-verified package exported from full acceptance. The
resulting private directory contains immutable assets, source caches and two
catalog candidates. Activation requires a deployment holding the runner lock
with catalog writers stopped; source conflicts and old evidence must be retained.
"""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from types import SimpleNamespace
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]/'camoufox'
sys.path.insert(0,str(ROOT))
from template_sources import raw_json,sha,BUILTIN_FINGERPRINTS,TARGETS
from native_jobs import definition,runtime_spec,accepted


def write(path,value):
    with path.open('x') as f:
        os.chmod(path,0o600);json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')


from builtin_bundle import verify_bundle


def merge(existing,incoming,key,metadata=()):
    result=copy.deepcopy(existing or [])
    for value in incoming:
        matches=[v for v in result if all(v[k]==value[k] for k in key)]
        if matches and (len(matches)!=1 or {k:v for k,v in matches[0].items() if k not in metadata}!={k:v for k,v in value.items() if k not in metadata}):raise ValueError('BUILTIN_INSTALL_CONFLICT')
        if not matches:result.append(value)
    return result


def prepare(args):
    origin=urlsplit(args.session_origin)
    if origin.scheme!='https' or not origin.hostname or origin.username is not None or origin.password is not None or origin.path not in ('','/') or origin.query or origin.fragment:raise ValueError('BUILTIN_ORIGIN_INVALID')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',args.username):raise ValueError('BUILTIN_USERNAME_INVALID')
    catalog,templates=verify_bundle(args.bundle)
    if args.output.exists():raise ValueError('BUILTIN_DESTINATION_EXISTS')
    for image in {e['image'] for e in catalog['artifacts']}:
        actual=subprocess.check_output(['docker','image','inspect',image,'--format','{{.Id}}'],text=True).strip()
        if actual!=image:raise ValueError('BUILTIN_IMAGE_MISMATCH')
    args.output.mkdir(mode=0o700,parents=True)
    for name in ['combinations','templates','fingerprint-cache']:
        shutil.copytree(args.bundle/name,args.output/name)
    spec=importlib.util.spec_from_file_location('builtin_runner',ROOT/'environment-job.py');runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    options=SimpleNamespace(username=args.username,session_origin=args.session_origin,clipboard_addon=args.clipboard_addon,template='Default',store='SealSkin Apps')
    entries=[]
    for entry in catalog['artifacts']:
        artifact=args.output/'combinations'/entry['id']/'environment.json';report=artifact.with_name('acceptance.json');value=raw_json(artifact)
        row=copy.deepcopy(entry);row.pop('desktop_acceptance_sha256',None)
        if entry['browser_engine']=='camoufox' and entry['screen']!='auto@system':
            row['application']=runner.build_template(runner.load_prepare(),artifact_path=artifact,report_path=report,artifact=value,image=entry['image'],args=options,verify=True)
        else:row['application']=definition(artifact,report,runtime_spec(value),entry['browser_engine'],options)
        entries.append(row)
    ec=raw_json(args.environment_catalog) if args.environment_catalog else {'version':1,'artifacts':[]}
    tc=raw_json(args.template_catalog) if args.template_catalog else {'version':1,'browser_templates':[],'display_templates':[],'compatibility':[]}
    ec['artifacts']=merge(ec['artifacts'],entries,['id'])
    for field,keys in [('browser_templates',['id']),('display_templates',['id']),('compatibility',['browser_template_id','environment_artifact_id','display_template_id'])]:
        # Existing accepted target names/dates are presentation/history. Keep
        # them only if every runtime identity and admission field still agrees.
        tc[field]=merge(tc[field],templates[field],keys,('label','accepted_at') if field=='browser_templates' else ())
    write(args.output/'environment-catalog.json',ec);write(args.output/'template-catalog.json',tc)
    manifest={str(p.relative_to(args.output)):sha(p) for p in args.output.rglob('*') if p.is_file()}
    write(args.output/'install-manifest.json',manifest)
    return {'result':'PREPARED','builtin_combinations':len(entries),'files':len(manifest),'activated':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['bundle','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--username',required=True);p.add_argument('--session-origin',required=True)
    for name in ['clipboard-addon','environment-catalog','template-catalog']:p.add_argument('--'+name,type=Path)
    a=p.parse_args();os.umask(0o077)
    for name in ['bundle','output','clipboard_addon','environment_catalog','template_catalog']:
        if getattr(a,name) is not None:setattr(a,name,getattr(a,name).resolve())
    print(json.dumps(prepare(a)))

if __name__=='__main__':main()
