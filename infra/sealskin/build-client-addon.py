#!/usr/bin/env python3
"""Freeze the versioned Selkies scripts into a new, content-addressed directory."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-parent', type=Path, required=True)
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    names = ('enable-screenshot-paste.py','screenshot-paste.js','screenshot-paste-init.sh')
    hashes = {name:hashlib.sha256((source/name).read_bytes()).hexdigest() for name in names}
    digest = hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    parent = args.output_parent.resolve(); parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    output = parent/('native-clipboard-'+digest[:16])
    manifest = {'bundleSHA256':digest,'files':hashes}
    if output.exists():
        assert not output.is_symlink() and json.loads((output/'bundle.json').read_text()) == manifest
        assert all(hashlib.sha256((output/name).read_bytes()).hexdigest() == value for name,value in hashes.items())
    else:
        output.mkdir(mode=0o755)
        for name in names:
            shutil.copyfile(source/name,output/name); (output/name).chmod(0o755 if name.endswith('.sh') else 0o644)
        (output/'bundle.json').write_text(json.dumps(manifest,indent=2)+'\n'); (output/'bundle.json').chmod(0o644)
    print(json.dumps({'path':str(output),**manifest}))


if __name__ == '__main__':
    main()
