#!/usr/bin/env python3
"""Current-release, local isolated DR on a prepared Work QA fixture.

Explicit phases retain failure evidence. This runner never accepts production
owners, Homes, containers or config roots. Images remain explicit local inputs;
this is not an independent-host image import test.
"""
import argparse
import copy
import hashlib
import http.client
import http.cookies
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import uuid
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

migration = module('dr_migration', HERE / 'check-work-migration.py')
network, work = migration.network, migration.work
layout = module('dr_layout', HERE / 'recovery-layout.py')
PROFILE, HOME = migration.PROFILE, migration.HOME
READ = """(async()=>{let db=await new Promise((ok,fail)=>{let q=indexedDB.open('r7f-work',1);q.onsuccess=()=>ok(q.result);q.onerror=()=>fail(q.error)});let idb=await new Promise((ok,fail)=>{let q=db.transaction('values').objectStore('values').get('marker');q.onsuccess=()=>ok(q.result);q.onerror=()=>fail(q.error)});db.close();let cookie=(document.cookie.split('; ').find(v=>v.startsWith('r7f_marker='))||'').slice(11);return JSON.stringify({local:localStorage.getItem('r7f-marker'),cookie,idb})})()"""


def read(p): return json.loads(Path(p).read_bytes())
def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()
def write(p, value):
    p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    p.write_text(json.dumps(value, indent=2) + '\n'); p.chmod(0o600)


