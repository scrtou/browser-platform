import contextlib
import datetime
import fcntl
import http.server
import importlib.util
import json
import os
from pathlib import Path
import socketserver
import tempfile
import threading
import unittest

spec = importlib.util.spec_from_file_location('monitor', Path(__file__).with_name('monitor.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class TestMonitor(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cfg = dict(socket=str(self.root/'control.sock'), profiles=['personal'], storage_path=str(self.root),
                        state_directory=str(self.root/'state'), memory_min_mib=1024, disk_min_mib=4096,
                        failure_samples=2, recovery_samples=2, retention_days=14, max_events=20)
        self.good = lambda _: dict(available_memory_mib=2048, available_disk_mib=8192)

    def sample(self, state, now, reader=None):
        return m.run(self.cfg, now, observer=lambda *a:state, resource_reader=reader or self.good)

    def test_transition_restart_dedup_recovery(self):
        self.assertFalse(self.sample('unhealthy', 1)['signals']['profile:personal']['active'])
        self.assertTrue(self.sample('unhealthy', 2)['signals']['profile:personal']['active'])
        self.assertEqual(len(self.sample('unhealthy', 3)['events']), 1)
        self.assertTrue(self.sample('healthy', 4)['signals']['profile:personal']['active'])
        v=self.sample('healthy', 5)
        self.assertFalse(v['signals']['profile:personal']['active'])
        self.assertEqual([e['transition'] for e in v['events']], ['firing','resolved'])

    def test_resource_unknown_does_not_resolve(self):
        low=lambda _:dict(available_memory_mib=100,available_disk_mib=100)
        self.sample('healthy',1,low);self.sample('healthy',2,low)
        def missing(_):raise OSError('password=SHOULD_NOT_LEAK')
        self.sample('healthy',3,missing);v=self.sample('healthy',4,missing)
        self.assertTrue(v['signals']['memory_low']['active'])
        self.assertTrue(v['signals']['disk_low']['active'])
        self.assertTrue(v['signals']['resource_unavailable']['active'])
        self.assertNotIn('SHOULD_NOT_LEAK',json.dumps(v))

    def test_retention_count_age_and_size(self):
        self.cfg.update(failure_samples=1,recovery_samples=1,max_events=3)
        for n in range(20):v=self.sample('healthy' if n%2 else 'unhealthy',n)
        self.assertEqual(len(v['events']),3)
        v=self.sample('healthy',15*86400)
        self.assertEqual(v['events'],[])
        self.assertLess((self.root/'state/status.json').stat().st_size, m.MAX_FILE)

    def test_private_permissions_and_corruption_preserved(self):
        self.sample('healthy',1)
        p=self.root/'state/status.json'
        self.assertEqual(p.stat().st_mode&0o777,0o600)
        p.write_text('SECRET_CORRUPT')
        with self.assertRaises(ValueError):self.sample('healthy',2)
        self.assertEqual(p.read_text(),'SECRET_CORRUPT')

    def test_overlap_and_symlink_refused(self):
        self.sample('healthy',1)
        p=self.root/'state/monitor.lock'
        with p.open('r+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):self.sample('healthy',2)
        p.unlink();p.symlink_to(self.root/'target')
        with self.assertRaises(OSError):self.sample('healthy',3)
        self.assertFalse((self.root/'target').exists())

    def test_unix_health_stale_failure_stopped_whitelist(self):
        now=1000
        report={'overall':'healthy','stale':False,'expires_at':'1970-01-01T00:20:00Z',
                'message':'COOKIE_SECRET','session_url':'https://x/?token=SECRET'}
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.server.paths.append(self.path)
                raw=json.dumps({'health':report}).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def log_message(self,*a):pass
        class Server(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):daemon_threads=True
        server=Server(self.cfg['socket'],Handler);server.paths=[];os.chmod(self.cfg['socket'],0o600)
        thread=threading.Thread(target=server.serve_forever);thread.start()
        try:
            self.assertEqual(m.observe_profile(self.cfg['socket'],'personal',now),'healthy')
            report['stale']=True
            self.assertEqual(m.observe_profile(self.cfg['socket'],'personal',now),'stale')
            report.update(stale=False,overall='degraded')
            self.assertEqual(m.observe_profile(self.cfg['socket'],'personal',now),'unhealthy')
            report.update(overall='offline',binding={'status':'stopped'},runtime=dict(workers=0,records=0,resources=0))
            self.assertEqual(m.observe_profile(self.cfg['socket'],'personal',now),'stopped')
            v=m.run(self.cfg,now,resource_reader=self.good)
            self.assertNotIn('SECRET',json.dumps(v))
            self.assertTrue(all(p=='/profiles/personal/health?cached=1' for p in server.paths))
        finally:server.shutdown();thread.join();server.server_close()
        self.assertEqual(m.observe_profile(self.cfg['socket'],'personal',now),'unavailable')

    def test_invalid_config(self):
        self.cfg['profiles']=['personal?token=SECRET']
        with self.assertRaises(ValueError):m.validate(self.cfg)

if __name__=='__main__':unittest.main()
