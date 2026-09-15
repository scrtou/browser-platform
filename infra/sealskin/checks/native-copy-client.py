"""Native remote Firefox copy -> denied-API Chromium clipboard.

The copy shortcut is a real CDP platform editing command with a Meta modifier.
It tests the Mac Selkies keyboard branch on Linux; actual Trilium/macOS remains
a separate acceptance check. No production browser or clipboard is accessed.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import traceback
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

parser=argparse.ArgumentParser()
parser.add_argument('--session-file',type=Path,required=True)
parser.add_argument('--output-dir',type=Path,required=True)
parser.add_argument('--emulate-mac-keyboard',action='store_true')
parser.add_argument('--origin', default='https://mysession.azhen.de')
parser.add_argument('--host-resolver-rules')
parser.add_argument('--certificate-spki')
args=parser.parse_args()
session_url=urljoin(args.origin,json.loads(args.session_file.read_text())['session_url'])
client_args=[]
if args.host_resolver_rules: client_args += ['--host-resolver-rules='+args.host_resolver_rules, '--no-proxy-server']
if args.certificate_spki: client_args += ['--ignore-certificate-errors-spki-list='+args.certificate_spki]
report={'status':'running','startedAt':datetime.now(timezone.utc).isoformat(),
        'clientOS':'Linux; MacIntel branch and native platform Copy command; actual Mac Trilium requires user validation'}

def checkpoint(stage):
    report['stage']=stage
    (args.output_dir/'native-copy.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('native_copy_stage='+stage,flush=True)

try:
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=client_args)
        report['clientBrowser']=browser.version
        context=browser.new_context(viewport={'width':1920,'height':1080})
        context.add_init_script("Object.defineProperty(navigator,'platform',{get:()=> 'MacIntel'});")
        context.grant_permissions([],origin=args.origin)
        context.grant_permissions(['clipboard-read','clipboard-write'],origin='https://clipboard-seed.test')
        helper=context.new_page()
        helper.route('https://clipboard-seed.test/',lambda r:r.fulfill(content_type='text/html',body='<textarea id="local"></textarea>'))
        helper.goto('https://clipboard-seed.test/')
        page=context.new_page()
        page.set_default_timeout(12000)
        counts={'video':0,'remoteCopyKeys':0,'altDowns':0}
        gate={'hold':False,'held':[]}
        routes=[]
        native=[]
        page.expose_function('recordNativeCopy',lambda item:native.append(item))
        page.add_init_script("""window.addEventListener('copy',e=>window.recordNativeCopy({
            trusted:e.isTrusted,target:e.target?.id,active:navigator.userActivation.isActive
        }),true);""")

        def route_socket(route):
            routes.append(route)
            server=route.connect_to_server()
            def client(message):
                if message=='kd,99':counts['remoteCopyKeys']+=1
                if message in ['kd,65513','kd,65514']:counts['altDowns']+=1
                server.send(message)
            def incoming(message):
                if isinstance(message,bytes):counts['video']+=1
                if isinstance(message,str) and message.startswith(('clipboard,','clipboard_')) and gate['hold']:
                    gate['held'].append(message);return
                route.send(message)
            route.on_message(client)
            server.on_message(incoming)
        page.route_web_socket('**/*websockets*',route_socket)
        checkpoint('connect')
        page.goto(session_url,wait_until='domcontentloaded',timeout=30000)
        for _ in range(200):
            if counts['video']:break
            page.wait_for_timeout(100)
        assert counts['video']
        report['permissions']=page.evaluate("""async()=>{
            const out={};for(const name of ['read','write']){
                out[name]=(await navigator.permissions.query({name:'clipboard-'+name})).state;
                try{if(name==='read')await navigator.clipboard.readText();else await navigator.clipboard.writeText('must fail');out[name+'API']='allowed';}
                catch(e){out[name+'API']=e.name;}
            }return out;
        }""")
        assert report['permissions']=={'read':'denied','readAPI':'NotAllowedError','write':'denied','writeAPI':'NotAllowedError'}
        page.locator('#overlayInput').focus()
        page.keyboard.press('Control+l')
        page.keyboard.type('file:///tmp/browser-platform-native-copy.html',delay=1)
        page.keyboard.press('Enter')
        page.wait_for_timeout(1200)
        page.mouse.click(6,540)
        toggle=page.locator('[aria-controls="clipboard-content"]')
        if toggle.get_attribute('aria-expanded')!='true':toggle.click()
        field=page.locator('#dashboardClipboardTextarea')
        overlay=page.locator('#overlayInput')
        status=page.locator('#browser-platform-paste-status')
        cdp=context.new_cdp_session(page)
        sample_index=-1

        def prepare():
            global sample_index
            sample_index+=1
            page.bring_to_front();overlay.focus()
            # The manual panel sends its current value on blur. Let that test
            # setup transfer settle before the fixture establishes its baseline.
            page.wait_for_timeout(650)
            page.keyboard.press('F8')
            baseline='BP_COPY_BASELINE_'+str(sample_index)
            try:
                page.wait_for_function('(x)=>document.querySelector("#dashboardClipboardTextarea").value===x',arg=baseline)
            except Exception:
                report['fixtureBaselineFailure']={'expected':baseline,'actualPrefix':field.input_value()[:64]}
                raise
            expected='遠端中文'*100000+'\nlarge-end-😀' if sample_index==1 else '遠端原生複製 '+str(sample_index)+'\n中文、emoji 📋\nsecond line'
            return baseline,expected

        def seed_local(value='LOCAL_MUST_STAY_UNCHANGED'):
            helper.bring_to_front();helper.evaluate('(s)=>navigator.clipboard.writeText(s)',value)
            page.bring_to_front();overlay.focus()

        def copy_shortcut():
            alt_before=counts['altDowns']
            cdp.send('Input.dispatchKeyEvent',{'type':'rawKeyDown','key':'Meta','code':'MetaLeft','modifiers':4,'windowsVirtualKeyCode':91})
            cdp.send('Input.dispatchKeyEvent',{'type':'rawKeyDown','key':'c','code':'KeyC','modifiers':4,'windowsVirtualKeyCode':67,'commands':['copy']})
            cdp.send('Input.dispatchKeyEvent',{'type':'keyUp','key':'c','code':'KeyC','modifiers':4,'windowsVirtualKeyCode':67})
            cdp.send('Input.dispatchKeyEvent',{'type':'keyUp','key':'Meta','code':'MetaLeft','modifiers':0,'windowsVirtualKeyCode':91})
            assert counts['altDowns']==alt_before,'copy sent a remote Alt key'

        def native_edit_copy():
            # A native editing command creates a trusted Copy event without a
            # DOM keydown, as Electron's Edit menu can do. No ClipboardEvent is
            # fabricated. User activation is explicit for this isolated action.
            cdp.send('Runtime.evaluate',{'expression':'document.execCommand("copy")','userGesture':True})

        def wait_status(value,timeout=12000):
            page.wait_for_function('(s)=>document.querySelector("#browser-platform-paste-status")?.dataset.status===s',arg=value,timeout=timeout)

        def local_clipboard():
            helper.bring_to_front()
            return helper.evaluate('navigator.clipboard.readText()')

        def flush():
            gate['hold']=False
            for message in gate['held']:routes[-1].send(message)
            gate['held']=[]

        checkpoint('native-small-text')
        _,expected=prepare();seed_local();copy_shortcut();wait_status('copied')
        assert local_clipboard()==expected
        assert native[-1]['trusted'] and native[-1]['target']=='overlayInput'
        report['smallText']='pass'

        checkpoint('native-multipart-text')
        _,expected=prepare();seed_local();copy_shortcut();wait_status('copied')
        result=local_clipboard();assert result==expected
        report['multipartText']={'bytes':len(result.encode()),'sha256':hashlib.sha256(result.encode()).hexdigest()}

        checkpoint('unchanged-clipboard-needs-explicit-confirmation')
        seed_local();before=len(native);copy_shortcut();wait_status('copy-ready')
        assert len(native)==before,'old cached clipboard was exported automatically'
        native_edit_copy();wait_status('copied');assert local_clipboard()==expected
        report['unchangedClipboardExplicitCopy']='pass'

        checkpoint('native-edit-command-initial-copy-preserves-old-clipboard')
        prepare();seed_local();gate['hold']=True
        report['nativeEditBefore']=page.evaluate("""()=>{const e=document.querySelector('#overlayInput');return {tag:e.tagName,value:e.value,selection:[e.selectionStart,e.selectionEnd],domSelection:window.getSelection()?.toString().slice(0,80),active:document.activeElement?.id};}""")
        native_edit_copy()
        page.wait_for_timeout(500)
        actual=local_clipboard()
        report['nativeEditInitialClipboard']={'length':len(actual),'prefix':actual[:80]}
        assert actual=='LOCAL_MUST_STAY_UNCHANGED'
        # Headless Chromium pages can each report window focus. Use an actual
        # DOM focus change to test cancellation instead of relying on tab focus.
        field.focus()
        flush();page.wait_for_timeout(200)
        assert local_clipboard()=='LOCAL_MUST_STAY_UNCHANGED'
        report['nativeEditPendingCancellation']='pass'

        checkpoint('native-edit-command-without-keydown')
        _,expected=prepare();seed_local();native_edit_copy();wait_status('copied')
        assert local_clipboard()==expected
        report['nativeEditCommand']='pass'

        checkpoint('stale-echo-is-not-copy-completion')
        baseline,expected=prepare();seed_local();gate['hold']=True;before=len(native);copy_shortcut()
        page.wait_for_timeout(500)
        routes[-1].send('clipboard,'+base64.b64encode(baseline.encode()).decode())
        page.wait_for_timeout(300)
        assert len(native)==before,'stale clipboard was exported'
        flush();wait_status('copied');assert local_clipboard()==expected
        report['staleEchoRejected']='pass'

        checkpoint('delayed-response-needs-another-native-copy')
        _,expected=prepare();seed_local();gate['hold']=True;before=len(native);copy_shortcut()
        # Do not evaluate JavaScript during this wait: Playwright's evaluation
        # can itself supply userGesture and would invalidate the expiry check.
        page.wait_for_timeout(5700)
        flush();page.wait_for_timeout(350)
        assert len(native)==before,'copied after the operation activation deadline'
        assert status.get_attribute('data-status')=='copy-ready'
        copy_shortcut();wait_status('copied');assert local_clipboard()==expected
        report['lateResponseExplicitCopy']='pass'
        report['activationTestBoundary']='End-to-end tests enforce the operation deadline; actual browser activation expiry is checked separately without a routed WebSocket.'

        checkpoint('focus-change-cancels-late-copy')
        prepare();seed_local();gate['hold']=True;before=len(native);copy_shortcut()
        page.wait_for_timeout(600);field.focus();flush();page.wait_for_timeout(300)
        assert len(native)==before
        assert status.get_attribute('data-status')=='error'
        assert local_clipboard()=='LOCAL_MUST_STAY_UNCHANGED'
        report['focusCancellation']='pass'

        checkpoint('outbound-disabled')
        prepare();seed_local()
        page.evaluate("window.postMessage({type:'settings',settings:{clipboard_out_enabled:false}},location.origin)")
        page.wait_for_timeout(200)
        before=(counts['remoteCopyKeys'],len(native));copy_shortcut();page.wait_for_timeout(200)
        assert before==(counts['remoteCopyKeys'],len(native))
        assert local_clipboard()=='LOCAL_MUST_STAY_UNCHANGED'
        report['outboundDisabled']='pass'
        page.bring_to_front()
        page.evaluate("window.postMessage({type:'settings',settings:{clipboard_out_enabled:true}},location.origin)")
        page.wait_for_timeout(200)

        checkpoint('synthetic-copy-rejected')
        prepare();seed_local();before=(counts['remoteCopyKeys'],len(native))
        page.evaluate("""()=>{
          const input=document.querySelector('#overlayInput');
          input.dispatchEvent(new KeyboardEvent('keydown',{bubbles:true,code:'KeyC',key:'c',metaKey:true}));
          input.dispatchEvent(new ClipboardEvent('copy',{bubbles:true,clipboardData:new DataTransfer()}));
        }""")
        page.wait_for_timeout(200)
        assert counts['remoteCopyKeys']==before[0]
        assert local_clipboard()=='LOCAL_MUST_STAY_UNCHANGED'
        report['syntheticCopyRejected']='pass'

        checkpoint('inbound-disabled-still-allows-outbound-copy')
        _,expected=prepare();seed_local()
        page.evaluate("window.postMessage({type:'settings',settings:{clipboard_in_enabled:false}},location.origin)")
        page.wait_for_timeout(200);copy_shortcut();wait_status('copied')
        assert local_clipboard()==expected
        report['outboundOnly']='pass'
        page.bring_to_front()
        page.evaluate("window.postMessage({type:'settings',settings:{clipboard_in_enabled:true}},location.origin)")
        page.wait_for_timeout(200)

        checkpoint('disconnect-cancels-copy')
        prepare();seed_local();gate['hold']=True;before=len(native);copy_shortcut()
        page.wait_for_timeout(300);routes[-1].close(code=1000,reason='isolated-copy-test')
        page.wait_for_timeout(300)
        assert len(native)==before
        assert local_clipboard()=='LOCAL_MUST_STAY_UNCHANGED'
        report['disconnectCancellation']='pass'

        checkpoint('shared-viewer-rejects-copy')
        gate['hold']=False;gate['held']=[]
        page.goto(session_url+'#shared',wait_until='domcontentloaded',timeout=30000)
        page.wait_for_function('window.webrtcInput?.isSharedMode === true')
        seed_local();before=(counts['remoteCopyKeys'],len(native))
        copy_shortcut();page.wait_for_timeout(300)
        assert before==(counts['remoteCopyKeys'],len(native))
        assert local_clipboard()=='LOCAL_MUST_STAY_UNCHANGED'
        report['sharedViewer']='pass'
        report['nativeEvents']=native
        report['counts']=counts
        assert counts['altDowns']==0
        report['status']='pass';checkpoint('complete')
        browser.close()
except Exception as error:
    report['status']='fail';report['errorType']=type(error).__name__;checkpoint('failed')
    print(traceback.format_exc().replace(session_url,'<private Session URL>'))
    raise SystemExit(1)
