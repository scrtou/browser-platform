#!/usr/bin/env python3
"""Verify a real completed built-in package, tamper refusal, and host preparation."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

from builtin_bundle import verify_bundle
from template_sources import raw_json,sha
module_spec=importlib.util.spec_from_file_location('tested_builtin_install',Path(__file__).with_name('prepare-builtin-install.py'))
installer=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(installer)

def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');path.chmod(0o600)

def manifest(root):
    value={str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file() and p.name!='manifest.json'}
    write(root/'manifest.json',value)

def mutate_json(path,edit):
    value=raw_json(path);edit(value);write(path,value)

def check(args):
    os.umask(0o077);bundle=args.bundle.resolve();output=args.output.resolve()
    if output.exists():raise ValueError('QA_DESTINATION_EXISTS')
    original=sha(bundle/'manifest.json');catalog,_=verify_bundle(bundle)
    output.mkdir(mode=0o700)
    records=[]
    def refusal(name,edit,rehash=True):
        dest=output/name;shutil.copytree(bundle,dest);edit(dest)
        if rehash:manifest(dest)
        try:verify_bundle(dest)
        except (ValueError,KeyError,TypeError,OSError) as error:
            records.append({'case':name,'result':'rejected','code':str(error) if isinstance(error,ValueError) else type(error).__name__})
        else:raise AssertionError('INVALID_BUILTIN_BUNDLE_ACCEPTED_'+name)
    native=next(e for e in catalog['artifacts'] if e['browser_engine']=='chromix')
    fixed=next(e for e in catalog['artifacts'] if e['browser_engine']=='camoufox' and e['screen']=='1920x1080@1')
    def artifact_path(root,entry,name='environment.json'):return root/'combinations'/entry['id']/name
    def digest_corruption(root):
        with artifact_path(root,native).open('a') as f:f.write(' ')
    refusal('changed-digest',digest_corruption,False)
    refusal('extra-file',lambda root:(root/'unexpected.txt').write_text('extra'),False)
    def symlink(root):
        target=artifact_path(root,native);target.unlink();target.symlink_to(artifact_path(bundle,native))
    refusal('symlink',symlink,False)
    refusal('duplicate-provenance',lambda root:mutate_json(root/'provenance.json',lambda v:v.__setitem__(1,copy.deepcopy(v[0]))))
    refusal('compatibility-mix',lambda root:mutate_json(root/'template-catalog.json',lambda v:v['compatibility'][0].__setitem__('display_template_id','display-0000000000000002' if v['compatibility'][0]['display_template_id'].endswith('1') else 'display-0000000000000001')))
    refusal('source-mix',lambda root:mutate_json(root/'templates/fingerprints/fp-0000000000000001.json',lambda v:v.__setitem__('timezone','Asia/Tokyo')))
    refusal('display-mix',lambda root:mutate_json(root/'templates/displays/display-0000000000000002.json',lambda v:v.__setitem__('width',1280)))
    def cache_mix(root):
        cache=next(p for p in (root/'fingerprint-cache').rglob('device.json') if 'seed' in raw_json(p))
        mutate_json(cache,lambda v:v.__setitem__('seed',v['seed']+1))
    refusal('device-mix',cache_mix)
    def report_short(root):
        path=artifact_path(root,native,'acceptance.json');mutate_json(path,lambda v:v.__setitem__('observations',v['observations'][:1]))
        mutate_json(root/'catalog.json',lambda v:next(e for e in v['artifacts'] if e['id']==native['id']).__setitem__('acceptance_sha256',sha(path)))
    refusal('short-report',report_short)
    def missing_desktop(root):
        artifact_path(root,fixed,'desktop-acceptance.json').unlink()
        mutate_json(root/'catalog.json',lambda v:next(e for e in v['artifacts'] if e['id']==fixed['id']).pop('desktop_acceptance_sha256'))
    refusal('missing-desktop',missing_desktop)
    def image_mix(root):
        mutate_json(root/'native-targets.json',lambda v:v['targets'][native['browser_template_id']].__setitem__('image',fixed['image']))
    refusal('image-mix',image_mix)
    pristine=output/'pristine'
    options=SimpleNamespace(bundle=bundle,output=pristine,username='r6aw-qa',session_origin='https://entry.r6aw.test',
        clipboard_addon=args.clipboard_addon.resolve(),environment_catalog=None,template_catalog=None)
    prepared=installer.prepare(options)
    before={str(p.relative_to(pristine)):sha(p) for p in pristine.rglob('*') if p.is_file()}
    try:installer.prepare(options)
    except ValueError as error:
        if str(error)!='BUILTIN_DESTINATION_EXISTS':raise
    else:raise AssertionError('REPEATED_INSTALL_OVERWROTE_OUTPUT')
    if before!={str(p.relative_to(pristine)):sha(p) for p in pristine.rglob('*') if p.is_file()}:
        raise AssertionError('REPEATED_INSTALL_CHANGED_OUTPUT')
    records.append({'case':'repeat-destination','result':'rejected-without-change'})
    conflict=output/'conflicting-environments.json';values=raw_json(pristine/'environment-catalog.json')
    values['artifacts'][0]['timezone']='Pacific/Honolulu';write(conflict,values)
    other=SimpleNamespace(**{**vars(options),'output':output/'conflict-install','environment_catalog':conflict})
    try:installer.prepare(other)
    except ValueError as error:
        if str(error)!='BUILTIN_INSTALL_CONFLICT':raise
    else:raise AssertionError('CONFLICT_OVERWRITTEN')
    records.append({'case':'existing-conflict','result':'rejected'})
    with (output/'catalog-test.log').open('w') as log:
        subprocess.run([str(args.catalog_test.resolve()),'-test.run=^TestR6AWInstalledCatalog$','-test.v'],
            env=dict(os.environ,R6AW_CATALOG_ROOT=str(pristine)),stdout=log,stderr=subprocess.STDOUT,check=True)
    choices=raw_json(pristine/'verified-choices.json')
    if len(choices)!=24 or sha(bundle/'manifest.json')!=original:raise AssertionError('PACKAGE_CHANGED')
    verify_bundle(bundle)
    result={'result':'PASS','bundle_manifest_sha256':original,'actual_combinations':len(choices),'preparation':prepared,
        'cases':records,'source_bundle_unchanged':True,'production_modified':False}
    write(output/'result.json',result);return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('bundle','output','clipboard-addon','catalog-test'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();result=check(a);print(json.dumps(result))
if __name__=='__main__':main()
