"""Strict artifacts for custom Chromix and native Firefox environments."""
import hashlib
import json
import re
from zoneinfo import ZoneInfo

VERSIONS={'chromix':'154.0.8037.57','firefox':'155.0.1'}
LEGACY_SCHEMAS={'chromix':'browser-platform/chromix-environment/v3','firefox':'browser-platform/firefox-environment/v2'}
SCHEMAS={'chromix':'browser-platform/chromix-environment/v4','firefox':'browser-platform/firefox-environment/v3'}

def require(value,code):
    if not value:raise ValueError(code)

def decode(raw):
    def pairs(items):
        value={}
        for k,v in items:
            require(k not in value,'NATIVE_DUPLICATE_FIELD');value[k]=v
        return value
    return json.loads(raw,object_pairs_hook=pairs)

def validate(spec,engine):
    fields={'schemaVersion','id','revision','browserVersion','locale','languages','timezone','screen','window','runtimeImageDigest'}
    if engine=='chromix':fields.add('seed')
    require(isinstance(spec,dict) and set(spec)==fields,'NATIVE_SPEC_FIELDS')
    require(spec['schemaVersion'] in (SCHEMAS[engine],LEGACY_SCHEMAS[engine]) and spec['browserVersion']==VERSIONS[engine],'NATIVE_VERSION_MISMATCH')
    require(isinstance(spec['id'],str) and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,95}',spec['id']) and type(spec['revision']) is int and spec['revision']>=1,'NATIVE_SPEC_ID')
    languages=spec['languages']
    require(isinstance(languages,list) and 1<=len(languages)<=10 and all(isinstance(v,str) and re.fullmatch(r'[a-zA-Z]{2,8}(?:-[a-zA-Z0-9]{1,8})*',v) for v in languages),'NATIVE_LANGUAGES_INVALID')
    require(len(set(languages))==len(languages) and spec['locale']==languages[0],'NATIVE_LOCALE_INVALID')
    require(isinstance(spec['timezone'],str) and spec['timezone']!='Local' and len(spec['timezone'])<=64,'NATIVE_TIMEZONE_INVALID');ZoneInfo(spec['timezone'])
    screen=spec['screen'];window=spec['window']
    auto=screen.get('mode')=='auto'
    if auto:
        require(spec['schemaVersion']==SCHEMAS[engine] and set(screen)=={'mode','width','height','dpr'} and screen['dpr']=='system','NATIVE_SCREEN_INVALID')
    else:
        require(isinstance(screen,dict) and set(screen)=={'width','height','dpr'} and type(screen['dpr']) is int and screen['dpr']==1,'NATIVE_SCREEN_INVALID')
    require(isinstance(window,dict) and set(window)=={'width','height'},'NATIVE_WINDOW_INVALID')
    for k,low,high in [('width',640,3840),('height',480,2160)]:
        require(type(screen[k]) is int and type(window[k]) is int and low<=window[k]<=screen[k]<=high,'NATIVE_SCREEN_INVALID')
    require(isinstance(spec['runtimeImageDigest'],str) and re.fullmatch('sha256:[a-f0-9]{64}',spec['runtimeImageDigest']),'NATIVE_IMAGE_INVALID')
    if engine=='chromix':require(type(spec['seed']) is int and 0<spec['seed']<2**64,'NATIVE_SEED_INVALID')

def verify(spec,engine,raw,env):
    validate(spec,engine)
    expected={'BROWSER_PLATFORM_ARTIFACT_SHA256':hashlib.sha256(raw).hexdigest(),'BROWSER_PLATFORM_ENVIRONMENT_ID':spec['id'],
              'BROWSER_PLATFORM_RUNTIME_IMAGE_DIGEST':spec['runtimeImageDigest'],'TZ':spec['timezone'],
              'BROWSER_PLATFORM_LOCALE':spec['locale'],'BROWSER_PLATFORM_LANGUAGES':','.join(spec['languages']),
              'PIXELFLUX_WAYLAND':'false','SELKIES_MANUAL_WIDTH':str(spec['screen']['width']),'SELKIES_MANUAL_HEIGHT':str(spec['screen']['height'])}
    if spec['screen'].get('mode')=='auto':
        expected.pop('SELKIES_MANUAL_WIDTH');expected.pop('SELKIES_MANUAL_HEIGHT');expected['MAX_RES']='3840x2160';expected['BROWSER_PLATFORM_DISPLAY_MODE']='auto'
        require(not any(env.get(k) for k in ('SELKIES_MANUAL_WIDTH','SELKIES_MANUAL_HEIGHT')),'NATIVE_CONFIG_DRIFT')
    if spec['screen'].get('mode')!='auto':require(env.get('BROWSER_PLATFORM_DISPLAY_MODE','fixed')=='fixed','NATIVE_CONFIG_DRIFT')
    require(all(env.get(k)==v for k,v in expected.items()),'NATIVE_CONFIG_DRIFT')
