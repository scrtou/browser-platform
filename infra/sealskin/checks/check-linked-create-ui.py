#!/usr/bin/env python3
"""Exercise R6U's rendered fixtures with their real HTTP CSP, without production writes."""
import argparse
import json
from pathlib import Path
from urllib.parse import parse_qs

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True, type=Path)
    args = parser.parse_args()
    root = args.root
    assert not (root / 'result.json').exists(), 'OUTPUT_ALREADY_EXISTS'
    fixtures = {p.stem: json.loads(p.read_text()) for p in root.glob('*.json')}
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=['--no-sandbox'])
        for width, height in [(1280, 800), (768, 800), (390, 844)]:
            context = browser.new_context(viewport={'width': width, 'height': height})
            posted = []

            def serve(route):
                request = route.request
                name = request.url.rsplit('/', 1)[-1].split('?')[0]
                if request.method == 'POST':
                    posted.append(parse_qs(request.post_data, keep_blank_values=True))
                    name = 'multi'
                fixture = fixtures.get(name, fixtures['multi'])
                route.fulfill(status=200, headers=fixture['headers'], body=fixture['body'])

            context.route('https://adapter.example/**', serve)
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto('https://adapter.example/multi')
            engine = page.locator('#cb-browser-template')
            fingerprint = page.locator('#cb-fingerprint-template')
            assert engine.locator('option').count() == 3
            assert page.locator('#cb-display-template').count() == 0
            assert page.locator('.browser-create-form [name=display_template_id]').count() == 0
            for target in ['camoufox', 'chromix', 'firefox', 'camoufox']:
                engine.select_option(target)
                options = fingerprint.locator('option').evaluate_all('(rows) => rows.map(o => [o.value, o.dataset.browser])')
                assert {v for v, _ in options} == {target + '-fixed', target + '-auto'}, options
                assert all(owner == target for _, owner in options)
                fingerprint.select_option(target + '-auto')
                assert 'auto 显示' in page.locator('#cb-template-info').inner_text()
                page.locator('#cb-label').fill('独立测试')
                page.locator('#cb-start-url').fill('https://start.example/')
                page.locator('#cb-idempotency-key').fill('isolated-' + target)
                page.locator('#cb-submit').click()
                page.wait_for_load_state()
                assert posted[-1]['browser_template_id'] == [target]
                assert posted[-1]['environment_artifact_id'] == [target + '-auto']
                assert 'display_template_id' not in posted[-1] and 'template_combination' not in posted[-1]
            engine.focus()
            page.keyboard.press('ArrowDown')
            page.keyboard.press('Tab')
            assert fingerprint.evaluate('(e) => e === document.activeElement')
            assert fingerprint.locator('option').evaluate_all('(rows) => rows.every(o => o.dataset.browser === document.getElementById("cb-browser-template").value)')
            # A restored select value must be reconciled on pageshow, including bfcache.
            engine.evaluate('(e) => { e.value = "firefox"; window.dispatchEvent(new PageTransitionEvent("pageshow", {persisted:true})); }')
            assert fingerprint.input_value().startswith('firefox-')
            page.locator('.browser-create-form').evaluate('(f) => f.reset()')
            page.wait_for_function('document.querySelector("#cb-fingerprint-template").value.startsWith(document.querySelector("#cb-browser-template").value + "-")')
            assert page.evaluate('document.documentElement.scrollWidth') <= width + 1
            page.screenshot(path=str(root / ('linked-' + str(width) + '.png')), full_page=True)
            for name in ['empty', 'unavailable', 'ambiguous', 'network-unavailable']:
                page.goto('https://adapter.example/' + name)
                assert page.locator('#cb-submit').is_disabled(), name
                if name != 'network-unavailable':
                    assert fingerprint.is_disabled() and not fingerprint.input_value(), name
            page.goto('https://adapter.example/escaped-label')
            assert page.evaluate('window.injected === undefined')
            assert fingerprint.locator('option').count() == 2
            assert not errors, errors
            # Enforced CSP must reject an added script that has no nonce.
            page.evaluate('''() => {
              window.blockedScript = false;
              document.addEventListener('securitypolicyviolation', () => { window.blockedScript = true; });
              const script = document.createElement('script');
              script.textContent = 'window.injected=true'; document.body.appendChild(script);
            }''')
            page.wait_for_function('window.blockedScript')
            assert page.evaluate('window.injected === undefined')
            results.append({'width': width, 'engines': 3, 'submissions': len(posted), 'empty_and_network_states': 'pass', 'keyboard_restore_reset': 'pass', 'csp_and_escaped_labels': 'pass'})
            context.close()
        context = browser.new_context(java_script_enabled=False)
        fixture = fixtures['multi']
        context.route('https://adapter.example/**', lambda route: route.fulfill(status=200, headers=fixture['headers'], body=fixture['body']))
        page = context.new_page()
        page.goto('https://adapter.example/multi')
        assert page.locator('#cb-submit').is_disabled() and page.locator('#cb-fingerprint-template').is_disabled()
        assert page.locator('noscript').is_visible()
        context.close()
        (root / 'result.json').write_text(json.dumps({'result': 'PASS', 'browser': browser.version, 'cases': results, 'javascript_disabled': 'pass', 'scope': 'isolated rendered HTTP fixtures; actual gateway/POST resolution covered by Go tests'}, indent=2) + '\n')
        browser.close()
    print('PASS linked create: 3 engines, 3 widths, 12 form submissions, empty states, keyboard, nonce CSP and no-script')


if __name__ == '__main__':
    main()
