#!/usr/bin/env python3
"""Exercise real Go-rendered sensitive forms and exact replay on isolated HTTP."""
import argparse,json
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs,urlsplit
from playwright.sync_api import sync_playwright,expect
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);root=p.parse_args().root
fixtures={}
for name in ['network','accounts']:
 fixtures[name]=json.loads((root/'qa/runtime/r6y-management-delete-ui'/(name+'.json')).read_text())
fixtures['browsers']=json.loads((root/'qa/runtime/r6aa-auth/browsers.json').read_text())
state={'authorized':False,'first':None,'posts':0,'applied':0,'fixture':'browsers','reject':False};errors=[];results=[]
output=root/'ui-check';output.mkdir(exist_ok=True)
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  name=parse_qs(urlsplit(self.path).query).get('fixture',[state['fixture']])[0];state['fixture']=name
  f=fixtures[name];self.send_response(200)
  for k,v in f['headers'].items():self.send_header(k,v)
  self.end_headers();self.wfile.write(f['body'].encode())
 def do_POST(self):
  fields=parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode(),keep_blank_values=True);state['posts']+=1
  assert 'csrf' in fields
  if self.path=='/auth/reauth':
   state['authorized']=fields.get('password')==['synthetic-password'];code=200 if state['authorized'] else 401;data={'done':state['authorized'],'message':'密码不正确'}
  elif state['reject']:
   self.send_response(403);self.send_header('Content-Type','text/plain');self.end_headers();self.wfile.write(b'Forbidden');return
  elif not state['authorized']:
   state['first']=(self.path,fields);code=403;data={'done':False,'reauth':True}
  else:
   assert state['first']==(self.path,fields),'original form changed after password confirmation'
   state['applied']+=1
   if state['applied']%2:
    self.send_response(303);self.send_header('Location','/manage/?fixture='+state['fixture']+'&notice=updated');self.end_headers();return
   code=200;data={'done':True,'message':'已完成'}
  self.send_response(code);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps(data).encode())
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever,daemon=True);thread.start();origin='http://127.0.0.1:'+str(server.server_port)
cases=[('network','.network-profile-create-form'),('network','form:has(input[name=action][value=disable])'),('network','form:has(input[name=action][value=revoke])'),('network','form:has(input[name=action][value=delete])'),('accounts','#create-account-dialog form'),('accounts','.pwd-reset-form'),('accounts','form:has(input[name=action][value=disable])'),('accounts','form:has(input[name=action][value=role])'),('accounts','.delete-form'),('browsers','form:has(input[name=action][value=network_select])'),('browsers','.template-apply-form'),('browsers','form:has(input[name=action][value=delete])')]
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
  for width in [1280,768,390]:
   ctx=browser.new_context(viewport={'width':width,'height':900});page=ctx.new_page();page.on('pageerror',lambda e:(errors.append(str(e)),print('SCRIPT ERROR',str(e),flush=True)))
   for name,selector in cases:
    print('CASE',width,name,selector,flush=True);state.update(authorized=False,first=None,reject=False);page.goto(origin+'/?fixture='+name)
    form=page.locator(selector).first;assert form.count(),(name,selector)
    form.evaluate('''f=>{let p=f.parentElement;while(p){if(p.tagName==='DETAILS')p.open=true;if(p.getAttribute('role')==='tabpanel'){const tab=document.querySelector('[aria-controls="'+p.id+'"]');if(tab)tab.click()}if(p.tagName==='DIALOG')p.showModal();p=p.parentElement}}''')
    if selector=='#create-account-dialog form':form.locator('[name=role][value=admin]').check()
    for control in form.locator('input:not([type=hidden]),select').all():
     if not control.is_visible() or control.is_disabled():continue
     typ=control.get_attribute('type')
     if typ=='radio':continue
     if typ=='checkbox':control.check()
     elif control.evaluate('e=>e.tagName')=='SELECT':
      if not control.input_value():
       values=control.locator('option').evaluate_all('(els)=>els.filter(e=>e.value&&!e.disabled&&!e.hidden).map(e=>e.value)');assert values;control.select_option(values[0])
     elif not control.input_value():
      value='qa-original-key'
      if typ=='password':value='synthetic-new-password'
      elif typ=='url':value='https://example.test/'
      elif typ=='number':value=control.get_attribute('min') or '1080'
      control.fill(value)
    assert form.evaluate('f=>f.reportValidity()'),(name,selector)
    before=state['applied'];form.locator('[type=submit]').first.click();auth=page.locator('#reauth-dialog');expect(auth).to_be_visible()
    if selector=='.network-profile-create-form':
     auth.locator('[data-reauth-cancel]').click();expect(auth).not_to_be_visible();assert state['applied']==before
     expect(form.locator('.delete-result')).to_contain_text('尚未执行')
     form.locator('[type=submit]').first.click();expect(auth).to_be_visible()
     auth.locator('[name=password]').fill('wrong');auth.locator('[type=submit]').click();expect(auth.locator('[role=status]')).to_have_text('密码不正确')
     page.screenshot(path=str(output/('network-reauth-'+str(width)+'.png')))
    auth.locator('[name=password]').fill('synthetic-password');auth.locator('[type=submit]').click()
    expect(auth).not_to_be_visible();page.wait_for_load_state()
    expect(page.locator('.delete-result')).to_have_count(0)
    assert state['applied']==before+1,(name,selector)
    results.append({'width':width,'fixture':name,'form':selector,'exact_replay':True})
   # An ordinary 403 must not prompt or replay.
   state.update(reject=True,authorized=False);page.goto(origin+'/?fixture=network')
   form=page.locator('form:has(input[name=action][value=disable])').first
   form.evaluate("f=>{let p=f.parentElement;while(p){if(p.tagName==='DETAILS')p.open=true;if(p.getAttribute('role')==='tabpanel')document.querySelector('[aria-controls=\"'+p.id+'\"]').click();if(p.tagName==='DIALOG')p.showModal();p=p.parentElement}}")
   form.locator('[name=idempotency_key]').fill('qa-forbidden');count=state['posts'];form.locator('[type=submit]').click();expect(form.locator('.delete-result')).to_contain_text('HTTP 403');assert state['posts']==count+1;expect(page.locator('#reauth-dialog')).not_to_be_visible()
   # A still-valid confirmation executes directly, without a second prompt.
   state.update(reject=False,authorized=True)
   state['first']=form.evaluate("f=>[new URL(f.getAttribute('action'),location.href).pathname,Array.from(new FormData(f)).reduce((o,[k,v])=>{(o[k]??=[]).push(v);return o},{})]")
   state['first']=tuple(state['first'])
   before=state['applied'];count=state['posts'];form.locator('[type=submit]').click()
   expect(page.locator('.delete-result')).to_have_count(0)
   assert state['applied']==before+1 and state['posts']==count+1
   expect(page.locator('#reauth-dialog')).not_to_be_visible()
   ctx.close()
  browser.close()
 assert not errors,errors
 (output/'result.json').write_text(json.dumps({'result':'PASS','cases':results,'posts':state['posts'],'applied':state['applied'],'cancel':True,'wrong_password':True,'ordinary_403_no_retry':True,'authorized_direct':True,'errors':errors},indent=2))
 print('PASS',len(results),'sensitive forms with exact replay, cancellation and no retry on ordinary 403')
finally:server.shutdown();server.server_close();thread.join()
