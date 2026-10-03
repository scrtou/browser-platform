#!/usr/bin/env python3
"""QA-only client, invoked inside an isolated Worker with credentials on stdin."""
import json
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

exec(Path('/opt/chromix-qa/check-bidi.py').read_text().split('class BiDi:',1)[0])

def remote(expression):
    target=next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9222/json')) if t['type']=='page')
    socket=WebSocket('127.0.0.1',9222,urlsplit(target['webSocketDebuggerUrl']).path)
    socket.send_json({'id':1,'method':'Runtime.evaluate','params':{'expression':expression,'returnByValue':True}})
    try:
        while True:
            r=socket.receive_json()
            if r.get('id')==1:
                assert 'exceptionDetails' not in r['result']
                return r['result']['result'].get('value')
    finally:socket.socket.close()

config=json.load(sys.stdin)
output=Path('/qa-output')
rows=[]
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/opt/chromix/chrome',headless=True,chromium_sandbox=True,args=['--disable-setuid-sandbox','--disable-dev-shm-usage'])
    context=browser.new_context(http_credentials={'username':config['user'],'password':config['password']},viewport={'width':1280,'height':800},device_scale_factor=1)
    page=context.new_page()
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:3000/'+config['sid']+'/',wait_until='domcontentloaded')
    for width,height in [(1280,800),(1600,900),(800,600),(1280,800)]:
        page.set_viewport_size({'width':width,'height':height})
        deadline=time.monotonic()+25
        value=None
        while time.monotonic()<deadline:
            page.wait_for_timeout(500)
            value=remote('({screen:[screen.width,screen.height],outer:[outerWidth,outerHeight],inner:[innerWidth,innerHeight],dpr:devicePixelRatio})')
            if value['screen']==[width,height]:break
        page.screenshot(path=str(output/f'client-{width}-{height}.png'))
        rows.append({'client':[width,height],'remote':value})
        (output/'client-resize.json').write_text(json.dumps({'samples':rows,'page_errors':errors},indent=2))
        assert value['screen']==[width,height], 'REMOTE_SCREEN_DID_NOT_FOLLOW_CLIENT'
        remote("document.body.innerHTML='<input id=qa style=\"position:absolute;left:80px;top:80px;width:240px;height:40px\">';true")
        page.mouse.click(120,value['outer'][1]-value['inner'][1]+100)
        # Mouse and key events traverse asynchronous transport/desktop focus.
        # Observe remote focus before sending text; never repeat lost text.
        deadline=time.monotonic()+5
        while not remote("document.activeElement.id==='qa'"):
            assert time.monotonic()<deadline, 'RESIZED_POINTER_MISSED_INPUT'
            page.wait_for_timeout(50)
        page.keyboard.type('resize-check',delay=30)
        page.wait_for_timeout(500)
        assert remote("document.querySelector('#qa').value")=='resize-check', 'RESIZED_INPUT_COORDINATES_FAILED'
        rows[-1]['click_and_type']=True
    context.close()
    for width,height,dpr in [(1024,768,1),(1024,768,2),(2560,1440,2)]:
        scale=min(1,3840/(width*dpr),2160/(height*dpr))
        expected=[int(width*dpr*scale)//2*2,int(height*dpr*scale)//2*2]
        expected_dpr=dpr if config.get('system_dpi') else 1
        expected_css=[round(n/expected_dpr) for n in expected]
        context=browser.new_context(http_credentials={'username':config['user'],'password':config['password']},viewport={'width':width,'height':height},device_scale_factor=dpr)
        page=context.new_page()
        page.goto('http://127.0.0.1:3000/'+config['sid']+'/',wait_until='domcontentloaded')
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            page.wait_for_timeout(500)
            value=remote('({screen:[screen.width,screen.height],outer:[outerWidth,outerHeight],inner:[innerWidth,innerHeight],dpr:devicePixelRatio})')
            if value['screen']==expected_css and value['dpr']==expected_dpr:break
        rows.append({'reconnect':True,'client':[width,height],'client_dpr':dpr,'remote':value,'expected':expected})
        (output/'client-resize.json').write_text(json.dumps({'samples':rows,'page_errors':errors},indent=2))
        assert value['screen']==expected_css and value['dpr']==expected_dpr, 'RECONNECT_OR_CLIENT_DPR_FAILED'
        remote("document.body.innerHTML='<input id=qa style=\"position:absolute;left:80px;top:80px;width:240px;height:40px\">';true")
        page.wait_for_timeout(500)
        page.screenshot(path=str(output/f'reconnect-{width}-{height}-{dpr}.png'))
        surface=page.locator('#videoCanvas')
        if surface.count()==0 or not surface.is_visible():surface=page.locator('#stream')
        box=surface.bounding_box()
        rows[-1]['surface']=box
        assert box and box['width']>0 and box['height']>0
        page.mouse.click(box['x']+120*box['width']/expected_css[0],box['y']+(value['outer'][1]-value['inner'][1]+100)*box['height']/expected_css[1])
        deadline=time.monotonic()+5
        while not remote("document.activeElement.id==='qa'"):
            assert time.monotonic()<deadline, 'RECONNECT_POINTER_MISSED_INPUT'
            page.wait_for_timeout(50)
        page.keyboard.type('reconnect-check',delay=30)
        page.wait_for_timeout(500)
        assert remote("document.querySelector('#qa').value")=='reconnect-check', 'RECONNECT_INPUT_FAILED'
        rows[-1]['click_and_type']=True
        (output/'client-resize.json').write_text(json.dumps({'samples':rows,'page_errors':errors},indent=2))
        context.close()
    if config.get('system_dpi'):
        context=browser.new_context(http_credentials={'username':config['user'],'password':config['password']},viewport={'width':1280,'height':800},device_scale_factor=1)
        page=context.new_page()
        page.goto('http://127.0.0.1:3000/'+config['sid']+'/',wait_until='domcontentloaded')
        page.wait_for_timeout(2500)
        scaling=[]
        dashboard=next(f for f in page.frames if f.locator('.toggle-handle').count())
        for dpi,width,height in [(96,1280,800),(144,1280,800),(192,1280,800),(144,1600,900),(96,1280,800)]:
            page.set_viewport_size({'width':width,'height':height})
            dashboard.locator('.toggle-handle').click()
            header=dashboard.locator('[aria-controls=screen-settings-content]')
            if header.get_attribute('aria-expanded') != 'true':header.click()
            dashboard.locator('#uiScalingSelect').select_option(str(dpi))
            dashboard.locator('.toggle-handle').click()
            deadline=time.monotonic()+20
            while time.monotonic()<deadline:
                page.wait_for_timeout(300)
                value=remote('({screen:[screen.width,screen.height],outer:[outerWidth,outerHeight],inner:[innerWidth,innerHeight],dpr:devicePixelRatio})')
                if value['dpr']==dpi/96 and abs(value['screen'][0]*value['dpr']-width)<=1:break
            assert value['dpr']==dpi/96 and abs(value['screen'][0]*value['dpr']-width)<=1, 'UI_SCALING_NOT_APPLIED'
            remote("document.body.innerHTML='<input id=qa style=\"position:absolute;left:80px;top:30px;width:240px;height:40px\">';true")
            page.wait_for_timeout(500)
            surface=page.locator('#videoCanvas')
            if surface.count()==0 or not surface.is_visible():surface=page.locator('#stream')
            box=surface.bounding_box()
            page.mouse.click(box['x']+120*value['dpr']*box['width']/width,box['y']+(value['outer'][1]-value['inner'][1]+50)*value['dpr']*box['height']/height)
            deadline=time.monotonic()+5
            while not remote("document.activeElement.id==='qa'"):
                assert time.monotonic()<deadline, 'SCALING_POINTER_MISSED'
                page.wait_for_timeout(50)
            page.keyboard.type('scaling-check',delay=30)
            page.wait_for_timeout(300)
            assert remote("document.querySelector('#qa').value")=='scaling-check'
            page.screenshot(path=str(output/f'scaling-{dpi}-{width}.png'))
            scaling.append({'dpi':dpi,'client':[width,height],'remote':value,'click_and_type':True})
            (output/'client-scaling.json').write_text(json.dumps({'samples':scaling},indent=2))
        context.close()
    browser.close()
print('PASS real Selkies client window resize')
