"""Migration preparation preserves ownership, policy revisions and rollback data."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
spec = importlib.util.spec_from_file_location('migration',ROOT/'prepare-migration.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        policy = {**migration.POLICY_DEFAULTS,'username':'owner','profile_id':'personal','home_name':'personal',
            'application_id':'firefox-personal','relay_image':'sha256:'+'a'*64,'probe_image':'sha256:'+'b'*64,
            'upstream_host':'proxy.example.invalid','upstream_port':1080,'probe_url':'https://example.com/'}
        self.registry = {'version':1,'policies':{'old':policy}}
        self.config = {'state_file':'/state/journal.json','sealskin':{'username':'owner','lifecycle_enabled':True},
            'profiles':[{'id':'personal','home_name':'personal','application_id':'firefox-personal',
                         'network_policy_id':'old','network_policy_sha256':migration.revision(policy),
                         'idle_policy':{'mode':'off'}},
                        {'id':'work','home_name':'work','application_id':'firefox-work'}]}
        self.state = {'version':1,'bindings':{'personal':{'profile_id':'personal','status':'running',
            'operation_id':'c'*32,'session_id':'old-session'}}}

    def plan(self):
        return migration.candidates(self.config,self.state,self.registry,'personal','personal-camoufox',
                                    'camoufox-personal-new','new-policy')

    def test_preparation_keeps_journal_old_policy_and_other_profiles(self):
        originals = copy.deepcopy((self.config,self.state,self.registry))
        future,registry,binding = self.plan()
        self.assertEqual((self.config,self.state,self.registry),originals)
        self.assertEqual(future['state_file'],self.config['state_file'])
        self.assertEqual(future['profiles'][1],self.config['profiles'][1])
        self.assertEqual(registry['policies']['old'],self.registry['policies']['old'])
        self.assertEqual(binding,self.state['bindings']['personal'])
        new = future['profiles'][0]
        self.assertEqual(new['home_name'],'personal-camoufox')
        self.assertEqual(new['language'],'zh_TW.UTF-8')
        self.assertEqual(new['network_policy_sha256'],migration.revision(registry['policies']['new-policy']))

    def test_referenced_home_cannot_be_reused(self):
        for home in ['personal','work']:
            with self.subTest(home=home), self.assertRaises(ValueError):
                migration.candidates(self.config,self.state,self.registry,'personal',home,'camoufox-new','new')
        self.state['bindings']['pending'] = {'home_name':'personal-camoufox'}
        with self.assertRaises(ValueError):
            self.plan()

    def test_unresolved_or_mismatched_binding_is_rejected(self):
        binding = self.state['bindings']['personal']
        for status in ['unknown','launching','stopping','failed']:
            binding['status'] = status
            with self.subTest(status=status),self.assertRaises(ValueError):
                self.plan()
        binding['status'] = 'running'
        binding['home_name'] = 'different-home'
        with self.assertRaises(ValueError):
            self.plan()

    def test_policy_drift_cannot_be_silently_rebased(self):
        self.registry['policies']['old']['upstream_port'] = 8080
        with self.assertRaises(ValueError):
            self.plan()

    def test_legacy_policy_defaults_and_relative_config_paths(self):
        del self.registry['policies']['old']['probe_ca_file']
        self.plan()  # Server defaults are included in the same canonical digest.
        self.config['state_file'] = './state.json'
        self.config['sealskin']['client_private_key_file'] = './private.pem'
        fixed = migration.resolve_config(self.config,Path('/original'))
        self.assertEqual(fixed['state_file'],'/original/state.json')
        self.assertEqual(fixed['control_socket'],'/original/state.json.control.sock')
        self.assertEqual(fixed['sealskin']['client_private_key_file'],'/original/private.pem')


if __name__ == '__main__':
    unittest.main()
