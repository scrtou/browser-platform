#!/usr/bin/env python3
"""Prepare additive, same-seed cache revisions; never modify the source spool."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'camoufox'))
from template_sources import raw_json, sha, validate_target_shape, write


def stage(spool, old_image, new_image, output):
    assert old_image != new_image
    for image in (old_image, new_image):
        assert re.fullmatch('sha256:[a-f0-9]{64}', image)
        value = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image]))[0]
        assert value['Id'] == image
        labels = value['Config']['Labels']
        assert labels['io.browser-platform.browser-engine'] == 'chromix'
        assert labels['io.browser-platform.chromix-version'] == '154.0.8037.57'
        assert labels['io.browser-platform.custom-generation'] == '1'
    output.mkdir(mode=0o700)
    entries = []
    for path in sorted((spool/'fingerprint-cache').glob('*/*/device.json')):
        original = raw_json(path)
        if original['generation']['engine'] != 'chromix':
            continue
        assert set(original) == {'source_sha256', 'generation', 'image', 'seed'}
        assert original['image'] == old_image, 'UNREVIEWED_CHROMIX_CACHE_IMAGE'
        assert type(original['seed']) is int and 0 < original['seed'] < 2**64
        validate_target_shape(original['generation'])
        target_hash = hashlib.sha256(json.dumps(original['generation'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        assert path.parent.name == target_hash
        source = spool/'templates/fingerprints'/(path.parent.parent.name+'.json')
        fp = raw_json(source)
        assert fp['version'] == 2 and fp['id'] == path.parent.parent.name
        assert sha(source) == original['source_sha256']
        rel = path.parent.relative_to(spool)/'runtimes'/new_image[7:]/'device.json'
        assert not (spool/rel).exists(), 'CACHE_REVISION_ALREADY_EXISTS'
        destination = output/rel
        destination.parent.mkdir(parents=True, mode=0o700)
        write(destination, {**original, 'image': new_image})
        entries.append({'path':str(rel), 'sha256':sha(destination),
                        'original':str(path.relative_to(spool)), 'original_sha256':sha(path),
                        'source':str(source.relative_to(spool)), 'source_sha256':sha(source)})
    receipt = {'old_image':old_image, 'new_image':new_image, 'entries':entries}
    write(output/'receipt.json', receipt)
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--spool', type=Path, required=True)
    p.add_argument('--old-image', required=True)
    p.add_argument('--new-image', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    result = stage(a.spool.resolve(), a.old_image, a.new_image, a.output.resolve())
    print('Prepared', len(result['entries']), 'same-seed cache revisions; source spool unchanged')


if __name__ == '__main__':
    main()
