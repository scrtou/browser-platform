"""Real Chromium native paste -> Selkies -> real remote Firefox paste event.

The screenshot is created and seeded into the OS clipboard only in memory.
The target denies Async Clipboard API access. CDP's native edit command supplies
macOS Command+V's platform action on this Linux test host; no ClipboardEvent is
fabricated for the success path. Actual macOS / Trilium remains a user check.
"""

import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import traceback
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright


parser = argparse.ArgumentParser()
parser.add_argument('--session-file', type=Path, required=True)
parser.add_argument('--output-dir', type=Path, required=True)
parser.add_argument('--emulate-mac-keyboard', action='store_true')
parser.add_argument('--origin', default='https://mysession.azhen.de')
parser.add_argument('--host-resolver-rules')
parser.add_argument('--certificate-spki')
args = parser.parse_args()
session_url = urljoin(args.origin, json.loads(args.session_file.read_text())['session_url'])
client_args = []
if args.host_resolver_rules: client_args += ['--host-resolver-rules='+args.host_resolver_rules, '--no-proxy-server']
if args.certificate_spki: client_args += ['--ignore-certificate-errors-spki-list='+args.certificate_spki]
report = {'status': 'running', 'startedAt': datetime.now(timezone.utc).isoformat(),
          'clientOS': 'Linux; native CDP paste with Meta modifier; macOS Trilium requires user validation',
          'sourceScreenshotWrittenToLocalDisk': False}


