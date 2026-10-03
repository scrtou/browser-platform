#!/usr/bin/env python3
"""Install a verified 1.0 release into a NEW private root (Linux amd64/systemd).

Never upgrades or erases an existing installation. Failed roots and logs remain
for diagnosis. Web administrators are initialized separately using profile-accounts.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import platform
import pwd
import re
import shutil
import socket
import stat
import ssl
import subprocess
import sys
import time
from urllib.parse import urlsplit


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write(path, value, mode=0o600):
    raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    with path.open('x') as f:
        os.chmod(path, mode)
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def verify_tree(root):
    """Reject extra files, traversal, symlinks and changed executable modes."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError('RELEASE_ROOT_INVALID')
    manifest = json.loads((root / 'release-manifest.json').read_text())
    if manifest.get('schema') != 'browser-platform/release-files/v1':
        raise ValueError('RELEASE_MANIFEST_INVALID')
    files = manifest['files']
    actual = set()
    for path in root.rglob('*'):
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise ValueError('RELEASE_SPECIAL_FILE')
        if path.is_file() and path != root / 'release-manifest.json':
            actual.add(path.relative_to(root).as_posix())
    if actual != set(files):
        raise ValueError('RELEASE_FILE_SET_CHANGED')
    for name, record in files.items():
        p = Path(name)
        if p.is_absolute() or '..' in p.parts or str(p) != name:
            raise ValueError('RELEASE_PATH_INVALID')
        path = root / p
        if digest(path) != record['sha256'] or path.stat().st_size != record['size'] or stat.S_IMODE(path.stat().st_mode) != record['mode']:
            raise ValueError('RELEASE_FILE_CHANGED: ' + name)
    return manifest


def retain_images(records, name, run):
    """Keep ID-loaded release images out of dangling-image garbage collection.

    Runtime configuration still uses exact IDs. Never replace a foreign tag.
    Preflight all tags before adding any references, retaining partial failures.
    """
    refs = {}
    for record in records:
        image = record['id']
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', image):
            raise ValueError('IMAGE_ID_INVALID')
        tag = 'browser-platform-retained/' + name + ':sha256-' + image[7:]
        existing = subprocess.check_output(
            ['docker', 'image', 'ls', '--no-trunc', '--quiet', tag], text=True).split()
        if existing and set(existing) != {image}:
            raise ValueError('IMAGE_RETENTION_TAG_CONFLICT')
        refs[tag] = image
    for tag, image in refs.items():
        run(['docker', 'image', 'tag', image, tag])
        actual = json.loads(subprocess.check_output(['docker', 'image', 'inspect', tag]))[0]
        if actual['Id'] != image:
            raise ValueError('IMAGE_RETENTION_VERIFY_FAILED')
    return refs


def origin(value):
    p = urlsplit(value)
    if (p.scheme != 'https' or p.username is not None or p.password is not None
            or p.path or p.query or p.fragment or not p.hostname
            or not re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)*', p.hostname)
            or len(p.hostname) > 253 or any(len(x) > 63 for x in p.hostname.split('.'))):
        raise ValueError('HTTPS_ORIGIN_INVALID')
    if p.port is not None and not 1024 <= p.port <= 65535:
        raise ValueError('ORIGIN_PORT_INVALID')
    return p


def validate(args):
    if not re.fullmatch(r'bp-[a-z0-9][a-z0-9-]{0,19}', args.name):
        raise ValueError('NAME_REQUIRES_BP_PREFIX')
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,30}', args.user) or args.user == 'root':
        raise ValueError('NEW_NONROOT_USER_REQUIRED')
    root = args.root
    if (not root.is_absolute() or root.resolve() != root or root.exists()
            or root.parent.resolve() != root.parent or not root.parent.is_dir()
            or not re.fullmatch(r'/[A-Za-z0-9_./-]+', str(root))
            or len(str(root / 'control.sock')) >= 104):
        raise ValueError('NEW_ROOT_REQUIRED')
    entry, session = origin(args.entry_origin), origin(args.session_origin)
    if entry.hostname == session.hostname or (entry.port or 443) != (session.port or 443):
        raise ValueError('SEPARATE_HOSTS_SAME_PORT_REQUIRED')
    if not args.private_tls and (entry.port or 443) != 443:
        raise ValueError('PUBLIC_TLS_REQUIRES_PORT_443')
    ports = [args.adapter_port, args.api_port, args.backend_port, entry.port or 443]
    if len(set(ports)) != 4 or any(not 1024 <= p <= 65535 for p in ports[:3]):
        raise ValueError('DISTINCT_PORTS_REQUIRED')
    return entry, session, ports


