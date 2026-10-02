#!/usr/bin/env python3
"""Read browser APIs and persistent stores through QA-only local debugging."""
import argparse
import json
from pathlib import Path
import socket
import time
import urllib.request
from urllib.parse import urlsplit
from check_bidi import WebSocket,BiDi

p=argparse.ArgumentParser();p.add_argument('--role',required=True);p.add_argument('--iteration',type=int,required=True);a=p.parse_args()
spec=json.loads(Path('/run/browser-platform/environment.json').read_bytes());engine='camoufox' if 'spec' in spec else 'chromix' if '/chromix-' in spec['schemaVersion'] else 'firefox'
if engine=='camoufox':
    source=spec;spec=dict(source['spec']);screen=spec['screen'];spec['screen']={**screen,'dpr':'system' if screen.get('mode')=='auto' else 1}
chromix=engine=='chromix'
from browser_client import Browser
client=Browser(engine);evaluate=client.evaluate
for _ in range(60):
    try:
        if not chromix:
            contexts=client.bidi.command('browsingContext.getTree',{})['contexts']
            if contexts:client.context=next((c['context'] for c in contexts if c.get('url','').startswith('https://example.com')),contexts[0]['context'])
        if evaluate('document.title')=='Example Domain':break
    except RuntimeError as error:
        if str(error)!='script.evaluate failed: no such frame':raise
    time.sleep(.5)
else:raise AssertionError('NATIVE_QA_HTTPS_FAILED')
assert evaluate('location.href').startswith('https://example.com/')
root=Path(__file__).parent
storage=(root/'storage.js').read_text();marker='native-home-'+a.role
before=evaluate('('+storage+')({operation:"read"})')
expected={k:marker for k in ('cookie','localStorage','indexedDB')}
assert before==({k:None for k in expected} if a.iteration==0 else expected),('storage-before',before)
assert evaluate('('+storage+')('+json.dumps({'operation':'write','value':marker})+')')==expected
observe=(root/'observe.js').read_text()
# Allow voices to finish initializing, then the report must match on all replays.
time.sleep(1)
voice_count=len(source['resolvedConfig']['voices']) if engine=='camoufox' else 0
observed=evaluate('('+observe+')('+json.dumps({'expectedVoiceCount':voice_count})+')')
assert observed['voicesReady'] is True,'NATIVE_QA_VOICES_NOT_READY'
for key,value in [('locale',spec['locale']),('languages',spec['languages']),('timezone',spec['timezone'])]:
    assert observed[key]==value,(key,observed[key],value)
if spec['screen'].get('mode')!='auto':
    assert observed['deviceScaleFactor']==1
    assert observed['screen']['width']==spec['screen']['width'] and observed['screen']['height']==spec['screen']['height'],('screen',observed['screen'])
    assert observed['window']['outerWidth']==spec['window']['width'] and observed['window']['outerHeight']==spec['window']['height'],('window',observed['window'])
else:
    assert observed['deviceScaleFactor']>0 and observed['screen']['width']>0 and observed['screen']['height']>0
assert observed['platform']=='Linux x86_64'
# Native Firefox disables WebRTC; Chromium restricts non-proxy UDP via its engine policy.
if not chromix:assert observed['webrtcType']=='undefined'
network={}
for label,address in [('ipv4',('1.1.1.1',443)),('ipv6',('2606:4700:4700::1111',443))]:
    try:
        s=socket.create_connection(address,timeout=2);s.close();raise AssertionError('DIRECT_'+label)
    except OSError:network[label]='blocked'
# Install a fixture on the already verified HTTPS origin for real X11 input.
geometry=evaluate("""(()=>{document.body.innerHTML='<input id="input" style="position:absolute;left:80px;top:100px;width:300px">';
document.querySelector('#input').oninput=e=>document.title='typed:'+e.target.value;
const points=[[20,20],[innerWidth-70,20],[innerWidth-70,innerHeight-60]];
points.forEach(([x,y],i)=>{let b=document.createElement('button');b.style=`position:absolute;left:${x}px;top:${y}px;width:50px;height:40px`;b.innerText='hit'+i;b.onclick=()=>document.title='hit'+i;document.body.appendChild(b)});
return {points:points.map(([x,y])=>[x+25,y+20]),inner:[innerWidth,innerHeight]};})()""")
print(json.dumps({'role':a.role,'iteration':a.iteration,'observed':observed,'network':network,'stores':expected,'geometry':geometry}));client.close()
