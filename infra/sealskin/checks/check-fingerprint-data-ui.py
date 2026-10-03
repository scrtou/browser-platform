#!/usr/bin/env python3
"""R6V rendered HTTP fixtures, isolated transport, no production resources."""
import argparse
import json
from pathlib import Path
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlsplit
from playwright.sync_api import sync_playwright


@contextmanager
def fixture_server(fixtures):
    mode, posted = ['filled'], []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            section = parse_qs(urlsplit(self.path).query).get('section', ['fingerprints'])[0]
            fixture = fixtures[mode[0] + '-' + section]
            body = fixture['body'].encode()
            self.send_response(200)
            for key, value in fixture['headers'].items():
                self.send_header(key, value)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            values = parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode(), keep_blank_values=True)
            posted.append({'path': self.path, 'values': values})
            section = {'fingerprint-templates': 'fingerprints', 'display-templates': 'displays', 'template-combinations': 'combinations'}[self.path.rsplit('/', 1)[-1]]
            self.send_response(303)
            self.send_header('Location', '/manage/?tab=fingerprint-data&section=' + section)
            self.send_header('Content-Length', '0')
            self.end_headers()

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:' + str(server.server_port), mode, posted
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True, type=Path)
    args = parser.parse_args()
    root = args.root
    assert not (root / 'result.json').exists()
    fixtures = {p.stem: json.loads(p.read_text()) for p in root.glob('*.json')}
    results = []
    with fixture_server(fixtures) as fixture, sync_playwright() as pw:
        origin, mode, posted = fixture
        browser = pw.chromium.launch(headless=True, args=['--no-sandbox'])
        for width, height in [(1280, 800), (768, 800), (390, 844)]:
            context = browser.new_context(viewport={'width': width, 'height': height})
            posted.clear()
            mode[0] = 'filled'
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(origin + '/manage/?tab=fingerprint-data')
            nav = page.locator('.data-nav')
            assert page.locator('.nav-tabs a', has_text='指纹数据').count() == 1
            assert page.locator('.nav-tabs a', has_text='指纹模板').count() == 0
            assert page.locator('.nav-tabs a', has_text='显示模板').count() == 0
            for section, label in [('fingerprints', '指纹模板'), ('displays', '显示模板'), ('combinations', '组合验收')]:
                nav.get_by_role('link', name=label).click()
                assert page.locator('.fingerprint-function').get_attribute('data-section') == section
                assert nav.locator('[aria-current=page]').count() == 1
                assert page.locator('.fingerprint-function form').count() == 1
                # Every editable input/select has an explicit associated label.
                assert page.locator('.fingerprint-function input:not([type=hidden]), .fingerprint-function select').evaluate_all('(rows) => rows.every(e => e.labels.length > 0)')
                assert page.evaluate('document.documentElement.scrollWidth') <= width + 1
                page.screenshot(path=str(root / (section + '-' + str(width) + '.png')), full_page=True)
                if section == 'fingerprints':
                    page.locator('#fp-label').fill('独立 QA 模板')
                    page.locator('#fp-locale').fill('zh-CN')
                    page.locator('#fp-languages').fill('zh-CN,en-US')
                    page.locator('#fp-timezone').fill('Asia/Shanghai')
                    page.get_by_role('button', name='保存指纹模板').click()
                    page.wait_for_load_state()
                    assert set(posted[-1]['values']) == {'csrf', 'label', 'locale', 'languages', 'timezone'}
                elif section == 'displays':
                    assert page.locator('.fingerprint-function input[type=number]').evaluate_all('(rows) => rows.every(e => e.getBoundingClientRect().height >= 38)')
                    page.locator('#display-label').fill('独立 QA 显示')
                    page.locator('#display-ww').fill('1600')
                    page.locator('#display-wh').fill('900')
                    page.get_by_role('button', name='保存显示模板').click()
                    page.wait_for_load_state()
                    assert set(posted[-1]['values']) == {'csrf', 'label', 'mode', 'width', 'height', 'dpr', 'window_width', 'window_height'}
                else:
                    assert page.locator('.jobs-table tbody tr').count() == 4
                    assert page.locator('.accepted-combinations article').count() == 6
                    for engine in ['camoufox', 'chromix', 'firefox']:
                        page.locator('#combo-fingerprint').select_option('fp-one')
                        page.locator('#combo-engine').select_option(engine)
                        page.locator('#combo-display').select_option('display-auto')
                        page.get_by_role('button', name='生成并验收组合').click()
                        page.wait_for_load_state()
                        assert posted[-1]['values']['browser_template_id'] == [engine]
                        assert set(posted[-1]['values']) == {'csrf', 'fingerprint_id', 'browser_template_id', 'display_id'}
                assert page.locator('.fingerprint-function').get_attribute('data-section') == section
            nav.get_by_role('link', name='指纹模板').focus()
            page.keyboard.press('Tab')
            assert nav.get_by_role('link', name='显示模板').evaluate('(e) => e === document.activeElement')
            page.keyboard.press('Enter')
            page.wait_for_load_state()
            assert page.locator('.fingerprint-function').get_attribute('data-section') == 'displays'
            page.go_back()
            assert page.locator('.fingerprint-function').get_attribute('data-section') == 'combinations'
            page.go_forward()
            page.reload()
            assert page.locator('.fingerprint-function').get_attribute('data-section') == 'displays'
            for state in ['empty', 'no-targets', 'no-displays']:
                mode[0] = state
                page.goto(origin + '/manage/?tab=fingerprint-data&section=combinations')
                assert page.get_by_role('button', name='生成并验收组合').is_disabled()
                assert page.evaluate('document.documentElement.scrollWidth') <= width + 1
            mode[0] = 'empty'
            for section in ['fingerprints', 'displays']:
                page.goto(origin + '/manage/?tab=fingerprint-data&section=' + section)
                assert page.locator('.data-empty').is_visible()
            mode[0] = 'escaped'
            page.goto(origin + '/manage/?tab=fingerprint-data&section=fingerprints')
            assert page.evaluate('window.injected === undefined')
            assert page.evaluate('document.documentElement.scrollWidth') <= width + 1
            assert not errors, errors
            results.append({'width': width, 'functions': 3, 'submissions': len(posted), 'keyboard_history_reload': 'PASS', 'empty_and_missing_dependencies': 'PASS', 'escaping': 'PASS'})
            context.close()
        context = browser.new_context(java_script_enabled=False)
        mode[0] = 'filled'
        page = context.new_page()
        page.goto(origin + '/manage/?tab=fingerprint-data')
        for section, label in [('displays', '显示模板'), ('combinations', '组合验收'), ('fingerprints', '指纹模板')]:
            page.locator('.data-nav').get_by_role('link', name=label).click()
            assert page.locator('.fingerprint-function').get_attribute('data-section') == section
        context.close()
        (root / 'result.json').write_text(json.dumps({'result': 'PASS', 'browser': browser.version, 'cases': results, 'no_script_navigation': 'PASS', 'scope': 'rendered HTTP fixtures with actual CSP on isolated loopback server; actual POST/303/GET transport; handler/gateway separately tested'}, indent=2) + '\n')
        browser.close()
    print('PASS fingerprint data: 3 functions, 3 widths, 15 submissions, keyboard/history, empty states and no-script navigation')


if __name__ == '__main__':
    main()
