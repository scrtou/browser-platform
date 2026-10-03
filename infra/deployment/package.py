#!/usr/bin/env python3
"""Seal an explicitly staged public release and produce a deterministic archive.

Stage reviewed source, binaries, builtins and runtime-dependencies first. Never
point this command at a live installation: it packages every file in the root.
"""
import argparse
import gzip
import importlib.util
import json
from pathlib import Path
import stat
import tarfile

spec=importlib.util.spec_from_file_location('installer',Path(__file__).with_name('install.py'))
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)


def seal(root, output):
    if output.exists() or output.is_symlink() or root.is_symlink() or output.resolve().is_relative_to(root.resolve()):
        raise ValueError('NEW_EXTERNAL_ARCHIVE_REQUIRED')
    files={}
    for path in sorted(root.rglob('*')):
        info=path.lstat()
        if path.is_symlink() or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise ValueError('RELEASE_SPECIAL_FILE')
        if path.is_file():
            name=path.relative_to(root).as_posix()
            if name=='release-manifest.json':raise ValueError('RELEASE_ALREADY_SEALED')
            files[name]={'sha256':installer.digest(path),'size':info.st_size,'mode':stat.S_IMODE(info.st_mode)}
    installer.write(root/'release-manifest.json',{'schema':'browser-platform/release-files/v1','files':files})
    installer.verify_tree(root)
    with output.open('xb') as raw, gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as compressed, tarfile.open(fileobj=compressed,mode='w') as tar:
        for path in [root,*sorted(root.rglob('*'))]:
            name='browser-platform-1.0'+('/'+path.relative_to(root).as_posix() if path!=root else '')
            info=tar.gettarinfo(str(path),arcname=name)
            info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0
            if path.is_file():
                with path.open('rb') as data:tar.addfile(info,data)
            else:tar.addfile(info)
    receipt={'archive':output.name,'sha256':installer.digest(output),'bytes':output.stat().st_size,
             'files':len(files),'manifest_sha256':installer.digest(root/'release-manifest.json')}
    installer.write(output.with_name(output.name+'.json'),receipt)
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(seal(a.root,a.output)))
