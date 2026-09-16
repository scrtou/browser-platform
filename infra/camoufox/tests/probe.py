#!/usr/bin/env python3
"""One real browser run inside a disposable Worker with a persistent QA Home."""

import argparse
import importlib.abc
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

sys.path.insert(0, "/usr/local/lib/browser-platform")
import environment as engine

FIXTURE = "https://profile-fixture.browser-platform.test/"
ROOT = Path(__file__).resolve().parent
SCRIPT = ("const storageProof = " + (ROOT / "storage.js").read_text() + ";\n"
          + "const observeEnvironment = " + (ROOT / "observe.js").read_text() + ";\n"
          + (ROOT / "fixture-runner.js").read_text())
HTML = (ROOT / "fixture.html").read_text().replace("</html>", "<script>" + SCRIPT + "</script></html>")


def read_result(page):
    # Observe in the page's own realm. Camoufox's default evaluation sandbox
    # uses Xrays; sampling audio/canvas there would not test real page behavior.
    page.wait_for_selector('#qa-result[data-complete="true"]', state="attached", timeout=15000)
    result = json.loads(page.locator("#qa-result").text_content())
    if "error" in result:
        raise AssertionError("fixture failed: " + result["error"])
    return result


class DenyGeneration(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname.split(".", 1)[0] in {"camoufox", "browserforge", "apify_fingerprint_datapoints"}:
            raise AssertionError("runtime attempted to import a generator: " + fullname)
        return None


def assert_equal(actual, expected, name):
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")


def check_network():
    result = {}
    for name, address in (("directIPv4Blocked", ("1.1.1.1", 443)),
                          ("directIPv6Blocked", ("2606:4700:4700::1111", 443))):
        try:
            connection = socket.create_connection(address, timeout=2)
        except OSError:
            result[name] = True
        else:
            connection.close()
            raise AssertionError(name + " failed")
    socket.getaddrinfo("profile-relay", 1080)
    result["relayAliasResolvable"] = True
    try:
        socket.getaddrinfo("example.com", 443)
    except socket.gaierror:
        result["publicDNSBlocked"] = True
    else:
        raise AssertionError("publicDNSBlocked failed")
    return result


def run(args):
    artifact = engine.load_artifact(os.environ["BROWSER_PLATFORM_ARTIFACT_FILE"],
                                    os.environ["BROWSER_PLATFORM_ARTIFACT_SHA256"])
    sys.meta_path.insert(0, DenyGeneration())
    from playwright.sync_api import sync_playwright

    spec = artifact["spec"]
    profile = Path("/config/.camoufox/profile")
    profile.mkdir(mode=0o700, parents=True, exist_ok=True)
    display = ":99"
    os.environ["DISPLAY"] = display
    xvfb = subprocess.Popen(["Xvfb", display, "-screen", "0",
                             f'{spec["screen"]["width"]}x{spec["screen"]["height"]}x24',
                             "-nolisten", "tcp", "-ac"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(200):
            if Path("/tmp/.X11-unix/X99").exists():
                break
            if xvfb.poll() is not None:
                raise AssertionError("Xvfb exited")
            time.sleep(0.05)
        else:
            raise AssertionError("Xvfb startup timed out")
        result = {"role": args.role, "iteration": args.iteration, "artifactSHA256": os.environ["BROWSER_PLATFORM_ARTIFACT_SHA256"]}
        with sync_playwright() as playwright:
            context = playwright.firefox.launch_persistent_context(
                user_data_dir=str(profile), executable_path=str(engine.EXECUTABLE),
                headless=False, no_viewport=True, env=engine.replay_environment(artifact),
                timeout=45000,
            )
            try:
                headers = []
                def route_fixture(route):
                    headers.append(route.request.all_headers().get("accept-language"))
                    route.fulfill(status=200, content_type="text/html; charset=utf-8",
                                  body=HTML.replace("__EXPECTED_VOICE_COUNT__", str(len(artifact["resolvedConfig"]["voices"]))))
                context.route(FIXTURE + "**", route_fixture)
                page = context.pages[0] if context.pages else context.new_page()
                marker = "browser-platform-home-" + args.role
                first_url = FIXTURE + "first" + ("?initialize=" + marker if args.iteration == 0 else "")
                page.goto(first_url, wait_until="load")
                sample = read_result(page)
                proof = sample["before"]
                expected = {"cookie": marker, "localStorage": marker, "indexedDB": marker}
                if args.iteration == 0:
                    assert_equal(proof, {key: None for key in expected}, "new Home isolation")
                else:
                    assert_equal(proof, expected, "Home persistence")
                assert_equal(sample["after"], expected, "stored proof")
                observed = sample["observed"]
                for key, wanted in (("locale", spec["locale"]), ("languages", spec["languages"]),
                                    ("timezone", spec["timezone"]), ("deviceScaleFactor", 1),
                                    ("webrtcType", "undefined"), ("voicesReady", True)):
                    assert_equal(observed[key], wanted, key)
                for key in ("width", "height"):
                    assert_equal(observed["screen"][key], spec["screen"][key], "screen." + key)
                for key, window_size in (("outerWidth", spec["window"]["width"]),
                                         ("outerHeight", spec["window"]["height"])):
                    assert_equal(observed["window"][key], window_size, "window." + key)
                assert 0 < observed["window"]["innerWidth"] <= observed["window"]["outerWidth"], "inner/outer width mismatch"
                assert 0 < observed["window"]["innerHeight"] <= observed["window"]["outerHeight"], "inner/outer height mismatch"
                for key, property_name in (("userAgent", "navigator.userAgent"), ("platform", "navigator.platform"),
                                           ("hardwareConcurrency", "navigator.hardwareConcurrency")):
                    assert_equal(observed[key], artifact["resolvedConfig"][property_name], key)
                assert observed["webgl"], "WebGL observation unavailable"
                assert_equal(observed["webgl"]["vendor"], artifact["resolvedConfig"]["webGl:vendor"], "WebGL vendor")
                assert_equal(observed["webgl"]["renderer"], artifact["resolvedConfig"]["webGl:renderer"], "WebGL renderer")
                assert_equal(headers[0], artifact["resolvedConfig"]["headers.Accept-Language"], "Accept-Language")
                page.goto(FIXTURE + "second", wait_until="load")
                page.go_back(wait_until="load")
                assert_equal(page.url, first_url, "history back")
                page.go_forward(wait_until="load")
                assert_equal(page.url, FIXTURE + "second", "history forward")
                tab = context.new_page()
                tab.goto(FIXTURE + "tab", wait_until="load")
                assert_equal(read_result(tab)["after"], expected, "new tab storage")
                tab.close()
                result.update(observed=observed, acceptLanguage=headers[0], storage=proof if args.iteration else expected,
                              navigation="pass", runtimeGeneration="not-imported")
                if args.network:
                    response = page.goto("https://example.com/", wait_until="load", timeout=45000)
                    assert response is not None and response.status == 200, "browser proxy request failed"
                    result["network"] = {"browserHTTPSViaRelay": 200, **check_network()}
            finally:
                context.close()
        print(json.dumps(result, sort_keys=True))
    finally:
        xvfb.terminate()
        try:
            xvfb.wait(timeout=10)
        except subprocess.TimeoutExpired:
            xvfb.kill()
            xvfb.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=("A", "B"), required=True)
    parser.add_argument("--iteration", type=int, required=True)
    parser.add_argument("--network", action="store_true")
    run(parser.parse_args())
