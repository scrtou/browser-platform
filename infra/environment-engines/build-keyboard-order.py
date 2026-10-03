#!/usr/bin/env python3
"""Build an offline keyboard-order layer on each exact generator image."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--targets',required=True,type=Path);p.add_argument('--output',required=True,type=Path);args=p.parse_args();os.umask(0o077)
    output=args.output.resolve();output.mkdir(mode=0o700)
    registry=json.loads(args.targets.read_bytes());results={}
    for ident,target in registry['targets'].items():
        base=target['image'];engine=target['engine']
        actual=json.loads(subprocess.check_output(['docker','image','inspect',base]))[0]
        assert actual['Id']==base and actual['Config']['Labels']['io.browser-platform.browser-engine']==engine
        context=output/engine;context.mkdir(mode=0o700)
        source=ROOT/'browser-runtime/install-keyboard-order.py';shutil.copy2(source,context/source.name)
        helper=ROOT/'browser-runtime/keyboard_subprocess.py';shutil.copy2(helper,context/helper.name)
        dockerfile='ARG BASE_IMAGE\nFROM ${BASE_IMAGE}\nARG INPUT_SHA256\nCOPY install-keyboard-order.py keyboard_subprocess.py /tmp/\nRUN python3 /tmp/install-keyboard-order.py && rm /tmp/install-keyboard-order.py /tmp/keyboard_subprocess.py\nLABEL io.browser-platform.keyboard-order-version="1" io.browser-platform.keyboard-order-sha256="${INPUT_SHA256}"\n'
        (context/'Dockerfile').write_text(dockerfile)
        inputs={'base':base,'patch_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'helper_sha256':hashlib.sha256(helper.read_bytes()).hexdigest(),'dockerfile_sha256':hashlib.sha256(dockerfile.encode()).hexdigest()}
        digest=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()
        base_tag='browser-platform/'+engine+':keyboard-order-base-'+base[7:19];subprocess.run(['docker','tag',base,base_tag],check=True)
        tag='browser-platform/'+engine+':keyboard-order-'+digest[:16]
        with (output/(engine+'.log')).open('w') as log:subprocess.run(['docker','build','--network','none','--pull=false','--build-arg','BASE_IMAGE='+base_tag,'--build-arg','INPUT_SHA256='+digest,'-t',tag,str(context)],stdout=log,stderr=subprocess.STDOUT,check=True)
        revised=json.loads(subprocess.check_output(['docker','image','inspect',tag]))[0]
        assert revised['RootFS']['Layers'][:len(actual['RootFS']['Layers'])]==actual['RootFS']['Layers']
        assert revised['Config']['Labels']['io.browser-platform.keyboard-order-sha256']==digest
        results[ident]={'base':base,'image':revised['Id'],'inputs':inputs,'tag':tag};target['image']=revised['Id']
    (output/'builds.json').write_text(json.dumps(results,indent=2)+'\n');(output/'native-targets.json').write_text(json.dumps(registry,indent=2)+'\n')
    print(json.dumps({k:v['image'] for k,v in results.items()}))

if __name__=='__main__':main()
