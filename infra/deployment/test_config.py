"""Deployment inputs, generated listeners and first-admin boundaries."""
import argparse
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('config_installer', Path(__file__).with_name('install.py'))
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class ConfigFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.path = self.base/'install.local.json'
        self.values = {'release':str(self.base/'release'), 'root':str(self.base/'instance'),
                       'name':'bp-config-test', 'user':'bpconfigqa',
                       'entry_origin':'https://entry.example.test', 'session_origin':'https://session.example.test',
                       'admin':{'username':'qaadmin', 'password':'synthetic-admin-value'}}
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.values))
        self.path.chmod(0o600)


class ConfigTests(ConfigFixture):
    def test_config_and_cli_precedence(self):
        self.values['adapter_port'] = 21100
        self.save()
        args = installer.parse_args(['--config',str(self.path),'--adapter-port','22100','--check-only'])
        self.assertEqual(args.adapter_port,22100)
        self.assertEqual(args.backend_port,18443)
        self.assertEqual(args.root,self.base/'instance')
        self.assertEqual(args.admin,self.values['admin'])
        self.assertTrue(args.check_only)
        installer.validate(args)

    def test_cli_without_config_remains_supported(self):
        args = installer.parse_args(['--release',str(self.base/'release'),'--root',str(self.base/'instance'),
            '--name','bp-config-test','--user','bpconfigqa','--entry-origin','https://entry.test',
            '--session-origin','https://session.test'])
        self.assertIsNone(args.admin)
        self.assertEqual((args.adapter_port,args.api_port,args.backend_port),(19100,18000,18443))

    def test_no_admin_and_explicit_qa_override(self):
        self.values['admin'] = None
        self.values['private_tls'] = True
        self.save()
        args = installer.parse_args(['--config',str(self.path),'--no-private-tls'])
        self.assertIsNone(args.admin)
        self.assertFalse(args.private_tls)

    def test_private_regular_file_required(self):
        self.path.chmod(0o644)
        with self.assertRaisesRegex(ValueError,'NOT_PRIVATE'):
            installer.load_install_config(self.path)
        self.path.chmod(0o600)
        link = self.base/'link.json'
        link.symlink_to(self.path)
        fifo = self.base/'fifo'
        os.mkfifo(fifo,0o600)
        for path in [link,fifo,self.base,self.base/'missing']:
            with self.assertRaisesRegex(ValueError,'NOT_PRIVATE'):
                installer.load_install_config(path)

    def test_invalid_json_and_duplicate_keys_do_not_echo_values(self):
        for raw in ['{"private-password":', '{"admin":null,"admin":{"password":"secret"}}',
                    '{"admin":{"username":"a","username":"b","password":"secret"}}', '{} {}']:
            self.path.write_text(raw)
            with self.assertRaises(ValueError) as error:
                installer.load_install_config(self.path)
            self.assertEqual(str(error.exception),'INSTALL_CONFIG_INVALID_OR_NOT_PRIVATE')

    def test_unknown_fields_types_and_relative_paths_rejected(self):
        cases = [{'admin_password':'private-value'}, {'adapter_port':True}, {'api_port':'19000'},
                 {'private_tls':'false'}, {'admin':[]}, {'root':'relative'}, {'name':''}, [], None]
        for value in cases:
            self.path.write_text(json.dumps(value))
            with self.assertRaises(ValueError) as error:
                installer.load_install_config(self.path)
            self.assertNotIn('private-value',str(error.exception))

    def test_invalid_admin_before_any_installation_writes(self):
        bad = [{'username':'BadName','password':'value'}, {'username':'ok','password':''},
               {'username':'ok','password':'a\nbc'}, {'username':'ok','password':'a\rbc'},
               {'username':'ok','password':'长'*86}, {'username':'ok','password':True},
               {'username':'ok','password':'\ud800'}, {'username':'ok'}, {},
               {'username':'ok','password':'value','role':'admin'}]
        for admin in bad:
            self.values['admin'] = admin
            self.save()
            with self.assertRaises(ValueError):
                installer.parse_args(['--config',str(self.path)])
            self.assertFalse((self.base/'instance').exists())

    def test_utf8_password_length_and_whitespace_preserved(self):
        installer.validate_admin({'username':'a_1-b','password':'密碼'})
        self.values['admin']['password'] = '  meaningful whitespace  '
        self.save()
        self.assertEqual(installer.load_install_config(self.path)['admin']['password'],'  meaningful whitespace  ')

    def test_config_cannot_be_part_of_the_release(self):
        self.values['release'] = str(self.base)
        self.save()
        args = installer.parse_args(['--config',str(self.path)])
        with self.assertRaisesRegex(ValueError,'OUTSIDE_RELEASE'):
            installer.validate(args)

    def test_check_only_does_not_initialize_or_create_resources(self):
        release = self.base/'release'
        (release/'deployment').mkdir(parents=True)
        (release/'deployment/inputs.json').write_text('{}')
        manifest(release)
        args = installer.parse_args(['--config',str(self.path),'--check-only'])
        with patch.object(installer.subprocess,'run',side_effect=AssertionError('subprocess mutation')):
            self.assertEqual(installer.install(args),{'result':'INPUTS_VALID','side_effects':False})
        self.assertFalse(args.root.exists())

    def test_ports_and_canonical_public_origins(self):
        args = installer.parse_args(['--config',str(self.path),'--entry-origin','https://entry.example.test:443',
                                     '--session-origin','https://session.example.test:443'])
        _, _, ports = installer.validate(args)
        self.assertEqual(ports,[19100,18000,18443,443])
        self.assertEqual(args.entry_origin,'https://entry.example.test')
        for field,value in [('adapter_port',18000),('api_port',80),('backend_port',65536),
                            ('entry_origin','https://entry.test:19443')]:
            altered = argparse.Namespace(**vars(args))
            setattr(altered,field,value)
            with self.assertRaises(ValueError):installer.validate(altered)

    def test_public_listener_preflight_includes_80_and_qa_is_loopback(self):
        args = installer.parse_args(['--config',str(self.path)])
        with patch.object(installer.socket,'socket') as socket:
            installer.check_listeners(args,[19100,18000,18443,443])
            binds = socket.return_value.__enter__.return_value.bind.call_args_list
            self.assertEqual([call.args[0] for call in binds],[
                ('127.0.0.1',19100),('127.0.0.1',18000),('127.0.0.1',18443),('0.0.0.0',443),('0.0.0.0',80)])
        args.private_tls = True
        with patch.object(installer.socket,'socket') as socket:
            installer.check_listeners(args,[19100,18000,18443,19443])
            binds = socket.return_value.__enter__.return_value.bind.call_args_list
            self.assertEqual([call.args[0] for call in binds],[
                ('127.0.0.1',19100),('127.0.0.1',18000),('127.0.0.1',18443),('127.0.0.1',19443)])

    def test_admin_password_only_goes_to_stdin(self):
        args = installer.parse_args(['--config',str(self.path)])
        with patch.object(installer.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as run:
            self.assertTrue(installer.initialize_admin(args,args.root))
        call = run.call_args
        secret = args.admin['password']
        self.assertNotIn(secret,repr(call.args))
        self.assertEqual(call.kwargs['input'],secret+'\n')
        self.assertEqual(call.kwargs['stdout'],subprocess.DEVNULL)
        self.assertEqual(call.kwargs['stderr'],subprocess.DEVNULL)
        self.assertNotIn(secret,json.dumps(installer.install_request(args)))
        self.assertNotIn('admin',installer.install_request(args))

    def test_no_admin_skips_cli_and_failures_are_redacted(self):
        args = installer.parse_args(['--config',str(self.path)])
        for problem in [SimpleNamespace(returncode=1), subprocess.TimeoutExpired('secret',1,output='secret'),OSError('secret')]:
            with patch.object(installer.subprocess,'run') as run:
                if isinstance(problem,Exception):run.side_effect=problem
                else:run.return_value=problem
                with self.assertRaisesRegex(ValueError,'^WEB_ADMIN_INITIALIZATION_FAILED$'):
                    installer.initialize_admin(args,args.root)
        args.admin = None
        with patch.object(installer.subprocess,'run') as run:
            self.assertFalse(installer.initialize_admin(args,args.root))
            run.assert_not_called()


def manifest(release):
    rows = {str(p.relative_to(release)):{'sha256':installer.digest(p),'size':p.stat().st_size,
            'mode':p.stat().st_mode & 0o777} for p in release.rglob('*') if p.is_file() and p.name!='release-manifest.json'}
    (release/'release-manifest.json').write_text(json.dumps({'schema':'browser-platform/release-files/v1','files':rows}))


class InstallFlowTests(ConfigFixture):
    """Run actual file generation with system/Docker operations replaced by stubs."""
    def prepare(self, admin=True):
        args = installer.parse_args(['--config',str(self.path),'--adapter-port','21100','--api-port','21000',
                                     '--backend-port','21443'])
        if not admin:args.admin=None
        (args.release/'deployment').mkdir(parents=True)
        (args.release/'deployment/inputs.json').write_text(json.dumps({'images':[],'controller':'sha256:'+'a'*64,
            'proxy_template':{},'direct_template':{},'native_targets':{'targets':{'camoufox-linux-v152':{'image':'sha256:'+'b'*64}}}}))
        (args.release/'deployment/Caddyfile.template').write_text(Path(__file__).with_name('Caddyfile.template').read_text())
        manifest(args.release)
        return args

    def stubs(self, args, stack):
        def run(command, **kwargs):
            text = [str(x) for x in command]
            if text[:2] == ['systemctl','start']:
                installer.write(args.root/'config/admin.json',{'username':'control-admin','private_key':'synthetic','server_public_key':'synthetic'})
            if any(x.endswith('/prepare-builtin-install.py') for x in text):
                for part in ['templates','fingerprint-cache']:
                    (args.root/'builtins'/part).mkdir(parents=True)
            return SimpleNamespace(returncode=0)
        real_write = installer.write
        def safe_write(path, *values):
            if path.is_relative_to(args.root):real_write(path,*values)
            elif not str(path).startswith(('/etc/systemd/system/bp-config-test-', '/etc/tmpfiles.d/bp-config-test.')):
                raise AssertionError('unexpected external write')
        def fake_tls(path, names):
            path.mkdir()
            (path/'key.pem').write_text('synthetic')
            (path/'cert.pem').write_text('synthetic')
        patches = [patch.object(installer.os,'geteuid',return_value=0),
            patch.object(installer.platform,'system',return_value='Linux'),
            patch.object(installer.platform,'machine',return_value='x86_64'),
            patch.object(installer.shutil,'which',return_value='/bin/stub'),
            patch.object(installer.pwd,'getpwnam',side_effect=[KeyError(),SimpleNamespace(pw_uid=os.getuid(),pw_gid=os.getgid())]),
            patch.object(installer.subprocess,'run',side_effect=run),
            patch.object(installer.subprocess,'check_output',return_value=''),
            patch.object(installer.socket,'create_connection'),patch.object(installer,'chown_tree'),
            patch.object(installer,'tls',side_effect=fake_tls),patch.object(installer,'write',side_effect=safe_write)]
        for item in patches:stack.enter_context(item)

    def test_generated_ports_credentials_and_receipts(self):
        args=self.prepare()
        with ExitStack() as stack:
            self.stubs(args,stack)
            stack.enter_context(patch.object(installer,'check_listeners'))
            ready=stack.enter_context(patch.object(installer,'wait_ready'))
            result=installer.install(args)
        cfg=json.loads((args.root/'adapter-config.json').read_text())
        compose=json.loads((args.root/'compose.json').read_text())
        self.assertEqual(cfg['listen_address'],'127.0.0.1:21100')
        self.assertEqual(cfg['sealskin']['api_base_url'],'https://127.0.0.1:21443')
        self.assertEqual(cfg['access']['session_upstream_url'],'https://127.0.0.1:21443')
        self.assertEqual(compose['services']['controller']['ports'],['127.0.0.1:21443:8443','127.0.0.1:21000:8000'])
        self.assertIn('reverse_proxy 127.0.0.1:21100',(args.root/'Caddyfile').read_text())
        self.assertEqual(json.loads((args.root/'access/bootstrap.json').read_text())['server_endpoint'],'http://127.0.0.1:21000')
        self.assertTrue(result['web_admin_initialized'])
        ready.assert_called_once_with(args,args.root,admin_initialized=True)
        for path in args.root.rglob('*'):
            if path.is_file():self.assertNotIn(args.admin['password'].encode(),path.read_bytes())

    def test_default_install_remains_pending(self):
        args=self.prepare(admin=False)
        with ExitStack() as stack:
            self.stubs(args,stack)
            stack.enter_context(patch.object(installer,'check_listeners'))
            ready=stack.enter_context(patch.object(installer,'wait_ready'))
            result=installer.install(args)
        self.assertFalse(result['web_admin_initialized'])
        ready.assert_called_once_with(args,args.root,admin_initialized=False)
        registry=json.loads((args.root/'access/entry-users.json').read_text())
        self.assertEqual(registry,{'version':3,'users':[],'setup_required':True})

    def test_public_80_conflict_precedes_all_writes(self):
        args=self.prepare()
        with ExitStack() as stack:
            self.stubs(args,stack)
            sock=stack.enter_context(patch.object(installer.socket,'socket'))
            def bind(address):
                if address==('0.0.0.0',80):raise OSError('address in use')
            sock.return_value.__enter__.return_value.bind.side_effect=bind
            with self.assertRaisesRegex(ValueError,'PORT_UNAVAILABLE: 0.0.0.0:80'):installer.install(args)
        self.assertFalse(args.root.exists())

    def test_initialization_failure_never_reports_installed(self):
        args=self.prepare()
        with ExitStack() as stack:
            self.stubs(args,stack)
            stack.enter_context(patch.object(installer,'check_listeners'))
            stack.enter_context(patch.object(installer,'initialize_admin',side_effect=ValueError('WEB_ADMIN_INITIALIZATION_FAILED')))
            ready=stack.enter_context(patch.object(installer,'wait_ready'))
            with self.assertRaisesRegex(ValueError,'WEB_ADMIN_INITIALIZATION_FAILED'):installer.install(args)
        ready.assert_not_called()
        self.assertFalse((args.root/'installation.json').exists())
        failed=json.loads((args.root/'installation-failed.json').read_text())
        self.assertEqual(failed['result'],'FAILED')
        self.assertNotIn(args.admin['password'],json.dumps(failed))


class ReadinessTests(unittest.TestCase):
    def test_both_account_states_and_wrong_state_rejection(self):
        for initialized,body,passes in [(False,'平台尚未初始化',True),
                (True,'<form method="post" action="/auth/login">',True),
                (True,'平台尚未初始化',False),(False,'<form method="post" action="/auth/login">',False)]:
            with self.subTest(initialized=initialized,passes=passes),ExitStack() as stack:
                args=argparse.Namespace(entry_origin='https://entry.test',adapter_port=19100,private_tls=False)
                stack.enter_context(patch.object(installer.ssl,'create_default_context'))
                stack.enter_context(patch.object(installer.socket,'create_connection'))
                plain=stack.enter_context(patch.object(installer.http.client,'HTTPConnection'))
                plain.return_value.getresponse.return_value.status=200
                secure=stack.enter_context(patch.object(installer.http.client,'HTTPSConnection'))
                secure.return_value.getresponse.return_value.status=200
                secure.return_value.getresponse.return_value.read.return_value=body.encode()
                stack.enter_context(patch.object(installer.time,'sleep'))
                stack.enter_context(patch.object(installer.time,'monotonic',side_effect=[0,0,2]))
                if passes:installer.wait_ready(args,Path('/not-used'),timeout=1,admin_initialized=initialized)
                else:
                    with self.assertRaisesRegex(ValueError,'READINESS_TIMEOUT'):
                        installer.wait_ready(args,Path('/not-used'),timeout=1,admin_initialized=initialized)


if __name__ == '__main__':
    unittest.main()
