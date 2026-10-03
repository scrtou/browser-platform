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
    fixtures={p.stem:json.loads(p.read_bytes()) for p in (root/'qa/runtime/r6aa-auth').glob('*.json')}
    for name in ('fingerprints','displays','combinations','network','accounts'):
        fixtures[name]=json.loads((root/'qa/runtime/r6y-management-delete-ui'/(name+'.json')).read_bytes())
    for name in ('empty-combinations','empty-displays','empty-fingerprints'):
        fixtures[name]=json.loads((root/'qa/runtime/r6v-fingerprint-data-ui'/(name+'.json')).read_bytes())
    for name in ('empty','unavailable','network-unavailable'):
        fixtures['create-'+name]=json.loads((root/'qa/runtime/r6u-linked-create-ui'/(name+'.json')).read_bytes())
    fixtures['network-running']=json.loads((root/'qa/runtime/r6x-network-select-ui/running.json').read_bytes())
    for path in (root/'qa/runtime/r6v-fingerprint-data-ui').glob('*.json'):
        fixtures[path.stem]=json.loads(path.read_bytes())
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
                # R6AB unified sidebar, readonly detail dialogs and keyboard behavior.
                page.goto(origin+'/')
                assert page.locator('.browser-table tbody tr').count()==2
                assert page.locator('.card').count()==0
                assert page.locator('.trigger-details-btn:visible').count()==2
                for i in range(2):
                    trigger=page.locator('.trigger-details-btn').nth(i)
                    trigger.click();dialog=page.locator('dialog[open]')
                    assert dialog.count()==1
                    for label in ['健康','网络','浏览器模板','指纹模板','显示模板','采样时间']:
                        assert label in dialog.inner_text()
                    if i==0:
                        for value in ['offline · PROFILE_STOPPED','proxy_required','camoufox-linux-v152','env-tw-camoufox-r10','x11-selkies-1920x1080','2026-10-02T02:28:28Z']:
                            assert value in dialog.inner_text(),value
                    if i==1:
                        assert '未知（采样已过期）' in dialog.inner_text()
                        assert 'healthy' not in dialog.inner_text()
                    for _ in range(8):
                        page.keyboard.press('Tab');assert dialog.evaluate('(e)=>e.contains(document.activeElement)')
                    page.keyboard.press('Shift+Tab');assert dialog.evaluate('(e)=>e.contains(document.activeElement)')
                    if i==0:page.screenshot(path=str(output/('home-details-'+str(width)+'.png')))
                    page.keyboard.press('Escape');assert page.locator('dialog[open]').count()==0
                    assert trigger.evaluate('(e)=>document.activeElement===e')
                    trigger.click();page.locator('dialog[open] .dialog-close-btn').first.click()
                    assert trigger.evaluate('(e)=>document.activeElement===e')
                for name in ['home-admin','browsers','network','accounts','fingerprints','displays','combinations']:
                    page.goto(origin+'/?fixture='+name)
                    sidebar=page.locator('.app-sidebar');toggle=page.locator('.sidebar-toggle-btn')
                    # Closed sidebar must leave the full main area within viewport.
                    if width>768:toggle.click()
                    assert not sidebar.is_visible()
                    box=page.locator('.app-main-wrapper').bounding_box()
                    assert box['x']>=0 and box['x']+box['width']<=width+1,(name,width,box)
                    toggle.focus();page.keyboard.press('Enter')
                    assert sidebar.is_visible()
                    assert toggle.get_attribute('aria-expanded')=='true'
                    if width<=768:
                        for _ in range(18):
                            page.keyboard.press('Tab');assert sidebar.evaluate('(e)=>e.contains(document.activeElement)')
                    menu=page.locator('#manage-menu');before=page.url
                    if menu.get_attribute('open') is not None:menu.locator('summary').click()
                    menu.locator('summary').click()
                    assert page.url==before
                    assert 2 <= menu.locator('a').count() <= 4
                    if name=='home-admin':
                        assert menu.locator('a').count()==4
                        page.screenshot(path=str(output/('home-navigation-'+str(width)+'.png')))
                    if width<=768:
                        page.keyboard.press('Escape');assert not sidebar.is_visible()
                        assert toggle.evaluate('(e)=>document.activeElement===e')
                # Traverse real secondary GET URLs and native browser history.
                page.goto(origin+'/')
                if width<=768:page.locator('.sidebar-toggle-btn').click()
                page.locator('#manage-menu summary').click()
                page.locator('#manage-menu a[href="/manage/?tab=network"]').click()
                assert page.url==origin+'/manage/?tab=network'
                assert page.locator('.app-title').inner_text()=='网络代理'
                page.go_back();assert page.url==origin+'/'
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
                    rows=page.locator('.section-browsers .table-container > table > tbody > tr, .network-profile-table > tbody > tr, .accounts-table > tbody > tr')
                    assert rows.count()>0 and rows.locator('visible=true').count()==0
                    assert '找到 0 条' in page.locator('.filter-status').inner_text()
                    search.fill('')
                    if not all(rows.nth(i).is_visible() for i in range(rows.count())):
                        details=rows.evaluate_all('(rows)=>rows.map(e=>({tag:e.tagName,hidden:e.hidden,display:getComputedStyle(e).display,visibility:getComputedStyle(e).visibility,rect:[e.getBoundingClientRect().width,e.getBoundingClientRect().height]}))')
                        raise AssertionError((name,width,'filter restore',details,search.input_value(),page.evaluate('document.activeElement.outerHTML.slice(0,200)')))
                # R6AC all management resources remain real table rows.
                for name in ['browsers','network','accounts','fingerprints','displays','combinations']:
                    page.goto(origin+'/?fixture='+name)
                    tables=page.locator('table.management-table')
                    assert tables.count()>0,(name,'missing management table')
                    assert page.locator('article.data-card:visible, article.browser-card:visible').count()==0
                    assert tables.locator('thead th').count()>0 and tables.locator('tbody tr').count()>0
                    assert page.evaluate('document.documentElement.scrollWidth')<=width+1
                    if name in ['fingerprints','displays','combinations']:
                        create=page.locator('details.list-create')
                        assert create.count()==1 and create.get_attribute('open') is None
                        create.locator('summary').click();assert page.locator('dialog.record-dialog[open] form').is_visible()
                        page.keyboard.press('Escape')
                    ids=page.locator('[id]').evaluate_all('(els)=>els.map(e=>e.id)')
                    assert len(ids)==len(set(ids)),(name,'duplicate control IDs')
                for name in ['browsers','network','accounts']:
                    page.goto(origin+'/?fixture='+name)
                    triggers=page.locator('details.record-details > summary')
                    assert triggers.count()>0
                    trigger=triggers.first;trigger.focus();page.keyboard.press('Enter')
                    dialog=page.locator('dialog.record-dialog[open]')
                    assert dialog.count()==1 and dialog.get_attribute('aria-labelledby')
                    assert dialog.locator('form').count()>0
                    dialog.locator('details').evaluate_all('(els)=>els.forEach(e=>e.open=true)')
                    controls=dialog.locator('button:not([disabled]), a[href], input:not([disabled]):not([type=hidden]), select:not([disabled]), textarea:not([disabled]), summary').locator('visible=true')
                    controls.last.focus();page.keyboard.press('Tab');assert controls.first.evaluate('(e)=>e===document.activeElement')
                    page.keyboard.press('Shift+Tab');assert controls.last.evaluate('(e)=>e===document.activeElement')
                    for _ in range(12):
                        page.keyboard.press('Tab');assert dialog.evaluate('(e)=>e.contains(document.activeElement)')
                    page.screenshot(path=str(output/(name+'-record-'+str(width)+'.png')))
                    page.keyboard.press('Escape');assert page.locator('dialog.record-dialog[open]').count()==0
                    assert trigger.evaluate('(e)=>e===document.activeElement')
                    trigger.click();page.locator('dialog.record-dialog[open] .dialog-close').click()
                    search=page.locator('.search-input');search.fill('no-match-row-details')
                    assert search.input_value()=='no-match-row-details'
                    assert page.locator('table.management-table > tbody > tr:visible').count()==0
                    search.fill('');assert triggers.first.is_visible()
                # Submit moved forms over loopback: exact owner/action and confirmation survive.
                for name in ['network','accounts']:
                    page.goto(origin+'/?fixture='+name)
                    page.locator('details.record-details > summary').first.click()
                    dialog=page.locator('dialog.record-dialog[open]')
                    if name=='network':
                        detail=dialog.locator('.delete-control').first;detail.locator('summary').click()
                        form=detail.locator('form');count=len(posts);form.locator('button').click();assert len(posts)==count
                        form.locator('[name=confirm]').check();form.locator('button').click()
                        page.wait_for_load_state();assert posts[-1]['fields']['action']==['delete'] and posts[-1]['fields']['id']==['corp']
                    else:
                        detail=dialog.locator('.grants-form').locator('..');detail.locator('summary').click()
                        detail.locator('button').click();page.wait_for_load_state()
                        assert posts[-1]['path']=='/manage/accounts/alice' and posts[-1]['fields']['action']==['grants']
                # R6AD all seven fingerprint operations open dedicated dialogs.
                operations=[('fingerprints','details.list-create','/manage/fingerprint-templates'),('displays','details.list-create','/manage/display-templates'),('combinations','details.list-create','/manage/template-combinations'),('fingerprints','.fingerprint-table .delete-control','/manage/fingerprint-templates/'),('displays','.display-table .delete-control','/manage/display-templates/'),('combinations','.jobs-table .delete-control','/manage/environment-jobs/'),('combinations','.combinations-table .delete-control','/manage/template-combinations/')]
                for name,selector,action in operations:
                    page.goto(origin+'/?fixture='+name)
                    trigger=page.locator(selector+' > summary').first
                    count=len(posts);trigger.focus();page.keyboard.press('Enter')
                    dialog=page.locator('dialog.record-dialog[open]')
                    assert dialog.count()==1 and dialog.locator('form').count()==1
                    assert dialog.get_attribute('aria-labelledby')
                    form=dialog.locator('form');assert form.get_attribute('action').startswith(action)
                    title=dialog.locator('.dialog-title').inner_text()
                    assert trigger.inner_text() in title
                    assert not page.locator(selector).first.get_attribute('open')
                    if 'delete-control' in selector:
                        row=trigger.locator('xpath=ancestor::tr').first
                        assert row.locator('td').first.locator('strong, .job-id').first.inner_text().strip() in title
                        assert 'danger-dialog' in dialog.get_attribute('class')
                    controls=dialog.locator('button:not([disabled]), input:not([type=hidden]):not([disabled]), select:not([disabled])').locator('visible=true')
                    controls.last.focus();page.keyboard.press('Tab');assert controls.first.evaluate('(e)=>document.activeElement===e')
                    page.keyboard.press('Shift+Tab');assert controls.last.evaluate('(e)=>document.activeElement===e')
                    page.keyboard.press('Escape');assert not dialog.is_visible();assert trigger.evaluate('(e)=>document.activeElement===e')
                    assert len(posts)==count
                    trigger.click();dialog=page.locator('dialog.record-dialog[open]')
                    dialog.get_by_role('button',name='取消',exact=True).click();assert not dialog.is_visible()
                    assert len(posts)==count and trigger.evaluate('(e)=>document.activeElement===e')
                    trigger.click();dialog=page.locator('dialog.record-dialog[open]');form=dialog.locator('form')
                    if 'delete-control' in selector:
                        form.locator('button[type=submit]').click();assert len(posts)==count
                        form.locator('[name=confirm]').check()
                    elif name=='fingerprints':
                        form.locator('[name=label]').fill('QA dialog fingerprint');form.locator('[name=locale]').fill('en-US');form.locator('[name=languages]').fill('en-US,en');form.locator('[name=timezone]').fill('UTC')
                    elif name=='displays':form.locator('[name=label]').fill('QA dialog display')
                    else:
                        for key in ['fingerprint_id','browser_template_id','display_id']:form.locator('[name='+key+']').select_option(index=1)
                    page.screenshot(path=str(output/('fingerprint-operation-'+name+'-'+str(operations.index((name,selector,action)))+'-'+str(width)+'.png')))
                    form.locator('button[type=submit]').click();page.wait_for_load_state()
                    assert len(posts)==count+1 and posts[-1]['path'].startswith(action)
                    assert 'csrf' in posts[-1]['fields']
                    if 'delete-control' in selector:assert posts[-1]['fields']['confirm']==['delete']
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
                for name in ['browsers','network','accounts']:
                    page.goto(origin+'/?fixture='+name)
                    record=page.locator('details.record-details').first
                    record.locator(':scope > summary').click()
                    assert record.locator('.record-content').is_visible()
                    assert page.locator('dialog.record-dialog').count()==0
                page.goto(origin+'/')
                assert not page.locator('.trigger-details-btn').first.is_visible()
                detail=page.locator('.details-fallback').first
                detail.locator('summary').click();assert detail.locator('.fallback-details-body').is_visible()
                if width<=768:page.locator('.sidebar-toggle-btn').click()
                page.locator('#manage-menu summary').click()
                assert page.locator('#manage-menu a').count()==4
                page.locator('#manage-menu a[href="/manage/?tab=network"]').click()
                assert page.locator('.app-title').inner_text()=='网络代理'
                # Preserve mandatory deletion confirmation and real POST/303.
                for name in ('network','accounts','fingerprints','displays','combinations'):
                    page.goto(origin+'/?fixture='+name)
                    detail=page.locator('.delete-control').first
                    detail.evaluate('(el)=>{let p=el.parentElement;while(p){if(p.tagName==="DETAILS")p.open=true;p=p.parentElement}}')
                    detail.locator('summary').click();form=detail.locator('form')
                    count=len(posts);form.locator('button').click();assert len(posts)==count
                    form.locator('[name=confirm]').check();form.locator('button').click();page.wait_for_load_state()
                    assert len(posts)==count+1 and posts[-1]['fields']['confirm']==['delete'] and 'csrf' in posts[-1]['fields']
                plain.close()
            assert not errors,errors
            browser.close()
        (output/'result.json').write_text(json.dumps({'result':'PASS','layouts':results,'posts':len(posts),'script_errors':errors,'modal_keyboard':True,'search':True,'linked_selects':True,'no_js_forms':True,'deletion_confirmation':True,'workspace_sidebar':True,'workspace_details':True,'history':True,'management_lists':True,'record_dialogs':True,'moved_forms':True,'fingerprint_dialogs':True},indent=2)+'\n')
        (root/'workspace-ui').mkdir(exist_ok=True)
        (root/'workspace-ui/result.json').write_text((output/'result.json').read_text())
        print('PASS',len(results),'layouts;',len(posts),'real submissions; modal/keyboard/search/linked selection/no-JS contracts')
    finally:
        server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()
