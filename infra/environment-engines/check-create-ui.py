#!/usr/bin/env python3
"""Render creation choices exported from the actual accepted six-combination catalog."""
import argparse,json
from pathlib import Path
from playwright.sync_api import sync_playwright
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root
assert not (root/'result.json').exists()
with sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True,args=['--no-sandbox']);page=browser.new_page();rows=[]
 for width,height in [(1280,800),(768,800),(390,844)]:
  page.set_viewport_size({'width':width,'height':height});page.set_content((root/'browsers.html').read_text())
  select=page.locator('#cb-browser-template')
  assert set(select.locator('option').evaluate_all('(es)=>es.map(e=>e.value)'))=={'camoufox-linux-v152','chromix-linux-154','firefox-linux-155'}
  displays=page.locator('#cb-display-template');assert displays.locator('option').count()==2
  for engine in ('camoufox-linux-v152','chromix-linux-154','firefox-linux-155'):
   select.select_option(engine);assert select.input_value()==engine
   displays.select_option('display-0000000000000001');assert displays.input_value()=='display-0000000000000001'
  assert page.evaluate('document.documentElement.scrollWidth')<=width+1
  page.screenshot(path=str(root/('create-'+str(width)+'.png')),full_page=True);rows.append({'width':width,'engines':3,'shared_displays':2})
 (root/'result.json').write_text(json.dumps({'result':'PASS','browser':browser.version,'cases':rows},indent=2)+'\n');browser.close()
print('PASS creation UI: three engines, two shared displays, three widths')
