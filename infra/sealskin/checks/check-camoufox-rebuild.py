#!/usr/bin/env python3
"""Rebuild only the prepared Camoufox QA Home through SealSkin's lifecycle.

Verify persistent browser storage, the frozen image/environment, resource limits
and a newly prepared immutable client bundle. No production Home is accepted.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

spec = importlib.util.spec_from_file_location('desktop', Path(__file__).with_name('qa-desktop.py'))
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)
network = desktop.network


def observe(worker):
    control = desktop.Desktop(worker)
    control.navigate('https://entry.leak.qa.test/client')
    control.key('F9')
    time.sleep(.3)
    value = control.run('xclip', '-selection', 'clipboard', '-o')
    assert value.startswith('BP_CLIENT_REPORT:')
    result = json.loads(value[len('BP_CLIENT_REPORT:'):])
    assert result['storage']['cookie'] and len(set(result['storage'].values())) == 1
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--clipboard-addon', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    qa, output = args.root.resolve(), args.output.resolve()
    checks = network.Checks(qa)
    info = json.loads((qa/'browser-worker.json').read_text())
    request = json.loads((qa/'browser-launch.json').read_text())
    assert info['engine'] == 'camoufox' and info['home'] == 'network-qa-home-browser'
    assert request['home_name'] == info['home'] and request['profile_id'] == 'network-qa-browser'
    assert request['application_id'] == 'camoufox-network-qa-r4'
    assert not output.exists(), 'use a new evidence directory'
    output.mkdir(mode=0o700, parents=True)
    old_app = json.loads((qa/'camoufox-app.json').read_text())
    mounts = {m['Target']:m['Source'] for m in old_app['provider_config']['docker_overrides']['mounts']}
    artifact, acceptance = Path(mounts['/run/browser-platform/environment.json']), Path(mounts['/run/browser-platform/acceptance.json'])
    command = [sys.executable, str(Path(__file__).resolve().parents[2]/'camoufox/prepare-sealskin.py'),
        '--artifact',str(artifact),'--acceptance',str(acceptance),'--app-id',request['application_id'],
        '--username','network-qa','--store','QA','--session-origin','https://network.invalid',
        '--network-policy-id',request['network_policy_id'],'--network-policy-sha256',request['network_policy_sha256'],
        '--clipboard-addon',str(args.clipboard_addon.resolve()),'--output',str(output/'app.json')]
    prepared = subprocess.run(command,capture_output=True,text=True,timeout=90)
    assert prepared.returncode == 0, 'new QA app rejected: '+prepared.stderr[:250]
    app = json.loads((output/'app.json').read_text())
    before = json.loads(network.docker('inspect',info['instance_id']).stdout)[0]
    before_observation = observe(before['Id'])
    status, before_inventory = checks.client.call('GET','/api/profile-runtime/'+info['home'])
    assert status == 200 and len(before_inventory['workers']) == 1
    network.write_json(output/'before.json',{'observation':before_observation,'inventory':before_inventory,
        'worker':before['Id'],'startedAt':before['State']['StartedAt'],'launch':request,
        'image':before['Image'],'resourceLimits':{k:before['HostConfig'][k] for k in ['Memory','NanoCpus','PidsLimit','ShmSize']}})
    status, _ = checks.client.call('POST','/api/profile-runtime/'+info['home']+'/stop',json.loads((qa/'browser-stop.json').read_text()))
    assert status == 204, 'verified QA stop failed'
    status, empty = checks.client.call('GET','/api/profile-runtime/'+info['home'])
    assert status == 200 and empty['workers'] == empty['records'] == empty['resources'] == []
    assert network.docker('inspect',before['Id'],check=False).returncode != 0
    network.write_json(output/'stopped.json',{'status':'pass','inventory':empty})
    allowed = json.loads((qa/'allow.json').read_text())
    allowed['readonly_sources'] = [m['Source'] for m in app['provider_config']['docker_overrides']['mounts']]
    network.write_json(qa/'allow.json',allowed)
    admin = json.loads((qa/'admin.json').read_text())
    client = network.SecureClient(qa,username=admin['username'],private=admin['private_key'].encode(),public=admin['server_public_key'].encode())
    status, _ = client.call('PATCH','/api/admin/apps/installed/'+app['id'],{'provider_config':app['provider_config']})
    assert status == 200, 'QA app update failed'
    network.write_json(qa/'camoufox-app.json',app)
    request.update(language='zh_TW.UTF-8', operation_id=uuid.uuid4().hex)
    network.write_json(qa/'browser-launch.json',request)
    stop = {key:request[key] for key in ('application_id','profile_id','operation_id','network_policy_id','network_policy_sha256')}
    stop['bootstrap_url'] = request['url']
    network.write_json(qa/'browser-stop.json',stop)
    status, launched = checks.client.call('POST','/api/launch/url',request)
    assert status == 200, 'new QA generation failed to launch'
    stop['session_id'] = launched['session_id']
    network.write_json(qa/'browser-stop.json',stop)
    status, inventory = checks.client.call('GET','/api/profile-runtime/'+info['home'])
    assert status == 200 and len(inventory['workers']) == 1
    info['instance_id'] = inventory['workers'][0]['instance_id']
    network.write_json(qa/'browser-worker.json',info)
    after = json.loads(network.docker('inspect',info['instance_id']).stdout)[0]
    assert before['Id'] != after['Id'] and before['Image'] == after['Image']
    assert all(before['HostConfig'][key] == after['HostConfig'][key] for key in ['Memory','NanoCpus','PidsLimit','ShmSize'])
    assert 'LC_ALL=zh_TW.UTF-8' in after['Config']['Env']
    network.wait(lambda: network.docker('exec','--user','1000','-e','DISPLAY=:1',after['Id'],
        'xdotool','getactivewindow','getwindowname',check=False).stdout.startswith('Private browser network check'),'rebuilt Camoufox ready')
    after_observation = observe(after['Id'])
    assert before_observation['storage'] == after_observation['storage'], 'browser storage changed across rebuild'
    assert before_observation['environment'] == after_observation['environment'], 'frozen browser environment changed'
    manifest = json.loads(network.docker('exec',after['Id'],'cat','/var/lib/browser-platform/screenshot-paste/manifest.json').stdout)
    assert manifest['addonSHA256'] == hashlib.sha256((args.clipboard_addon/'screenshot-paste.js').read_bytes()).hexdigest()
    expected_installer = hashlib.sha256((args.clipboard_addon/'enable-screenshot-paste.py').read_bytes()).hexdigest()
    installed = network.docker('exec',after['Id'],'sha256sum','/opt/browser-platform/selkies-paste/enable-screenshot-paste.py').stdout.split()[0]
    assert installed == expected_installer and manifest['servicesRestarted'] is False
    result = {'status':'pass','checkedAt':datetime.now(timezone.utc).isoformat(),'engine':'camoufox',
        'oldWorker':before['Id'],'newWorker':after['Id'],'verifiedStopReleasedAllResources':True,
        'sameHome':info['home'],'persistentCookieLocalStorageIndexedDB':True,'sameFrozenImageAndEnvironment':True,
        'resourceLimitsPreserved':True,'posixLocale':'zh_TW.UTF-8','browserLocale':after_observation['environment']['language'],
        'clientManifest':manifest,'clientInstallerSHA256':installed,'afterObservation':after_observation}
    network.write_json(output/'rebuild.json',result)
    checks.passed('Camoufox verified stop and rebuild preserve Home data, frozen environment and resources; new client bundle installed',
        evidence=str(output/'rebuild.json'))
    print(json.dumps({'status':'pass','check':'camoufox-rebuild','evidence':str(output)}))


if __name__ == '__main__':
    main()