class Drill:
    def __init__(self, root, age=None, artifact=None, secret_store_module=None):
        self.root = root.resolve()
        assert self.root.name.startswith('r6k-') and 'runtime' in self.root.parts
        assert self.root.is_dir() and self.root.stat().st_uid == os.getuid() and self.root.stat().st_mode & 0o077 == 0
        self.source = self.root / 'source'
        self.q = self.source / 'qa'
        self.inputs = self.root / 'inputs'
        self.backup = self.root / 'backup'
        resources=read(self.root/'resources.json')
        self.target = Path(resources['recovery_target'])
        self.bundle = Path(resources['restore_bundle'])
        assert self.target.is_relative_to('/dev/shm/r6k-local-dr') and self.bundle.is_relative_to('/dev/shm/r6k-local-dr')
        tools=read(self.inputs/'recovery-tools.json') if (self.inputs/'recovery-tools.json').exists() else {}
        self.age = Path(age or tools.get('age') or shutil.which('age') or '')
        assert self.age.is_file(), 'explicit age executable input required'
        if tools: assert sha(self.age)==tools['age_sha256']
        self.artifact=Path(artifact) if artifact else self.inputs/'artifact.json'
        self.store_module=Path(secret_store_module) if secret_store_module else self.inputs/'secret_store.py'
        assert self.store_module.is_file(), 'explicit exact-controller Secret Store module required'
        if tools: assert sha(self.store_module)==tools['secret_store_sha256']
        self.script = ROOT / 'infra/sealskin/lifecycle/secure-backup.py'
        self.storage = module('dr_secret_store', self.store_module)

    def command(self, args, name, *, expected=0, data=None, timeout=240):
        start = time.monotonic()
        result = subprocess.run([str(x) for x in args], input=data, capture_output=True, timeout=timeout)
        (self.root / (name + '.stdout')).write_bytes(result.stdout)
        (self.root / (name + '.stderr')).write_bytes(result.stderr)
        write(self.root / (name + '.timing.json'), {'seconds': round(time.monotonic()-start, 3), 'exit_code': result.returncode})
        assert result.returncode == expected, name + ' failed; inspect private evidence'
        return result.stdout

    def inventory(self, qa):
        client, _ = migration.clients(qa)
        status, value = client.call('GET', '/api/profile-runtime/' + HOME)
        assert status == 200
        return value

    def launch(self, qa, name):
        migration.scope(qa)
        browser = migration.Browser(qa); browser.login()
        status, _, raw = browser.request('GET', '/browser/' + PROFILE + '/')
        assert status == 200
        fields = dict((k.decode(), v.decode()) for k,v in re.findall(rb'name="(csrf|launch_plan)" value="([^"]+)"', raw))
        assert set(fields) == {'csrf','launch_plan'}
        status, location, _ = browser.request('POST', '/browser/' + PROFILE + '/start', fields)
        assert status in (302,303)
        handoff_status = self.display_handoff(qa, location)
        inventory = self.inventory(qa)
        assert len(inventory['workers']) == len(inventory['records']) == 1 and len(inventory['resources']) == 5
        worker = inventory['workers'][0]['instance_id']
        work.wait(lambda: work.process_identity(network,worker)['native_wayland'], 'restored Wayland browser', seconds=90)
        work.wait(lambda: work.bidi_value(network,worker,'document.title',navigate='https://example.com/') == 'Example Domain', 'restored HTTPS', seconds=90)
        actual = json.loads(work.bidi_value(network,worker,READ))
        marker = read(self.inputs/'marker.json')['value']
        assert actual == {'local':marker,'cookie':marker,'idb':marker}
        assert not any(work.raw_bypass(network,worker).values())
        c = json.loads(network.docker('inspect',worker).stdout)[0]
        assert c['Image'] == read(self.inputs/'images.json')['worker']
        assert any(m['Source']==str(qa/'storage/network-qa'/HOME) and m['Destination']=='/config' for m in c['Mounts'])
        assert c['HostConfig']['LogConfig'] == {'Type':'json-file','Config':{'max-size':'10m','max-file':'3','compress':'true'}}
        write(self.root/(name+'-runtime.json'), {'inventory':inventory,'worker':c['Id'],'image':c['Image'],'storage':actual,'authenticated_handoff_status':handoff_status})
        return browser, inventory, worker

    def display_handoff(self, qa, location):
        context=ssl.create_default_context(cafile=str(qa/'access/cert.pem'))
        cookies=http.cookies.SimpleCookie()
        for _ in range(5):
            parsed=urlsplit(location)
            assert parsed.scheme=='https' and parsed.netloc==urlsplit(migration.SESSION).netloc
            path=parsed.path+('?' + parsed.query if parsed.query else '')
            connection=http.client.HTTPSConnection(parsed.hostname,parsed.port,context=context,timeout=30)
            connection.sock=context.wrap_socket(socket.create_connection(('127.0.0.1',parsed.port),timeout=30),server_hostname=parsed.hostname)
            try:
                headers={'Cookie':'; '.join(k+'='+v.value for k,v in cookies.items())} if cookies else {}
                connection.request('GET',path,headers=headers)
                response=connection.getresponse();body=response.read();status=response.status
                for key,value in response.getheaders():
                    if key.lower()=='set-cookie':cookies.load(value)
                if status==200:
                    assert b'<html' in body.lower() and cookies
                    return status
                assert status in (302,303),'session host handoff rejected'
                location=response.getheader('Location')
                if location.startswith('/'):location=migration.SESSION+location
            finally:connection.close()
        raise AssertionError('display redirect loop')

    def stop(self, qa, browser):
        assert browser.action('stop') == 'stopped'
        v = self.inventory(qa)
        assert all(not v[k] for k in ('records','workers','resources'))

    def freeze(self):
        assert not (self.backup/'home.age').exists()
        migration.scope(self.q)
        self.inputs.mkdir(mode=0o700,exist_ok=True); self.backup.mkdir(mode=0o700,exist_ok=True)
        if not (self.inputs/'bin').exists():shutil.copytree(self.q/'bin',self.inputs/'bin')
        if self.store_module.resolve()!=(self.inputs/'secret_store.py').resolve():shutil.copyfile(self.store_module,self.inputs/'secret_store.py')
        write(self.inputs/'recovery-tools.json',{'age':str(self.age.resolve()),'age_sha256':sha(self.age),'secret_store_sha256':sha(self.store_module)})
        for source, dest in [(self.source/'marker.json','marker.json'),(self.q/'access/account.json','account.json')]:
            shutil.copyfile(source,self.inputs/dest)
        controller = migration.scope(self.q)
        image = read(self.q/'source.json')['target_image']
        direct = read(self.q/'adapter-config.json')['direct_template']
        write(self.inputs/'images.json',{'controller':controller['Image'],'worker':image,'relay':direct['relay_image'],'probe':direct['probe_image']})
        for identifier in read(self.inputs/'images.json').values():
            assert network.docker('image','inspect',identifier,'--format','{{.Id}}').stdout.strip()==identifier
        key = self.source/'master-key/master.key'
        directory=self.q/'config/.config/sealskin/proxy-secret-store'
        store = self.storage.FileSecretStore(directory,key) if directory.exists() else self.storage.FileSecretStore.initialize(directory,key)
        write(self.q/'config/.config/sealskin/profile-secret-store.json',{'version':1,'key_file':'/run/browser-platform-key/master.key','runtime_dir':'/run/browser-platform-secrets'})
        grant = {'owner':'network-qa','profile':PROFILE,'home':HOME,'app':migration.APP}
        for version in (1,2):
            if not store.revision_path('dr-check',version).exists():store.put('dr-check',version,[grant],username='isolated-dr',password=uuid.uuid4().hex)
        if (self.inputs/'disabled-account.json').exists():
            account=read(self.inputs/'disabled-account.json')
        else:
            account = {'username':'dr-disabled','password':uuid.uuid4().hex+uuid.uuid4().hex}
            self.command([self.q/'bin/profile-accounts','put','--config',self.q/'adapter-config.json','--user',account['username'],'--profiles',PROFILE], 'source-extra-account', data=account['password'].encode())
            write(self.inputs/'disabled-account.json',account)
        browser, inventory, worker = self.launch(self.q,'source-checkpoint')
        state = json.loads(self.command([self.q/'bin/profile-adapter','-config',self.q/'adapter-config.json','-inspect-profile',PROFILE],'source-inspect'))
        assert state['status']=='running' and state['orphans']==0
        assert self.artifact.is_file(), 'fixed Worker image build evidence required'
        if self.artifact.resolve()!=(self.inputs/'artifact.json').resolve():shutil.copyfile(self.artifact,self.inputs/'artifact.json')
        write(self.inputs/'acceptance.json',{'status':'PASS','profiles':{PROFILE:state},'containers':{PROFILE:{'worker_image':image,'all_running':True}},'scope':'current DR source generation, exact image/Home, real browser three stores and HTTPS/no-bypass'})
        self.stop(self.q,browser)
        identity = self.inputs/'age-identity.txt'
        self.command([self.age.with_name('age-keygen'),'-o',identity],'age-keygen')
        recipient = subprocess.check_output([str(self.age.with_name('age-keygen')),'-y',str(identity)]).decode().strip()
        args=[sys.executable,self.script,'create','--config',self.q/'adapter-config.json','--profile',PROFILE,'--storage',self.q/'storage','--sealskin-config',self.q/'config/.config/sealskin','--artifact',self.inputs/'artifact.json','--acceptance',self.inputs/'acceptance.json','--fixed-runtime-evidence','--master-key-file',key,'--admin-recovery-file',self.q/'admin.json','--recipient',recipient,'--age',self.age,'--output',self.backup/'home.age']
        receipt=json.loads(self.command(args,'backup-create',timeout=600))
        write(self.backup/'receipt.json',receipt)
        # Current trust state changes after the backup. Recovery must merge it.
        store.revoke(self.storage.references('dr-check',2)['password'],uuid.uuid4().hex)
        self.command([self.q/'bin/profile-accounts','disable','--config',self.q/'adapter-config.json','--user',account['username']],'post-backup-disable')
        write(self.inputs/'tools.json',{str(p.relative_to(self.inputs)):sha(p) for p in (self.inputs/'bin').iterdir()})
        print('PASS source checkpoint, encrypted backup and post-backup account/revocation changes',flush=True)

    def restore(self):
        assert not (self.bundle).exists() and not self.target.exists()
        archive = self.backup/'home.age'; identity = self.inputs/'age-identity.txt'
        assert sha(archive)==read(self.backup/'receipt.json')['archive_sha256']
        with tempfile.TemporaryDirectory(prefix='r6k-restore-',dir='/dev/shm') as scratch:
            common=['--age',self.age,'--archive',archive,'--identity',identity,'--scratch-root',scratch]
            self.command([sys.executable,self.script,'verify',*common],'backup-verify',timeout=600)
            self.command([sys.executable,self.script,'restore',*common,'--target',self.bundle],'backup-restore',timeout=600)
            assert not list(Path(scratch).iterdir())
        bundle=self.bundle
        restored=self.storage.FileSecretStore(bundle/'control/proxy-secret-store',bundle/'key-material/secret-store.key')
        grant={'owner':'network-qa','profile':PROFILE,'home':HOME,'app':migration.APP};refs=self.storage.references('dr-check',1)
        try: restored.resolve(grant,refs['username'],refs['password']); raise AssertionError('restored secret unexpectedly unlocked')
        except self.storage.SecretError as err: assert err.code=='SECRET_RECOVERY_LOCKED'
        self.command([sys.executable,self.script,'activate','--bundle',bundle,'--current-store',self.q/'config/.config/sealskin/proxy-secret-store'],'activate-no-account',expected=1)
        # Retire all original fixtures, processes, bridge and mounts before activation.
        migration.cleanup(self.q)
        creds=Path('/dev/shm/r6k-source-credentials'); assert not list(creds.iterdir());creds.rmdir()
        self.command([sys.executable,self.script,'activate','--bundle',bundle,'--current-store',self.q/'config/.config/sealskin/proxy-secret-store','--current-access-users',self.q/'access/users.json'],'activate-reviewed')
        restored.resolve(grant,refs['username'],refs['password'])
        revoked=self.storage.references('dr-check',2)
        try: restored.resolve(grant,revoked['username'],revoked['password']);raise AssertionError('revocation lost')
        except self.storage.SecretError as err: assert err.code=='SECRET_REVOKED'
        assert read(bundle/'adapter/access-users.json')==read(self.q/'access/users.json')
        self.source.rename(self.root/'source-retired')
        self.target.mkdir(mode=0o700)
        result=layout.stage(bundle,self.target/'qa')
        assert not self.source.exists()
        write(self.root/'staged.json',result)
        self.start_services(self.target/'qa',bundle/'key-material/secret-store.key','recovered')
        print('PASS source retired and path removed; reviewed backup staged into a fresh controller root',flush=True)

    def process(self,qa,name,args,env=None):
        with (qa/(name+'.log')).open('ab') as log:
            p=subprocess.Popen([str(x) for x in args],stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env=env)
        write(qa/(name+'-pid.json'),{'pid':p.pid})
        return p

    def start_services(self,qa,key_source,label):
        qa=qa.resolve();assert qa.name=='qa' and read(qa/'adapter-config.json')['sealskin']['username']=='network-qa'
        assert network.docker('inspect',network.SERVER,check=False).returncode!=0
        assert network.docker('network','inspect','browser-platform-network-qa',check=False).returncode!=0
        keys=qa.parent/'runtime-key';keys.mkdir(mode=0o700);shutil.copyfile(key_source,keys/'master.key');(keys/'master.key').chmod(0o600)
        display=Path('/dev/shm/r6k-'+label+'-display');creds=Path('/dev/shm/r6k-'+label+'-credentials')
        for p in (display,creds):p.mkdir(mode=0o700)
        images=read(self.inputs/'images.json')
        if not (qa/'bin').exists():shutil.copytree(self.inputs/'bin',qa/'bin')
        write(qa/'images.json',images)
        cfg=read(qa/'adapter-config.json')
        assets=[]
        for app in __import__('yaml').safe_load((qa/'config/.config/sealskin/installed_apps.yml').read_text()):
            assets += [m['Source'] for m in app.get('overrides',{}).get('provider_config',{}).get('docker_overrides',{}).get('mounts',[])]
        write(qa/'allow.json',{'images':list(set(images.values())),'guard_images':[images['relay']],'direct_images':[images['relay']], 'readonly_sources':assets,'display_runtime_root':str(display),'credential_runtime_root':str(creds)})
        write(qa/'policy.json',{})
        write(qa.parent/'live-resources.json',{'display':str(display),'credentials':str(creds),'keys':str(keys)})
        socket_path=Path('/tmp/browser-platform-network-qa-docker.sock');assert not socket_path.exists()
        self.process(qa,'proxy',['sg','docker','-c',shlex.join(['python3',str(ROOT/'infra/sealskin/lifecycle/qa-network-docker-proxy.py'),'--root',str(qa),'--socket',str(socket_path)])])
        network.wait(socket_path.exists,'DR Docker proxy',seconds=15)
        network.docker('network','create','--label','io.browser-platform.qa=network-20260913','browser-platform-network-qa')
        cmd=['run','-d','--name',network.SERVER,'--label','io.browser-platform.qa=network-20260913','--network','browser-platform-network-qa','--memory','512m','--cpus','1.5','--pids-limit','256','-e','PUID=1000','-e','PGID=1000','-e','TZ=Etc/UTC','-e','HOST_URL=network.invalid','--log-driver','json-file','--log-opt','max-size=10m','--log-opt','max-file=3','--log-opt','compress=true']
        for source,dest,ro in [(qa/'config','/config',False),(qa/'storage','/storage',False),(socket_path,'/var/run/docker.sock',False),(keys,'/run/browser-platform-key',True),(creds,'/run/browser-platform-secrets',False),(display,'/run/browser-platform-session-secrets',False),(Path('/proc/1/net/fib_trie'),'/run/browser-platform-host/ipv4-fib-trie',True)]:
            cmd += ['--mount','type=bind,src='+str(source)+',dst='+dest+(',readonly' if ro else '')]
        cmd += ['-p','127.0.0.1:28110:8000','-p','127.0.0.1:28443:8443',images['controller']]
        network.docker(*cmd)
        network.wait(lambda:network.request('POST','/api/handshake/initiate')[0]==200,'DR controller',seconds=60)
        client,admin=migration.clients(qa);assert admin.call('GET','/api/admin/apps/installed')[0]==200
        access=qa/'access';shutil.copyfile(self.inputs/'account.json',access/'account.json')
        logcheck=module('dr_front_identity',HERE/'check-entry-log-boundary.py');cert,key=logcheck.identity(access)
        template=(ROOT/'infra/sealskin/entry-auth/Caddyfile.example').read_text().replace('admin off','admin off\n    auto_https off',1)
        template=template.replace('mybrowser.example.com, mysession.example.com {',migration.ENTRY+', '+migration.SESSION+' {\n    bind 127.0.0.1\n    tls '+str(cert)+' '+str(key))
        template=template.replace('127.0.0.1:8080',cfg['listen_address']);(access/'Caddyfile').write_text(template)
        env=dict(os.environ,XDG_CONFIG_HOME=str(access/'caddy-config'),XDG_DATA_HOME=str(access/'caddy-data'))
        self.command(['caddy','adapt','--config',access/'Caddyfile','--adapter','caddyfile','--validate'],label+'-caddy-validation')
        self.process(qa,'adapter',[qa/'bin/profile-adapter','-config',qa/'adapter-config.json'])
        self.process(qa,'front-caddy',['caddy','run','--config',access/'Caddyfile','--adapter','caddyfile'],env)
        network.wait(lambda:network.request('GET','/readyz',headers={'Host':urlsplit(migration.ENTRY).netloc},port=29110)[0]==200,'DR Adapter',seconds=45)

    def verify(self):
        assert not self.source.exists(),'source paths must remain absent throughout recovery validation'
        qa=self.target/'qa'
        account=read(self.inputs/'disabled-account.json');b=migration.Browser(qa)
        status,_,_=b.request('POST','/auth/login',{**account,'csrf':b.csrf('/auth/login'),'next':'/manage/'})
        assert status in (401,403),'disabled account was resurrected'
        b,inventory,worker=self.launch(qa,'recovered')
        assert worker!=read(self.root/'source-checkpoint-runtime.json')['worker']
        report=json.loads(self.command([qa/'bin/profile-adapter','-config',qa/'adapter-config.json','-probe-profile',PROFILE],'recovered-health'))
        assert report['overall']=='healthy' and not report['stale']
        self.stop(qa,b)
        write(self.root/'recovery-result.json',{'result':'PASS','source_path_absent':True,'new_controller_home_and_generation':True,'current_admin_identity_and_login':True,'disabled_account_rejected':True,'revocation_preserved':True,'real_browser_cookie_localStorage_indexedDB_equal':True,'https_and_no_bypass':True,'health':'healthy','normal_stop_resources':0,'scope':'local isolated recovery using explicitly pinned local images; no independent-host import'})
        print('PASS fresh-root authentication, disabled user rejection, browser stores, HTTPS, isolation and normal stop',flush=True)

    def retire(self,qa):
        v=self.inventory(qa);assert all(not v[k] for k in ('records','workers','resources'))
        stage=module('dr_stop_process',HERE/'stage-entry-auth.py')
        for name,exe in [('front-caddy','caddy'),('adapter',qa/'bin/profile-adapter')]:stage.stop_process(qa,name,exe)
        c=migration.scope(qa);network.docker('stop','-t','10',c['Id']);network.docker('rm','-v',c['Id'])
        network.docker('network','rm','browser-platform-network-qa');stage.stop_process(qa,'proxy',ROOT/'infra/sealskin/lifecycle/qa-network-docker-proxy.py')
        for name in ('/tmp/browser-platform-network-qa-docker.sock','/tmp/browser-platform-network-qa.sock'):
            p=Path(name)
            if p.exists():
                with socket.socket(socket.AF_UNIX) as s:assert s.connect_ex(name)!=0
                p.unlink()
        resources=read(qa.parent/'live-resources.json')
        for key in ('display','credentials'):
            p=Path(resources[key]);assert p.parent==Path('/dev/shm') and not list(p.iterdir());p.rmdir()
        keys=Path(resources['keys']);assert keys==qa.parent/'runtime-key';(keys/'master.key').unlink();keys.rmdir()

    def rollback(self):
        assert read(self.root/'recovery-result.json')['result']=='PASS'
        self.retire(self.target/'qa')
        (self.root/'source-retired').rename(self.source)
        self.start_services(self.q,self.source/'master-key/master.key','rollback')
        browser,_,_=self.launch(self.q,'rollback')
        self.stop(self.q,browser)
        self.retire(self.q)
        write(self.root/'rollback-result.json',{'result':'PASS','normal_cleanup_before_switch':True,'same_checkpoint_stores_read':True,'source_latest_revocations_and_account_registry_preserved':True,'no_reverse_replication_claim':True})
        print('PASS controlled return to retained source checkpoint and final QA cleanup',flush=True)


def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('freeze','restore','verify','rollback'))
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--age',type=Path,help='age v1.2.1 executable; required on first freeze unless on PATH')
    parser.add_argument('--artifact',type=Path,help='exact fixed Worker image build evidence for initial freeze')
    parser.add_argument('--secret-store-module',type=Path,help='verified module exported from the pinned controller for initial freeze')
    args=parser.parse_args()
    drill=Drill(args.root,args.age,args.artifact,args.secret_store_module);getattr(drill,args.phase)()

if __name__=='__main__':main()
