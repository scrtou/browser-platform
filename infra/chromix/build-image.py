#!/usr/bin/env python3
"""Build a pinned Chromix worker over the reviewed local X11 display image."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE=Path(__file__).resolve().parent
BASE='sha256:9a128663eb05d1b7a64a9519b597b745ba2b9be76af7b6649755a2a50d168306'


def docker(*args):
    return subprocess.check_output(['docker',*map(str,args)],text=True)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():
        parser.error('output exists')
    lock=json.loads((HERE/'release.lock.json').read_text())
    if json.loads((args.package/'verified-release.json').read_text()) != lock:
        parser.error('package lock differs')
    for name,expected in lock['executables'].items():
        if sha(args.package/name) != expected['sha256']:
            parser.error('package executable mismatch')
    base=json.loads(docker('image','inspect',BASE))[0]
    if base['Architecture'] != 'amd64' or base['Config']['Labels'].get('io.browser-platform.session-auth') != '1':
        parser.error('reviewed base required')
    if shutil.disk_usage(args.output.parent).free < 4*2**30 + 4*lock['expandedBytes']:
        parser.error('build would risk the 4 GiB disk reserve')
    sources={n:HERE/n for n in ['Dockerfile','fonts.lock.json','fonts.conf.template','launcher.py','shutdown.py','autostart','entrypoint','release.lock.json']}
    sources['x11_shutdown.py']=HERE.parent/'browser-runtime/browser-shutdown.py'
    hashes={n:sha(p) for n,p in sources.items()}
    # Include every packaged file, not just the main executable.
    hashes.update({'package/'+str(p.relative_to(args.package)):sha(p) for p in args.package.rglob('*') if p.is_file()})
    fingerprint=hashlib.sha256(json.dumps({'base':BASE,'files':hashes},sort_keys=True).encode()).hexdigest()
    tag='browser-platform/chromix:154.0.8037.57-'+fingerprint[:16]
    alias='browser-platform/chromix-base:'+BASE[7:]
    subprocess.run(['docker','tag',BASE,alias],check=True)
    with tempfile.TemporaryDirectory(prefix='chromix-build-',dir=args.output.parent) as raw:
        context=Path(raw)
        for name,path in sources.items():
            shutil.copyfile(path,context/name)
        shutil.copytree(args.package/'chromix',context/'chromix')
        for directory in [context/'chromix', *[p for p in (context/'chromix').rglob('*') if p.is_dir()]]:
            directory.chmod(0o755)
        subprocess.run(['docker','build','--network=none','--pull=false','--build-arg','BASE_IMAGE='+alias,'--build-arg','INPUT_SHA256='+fingerprint,'-t',tag,str(context)],check=True)
    image=json.loads(docker('image','inspect',tag))[0]
    assert image['RootFS']['Layers'][:len(base['RootFS']['Layers'])] == base['RootFS']['Layers']
    result={'image':tag,'imageId':image['Id'],'baseImageId':BASE,'inputSHA256':fingerprint,'files':hashes,'status':'candidate-not-accepted'}
    with args.output.open('x') as stream:
        json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps({'image':tag,'imageId':image['Id'],'status':result['status']}))


if __name__ == '__main__':
    main()
