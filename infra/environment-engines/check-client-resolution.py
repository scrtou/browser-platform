#!/usr/bin/env python3
"""Execute the shipped JS resolution paths before/after the bounded patch."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess

p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--image',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
spec=importlib.util.spec_from_file_location('patcher',Path(__file__).resolve().parents[1]/'browser-runtime/install-client-resolution.py');patcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(patcher)
old=a.source.read_bytes();new=patcher.patch(old)
node=['docker','run','--rm','-i','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--entrypoint','/opt/camoufox-python/lib/python3.14/site-packages/playwright/driver/node',a.image]
subprocess.run(node+['--input-type=module','--check'],input=new,check=True,capture_output=True)

def fragments(raw):
    s=raw.decode()
    getter=s[s.index('getWindowResolution(){'):s.index('resize(){this._windowMath()')]
    start=s.index('let ae=gt(Z.width*x),we=gt(Z.height*x);');end=s.index('_.initialClientHeight=we',start)+len('_.initialClientHeight=we')
    initial=s[start:end]
    start=s.index('let X,Z,ae=1;window.is_manual_resolution_mode?');end=s.index(';const we=`${X}x${Z}`',start)
    send=s[start:end]+';return[X,Z];'
    start=s.index('const we=_.getWindowResolution();');end=s.index('Xi(Re,qe),Za(Re,qe)',start)+len('Xi(Re,qe),Za(Re,qe)')
    return {'getter':getter,'initial':initial,'send':send,'resize':s[start:end]}

script=r'''
const assert=require('assert');
const versions=VERSIONS;
const cases=[[1280,800,1],[1600,900,1],[1024,768,2],[2560,1440,2],[3840,2160,2],[777,555,1.25]];
let oldFailures=0;const rows=[];
for(const [name,s] of Object.entries(versions)) for(const [width,height,dpr] of cases) for(const aligned of [false,true]) {
 const window={innerWidth:width,innerHeight:height,devicePixelRatio:dpr,is_manual_resolution_mode:false};
 const document={body:{offsetWidth:width,offsetHeight:height}};
 const ht=false,gt=n=>Math.floor(n/(aligned?16:2))*(aligned?16:2);
 const probe=new Function('window','document','return new(class{'+s.getter+'})()')(window,document);
 const first=new Function('gt','Z','x','let _={};'+s.initial+';return[_.initialClientWidth,_.initialClientHeight]')(gt,{width,height},dpr);
 const send=new Function('window','ht','gt','_','x',s.send);
 let resized;const Xi=(w,h)=>resized=send(window,ht,gt,w,h),Za=()=>{};
 new Function('_','gt','ht','window','Xi','Za',s.resize)(probe,gt,ht,window,Xi,Za);
 const expected=[gt(width*dpr),gt(height*dpr)];
 const correct=JSON.stringify(first)===JSON.stringify(expected)&&JSON.stringify(resized)===JSON.stringify(expected);
 if(name==='patched')assert(correct,JSON.stringify({width,height,dpr,aligned,first,resized,expected}));
 else if(!correct)oldFailures++;
 rows.push({name,width,height,dpr,aligned,first,resized,expected,correct});
 // Manual mode retains its prior independent 4080 cap and no DPR conversion.
 window.is_manual_resolution_mode=true;
 assert.deepStrictEqual(send(window,ht,gt,5000,3000),[4080,gt(3000)]);
}
assert(oldFailures>0,'old code must reproduce a DPR/limit regression');
console.log(JSON.stringify({result:'PASS',oldFailures,cases:rows}));
'''.replace('VERSIONS',json.dumps({'original':fragments(old),'patched':fragments(new)}))
r=subprocess.run(node+['-'],input=script.encode(),capture_output=True,check=True)
a.output.write_bytes(r.stdout);a.output.chmod(0o600)
print('PASS actual JS syntax, initial/resize/manual dimensions; old-code failures reproduced')
