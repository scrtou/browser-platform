#!/usr/bin/env python3
"""Render an authenticated, isolated Adapter UI in real Linux Chromium.

The private evidence directory supplies account.json and connection.json.
Only the fixed QA origin and login POST are permitted. No browser start,
configuration submission, production account or Session URL is used.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    account = json.loads((evidence / "account.json").read_text())
    connection = json.loads((evidence / "connection.json").read_text())
    origin = connection["origin"]
    assert origin == "https://entry.r5d.test:29443"
    assert account["username"] == "work-qa-admin"
    output = evidence / "render-result.json"
    assert not output.exists(), "preserve earlier results"
    result = {"status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
              "platform": "Linux Chromium; no Mac or Trilium assertion", "views": [], "blocked_requests": []}

    def checkpoint():
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=[
                "--no-proxy-server", "--host-resolver-rules=MAP entry.r5d.test 127.0.0.1",
                "--ignore-certificate-errors-spki-list=" + connection["spki"]])
            result["browser_version"] = browser.version
            context = browser.new_context(viewport={"width": 1280, "height": 800})

            def boundary(route):
                request = route.request
                parsed = urlsplit(request.url)
                permitted = parsed.scheme + "://" + parsed.netloc == origin
                permitted = permitted and (request.method in ("GET", "HEAD") or
                    request.method == "POST" and parsed.path == "/auth/login")
                if permitted:
                    route.continue_()
                else:
                    result["blocked_requests"].append({"method": request.method, "path": parsed.path})
                    route.abort()

            context.route("**/*", boundary)
            page = context.new_page()
            page.set_default_timeout(15000)
            page.goto(origin + "/auth/login", wait_until="networkidle")
            page.locator('input[name="username"]').fill(account["username"])
            page.locator('input[name="password"]').fill(account["password"])
            page.locator("form button").click()
            page.wait_for_url(origin + "/")
            cases = [("home", "/"), ("browsers", "/manage/"), ("network", "/manage/?tab=network")]
            for width, height in ((1280, 800), (768, 800), (390, 844)):
                page.set_viewport_size({"width": width, "height": height})
                for name, path in cases:
                    response = page.goto(origin + path, wait_until="networkidle")
                    assert response.status == 200
                    assert page.locator('meta[name="viewport"]').count() == 1
                    assert page.locator('script,script[src],link[rel="stylesheet"]').count() == 0
                    if name == "browsers":
                        choices = {}
                        for field in ("browser_template_id", "environment_artifact_id", "display_template_id", "network_selection"):
                            select = page.locator('form[action="/manage/browsers"] select[name="' + field + '"]')
                            assert select.count() == 1 and select.is_visible() and select.is_enabled()
                            choices[field] = select.locator("option").count()
                            assert choices[field] > 0
                            assert select.evaluate("e=>e.labels.length") > 0
                            select.select_option(index=choices[field] - 1)
                            select.focus()
                            page.keyboard.press("Tab")
                            assert select.evaluate("e=>document.activeElement!==e")
                        result["template_choices"] = choices
                        display_names = page.locator('#cb-display-template option').all_text_contents()
                        assert all("固定指纹" in name and not any(tech in name.lower() for tech in ("x11", "wayland", "selkies")) for name in display_names)
                        result["display_effect_names"] = display_names
                    elif name == "network":
                        assert page.get_by_text("隔离代理示例", exact=True).count() > 0
                        assert page.get_by_text("已停用的测试代理", exact=True).count() > 0
                        assert page.locator('a[aria-current="page"]').get_attribute("href") == "/manage/?tab=network"
                    else:
                        assert page.get_by_text("工作浏览器 · 独立页面检查", exact=True).count() > 0
                    dimensions = page.evaluate("""()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
                        controls:[...document.querySelectorAll('input:not([type=hidden]),select,textarea,button')]
                        .filter(e=>e.getClientRects().length).map(e=>{let r=e.getBoundingClientRect(),a=e.parentElement;
                          while(a&&!(a.scrollWidth>a.clientWidth&&['auto','scroll'].includes(getComputedStyle(a).overflowX)))a=a.parentElement;
                          let ar=a?.getBoundingClientRect();
                          return {tag:e.tagName,name:e.name,left:r.left,right:r.right,width:r.width,
                            localScroll:!!ar&&ar.left>=0&&ar.right<=innerWidth}})})""")
                    page.screenshot(path=str(evidence / f"{name}-{width}-full.png"), full_page=True)
                    page.evaluate("scrollTo(0,0)")
                    page.screenshot(path=str(evidence / f"{name}-{width}.png"))
                    result["views"].append({"page": name, "viewport": [width, height], "dimensions": dimensions})
                    checkpoint()
                    assert dimensions["scrollWidth"] <= width + 1, "page horizontally overflows"
                    assert all(c["localScroll"] or c["left"] >= -1 and c["right"] <= width + 1 for c in dimensions["controls"]), "form controls overflow viewport"
                    # Narrow tables may scroll locally by design. Verify the
                    # controls can actually be brought into view without a POST.
                    for control in page.locator("input:not([type=hidden]),select,textarea,button").all():
                        if not control.is_visible():
                            continue
                        reachable = control.evaluate("""e=>{e.scrollIntoView({block:'nearest',inline:'nearest'});
                            let r=e.getBoundingClientRect();return r.left>=-1&&r.right<=innerWidth+1}""")
                        assert reachable, "control cannot be reached by local scrolling"
                    result["views"][-1]["controls_reachable"] = True
            page.set_viewport_size({"width": 1280, "height": 800})
            page.goto(origin + "/manage/")
            link = page.locator('a[href="/manage/?tab=network"]')
            link.focus()
            page.keyboard.press("Enter")
            page.wait_for_url(origin + "/manage/?tab=network")
            page.go_back()
            page.wait_for_url(origin + "/manage/")
            page.reload()
            assert page.locator('a[aria-current="page"]').get_attribute("href") == "/manage/?tab=browsers"
            result["keyboard_navigation_back_reload"] = "PASS"
            assert not result["blocked_requests"], "unexpected request attempted"
            result["status"] = "PASS"
            result["finished_at"] = datetime.now(timezone.utc).isoformat()
            browser.close()
    except Exception as error:
        result["status"] = "FAIL"
        result["error_type"] = type(error).__name__
        raise
    finally:
        checkpoint()
    print(json.dumps({"status": result["status"], "views": len(result["views"]),
                      "browser": result["browser_version"]}), flush=True)


if __name__ == "__main__":
    main()
