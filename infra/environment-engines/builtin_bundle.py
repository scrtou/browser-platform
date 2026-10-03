"""Strict portable built-in package validation shared by export and installation."""
import hashlib
import itertools
import json
from pathlib import Path
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'camoufox'))
from template_sources import BUILTIN_FINGERPRINTS,TARGETS,compose,raw_json,sha,source_records,validate_generation_target
from native_jobs import target_image
from artifact import validate

DISPLAY_IDS={'display-0000000000000001','display-0000000000000002'}

def desktop_report(path,artifact,image,auto):
    report=raw_json(path)
    if (report.get('schemaVersion')!='browser-platform/native-acceptance/v1'
            or report.get('status')!='pass' or report.get('phase')!='all'
            or report.get('artifactSHA256')!=sha(artifact) or report.get('runtimeImageDigest')!=image
            or report.get('recreationsPerHome',0)<10 or len(report.get('observations',[]))<22
            or report.get('offlineBackupRestore')!='pass' or report.get('normalDesktopInput') is not True
            or report.get('displayAuthentication') is not True or auto and report.get('dynamicDisplay')!='pass'):
        raise ValueError('BUILTIN_DESKTOP_ACCEPTANCE_FAILED')
    return report

def verify_bundle(bundle):
    if bundle.is_symlink():raise ValueError('BUILTIN_BUNDLE_SYMLINK')
    manifest=raw_json(bundle/'manifest.json')
    actual=set()
    for path in bundle.rglob('*'):
        if path.is_symlink():raise ValueError('BUILTIN_BUNDLE_SYMLINK')
        if not path.is_dir() and not path.is_file():raise ValueError('BUILTIN_BUNDLE_NOT_REGULAR')
        if path.is_file() and path!=bundle/'manifest.json':actual.add(str(path.relative_to(bundle)))
    if actual!=set(manifest):raise ValueError('BUILTIN_BUNDLE_CONTENT_CHANGED')
    for name,digest in manifest.items():
        path=Path(name)
        if path.is_absolute() or '..' in path.parts or sha(bundle/path)!=digest:raise ValueError('BUILTIN_BUNDLE_DIGEST')
    catalog=raw_json(bundle/'catalog.json');templates=raw_json(bundle/'template-catalog.json')
    provenance=raw_json(bundle/'provenance.json')
    if (catalog.get('version')!=1 or templates.get('version')!=1
            or len(catalog['artifacts'])!=24 or len(templates['compatibility'])!=24 or len(provenance)!=24):
        raise ValueError('BUILTIN_EXPECTED_24')
    if (len(templates['browser_templates'])!=3 or {v['id'] for v in templates['browser_templates']}!=set(TARGETS)
            or len(templates['display_templates'])!=2 or {v['id'] for v in templates['display_templates']}!=DISPLAY_IDS):
        raise ValueError('BUILTIN_TEMPLATE_SET')
    expected=set(itertools.product(TARGETS,BUILTIN_FINGERPRINTS,DISPLAY_IDS))
    sources={v['environment_id']:v for v in provenance}
    entries={v['id']:v for v in catalog['artifacts']}
    if len(sources)!=24 or len(entries)!=24 or set(sources)!=set(entries):raise ValueError('BUILTIN_ID_SET')
    files={'catalog.json','template-catalog.json','provenance.json','native-targets.json'}
    seen=set();pairs=set()
    for ident,entry in entries.items():
        if not re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,127}',ident):raise ValueError('BUILTIN_ID_INVALID')
        ref=sources[ident];generation=ref['generation'];target=generation['browser_template_id']
        if target not in TARGETS:raise ValueError('BUILTIN_TARGET_MISMATCH')
        engine,version,_=TARGETS[target]
        if generation!={'browser_template_id':target,'browser_template_revision':1,'engine':engine,'browser_version':version}:
            raise ValueError('BUILTIN_TARGET_MISMATCH')
        validate_generation_target(bundle/'template-catalog.json',generation,target,templates)
        image=target_image(bundle/'native-targets.json',generation)
        key=target,ref['templates']['fingerprint_id'],ref['templates']['display_id']
        if key not in expected or key in seen:raise ValueError('BUILTIN_MATRIX_INCOMPLETE')
        seen.add(key)
        fp=raw_json(bundle/'templates/fingerprints'/(key[1]+'.json'))
        dp=raw_json(bundle/'templates/displays'/(key[2]+'.json'));auto=dp['mode']=='auto'
        expected_name='自动分辨率 · DPR 随缩放变化' if auto else '固定 1920×1080 · DPR 1'
        expected_date='2026-10-01T00:00:00Z' if auto else '2026-10-02T00:00:00Z'
        if dp['label']!=expected_name or dp['created_at']!=expected_date:raise ValueError('BUILTIN_DISPLAY_SOURCE_CHANGED')
        screen={'width':1280,'height':720,'mode':'auto','dprMode':'system'} if auto else {'width':dp['width'],'height':dp['height'],'deviceScaleFactor':dp['dpr']}
        source_spec={k:fp[k] for k in ('locale','languages','timezone')}
        source_spec.update(screen=screen,window={'width':dp['window_width'],'height':dp['window_height']})
        source_records(bundle,{'version':3,'generation':generation,'templates':ref['templates'],'spec':source_spec})
        prefix='combinations/'+ident+'/'
        artifact_path=bundle/prefix/'environment.json';report_path=bundle/prefix/'acceptance.json'
        value=raw_json(artifact_path);spec=value.get('spec',value)
        if (entry.get('status')!='accepted' or entry.get('source')!='frozen'
                or entry['browser_template_id']!=target or entry['browser_engine']!=engine or entry['browser_version']!=version
                or entry['image']!=image or value['runtimeImageDigest']!=image or spec['id']!=ident
                or entry['sha256']!=sha(artifact_path) or entry['acceptance_sha256']!=sha(report_path)):
            raise ValueError('BUILTIN_ARTIFACT_BINDING')
        if any(spec[k]!=fp[k] or entry[k]!=fp[k] for k in ('locale','languages','timezone')):
            raise ValueError('BUILTIN_FINGERPRINT_MISMATCH')
        expected_screen='auto@system' if auto else '1920x1080@1'
        if entry['screen']!=expected_screen or spec['window']!=source_spec['window']:
            raise ValueError('BUILTIN_DISPLAY_MISMATCH')
        expected_pair={'browser_template_id':target,'environment_artifact_id':ident,'display_template_id':key[2],'status':'accepted','builtin':True}
        if templates['compatibility'].count(expected_pair)!=1:raise ValueError('BUILTIN_COMPATIBILITY_MISMATCH')
        pairs.add((target,ident,key[2]))
        display=next(v for v in templates['display_templates'] if v['id']==key[2])
        if display!={'id':dp['id'],'revision':1,'status':'accepted','label':dp['label'],'display_server':'x11','transport':'selkies','screen':expected_screen,'scaling':'auto' if auto else 'fixed'}:
            raise ValueError('BUILTIN_DISPLAY_CATALOG_MISMATCH')
        digest=hashlib.sha256(json.dumps(generation,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        cache='fingerprint-cache/'+fp['id']+'/'+digest+'/'
        binding={'source_sha256':ref['templates']['fingerprint_sha256'],'image':image}
        if engine=='camoufox':
            base=raw_json(bundle/cache/'environment.json');receipt=raw_json(bundle/cache/'receipt.json')
            if receipt!={**binding,'artifact_sha256':sha(bundle/cache/'environment.json')}:
                raise ValueError('BUILTIN_CACHE_BINDING')
            if spec['screen']!=screen:raise ValueError('BUILTIN_DISPLAY_MISMATCH')
            composed=compose(base,spec,image)
            if {k:v for k,v in composed.items() if k!='createdAt'}!={k:v for k,v in value.items() if k!='createdAt'}:
                raise ValueError('BUILTIN_CACHE_DEVICE_MISMATCH')
            files.update({cache+'environment.json',cache+'receipt.json'})
        else:
            validate(value,engine)
            device=raw_json(bundle/cache/'device.json')
            expected_device={**binding,'generation':generation}
            if engine=='chromix':expected_device['seed']=value['seed']
            if device!=expected_device:raise ValueError('BUILTIN_CACHE_DEVICE_MISMATCH')
            expected_native_screen={'width':dp['width'],'height':dp['height'],'dpr':1}
            if auto:expected_native_screen.update(mode='auto',dpr='system')
            if spec['screen']!=expected_native_screen:raise ValueError('BUILTIN_DISPLAY_MISMATCH')
            files.add(cache+'device.json')
        if engine=='camoufox' and not auto:
            report=raw_json(report_path);replay=report.get('results',{}).get('homeReplay',{})
            if (report.get('schemaVersion')!='browser-platform/camoufox-acceptance/v1'
                    or report.get('status')!='pass' or report.get('phase')!='all'
                    or report.get('artifactSHA256')!=entry['sha256'] or report.get('runtimeImageDigest')!=image
                    or replay.get('homes')!=2 or replay.get('recreationsPerHome',0)<10
                    or len(replay.get('observations',[]))<22 or replay.get('observationsStable') is not True
                    or replay.get('storageRestored') is not True or replay.get('offlineBackupRestore')!='pass'):
                raise ValueError('BUILTIN_FULL_ACCEPTANCE_REQUIRED')
            extra=bundle/prefix/'desktop-acceptance.json'
            if entry.get('desktop_acceptance_sha256')!=sha(extra):raise ValueError('BUILTIN_DESKTOP_DIGEST')
            desktop_report(extra,artifact_path,image,False);files.add(prefix+'desktop-acceptance.json')
        else:desktop_report(report_path,artifact_path,image,auto)
        files.update({prefix+'environment.json',prefix+'acceptance.json','templates/fingerprints/'+fp['id']+'.json','templates/displays/'+dp['id']+'.json'})
    if seen!=expected or len(pairs)!=24:raise ValueError('BUILTIN_MATRIX_INCOMPLETE')
    if files!=set(manifest):raise ValueError('BUILTIN_UNEXPECTED_FILES')
    return catalog,templates
