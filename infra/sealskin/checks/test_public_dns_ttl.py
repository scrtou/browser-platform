"""Tool validation with loopback DNS only; this is not public DNS acceptance."""

import contextlib
import importlib.util
import io
import json
import shutil
import socketserver
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import dns.flags
import dns.message
import dns.query
import dns.rdatatype
import dns.rrset

SOURCE = Path(__file__).with_name("check-public-dns-ttl.py")
SPEC = importlib.util.spec_from_file_location("public_dns_ttl", SOURCE)
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)


def config():
    # These are symbolic endpoints routed to loopback exclusively by the test.
    return {"zone": "r5c2.fixture.example.org", "ttl_seconds": 30,
            "parent_authority_ipv4": "8.8.4.4",
            "authorities": [{"name": "ns1.r5c2.fixture.example.org", "ipv4": "9.9.9.9"},
                            {"name": "ns2.r5c2.fixture.example.org", "ipv4": "149.112.112.112"}],
            "paths": {key: {"resolver_id": "fixture-" + key, "resolver_ipv4": "8.8.8.8",
                            "before_ipv4": "1.1.1.1", "after_ipv4": "1.0.0.1"} for key in sorted(TOOL.PATHS)}}


class Clock:
    def __init__(self, value):
        self.value = value

    def time(self):
        self.value += 0.001
        return self.value

    def monotonic(self):
        return time.monotonic()


class Fixture:
    def __init__(self, multiple_caches=False):
        self.config = config()
        self.phase = "before"
        self.servers = []
        self.ports = {}
        self.calls = []
        self.multiple_caches = multiple_caches
        self.cache_counts = {}

    def reply(self, payload, endpoint, tcp):
        request = dns.message.from_wire(payload)
        response = dns.message.make_response(request)
        q = request.question[0]
        qname, qtype = q.name.to_text(), dns.rdatatype.to_text(q.rdtype)
        self.calls.append((endpoint, qname, qtype, tcp))
        resolver = endpoint == "8.8.8.8"
        parent = endpoint == self.config["parent_authority_ipv4"]
        response.flags |= dns.flags.RA if resolver else 0 if parent else dns.flags.AA
        if resolver and qname.startswith("bootstrap-") and not tcp:
            response.flags |= dns.flags.TC
            return response.to_wire()
        zone = TOOL.name(self.config["zone"])
        if qtype == "NS":
            records = dns.rrset.from_text(zone, 30, "IN", "NS", *[TOOL.name(a["name"]) for a in self.config["authorities"]])
            (response.authority if parent else response.answer).append(records)
            if parent:
                for authority in self.config["authorities"]:
                    response.additional.append(dns.rrset.from_text(TOOL.name(authority["name"]), 30, "IN", "A", authority["ipv4"]))
        elif qtype == "SOA":
            response.answer.append(dns.rrset.from_text(zone, 30, "IN", "SOA", f"ns1.{zone} hostmaster.{zone} 1 60 60 300 30"))
        else:
            authority = next((a for a in self.config["authorities"] if TOOL.name(a["name"]) == qname), None)
            if authority:
                endpoint_address, ttl = authority["ipv4"], 30
            else:
                old = self.phase == "before" or (resolver and self.phase == "cached")
                endpoint_address = "1.1.1.1" if old else "1.0.0.1"
                ttl = 20 if resolver and self.phase == "cached" else 30
                if resolver and self.multiple_caches:
                    key = self.phase, qname
                    index = self.cache_counts.get(key, 0)
                    self.cache_counts[key] = index + 1
                    if self.phase == "before":
                        ttl = (30, 28)[index % 2]
                    elif self.phase == "cached":
                        ttl = (18, 20)[index % 2]
            response.answer.append(dns.rrset.from_text(qname, ttl, "IN", "A", endpoint_address))
        return response.to_wire()

    def __enter__(self):
        fixture = self

        class UDP(socketserver.BaseRequestHandler):
            def handle(self):
                payload, sock = self.request
                sock.sendto(fixture.reply(payload, self.server.endpoint, False), self.client_address)

        class TCP(socketserver.StreamRequestHandler):
            def handle(self):
                size = struct.unpack("!H", self.rfile.read(2))[0]
                reply = fixture.reply(self.rfile.read(size), self.server.endpoint, True)
                self.wfile.write(struct.pack("!H", len(reply)) + reply)

        endpoints = [self.config["parent_authority_ipv4"], "8.8.8.8"] + [a["ipv4"] for a in self.config["authorities"]]
        for endpoint in endpoints:
            self.ports[endpoint] = {}
            for transport, server_type, handler in [("udp", socketserver.ThreadingUDPServer, UDP),
                                                     ("tcp", socketserver.ThreadingTCPServer, TCP)]:
                server = server_type(("127.0.0.1", 0), handler)
                server.daemon_threads = True
                server.endpoint = endpoint
                thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
                thread.start()
                self.servers.append((server, thread))
                self.ports[endpoint][transport] = server.server_address[1]
        return self

    def __exit__(self, *args):
        for server, thread in self.servers:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def transport(self, original, kind):
        def send(request, endpoint, **kwargs):
            if endpoint not in self.ports:
                raise RuntimeError("Test attempted an unconfigured DNS endpoint")
            return original(request, "127.0.0.1", port=self.ports[endpoint][kind], **kwargs)
        return send


