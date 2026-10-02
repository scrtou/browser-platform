#!/usr/bin/env python3
"""Stage an activated, single-Home QA backup without any source-path fallback.

Images, executables and the current revocation/account registry are explicit
external recovery inputs. This module does not activate or start services.
"""
import copy
import json
from pathlib import Path
import shutil

import yaml

DEPENDENCIES = ('profile_directory', 'environment_catalog', 'template_catalog',
                'network_profile_catalog', 'legacy_network_migrations')


def read(path):
    return json.loads(Path(path).read_bytes())


def require(value, code):
    if not value:
        raise ValueError(code)


def rebind_config(config, bundle, target):
    result = copy.deepcopy(config)
    require(result['sealskin']['username'] == 'network-qa', 'RECOVERY_QA_OWNER_REQUIRED')
    require(not result.get('environment_job_spool'), 'RECOVERY_JOB_SPOOL_INPUT_REQUIRED')
    result.update(state_file=str(target / 'adapter-state.json'),
                  control_socket='/tmp/browser-platform-network-qa.sock')
    for key, leaf in (('server_public_key_file', 'server-public.pem'), ('client_private_key_file', 'client-private.pem')):
        require((bundle / 'adapter' / leaf).is_file(), 'RECOVERY_IDENTITY_MISSING')
        result['sealskin'][key] = str(target / leaf)
    for field in DEPENDENCIES:
        if config.get(field):
            require((bundle / 'adapter/dependencies' / (field + '.json')).is_file(), 'RECOVERY_DEPENDENCY_MISSING')
            result[field] = str(target / 'dependencies' / (field + '.json'))
    if result.get('sealskin_admin') is not None:
        require((bundle / 'adapter/admin-client-private.pem').is_file(), 'RECOVERY_ADMIN_IDENTITY_MISSING')
        result['sealskin_admin']['client_private_key_file'] = str(target / 'access/admin-private.pem')
    if result.get('access') is not None:
        for field, leaf in (('users_file', 'access-users.json'), ('session_ca_file', 'session-ca.pem')):
            require((bundle / 'adapter' / leaf).is_file(), 'RECOVERY_ACCESS_INPUT_MISSING')
            result['access'][field] = str(target / 'access' / leaf)
    return result


def stage(bundle, target):
    bundle, target = Path(bundle).resolve(), Path(target).resolve()
    require(not target.exists() and target.name == 'qa' and 'runtime' in target.parts, 'RECOVERY_FRESH_QA_ROOT_REQUIRED')
    receipt = read(bundle / 'recovery.json')
    require(receipt.get('result') == 'BACKUP_RESTORED' and receipt.get('archive_format') == 'browser-platform/encrypted-backup/v1', 'RECOVERY_FORMAT_INVALID')
    require(read(bundle / 'activation.json').get('result') == 'BACKUP_REVOCATIONS_MERGED'
            and not (bundle / 'control/proxy-secret-store/.recovery-pending').exists(), 'RECOVERY_ACCESS_REVIEW_REQUIRED')
    config = rebind_config(read(bundle / 'adapter/config.json'), bundle, target)
    profile = receipt['profile']
    require(profile.startswith('network-qa-'), 'RECOVERY_QA_PROFILE_REQUIRED')
    definitions = config['profiles']
    if config.get('profile_directory'):
        definitions = read(bundle / 'adapter/dependencies/profile_directory.json')['browsers']
    active = [p for p in definitions if p.get('status') != 'deleted' and not p.get('disabled', False)]
    require(len(active) == 1 and active[0]['id'] == profile, 'RECOVERY_SINGLE_HOME_SCOPE_REQUIRED')
    definition = active[0]
    require(definition['home_name'].startswith('network-qa-'), 'RECOVERY_QA_HOME_REQUIRED')
    journal = read(bundle / 'adapter/state.json')
    require(all(v['status'] == 'stopped' for v in journal['bindings'].values()), 'RECOVERY_STOPPED_CHECKPOINT_REQUIRED')
    apps = yaml.safe_load((bundle / 'control/installed_apps.yml').read_text())
    for app in apps:
        for mount in app.get('overrides', {}).get('provider_config', {}).get('docker_overrides', {}).get('mounts', []):
            leaf = {'/run/browser-platform/environment.json': 'artifact.json',
                    '/run/browser-platform/acceptance.json': 'acceptance.json'}.get(mount.get('Target'))
            require(app['id'] == definition['application_id'] and leaf and mount.get('ReadOnly') is True,
                    'RECOVERY_UNPACKAGED_APP_ASSET')
            require((bundle / 'environment' / leaf).is_file(), 'RECOVERY_ENVIRONMENT_ASSET_MISSING')
            mount['Source'] = str(target / 'environment' / leaf)
    target.mkdir(mode=0o700, parents=True)
    metadata = target / 'config/.config/sealskin'
    shutil.copytree(bundle / 'control', metadata, ignore=shutil.ignore_patterns('ssl', 'admin.json'))
    shutil.copytree(bundle / 'control/ssl', target / 'config/ssl')
    for dest in (target / 'config/admin.json', target / 'admin.json'):
        shutil.copyfile(bundle / 'control/admin.json', dest); dest.chmod(0o600)
    shutil.copytree(bundle / 'home', target / 'storage/network-qa' / definition['home_name'], symlinks=True)
    shutil.copytree(bundle / 'environment', target / 'environment')
    if (bundle / 'adapter/dependencies').exists():
        shutil.copytree(bundle / 'adapter/dependencies', target / 'dependencies')
    (target / 'access').mkdir(mode=0o700)
    pairs = [('state.json', target / 'adapter-state.json'), ('server-public.pem', target / 'server-public.pem'),
             ('client-private.pem', target / 'client-private.pem')]
    if config.get('sealskin_admin'):
        pairs += [('admin-client-private.pem', target / 'access/admin-private.pem')]
    if config.get('access'):
        pairs += [('access-users.json', target / 'access/access-users.json'), ('session-ca.pem', target / 'access/session-ca.pem')]
    for leaf, dest in pairs:
        shutil.copyfile(bundle / 'adapter' / leaf, dest); dest.chmod(0o600)
    (target / 'adapter-config.json').write_text(json.dumps(config, indent=2))
    (target / 'adapter-config.json').chmod(0o600)
    (metadata / 'installed_apps.yml').write_text(yaml.safe_dump(apps, sort_keys=False))
    return {'profile': profile, 'home': definition['home_name'], 'application': definition['application_id'],
            'archived_configuration_rebound': True, 'started_workers': 0}
