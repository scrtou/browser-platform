"""QA-only CDP/BiDi observation; never installed in a Worker image."""
import json
import urllib.request
from urllib.parse import urlsplit
from check_bidi import WebSocket,BiDi

class Browser:
    def __init__(self,engine):
        self.engine=engine;self.counter=0
        if engine=='chromix':
            target=next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9222/json',timeout=5)) if t['type']=='page')
            self.ws=WebSocket('127.0.0.1',9222,urlsplit(target['webSocketDebuggerUrl']).path)
        else:
            self.ws=WebSocket('127.0.0.1',9222);self.bidi=BiDi(self.ws);self.bidi.command('session.new',{'capabilities':{}})
            self.context=self.bidi.command('browsingContext.getTree',{})['contexts'][0]['context']
    def evaluate(self,expression):
        code='(async()=>JSON.stringify(await eval('+json.dumps(expression)+')))()'
        if self.engine!='chromix':return json.loads(self.bidi.evaluate(self.context,code))
        self.counter+=1;self.ws.send_json({'id':self.counter,'method':'Runtime.evaluate','params':{'expression':code,'awaitPromise':True,'returnByValue':True}})
        while True:
            r=self.ws.receive_json()
            if r.get('id')==self.counter:
                assert 'error' not in r and 'exceptionDetails' not in r['result'],r
                return json.loads(r['result']['result']['value'])
    def close(self):
        try:
            if self.engine!='chromix':self.bidi.command('session.end',{})
        finally:self.ws.socket.close()
