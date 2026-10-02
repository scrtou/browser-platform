import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parent))
spec=importlib.util.spec_from_file_location('check_bidi',Path(__file__).resolve().parents[1]/'firefox-proxy/check-bidi.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);sys.modules['check_bidi']=module
from browser_client import wait_initial_page

class InitialDocumentTests(unittest.TestCase):
    def fixture(self,values):
        client=Mock(engine='camoufox')
        client.bidi.command.return_value={'contexts':[{'url':'https://example.com/','context':'fresh'}]}
        client.evaluate.side_effect=values
        tick=[0.0]
        def sleep(seconds):tick[0]+=seconds
        return client,{'clock':lambda:tick[0],'sleep':sleep}

    def test_transient_realm_errors_then_real_title(self):
        failures=['script.evaluate failed: no such frame','script.evaluate failed: unknown error']
        client,timing=self.fixture([RuntimeError(v) for v in failures]+['Example Domain'])
        self.assertEqual(wait_initial_page(client,**timing),failures)
        self.assertEqual(client.context,'fresh')
        self.assertEqual(client.evaluate.call_count,3)

    def test_persistent_error_never_becomes_ready(self):
        client,timing=self.fixture(RuntimeError('script.evaluate failed: unknown error'))
        with self.assertRaisesRegex(AssertionError,'NATIVE_QA_HTTPS_FAILED'):
            wait_initial_page(client,timeout=2,**timing)
        self.assertEqual(client.evaluate.call_count,4)

    def test_unrelated_error_is_not_retried(self):
        client,timing=self.fixture(RuntimeError('script.evaluate failed: invalid argument'))
        with self.assertRaisesRegex(RuntimeError,'invalid argument'):wait_initial_page(client,**timing)
        self.assertEqual(client.evaluate.call_count,1)

    def test_blank_context_is_not_observed_as_target(self):
        client,timing=self.fixture(['Example Domain'])
        client.bidi.command.side_effect=[{'contexts':[{'url':'about:blank','context':'old'}]}, {'contexts':[{'url':'https://example.com/','context':'new'}]}]
        self.assertEqual(wait_initial_page(client,**timing),[])
        self.assertEqual(client.context,'new')
        self.assertEqual(client.evaluate.call_count,1)

if __name__=='__main__':unittest.main()
