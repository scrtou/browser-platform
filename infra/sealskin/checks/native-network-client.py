#!/usr/bin/env python3
"""QA-only normal-browser CDP/BiDi transport, never installed in runtime images."""
import json,subprocess,sys,time,socket

# Exercise ICE while the caller records outbound packet metadata. Chromix
# retains the API but its accepted launcher disables non-proxied UDP.
WEBRTC_PROBE = """(async()=>{const pc=new RTCPeerConnection({iceServers:[{urls:'stun:stun-'+qa.nonce+'.leak.qa.test:3478'}]});const candidates=[];pc.onicecandidate=e=>{if(e.candidate)candidates.push(e.candidate.candidate)};try{pc.createDataChannel('qa');await pc.setLocalDescription(await pc.createOffer());await new Promise(r=>setTimeout(r,2500));return candidates}finally{pc.close()}})()"""

class NativeDesktop:
    def __init__(self,worker,engine):
        assert engine in ('camoufox','chromix','firefox')
        self.worker,self.engine=worker,engine
    def command(self,action,value):
        result=subprocess.run(['docker','exec','-i','--user','1000',self.worker,'/opt/camoufox-python/bin/python','/qa-native/native-network-client.py','--inside'],input=json.dumps({'engine':self.engine,'action':action,'value':value}),text=True,capture_output=True,timeout=90)
        if result.returncode:raise RuntimeError('NATIVE_BROWSER_COMMAND_FAILED: '+result.stderr[-500:])
        return json.loads(result.stdout)
    def evaluate(self,expression):return self.command('evaluate',expression)
    def navigate(self,url):return self.command('navigate',url)
    def title(self):return self.evaluate('document.title')
    def available_title(self):return self.title()
    def assert_webrtc_confined(self):
        assert self.engine=='chromix'
        result=self.evaluate(WEBRTC_PROBE)
        assert result==[], 'WEBRTC_UNPROXIED_CANDIDATE'
        return result

def process_identity_source(engine):
    """Observe the one native browser main process, excluding renderers.

    The pinned Chromix build rewrites argv as a space-delimited process title.
    Other engines retain NUL-separated argv. Only fixed QA flags are parsed.
    """
    assert engine in ('camoufox','chromix','firefox')
    return """import json
from pathlib import Path
out=[]
for process in Path('/proc').glob('[0-9]*'):
 try:
  args=process.joinpath('cmdline').read_bytes().split(bytes([0]))
  if ENGINE=='chromix':args=b' '.join(args).split()
  if b'--remote-debugging-port=9222' in args and not any(a.startswith(b'--type=') for a in args):
   out.append([int(process.name),process.joinpath('stat').read_text().split()[21]])
 except (OSError,IndexError):pass
assert len(out)==1, 'NATIVE_MAIN_PROCESS_NOT_UNIQUE'
print(json.dumps(out))
""".replace('ENGINE',repr(engine))

def inside():
    from browser_client import Browser
    request=json.load(sys.stdin)
    # Wait only for a read-only readiness observation. Never replay an action
    # after a command might have reached the browser.
    deadline=time.monotonic()+40
    while True:
        try:
            connection=socket.create_connection(('127.0.0.1',9222),.5);connection.close();break
        except OSError:
            if time.monotonic()>=deadline:raise
            time.sleep(.2)
    browser=Browser(request['engine'])
    try:
        if request['action']=='navigate':
            if request['engine']=='chromix':
                browser.counter+=1;identifier=browser.counter
                browser.ws.send_json({'id':identifier,'method':'Page.navigate','params':{'url':request['value']}})
                while True:
                    message=browser.ws.receive_json()
                    if message.get('id')==identifier:
                        assert 'error' not in message and 'errorText' not in message.get('result',{});break
            else:browser.bidi.command('browsingContext.navigate',{'context':browser.context,'url':request['value'],'wait':'complete'})
            deadline=time.monotonic()+20
            while time.monotonic()<deadline:
                try:
                    if browser.evaluate('location.href')==request['value'] and browser.evaluate('document.readyState')=='complete':print('true');return
                except Exception:pass
                time.sleep(.1)
            raise RuntimeError('NATIVE_NAVIGATION_NOT_READY')
        assert request['action']=='evaluate';print(json.dumps(browser.evaluate(request['value'])))
    finally:browser.close()
if __name__=='__main__':
    assert sys.argv[1:]==['--inside'];inside()
