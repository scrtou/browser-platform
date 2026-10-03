"""Custom Chromix/native Firefox generation and publication under the spool lock."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
from datetime import datetime,timezone
from template_sources import raw_json,write,sha,source_records,validate_generation_target,publish_compatibility,TARGETS

ROOT=Path(__file__).resolve().parent
ENGINE_ROOT=ROOT.parent/'environment-engines'
sys.path.insert(0,str(ENGINE_ROOT))
from artifact import validate,SCHEMAS

def runtime_spec(artifact):
    if "spec" not in artifact:return artifact
    spec=artifact["spec"];return {"id":spec["id"],"revision":spec["revision"],"browserVersion":"152.0","schemaVersion":artifact["schemaVersion"],"locale":spec["locale"],"languages":spec["languages"],"timezone":spec["timezone"],"screen":{"width":spec["screen"]["width"],"height":spec["screen"]["height"],"dpr":"system","mode":"auto"},"window":spec["window"],"runtimeImageDigest":artifact["runtimeImageDigest"]}


def now():return datetime.now(timezone.utc).isoformat()
def encode(value):return (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
def write_private(path,raw):write(path,json.loads(raw))
def private(path):
    path.mkdir(mode=0o700,parents=True,exist_ok=True)
    if path.is_symlink() or path.stat().st_mode&0o077:raise ValueError('NATIVE_DIRECTORY_UNSAFE')
    return path

def target_image(path,target):
    registry=raw_json(path)
    if set(registry)!={'version','targets'} or registry['version']!=1:raise ValueError('NATIVE_TARGET_REGISTRY_INVALID')
    value=registry['targets'].get(target['browser_template_id'])
    if not isinstance(value,dict) or set(value)!={'engine','version','image'} or value['engine']!=target['engine'] or value['version']!=target['browser_version'] or not re.fullmatch('sha256:[a-f0-9]{64}',value['image']):raise ValueError('NATIVE_TARGET_UNSUPPORTED')
    return value['image']

def generate(root,request,image,out):
    fp,dp=source_records(root,request);target=request['generation'];engine=target['engine']
    if fp.get('version')!=2:raise ValueError('NATIVE_GENERIC_SOURCE_REQUIRED')
    digest=hashlib.sha256(json.dumps(target,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    cache=private(private(private(root/'fingerprint-cache')/fp['id'])/digest);device=cache/'device.json'
    expected={'source_sha256':request['templates']['fingerprint_sha256'],'generation':target,'image':image}
    created=not device.exists()
    if created:write(device,{**expected,**({'seed':secrets.randbelow(2**64-1)+1} if engine=='chromix' else {})})
    frozen=raw_json(device)
    if frozen.get('image')!=image:
        # Only an explicitly staged runtime revision may reuse this identity.
        # Never mutate the canonical cache or silently reroll its seed.
        variant=cache/'runtimes'/image.removeprefix('sha256:')/'device.json'
        if not variant.is_file():raise ValueError('NATIVE_CACHE_CHANGED')
        revised=raw_json(variant)
        if {k:v for k,v in revised.items() if k!='image'}!={k:v for k,v in frozen.items() if k!='image'}:
            raise ValueError('NATIVE_CACHE_CHANGED')
        frozen=revised
    if {k:v for k,v in frozen.items() if k!='seed'}!=expected:raise ValueError('NATIVE_CACHE_CHANGED')
    spec=request['spec']
    artifact={'schemaVersion':SCHEMAS[engine],'id':spec['id'],'revision':spec['revision'],'browserVersion':target['browser_version'],
              'locale':fp['locale'],'languages':fp['languages'],'timezone':fp['timezone'],'screen':{'width':dp['width'],'height':dp['height'],'dpr':1},
              'window':{'width':dp['window_width'],'height':dp['window_height']},'runtimeImageDigest':image}
    if dp['mode']=='auto':artifact['screen'].update(mode='auto',dpr='system')
    if engine=='chromix':artifact['seed']=frozen['seed']
    validate(artifact,engine)
    path=out/'environment.json'
    if path.exists():
        if raw_json(path)!=artifact:raise ValueError('NATIVE_ARTIFACT_CHANGED')
    else:write(path,artifact)
    return artifact,fp,dp,int(created)

def accepted(report,artifact,image):
    value=raw_json(report)
    if (value.get('schemaVersion')!='browser-platform/native-acceptance/v1' or value.get('status')!='pass' or value.get('phase')!='all'
            or value.get('artifactSHA256')!=sha(artifact) or value.get('runtimeImageDigest')!=image
            or value.get('recreationsPerHome',0)<10 or len(value.get('observations',[]))<22
            or value.get('offlineBackupRestore')!='pass' or value.get('normalDesktopInput') is not True or value.get('displayAuthentication') is not True):
        raise ValueError('NATIVE_ACCEPTANCE_FAILED')
    if runtime_spec(raw_json(artifact))['screen'].get('mode')=='auto' and value.get('dynamicDisplay')!='pass':raise ValueError('NATIVE_ACCEPTANCE_FAILED')
    return value

def definition(artifact_path,report_path,spec,engine,args):
    image=spec['runtimeImageDigest']
    env={'BROWSER_PLATFORM_ENVIRONMENT_ID':spec['id'],'BROWSER_PLATFORM_ARTIFACT_SHA256':sha(artifact_path),'BROWSER_PLATFORM_ACCEPTANCE_SHA256':sha(report_path),
         'BROWSER_PLATFORM_RUNTIME_IMAGE_DIGEST':image,'BROWSER_PLATFORM_LOCALE':spec['locale'],'BROWSER_PLATFORM_LANGUAGES':','.join(spec['languages']),
         'PIXELFLUX_WAYLAND':'false','TZ':spec['timezone'],'LANG':spec['locale'].replace('-','_')+'.UTF-8',
         'SELKIES_MANUAL_WIDTH':str(spec['screen']['width']),'SELKIES_MANUAL_HEIGHT':str(spec['screen']['height']),
         'SELKIES_ALLOWED_ORIGINS':args.session_origin.rstrip('/'),'TITLE':engine.title(),'SELKIES_UI_TITLE':engine.title()}
    if spec['screen'].get('mode')=='auto':
        env.pop('SELKIES_MANUAL_WIDTH');env.pop('SELKIES_MANUAL_HEIGHT');env.update(BROWSER_PLATFORM_DISPLAY_MODE='auto',MAX_RES='3840x2160',SELKIES_MANUAL_RESOLUTION='false')
    else:env['SELKIES_MANUAL_RESOLUTION']='true'
    executable=('/opt/camoufox-python/bin/python /usr/local/lib/browser-platform/environment.py' if engine=='camoufox' else 'python3 /usr/local/lib/browser-platform/'+engine+'-launcher.py')
    script='#!/bin/sh\nexec '+executable+' launch "${SEALSKIN_URL:-about:blank}"\n'
    mounts=[{'Type':'bind','Source':str(p),'Target':'/run/browser-platform/'+p.name,'ReadOnly':True} for p in (artifact_path,report_path)]
    if args.clipboard_addon:
        import importlib.util
        module=importlib.util.spec_from_file_location('native_prepare',ROOT/'prepare-sealskin.py');prepare=importlib.util.module_from_spec(module);module.loader.exec_module(prepare)
        extras,_=prepare.clipboard_mounts(args.clipboard_addon);mounts+=extras
        env.update(SELKIES_UI_SIDEBAR_SHOW_FILES='true',SELKIES_FILE_TRANSFERS='upload')
    security=['no-new-privileges:true']
    if engine=='chromix':security+=['seccomp='+json.dumps(json.loads((ROOT.parent/'chromix/seccomp.json').read_bytes()),separators=(',',':'))]
    return {'id':engine+'-template','name':engine.title(),'logo':'','url':'https://example.com/','source':'Browser Platform','source_app_id':engine,
            'provider':'docker','home_directories':True,'users':[args.username],'groups':[],'auto_update':False,'app_template':args.template,'is_meta_app':False,
            'provider_config':{'image':image,'port':3000,'type':'browser','url_support':True,'open_support':False,'nvidia_support':False,'dri3_support':False,'extensions':[],
            'autostart':True,'custom_autostart_script_b64':base64.b64encode(script.encode()).decode(),'env':[{'name':k,'value':v} for k,v in env.items()],
            'docker_overrides':{'mem_limit':'1536m','nano_cpus':1500000000,'pids_limit':512,'shm_size':'256m','security_opt':security,'mounts':mounts}}}

def process_native(spool,request,args,*,fixture,append_catalog,generator=None):
    job=request['job_id'];target=request['generation'];engine=target['engine'];started=now();progress={'started_at':started}
    try:
        if not args.native_targets or not args.template_catalog:raise ValueError('NATIVE_TARGET_REGISTRY_REQUIRED')
        image=target_image(args.native_targets,target);progress['image']=image
        validate_generation_target(args.template_catalog,target,target['browser_template_id'])
        actual=json.loads(subprocess.check_output(['docker','image','inspect',image],timeout=15))[0]
        if actual['Id']!=image or actual['Config']['Labels'].get('io.browser-platform.custom-generation')!='1' or actual['Config']['Labels'].get('io.browser-platform.browser-engine')!=engine:raise ValueError('NATIVE_IMAGE_MISMATCH')
        out=private(spool.root/'artifacts'/request['spec']['id']);evidence=private(spool.root/'evidence'/job)
        spool.write_status(job,status='running',phase='generate',**progress)
        if engine=='camoufox':
            from template_sources import generate_combination
            attempts,fp,dp=generate_combination(spool.root,request,image,out,evidence,generator)
            artifact=raw_json(out/'environment.json')
        else:artifact,fp,dp,attempts=generate(spool.root,request,image,out)
        path=out/'environment.json';report_path=out/'acceptance.json';progress.update(attempts=attempts,artifact_id=artifact['id'],artifact_sha256=sha(path))
        spool.write_status(job,status='running',phase='acceptance',**progress)
        if not report_path.exists():
            with fixture(job,image) as active:
                with (evidence/'acceptance.log').open('w') as log:
                    code=subprocess.run([sys.executable,str(ENGINE_ROOT/'acceptance.py'),'--artifact',str(path),'--network',active.networks['internal'],'--output',str(report_path),'--recreations',str(args.recreations)]+(['--client-browsers',str(args.client_browsers.resolve())] if getattr(args,'client_browsers',None) else []),stdout=log,stderr=subprocess.STDOUT,timeout=3600).returncode
            if code:raise ValueError('NATIVE_ACCEPTANCE_FAILED')
        report=accepted(report_path,path,image);observed=report['observations'][0]['observed'];spec=runtime_spec(artifact)
        ua=observed['userAgent'];major=target['browser_version'].split('.')[0]
        if observed['platform']!='Linux x86_64' or (('Chrome/'+major+'.') not in ua if engine=='chromix' else not ua.endswith('Firefox/'+major+'.0')):raise ValueError('NATIVE_BROWSER_MISMATCH')
        progress['acceptance_sha256']=sha(report_path);spool.write_status(job,status='running',phase='publish',**progress)
        validate_generation_target(args.template_catalog,target,target['browser_template_id'])
        if target_image(args.native_targets,target)!=image:raise ValueError('NATIVE_TARGET_IMAGE_CHANGED')
        entry={'id':artifact['id'],'sha256':sha(path),'acceptance_sha256':sha(report_path),'image':image,'source':'custom','status':'accepted','application':definition(path,report_path,spec,engine,args),
               'required_runtime_capabilities':{'browser_shutdown_version':1,'session_auth_version':1},'template_revision':1,'browser_template_id':target['browser_template_id'],
               'browser_engine':engine,'browser_version':target['browser_version'],'os_family':'linux','platform':observed['platform'],'user_agent':ua,
               'locale':spec['locale'],'languages':spec['languages'],'timezone':spec['timezone'],'screen':'auto@system' if dp['mode']=='auto' else str(dp['width'])+'x'+str(dp['height'])+'@1',
               'job_id':job,'label':fp['label']+' · '+dp['label'],'accepted_at':now()}
        append_catalog(args.catalog,entry)
        publish_compatibility(args.template_catalog,entry,dp,write_private,encode,target)
        spool.write_status(job,status='accepted',phase='done',finished_at=now(),environment_id=artifact['id'],**progress);return 'accepted'
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as error:
        code=str(error) if isinstance(error,ValueError) and re.fullmatch('[A-Z_]+',str(error)) else 'NATIVE_JOB_FAILED'
        spool.write_status(job,status='failed',phase='failed',code=code,finished_at=now(),**progress);return 'failed'
