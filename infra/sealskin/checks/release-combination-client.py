#!/usr/bin/env python3
"""R5E client: real forms, authenticated display and generation-bound gates."""

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import time
from urllib.parse import parse_qs, urlsplit
import uuid

spec = importlib.util.spec_from_file_location("combination_client_base", Path(__file__).with_name("entry-auth-client.py"))
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


class Client(entry.Client):
    def save(self, name, value):
        (self.args.output / (name + ".json")).write_text(json.dumps(value, indent=2) + "\n")

    def open(self, actor):
        page = actor["context"].new_page()
        state = self.watch(page)
        page.set_default_timeout(20000)
        try:
            for attempt in range(4):
                start = len(state["requests"])
                page.goto(self.entry + "/browser/" + actor["account"]["profile"] + "/", wait_until="domcontentloaded", timeout=90000)
                if urlsplit(page.url).netloc != urlsplit(self.session).netloc:
                    button = page.locator('form[action="start"] button')
                    # A blocked-health hint intentionally requires the ordinary
                    # Continue button. Retry only that same, retained generation.
                    if button.count() and page.locator("script[nonce]").count() == 0:
                        with page.expect_navigation(wait_until="domcontentloaded", timeout=90000):
                            button.click()
                self.wait(lambda: urlsplit(page.url).netloc == urlsplit(self.session).netloc or
                          any(r["event"] == "response" and r["method"] == "POST" and r["path"].endswith("/start")
                              and r["status"] >= 400 for r in state["requests"][start:]), seconds=110)
                if urlsplit(page.url).netloc == urlsplit(self.session).netloc:
                    break
                failures = [r for r in state["requests"][start:] if r["event"] == "response" and r["path"].endswith("/start")]
                assert failures and failures[-1]["status"] == 503, "ENTRY_NONRETRYABLE_FAILURE"
                self.timer.wait_for_timeout(10200)
            assert urlsplit(page.url).netloc == urlsplit(self.session).netloc, "COHERENCE_ENTRY_NOT_READY"
            self.wait(lambda: state["binary"] >= 2 and state["bytes"] > 1000, seconds=45)
        finally:
            identifier = uuid.uuid4().hex
            self.save("display-" + identifier, state)
            (self.args.output / ("display-" + identifier + ".html")).write_text(page.content())
        assert not self.violations and not (set(parse_qs(urlsplit(page.url).query)) & {"access_token", "token"})
        assert state["postOrigins"] and all(v == self.entry for v in state["postOrigins"])
        sid = urlsplit(page.url).path.split("/")[1]
        assert str(uuid.UUID(sid)) == sid
        cookies = actor["context"].cookies()
        display = [c for c in cookies if c["name"] == "__Host-bp_display_" + sid]
        assert len(display) == 1 and display[0]["secure"] and display[0]["httpOnly"] and display[0]["sameSite"] == "Lax"
        assert display[0]["domain"] == urlsplit(self.session).hostname and display[0]["path"] == "/"
        assert not any(c["name"].startswith(("sealskin_session", "collab_token")) for c in cookies)
        view = {"page": page, "state": state, "sid": sid, "url": page.url}
        self.views.append(view)
        return view

    def report_valid(self, report, country=None):
        assert report["allowed"] and report["overall"] == "degraded"
        assert report["observed"]["locale"] == "zh-TW" and report["observed"]["timezone"] == "Asia/Taipei"
        assert report["checked_at"] < report["expires_at"] and report["expires_at"] > time.time()
        assert all(row["status"] == "pass" for row in report["checks"] if row["required"])
        if country:
            assert report["exit"]["geoip"]["country"] == country

    def http(self, actor, url):
        # Playwright's APIRequestContext uses its own resolver outside Chromium.
        # Real navigation uses this client's isolated loopback forwarding and
        # pinned certificate. Disable scripts to avoid Selkies primary takeover.
        context = self.browser.new_context(java_script_enabled=False)
        context.add_cookies(actor["context"].cookies())
        try:
            page = context.new_page()
            response = page.goto(url, wait_until="domcontentloaded", timeout=90000)
            result = {"status": response.status, "headers": response.headers, "body": response.text()}
            self.save("http-" + uuid.uuid4().hex, result)
            return result
        finally:
            context.close()

    def display_status(self, actor, view, expected):
        response = self.http(actor, view["url"])
        assert response["status"] == expected
        if expected == 503:
            assert "set-cookie" not in response["headers"]

    def reload(self, view):
        before = view["state"]["binary"]
        view["page"].reload(wait_until="domcontentloaded")
        self.wait(lambda: view["state"]["binary"] > before + 1, seconds=40)

    def base(self):
        accounts = self.private["accounts"]
        self.checkpoint("unauthenticated-and-read-only")
        guest = self.browser.new_context()
        page = guest.new_page()
        page.goto(self.entry + "/auth/login")
        assert self.fetch(page, "/browser/" + accounts[0]["profile"] + "/health") == 401
        assert self.fetch(page, "/browser/" + accounts[0]["profile"] + "/start", "csrf=invalid") == 401
        assert self.action("inventory_empty")["empty"]
        guest.close()
        alice, bob = self.login(accounts[0]), self.login(accounts[1])
        for actor, other in ((alice, accounts[1]), (bob, accounts[0])):
            assert self.fetch(actor["index"], "/browser/" + actor["account"]["profile"] + "/health") == 200
            assert self.fetch(actor["index"], "/browser/" + other["profile"] + "/health") == 404
            assert self.fetch(actor["index"], "/browser/" + actor["account"]["profile"] + "/start", "csrf=wrong") == 403
        assert self.action("inventory_empty")["empty"]
        self.passed("anonymous-read-only-cross-profile-and-csrf-create-no-worker")
        self.checkpoint("real-coherence-gated-display")
        a, b = self.open(alice), self.open(bob)
        baseline = self.action("snapshot", browser_storage=True)
        reports = self.action("reports")
        for account, country in zip(accounts, ("JP", "US")):
            report = reports[account["profile"]]
            self.report_valid(report, country)
            assert self.action("private_gate", profile=account["profile"])["status"] == 200
        assert reports[accounts[0]["profile"]]["nonce"] != reports[accounts[1]["profile"]]["nonce"]
        assert baseline["storage"][accounts[0]["profile"]] != baseline["storage"][accounts[1]["profile"]]
        assert self.action("materials")["r7_and_material_boundaries"]
        self.save("baseline", {"snapshot": baseline, "reports": reports})
        self.passed("C01-C03-r7-zh-TW-Taipei-US-direct-and-JP-secret-proxy")
        for actor, view in ((alice, b), (bob, a)):
            assert self.http(actor, view["url"])["status"] == 401
        websocket = a["page"].evaluate("""url => new Promise(resolve => {
            const ws = new WebSocket(url); let finished = false;
            const done = value => {if (!finished) {finished = true; resolve(value); ws.close();}};
            ws.onopen = () => done('opened'); ws.onerror = () => done('rejected');
            setTimeout(() => done('timeout'), 4000);
        })""", self.session.replace("https:", "wss:") + "/" + b["sid"] + "/websockets")
        assert websocket == "rejected"
        self.passed("authorized-http-binary-websocket-and-cross-session-refusal")
        repeated = self.open(alice)
        assert repeated["sid"] == a["sid"]
        assert self.action("snapshot")["profiles"] == baseline["profiles"]
        self.passed("repeated-authenticated-entry-retains-both-generations")
        for actor, view in ((alice, repeated), (bob, b)):
            response = self.http(actor, self.entry + "/browser/" + actor["account"]["profile"] + "/health")
            assert response["status"] == 200 and view["sid"] not in response["body"] and "access_token" not in response["body"]
        self.passed("public-health-removes-session-capability-and-identity")
        with alice["index"].expect_navigation():
            alice["index"].locator('form[action="/auth/logout"] button').click()
        self.wait(lambda: self.closed(repeated), seconds=6)
        assert not self.closed(b) and self.action("snapshot")["profiles"] == baseline["profiles"]
        alice = self.login(accounts[0])
        self.open(alice)
        after = self.action("snapshot", browser_storage=True)
        assert after == baseline
        self.passed("logout-revokes-display-keeps-workers-store-and-browser-data")

    def faults(self):
        accounts = self.private["accounts"]
        alice, bob = self.login(accounts[0]), self.login(accounts[1])
        a, b = self.open(alice), self.open(bob)
        baseline = self.action("snapshot", browser_storage=True)
        before = self.action("reports")
        self.checkpoint("geoip-data-source-failure")
        unknown = self.action("geoip", unavailable=True)
        for actor, view in ((alice, a), (bob, b)):
            profile = actor["account"]["profile"]
            assert not unknown[profile]["allowed"] and unknown[profile]["overall"] == "unknown"
            self.display_status(actor, view, 503)
            private = self.action("private_gate", profile=profile)
            assert private["status"] == 503 and not private["set_cookie"]
        self.passed("C04-missing-GeoIP-blocks-login-cookie-and-private-capability")
        restored = self.action("geoip", unavailable=False)
        for actor, view in ((alice, a), (bob, b)):
            profile = actor["account"]["profile"]
            self.report_valid(restored[profile])
            assert restored[profile]["binding"] == before[profile]["binding"]
            self.display_status(actor, view, 200)
            self.reload(view)
        assert self.action("snapshot", browser_storage=True) == baseline
        self.passed("GeoIP-recovery-retains-login-generation-and-browser-data")
        self.checkpoint("sealed-controller-restart")
        result = self.action("controller_restart")
        assert result["sessions_preserved"] and result["workers_preserved"]
        self.reload(a)
        self.reload(b)
        assert self.action("snapshot", browser_storage=True) == baseline
        self.passed("sealed-control-restart-with-Store-and-coherence")
        self.resume_steps(accounts, alice, bob, a, b, baseline)
        self.save("faults-baseline", baseline)

    def resume_steps(self, accounts, alice, bob, a, b, baseline):
        self.checkpoint("display-and-proxy-tmpfs-loss")
        resumed = self.action("resume_combined", profile=accounts[0]["profile"])
        assert resumed["same_generation"] and resumed["display_and_store_rematerialized"]
        self.report_valid(resumed["fresh_report"])
        self.display_status(alice, a, 401)
        old_sid = a["sid"]
        a = self.open(alice)
        assert a["sid"] == old_sid
        after = self.action("snapshot", browser_storage=True)
        assert after["storage"] == baseline["storage"]
        for profile in baseline["profiles"]:
            assert after["profiles"][profile]["worker"] == baseline["profiles"][profile]["worker"]
            assert after["profiles"][profile]["session"] == baseline["profiles"][profile]["session"]
        self.passed("same-generation-resume-recreates-materials-and-requires-fresh-display-handoff")
        self.checkpoint("actual-gate-expiry")
        expired = self.action("expiry", profile=accounts[0]["profile"])
        assert expired["closed_on_expiry"] and expired["same_generation"] and expired["fresh_nonce"]
        self.action("reports")
        self.reload(a)
        self.reload(b)
        assert self.action("snapshot", browser_storage=True)["storage"] == baseline["storage"]
        self.passed("C04-real-expiry-closes-existing-website-tunnel-and-recovers")
        self.save("resume-baseline", baseline)

    def resume(self):
        accounts = self.private["accounts"]
        alice, bob = self.login(accounts[0]), self.login(accounts[1])
        a, b = self.open(alice), self.open(bob)
        baseline = self.action("snapshot", browser_storage=True)
        self.resume_steps(accounts, alice, bob, a, b, baseline)

    def blocked_start(self, actor, expected_status=503, require_no_display_cookie=True):
        page = actor["context"].new_page()
        replies = []
        page.on("response", lambda response: replies.append({"status": response.status, "headers": response.headers})
                if response.request.method == "POST" and urlsplit(response.url).path.endswith("/start") else None)
        try:
            page.goto(self.entry + "/browser/" + actor["account"]["profile"] + "/", wait_until="domcontentloaded", timeout=90000)
            button = page.locator('form[action="start"] button')
            if button.count() and page.locator("script[nonce]").count() == 0:
                with page.expect_navigation(wait_until="domcontentloaded", timeout=90000):
                    button.click()
            self.wait(lambda: bool(replies), seconds=110)
            self.save("blocked-start-" + uuid.uuid4().hex, {"responses": replies, "body": page.content()})
            assert replies[-1]["status"] == expected_status and "location" not in replies[-1]["headers"]
            assert "set-cookie" not in replies[-1]["headers"]
            if require_no_display_cookie:
                assert not any(c["name"].startswith("__Host-bp_display_") for c in actor["context"].cookies())
        finally:
            page.close()

    def policies(self):
        accounts = self.private["accounts"]
        for variant, code in (("strict-timezone", "COHERENCE_TIMEZONE_MISMATCH"),
                              ("strict-country", "COHERENCE_COUNTRY_MISMATCH"), ("advisory", None)):
            self.checkpoint("policy-" + variant)
            self.action("configure", variant=variant)
            alice, bob = self.login(accounts[0]), self.login(accounts[1])
            if code:
                self.blocked_start(alice)
            else:
                a = self.open(alice)
            b = self.open(bob)
            report = self.action("report", profile=accounts[0]["profile"], allowed=not bool(code), address="188.253.118.223")
            self.save("policy-" + variant, report)
            assert report["observed"]["timezone"] == "Asia/Taipei" and report["observed"]["locale"] == "zh-TW"
            assert report["expected"]["timezone"] == "Asia/Taipei" and report["exit"]["geoip"]["country"] == "JP"
            if code:
                assert report["overall"] == "unhealthy" and report["code"] == "COHERENCE_FAILED"
                assert any(c["code"] == code and c["status"] == "fail" and c["required"] for c in report["checks"])
                self.blocked_start(alice)
                assert self.action("private_gate", profile=accounts[0]["profile"])["status"] == 503
            else:
                self.report_valid(report, "JP")
                for name in ("country", "allowed_timezone"):
                    row = next(c for c in report["checks"] if c["name"] == name)
                    assert row["status"] == "warn" and not row["required"]
                self.display_status(alice, a, 200)
            self.display_status(bob, b, 200)
            self.report_valid(self.action("report", profile=accounts[1]["profile"], allowed=True), "US")
            self.passed("C02-" + variant + "-keeps-frozen-environment-and-other-profile")
            alice["context"].close()
            bob["context"].close()
        self.action("configure", variant="baseline")

    def rotation(self):
        accounts = self.private["accounts"]
        a_id, b_id = (a["profile"] for a in accounts)
        self.action("configure", variant="rotation")
        self.action("endpoint", operation="rotation", value="local")
        self.action("endpoint", operation="mode", value="online")
        alice, bob = self.login(accounts[0]), self.login(accounts[1])
        a, b = self.open(alice), self.open(bob)
        baseline = self.action("snapshot", browser_storage=True)
        before = self.action("reports")
        for report in before.values():
            self.report_valid(report, "JP")
        assert before[a_id]["nonce"] != before[b_id]["nonce"]
        for field in ("operation_id", "session_id", "profile_id", "home_name", "worker_id", "relay_id", "guard_id"):
            assert before[a_id]["binding"][field] != before[b_id]["binding"][field]
        self.save("rotation-baseline", {"snapshot": baseline, "reports": before})
        self.passed("C05-two-Store-backed-Profiles-share-one-proxy-with-independent-reports")
        self.checkpoint("rotation-outage")
        self.action("endpoint", operation="mode", value="offline")
        unknown = self.action("reports", allowed=False)
        histories = self.action("histories")
        for profile, report in unknown.items():
            assert report["overall"] == "unknown" and not report["allowed"]
            assert histories[profile]["observation"]["browser_ip"] == "188.253.118.223"
            assert histories[profile]["observation"]["checked_at"] <= report["checked_at"]
            assert self.action("private_gate", profile=profile)["status"] == 503
        self.display_status(alice, a, 503)
        self.display_status(bob, b, 503)
        self.save("rotation-unavailable", {"reports": unknown, "histories": histories})
        self.passed("C05-UNKNOWN-retains-each-actual-exit-history-and-blocks-authorized-display")
        self.action("endpoint", operation="rotation", value="peer")
        self.action("endpoint", operation="mode", value="online")
        rotated = {profile: self.action("report", profile=profile, allowed=profile == a_id, address="202.155.153.31")
                   for profile in (a_id, b_id)}
        for profile, report in rotated.items():
            assert report["exit"]["geoip"]["country"] == "HK" and report["binding"] == before[profile]["binding"]
            assert report["expected"] == before[profile]["expected"] and report["observed"]["locale"] == "zh-TW"
        self.report_valid(rotated[a_id], "HK")
        assert rotated[a_id]["nonce"] != rotated[b_id]["nonce"]
        assert rotated[b_id]["overall"] == "unhealthy" and rotated[b_id]["exit_change_blocked"]
        self.display_status(alice, a, 200)
        self.display_status(bob, b, 503)
        assert self.action("private_gate", profile=b_id)["status"] == 503
        current = self.action("snapshot_one", profile=a_id, browser_storage=True)
        assert current["storage"] == baseline["storage"][a_id]
        self.save("rotation-HK", rotated)
        self.passed("C05-actual-HK-recheck-allows-and-block-latches-after-UNKNOWN")
        self.action("endpoint", operation="rotation", value="local")
        returned = {profile: self.action("report", profile=profile, allowed=profile == a_id, address="188.253.118.223")
                    for profile in (a_id, b_id)}
        assert returned[b_id]["exit_change_blocked"] and returned[b_id]["overall"] == "unhealthy"
        self.display_status(bob, b, 503)
        self.action("stop_profile", profile=b_id)
        new_b = self.open(bob)
        reset = self.action("report", profile=b_id, allowed=True, address="188.253.118.223")
        self.report_valid(reset, "JP")
        assert not reset.get("exit_change_blocked", False)
        for field in ("operation_id", "session_id", "worker_id", "relay_id", "guard_id"):
            assert reset["binding"][field] != before[b_id]["binding"][field]
        after = self.action("snapshot", browser_storage=True)
        assert after["storage"] == baseline["storage"] and new_b["sid"] != b["sid"]
        self.save("rotation-reset", {"returned": returned, "reset": reset, "snapshot": after})
        self.passed("C05-return-keeps-block-normal-new-generation-recovers-same-Home-data")
        self.action("stop_all")

    def revocation(self):
        accounts = self.private["accounts"]
        a_id, b_id = (a["profile"] for a in accounts)
        self.action("configure", variant="revocation")
        alice, bob = self.login(accounts[0]), self.login(accounts[1])
        a, b = self.open(alice), self.open(bob)
        baseline = self.action("snapshot", browser_storage=True)
        self.action("reports")
        self.checkpoint("Store-revocation-existing-browser-connections")
        revoked = self.action("revoke", profile=a_id)
        assert revoked["revoked"] and revoked["browser_ws_and_wss_closed"] and revoked["worker_wire_has_no_direct_fallback"]
        self.wait(lambda: self.closed(a), seconds=6)
        self.display_status(bob, b, 200)
        other = self.action("snapshot_one", profile=b_id, browser_storage=True)
        assert other["identity"] == baseline["profiles"][b_id] and other["storage"] == baseline["storage"][b_id]
        self.passed("Store-revocation-closes-WS-WSS-and-blocks-browser-and-native-fallback")
        self.blocked_start(alice, expected_status=502, require_no_display_cookie=False)
        assert not any(self.action("inventory_counts", profile=a_id).values())
        self.passed("revoked-current-revision-cannot-create-new-worker")
        self.action("configure", variant="recovery")
        alice, bob = self.login(accounts[0]), self.login(accounts[1])
        self.open(alice)
        self.open(bob)
        self.action("reports")
        after = self.action("snapshot", browser_storage=True)
        assert after["storage"] == baseline["storage"]
        self.save("revocation-recovered-v2", after)
        self.passed("new-unrevoked-Store-revision-retains-both-Home-datasets")

    def recovered(self):
        accounts = self.private["accounts"]
        expected = self.private["recovery_expected"]
        a_id, b_id = (a["profile"] for a in accounts)
        assert self.action("inventory_empty")["empty"]
        denied = self.browser.new_context()
        page = denied.new_page()
        page.goto(self.entry + "/auth/login")
        page.locator('input[name="username"]').fill(accounts[1]["username"])
        page.locator('input[name="password"]').fill(accounts[1]["password"])
        with page.expect_navigation() as response:
            page.locator('form[action="/auth/login"] button').click()
        assert response.value.status == 401
        denied.close()
        assert self.action("inventory_empty")["empty"]
        self.passed("post-backup-account-disable-survives-encrypted-restoration")
        alice = self.login(accounts[0])
        a = self.open(alice)
        report = self.action("report", profile=a_id, allowed=True, address="188.253.118.223")
        self.report_valid(report, "JP")
        actual = self.action("snapshot_one", profile=a_id, browser_storage=True)
        assert actual["storage"] == expected["storage"]
        assert actual["identity"]["home"] == expected["source_home"]
        for field in ("worker", "session", "operation"):
            assert actual["identity"][field] != expected["original_identity"][field]
        assert actual["identity"]["image"] == expected["original_identity"]["image"]
        assert not any(self.action("inventory_counts", profile=b_id).values())
        assert self.action("materials", profile=a_id)["r7_and_material_boundaries"]
        assert self.action("private_gate", profile=a_id)["status"] == 200
        self.display_status(alice, a, 200)
        self.reload(a)
        self.save("recovered-browser", {"actual": actual, "report": report, "expected": expected})
        self.passed("S05-new-private-root-restores-r7-Store-assets-login-and-three-browser-stores")
        self.action("stop_all")

    def run(self):
        phase = self.private["combination_phase"]
        assert phase in {"base", "faults", "resume", "policies", "rotation", "revocation", "recovered"}
        getattr(self, phase)()
        assert not self.violations
        self.report.update(status="pass", backendCapabilityInURL=False, finishedAt=datetime.now(timezone.utc).isoformat())
        self.checkpoint("complete")


if __name__ == "__main__":
    entry.main(Client)
