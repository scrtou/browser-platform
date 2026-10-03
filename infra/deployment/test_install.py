"""Installation admission tests: rejected input cannot create system resources."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('installer', Path(__file__).with_name('install.py'))
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.release = self.base / 'release'
        (self.release / 'deployment').mkdir(parents=True)
        (self.release / 'deployment/inputs.json').write_text('{}\n')
        self.manifest()
        self.args = argparse.Namespace(release=self.release, root=self.base/'install', name='bp-test', user='bpqa',
            entry_origin='https://entry.example.test:19443', session_origin='https://session.example.test:19443',
            adapter_port=19100, api_port=18000, backend_port=18443, private_tls=True, check_only=True)

    def manifest(self):
        rows = {str(p.relative_to(self.release)): {'sha256': installer.digest(p), 'size': p.stat().st_size,
            'mode': p.stat().st_mode & 0o777} for p in self.release.rglob('*') if p.is_file() and p.name!='release-manifest.json'}
        (self.release/'release-manifest.json').write_text(json.dumps({'schema':'browser-platform/release-files/v1','files':rows}))

    def test_valid_check_never_calls_system(self):
        with patch.object(installer.subprocess, 'run', side_effect=AssertionError('mutation')):
            self.assertEqual(installer.install(self.args)['result'], 'INPUTS_VALID')
        self.assertFalse(self.args.root.exists())

    def test_existing_destination_untouched(self):
        self.args.root.mkdir()
        marker=self.args.root/'retain';marker.write_text('data')
        with self.assertRaisesRegex(ValueError,'NEW_ROOT_REQUIRED'):
            installer.install(self.args)
        self.assertEqual(marker.read_text(),'data')

    def test_symlink_parent_and_destination_rejected(self):
        (self.base/'link').symlink_to(self.base, target_is_directory=True)
        for root in [self.base/'link/install', self.base/'broken']:
            if root.name=='broken':root.symlink_to(self.base/'missing')
            self.args.root=root
            with self.assertRaisesRegex(ValueError,'NEW_ROOT_REQUIRED'):installer.validate(self.args)

    def test_origins_ports_and_names(self):
        bad=[('entry_origin','https://user:secret@entry.test'),('entry_origin','http://entry.test'),
             ('entry_origin','https://entry.test/path'),('entry_origin','https://entry.test?token=x'),
             ('entry_origin','https://entry.test#x'),('entry_origin','https://ENTRY.test/'),
             ('session_origin',self.args.entry_origin),('adapter_port',18443),('name','docker'),
             ('name','bp-../foo'),('user','root'),('root',self.base/'new directory')]
        for name,value in bad:
            args=copy.copy(self.args);setattr(args,name,value)
            with self.subTest(name=name,value=value),self.assertRaises(ValueError):installer.validate(args)

    def test_corruption_extras_modes_and_symlinks(self):
        target=self.release/'deployment/inputs.json'
        target.write_text('{"changed":true}')
        with self.assertRaisesRegex(ValueError,'RELEASE_FILE_CHANGED'):installer.verify_tree(self.release)
        self.manifest()
        target.chmod(0o755)
        with self.assertRaisesRegex(ValueError,'RELEASE_FILE_CHANGED'):installer.verify_tree(self.release)
        self.manifest()
        extra=self.release/'extra';extra.write_text('unexpected')
        with self.assertRaisesRegex(ValueError,'RELEASE_FILE_SET_CHANGED'):installer.verify_tree(self.release)
        extra.unlink();extra.symlink_to(target)
        with self.assertRaisesRegex(ValueError,'RELEASE_SPECIAL_FILE'):installer.verify_tree(self.release)

    def test_traversal_and_missing_file(self):
        m=json.loads((self.release/'release-manifest.json').read_text())
        m['files']['../outside']=m['files'].pop('deployment/inputs.json')
        (self.release/'release-manifest.json').write_text(json.dumps(m))
        with self.assertRaises(ValueError):installer.verify_tree(self.release)

class ImageRetentionTests(unittest.TestCase):
    def test_retain_all_exact_images_and_accept_same_id(self):
        ids = ['sha256:' + c * 64 for c in 'ab']
        run = Mock()
        responses = ['', ids[1] + '\n', *[json.dumps([{'Id': i}]) for i in ids]]
        with patch.object(installer.subprocess, 'check_output', side_effect=responses):
            refs = installer.retain_images([{'id': i} for i in ids], 'bp-test', run)
        self.assertEqual(set(refs.values()), set(ids))
        self.assertEqual(run.call_count, 2)
        for call in run.call_args_list:
            argv = call.args[0]
            self.assertEqual(argv[:3], ['docker', 'image', 'tag'])
            self.assertEqual(refs[argv[4]], argv[3])

    def test_conflict_preflight_never_mutates_any_tag(self):
        run = Mock()
        with patch.object(installer.subprocess, 'check_output', side_effect=['', 'sha256:' + 'c' * 64]):
            with self.assertRaisesRegex(ValueError, 'IMAGE_RETENTION_TAG_CONFLICT'):
                installer.retain_images([{'id': 'sha256:' + c * 64} for c in 'ab'], 'bp-test', run)
        run.assert_not_called()

    def test_mismatched_tag_readback_fails_installation(self):
        with patch.object(installer.subprocess, 'check_output', side_effect=['', '[{"Id":"wrong"}]']):
            with self.assertRaisesRegex(ValueError, 'IMAGE_RETENTION_VERIFY_FAILED'):
                installer.retain_images([{'id': 'sha256:' + 'a' * 64}], 'bp-test', Mock())


if __name__=='__main__':unittest.main()
