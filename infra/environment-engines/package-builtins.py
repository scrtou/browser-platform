#!/usr/bin/env python3
"""Export only the 24 fully accepted built-in combinations and their source caches.

The package has no accounts, Home data, queue, credentials or host-specific app
configuration. A deployment must rebuild application definitions for its paths.
"""
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'camoufox'))
from template_sources import BUILTIN_FINGERPRINTS, TARGETS, source_records, raw_json, sha
from native_jobs import accepted as native_accepted

from builtin_bundle import DISPLAY_IDS, verify_bundle

def write(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open('x') as stream:
        os.chmod(path, 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')

def copy(source, destination):
    if source.is_symlink() or not source.is_file():
        raise ValueError('BUILTIN_SOURCE_NOT_REGULAR')
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with source.open('rb') as src, destination.open('xb') as dst:
        os.chmod(destination, 0o600)
        shutil.copyfileobj(src, dst)

def export(qa, targets, destination):
    if destination.exists():
        raise ValueError('BUILTIN_DESTINATION_EXISTS')
    spool = qa / 'jobs'
    catalog = raw_json(qa / 'environment-catalog.json')
    templates = raw_json(qa / 'template-catalog.json')
    registry = raw_json(targets)['targets']
    entries = catalog['artifacts']
    expected = set(itertools.product(TARGETS, BUILTIN_FINGERPRINTS, DISPLAY_IDS))
    if len(entries) != 24 or len(templates['compatibility']) != 24:
        raise ValueError('BUILTIN_EXPECTED_24')
    seen = set()
    validated = []
    for entry in entries:
        request = raw_json(spool / 'queue' / (entry['job_id'] + '.json'))
        status = raw_json(spool / 'status' / (entry['job_id'] + '.json'))
        fp, display = source_records(spool, request)
        key = entry['browser_template_id'], fp['id'], display['id']
        if key not in expected or key in seen or status['status'] != 'accepted':
            raise ValueError('BUILTIN_COMBINATION_INVALID')
        seen.add(key)
        if request['generation']['browser_template_id'] != key[0] or entry['image'] != registry[key[0]]['image']:
            raise ValueError('BUILTIN_TARGET_MISMATCH')
        mounts = entry['application']['provider_config']['docker_overrides']['mounts']
        files = {}
        for name in ('environment.json', 'acceptance.json'):
            sources = [Path(m['Source']) for m in mounts if m['Target'] == '/run/browser-platform/' + name]
            if len(sources) != 1 or sources[0].is_symlink() or not sources[0].resolve().is_relative_to((spool / 'artifacts').resolve()):
                raise ValueError('BUILTIN_ARTIFACT_PATH')
            files[name] = sources[0]
        artifact, report = raw_json(files['environment.json']), raw_json(files['acceptance.json'])
        if sha(files['environment.json']) != entry['sha256'] or sha(files['acceptance.json']) != entry['acceptance_sha256']:
            raise ValueError('BUILTIN_ARTIFACT_DIGEST')
        if artifact['runtimeImageDigest'] != entry['image'] or report['artifactSHA256'] != entry['sha256'] or report['runtimeImageDigest'] != entry['image']:
            raise ValueError('BUILTIN_REPORT_BINDING')
        if report.get('schemaVersion') == 'browser-platform/native-acceptance/v1':
            native_accepted(files['acceptance.json'], files['environment.json'], entry['image'])
        else:
            replay = report.get('results', {}).get('homeReplay', {})
            if (report.get('schemaVersion') != 'browser-platform/camoufox-acceptance/v1'
                    or report.get('status') != 'pass' or report.get('phase') != 'all'
                    or replay.get('recreationsPerHome', 0) < 10 or not replay.get('observationsStable')
                    or not replay.get('storageRestored') or replay.get('offlineBackupRestore') != 'pass'):
                raise ValueError('BUILTIN_FULL_ACCEPTANCE_REQUIRED')
        pair = [p for p in templates['compatibility'] if
                (p['browser_template_id'], p['environment_artifact_id'], p['display_template_id']) ==
                (key[0], entry['id'], key[2])]
        if len(pair) != 1 or pair[0]['status'] != 'accepted' or entry['status'] != 'accepted':
            raise ValueError('BUILTIN_PUBLICATION_REQUIRED')
        spec = artifact.get('spec', artifact)
        if any(spec[k] != fp[k] or entry[k] != fp[k] for k in ('locale', 'languages', 'timezone')):
            raise ValueError('BUILTIN_FINGERPRINT_MISMATCH')
        if entry['browser_engine'] == 'camoufox' and entry['screen'] != 'auto@system':
            files['desktop-acceptance.json'] = files['environment.json'].with_name('desktop-acceptance.json')
            entry['desktop_acceptance_sha256'] = sha(files['desktop-acceptance.json'])
        validated.append((entry, request, files))
    if seen != expected:
        raise ValueError('BUILTIN_MATRIX_INCOMPLETE')
    destination.mkdir(mode=0o700, parents=True)
    exported = []
    provenance = []
    for entry, request, files in validated:
        for name, source in files.items():
            copy(source, destination / 'combinations' / entry['id'] / name)
        value = {k: v for k, v in entry.items() if k not in ('application', 'job_id')}
        value['source'] = 'frozen'
        exported.append(value)
        provenance.append({'environment_id': entry['id'], 'templates': request['templates'], 'generation': request['generation']})
    for kind, ids in [('fingerprints', BUILTIN_FINGERPRINTS), ('displays', DISPLAY_IDS)]:
        for ident in sorted(ids):
            copy(spool / 'templates' / kind / (ident + '.json'), destination / 'templates' / kind / (ident + '.json'))
    # Copy only the 12 current source/target caches, never Homes or historical QA.
    for ident in BUILTIN_FINGERPRINTS:
        for target, (engine, version, _) in TARGETS.items():
            generation = {'browser_template_id': target, 'browser_template_revision': 1, 'engine': engine, 'browser_version': version}
            digest = hashlib.sha256(json.dumps(generation, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            source = spool / 'fingerprint-cache' / ident / digest
            names = ('environment.json', 'receipt.json') if engine == 'camoufox' else ('device.json',)
            receipt = raw_json(source / names[-1])
            if receipt['image'] != registry[target]['image'] or receipt['source_sha256'] != sha(destination / 'templates/fingerprints' / (ident + '.json')):
                raise ValueError('BUILTIN_CACHE_BINDING')
            if engine == 'camoufox' and receipt['artifact_sha256'] != sha(source / 'environment.json'):
                raise ValueError('BUILTIN_CACHE_DIGEST')
            for name in names:
                copy(source / name, destination / 'fingerprint-cache' / ident / digest / name)
    for pair in templates['compatibility']:
        pair['builtin'] = True
    write(destination / 'catalog.json', {'version': 1, 'artifacts': exported})
    write(destination / 'template-catalog.json', templates)
    write(destination / 'provenance.json', provenance)
    copy(targets, destination / 'native-targets.json')
    manifest = {str(p.relative_to(destination)): sha(p) for p in destination.rglob('*') if p.is_file()}
    write(destination / 'manifest.json', manifest)
    verify_bundle(destination)
    return {'result': 'PASS', 'combinations': len(exported), 'files': len(manifest)}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qa', type=Path, required=True)
    parser.add_argument('--targets', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    print(json.dumps(export(args.qa.resolve(), args.targets.resolve(), args.output.resolve())))

if __name__ == '__main__':
    main()
