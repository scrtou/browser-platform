#!/usr/bin/env python3
"""Exercise the real streamed QA browser across client sizes and reconnects.

Linux Chromium uses the Mac key mapping. Native Mac IME, Finder and Trilium
remain explicit manual acceptance items; no user account data is used.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import uuid
import traceback

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session-file', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--origin', required=True)
    parser.add_argument('--host-resolver-rules')
    parser.add_argument('--certificate-spki')
    parser.add_argument('--storage-state', type=Path, help='private Playwright login state for an authenticated QA entry')
    parser.add_argument('--emulate-mac-keyboard', action='store_true')
    args = parser.parse_args()
    report = {'schemaVersion':'browser-platform/client-boundary/v1', 'status':'running',
              'startedAt':datetime.now(timezone.utc).isoformat(), 'clientOS':'Linux',
              'scope':'Chromium client with Mac key mapping; no macOS, native IME or Trilium assertion',
              'viewportChecks':[], 'uploads':[]}
    private = json.loads(args.session_file.read_text())
    session_url = urljoin(args.origin, private['session_url'])
    fixture = 'https://entry.leak.qa.test/client'
    clipboard, drops, routes, keys = [], [], [], []
    frames = [0]
    command_key = 'Meta' if args.emulate_mac_keyboard else 'Control'

    def checkpoint(stage):
        report['stage'] = stage
        (args.output_dir/'client-boundary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print('client_boundary_stage='+stage,flush=True)

    def incoming(message):
        if isinstance(message,bytes): frames[0] += 1
        elif message.startswith('clipboard,'):
            clipboard.append(base64.b64decode(message[10:]).decode('utf-8'))

    launch_args = ['--no-proxy-server']
    if args.host_resolver_rules: launch_args += ['--host-resolver-rules='+args.host_resolver_rules]
    if args.certificate_spki: launch_args += ['--ignore-certificate-errors-spki-list='+args.certificate_spki]
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True,args=launch_args)
            report['clientBrowser'] = browser.version
            assert browser.version == '151.0.7922.34'
            context = browser.new_context(viewport={'width':1920,'height':1080},
                                          storage_state=str(args.storage_state) if args.storage_state else None)
            context.grant_permissions([], origin=args.origin)
            if args.emulate_mac_keyboard:
                context.add_init_script("Object.defineProperty(navigator,'platform',{get:()=> 'MacIntel'});")
            page = context.new_page()
            page.set_default_timeout(15000)
            page.expose_function('qaDrop',lambda value:drops.append(value))
            page.add_init_script("window.addEventListener('drop',e=>qaDrop({trusted:e.isTrusted,files:[...e.dataTransfer.files].map(f=>f.name)}),true)")
            def socket_route(route):
                server = route.connect_to_server(); routes.append((route,server))
                def send(message):
                    if isinstance(message,str) and message.startswith(('kd,','ku,','kr')):
                        keys.append(message)
                    server.send(message)
                route.on_message(send)
                def receive(message): incoming(message); route.send(message)
                server.on_message(receive)
            page.route_web_socket('**/*websocket*',socket_route)
            checkpoint('connect')
            page.goto(session_url,wait_until='domcontentloaded',timeout=40000)
            def wait_frames(before=0):
                for _ in range(160):
                    if frames[0] > before: return
                    page.wait_for_timeout(100)
                raise AssertionError('no fresh video frame')
            wait_frames()
            report['clientAsset'] = page.evaluate("[...document.scripts].map(script=>new URL(script.src||location.href).pathname).find(path=>path.includes('/assets/index-'))")
            clean_url = args.origin + urlsplit(page.url).path
            report['permissions'] = page.evaluate("""async()=>{
                const result={};
                for(const key of ['read','write']) {
                  result[key]=(await navigator.permissions.query({name:'clipboard-'+key})).state;
                  try{if(key==='read')await navigator.clipboard.readText();else await navigator.clipboard.writeText('must fail');result[key+'API']='allowed';}
                  catch(error){result[key+'API']=error.name;}
                }return result;
            }""")
            assert report['permissions'] == {'read':'denied','write':'denied','readAPI':'NotAllowedError','writeAPI':'NotAllowedError'}
            overlay = page.locator('#overlayInput')
            page.wait_for_function('window.webrtcInput?.inputAttached === true')
            def remote(step=None):
                for _ in range(8):
                    before = len(clipboard); overlay.focus(); page.keyboard.press('F9')
                    for _ in range(35):
                        page.wait_for_timeout(100)
                        for value in clipboard[before:]:
                            if value.startswith('BP_CLIENT_REPORT:'):
                                observed = json.loads(value[len('BP_CLIENT_REPORT:'):])
                                if step is None or observed['step'] == step: return observed
                report['recentKeyMessages'] = keys[-180:]
                report['clientInputState'] = page.evaluate('({attached:window.webrtcInput?.inputAttached,keys:window.webrtcInput?._keyDownList,active:document.activeElement?.id})')
                page.screenshot(path=str(args.output_dir/'client-no-report.png'))
                raise AssertionError('no fresh remote fixture report')
            def navigate(url,step):
                overlay.focus(); page.keyboard.press(command_key+'+l'); page.wait_for_timeout(250)
                page.keyboard.type(url,delay=20); page.keyboard.press('Enter')
                page.wait_for_timeout(900)
                return remote(step)
            def map_point(observed,rect):
                env = observed['environment']; box = overlay.bounding_box()
                x = env['position']['x'] + (env['outer']['width']-env['inner']['width'])/2 + rect['x'] + rect['width']/2
                y = env['position']['y'] + env['outer']['height']-env['inner']['height'] + rect['y'] + rect['height']/2
                return box['x']+box['width']*x/env['screen']['width'], box['y']+box['height']*y/env['screen']['height']

            baseline = navigate(fixture,'one')
            report['baseline'] = baseline
            env = baseline['environment']
            assert (env['screen']['width'],env['screen']['height'],env['dpr'],env['language'],env['timezone']) == (1920,1080,1,'zh-TW','Asia/Taipei')
            storage = baseline['storage']; assert storage['localStorage'] and len(set(storage.values())) == 1
            checkpoint('fixed-screen-and-input-coordinates')
            cdp = context.new_cdp_session(page)
            for width,height,dpr in [(1920,1080,1),(1280,720,1),(1000,760,2)]:
                page.set_viewport_size({'width':width,'height':height})
                cdp.send('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':dpr,'mobile':False})
                page.wait_for_timeout(700)
                client = page.evaluate('({width:innerWidth,height:innerHeight,dpr:devicePixelRatio})')
                overlay_box = overlay.bounding_box()
                canvas_box = page.locator('#videoCanvas').bounding_box()
                expected_box = {'x':0,'y':0,'width':width,'height':height}
                assert client == {'width':width,'height':height,'dpr':dpr}
                assert all(abs(overlay_box[key]-value) <= 1 for key,value in expected_box.items()), \
                    'input overlay does not fill the client viewport'
                assert all(abs(canvas_box[key]-value) <= 1 for key,value in expected_box.items()), \
                    'fixed display does not fill the client viewport'
                observed = remote()
                assert observed['environment']['screen'] == env['screen'] and observed['environment']['dpr'] == env['dpr']
                clicks = []
                for rect in observed['targets']:
                    point = map_point(observed,rect); page.mouse.click(*point); page.wait_for_timeout(100)
                    latest = remote()
                    event = latest['coordinates'][-1]
                    assert event['trusted'] and event['target'] == rect['id'], 'input landed on a different target'
                    assert abs(event['clientX']-rect['x']-rect['width']/2) <= 6
                    assert abs(event['clientY']-rect['y']-rect['height']/2) <= 6
                    clicks.append(event)
                report['viewportChecks'].append({'client':client,
                    'displayBounds':{'overlay':overlay_box,'canvas':canvas_box},
                    'remoteScreen':observed['environment']['screen'],'remoteDPR':observed['environment']['dpr'],'clicks':clicks})
                checkpoint('coordinates-'+str(width)+'-'+str(dpr))
            cdp.send('Emulation.clearDeviceMetricsOverride')
            page.set_viewport_size({'width':1920,'height':1080}); page.wait_for_timeout(500)
            observed = remote(); page.mouse.click(*map_point(observed,observed['inputRect']))
            page.keyboard.press(command_key+'+a'); page.keyboard.type('camoufox-',delay=30)
            checkpoint('unicode-input')
            key_start = len(keys)
            page.locator('#keyboard-input-assist').focus(); page.keyboard.insert_text('繁體中文😀𠮷'); page.wait_for_timeout(500)
            observed = remote()
            report['unicodeInput'] = {'value':observed['input'],'events':observed['inputEvents'],
                                      'keyMessages':keys[key_start:],
                                      'path':'Selkies keyboard assist; native OS IME untested'}
            assert observed['input'] == 'camoufox-繁體中文😀𠮷', 'Unicode input differs: '+repr(observed['input'])
            checkpoint('unicode-composition')
            page.mouse.click(*map_point(observed,observed['inputRect']))
            page.keyboard.press(command_key+'+a')
            for key in ['K','E','E','P',':']:
                page.keyboard.press('Shift+'+key)
            page.wait_for_timeout(200)
            assert remote()['input'] == 'KEEP:', 'prefix was not entered before composition'
            overlay.focus()
            page.evaluate("""() => {
              window.qaComposition=[];
              for(const type of ['compositionstart','compositionupdate','compositionend'])
                document.querySelector('#overlayInput').addEventListener(type,event=>qaComposition.push({type,trusted:event.isTrusted,data:event.data}));
            }""")
            for text in ['😀a','😀𠮷']:
                units = len(text.encode('utf-16-le'))//2
                cdp.send('Input.imeSetComposition',{'text':text,'selectionStart':units,'selectionEnd':units})
                page.wait_for_timeout(150)
            cdp.send('Input.insertText',{'text':'😀𠮷'})
            page.wait_for_timeout(400)
            observed = remote()
            report['composition'] = {'value':observed['input'],'events':page.evaluate('window.qaComposition'),
                                     'path':'trusted CDP composition start/updates; CDP commit can be untrusted; native OS IME untested'}
            assert observed['input'] == 'KEEP:😀𠮷', 'composition changed surrounding text: '+repr(observed['input'])
            for kind in ['compositionstart','compositionupdate']:
                assert any(event['type']==kind and event['trusted'] for event in report['composition']['events'])
            assert any(event['type']=='compositionend' for event in report['composition']['events'])
            checkpoint('navigation-tabs-and-storage')
            assert navigate(fixture+'?step=two','two')['storage'] == storage
            page.keyboard.press('Meta+[' if args.emulate_mac_keyboard else 'Alt+Left'); page.wait_for_timeout(500); assert remote('one')['storage'] == storage
            page.keyboard.press('Meta+]' if args.emulate_mac_keyboard else 'Alt+Right'); page.wait_for_timeout(500); assert remote('two')['storage'] == storage
            page.keyboard.press(command_key+'+t'); assert navigate(fixture+'?step=tab','tab')['storage'] == storage
            page.keyboard.press('Control+Shift+Tab'); page.wait_for_timeout(300); assert remote('two')['storage'] == storage
            page.keyboard.press('Control+Tab'); page.wait_for_timeout(300); assert remote('tab')['storage'] == storage
            page.keyboard.press(command_key+'+w'); page.wait_for_timeout(300); assert remote('two')['storage'] == storage
            report['navigation'] = {'back':'pass','forward':'pass','newTab':'pass','switchTab':'pass','closeTestTab':'pass','storageUnchanged':True}
            # Wheel over the page background, outside its text fields.
            page.mouse.move(1550,800); page.mouse.wheel(0,600); page.wait_for_timeout(500)
            assert remote()['scroll']['y'] > 0
            page.keyboard.press('Control+Home'); page.wait_for_timeout(300)
            report['scroll'] = 'pass'
            checkpoint('files-native-picker-and-cdp-drop')
            page.mouse.click(6,540)
            files = page.get_by_role('button',name='Files',exact=True)
            if files.get_attribute('aria-expanded') != 'true': files.click()
            paths = []
            for method in ['button','drop']:
                name = 'bp-r4-'+uuid.uuid4().hex[:12]+'-'+method+'.png'
                path = Path('/tmp')/name
                encoded = page.evaluate("""() => {
                  const canvas=document.createElement('canvas');canvas.width=24;canvas.height=16;
                  const context=canvas.getContext('2d');context.fillStyle='rgb(23,115,202)';context.fillRect(0,0,24,16);
                  return canvas.toDataURL('image/png').split(',')[1];
                }""")
                path.write_bytes(base64.b64decode(encoded))
                paths.append(path)
                report['uploads'].append({'method':method,'name':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size})
            with page.expect_file_chooser() as chosen:
                page.get_by_role('button',name='Upload Files',exact=True).click()
            chosen.value.set_files(str(paths[0])); page.wait_for_timeout(1200)
            box = overlay.bounding_box(); x,y = box['x']+box['width']/2,box['y']+box['height']/2
            data = {'items':[],'files':[str(paths[1])],'dragOperationsMask':1}
            for kind in ['dragEnter','dragOver','drop']:
                cdp.send('Input.dispatchDragEvent',{'type':kind,'x':x,'y':y,'data':data})
            page.wait_for_timeout(1200)
            assert any(item['trusted'] and paths[1].name in item['files'] for item in drops)
            report['dropEvents'] = drops
            report['filesScope'] = 'Linux native file chooser with automated selection; trusted CDP file drag, not Finder'
            checkpoint('connection-loss-and-reconnect')
            before_frames = frames[0]; before_routes = len(routes)
            routes[-1][1].close(code=1012,reason='isolated QA connection loss')
            routes[-1][0].close(code=1012,reason='isolated QA connection loss')
            # A user reloads the stable Session route after a severed transport.
            page.wait_for_timeout(500); page.goto(clean_url,wait_until='domcontentloaded',timeout=30000); wait_frames(before_frames)
            assert len(routes) > before_routes and remote('two')['storage'] == storage
            report['transportReconnect'] = {'newWebSocket':True,'storageUnchanged':True,'path':'severed WebSocket then page reload'}
            context.set_offline(True)
            try: page.reload(wait_until='domcontentloaded',timeout=6000)
            except Exception: pass
            context.set_offline(False); before_frames=frames[0]
            page.goto(clean_url,wait_until='domcontentloaded',timeout=30000); wait_frames(before_frames)
            assert remote('two')['storage'] == storage
            report['offlineReloadRecovery'] = 'pass'
            page.screenshot(path=str(args.output_dir/'client-final.png'))
            report['final'] = remote('two'); report['status']='pass'
            browser.close()
    except Exception as error:
        report['status']='fail'; report['errorType']=type(error).__name__
        # Private logs may contain a token-bearing navigation exception; public
        # output uses only the stable stage and exception type.
        (args.output_dir/'failure.txt').write_text(traceback.format_exc())
        checkpoint('failed-'+report.get('stage','unknown'))
        return 1
    checkpoint('complete')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