def quiet(call, *args):
    with contextlib.redirect_stdout(io.StringIO()):
        return call(*args)


def rewire(value, change):
    message = dns.message.from_wire(bytes.fromhex(value["wire_hex"]), one_rr_per_rrset=True)
    change(message)
    encoded = message.to_wire().hex()
    value["wire_hex"] = encoded
    value["records"] = TOOL.record_list(TOOL.wire(encoded))
    value["authoritative"] = bool(message.flags & dns.flags.AA)


def shift_times(value, seconds):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ("started_at", "received_at", "finished_at"):
                value[key] += seconds
            else:
                shift_times(child, seconds)
    elif isinstance(value, list):
        for child in value:
            shift_times(child, seconds)


class PublicDNSEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="public-dns-tool-tests-")
        root = Path(cls.directory.name)
        config_file = root / "config.json"
        config_file.write_text(json.dumps(config()))
        cls.baseline = root / "baseline"
        clock = Clock(900)
        udp, tcp = dns.query.udp, dns.query.tcp
        with Fixture() as fixture, mock.patch.object(TOOL, "time", clock), \
                mock.patch.object(dns.query, "udp", fixture.transport(udp, "udp")), \
                mock.patch.object(dns.query, "tcp", fixture.transport(tcp, "tcp")):
            quiet(TOOL.prepare, config_file, cls.baseline)
            for phase, stamp in [("before", 1000), ("cached", 1010), ("expired", 1032)]:
                fixture.phase, clock.value = phase, stamp
                quiet(TOOL.sample, cls.baseline, phase)
            cls.wire_calls = list(fixture.calls)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def setUp(self):
        self.run = Path(self.directory.name) / self.id().split(".")[-1]
        shutil.copytree(self.baseline, self.run)

    def mutate(self, phase, action):
        path = self.run / (phase + ".json")
        value = json.loads(path.read_text())
        action(value)
        path.write_text(json.dumps(value))

    def rejected(self):
        with self.assertRaises((TOOL.EvidenceError, KeyError, TypeError, ValueError)):
            quiet(TOOL.verify, self.run)
        self.assertFalse((self.run / "verification.json").exists())

    def test_real_udp_tcp_three_phase_roundtrip_remains_partial(self):
        self.assertTrue(any(call[3] for call in self.wire_calls))
        self.assertTrue(any(not call[3] for call in self.wire_calls))
        result = quiet(TOOL.verify, self.run)
        self.assertEqual(result["result"], "PARTIAL")
        self.assertEqual(result["delegation_and_recursive_ttl"], "PASS")
        self.assertEqual(result["public_N04_N08"], "NOT_COMPLETE")
        self.assertEqual(set(result["evidence_sha256"]), set(TOOL.PHASES))

    def test_missing_delegation(self):
        self.mutate("cached", lambda v: v.update(delegation={}))
        self.rejected()

    def test_empty_authority(self):
        self.mutate("before", lambda v: v["paths"]["direct"].update(authority=[]))
        self.rejected()

    def test_partial_authority_set(self):
        self.mutate("cached", lambda v: v["paths"]["bootstrap"]["authority"].pop())
        self.rejected()

    def test_duplicate_authority(self):
        self.mutate("expired", lambda v: v["paths"]["upstream"].update(authority=[v["paths"]["upstream"]["authority"][0]] * 2))
        self.rejected()

    def test_wrong_authority_endpoint(self):
        self.mutate("cached", lambda v: v["paths"]["direct"]["authority"][0].update(server="8.8.8.8"))
        self.rejected()

    def test_missing_child_evidence(self):
        self.mutate("before", lambda v: v["delegation"].update(children=[]))
        self.rejected()

    def test_missing_parent_glue(self):
        self.mutate("cached", lambda v: rewire(v["delegation"]["parent"], lambda m: m.additional.clear()))
        self.rejected()

    def test_wrong_parent_delegation(self):
        self.mutate("before", lambda v: rewire(v["delegation"]["parent"], lambda m: m.authority.clear()))
        self.rejected()

    def test_non_authoritative_child_soa(self):
        self.mutate("expired", lambda v: rewire(v["delegation"]["children"][0]["soa"], lambda m: setattr(m, "flags", m.flags & ~dns.flags.AA)))
        self.rejected()

    def test_missing_request_wire(self):
        self.mutate("before", lambda v: v["paths"]["upstream"]["recursive"].pop("query_wire_hex"))
        self.rejected()

    def test_missing_response_wire(self):
        self.mutate("before", lambda v: v["paths"]["upstream"]["recursive"].update(wire_hex=""))
        self.rejected()

    def test_wire_trailing_data(self):
        def damage(v):
            value = v["paths"]["direct"]["recursive"]
            value["wire_hex"] += "00"
        self.mutate("cached", damage)
        self.rejected()

    def test_wrong_transaction_id(self):
        self.mutate("cached", lambda v: rewire(v["paths"]["direct"]["recursive"], lambda m: setattr(m, "id", m.id ^ 1)))
        self.rejected()

    def test_record_metadata_differs_from_wire(self):
        self.mutate("cached", lambda v: v["paths"]["direct"]["recursive"]["records"][0].update(ttl=19))
        self.rejected()

    def test_tcp_fallback_without_validated_truncation(self):
        self.mutate("cached", lambda v: v["paths"]["bootstrap"]["recursive"].update(truncated_response_wire_hex=None))
        self.rejected()

    def test_resolver_without_recursion_available(self):
        self.mutate("cached", lambda v: rewire(v["paths"]["direct"]["recursive"], lambda m: setattr(m, "flags", m.flags & ~dns.flags.RA)))
        self.rejected()

    def test_authoritative_answer_is_not_recursive_cache_evidence(self):
        self.mutate("cached", lambda v: rewire(v["paths"]["direct"]["recursive"], lambda m: setattr(m, "flags", m.flags | dns.flags.AA)))
        self.rejected()

    def test_cached_ttl_does_not_decay(self):
        self.mutate("cached", lambda v: rewire(v["paths"]["direct"]["recursive"], lambda m: setattr(m.answer[0], "ttl", 30)))
        self.rejected()

    def test_cached_ttl_expires_at_different_time(self):
        self.mutate("cached", lambda v: rewire(v["paths"]["direct"]["recursive"], lambda m: setattr(m.answer[0], "ttl", 1)))
        self.rejected()

    def test_expired_phase_starts_too_early(self):
        self.mutate("expired", lambda v: shift_times(v, -2))
        self.rejected()

    def test_cached_phase_occurs_after_expiry(self):
        self.mutate("cached", lambda v: shift_times(v, 25))
        self.mutate("expired", lambda v: shift_times(v, 25))
        self.rejected()

    def test_overlapping_phases(self):
        self.mutate("cached", lambda v: v.update(started_at=1000))
        self.rejected()

    def test_sampling_origin_changed(self):
        self.mutate("cached", lambda v: v["origin"].update(network_namespace="net:[123]"))
        self.rejected()

    def test_nonfinite_timestamp(self):
        self.mutate("cached", lambda v: v["paths"]["direct"]["recursive"].update(received_at=float("nan")))
        self.rejected()

    def test_wrong_resolver_identity(self):
        self.mutate("expired", lambda v: v["paths"]["direct"].update(resolver_id="unapproved"))
        self.rejected()

    def test_missing_path(self):
        self.mutate("cached", lambda v: v["paths"].pop("bootstrap"))
        self.rejected()

    def test_changed_plan_binding(self):
        self.mutate("before", lambda v: v.update(plan_sha256="0" * 64))
        self.rejected()

    def test_legacy_evidence_is_not_silently_accepted(self):
        self.mutate("before", lambda v: v.update(version=1))
        self.rejected()

    def test_optimized_interpreter_accepts_valid_and_rejects_incomplete_evidence(self):
        result = subprocess.run([sys.executable, "-O", str(SOURCE), "verify", "--run", str(self.run)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["result"], "PARTIAL")
        (self.run / "verification.json").unlink()
        self.mutate("cached", lambda v: v["paths"]["direct"].update(authority=[]))
        result = subprocess.run([sys.executable, "-O", str(SOURCE), "verify", "--run", str(self.run)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stderr)["result"], "REJECTED")
        self.assertFalse((self.run / "verification.json").exists())

    def test_existing_phase_is_rejected_before_network_queries(self):
        with mock.patch.object(TOOL, "query") as query:
            with self.assertRaises(TOOL.EvidenceError):
                quiet(TOOL.sample, self.run, "before")
            query.assert_not_called()

    def test_failed_sampling_keeps_evidence_and_rejects_retry(self):
        (self.run / "before.json").unlink()
        with mock.patch.object(TOOL, "query", side_effect=dns.exception.Timeout) as query:
            with self.assertRaises(dns.exception.Timeout):
                quiet(TOOL.sample, self.run, "before")
            failure = json.loads((self.run / "before.failed.json").read_text())
            self.assertEqual(failure["failure"], "Timeout")
            self.assertFalse((self.run / "before.json").exists())
            with self.assertRaises(TOOL.EvidenceError):
                quiet(TOOL.sample, self.run, "before")
            self.assertEqual(query.call_count, 1)

    def test_verification_does_not_overwrite_prior_result(self):
        quiet(TOOL.verify, self.run)
        output = (self.run / "verification.json").read_bytes()
        with self.assertRaises(TOOL.EvidenceError):
            quiet(TOOL.verify, self.run)
        self.assertEqual((self.run / "verification.json").read_bytes(), output)

    def test_placeholder_rejected_before_queries(self):
        (self.run / "before.json").unlink()
        path = self.run / "plan.json"
        plan = json.loads(path.read_text())
        plan["config"]["zone"] = "dns.example.invalid"
        path.write_text(json.dumps(plan))
        with mock.patch.object(TOOL, "query") as query:
            with self.assertRaises(TOOL.EvidenceError):
                quiet(TOOL.sample, self.run, "before")
            query.assert_not_called()


class MultipleCacheEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="public-dns-cache-set-tests-")
        root = Path(cls.directory.name)
        config_file = root / "config.json"
        config_file.write_text(json.dumps(config()))
        cls.baseline = root / "baseline"
        clock = Clock(900)
        udp, tcp = dns.query.udp, dns.query.tcp
        with Fixture(multiple_caches=True) as fixture, mock.patch.object(TOOL, "time", clock), \
                mock.patch.object(dns.query, "udp", fixture.transport(udp, "udp")), \
                mock.patch.object(dns.query, "tcp", fixture.transport(tcp, "tcp")):
            quiet(TOOL.prepare, config_file, cls.baseline, 4)
            for phase, stamp in [("before", 1000), ("cached", 1010), ("expired", 1032)]:
                fixture.phase, clock.value = phase, stamp
                quiet(TOOL.sample, cls.baseline, phase)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def setUp(self):
        self.run = Path(self.directory.name) / self.id().split(".")[-1]
        shutil.copytree(self.baseline, self.run)

    def mutate(self, phase, action):
        path = self.run / (phase + ".json")
        value = json.loads(path.read_text())
        action(value)
        path.write_text(json.dumps(value))

    def rejected(self):
        with self.assertRaises((TOOL.EvidenceError, KeyError, TypeError, ValueError)):
            quiet(TOOL.verify, self.run)
        self.assertFalse((self.run / "verification.json").exists())

    def test_every_cached_reply_matches_a_previously_observed_expiry(self):
        before = TOOL.load(self.run / "before.json")["paths"]["direct"]["recursive_samples"]
        cached = TOOL.load(self.run / "cached.json")["paths"]["direct"]["recursive_samples"]
        self.assertEqual([r["records"][0]["ttl"] for r in before], [30, 28, 30, 28])
        self.assertEqual([r["records"][0]["ttl"] for r in cached], [18, 20, 18, 20])
        result = quiet(TOOL.verify, self.run)
        self.assertEqual(result["result"], "PARTIAL")
        self.assertEqual(result["evidence_version"], 3)
        self.assertEqual(result["cache_observations_per_path_phase"], 4)

    def test_missing_sample_set_rejected(self):
        self.mutate("cached", lambda v: v["paths"]["direct"].pop("recursive_samples"))
        self.rejected()

    def test_dropping_one_observation_rejected(self):
        self.mutate("cached", lambda v: v["paths"]["direct"]["recursive_samples"].pop())
        self.rejected()

    def test_primary_alias_cannot_hide_a_different_observation(self):
        def change(v):
            v["paths"]["direct"]["recursive"] = v["paths"]["direct"]["recursive_samples"][1]
        self.mutate("cached", change)
        self.rejected()

    def test_one_refreshed_extra_sample_fails_the_entire_set(self):
        self.mutate("cached", lambda v: rewire(v["paths"]["direct"]["recursive_samples"][2],
                                               lambda m: setattr(m.answer[0], "ttl", 30)))
        self.rejected()

    def test_decreased_ttl_with_an_unobserved_expiry_is_rejected(self):
        self.mutate("cached", lambda v: rewire(v["paths"]["direct"]["recursive_samples"][2],
                                               lambda m: setattr(m.answer[0], "ttl", 22)))
        self.rejected()

    def test_one_new_address_cannot_be_ignored(self):
        def change(message):
            qname = message.question[0].name.to_text()
            message.answer = [dns.rrset.from_text(qname, 18, "IN", "A", "1.0.0.1")]
        self.mutate("cached", lambda v: rewire(v["paths"]["direct"]["recursive_samples"][2], change))
        self.rejected()

    def test_each_extra_wire_response_is_revalidated(self):
        self.mutate("cached", lambda v: v["paths"]["direct"]["recursive_samples"][2].update(wire_hex="00"))
        self.rejected()

    def test_each_extra_resolver_endpoint_is_revalidated(self):
        self.mutate("cached", lambda v: v["paths"]["direct"]["recursive_samples"][2].update(server="1.1.1.1"))
        self.rejected()

    def test_repeated_sample_cannot_fake_complete_sequential_observations(self):
        def change(value):
            rows = value["paths"]["direct"]["recursive_samples"]
            rows[1] = rows[0]
        self.mutate("cached", change)
        self.rejected()

    def test_expired_phase_waits_for_the_latest_observed_expiry(self):
        self.mutate("expired", lambda v: shift_times(v, -2))
        self.rejected()

    def test_version_downgrade_cannot_ignore_the_sample_count(self):
        plan = TOOL.load(self.run / "plan.json")
        plan["version"] = 1
        with self.assertRaises(TOOL.EvidenceError):
            TOOL.validate_plan(plan)

    def test_evidence_version_is_bound_to_the_plan_mode(self):
        self.mutate("cached", lambda v: v.update(version=2))
        self.rejected()

    def test_sample_count_is_bounded_and_not_boolean(self):
        plan = TOOL.load(self.run / "plan.json")
        for count in (True, 1, 33):
            with self.subTest(count=count):
                plan["cache_observations"] = count
                with self.assertRaises(TOOL.EvidenceError):
                    TOOL.validate_plan(plan)


