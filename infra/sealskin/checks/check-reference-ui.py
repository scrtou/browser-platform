#!/usr/bin/env python3
"""Exercise Go-rendered UI fixtures over isolated loopback HTTP."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit
from playwright.sync_api import sync_playwright


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    root=a.root.resolve();output=root/'ui-check';output.mkdir(mode=0o700)
    fixtures={p.stem:json.loads(p.read_bytes()) for p in (root/'ui-auth').glob('*.json')}
    for name in ('fingerprints','displays','combinations','network','accounts'):
        fixtures[name]=json.loads((root/'qa/runtime/r6y-management-delete-ui'/(name+'.json')).read_bytes())
    for name in ('empty-combinations','empty-displays','empty-fingerprints'):
        fixtures[name]=json.loads((root/'qa/runtime/r6v-fingerprint-data-ui'/(name+'.json')).read_bytes())
    for name in ('empty','unavailable','network-unavailable'):
        fixtures['create-'+name]=json.loads((root/'qa/runtime/r6u-linked-create-ui'/(name+'.json')).read_bytes())
    fixtures['network-running']=json.loads((root/'qa/runtime/r6x-network-select-ui/running.json').read_bytes())
    posts=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            parsed=urlsplit(self.path);query=parse_qs(parsed.query)
            name=query.get('fixture',[None])[0]
            if not name:
                name={'/':'home-admin','/auth/login':'login','/auth/reauth':'reauth','/auth/password':'password'}.get(parsed.path)
            if not name:
                tab=query.get('tab',['browsers'])[0]
                name=query.get('section',['fingerprints'])[0] if tab=='fingerprint-data' else tab
            value=fixtures.get(name,fixtures['browsers']);body=value['body'].encode()
            self.send_response(200)
            for key,val in value['headers'].items():self.send_header(key,val)
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_POST(self):
            fields=parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode(),keep_blank_values=True)
            posts.append({'path':self.path,'fields':fields})
            target=urlsplit(self.headers.get('Referer','/manage/'))
            self.send_response(303);self.send_header('Location',target.path+('?' + target.query if target.query else ''));self.send_header('Content-Length','0');self.end_headers()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    origin='http://127.0.0.1:'+str(server.server_port);results=[];errors=[]
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
            for width in (1280,768,390):
                context=browser.new_context(viewport={'width':width,'height':900})
                page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                for name in fixtures:
                    page.goto(origin+'/?fixture='+name)
                    assert page.evaluate('document.documentElement.scrollWidth')<=width+1,(name,width,'overflow')
                    if name in ('login','home-admin','browsers','network','accounts','fingerprints','displays','combinations'):
                        page.screenshot(path=str(output/(name+'-'+str(width)+'.png')))
                    results.append({'case':name,'width':width,'layout':'PASS'})
                for name,dialog_id,trigger_id in [('browsers','create-browser-dialog','open-cb-dialog'),('network','create-network-dialog','open-np-dialog'),('accounts','create-account-dialog','open-na-dialog')]:
                    page.goto(origin+'/?fixture='+name)
                    dialog=page.locator('#'+dialog_id);trigger=page.locator('#'+trigger_id)
                    assert not dialog.is_visible()
                    trigger.focus();page.keyboard.press('Enter')
                    assert dialog.is_visible() and dialog.get_attribute('open') is not None
                    assert dialog.evaluate('(e)=>e.contains(document.activeElement)')
                    for _ in range(25):
                        page.keyboard.press('Tab')
                        assert dialog.evaluate('(e)=>e.contains(document.activeElement)'),'focus escaped modal'
                    page.screenshot(path=str(output/(name+'-modal-'+str(width)+'.png')))
                    page.keyboard.press('Escape');assert not dialog.is_visible()
                    assert trigger.evaluate('(e)=>document.activeElement===e')
                    trigger.click();dialog.locator('.dialog-cancel-btn').click();assert not dialog.is_visible()
                    search=page.locator('.search-input');search.fill('no-match-reference-qa')
                    rows=page.locator('.browser-card, .network-profile-table tbody tr, .accounts-table tbody tr')
                    assert rows.count()>0 and rows.locator('visible=true').count()==0
                    assert '找到 0 条' in page.locator('.filter-status').inner_text()
                    search.fill('')
                    if not all(rows.nth(i).is_visible() for i in range(rows.count())):
                        details=rows.evaluate_all('(rows)=>rows.map(e=>({tag:e.tagName,hidden:e.hidden,display:getComputedStyle(e).display,visibility:getComputedStyle(e).visibility,rect:[e.getBoundingClientRect().width,e.getBoundingClientRect().height]}))')
                        raise AssertionError((name,width,'filter restore',details,search.input_value(),page.evaluate('document.activeElement.outerHTML.slice(0,200)')))
                # The actual linked engine/fingerprint selector remains functional.
                page.goto(origin+'/?fixture=browsers');page.locator('#open-cb-dialog').click()
                for engine in ('camoufox','chromix','firefox'):
                    page.locator('#cb-browser-template').select_option(engine)
                    options=page.locator('#cb-fingerprint-template option').evaluate_all('(rows)=>rows.filter(o=>!o.hidden&&!o.disabled&&o.value).map(o=>o.value)')
                    assert options and all(engine in value for value in options),options
                # Login submission retains the exact credential field contract.
                page.goto(origin+'/?fixture=login');page.locator('[name=username]').fill('qa-user');page.locator('[name=password]').fill('qa-password-example')
                page.get_by_role('button',name='登录',exact=True).click();page.wait_for_load_state()
                assert set(posts[-1]['fields'])=={'csrf','next','username','password'}
                context.close()
                plain=browser.new_context(viewport={'width':width,'height':900},java_script_enabled=False);page=plain.new_page()
                for name,dialog_id in [('browsers','create-browser-dialog'),('network','create-network-dialog'),('accounts','create-account-dialog')]:
                    page.goto(origin+'/?fixture='+name)
                    assert page.locator('#'+dialog_id).is_visible(),('fallback hidden',name)
                    assert not page.locator('.search-box').is_visible()
                    assert page.evaluate('document.documentElement.scrollWidth')<=width+1
                # Preserve mandatory deletion confirmation and real POST/303.
                for name in ('network','accounts','fingerprints','displays','combinations'):
                    page.goto(origin+'/?fixture='+name)
                    detail=page.locator('.delete-control').first;detail.locator('summary').click();form=detail.locator('form')
                    count=len(posts);form.locator('button').click();assert len(posts)==count
                    form.locator('[name=confirm]').check();form.locator('button').click();page.wait_for_load_state()
                    assert len(posts)==count+1 and posts[-1]['fields']['confirm']==['delete'] and 'csrf' in posts[-1]['fields']
                plain.close()
            assert not errors,errors
            browser.close()
        (output/'result.json').write_text(json.dumps({'result':'PASS','layouts':results,'posts':len(posts),'script_errors':errors,'modal_keyboard':True,'search':True,'linked_selects':True,'no_js_forms':True,'deletion_confirmation':True},indent=2)+'\n')
        print('PASS',len(results),'layouts;',len(posts),'real submissions; modal/keyboard/search/linked selection/no-JS contracts')
    finally:
        server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()
