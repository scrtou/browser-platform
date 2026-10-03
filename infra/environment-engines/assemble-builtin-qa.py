#!/usr/bin/env python3
"""Assemble completed independent QA parts without changing their reports/status."""
import argparse
import copy
import itertools
import json
import os
import re
from pathlib import Path
import shutil

from builtin_bundle import DISPLAY_IDS
from template_sources import BUILTIN_FINGERPRINTS,TARGETS,raw_json,sha,source_records

def write(path,value):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    with path.open('x') as f:
        os.fchmod(f.fileno(),0o600);json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')

def copy_equal(source,destination):
    if source.is_symlink() or not source.is_file():raise ValueError('QA_SOURCE_NOT_REGULAR')
    if destination.exists():
        if sha(destination)!=sha(source):raise ValueError('QA_PARTS_DISAGREE')
        return
    destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    with source.open('rb') as src,destination.open('xb') as dst:
        os.fchmod(dst.fileno(),0o600);shutil.copyfileobj(src,dst)

def assemble(parts,destination):
    if destination.exists():raise ValueError('QA_DESTINATION_EXISTS')
    expected=set(itertools.product(TARGETS,BUILTIN_FINGERPRINTS,DISPLAY_IDS));seen=set()
    templates={'version':1,'browser_templates':[],'display_templates':[],'compatibility':[]}
    entries=[];provenance=[]
    for part in parts:
        origin=Path(raw_json(part/'origin.json')['qa']) if (part/'origin.json').exists() else part
        catalog=raw_json(part/'environment-catalog.json');tc=raw_json(part/'template-catalog.json')
        if not catalog['artifacts']:raise ValueError('QA_PART_EMPTY')
        for field,keys in [('browser_templates',('id',)),('display_templates',('id',)),('compatibility',('browser_template_id','environment_artifact_id','display_template_id'))]:
            for value in tc[field]:
                same=[v for v in templates[field] if all(v[k]==value[k] for k in keys)]
                if same and same!=[value]:raise ValueError('QA_CATALOG_CONFLICT')
                if not same:templates[field].append(value)
        for value in catalog['artifacts']:
            entry=copy.deepcopy(value);ident=entry['id'];job=entry['job_id']
            if not re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,127}',ident) or not re.fullmatch(r'job-[a-f0-9]{16}',job):raise ValueError('QA_ID_INVALID')
            if any(v['id']==ident or v['job_id']==job for v in entries):raise ValueError('QA_DUPLICATE_ID')
            request=raw_json(part/'jobs/queue'/(job+'.json'));status=raw_json(part/'jobs/status'/(job+'.json'))
            fp,dp=source_records(part/'jobs',request)
            key=entry['browser_template_id'],fp['id'],dp['id']
            if key not in expected or key in seen or status['status']!='accepted':raise ValueError('QA_NOT_ACCEPTED_MATRIX')
            seen.add(key)
            for folder in ('queue','status'):copy_equal(part/'jobs'/folder/(job+'.json'),destination/'jobs'/folder/(job+'.json'))
            mounts=entry['application']['provider_config']['docker_overrides']['mounts']
            for name in ('environment.json','acceptance.json'):
                matches=[m for m in mounts if m['Target']=='/run/browser-platform/'+name]
                if len(matches)!=1 or Path(matches[0]['Source'])!=origin/'jobs/artifacts'/ident/name:
                    raise ValueError('QA_ARTIFACT_PATH')
                source=part/'jobs/artifacts'/ident/name;target=destination/'jobs/artifacts'/ident/name
                copy_equal(source,target);matches[0]['Source']=str(target)
            if entry['browser_engine']=='camoufox' and entry['screen']!='auto@system':
                copy_equal(part/'jobs/artifacts'/ident/'desktop-acceptance.json',destination/'jobs/artifacts'/ident/'desktop-acceptance.json')
            entries.append(entry)
        for kind,ids in [('fingerprints',BUILTIN_FINGERPRINTS),('displays',DISPLAY_IDS)]:
            for ident in ids:copy_equal(part/'jobs/templates'/kind/(ident+'.json'),destination/'jobs/templates'/kind/(ident+'.json'))
        for source in (part/'jobs/fingerprint-cache').rglob('*'):
            if source.is_file():copy_equal(source,destination/'jobs/fingerprint-cache'/source.relative_to(part/'jobs/fingerprint-cache'))
        provenance.append({'qa':str(origin),'collected_at':str(part),'environment_catalog_sha256':sha(part/'environment-catalog.json'),
            'template_catalog_sha256':sha(part/'template-catalog.json'),'combinations':len(catalog['artifacts'])})
    if seen!=expected or len(entries)!=24 or len(templates['compatibility'])!=24:raise ValueError('QA_MATRIX_INCOMPLETE')
    write(destination/'environment-catalog.json',{'version':1,'artifacts':entries})
    write(destination/'template-catalog.json',templates)
    write(destination/'assembly-provenance.json',provenance)
    write(destination/'assembly-manifest.json',{str(p.relative_to(destination)):sha(p) for p in destination.rglob('*') if p.is_file()})
    return {'result':'PASS','combinations':len(entries),'parts':len(parts),'reports_unchanged':True}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--part',type=Path,action='append',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();os.umask(0o077);print(json.dumps(assemble([x.resolve() for x in a.part],a.output.resolve())))
if __name__=='__main__':main()
