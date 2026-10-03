"""Independent template composition. No random generation on display reuse."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
from datetime import datetime, timezone

DISPLAY_KEYS={'screen.width','screen.height','screen.availWidth','screen.availHeight',
              'window.outerWidth','window.outerHeight','window.devicePixelRatio',
              'window.screenX','window.screenY'}

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def raw_json(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:raise ValueError('TEMPLATE_FILE_UNSAFE')
    return json.loads(path.read_bytes())
def write(path,value):
    raw=(json.dumps(value,indent=2,sort_keys=True)+'\n').encode()
    temp=path.with_name(path.name+'.new')
    with temp.open('xb') as f:
        os.chmod(temp,0o600);f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)

TARGETS = {'camoufox-linux-v152':('camoufox','152.0','Firefox'), 'chromix-linux-154':('chromix','154.0.8037.57','Chrome'), 'firefox-linux-155':('firefox','155.0.1','Firefox')}

BUILTIN_FINGERPRINTS = {
    'fp-'+format(n,'016x'): {'id':'fp-'+format(n,'016x'), 'version':2, 'builtin':True,
        'revision':1, 'label':'通用 '+region, 'locale':locale, 'languages':languages,
        'timezone':zone, 'created_at':'2026-10-02T00:00:00Z'}
    for n,region,locale,languages,zone in [
        (1,'US','en-US',['en-US','en'],'America/New_York'),
        (2,'TW','zh-TW',['zh-TW','zh','en-US','en'],'Asia/Taipei'),
        (3,'JP','ja-JP',['ja-JP','ja','en-US','en'],'Asia/Tokyo'),
        (4,'CN','zh-CN',['zh-CN','zh','en-US','en'],'Asia/Shanghai')]
}

TARGET_FIELDS = {'browser_template_id', 'browser_template_revision', 'engine', 'browser_version'}

def validate_target_shape(target):
    if (not isinstance(target, dict) or set(target) != TARGET_FIELDS
            or not isinstance(target['browser_template_id'],str) or target['browser_template_id'] not in TARGETS
            or type(target['browser_template_revision']) is not int or target['browser_template_revision'] < 1
            or (target['engine'],target['browser_version']) != TARGETS[target['browser_template_id']][:2]):
        raise ValueError('GENERATION_TARGET_INVALID')

def validate_generation_target(path, target, runner_id, catalog=None):
    validate_target_shape(target)
    if target['browser_template_id'] != runner_id:
        raise ValueError('GENERATION_RUNNER_MISMATCH')
    if catalog is None:
        catalog = raw_json(path)
    matches = [b for b in catalog['browser_templates'] if b['id'] == runner_id]
    if len(matches) != 1:
        raise ValueError('GENERATION_TARGET_CHANGED')
    b = matches[0]
    if (b.get('status') != 'accepted' or b.get('allow_new_browsers') is not True
            or b.get('revision') != target['browser_template_revision']
            or b.get('engine') != target['engine'] or b.get('version') != target['browser_version']
            or b.get('os_family') != 'linux' or b.get('platform') != 'Linux x86_64'
            or b.get('user_agent_product') != TARGETS[runner_id][2]):
        raise ValueError('GENERATION_TARGET_CHANGED')


def source_records(root,request):
    refs=request['templates']
    if set(refs)!={'fingerprint_id','fingerprint_sha256','display_id','display_sha256'}:raise ValueError('TEMPLATE_REFERENCE_INVALID')
    for k,prefix in [('fingerprint_id','fp-'),('display_id','display-')]:
        if not re.fullmatch(prefix+'[a-f0-9]{16}',refs[k]):raise ValueError('TEMPLATE_ID_INVALID')
    fp=root/'templates/fingerprints'/(refs['fingerprint_id']+'.json')
    dp=root/'templates/displays'/(refs['display_id']+'.json')
    fingerprint,display=raw_json(fp),raw_json(dp)
    fields = {'id','label','revision','locale','languages','timezone','created_at'}
    builtin_fingerprints = BUILTIN_FINGERPRINTS
    if isinstance(fingerprint,dict) and 'builtin' in fingerprint:
        if fingerprint['builtin'] is not True or fingerprint.get('version')!=2 or fingerprint.get('id') not in builtin_fingerprints:raise ValueError('FINGERPRINT_TEMPLATE_FIELDS')
        fields.add('builtin')
    if isinstance(fingerprint,dict) and fingerprint.get('id') in builtin_fingerprints and fingerprint.get('builtin') is not True:raise ValueError('FINGERPRINT_TEMPLATE_FIELDS')
    if isinstance(fingerprint,dict) and fingerprint.get('builtin') and fingerprint != BUILTIN_FINGERPRINTS.get(fingerprint.get('id')):raise ValueError('FINGERPRINT_TEMPLATE_FIELDS')
    generic = fingerprint.get('version') == 2 if isinstance(fingerprint, dict) else False
    if not isinstance(fingerprint,dict) or set(fingerprint) != fields | ({'version'} if generic else {'engine','browser_version'}):raise ValueError('FINGERPRINT_TEMPLATE_FIELDS')
    if generic and (request.get('version') != 3 or type(fingerprint['version']) is not int):raise ValueError('GENERATION_TARGET_REQUIRED')
    if request.get('version') == 3:
        validate_target_shape(request.get('generation'))
    if not generic and (fingerprint['engine'] != 'camoufox' or fingerprint['browser_version'] != '152.0' or request.get('generation',{}).get('engine','camoufox') != fingerprint['engine']):raise ValueError('TEMPLATE_UNSUPPORTED')
    if not isinstance(display,dict) or set(display)!=({'id','label','revision','mode','width','height','dpr','window_width','window_height','created_at'}|(({'builtin','dpr_mode'} if display.get('mode')=='auto' else {'builtin'}) if display.get('builtin') else set())):raise ValueError('DISPLAY_TEMPLATE_FIELDS')
    if sha(fp)!=refs['fingerprint_sha256'] or sha(dp)!=refs['display_sha256']:raise ValueError('TEMPLATE_REVISION_CHANGED')
    if fingerprint['id']!=refs['fingerprint_id'] or display['id']!=refs['display_id'] or fingerprint['revision']!=1 or display['revision']!=1:raise ValueError('TEMPLATE_REVISION_INVALID')
    auto=display['mode']=='auto'
    if auto:
        if display['id']!='display-0000000000000001' or display.get('builtin') is not True or display.get('dpr_mode')!='system' or display['dpr']!=0 or (display['width'],display['height'],display['window_width'],display['window_height'])!=(1280,720,1280,720):raise ValueError('TEMPLATE_UNSUPPORTED')
    elif display['mode']!='fixed' or display['dpr']!=1:raise ValueError('TEMPLATE_UNSUPPORTED')
    elif display.get('builtin'):
        if display['builtin'] is not True or display['id']!='display-0000000000000002' or (display['width'],display['height'],display['window_width'],display['window_height'])!=(1920,1080,1920,1080):raise ValueError('TEMPLATE_UNSUPPORTED')
    elif display['id'] in {'display-0000000000000001','display-0000000000000002'}:raise ValueError('TEMPLATE_UNSUPPORTED')
    spec=request['spec']
    if any(spec[k]!=fingerprint[k] for k in ('locale','languages','timezone')):raise ValueError('TEMPLATE_SPEC_MISMATCH')
    expected_screen=({'width':1280,'height':720,'mode':'auto','dprMode':'system'} if auto else {'width':display['width'],'height':display['height'],'deviceScaleFactor':display['dpr']})
    if spec['screen']!=expected_screen or spec['window']!={'width':display['window_width'],'height':display['window_height']}:raise ValueError('TEMPLATE_SPEC_MISMATCH')
    return fingerprint,display

def non_display(artifact):
    return {k:v for k,v in artifact['resolvedConfig'].items() if k not in DISPLAY_KEYS}

def compose(base,spec,image):
    if base['runtimeImageDigest']!=image:raise ValueError('TEMPLATE_IMAGE_CHANGED')
    if any(base['spec'][k]!=spec[k] for k in ('locale','languages','timezone')):raise ValueError('TEMPLATE_FINGERPRINT_CHANGED')
    result=copy.deepcopy(base);result['spec']=copy.deepcopy(spec)
    result['id']=spec['id']+'-artifact-1';result['createdAt']=datetime.now(timezone.utc).isoformat()
    c=result['resolvedConfig'];screen=spec['screen'];window=spec['window']
    if screen.get('mode')=='auto':
        result['schemaVersion']='browser-platform/camoufox-environment/v2'
        for key in DISPLAY_KEYS:c.pop(key,None)
        result['firefoxUserPrefs']['layout.css.devPixelsPerPx']='-1.0'
        assert non_display(result)==non_display(base)
        return result
    result['schemaVersion']='browser-platform/camoufox-environment/v1'
    result['firefoxUserPrefs'].pop('layout.css.devPixelsPerPx',None)
    c.update({'screen.width':screen['width'],'screen.height':screen['height'],
              'screen.availWidth':screen['width'],'screen.availHeight':screen['height'],
              'window.outerWidth':window['width'],'window.outerHeight':window['height'],
              'window.devicePixelRatio':screen['deviceScaleFactor'],'window.screenX':0,'window.screenY':0})
    assert non_display(result)==non_display(base)
    # browserforgeFingerprint is original generation provenance, not a second
    # source of live display settings; the launcher reads resolvedConfig.
    return result

def generate_combination(root,request,image,artifact_dir,evidence_dir,generator):
    fingerprint,display=source_records(root,request)
    cache_root=root/'fingerprint-cache';cache_root.mkdir(mode=0o700,exist_ok=True)
    if cache_root.is_symlink() or cache_root.stat().st_mode & 0o077:raise ValueError('TEMPLATE_CACHE_UNSAFE')
    cache=cache_root/fingerprint['id'];cache.mkdir(mode=0o700,exist_ok=True)
    if cache.is_symlink() or cache.stat().st_mode & 0o077:raise ValueError('TEMPLATE_CACHE_UNSAFE')
    if fingerprint.get('version') == 2:
        # Target identity excludes the image intentionally: an image drift must
        # reject the existing receipt, never silently replace the frozen device.
        target_hash = hashlib.sha256(json.dumps(request['generation'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        cache = cache / target_hash
        cache.mkdir(mode=0o700,exist_ok=True)
        if cache.is_symlink() or cache.stat().st_mode & 0o077:raise ValueError('TEMPLATE_CACHE_UNSAFE')
    frozen=cache/'environment.json';receipt=cache/'receipt.json'
    if frozen.exists():
        info=raw_json(receipt)
        if info!={'source_sha256':request['templates']['fingerprint_sha256'],'artifact_sha256':sha(frozen),'image':image}:raise ValueError('TEMPLATE_CACHE_CHANGED')
        base=raw_json(frozen);attempts=0
    else:
        if receipt.exists():raise ValueError('TEMPLATE_CACHE_INCOMPLETE')
        from environment import fixed_spec
        seed_spec=fixed_spec(request['spec'])
        seed_spec['screen']={'width':1920,'height':1080,'deviceScaleFactor':1}
        seed_spec['window']={'width':1920,'height':1080}
        attempts=generator(seed_spec,image,cache,evidence_dir)
        base=raw_json(frozen)
        write(receipt,{'source_sha256':request['templates']['fingerprint_sha256'],'artifact_sha256':sha(frozen),'image':image})
    target=artifact_dir/'environment.json'
    result=compose(base,request['spec'],image)
    if target.exists():
        old=raw_json(target)
        if old['spec']!=result['spec'] or old['resolvedConfig']!=result['resolvedConfig'] or old['runtimeImageDigest']!=image:raise ValueError('COMBINATION_RESULT_CHANGED')
    else:write(target,result)
    write(evidence_dir/'composition.json',{'fingerprint_id':fingerprint['id'],'display_id':display['id'],
        'generation':request.get('generation'),'source_artifact_sha256':sha(frozen),'artifact_sha256':sha(target),'non_display_equal':True,'generated_source':attempts>0})
    return attempts,fingerprint,display

def publish_compatibility(path,entry,display,write_private,encode,generation=None):
    import fcntl
    with path.with_name(path.name+'.lock').open('a+b') as lock:
        os.chmod(lock.name,0o600);fcntl.flock(lock,fcntl.LOCK_EX)
        catalog=raw_json(path)
        for key in ('display_templates','compatibility'):
            if catalog.get(key) is None:catalog[key]=[]
            if not isinstance(catalog[key],list):raise ValueError('TEMPLATE_CATALOG_INVALID')
        if generation is not None:
            validate_generation_target(path,generation,entry['browser_template_id'],catalog)
        browser=next((b for b in catalog['browser_templates'] if b['id']==entry['browser_template_id']),None)
        if not browser or browser['engine']!=entry['browser_engine'] or browser['version']!=entry['browser_version']:raise ValueError('BROWSER_TEMPLATE_MISMATCH')
        candidate={'id':display['id'],'revision':display['revision'],'status':'accepted','label':display['label'],
            'display_server':'x11','transport':'selkies','screen':entry['screen'],'scaling':'auto' if display.get('mode')=='auto' else 'fixed'}
        existing=next((d for d in catalog['display_templates'] if d['id']==candidate['id']),None)
        if existing is not None and existing!=candidate:raise ValueError('DISPLAY_TEMPLATE_CONFLICT')
        if existing is None:catalog['display_templates'].append(candidate)
        pair={'browser_template_id':entry['browser_template_id'],'environment_artifact_id':entry['id'],'display_template_id':candidate['id'],'status':'accepted'}
        old=next((p for p in catalog['compatibility'] if all(p[k]==pair[k] for k in ('browser_template_id','environment_artifact_id','display_template_id'))),None)
        if old is not None and {k:v for k,v in old.items() if k!='builtin'}!=pair:raise ValueError('COMBINATION_CONFLICT')
        if old is None:catalog['compatibility'].append(pair)
        write_private(path,encode(catalog))
