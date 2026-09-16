#!/usr/bin/env python3
"""Prepare reviewable Camoufox migration files without changing a live service.

The existing Profile and journal remain authoritative. Outputs are private,
never include secret contents, and must be rechecked in the maintenance window.
"""
import argparse
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys

from acceptance import docker

NAME = r'[A-Za-z0-9_-]{1,128}'
POLICY_DEFAULTS = {'username_file':'','username_sha256':'','password_file':'','password_sha256':'',
                   'probe_ca_file':'','probe_ca_sha256':'','probe_timeout_seconds':10}
POLICY_REQUIRED = {'username','profile_id','home_name','application_id','relay_image','probe_image',
                   'upstream_host','upstream_port','probe_url'}
IMAGE_CAPABILITIES = {'io.browser-platform.browser-shutdown':'browser_shutdown_version',
                      'io.browser-platform.session-auth':'session_auth_version'}


def required_capabilities(labels):
    if not isinstance(labels,dict):
        raise ValueError('target image capability labels are unavailable')
    required = {}
    for label,name in IMAGE_CAPABILITIES.items():
        if label in labels:
            if labels[label] != '1':
                raise ValueError('unsupported target image capability version')
            required[name] = 1
    return required


def check_capabilities(current, required):
    actual = current.get('capabilities')
    expected = {'network_runtime_version':1,'network_enforcement_version':1,'launch_journal_version':1,**required}
    if not isinstance(actual,dict) or any(type(actual.get(k)) is not int or actual[k] != v for k,v in expected.items()):
        raise ValueError('running Adapter/controller does not confirm the target Worker capabilities; upgrade the matched control stack first')
    return {key:actual[key] for key in expected}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def revision(value):
    return sha(json.dumps(value,sort_keys=True,separators=(',',':')).encode())


def unique(pairs):
    value = {}
    for key,item in pairs:
        if key in value:
            raise ValueError('duplicate JSON field')
        value[key] = item
    return value