def checkpoint(stage):
    report['stage'] = stage
    (args.output_dir / 'screenshot-paste.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('screenshot_paste_stage=' + stage, flush=True)


try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=client_args)
        report['clientBrowser'] = browser.version
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        if args.emulate_mac_keyboard:
            context.add_init_script("Object.defineProperty(navigator,'platform',{get:()=> 'MacIntel'});")
            report['clientKeyboardMapping'] = 'MacIntel emulation on Linux; actual macOS remains unverified'
        context.grant_permissions([], origin=args.origin)
        context.grant_permissions(['clipboard-read', 'clipboard-write'], origin='https://clipboard-seed.test')
        helper = context.new_page()
        helper.route('https://clipboard-seed.test/', lambda route: route.fulfill(
            content_type='text/html', body='<div id="sample" style="width:200px;height:100px;background:rgb(30,170,220)">Clipboard PNG</div>'))
        helper.goto('https://clipboard-seed.test/')
        page = context.new_page()
        page.set_default_timeout(15000)
        counts = {'video': 0, 'clipboardWrites': 0, 'pasteKeys': 0, 'binaryEcho': 0, 'multipartEcho': 0, 'altKeyDowns': 0}
        settings = []
        gating = {'dropClipboard': False}
        native_events = []
        websocket_routes = []
        page.expose_function('recordNativePaste', lambda data: native_events.append(data))
        page.add_init_script("""window.addEventListener('paste', e => window.recordNativePaste({
            trusted:e.isTrusted, target:e.target.id, types:[...e.clipboardData.types],
            files:[...e.clipboardData.files].map(f => ({type:f.type,bytes:f.size}))
        }), true);""")

        def route_websocket(route):
            websocket_routes.append(route)
            server = route.connect_to_server()

            def from_client(message):
                if isinstance(message, str):
                    if message.startswith(('cb,', 'cw,', 'cbs,', 'cws,')):
                        counts['clipboardWrites'] += 1
                    if message == 'kd,118':
                        counts['pasteKeys'] += 1
                    if message in ['kd,65513', 'kd,65514']:
                        counts['altKeyDowns'] += 1
                    if message.startswith('SETTINGS,'):
                        settings.append(json.loads(message[9:]))
                server.send(message)

            def from_server(message):
                if isinstance(message, bytes):
                    counts['video'] += 1
                elif isinstance(message, str):
                    if message.startswith('clipboard_binary,'):
                        counts['binaryEcho'] += 1
                    if message.startswith('clipboard_start,'):
                        counts['multipartEcho'] += 1
                    if gating['dropClipboard'] and message.startswith(('clipboard,', 'clipboard_',)):
                        return
                route.send(message)

            route.on_message(from_client)
            server.on_message(from_server)

        page.route_web_socket('**/*websockets*', route_websocket)
        checkpoint('connect')
        page.goto(session_url, wait_until='domcontentloaded', timeout=30000)
        for _ in range(200):
            if counts['video'] and settings:
                break
            page.wait_for_timeout(100)
        assert counts['video'] and settings, 'no video or initial settings'
        report['permissions'] = page.evaluate("""async () => {
            const result = {};
            for (const name of ['read','write']) {
                result[name] = (await navigator.permissions.query({name:'clipboard-' + name})).state;
                try { if (name === 'read') await navigator.clipboard.read();
                      else await navigator.clipboard.writeText('must fail');
                      result[name + 'API'] = 'allowed'; }
                catch (error) { result[name + 'API'] = error.name; }
            }
            return result;
        }""")
        assert report['permissions'] == {'read':'denied', 'readAPI':'NotAllowedError', 'write':'denied', 'writeAPI':'NotAllowedError'}
        assert page.evaluate('typeof window.browserPlatformPaste.connect') == 'function'
        page.locator('#overlayInput').focus()
        page.keyboard.press('Control+l')
        page.keyboard.type('file:///tmp/browser-platform-screenshot-paste.html', delay=2)
        page.keyboard.press('Enter')
        page.wait_for_timeout(1300)
        page.mouse.click(6, 540)
        toggle = page.locator('[aria-controls="clipboard-content"]')
        if toggle.get_attribute('aria-expanded') != 'true':
            toggle.click()
        field = page.locator('#dashboardClipboardTextarea')
        page.locator('#overlayInput').focus()
        cdp = context.new_cdp_session(page)

        def native_paste(meta_already_held=False):
            page.locator('#overlayInput').focus()
            alt_before = counts['altKeyDowns']
            # The native platform edit command generates a trusted paste event,
            # using actual clipboard bytes even though target API access is denied.
            if not meta_already_held:
                cdp.send('Input.dispatchKeyEvent', {'type':'rawKeyDown', 'key':'Meta', 'code':'MetaLeft',
                                                  'modifiers':4, 'windowsVirtualKeyCode':91})
            cdp.send('Input.dispatchKeyEvent', {'type':'rawKeyDown', 'key':'v', 'code':'KeyV',
                                              'modifiers':4, 'windowsVirtualKeyCode':86, 'commands':['paste']})
            cdp.send('Input.dispatchKeyEvent', {'type':'keyUp', 'key':'v', 'code':'KeyV',
                                              'modifiers':4, 'windowsVirtualKeyCode':86})
            if not meta_already_held:
                cdp.send('Input.dispatchKeyEvent', {'type':'keyUp', 'key':'Meta', 'code':'MetaLeft',
                                                  'modifiers':0, 'windowsVirtualKeyCode':91})
            if args.emulate_mac_keyboard:
                assert counts['altKeyDowns'] == alt_before, 'native Command+V forwarded remote Alt'

        def seed_image(large=False):
            helper.bring_to_front()
            if not large:
                png = helper.locator('#sample').screenshot()
                result = helper.evaluate("""async png => {
                    const bytes = Uint8Array.from(atob(png), c => c.charCodeAt(0));
                    const blob = new Blob([bytes], {type:'image/png'});
                    await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);
                    const bitmap=await createImageBitmap(blob), canvas=document.createElement('canvas');
                    canvas.width=200;canvas.height=100;
                    const ctx=canvas.getContext('2d');ctx.drawImage(bitmap,0,0);bitmap.close();
                    const pixelSHA256=[...new Uint8Array(await crypto.subtle.digest('SHA-256',ctx.getImageData(0,0,200,100).data))].map(b=>b.toString(16).padStart(2,'0')).join('');
                    return {bytes:blob.size,width:200,height:100,pixel:[30,170,220,255],pixelSHA256};
                }""", base64.b64encode(png).decode())
            else:
                result = helper.evaluate("""async () => {
                    const canvas = document.createElement('canvas'); canvas.width=1100;canvas.height=800;
                    const ctx=canvas.getContext('2d'), pixels=ctx.createImageData(1100,800);
                    let seed=12345;
                    for(let i=0;i<pixels.data.length;i+=4){
                        seed=(Math.imul(seed,1664525)+1013904223)>>>0;
                        pixels.data[i]=seed&255;pixels.data[i+1]=(seed>>>8)&255;pixels.data[i+2]=(seed>>>16)&255;pixels.data[i+3]=255;
                    }
                    ctx.putImageData(pixels,0,0);
                    const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
                    await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);
                    const pixelSHA256=[...new Uint8Array(await crypto.subtle.digest('SHA-256',pixels.data))].map(b=>b.toString(16).padStart(2,'0')).join('');
                    return {bytes:blob.size,width:1100,height:800,pixel:[...ctx.getImageData(1095,795,1,1).data],pixelSHA256};
                }""")
            page.bring_to_front()
            return result

        def read_remote_results(expected_count, typed=None):
            for _ in range(35):
                page.keyboard.press('F8')
                page.wait_for_timeout(200)
                value = field.input_value()
                if value.startswith('BP_PASTE_REPORT:'):
                    remote = json.loads(value[len('BP_PASTE_REPORT:'):])
                    if len(remote['results']) >= expected_count and (typed is None or remote['typedText'] == typed):
                        return remote
            raise AssertionError('remote Firefox did not report the paste')

        checkpoint('native-small-screenshot')
        small = seed_image()
        native_paste()
        page.wait_for_function("document.querySelector('#browser-platform-paste-status')?.dataset.status === 'success'")
        remote = read_remote_results(1)
        received = remote['results'][0]
        assert received['trusted'] and received['type'] == 'image/png'
        for key in ['width','height','pixel','pixelSHA256']:
            assert received[key] == small[key], key
        report['smallPNG'] = {'source':small, 'remoteFirefoxPaste':received}
        checkpoint('native-multipart-screenshot')
        large = seed_image(large=True)
        assert large['bytes'] > 750 * 1024
        native_paste()
        page.wait_for_function("document.querySelector('#browser-platform-paste-status')?.dataset.status === 'success'", timeout=25000)
        remote = read_remote_results(2)
        received = remote['results'][1]
        assert received['trusted'] and received['type'] == 'image/png'
        for key in ['width','height','pixel','pixelSHA256']:
            assert received[key] == large[key], key
        report['multipartPNG'] = {'source':large, 'remoteFirefoxPaste':received}

        checkpoint('native-chinese-text')
        helper.bring_to_front()
        text = '截图直接粘贴\n繁體中文與 emoji 📷'
        helper.evaluate('text => navigator.clipboard.writeText(text)', text)
        page.bring_to_front()
        native_paste()
        page.wait_for_function("document.querySelector('#browser-platform-paste-status')?.dataset.status === 'success'")
        remote = read_remote_results(3)
        assert remote['results'][2]['text'] == text, 'native text mismatch'
        report['nativeText'] = 'pass'

        checkpoint('existing-manual-panel-and-typing')
        manual = '原有侧栏文字 Control+V'
        field.fill(manual)
        page.locator('#overlayInput').focus()
        page.wait_for_timeout(650)
        page.keyboard.press('Control+v')
        remote = read_remote_results(4)
        assert remote['results'][3]['text'] == manual, 'manual panel text mismatch'
        page.keyboard.type('normal-input-123', delay=20)
        remote = read_remote_results(4, typed='normal-input-123')
        assert remote['typedText'] == 'normal-input-123', 'ordinary typing mismatch'
        report['manualPanelAndKeyboard'] = 'pass'
        if args.emulate_mac_keyboard:
            checkpoint('other-mac-command-shortcuts')
            page.keyboard.press('Meta+a')
            page.keyboard.press('Meta+c')
            page.wait_for_function("document.querySelector('#dashboardClipboardTextarea').value === 'normal-input-123'")
            report['otherMacCommandShortcuts'] = 'pass'
            checkpoint('command-held-across-native-paste')
            seed_image()
            page.locator('#overlayInput').focus()
            page.keyboard.press('F8')
            page.wait_for_function("document.querySelector('#dashboardClipboardTextarea').value.startsWith('BP_PASTE_REPORT:')")
            page.keyboard.down('Meta')
            page.keyboard.press('a')
            native_paste(meta_already_held=True)
            page.wait_for_function("document.querySelector('#browser-platform-paste-status')?.dataset.status === 'success'")
            page.keyboard.press('a')
            page.keyboard.up('Meta')
            page.keyboard.press('Control+c')
            page.wait_for_function("document.querySelector('#dashboardClipboardTextarea').value === 'normal-input-123'")
            report['commandHeldAcrossNativePaste'] = 'pass'

        checkpoint('no-paste-before-confirmation-and-cancel-on-focus-change')
        seed_image()
        gating['dropClipboard'] = True
        paste_keys = counts['pasteKeys']
        native_paste()
        page.wait_for_timeout(1200)
        assert counts['pasteKeys'] == paste_keys, 'pasted without clipboard acknowledgement'
        assert page.locator('#browser-platform-paste-status').get_attribute('data-status') == 'sending'
        field.focus()
        page.wait_for_function("document.querySelector('#browser-platform-paste-status')?.dataset.status === 'error'")
        gating['dropClipboard'] = False
        page.locator('#overlayInput').focus()
        page.wait_for_timeout(400)
        assert counts['pasteKeys'] == paste_keys, 'late paste after cancellation'
        report['missingAcknowledgementAndFocusCancellation'] = 'pass'

        checkpoint('disabled-clipboard-rejects-paste')
        page.evaluate("window.postMessage({type:'settings',settings:{clipboard_in_enabled:false}},location.origin)")
        page.wait_for_timeout(300)
        seed_image()
        writes = counts['clipboardWrites']
        native_paste()
        page.wait_for_timeout(300)
        assert counts['clipboardWrites'] == writes and counts['pasteKeys'] == paste_keys
        assert page.locator('#browser-platform-paste-status').get_attribute('data-status') == 'error'
        page.evaluate("window.postMessage({type:'settings',settings:{clipboard_in_enabled:true}},location.origin)")
        page.wait_for_timeout(300)
        report['disabledClipboard'] = 'pass'

        checkpoint('untrusted-event-is-ignored')
        writes = counts['clipboardWrites']
        page.evaluate("""() => {
            const data=new DataTransfer();data.setData('text/plain','synthetic-should-not-send');
            document.querySelector('#overlayInput').dispatchEvent(new ClipboardEvent('paste',{bubbles:true,clipboardData:data}));
        }""")
        page.wait_for_timeout(150)
        assert counts['clipboardWrites'] == writes
        report['untrustedEventIgnored'] = True
        report['nativePasteEvents'] = [event for event in native_events if event['trusted']]
        assert len(report['nativePasteEvents']) >= 5, 'missing trusted native paste events'
        report['wireCounts'] = counts
        report['temporarySettings'] = settings
        # After initialization settles, temporary image support must be the only
        # difference in each SETTINGS pair sent by the native paste transaction.
        changed = []
        for i, item in enumerate(settings):
            if i and 'enable_binary_clipboard' in settings[i-1] and item.get('enable_binary_clipboard') != settings[i-1].get('enable_binary_clipboard'):
                delta = {key for key in set(item) | set(settings[i-1]) if item.get(key) != settings[i-1].get(key)}
                assert delta == {'enable_binary_clipboard'}, delta
                changed.append(sorted(delta))
        assert len(changed) >= 6 and settings[-1]['enable_binary_clipboard'] is False
        report['onlyBinaryClipboardSettingChanged'] = True

        checkpoint('disconnected-session-rejects-paste')
        seed_image()
        writes = counts['clipboardWrites']
        paste_keys = counts['pasteKeys']
        websocket_routes[-1].close()
        page.wait_for_timeout(100)
        native_paste()
        page.wait_for_timeout(200)
        assert counts['clipboardWrites'] == writes and counts['pasteKeys'] == paste_keys
        assert page.locator('#browser-platform-paste-status').get_attribute('data-status') == 'error'
        report['disconnectedSession'] = 'pass'

        checkpoint('shared-viewer-rejects-paste')
        page.goto(session_url + '#shared', wait_until='domcontentloaded', timeout=30000)
        page.wait_for_function('window.webrtcInput?.isSharedMode === true')
        seed_image()
        writes = counts['clipboardWrites']
        paste_keys = counts['pasteKeys']
        native_paste()
        page.wait_for_timeout(300)
        assert counts['clipboardWrites'] == writes and counts['pasteKeys'] == paste_keys
        assert page.locator('#browser-platform-paste-status').get_attribute('data-status') == 'error'
        report['sharedViewer'] = 'pass'
        report['status'] = 'pass'
        context.close()
        browser.close()
except Exception as error:
    report['status'] = 'fail'
    report['errorType'] = type(error).__name__
    report['errorLine'] = traceback.extract_tb(error.__traceback__)[-1].lineno
    # Keep Session URLs and image payloads out of diagnostics.
    if isinstance(error, AssertionError):
        report['assertion'] = str(error)[:200]
report['completedAt'] = datetime.now(timezone.utc).isoformat()
(args.output_dir / 'screenshot-paste.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({key:report[key] for key in ['status','stage','errorType','assertion'] if key in report}), flush=True)
raise SystemExit(0 if report['status'] == 'pass' else 1)
