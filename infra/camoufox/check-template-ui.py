#!/usr/bin/env python3
"""Render the exact isolated Adapter template pages in Linux Chromium."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True, type=Path)
    p.add_argument('--multi-engine',action='store_true')
    p.add_argument('--empty',action='store_true')
    a = p.parse_args()
    root = a.root
    assert not (root / 'result.json').exists()
    rows = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=['--no-sandbox'])
        page = browser.new_page()
        for width, height in [(1280, 800), (768, 800), (390, 844)]:
            page.set_viewport_size({'width': width, 'height': height})
            for tab in ['fingerprints', 'displays']:
                page.set_content((root / (tab + '.html')).read_text(), wait_until='load')
                assert page.locator('script,link[rel=stylesheet]').count() == 0
                form = page.locator('form[action="/manage/' + ('fingerprint' if tab == 'fingerprints' else 'display') + '-templates"]')
                assert form.count() == 1
                if tab == 'fingerprints':
                    assert form.locator('[name=width],[name=dpr],[name=window_width],[name=engine],[name=browser_version]').count() == 0
                    assert form.locator('[name=locale],[name=timezone]').count() == 2
                    combinations=page.locator('form[action="/manage/template-combinations"]')
                    assert combinations.count() > 0
                    assert combinations.locator('select[name=browser_template_id][required]').count() == combinations.count()
                    assert combinations.locator('option[value=camoufox-linux-v152]').count() == combinations.count()
                    if a.multi_engine:
                        for engine in ('chromix-linux-154','firefox-linux-155'):
                            assert combinations.locator('option[value='+engine+']').count() == combinations.count()
                    assert combinations.locator('option[value=display-0000000000000001]').count() == 1
                    assert combinations.locator('button[type=submit]').is_disabled() == a.empty
                    assert combinations.locator('select[name=fingerprint_id] option:not([value=""])').count() == (0 if a.empty else 1)
                else:
                    assert form.locator('[name=locale],[name=timezone]').count() == 0
                    assert form.locator('[name=width],[name=dpr],[name=window_width]').count() == 3
                geometry = page.evaluate('''() => ({width:innerWidth, scroll:document.documentElement.scrollWidth,
                  controls:[...document.querySelectorAll('form input:not([type=hidden]),form select,form button')]
                  .filter(e=>e.getClientRects().length).map(e=>({label:e.tagName==='BUTTON'||e.labels.length>0,
                    left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right}))})''')
                assert geometry['scroll'] <= width + 1
                for c in geometry['controls']:
                    assert c['label'] and c['left'] >= 0 and c['right'] <= width + 1
                focus = form.locator('input:not([type=hidden])').first
                focus.focus()
                page.keyboard.press('Tab')
                assert not focus.evaluate('(e)=>e===document.activeElement')
                page.screenshot(path=str(root / (tab + '-' + str(width) + '.png')), full_page=True)
                rows.append({'tab': tab, 'width': width, 'geometry': geometry})
        (root / 'result.json').write_text(json.dumps({'result': 'PASS', 'browser': browser.version, 'rows': rows,
            'scope': 'isolated rendered HTML; HTTP forms and auth separately covered by Go tests'}, indent=2) + '\n')
        browser.close()
    print('PASS six template-page views, field separation, labels, keyboard and responsive bounds')


if __name__ == '__main__':
    main()
