#!/usr/bin/env python3
"""Real Chromium forms, cookies and Selkies connections against private R5D QA."""

import argparse
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import select
import socket
import socketserver
import threading
from urllib.parse import parse_qs, urlsplit
import uuid

from playwright.sync_api import sync_playwright


class LocalForward(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class LocalRequest(socketserver.BaseRequestHandler):
    def handle(self):
        with socket.socket(socket.AF_UNIX) as upstream:
            upstream.settimeout(5)
            upstream.connect(self.server.socket_path)
            self.request.settimeout(5)
            peers = {self.request: upstream, upstream: self.request}
            try:
                while not self.server.stopping.is_set():
                    ready, _, _ = select.select(list(peers), [], [], .3)
                    for stream in ready:
                        value = stream.recv(65536)
                        if not value:
                            return
                        peers[stream].sendall(value)
            except OSError:
                return


class Client:
    def __init__(self, args, browser, private):
        self.args, self.browser, self.private = args, browser, private
        self.entry, self.session = private["entry_origin"], private["session_origin"]
        self.timer = browser.new_page()
        self.report = {"status": "running", "stage": "initial", "clientBrowser": browser.version,
                       "startedAt": datetime.now(timezone.utc).isoformat(), "checks": [], "backendCapabilityInURL": False}
        self.violations = []
        self.views = []

    def checkpoint(self, stage):
        self.report["stage"] = stage
        (self.args.output / "client-result.json").write_text(json.dumps(self.report, indent=2) + "\n")
        diagnostics = []
        for view in self.views:
            value = {"sid": view["sid"], "state": view["state"]}
            if not view["page"].is_closed():
                try:
                    value["closeEvents"] = view["page"].evaluate("window.__qa_closed || []")
                except Exception:
                    value["closeEventsUnavailable"] = True
            diagnostics.append(value)
        (self.args.output / "display-states.json").write_text(json.dumps(diagnostics, indent=2))
        print("entry_auth_stage=" + stage, flush=True)

    def passed(self, name):
        self.report["checks"].append(name)
        self.checkpoint(name)

    def wait(self, predicate, seconds=15):
        end = time.monotonic() + seconds
        while not predicate():
            if time.monotonic() >= end:
                raise AssertionError("CLIENT_CONDITION_TIMEOUT")
            self.timer.wait_for_timeout(100)

    def action(self, action, **values):
        identifier = uuid.uuid4().hex
        path = self.args.output / "requests" / (identifier + ".json")
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"action": action, **values}))
        temporary.rename(path)
        response = self.args.output / "responses" / path.name
        self.wait(response.exists, seconds=160)
        value = json.loads(response.read_text())
        if value.get("status") != "ok":
            raise AssertionError("HOST_ACTION_FAILED_" + action)
        return value["result"]

    def login(self, account):
        context = self.browser.new_context(viewport={"width": 1280, "height": 800})
        index = context.new_page()
        index.goto(self.entry + "/auth/login", wait_until="domcontentloaded")
        index.locator('input[name="username"]').fill(account["username"])
        index.locator('input[name="password"]').fill(account["password"])
        with index.expect_navigation(wait_until="domcontentloaded"):
            index.locator('form[action="/auth/login"] button').click()
        assert urlsplit(index.url).path == "/", "LOGIN_DID_NOT_REACH_INDEX"
        cookies = [c for c in context.cookies() if c["name"] == "__Host-bp_entry"]
        assert len(cookies) == 1
        cookie = cookies[0]
        assert cookie["secure"] and cookie["httpOnly"] and cookie["sameSite"] == "Lax" and cookie["path"] == "/"
        assert cookie["domain"] == urlsplit(self.entry).hostname
        return {"context": context, "index": index, "account": account}

    def watch(self, page):
        state = {"sockets": [], "binary": 0, "bytes": 0, "tickets": [], "postOrigins": [], "requests": [], "primaryTakeover": False}
        page.add_init_script("""(() => {
            window.__qa_closed = [];
            const Native = window.WebSocket;
            window.WebSocket = class extends Native {
                constructor(...args) { super(...args); this.addEventListener('close', event => {
                    window.__qa_closed.push({code:event.code, reason:event.reason, path:new URL(this.url).pathname});
                }); }
            };
        })();""")
        page.on("request", lambda r: state["requests"].append({"method": r.method, "path": urlsplit(r.url).path,
                                                              "time": time.time(), "event": "request"}))
        page.on("requestfailed", lambda r: state["requests"].append({"method": r.method, "path": urlsplit(r.url).path,
                                                                    "time": time.time(), "event": "failed", "failure": r.failure}))
        def opened(ws):
            value = {"closed": False, "urlPath": urlsplit(ws.url).path, "binary": 0}
            state["sockets"].append(value)
            def frame(payload):
                if isinstance(payload, bytes):
                    state["binary"] += 1
                    state["bytes"] += len(payload)
                    value["binary"] += 1
                elif payload == "KILL a new primary client connected connection killed":
                    state["primaryTakeover"] = True
            ws.on("framereceived", frame)
            ws.on("close", lambda: value.update(closed=True))
        page.on("websocket", opened)
        def response(value):
            parsed = urlsplit(value.url)
            state["requests"].append({"method": value.request.method, "path": parsed.path, "time": time.time(),
                                      "event": "response", "status": value.status})
            keys = set(parse_qs(parsed.query))
            if keys & {"access_token", "token"}:
                self.violations.append("backend-capability-query")
            if parsed.path == "/auth/accept":
                state["tickets"].append(value.url)
            if value.request.method == "POST" and parsed.path.endswith("/start"):
                state["postOrigins"].append(value.request.headers.get("origin"))
            location = value.headers.get("location", "")
            if "access_token" in parse_qs(urlsplit(location).query):
                self.violations.append("backend-capability-location")
        page.on("response", response)
        return state

    def open(self, actor):
        page = actor["context"].new_page()
        state = self.watch(page)
        page.set_default_timeout(20000)
        try:
            page.goto(self.entry + "/browser/" + actor["account"]["profile"] + "/", wait_until="domcontentloaded", timeout=90000)
            self.wait(lambda: urlsplit(page.url).netloc == urlsplit(self.session).netloc, seconds=100)
            self.wait(lambda: state["binary"] >= 2 and state["bytes"] > 1000, seconds=45)
        finally:
            # Full page/URL evidence remains only in the private QA directory.
            identifier = uuid.uuid4().hex
            (self.args.output / ("display-" + identifier + ".json")).write_text(json.dumps(state, indent=2))
            (self.args.output / ("display-" + identifier + ".html")).write_text(page.content())
        assert not self.violations and "access_token" not in page.url
        assert state["postOrigins"] and all(v == self.entry for v in state["postOrigins"])
        sid = urlsplit(page.url).path.split("/")[1]
        assert str(uuid.UUID(sid)) == sid
        cookies = actor["context"].cookies()
        display = [c for c in cookies if c["name"] == "__Host-bp_display_" + sid]
        assert len(display) == 1 and display[0]["secure"] and display[0]["httpOnly"] and display[0]["path"] == "/"
        assert display[0]["domain"] == urlsplit(self.session).hostname and display[0]["sameSite"] == "Lax"
        assert not any(c["name"].startswith(("sealskin_session", "collab_token")) for c in cookies)
        view = {"page": page, "state": state, "sid": sid, "url": page.url}
        self.views.append(view)
        return view

    def closed(self, view):
        return bool(view["state"]["sockets"]) and all(v["closed"] for v in view["state"]["sockets"])

    def fetch(self, index, path, body=None):
        # Login/index CSP deliberately forbids fetch. Exercise real navigation
        # and form submission while retaining the browser's cookie/Origin rules.
        probe = index.context.new_page()
        try:
            if body is None:
                return probe.goto(self.entry + path).status
            probe.goto(self.entry + "/auth/login")
            with probe.expect_navigation() as response:
                probe.evaluate("""({path, body}) => {
                    const form = document.createElement('form'); form.action = path; form.method = 'POST';
                    for (const [name, value] of new URLSearchParams(body)) {
                        const input = document.createElement('input'); input.type = 'hidden';
                        input.name = name; input.value = value; form.append(input);
                    }
                    document.body.append(form); form.submit();
                }""", {"path": path, "body": body})
            return response.value.status
        finally:
            probe.close()

    def run(self):
        accounts = self.private["accounts"]
        self.checkpoint("unauthenticated")
        guest = self.browser.new_context()
        page = guest.new_page()
        page.goto(self.entry + "/auth/login")
        assert self.fetch(page, "/browser/" + accounts[0]["profile"] + "/health") == 401
        assert self.fetch(page, "/browser/" + accounts[0]["profile"] + "/start", "csrf=invalid") == 401
        page.goto(self.entry + "/auth/login")
        page.locator('input[name="username"]').fill(accounts[0]["username"])
        page.locator('input[name="password"]').fill("incorrect-r5d-qa-password")
        with page.expect_navigation() as response:
            page.locator('form[action="/auth/login"] button').click()
        assert response.value.status == 401
        assert self.action("inventory_empty")["empty"]
        guest.close()
        self.passed("unauthenticated-and-wrong-password-no-worker")

        alice, bob = self.login(accounts[0]), self.login(accounts[1])
        for actor, other in ((alice, accounts[1]), (bob, accounts[0])):
            probe = actor["context"].new_page()
            assert probe.goto(self.entry + "/browser/" + other["profile"] + "/").status == 404
            probe.close()
            assert self.fetch(actor["index"], "/browser/" + other["profile"] + "/health") == 404
            assert self.fetch(actor["index"], "/browser/" + actor["account"]["profile"] + "/start", "csrf=wrong") == 403
        assert self.action("inventory_empty")["empty"]
        self.passed("profile-grants-and-csrf")
        self.checkpoint("first-real-display")
        a, b = self.open(alice), self.open(bob)
        baseline = self.action("snapshot", browser_storage=True)
        assert len(baseline["profiles"]) == 2
        self.passed("forms-cookies-private-handoff-and-binary-display")

        for actor, view in ((alice, b), (bob, a)):
            probe = actor["context"].new_page()
            assert probe.goto(view["url"]).status == 401
            probe.close()
        websocket = a["page"].evaluate("""url => new Promise(resolve => {
            const ws = new WebSocket(url); let finished = false;
            const done = value => {if (!finished) {finished = true; resolve(value); ws.close();}};
            ws.onopen = () => done('opened'); ws.onerror = () => done('rejected');
            setTimeout(() => done('timeout'), 4000);
        })""", self.session.replace("https:", "wss:") + "/" + b["sid"] + "/websockets")
        assert websocket == "rejected"
        self.passed("cross-session-http-and-websocket-denied")

        replay = alice["context"].new_page()
        assert a["state"]["tickets"] and replay.goto(a["state"]["tickets"][0]).status == 403
        replay.close()
        old_cookie = next(c["value"] for c in alice["context"].cookies() if c["name"] == "__Host-bp_display_" + a["sid"])
        handoff_context = self.browser.new_context(java_script_enabled=False)
        handoff_context.add_cookies(alice["context"].cookies())
        handoff = handoff_context.new_page()
        # Complete the real form/ticket exchange without starting another
        # Selkies primary controller, which intentionally takes over the old one.
        # An existing Selkies service worker can bypass page routing. A fresh
        # context with scripts disabled fetches the real authorized document,
        # while the entry's ordinary Continue button still submits its form.
        handoff.goto(self.entry + "/browser/" + accounts[0]["profile"] + "/", wait_until="domcontentloaded")
        with handoff.expect_navigation(wait_until="domcontentloaded"):
            handoff.locator('form[action="start"] button').click()
        self.wait(lambda: urlsplit(handoff.url).netloc == urlsplit(self.session).netloc)
        self.timer.wait_for_timeout(1200)
        assert not self.closed(a)
        assert next(c["value"] for c in handoff_context.cookies() if c["name"] == "__Host-bp_display_" + a["sid"]) == old_cookie
        handoff_context.close()
        self.passed("repeated-handoff-preserves-current-display-cookie-and-connection")
        repeated = self.open(alice)
        assert repeated["sid"] == a["sid"]
        self.wait(lambda: self.closed(a) and a["state"]["primaryTakeover"], seconds=6)
        assert self.action("snapshot")["profiles"] == baseline["profiles"]
        self.passed("single-use-ticket-and-selkies-primary-takeover-reuse-generation")

        expired = alice["context"].new_page()
        captured = []
        devtools = alice["context"].new_cdp_session(expired)
        # Pause the actual browser POST's response before Chromium follows its
        # redirect. Page routes do not reliably intercept a redirect chain.
        def capture(event):
            assert event["responseStatusCode"] == 303
            location = next(h["value"] for h in event["responseHeaders"] if h["name"].lower() == "location")
            assert urlsplit(location).path == "/auth/accept"
            captured.append(location)
            devtools.send("Fetch.fulfillRequest", {"requestId": event["requestId"], "responseCode": 200,
                "responseHeaders": [{"name": "Content-Type", "value": "text/html"}],
                "body": base64.b64encode(b"<p>QA ticket retained for expiry check</p>").decode()})
        devtools.on("Fetch.requestPaused", capture)
        devtools.send("Fetch.enable", {"patterns": [{"urlPattern": self.entry + "/browser/" + accounts[0]["profile"] + "/start",
                                                     "requestStage": "Response"}]})
        try:
            expired.goto(self.entry + "/browser/" + accounts[0]["profile"] + "/", wait_until="domcontentloaded")
        except Exception:
            pass
        self.wait(lambda: bool(captured))
        devtools.send("Fetch.disable")
        devtools.detach()
        self.timer.wait_for_timeout((self.private["ticket_seconds"] + 1) * 1000)
        assert expired.goto(captured[0]).status == 403
        expired.close()
        self.passed("expired-ticket-denied")

        with alice["index"].expect_navigation():
            alice["index"].locator('form[action="/auth/logout"] button').click()
        self.wait(lambda: self.closed(a) and self.closed(repeated), seconds=6)
        assert not self.closed(b)
        assert self.action("snapshot")["profiles"] == baseline["profiles"]
        self.passed("logout-closes-own-display-keeps-other-user-and-workers")
        self.action("disable", username=accounts[1]["username"])
        self.wait(lambda: self.closed(b), seconds=6)
        assert self.action("snapshot")["profiles"] == baseline["profiles"]
        self.action("enable", username=accounts[1]["username"])
        self.passed("account-disable-closes-display-keeps-workers")
        alice["context"].close(); bob["context"].close()

        self.action("lifetime", seconds=15)
        expiring = self.login(accounts[0])
        view = self.open(expiring)
        self.wait(lambda: self.closed(view), seconds=20)
        assert self.action("snapshot")["profiles"] == baseline["profiles"]
        self.passed("login-deadline-closes-display-keeps-workers")
        expiring["context"].close()
        self.action("lifetime", seconds=1800)

        actor = self.login(accounts[0])
        view = self.open(actor)
        self.action("binding_change", profile=accounts[0]["profile"])
        self.wait(lambda: self.closed(view), seconds=6)
        self.action("binding_restore", profile=accounts[0]["profile"])
        assert self.action("snapshot")["profiles"] == baseline["profiles"]
        self.passed("binding-change-closes-display-without-lifecycle-mutation")
        view = self.open(actor)
        recovery = self.action("controller_restart")
        assert recovery["sessions_preserved"] and recovery["workers_preserved"]
        view["page"].reload(wait_until="domcontentloaded")
        before = view["state"]["binary"]
        self.wait(lambda: view["state"]["binary"] > before + 1, seconds=30)
        after = self.action("snapshot", browser_storage=True)
        assert after["profiles"] == baseline["profiles"] and after["storage"] == baseline["storage"]
        self.passed("sealed-controller-restart-keeps-session-home-and-browser-storage")
        resumed = self.action("worker_resume", profile=accounts[0]["profile"])
        assert resumed["same_generation"] and resumed["materials_recreated"]
        view["page"].reload(wait_until="domcontentloaded")
        before = view["state"]["binary"]
        self.wait(lambda: view["state"]["binary"] > before + 1, seconds=30)
        after = self.action("snapshot", browser_storage=True)
        assert after["storage"] == baseline["storage"]
        self.passed("worker-resume-rematerializes-auth-and-keeps-browser-storage")
        assert not self.violations
        self.report.update(status="pass", backendCapabilityInURL=False,
            displayBinaryFrames=a["state"]["binary"] + b["state"]["binary"], finishedAt=datetime.now(timezone.utc).isoformat())
        self.checkpoint("complete")


def main(client_class=Client):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--certificate-spki", required=True)
    parser.add_argument("--forward-socket", required=True)
    args = parser.parse_args()
    private = json.loads(args.config.read_text())
    assert args.forward_socket == "/forward/entry.sock"
    forward = LocalForward(("127.0.0.1", 29443), LocalRequest)
    forward.socket_path, forward.stopping = args.forward_socket, threading.Event()
    threading.Thread(target=forward.serve_forever, daemon=True).start()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-proxy-server",
            "--host-resolver-rules=MAP entry.r5d.test 127.0.0.1, MAP session.r5d.test 127.0.0.1",
            "--ignore-certificate-errors-spki-list=" + args.certificate_spki])
        client = client_class(args, browser, private)
        try:
            assert browser.version == "151.0.7922.34"
            client.run()
        except Exception as exc:
            client.report.update(status="fail", errorType=type(exc).__name__)
            client.checkpoint(client.report["stage"])
            raise
        finally:
            browser.close()
            forward.stopping.set()
            forward.shutdown()
            forward.server_close()


if __name__ == "__main__":
    main()
