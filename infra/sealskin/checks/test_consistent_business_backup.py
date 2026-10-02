"""Real age round-trip and refusal tests on independent synthetic data."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('consistent-business-backup.py')
spec = importlib.util.spec_from_file_location('business_backup', SCRIPT)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class BusinessBackupTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='business-backup-test-', dir='/dev/shm')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.age = Path(os.environ.get('BP_AGE', shutil.which('age') or '/missing-age'))
        self.keygen = self.age.with_name('age-keygen')
        if not self.age.is_file() or not self.keygen.is_file():
            self.skipTest('explicit real age/age-keygen required')
        self.key = self.root / 'identity'
        subprocess.run([str(self.keygen), '-o', str(self.key)], check=True, capture_output=True)
        self.recipient = subprocess.check_output([str(self.keygen), '-y', str(self.key)], text=True).strip()
        self.storage = self.root / 'original'; self.storage.mkdir()
        (self.storage / 'db').write_bytes(b'current real-shaped data\0' * 100)
        (self.storage / 'link').symlink_to('db')
        self.plan = self.root / 'plan.json'; self.plan.write_text(json.dumps({'storage': str(self.storage)}))
        self.checkpoint = self.root / 'checkpoint.json'
        self.checkpoint.write_text(json.dumps({'result': 'QUIESCED', 'all_profiles_stopped': True, 'writers_stopped': True}))
        self.archive = self.root / 'backup.age'; self.receipt = self.root / 'receipt.json'; self.target = self.root / 'restored'

    def create(self, okay=True):
        p = subprocess.run(['python3', str(SCRIPT), 'create', '--plan', str(self.plan), '--checkpoint', str(self.checkpoint), '--output', str(self.archive), '--receipt', str(self.receipt), '--age', str(self.age), '--recipient', self.recipient], capture_output=True)
        self.assertEqual(p.returncode == 0, okay, p.stderr.decode())

    def restore(self, okay=True, identity=None):
        p = subprocess.run(['python3', str(SCRIPT), 'restore', '--archive', str(self.archive), '--receipt', str(self.receipt), '--identity', str(identity or self.key), '--scratch-root', str(self.root), '--age', str(self.age), '--target', str(self.target)], capture_output=True)
        self.assertEqual(p.returncode == 0, okay, p.stderr.decode())

    def test_roundtrip_files_modes_links_and_pending(self):
        (self.storage / 'db').chmod(0o600)
        self.create(); self.restore()
        self.assertEqual((self.target / 'storage/db').read_bytes(), (self.storage / 'db').read_bytes())
        self.assertEqual((self.target / 'storage/db').stat().st_mode & 0o777, 0o600)
        self.assertEqual(os.readlink(self.target / 'storage/link'), 'db')
        self.assertTrue((self.target / 'RECOVERY_PENDING').is_file())
        self.restore(False)

    def test_quiescence_required(self):
        self.checkpoint.write_text(json.dumps({'result': 'QUIESCED', 'all_profiles_stopped': True, 'writers_stopped': False}))
        self.create(False); self.assertFalse(self.archive.exists())

    def test_job_links_preserved_without_reading_targets(self):
        jobs = self.root / 'jobs'; jobs.mkdir()
        (jobs / 'font-cache-12').write_bytes(b'font cache')
        (jobs / 'font-cache-9').symlink_to('font-cache-12')
        outside = self.root / 'outside'; outside.write_bytes(b'not archived')
        (jobs / 'external').symlink_to(outside)
        self.plan.write_text(json.dumps({'jobs': str(jobs)}))
        self.create(); self.restore()
        self.assertEqual(os.readlink(self.target / 'jobs/font-cache-9'), 'font-cache-12')
        manifest = json.loads((self.target / 'MANIFEST.json').read_text())
        self.assertEqual(manifest['entries']['jobs/external']['kind'], 'symlink')
        self.assertNotIn('jobs/outside', manifest['entries'])
        self.assertEqual(outside.read_bytes(), b'not archived')

    def test_job_link_cannot_be_archive_parent(self):
        jobs = self.root / 'jobs'; jobs.mkdir()
        outside = self.root / 'outside'; outside.mkdir()
        (jobs / 'link').symlink_to(outside, target_is_directory=True)
        child = self.root / 'child'; child.write_bytes(b'not written through link')
        self.plan.write_text(json.dumps({'jobs': str(jobs), 'jobs/link/child': str(child)}))
        self.create(); self.restore(False)
        self.assertFalse(self.target.exists())
        self.assertEqual(list(outside.iterdir()), [])

    def test_config_symlinks_still_rejected(self):
        with self.assertRaises(ValueError):
            m.inventory({'controller-config': str(self.storage)})

    def test_ciphertext_corruption_before_target_creation(self):
        self.create(); raw = bytearray(self.archive.read_bytes()); raw[-20] ^= 1; self.archive.write_bytes(raw)
        # Even when a matching transport checksum is supplied, age must reject it.
        receipt = json.loads(self.receipt.read_text()); receipt['archive_sha256'] = hashlib.sha256(raw).hexdigest(); self.receipt.write_text(json.dumps(receipt))
        self.restore(False); self.assertFalse(self.target.exists())

    def test_wrong_key_before_target_creation(self):
        self.create(); wrong = self.root / 'wrong-key'
        subprocess.run([str(self.keygen), '-o', str(wrong)], check=True, capture_output=True)
        self.restore(False, wrong); self.assertFalse(self.target.exists())

    def test_manifest_pin_before_target_creation(self):
        self.create(); receipt = json.loads(self.receipt.read_text()); receipt['manifest_sha256'] = '0' * 64; self.receipt.write_text(json.dumps(receipt))
        self.restore(False); self.assertFalse(self.target.exists())

    def test_only_exact_runtime_socket_excluded(self):
        runtime = self.storage / 'owner/home/.XDG'; runtime.mkdir(parents=True)
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(str(runtime / 'wayland-0'))
            self.create(); self.restore()
            self.assertFalse((self.target / 'storage/owner/home/.XDG/wayland-0').exists())
            self.assertEqual(len(json.loads(self.receipt.read_text())['excluded_runtime_nodes']), 1)
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(str(self.storage / 'unknown.sock'))
            with self.assertRaises(ValueError): m.inventory({'storage': str(self.storage)})

    def test_source_alias_and_traversal_rejected(self):
        alias = self.root / 'alias'; alias.symlink_to(self.storage, target_is_directory=True)
        with self.assertRaises(ValueError): m.inventory({'storage': str(alias)})
        with self.assertRaises(ValueError): m.inventory({'../escaped': str(self.storage)})
        with self.assertRaises(ValueError): m.inventory({'storage': str(self.storage), 'storage/db': str(self.storage / 'db')})


if __name__ == '__main__':
    unittest.main()
