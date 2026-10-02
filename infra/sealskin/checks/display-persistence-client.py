#!/usr/bin/env python3
"""QA-only headless client, authenticates through the real candidate Gateway."""
import json,time
from pathlib import Path
from playwright.sync_api import sync_playwright
from browser_client import Browser
cfg=json.loads(Path('/qa-input.json').read_text());out=Path('/qa-output');rows=[];errors=[]
remote_browser=Browser(cfg['engine']);remote=remote_browser.evaluate
GEOMETRY='({screen:[screen.width,screen.height],outer:[outerWidth,outerHeight],inner:[innerWidth,innerHeight],dpr:devicePixelRatio})'
def record(): (out/(cfg['phase']+'-result.json')).write_text(json.dumps({'cases':rows,'page_errors':errors},indent=2))
def dashboard(page):return next(f for f in page.frames if f.locator('.toggle-handle').count())
def geometry(page,dpr):
 deadline=time.monotonic()+30
 last=None;stable=0
 while time.monotonic()<deadline:
  page.wait_for_timeout(300);value=remote(GEOMETRY)
  stable=stable+1 if last==value else 0;last=value
  if abs(value['dpr']-dpr)<.01 and stable>=3:return value
 (out/'geometry-failed.json').write_text(json.dumps(value));page.screenshot(path=str(out/'geometry-failed.png'));raise AssertionError('SAVED_REMOTE_DPR_NOT_APPLIED')
def enter(browser,dpr):
 ctx=browser.new_context(ignore_https_errors=True,viewport={'width':1280,'height':800},device_scale_factor=dpr)
 c=cfg['cookie'];ctx.add_cookies([{'name':c['Name'],'value':c['Value'],'url':cfg['url'].split('/')[0]+'//'+cfg['url'].split('/')[2]+'/','secure':True,'httpOnly':True,'sameSite':'Lax'}])
 page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(cfg['url'],wait_until='domcontentloaded');page.wait_for_timeout(2500)
 return ctx,page
def input_check(page,value,label):
 remote("document.body.innerHTML='<input id=qa style=\"position:absolute;left:80px;top:30px;width:240px;height:40px\">';true")
 page.wait_for_timeout(800)
 surface=page.locator('#videoCanvas')
 if not surface.count() or not surface.is_visible():surface=page.locator('#stream')
 box=surface.bounding_box();assert box and box['width']>0
 page.mouse.click(box['x']+120*box['width']/value['screen'][0],box['y']+(value['outer'][1]-value['inner'][1]+50)*box['height']/value['screen'][1])
 deadline=time.monotonic()+6
 while not remote("document.activeElement.id==='qa'"):
  assert time.monotonic()<deadline,'PERSISTED_DPI_POINTER_MISSED';page.wait_for_timeout(50)
 page.keyboard.type(label,delay=40);page.wait_for_timeout(500)
 assert remote("document.querySelector('#qa').value")==label,'PERSISTED_DPI_KEYBOARD_FAILED'
 page.screenshot(path=str(out/(label+'.png')))
def select(page,dpi):
 f=dashboard(page);f.locator('.toggle-handle').click();h=f.locator('[aria-controls=screen-settings-content]')
 if h.get_attribute('aria-expanded')!='true':h.click()
 f.locator('#uiScalingSelect').select_option(str(dpi));f.wait_for_timeout(1500)
 (out/'selection-diagnostics.json').write_text(json.dumps({'url':f.url,'helper':f.evaluate('typeof window.__bpDisplayScaling'),'status':f.locator('#bp-scaling-status').all_text_contents(),'scripts':f.locator('script[src]').evaluate_all('(nodes)=>nodes.map(n=>n.src)')},indent=2))
 f.wait_for_function("document.querySelector('#bp-scaling-status')?.textContent.includes('已保存')")
 f.locator('.toggle-handle').click()
def setting(page):return page.evaluate("async()=> (await fetch(location.pathname+'_browser-platform/display')).json()")
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/opt/chromix/chrome',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
  if cfg['phase']=='save':
   ctx,page=enter(browser,1);geometry(page,1);select(page,144)
   value=geometry(page,1.5);assert setting(page)['percent']==150
   input_check(page,value,'saved150');rows.append({'case':'remote-ui-save','remote':value,'input':True});record()
   page.reload(wait_until='domcontentloaded');value=geometry(page,1.5);input_check(page,value,'reload150');rows.append({'case':'refresh','remote':value,'input':True});record();ctx.close()
   ctx,page=enter(browser,2);value=geometry(page,1.5);input_check(page,value,'client2saved150');rows.append({'case':'fresh-client-dpr2','remote':value,'input':True});record()
   # A competing management-style update changes the revision. The existing
   # dashboard must report conflict and leave both saved/visible DPI untouched.
   current=setting(page)
   response=page.evaluate("async c=>{let r=await fetch(location.pathname+'_browser-platform/display',{method:'POST',headers:{'Content-Type':'application/json','X-Browser-Platform-CSRF':c.csrf},body:JSON.stringify({percent:200,revision:c.revision})});return r.status}",current);assert response==200
   f=dashboard(page);f.locator('.toggle-handle').click();h=f.locator('[aria-controls=screen-settings-content]')
   if h.get_attribute('aria-expanded')!='true':h.click()
   f.locator('#uiScalingSelect').select_option('96');f.wait_for_function("document.querySelector('#bp-scaling-status')?.textContent.includes('请刷新')")
   assert setting(page)['percent']==200;assert remote(GEOMETRY)['dpr']==1.5
   rows.append({'case':'revision-conflict','server_percent':200,'remote_dpr':1.5});record()
   page.reload(wait_until='domcontentloaded');value=geometry(page,2);input_check(page,value,'conflictrefresh200');rows.append({'case':'refresh-after-conflict','remote':value,'input':True});record();ctx.close()
  else:
   ctx,page=enter(browser,1);value=geometry(page,2);assert setting(page)['percent']==200
   input_check(page,value,'gatewayrestart200');rows.append({'case':'gateway-restart-new-client-dpr1','remote':value,'input':True});record()
   current=setting(page)
   response=page.evaluate("async c=>{let r=await fetch(location.pathname+'_browser-platform/display',{method:'POST',headers:{'Content-Type':'application/json','X-Browser-Platform-CSRF':c.csrf},body:JSON.stringify({percent:0,revision:c.revision})});return r.status}",current);assert response==200;ctx.close()
   for client_dpr in [2,1]:
    ctx,page=enter(browser,client_dpr);value=geometry(page,client_dpr);assert setting(page)['percent']==0
    input_check(page,value,'resetdefault'+str(client_dpr));rows.append({'case':'reset-client-default','client_dpr':client_dpr,'remote':value,'input':True});record();ctx.close()
  browser.close()
 assert not errors,'CLIENT_JAVASCRIPT_ERROR'
 print('PASS',cfg['phase'],len(rows),'real display cases')
except BaseException:
 try:
  (out/'failure-diagnostics.json').write_text(json.dumps([{'url':f.url,'helper':f.evaluate("typeof window.__bpDisplayScaling"),'status':f.locator('#bp-scaling-status').all_text_contents(),'scripts':f.locator('script[src]').evaluate_all('(nodes)=>nodes.map(n=>n.src)')} for f in page.frames],indent=2))
  page.screenshot(path=str(out/'failed.png'))
 except Exception:pass
 raise
finally:remote_browser.close();record()
