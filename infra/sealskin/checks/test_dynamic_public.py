"""Protect shared DNS records when publishing and removing one QA run."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("dynamic_public", Path(__file__).with_name("check-dynamic-public.py"))
public = importlib.util.module_from_spec(spec)
spec.loader.exec_module(public)


class ZoneOwnership(unittest.TestCase):
    name = "bootstrap-0123456789abcdef.dns-qa.azhen.de."
    zone = ('$ORIGIN dns-qa.azhen.de.\n@ IN SOA ns.example. host.example. (\n'
            ' 2026093001 ; serial: increment\n 60 30 86400 60\n)\n'
            'ready 60 IN TXT "preserved"\nother 300 IN A 192.0.2.1\n')

    def test_roundtrip_keeps_records_added_by_another_operator(self):
        first, serial = public.replace_zone(self.zone, {self.name}, [self.name + " 15 IN A 188.253.118.223"])
        concurrent = first + 'new-record 300 IN TXT "added later"\n'
        final, later = public.replace_zone(concurrent, {self.name}, [])
        self.assertEqual((serial, later), (2026093002, 2026093003))
        self.assertNotIn(self.name, final)
        self.assertIn('new-record 300 IN TXT "added later"', final)
        self.assertIn('other 300 IN A 192.0.2.1', final)
        self.assertIn('ready 60 IN TXT "preserved"', final)

    def test_other_runs_and_similar_names_are_preserved(self):
        peer = "bootstrap-fedcba9876543210.dns-qa.azhen.de. 15 IN A 192.0.2.2"
        similar = "x." + self.name + " 15 IN A 192.0.2.3"
        result, _ = public.replace_zone(self.zone + peer + "\n" + similar + "\n", {self.name}, [])
        self.assertIn(peer, result)
        self.assertIn(similar, result)

    def test_foreign_zone_or_non_run_name_rejected(self):
        for name in ("example.com.", "ready.dns-qa.azhen.de.", "bootstrap-123.dns-qa.azhen.de."):
            with self.subTest(name=name), self.assertRaises(AssertionError):
                public.replace_zone(self.zone, {name}, [])

    def test_record_outside_owned_set_rejected(self):
        with self.assertRaises(AssertionError):
            public.replace_zone(self.zone, {self.name}, ["other 15 IN A 192.0.2.4"])

    def test_missing_or_ambiguous_serial_rejected(self):
        for text in (self.zone.replace("; serial", "; unknown"), self.zone + " 2026093002 ; serial\n"):
            with self.subTest(text=text), self.assertRaises(AssertionError):
                public.replace_zone(text, {self.name}, [])


if __name__ == "__main__":
    unittest.main()