def read(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4*1024*1024:
        raise ValueError('input must be a bounded regular file')
    return json.loads(path.read_bytes(),object_pairs_hook=unique)


def write(path, value):
    with path.open('x') as stream:
        os.fchmod(stream.fileno(),0o600)
        json.dump(value,stream,ensure_ascii=False,indent=2)
        stream.write('\n')


def resolve_config(config, directory):
    config = copy.deepcopy(config)
    for target,keys in [(config,['state_file','control_socket']),
            (config['sealskin'],['server_public_key_file','client_private_key_file']),
            (config.get('access',{}),['users_file','session_ca_file']),
            (config.get('limits',{}),['storage_path'])]:
        for key in keys:
            if target.get(key):
                path = Path(target[key])
                target[key] = str(path if path.is_absolute() else (directory/path).resolve())
    config.setdefault('control_socket',config['state_file']+'.control.sock')
    return config


def candidates(config, state, registry, profile, home, app_id, policy_id):
    if not all(re.fullmatch(NAME,value) for value in [profile,home,policy_id]):
        raise ValueError('invalid Profile, Home or policy ID')
    if not re.fullmatch(r'camoufox-[a-z0-9-]+',app_id):
        raise ValueError('a separate camoufox-* application is required')
    if not config['sealskin'].get('lifecycle_enabled'):
        raise ValueError('verified lifecycle is required')
    selected = [item for item in config['profiles'] if item['id'] == profile]
    if len(selected) != 1 or state.get('version') != 1 or registry.get('version') != 1:
        raise ValueError('unknown Profile or metadata version')
    previous = selected[0]
    if any(p['home_name'] == home for p in config['profiles']) or any(b.get('home_name') == home for b in state['bindings'].values()):
        raise ValueError('new Home is already referenced')
    if any(p['application_id'] == app_id for p in config['profiles']) or policy_id in registry['policies']:
        raise ValueError('use new application and policy identities')
    binding = state['bindings'].get(profile)
    if not binding or binding['status'] not in ('running','stopped'):
        raise ValueError('resolve the current operation before preparing migration')
    if any(binding.get(key) and binding[key] != previous[key] for key in ['home_name','application_id']):
        raise ValueError('configured Profile differs from its active binding')
    source = registry['policies'].get(previous.get('network_policy_id'))
    if not source or not POLICY_REQUIRED <= set(source) or set(source) - POLICY_REQUIRED - set(POLICY_DEFAULTS):
        raise ValueError('a complete supported SOCKS5 policy is required')
    policy = {**POLICY_DEFAULTS,**source}
    if revision(policy) != previous.get('network_policy_sha256'):
        raise ValueError('configured policy revision differs from the registry')
    if (policy['username'],policy['profile_id'],policy['home_name'],policy['application_id']) != (
            config['sealskin']['username'],profile,previous['home_name'],previous['application_id']):
        raise ValueError('source policy ownership differs')
    if binding.get('network_policy_id') and (binding['network_policy_id'],binding['network_policy_sha256']) != (
            previous['network_policy_id'],previous['network_policy_sha256']):
        raise ValueError('active binding uses a different policy revision')
    policy.update(home_name=home,application_id=app_id)
    future_registry = copy.deepcopy(registry)
    future_registry['policies'][policy_id] = policy
    future = copy.deepcopy(config)
    target = next(p for p in future['profiles'] if p['id'] == profile)
    target.update(home_name=home,application_id=app_id,network_policy_id=policy_id,
        network_policy_sha256=revision(policy),language='zh_TW.UTF-8',timezone='Asia/Taipei',wayland_mode=False)
    return future, future_registry, binding


def inspect(control_socket, profile):
    class UnixConnection(http.client.HTTPConnection):
        def connect(self):
            self.sock = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            self.sock.settimeout(self.timeout)
            self.sock.connect(control_socket)
    connection = UnixConnection('adapter',timeout=30)
    try:
        connection.request('GET','/profiles/'+profile)
        response = connection.getresponse()
        value = json.loads(response.read(256*1024))
        if response.status != 200 or value.get('error'):
            raise ValueError('running Adapter could not verify current ownership')
        return value['result']
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['config','policy-registry','storage-root','artifact','acceptance','clipboard-addon','output']:
        parser.add_argument('--'+name,type=Path,required=True)
    for name in ['profile','new-home','new-app-id','new-policy-id']:
        parser.add_argument('--'+name,required=True)
    args = parser.parse_args()
    config_path, registry_path = args.config.resolve(),args.policy_registry.resolve()
    config = resolve_config(read(config_path),config_path.parent)
    state_path = Path(config['state_file'])
    # Share the Adapter's journal lock while taking the read-only snapshot.
    with Path(str(state_path)+'.lock').open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_SH)
        state = read(state_path)
        state_sha = sha(state_path.read_bytes())
    source_hashes = {'config':sha(config_path.read_bytes()),'registry':sha(registry_path.read_bytes()),'journal':state_sha}
    future,registry,binding = candidates(config,state,read(registry_path),args.profile,args.new_home,args.new_app_id,args.new_policy_id)
    current = inspect(config['control_socket'],args.profile)
    if (current['status'],current.get('session_id')) != (binding['status'],binding.get('session_id')):
        raise ValueError('binding changed while observing the running Adapter')
    artifact = read(args.artifact)
    image = artifact['runtimeImageDigest']
    if not isinstance(image,str) or not re.fullmatch(r'sha256:[a-f0-9]{64}',image):
        raise ValueError('target artifact must bind an exact image ID')
    observed_image = docker(['image','inspect',image],timeout=15)
    if observed_image.returncode:
        raise ValueError('target artifact-bound image is not installed')
    images = json.loads(observed_image.stdout)
    if len(images) != 1 or images[0].get('Id') != image:
        raise ValueError('target image identity differs from the artifact')
    required = required_capabilities(images[0]['Config'].get('Labels',{}))
    capabilities = check_capabilities(current,required)
    target = next(p for p in future['profiles'] if p['id'] == args.profile)
    if required:
        target['required_runtime_capabilities'] = required
    else:
        target.pop('required_runtime_capabilities',None)
    storage = args.storage_root.resolve(strict=True)/config['sealskin']['username']
    old = next(p for p in config['profiles'] if p['id'] == args.profile)
    if not (storage/old['home_name']).is_dir() or (storage/args.new_home).exists():
        raise ValueError('old Home must exist and new Home must be absent')
    listed = docker(['ps','-aq'],timeout=20)
    if listed.returncode:
        raise ValueError('cannot inspect Home mounts')
    identifiers = listed.stdout.split()
    runtime_workers = []
    if identifiers:
        observed = docker(['inspect',*identifiers],timeout=30)
        if observed.returncode:
            raise ValueError('container inventory changed; retry preparation')
        target = str(storage/args.new_home)
        containers = json.loads(observed.stdout)
        if any(m.get('Source') == target for c in containers for m in c.get('Mounts',[])):
            raise ValueError('new Home still has a container mount')
        for container in containers:
            if any(m.get('Source') == str(storage/old['home_name']) for m in container.get('Mounts',[])):
                environment = dict(item.split('=',1) for item in container['Config'].get('Env',[]) if '=' in item)
                runtime_workers.append({'id':container['Id'],'image':container['Image'],
                    'startedAt':container['State']['StartedAt'],'running':container['State']['Running'],
                    'autoRemove':container['HostConfig']['AutoRemove'],
                    'environmentReferences':{k:v for k,v in environment.items() if k in [
                        'BROWSER_PLATFORM_ENVIRONMENT_SHA256','BROWSER_PLATFORM_ACCEPTANCE_SHA256',
                        'BROWSER_PLATFORM_ENVIRONMENT_ID','LC_ALL','TZ']}})
    if len(runtime_workers) != current['workers']:
        raise ValueError('Docker mounts differ from the verified Adapter inventory')
    output = args.output.resolve()
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    new = next(p for p in future['profiles'] if p['id'] == args.profile)
    command = [sys.executable,str(Path(__file__).with_name('prepare-sealskin.py')),
        '--artifact',str(args.artifact.resolve()),'--acceptance',str(args.acceptance.resolve()),
        '--app-id',args.new_app_id,'--username',config['sealskin']['username'],
        '--session-origin',config['sealskin']['public_session_base_url'],
        '--network-policy-id',new['network_policy_id'],'--network-policy-sha256',new['network_policy_sha256'],
        '--clipboard-addon',str(args.clipboard_addon.resolve()),'--output',str(output/'application.json')]
    prepared = subprocess.run(command,capture_output=True,text=True,timeout=90)
    if prepared.returncode:
        raise ValueError('candidate image rejected the app or frozen evidence: '+prepared.stderr[:250])
    app = read(output/'application.json')
    if (artifact['spec']['locale'],artifact['spec']['timezone']) != ('zh-TW','Asia/Taipei'):
        raise ValueError('this migration helper requires the accepted Taiwan environment')
    if source_hashes != {'config':sha(config_path.read_bytes()),'registry':sha(registry_path.read_bytes()),'journal':sha(state_path.read_bytes())}:
        raise ValueError('source configuration or binding changed during preparation')
    latest = inspect(config['control_socket'],args.profile)
    if (latest['status'],latest.get('session_id')) != (current['status'],current.get('session_id')) or check_capabilities(latest,required) != capabilities:
        raise ValueError('running controller or binding changed during preparation')
    write(output/'adapter.candidate.json',future)
    write(output/'adapter.rollback.json',config)
    write(output/'network-policies.candidate.json',registry)
    # Store identities and digests, never a restorable copy of the live journal.
    observed_binding = {k:binding[k] for k in ['profile_id','status','session_id','operation_id','home_name',
        'application_id','network_policy_id','network_policy_sha256','updated_at'] if k in binding}
    report = {'schemaVersion':'browser-platform/migration-preparation/v1','status':'prepared',
        'preparedAt':datetime.now(timezone.utc).isoformat(),'productionChangesApplied':False,'readyToSwitch':False,
        'profile':args.profile,'from':old,'to':new,'observedBinding':observed_binding,'runtime':current,
        'observedOldWorkers':runtime_workers,
        'requiredRuntimeCapabilities':required,'observedControllerCapabilities':capabilities,
        'newHomeAbsentAndUnmounted':True,'sourceSHA256':source_hashes,
        'artifactSHA256':sha(args.artifact.read_bytes()),'acceptanceSHA256':sha(args.acceptance.read_bytes()),
        'image':app['provider_config']['image'],'applicationSHA256':sha((output/'application.json').read_bytes()),
        'rollbackPreservesJournal':True,'registryPreservesOldPolicies':True,
        'rollbackCreatesNewGenerationFromCurrentOldDefinition':True,
        'pending':['R4B target Mac/Trilium acceptance','maintenance window and consistent old Home backup',
            'recheck source hashes and current ownership','stop with old config and verify all resources released',
            'install candidate app and append policy; replace Adapter config; open new generation',
            'verify target Home, operation, image, policy, data and health; rollback uses verified stop then old config']}
    write(output/'migration.json',report)
    (output/'application.json').chmod(0o600)
    print(json.dumps({'status':'prepared','profile':args.profile,'readyToSwitch':False,'productionChangesApplied':False,'output':str(output)}))


if __name__ == '__main__':
    try:
        main()
    except (OSError,ValueError,KeyError) as error:
        raise SystemExit('Migration preparation refused: '+str(error))
