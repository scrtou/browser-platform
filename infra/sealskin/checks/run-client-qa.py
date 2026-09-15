#!/usr/bin/env python3
"""Run a separate Chromium client against the scoped QA controller's real Caddy.

The QA certificate is pinned by SPKI; host mapping keeps the exact configured
Session origin. Only labelled QA Homes are read or given test fixtures.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import uuid

from cryptography import x509
from cryptography.hazmat.primitives import serialization

spec = importlib.util.spec_from_file_location('qa_network', Path(__file__).resolve().parents[1] / 'lifecycle/check-network-live.py')
network = importlib.util.module_from_spec(spec)
spec.loader.exec_module(network)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--check', choices=('boundary', 'native-copy', 'screenshot-paste'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    qa, output = args.root.resolve(), args.output.resolve()
    project = Path(__file__).resolve().parents[3]
    checks = Path(__file__).resolve().parent
    assert qa.name == 'qa' and not output.exists(), 'use a fresh output directory and scoped QA root'
    info = json.loads((qa / 'browser-worker.json').read_text())
    client = network.SecureClient(qa)
    status, inventory = client.call('GET', '/api/profile-runtime/' + info['home'])
    assert status == 200 and len(inventory['workers']) == 1
    worker = inventory['workers'][0]['instance_id']
    assert worker == info['instance_id']
    container = json.loads(network.docker('inspect', worker).stdout)[0]
    labels = container['Config']['Labels']
    assert labels['io.browser-platform.owner'] == 'network-qa' and labels['io.browser-platform.home'] == info['home']
    assert info['home'].startswith('network-qa-')
    output.mkdir(mode=0o700, parents=True)
    if args.check == 'boundary':
        shutil.copyfile(checks / 'client-fixture.html', qa.parent / 'observer/client-fixture.html')
    controller = json.loads(network.docker('inspect', network.SERVER).stdout)[0]
    address = controller['NetworkSettings']['Networks']['browser-platform-network-qa']['IPAddress']
    cert = x509.load_pem_x509_certificate((qa / 'config/ssl/proxy_cert.pem').read_bytes())
    public_key = cert.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    pin = base64.b64encode(hashlib.sha256(public_key).digest()).decode()
    status, sessions = client.call('GET', '/api/sessions')
    assert status == 200
    session_id = json.loads((qa / 'browser-stop.json').read_text())['session_id']
    session = next(value for value in sessions if value['session_id'] == session_id)
    private = output / 'session.json'
    network.write_json(private, {'session_url': session['session_url']})
    for source, name in [('native-copy-fixture.html', 'native-copy'), ('screenshot-paste-fixture.html', 'screenshot-paste'),
                         ('client-fixture.html', 'client')]:
        path = checks / source
        if path.exists():
            network.docker('cp', str(path), worker + ':/tmp/browser-platform-' + name + '.html')
    name = 'bp-r4-client-' + uuid.uuid4().hex[:12]
    script = 'client-boundary.py' if args.check == 'boundary' else args.check + '-client.py'
    report_name = 'client-boundary.json' if args.check == 'boundary' else args.check + '.json'
    browsers = project / 'infra/camoufox/.build/playwright-client-browsers'
    command = ['docker', 'run', '--rm', '--name', name, '--network', 'host', '--user', '1000:1000',
               '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--read-only',
               '--memory', '1536m', '--cpus', '1.5', '--shm-size', '256m',
               '--tmpfs', '/tmp:rw,nosuid,nodev,size=256m', '--tmpfs', '/config:rw,nosuid,nodev,uid=1000,gid=1000,size=32m',
               '-e', 'PLAYWRIGHT_BROWSERS_PATH=/client-browsers',
               '--mount', f'type=bind,src={browsers},dst=/client-browsers,readonly',
               '--mount', f'type=bind,src={checks},dst=/checks,readonly',
               '--mount', f'type=bind,src={output},dst=/evidence',
               '--entrypoint', '/opt/camoufox-python/bin/python', 'browser-platform/camoufox:0.5.6-beta.30-r4',
               '/checks/' + script, '--session-file', '/evidence/session.json', '--output-dir', '/evidence',
               '--origin', 'https://network.invalid', '--host-resolver-rules', f'MAP network.invalid:443 {address}:8443',
               '--certificate-spki', pin, '--emulate-mac-keyboard']
    try:
        with (output / 'client.log').open('w') as log:
            os.fchmod(log.fileno(), 0o600)
            process = subprocess.Popen(['sg', 'docker', '-c', shlex.join(command)], stdout=log, stderr=subprocess.STDOUT)
            try:
                code = process.wait(timeout=400)
            except subprocess.TimeoutExpired:
                raise RuntimeError('QA client did not finish within its test budget')
        report = (json.loads((output / report_name).read_text()) if (output / report_name).exists()
                  else {'status':'fail','stage':'client-bootstrap','errorType':'MissingClientReport'})
        after = json.loads(network.docker('inspect', worker).stdout)[0]
        assert (after['Id'], after['State']['StartedAt']) == (container['Id'], container['State']['StartedAt'])
        report.update(workerImage=container['Image'], workerPreserved=True, engine=info.get('engine', 'firefox'),
                      sessionBindingPreserved=True, sessionTLS='QA controller SPKI pin', finishedAt=datetime.now(timezone.utc).isoformat())
        for item in report.get('uploads', []):
            assert Path(item['name']).name == item['name'] and item['name'].startswith('bp-r4-')
            path = qa / 'storage/network-qa' / info['home'] / 'Desktop' / item['name']
            assert path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256'], 'uploaded file differs in QA Home'
            item['remoteHomeSHA256Matched'] = True
        network.write_json(output / report_name, report)
        print(json.dumps({'check': args.check, 'status': report['status'], 'clientExitCode': code,
                          'workerPreserved': True, 'evidence': str(output)}), flush=True)
        return code
    finally:
        network.docker('rm', '-f', name, check=False)
        private.unlink(missing_ok=True)


if __name__ == '__main__':
    raise SystemExit(main())