def tls(directory, names):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    directory.mkdir(mode=0o700)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=365))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in names]), False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
            .add_extension(x509.KeyUsage(True, False, True, False, False, True, True, False, False), True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
            .sign(key, hashes.SHA256()))
    write(directory / 'key.pem', key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode())
    write(directory / 'cert.pem', cert.public_bytes(serialization.Encoding.PEM).decode())


def chown_tree(root, uid, gid):
    for path in [root, *root.rglob('*')]:
        os.chown(path, uid, gid, follow_symlinks=False)


def install(args):
    entry, session, ports = validate(args)
    verify_tree(args.release)
    inputs = json.loads((args.release / 'deployment/inputs.json').read_text())
    if args.check_only:
        return {'result': 'INPUTS_VALID', 'side_effects': False}
    if os.geteuid() != 0 or platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'amd64'):
        raise ValueError('ROOT_LINUX_AMD64_REQUIRED')
    from cryptography import x509  # Dependency preflight before creating anything.
    for name in ['docker', 'caddy', 'systemctl', 'systemd-tmpfiles', 'useradd', 'runuser']:
        if not shutil.which(name):
            raise ValueError('DEPENDENCY_MISSING: ' + name)
    try:
        pwd.getpwnam(args.user)
    except KeyError:
        pass
    else:
        raise ValueError('SYSTEM_USER_ALREADY_EXISTS')
    units = {kind: Path('/etc/systemd/system') / (args.name + '-' + kind + '.service') for kind in ['controller', 'adapter', 'jobs', 'front']}
    tmpfile = Path('/etc/tmpfiles.d') / (args.name + '.conf')
    runtime_dirs = [Path('/dev/shm') / (args.name + '-' + k) for k in ['credentials', 'sessions']]
    if any(p.exists() or p.is_symlink() for p in [*units.values(), tmpfile, *runtime_dirs]):
        raise ValueError('INSTALLATION_RESOURCE_EXISTS')
    for port in ports:
        with socket.socket() as s:
            s.bind(('127.0.0.1' if args.private_tls or port != 443 else '0.0.0.0', port))
    subprocess.run(['docker', 'compose', 'version'], check=True, stdout=subprocess.DEVNULL)
    existing = subprocess.check_output(['docker', 'container', 'ls', '-a', '--format', '{{.Names}}'], text=True).splitlines()
    if args.name + '-controller' in existing:
        raise ValueError('CONTROLLER_NAME_EXISTS')
    for record in inputs['images']:
        values = json.loads(subprocess.check_output(['docker', 'image', 'inspect', record['reference']]))[0]
        if any(values[k] != record[v] for k, v in [('Id','id'), ('Architecture','architecture'), ('Os','os')]):
            raise ValueError('IMAGE_IDENTITY_CHANGED')
    root = args.root
    root.mkdir(mode=0o700)
    log = (root / 'install.log').open('x')
    def run(argv, timeout=180):
        subprocess.run([str(x) for x in argv], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=timeout)
    try:
        write(root / 'install-request.json', {k: str(v) if isinstance(v, Path) else v for k,v in vars(args).items()})
        write(root / 'image-retention.json', retain_images(inputs['images'], args.name, run))
        run(['useradd', '--system', '--user-group', '--home-dir', root, '--no-create-home', '--shell', '/usr/sbin/nologin', '--groups', 'docker', args.user])
        account = pwd.getpwnam(args.user)
        shutil.copytree(args.release, root / 'release')
        verify_tree(root / 'release')
        for name in ['config', 'storage', 'secrets', 'jobs', 'access', 'caddy']:
            (root / name).mkdir(mode=0o700)
        meta = root / 'config/.config/sealskin'
        meta.mkdir(mode=0o700, parents=True)
        write(meta / 'app_stores.yml', '[]\n')
        write(meta / 'profile-secret-store.json', {'version':1, 'key_file':'/run/browser-platform-key/master.key', 'runtime_dir':'/run/browser-platform-secrets'})
        run([sys.executable, root / 'release/controller/app/secret_store.py', '--directory', meta / 'proxy-secret-store', '--key-file', root / 'secrets/master.key', 'init'])
        tls(root / 'config/ssl', [session.hostname])
        (root / 'config/ssl/key.pem').rename(root / 'config/ssl/proxy_key.pem')
        (root / 'config/ssl/cert.pem').rename(root / 'config/ssl/proxy_cert.pem')
        shutil.copyfile(root / 'config/ssl/proxy_cert.pem', root / 'access/session-ca.pem')
        if args.private_tls:
            tls(root / 'access/front-tls', [entry.hostname, session.hostname])
        write(tmpfile, ''.join(f'd {p} 0700 {args.user} {args.user} -\n' for p in runtime_dirs), 0o644)
        run(['systemd-tmpfiles', '--create', tmpfile])
        mounts = [(root/'config','/config',False),(root/'storage','/storage',False),(root/'secrets','/run/browser-platform-key',True),
                  (runtime_dirs[0],'/run/browser-platform-secrets',False),(runtime_dirs[1],'/run/browser-platform-session-secrets',False),
                  (Path('/proc/1/net/fib_trie'),'/run/browser-platform-host/ipv4-fib-trie',True),(Path('/var/run/docker.sock'),'/var/run/docker.sock',False)]
        compose = {'name':args.name,'services':{'controller':{'image':inputs['controller'],'container_name':args.name+'-controller',
            'environment':{'PUID':str(account.pw_uid),'PGID':str(account.pw_gid),'SEALSKIN_PUID':str(account.pw_uid),'SEALSKIN_PGID':str(account.pw_gid),'TZ':'Etc/UTC','HOST_URL':session.hostname},
            'volumes':[{'type':'bind','source':str(src),'target':dest,'read_only':ro,'bind':{'create_host_path':False}} for src,dest,ro in mounts],
            'ports':[f'127.0.0.1:{args.backend_port}:8443',f'127.0.0.1:{args.api_port}:8000'],
            'logging':{'driver':'json-file','options':{'max-size':'10m','max-file':'3'}},'restart':'unless-stopped'}}}
        write(root / 'compose.json', compose)
        chown_tree(root, account.pw_uid, account.pw_gid)
        controller = units['controller'].name
        write(units['controller'], f'[Unit]\nDescription=Browser Platform controller ({args.name})\nRequires=docker.service\nAfter=docker.service systemd-tmpfiles-setup.service\n\n[Service]\nType=oneshot\nRemainAfterExit=yes\nWorkingDirectory={root}\nExecStartPre=/usr/bin/systemd-tmpfiles --create {tmpfile}\nExecStart=/usr/bin/docker compose -f {root}/compose.json up -d --pull never\nExecStop=/usr/bin/docker compose -f {root}/compose.json stop\nTimeoutStartSec=180\nTimeoutStopSec=180\n\n[Install]\nWantedBy=multi-user.target\n', 0o644)
        run(['systemctl', 'daemon-reload'])
        run(['systemctl', 'start', controller])
        deadline = time.monotonic() + 180
        while not (root / 'config/admin.json').is_file():
            if time.monotonic() >= deadline:
                raise ValueError('CONTROLLER_BOOTSTRAP_TIMEOUT')
            time.sleep(1)
        admin = json.loads((root / 'config/admin.json').read_text())
        admin['server_endpoint'] = f'http://127.0.0.1:{args.api_port}'
        write(root / 'access/bootstrap.json', admin)
        write(root / 'access/server-public.pem', admin['server_public_key'])
        write(root / 'access/admin-private.pem', admin['private_key'])
        # Wait for the bootstrap HTTP listener, then provision over its encrypted API.
        while True:
            try:
                with socket.create_connection(('127.0.0.1', args.api_port), timeout=2):
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    raise ValueError('CONTROLLER_API_TIMEOUT')
                time.sleep(1)
        run([root/'release/bin/sealskin-provision','--admin-config',root/'access/bootstrap.json','--username','platform','--private-key',root/'access/client-private.pem'])
        chown_tree(root, account.pw_uid, account.pw_gid)
        run(['runuser','-u',args.user,'--',sys.executable,root/'release/runner/infra/environment-engines/prepare-builtin-install.py','--bundle',root/'release/builtins','--output',root/'builtins','--username','platform','--session-origin',args.session_origin,'--clipboard-addon',root/'release/runtime-dependencies/native-clipboard'])
        for name in ['templates','fingerprint-cache']:
            shutil.copytree(root / 'builtins' / name, root / 'jobs' / name)
        cfg = {'listen_address':f'127.0.0.1:{args.adapter_port}','public_base_url':args.entry_origin,
            'state_file':str(root/'adapter-state.json'),'control_socket':str(root/'control.sock'),
            'profile_directory':str(root/'profiles.json'),'environment_catalog':str(root/'builtins/environment-catalog.json'),
            'template_catalog':str(root/'builtins/template-catalog.json'),'environment_job_spool':str(root/'jobs'),
            'network_profile_catalog':str(root/'network-profiles.json'),
            'sealskin':{'api_base_url':f'https://127.0.0.1:{args.backend_port}','public_session_base_url':args.session_origin,'username':'platform','server_public_key_file':str(root/'access/server-public.pem'),'client_private_key_file':str(root/'access/client-private.pem'),'allow_unencrypted_http':False,'lifecycle_enabled':True},
            'sealskin_admin':{'username':admin['username'],'client_private_key_file':str(root/'access/admin-private.pem')},
            'proxy_template':dict(inputs['proxy_template'],owner='platform'),'direct_template':dict(inputs['direct_template'],owner='platform'),
            'access':{'users_file':str(root/'access/entry-users.json'),'session_upstream_url':f'https://127.0.0.1:{args.backend_port}','session_ca_file':str(root/'access/session-ca.pem'),'session_tls_name':session.hostname,'session_seconds':1800,'ticket_seconds':30},
            'limits':{'storage_path':str(root/'storage')},'profiles':[]}
        write(root / 'profiles.json', {'version':1,'revision':1,'browsers':[]})
        write(root / 'access/entry-users.json', {'version':3,'users':[],'setup_required':True})
        write(root / 'adapter-config.json', cfg)
        caddy = (root/'release/deployment/Caddyfile.template').read_text().replace('ENTRY_ORIGIN',args.entry_origin).replace('SESSION_ORIGIN',args.session_origin).replace('ADAPTER_UPSTREAM',f'127.0.0.1:{args.adapter_port}')
        tls_config = f'bind 127.0.0.1\n    tls {root}/access/front-tls/cert.pem {root}/access/front-tls/key.pem' if args.private_tls else ''
        caddy = caddy.replace('TLS_CONFIG',tls_config).replace('GLOBAL_OPTIONS','auto_https off' if args.private_tls else '')
        write(root / 'Caddyfile', caddy)
        camoufox = inputs['native_targets']['targets']['camoufox-linux-v152']['image']
        runner = f'/usr/bin/python3 {root}/release/runner/infra/camoufox/environment-job.py run --watch 10 --spool {root}/jobs --catalog {root}/builtins/environment-catalog.json --template-catalog {root}/builtins/template-catalog.json --browser-template-id camoufox-linux-v152 --image {camoufox} --native-targets {root}/release/runner/native-targets.json --username platform --session-origin {args.session_origin} --clipboard-addon {root}/release/runtime-dependencies/native-clipboard --client-browsers {root}/release/runtime-dependencies/job-client-browsers'
        commands = {'adapter':f'{root}/release/bin/profile-adapter --config {root}/adapter-config.json','jobs':runner,'front':f'/usr/bin/caddy run --config {root}/Caddyfile --adapter caddyfile'}
        for kind, command in commands.items():
            caps = 'AmbientCapabilities=CAP_NET_BIND_SERVICE\nCapabilityBoundingSet=CAP_NET_BIND_SERVICE\n' if kind == 'front' and not args.private_tls else ''
            write(units[kind], f'[Unit]\nDescription=Browser Platform {kind} ({args.name})\nRequires={controller}\nAfter={controller}\n\n[Service]\nUser={args.user}\nGroup={args.user}\nSupplementaryGroups=docker\nWorkingDirectory={root}\nEnvironment=XDG_DATA_HOME={root}/caddy\nEnvironment=XDG_CONFIG_HOME={root}/caddy\nEnvironment=PYTHONDONTWRITEBYTECODE=1\nExecStart={command}\nRestart=on-failure\nRestartSec=5\nTimeoutStopSec=180\nUMask=0077\nNoNewPrivileges=yes\n{caps}\n[Install]\nWantedBy=multi-user.target\n', 0o644)
        chown_tree(root, account.pw_uid, account.pw_gid)
        run(['runuser','-u',args.user,'--','caddy','validate','--config',root/'Caddyfile','--adapter','caddyfile'])
        run(['systemctl','daemon-reload'])
        run(['systemctl','enable','--now',*[p.name for p in units.values()]])
        wait_ready(args, root)
        result = {'result':'INSTALLED','ready_verified':True,'root':str(root),'services':[p.name for p in units.values()],
                  'web_admin_initialized':False,'entry_origin':args.entry_origin,'session_origin':args.session_origin,
                  'release_manifest_sha256':digest(root/'release/release-manifest.json')}
        write(root / 'installation.json', result)
        return result
    except Exception:
        write(root / 'installation-failed.json', {'result':'FAILED','retained':True,'private_log':str(root/'install.log')})
        raise
    finally:
        log.close()


