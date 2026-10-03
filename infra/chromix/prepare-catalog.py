#!/usr/bin/env python3
"""Prepare an immutable Chromix catalog candidate from matched runtime evidence.

Never writes live catalogs. Operator merges the resulting candidates only after
management/recovery verification and release review. No arbitrary Docker flags.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

HERE=Path(__file__).resolve().parent


def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');p.chmod(0o600)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--worker-result',type=Path,required=True)
    parser.add_argument('--direct-result',type=Path,required=True)
    parser.add_argument('--proxy-result',type=Path,required=True)
    parser.add_argument('--entry-result',type=Path,required=True)
    parser.add_argument('--management-result',type=Path)
    parser.add_argument('--recovery-result',type=Path)
    parser.add_argument('--session-origin',required=True)
    parser.add_argument('--owner',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    import re
    assert re.fullmatch(r'[A-Za-z0-9_-]{1,128}',args.owner)
    origin=urlsplit(args.session_origin);assert origin.scheme=='https' and origin.hostname and not origin.username and not origin.password and origin.path in ('','/') and not origin.query and not origin.fragment
    build=read(args.build);image=build['imageId']
    reports={k:read(getattr(args,k+'_result')) for k in ('worker','direct','proxy','entry')}
    assert all(r['result']=='PASS' for r in reports.values())
    assert not reports['worker'].get('diagnostic_launcher_bypass') and not reports['worker'].get('auto_resolution')
    assert all(reports[k]['image']==image for k in ('worker','direct','proxy'))
    assert reports['direct']['managed_direct'] and reports['direct']['public_https'] and reports['proxy']['authenticated_proxy_https']
    for k in ('direct','proxy'):
        assert reports[k]['no_bypass'] and reports[k]['gateway_failure_no_bypass'] and reports[k]['normal_stop_new_generation_stores']==3 and reports[k]['seed_preserved'] and reports[k]['final_runtime_resources']==0
    assert reports['entry']['session_host_display_handoff'] and reports['entry']['normal_stop'] and reports['entry']['fresh_health']=='healthy'
    observed=reports['worker']['observation'];assert observed['locale']=='en-US' and observed['timeZone']=='UTC' and observed['screen']==[1280,720,1]
    root=args.output.resolve();root.mkdir(mode=0o700)
    artifact_id='chromix-154-en-us-utc-1280-r1';browser_id='chromix-linux-154';display_id='chromix-x11-1280-r1'
    artifact={'schemaVersion':'browser-platform/chromix-environment/v1','id':artifact_id,'revision':1,'browserVersion':'154.0.8037.57','locale':'en-US','timezone':'UTC','screen':{'width':1280,'height':720,'dpr':1}}
    write(root/'environment.json',artifact)
    # This receipt covers engine/platform integration only; management/recovery
    # and production deployment have separate release gates.
    acceptance={'schemaVersion':'browser-platform/chromix-acceptance/v1','status':'pass','phase':'all','artifactSHA256':sha(root/'environment.json'),'runtimeImageDigest':image,'scope':'fixed en-US UTC X11 1280x720, seed persistence, authenticated display, DIRECT/authenticated SOCKS5, three stores and normal stop; no full GPU persona or cross-OS emulation claim','evidence':{k:sha(getattr(args,k+'_result')) for k in reports},'managementRecoveryReleaseGate':'pending'}
    if args.management_result or args.recovery_result:
        assert args.management_result and args.recovery_result
        management,recovery=read(args.management_result),read(args.recovery_result)
        assert management['result']=='PASS' and management['artifact_sha256']==acceptance['artifactSHA256']
        assert management['independent_home'] and management['no_debug_endpoint'] and management['normal_stop']
        assert recovery['result']=='PASS' and recovery['close_refusal_keeps_worker_home_resources'] and recovery['new_worker_three_stores_equal'] and recovery['seed_equal'] and recovery['final_stop']
        acceptance['managementRecoveryReleaseGate']='passed'
        acceptance['evidence'].update(management=sha(args.management_result),recovery=sha(args.recovery_result))
    write(root/'acceptance.json',acceptance)
    env={'BROWSER_PLATFORM_ENVIRONMENT_ID':artifact_id,'BROWSER_PLATFORM_ARTIFACT_SHA256':sha(root/'environment.json'),'BROWSER_PLATFORM_ACCEPTANCE_SHA256':sha(root/'acceptance.json'),'BROWSER_PLATFORM_RUNTIME_IMAGE_DIGEST':image,'PIXELFLUX_WAYLAND':'false','TZ':'UTC','LANG':'en_US.UTF-8','SELKIES_MANUAL_WIDTH':'1280','SELKIES_MANUAL_HEIGHT':'720','SELKIES_ALLOWED_ORIGINS':args.session_origin.rstrip('/'),'TITLE':'Chromix','SELKIES_UI_TITLE':'Chromix'}
    script='#!/bin/sh\nexec python3 /usr/local/lib/browser-platform/chromix-launcher.py launch "${SEALSKIN_URL:-about:blank}"\n'
    app={'id':'chromix-template','name':'Chromix','logo':'','url':'https://github.com/xiaozhou26/Chromix','source':'Browser Platform','source_app_id':'chromix','provider':'docker','home_directories':True,'users':[args.owner],'groups':[],'auto_update':False,'app_template':'Default','is_meta_app':False,'provider_config':{'image':image,'port':3000,'type':'browser','url_support':True,'open_support':False,'nvidia_support':False,'dri3_support':False,'extensions':[],'autostart':True,'custom_autostart_script_b64':base64.b64encode(script.encode()).decode(),'env':[{'name':k,'value':v} for k,v in env.items()],'docker_overrides':{'mem_limit':'1200m','nano_cpus':1500000000,'pids_limit':512,'shm_size':'256m','security_opt':['no-new-privileges:true','seccomp='+json.dumps(read(HERE/'seccomp.json'),separators=(',',':'))],'mounts':[{'Type':'bind','Source':str(root/name),'Target':'/run/browser-platform/'+name,'ReadOnly':True} for name in ('environment.json','acceptance.json')]}}}
    entry={'id':artifact_id,'sha256':sha(root/'environment.json'),'acceptance_sha256':sha(root/'acceptance.json'),'image':image,'source':'frozen','status':'accepted','application':app,'required_runtime_capabilities':{'browser_shutdown_version':1,'session_auth_version':1},'template_revision':1,'browser_template_id':browser_id,'browser_engine':'chromix','browser_version':artifact['browserVersion'],'os_family':'linux','platform':observed['platform'],'user_agent':observed['ua'],'locale':'en-US','languages':['en-US'],'timezone':'UTC','screen':'1280x720@1'}
    write(root/'environment-catalog.json',{'version':1,'artifacts':[entry]})
    write(root/'template-catalog.json',{'version':1,'browser_templates':[{'id':browser_id,'revision':1,'status':'accepted','label':'Chromix 154','engine':'chromix','version':artifact['browserVersion'],'os_family':'linux','platform':observed['platform'],'user_agent_product':'Chrome','allow_new_browsers':True}],'display_templates':[{'id':display_id,'revision':1,'status':'accepted','label':'Chromix · 1280×720','display_server':'x11','transport':'selkies','screen':'1280x720@1','scaling':'fixed'}],'compatibility':[{'browser_template_id':browser_id,'environment_artifact_id':artifact_id,'display_template_id':display_id,'status':'accepted'}]})
    print('CHROMIX_CATALOG_CANDIDATE_READY')


if __name__=='__main__':main()
