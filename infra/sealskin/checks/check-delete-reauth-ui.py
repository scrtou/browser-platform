#!/usr/bin/env python3
"""Go-rendered deletion UI on isolated loopback; actual auth covered by Go tests."""
import argparse,json,re
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs
from playwright.sync_api import sync_playwright,expect
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);root=p.parse_args().root
fixture=json.loads((root/'qa/runtime/r6y-management-delete-ui/combinations.json').read_text())
state={'authorized':False,'deleted':False,'posts':0,'mutations':0,'referenced':False}
output=root/'ui-check';output.mkdir(exist_ok=True)
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  body=fixture['body']
  if state['deleted']:
   body=re.sub(r'(<table class="jobs-table management-table">[\s\S]*?<tbody>)\s*<tr>[\s\S]*?</tr>',r'\1',body,count=1)
  body=body.encode();self.send_response(200)
  for k,v in fixture['headers'].items():self.send_header(k,v)
  self.end_headers();self.wfile.write(body)
 def do_POST(self):
  fields=parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode(),keep_blank_values=True);state['posts']+=1
  assert 'csrf' in fields
  code=200
  if self.path=='/auth/reauth':
   state['authorized']=fields.get('password')==['synthetic-password']
   code=200 if state['authorized'] else 401;data={'done':state['authorized'],'message':'密码不正确'}
  else:
   assert self.path.startswith('/manage/environment-jobs/') and fields.get('confirm')==['delete']
   if not state['authorized']:code=403;data={'done':False,'reauth':True}
   elif state['referenced']:code=409;data={'done':False,'message':'被浏览器引用，无法删除'}
   else:state['deleted']=True;state['mutations']+=1;data={'done':True,'message':'已删除'}
  raw=json.dumps(data).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(raw)
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
origin='http://127.0.0.1:'+str(server.server_port);errors=[]
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
  for width in [1280,768,390]:
   state.update(authorized=False,deleted=False,referenced=False)
   context=browser.new_context(viewport={'width':width,'height':900});page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(origin);before=page.locator('.jobs-table tbody tr').count();assert before
   page.locator('.jobs-table .delete-dialog-trigger').first.click();deletion=page.locator('dialog.danger-dialog[open]');deletion.locator('[name=confirm]').check();deletion.locator('[type=submit]').click()
   auth=page.locator('#reauth-dialog');expect(auth).to_be_visible()
   auth.get_by_role('button',name='取消',exact=True).click();expect(auth).not_to_be_visible();assert not state['deleted']
   expect(deletion.locator('.delete-result')).to_contain_text('尚未删除')
   deletion.locator('[type=submit]').click();expect(auth).to_be_visible()
   auth.locator('[name=password]').fill('wrong');auth.locator('[type=submit]').click();expect(auth.locator('[role=status]')).to_have_text('密码不正确');assert not state['deleted']
   for _ in range(8):page.keyboard.press('Tab');assert auth.evaluate('(e)=>e.contains(document.activeElement)')
   page.screenshot(path=str(output/('reauth-error-'+str(width)+'.png')))
   auth.locator('[name=password]').fill('synthetic-password');auth.locator('[type=submit]').click()
   expect(page.locator('.jobs-table tbody tr')).to_have_count(before-1)
   page.reload();expect(page.locator('.jobs-table tbody tr')).to_have_count(before-1)
   state.update(deleted=False,referenced=True)
   page.reload();page.locator('.jobs-table .delete-dialog-trigger').first.click();deletion=page.locator('dialog.danger-dialog[open]');deletion.locator('[name=confirm]').check();deletion.locator('[type=submit]').click();expect(deletion.locator('.delete-result')).to_contain_text('被浏览器引用');assert not state['deleted']
   assert page.evaluate('document.documentElement.scrollWidth')<=width+1
   context.close()
  browser.close()
 assert not errors,errors
 assert state['mutations']==3
 (output/'result.json').write_text(json.dumps({'result':'PASS','widths':[1280,768,390],'password_retry':True,'cancel_preserves':True,'reference_protection':True,'refresh_absent':True,'keyboard':True,'mutations':3,'posts':state['posts'],'errors':errors},indent=2))
 print('PASS delete reauth dialog: 3 widths, cancel/wrong/correct/reference/refresh/keyboard')
finally:server.shutdown();server.server_close();thread.join()