def wait_ready(args, root, timeout=180):
    """A started process is insufficient: require API readiness and verified TLS."""
    host = urlsplit(args.entry_origin)
    context = ssl.create_default_context(cafile=str(root/'access/front-tls/cert.pem') if args.private_tls else None)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            conn = http.client.HTTPConnection('127.0.0.1', args.adapter_port, timeout=5)
            try:
                conn.request('GET','/readyz',headers={'Host':host.netloc})
                response=conn.getresponse();response.read()
                if response.status != 200:raise OSError('ADAPTER_NOT_READY')
            finally:conn.close()
            conn = http.client.HTTPSConnection(host.hostname,host.port or 443,context=context,timeout=5)
            try:
                conn.sock = context.wrap_socket(socket.create_connection(('127.0.0.1',host.port or 443),timeout=5),server_hostname=host.hostname)
                conn.request('GET','/auth/login',headers={'Host':host.netloc})
                response=conn.getresponse();body=response.read(1024*1024).decode('utf-8')
                if response.status != 200 or '平台尚未初始化' not in body or '<form method="post" action="/auth/login">' in body:
                    raise OSError('INITIALIZATION_PAGE_NOT_READY')
            finally:conn.close()
            return
        except (OSError, http.client.HTTPException):
            time.sleep(1)
    raise ValueError('INSTALLATION_READINESS_TIMEOUT')


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['release','root']:
        p.add_argument('--'+name,type=Path,required=True)
    for name in ['name','user','entry-origin','session-origin']:
        p.add_argument('--'+name,required=True)
    for name, default in [('adapter-port',19100),('api-port',18000),('backend-port',18443)]:
        p.add_argument('--'+name,type=int,default=default)
    p.add_argument('--private-tls',action='store_true',help='QA only: new private certificate and loopback-only ingress')
    p.add_argument('--check-only',action='store_true',help='validate inputs and release files without host changes')
    return p


if __name__ == '__main__':
    os.umask(0o077)
    try:
        print(json.dumps(install(parser().parse_args())))
    except (ValueError,OSError,subprocess.SubprocessError) as e:
        # Never echo a controller/bootstrap error or sensitive response.
        print('INSTALL_FAILED: ' + (str(e) if isinstance(e,ValueError) else type(e).__name__) + '; retain the private install.log',file=sys.stderr)
        sys.exit(1)
