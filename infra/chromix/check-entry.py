#!/usr/bin/env python3
"""Authenticated entry/Session smoke for the stopped Chromix integration QA."""
import argparse
import hashlib
import http.client
import http.cookies
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import ssl
import subprocess
import uuid
from urllib.parse import urlsplit

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

m=module('chromix_integration',HERE/'check-integration.py')
migration=module('chromix_entry_client',ROOT/'infra/sealskin/checks/check-work-migration.py')
ENTRY=migration.ENTRY
SESSION=migration.SESSION


def handoff(qa,location):
    context=ssl.create_default_context(cafile=str(qa/'access/cert.pem'));cookies=http.cookies.SimpleCookie()
    for _ in range(5):
        parsed=urlsplit(location);assert parsed.scheme=='https' and parsed.netloc==urlsplit(SESSION).netloc
        c=http.client.HTTPSConnection(parsed.hostname,parsed.port,context=context,timeout=30)
        c.sock=context.wrap_socket(socket.create_connection(('127.0.0.1',parsed.port),timeout=30),server_hostname=parsed.hostname)
        try:
            headers={'Cookie':'; '.join(k+'='+v.value for k,v in cookies.items())} if cookies else {}
            c.request('GET',parsed.path+('?' + parsed.query if parsed.query else ''),headers=headers)
            r=c.getresponse();raw=r.read()
            for k,v in r.getheaders():
                if k.lower()=='set-cookie':cookies.load(v)
            if r.status==200:
                assert b'<html' in raw.lower() and cookies;return
            assert r.status in (302,303)
            location=r.getheader('Location')
            if location.startswith('/'):location=SESSION+location
        finally:c.close()
    raise RuntimeError('CHROMIX_HANDOFF_LOOP')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True);parser.add_argument('--verify-only',action='store_true');args=parser.parse_args();os.umask(0o077)
    qa=args.root.resolve();assert qa.name=='qa' and any(scope in qa.parts for scope in ('r6l-chromix-20261001','r6n-auto-20261001'))
    if args.verify_only:
        return verify(qa)
    source=qa.parent/'chromix-results-proxy';assert m.read(source/'result.json')['result']=='PASS'
    client=m.network.SecureClient(qa);status,snapshot=client.call('GET','/api/profile-runtime/'+m.HOME);assert status==200 and not any(snapshot[k] for k in ('workers','records','resources'))
    access=qa/'access';access.mkdir(mode=0o700)
    auth=module('chromix_private_tls',ROOT/'infra/sealskin/checks/prepare-entry-auth.py');auth.private_tls(qa,access,m.network)
    cfg=m.read(qa/'adapter-config.json');req=m.read(source/'second-request.json')
    definition={'id':m.PROFILE,'application_id':m.APP,'home_name':m.HOME,'start_url':req['url'],'network_policy_id':req['network_policy_id'],'network_policy_sha256':req['network_policy_sha256'],'language':'en_US.UTF-8','timezone':'UTC','wayland_mode':False}
    cfg.update(public_base_url=ENTRY,profiles=[definition],health={'sample_interval_seconds':0,'entry_hint':False})
    cfg['sealskin'].update(api_base_url='https://127.0.0.1:28443',public_session_base_url=SESSION,allow_unencrypted_http=False)
    cfg['access']={'users_file':str(access/'users.json'),'session_upstream_url':cfg['sealskin']['api_base_url'],'session_ca_file':str(access/'session-ca.pem'),'session_tls_name':'network.invalid','session_seconds':3600,'ticket_seconds':30}
    a=m.read(qa/'admin.json');(access/'admin-private.pem').write_text(a['private_key']);cfg['sealskin_admin']={'username':a['username'],'client_private_key_file':str(access/'admin-private.pem')}
    m.write(qa/'adapter-config.json',cfg)
    account={'username':'chromix-qa-admin','password':uuid.uuid4().hex+uuid.uuid4().hex};m.write(access/'account.json',account)
    result=subprocess.run([str(qa/'bin/profile-accounts'),'put','--config',str(qa/'adapter-config.json'),'--user',account['username'],'--profiles',m.PROFILE,'--role','admin'],input=account['password'],capture_output=True,text=True);assert result.returncode==0
    log=module('chromix_cert',ROOT/'infra/sealskin/checks/check-entry-log-boundary.py');cert,key=log.identity(access)
    template=(ROOT/'infra/sealskin/entry-auth/Caddyfile.example').read_text().replace('admin off','admin off\n    auto_https off',1).replace('mybrowser.example.com, mysession.example.com {',ENTRY+', '+SESSION+' {\n    bind 127.0.0.1\n    tls '+str(cert)+' '+str(key)).replace('127.0.0.1:8080',cfg['listen_address']);(access/'Caddyfile').write_text(template)
    for name,cmd,env in [('adapter',[str(qa/'bin/profile-adapter'),'-config',str(qa/'adapter-config.json')],None),('front-caddy',['caddy','run','--config',str(access/'Caddyfile'),'--adapter','caddyfile'],dict(os.environ,XDG_CONFIG_HOME=str(access/'caddy-config'),XDG_DATA_HOME=str(access/'caddy-data')))]:
        with (qa/(name+'.log')).open('ab') as output:p=subprocess.Popen(cmd,stdout=output,stderr=subprocess.STDOUT,start_new_session=True,env=env)
        m.write(qa/(name+'-pid.json'),{'pid':p.pid})
    verify(qa)


def verify(qa):
    access=qa/'access'
    m.workercheck.wait(lambda:m.network.request('GET','/readyz',headers={'Host':urlsplit(ENTRY).netloc},port=29110)[0]==200)
    browser=migration.Browser(qa)
    status,_,_=browser.request('GET','/browser/'+m.PROFILE+'/');assert status in (302,303)
    browser.login();status,_,raw=browser.request('GET','/browser/'+m.PROFILE+'/');assert status==200
    fields={k.decode():v.decode() for k,v in re.findall(rb'name="(csrf|launch_plan)" value="([^"]+)"',raw)};assert set(fields)=={'csrf','launch_plan'}
    status,location,_=browser.request('POST','/browser/'+m.PROFILE+'/start',fields);assert status in (302,303)
    handoff(qa,location)
    inspect=subprocess.run([str(qa/'bin/profile-adapter'),'-config',str(qa/'adapter-config.json'),'-probe-profile',m.PROFILE],capture_output=True,text=True);(access/'health.json').write_text(inspect.stdout);assert inspect.returncode==0
    health=json.loads(inspect.stdout);assert health['overall']=='healthy' and not health['stale']
    stop=subprocess.run([str(qa/'bin/profile-adapter'),'-config',str(qa/'adapter-config.json'),'-stop-profile',m.PROFILE],capture_output=True,text=True);(access/'stop.log').write_text(stop.stdout+stop.stderr);assert stop.returncode==0
    m.write(access/'result.json',{'result':'PASS','unauthenticated_entry_rejected':True,'admin_login_and_reauth':True,'launch_plan':True,'session_host_display_handoff':True,'fresh_health':'healthy','normal_stop':True,'adapter_sha256':hashlib.sha256((qa/'bin/profile-adapter').read_bytes()).hexdigest(),'scope':'isolated authenticated entry; QA services retained for template and recovery validation'})
    print('PASS entry login, launch plan, authenticated Session display, fresh health and stop')


if __name__=='__main__':main()