class QueryBudgetTests(unittest.TestCase):
    def test_udp_and_tcp_share_the_total_budget(self):
        clock = mock.Mock()
        clock.monotonic.side_effect = [0, 4, 6]
        clock.time.return_value = 1000

        def response(request, server, **kwargs):
            value = dns.message.make_response(request)
            value.flags |= dns.flags.TC
            return value

        def final(request, server, **kwargs):
            self.assertEqual(kwargs["timeout"], 1)
            return dns.message.make_response(request)

        with mock.patch.object(TOOL, "time", clock), mock.patch.object(dns.query, "udp", response), \
                mock.patch.object(dns.query, "tcp", final):
            with self.assertRaisesRegex(TOOL.EvidenceError, "total budget"):
                TOOL.query("8.8.8.8", "budget.fixture.example.org.", "A")

    def test_wrong_truncated_reply_does_not_trigger_tcp(self):
        def invalid(request, server, **kwargs):
            value = dns.message.make_response(request)
            value.flags |= dns.flags.TC
            value.id ^= 1
            return value

        with mock.patch.object(dns.query, "udp", invalid), mock.patch.object(dns.query, "tcp") as tcp:
            with self.assertRaises(TOOL.EvidenceError):
                TOOL.query("8.8.8.8", "invalid.fixture.example.org.", "A")
            tcp.assert_not_called()


if __name__ == "__main__":
    unittest.main()
