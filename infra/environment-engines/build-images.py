#!/usr/bin/env python3
"""Build two thin, offline revisions on verified local engine images."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
BASES={'camoufox':('browser-platform/camoufox:r10-managed-desktop-candidate','sha256:9a128663eb05d1b7a64a9519b597b745ba2b9be76af7b6649755a2a50d168306'),
       'chromix':('browser-platform/chromix:154-scaling-r1','sha256:819a225630907a72466a2c67e23cc6261e0efcd790744948dd13183f3f4bd0ac'),
       'firefox':('browser-platform/camoufox:r10-managed-desktop-candidate','sha256:9a128663eb05d1b7a64a9519b597b745ba2b9be76af7b6649755a2a50d168306')}
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--engine',choices=tuple(BASES),action='append');a=p.parse_args();os.umask(0o077)
    root=a.output.resolve();root.mkdir(mode=0o700);results={}
    for engine,(tag,image) in BASES.items():
        if a.engine and engine not in a.engine:continue
        assert subprocess.check_output(['docker','image','inspect',tag,'--format','{{.Id}}'],text=True).strip()==image
        ctx=root/engine;ctx.mkdir(mode=0o700)
        files=['display_config.py','Dockerfile.'+engine]+(['environment.py','install-resolution-limit.py'] if engine=='camoufox' else ['artifact.py','launcher.py'] if engine=='chromix' else ['artifact.py','install-resolution-limit.py','firefox_launcher.py','firefox_shutdown.py','browser-platform.cfg','browser-platform-autoconfig.js','firefox-entrypoint','firefox-autostart'])
        external={'launcher.py':HERE.parent/'chromix/launcher.py','environment.py':HERE.parent/'camoufox/environment.py','install-resolution-limit.py':HERE.parent/'chromix/install-resolution-limit.py'}
        for f in files:shutil.copy2(external.get(f,HERE/f),ctx/f)
        inputs={f:hashlib.sha256((ctx/f).read_bytes()).hexdigest() for f in files}
        fingerprint=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:16]
        target='browser-platform/'+engine+':custom-'+fingerprint
        existing=subprocess.run(['docker','image','inspect',target],capture_output=True,text=True)
        if existing.returncode==0:
            found=json.loads(existing.stdout)[0]
            assert found['Config']['Labels'].get('io.browser-platform.custom-input-sha256')==fingerprint
            (root/(engine+'.log')).write_text('Reused immutable image with matched input label.\n')
        else:
            with (root/(engine+'.log')).open('w') as log:
                r=subprocess.run(['docker','build','--network','none','--pull=false','--build-arg','BASE_IMAGE='+tag,'--build-arg','INPUT_SHA256='+fingerprint,'-f',str(ctx/('Dockerfile.'+engine)),'-t',target,str(ctx)],stdout=log,stderr=subprocess.STDOUT)
                if r.returncode:raise SystemExit(r.returncode)
        value=json.loads(subprocess.check_output(['docker','image','inspect',target]))[0]
        base=json.loads(subprocess.check_output(['docker','image','inspect',image]))[0]
        assert value['RootFS']['Layers'][:len(base['RootFS']['Layers'])]==base['RootFS']['Layers']
        results[engine]={'image':value['Id'],'base':image,'inputs':inputs}
    (root/'builds.json').write_text(json.dumps(results,indent=2)+'\n');print({e:v['image'] for e,v in results.items()})
if __name__=='__main__':main()
