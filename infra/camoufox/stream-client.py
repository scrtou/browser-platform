#!/usr/bin/env python3
"""Exercise the Selkies web client in a disposable, separate QA client.

Read the one-use Session URL from a private file; never log it. This is a web
client check, not a substitute for Trilium Desktop or the user's OS IME.
"""

import argparse
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import parse_qsl, urljoin, urlsplit

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-file", type=Path, required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    private = json.loads(args.session_file.read_bytes())
    session_url = urljoin(args.origin, private["session_url"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = {"schemaVersion": "browser-platform/camoufox-stream-acceptance/v1", "status": "running",
              "startedAt": datetime.now(timezone.utc).isoformat(),
              "websockets": {"connections": 0, "receivedFrames": 0, "binaryFrames": 0}}
    clipboard_received = []

    def checkpoint(stage):
        report["stage"] = stage
        (args.output_dir / "stream.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
        print("stream_stage=" + stage, flush=True)

    def received(payload):
        report["websockets"]["receivedFrames"] += 1
        if isinstance(payload, bytes):
            report["websockets"]["binaryFrames"] += 1
        elif payload.startswith("clipboard,"):
            clipboard_received.append(base64.b64decode(payload[10:]).decode("utf-8"))

    def opened(socket):
        report["websockets"]["connections"] += 1
        socket.on("framereceived", received)

    def wait_for_frames(page, previous=0):
        for _ in range(100):
            if report["websockets"]["binaryFrames"] > previous:
                return
            page.wait_for_timeout(100)
        raise AssertionError("no video frames received")

    client_home = Path("/tmp/browser-platform-stream-client")
    client_home.mkdir(mode=0o700, exist_ok=True)
    try:
        checkpoint("launch-client")
        with sync_playwright() as playwright:
            # The QA client has its own temporary profile and network. It does
            # not launch or modify the server's frozen browser configuration.
            browser = playwright.chromium.launch(headless=True, timeout=30000,
                                                 env={**os.environ, "HOME": str(client_home)})
            try:
                report["clientBrowser"] = "Chromium " + browser.version
                assert browser.version == "151.0.7922.34", "unexpected QA client browser version"
                page = browser.new_page(viewport={"width": 1920, "height": 1080},
                                        permissions=["clipboard-read", "clipboard-write"])
                page.set_default_timeout(15000)
                page.on("websocket", opened)
                report["navigationOrigins"] = []
                def navigation(request):
                    if request.is_navigation_request():
                        parsed = urlsplit(request.url)
                        origin = parsed.scheme + "://" + parsed.netloc
                        if origin not in report["navigationOrigins"]:
                            report["navigationOrigins"].append(origin)
                page.on("request", navigation)
                checkpoint("open-origin")
                root_response = page.goto(args.origin + "/", wait_until="domcontentloaded", timeout=30000)
                assert root_response is not None and root_response.status == 200
                report["httpsOrigin"] = 200
                checkpoint("open-session")
                response = page.goto(session_url, wait_until="domcontentloaded", timeout=45000)
                assert response is not None and response.status == 200
                report["httpsSessionUI"] = 200
                wait_for_frames(page)
                checkpoint("video-connected")
                page.mouse.click(800, 500)
                page.keyboard.press("Control+l")
                page.keyboard.type("file:///tmp/browser-platform-qa.html", delay=10)
                page.keyboard.press("Enter")
                page.wait_for_timeout(6500)
                page.keyboard.press("Shift+Tab")
                page.keyboard.type("camoufox-", delay=50)
                # This is Selkies' existing virtual-keyboard input path.
                page.locator("#keyboard-input-assist").focus()
                page.keyboard.insert_text("繁體中文")
                page.wait_for_timeout(300)
                checkpoint("unicode-input")
                # Open the native clipboard panel and use its textarea/blur
                # handler, which sends the text through the real WebSocket.
                page.locator('[aria-controls="clipboard-content"]').dispatch_event("click")
                field = page.locator("#dashboardClipboardTextarea")
                field.fill("剪貼簿", force=True)
                field.dispatch_event("blur")
                page.locator("#overlayInput").focus()
                page.wait_for_timeout(300)
                page.keyboard.press("Control+v")
                page.wait_for_timeout(500)
                page.keyboard.press("Control+a")
                page.keyboard.press("Control+c")
                page.wait_for_timeout(800)
                expected = "camoufox-繁體中文剪貼簿"
                report["unicodeInputAndClipboardRoundTrip"] = "pass" if expected in clipboard_received else "fail"
                assert expected in clipboard_received, "the server did not return the expected Unicode input/clipboard text"
                checkpoint("clipboard-verified")
                before = report["websockets"]["binaryFrames"]
                page.set_viewport_size({"width": 1280, "height": 720})
                page.wait_for_timeout(700)
                page.reload(wait_until="domcontentloaded", timeout=30000)
                wait_for_frames(page, before)
                report["reloadReconnect"] = "pass"
                page.set_viewport_size({"width": 1920, "height": 1080})
                page.wait_for_timeout(700)
                page.screenshot(path=str(args.output_dir / "session.png"))
                report["clientViewports"] = [[1920, 1080], [1280, 720], [1920, 1080]]
                report["status"] = "pass"
            finally:
                browser.close()
    except Exception as error:
        report["status"] = "fail"
        # Playwright exceptions may contain the private URL. Remove the URL
        # and query values before retaining a short diagnostic.
        report["errorType"] = type(error).__name__
        message = str(error).replace(session_url, "<session-url>")
        for _, value in parse_qsl(urlsplit(session_url).query):
            if value:
                message = message.replace(value, "<redacted>")
        lines = re.sub(r"(?:https?|wss?)://[^\s]+", "<url>", message).splitlines()
        report["errorSummary"] = (lines[0] if lines else type(error).__name__)[:240]
    report["completedAt"] = datetime.now(timezone.utc).isoformat()
    (args.output_dir / "stream.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
