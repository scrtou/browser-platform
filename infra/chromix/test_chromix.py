import hashlib
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

HERE=Path(__file__).resolve().parent

def module(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

launch=module('launcher')
prepare=module('prepare-release')
SPEC={'schemaVersion':launch.SCHEMA,'id':'chromix-test','revision':1,'browserVersion':'154.0.8037.57','locale':'en-US','timezone':'UTC','screen':{'width':1280,'height':720,'dpr':1}}


class LauncherTests(unittest.TestCase):
    def test_system_dpi_requires_new_auto_contract(self):
        spec=copy.deepcopy(SPEC)
        spec['schemaVersion']='browser-platform/chromix-environment/v2'
        spec['screen'].update(mode='auto',dpr='system')
        launch.validate(spec,SPEC['browserVersion'])
        args=launch.arguments(spec,123,Path('/config/.chromix'),'about:blank')
        self.assertFalse(any(v.startswith('--force-device-scale-factor') for v in args))
        self.assertIn('--force-device-scale-factor=1',launch.arguments(SPEC,123,Path('/config/.chromix'),'about:blank'))
        for mutate in (lambda s:s.update(schemaVersion=launch.SCHEMA),lambda s:s['screen'].pop('mode'),lambda s:s['screen'].update(dpr=1)):
            bad=copy.deepcopy(spec);mutate(bad)
            with self.assertRaises(ValueError):launch.validate(bad,SPEC['browserVersion'])

    def test_auto_contract_preserves_seed_network_and_sandbox(self):
        spec=copy.deepcopy(SPEC);spec['screen']['mode']='auto'
        launch.validate(spec,SPEC['browserVersion'])
        launch.verify_display(spec,{'MAX_RES':'3840x2160'})
        for env in ({}, {'MAX_RES':'7680x4320'}, {'MAX_RES':'3840x2160','SELKIES_MANUAL_WIDTH':'1280'}):
            with self.assertRaisesRegex(ValueError,'CHROMIX_DISPLAY_DRIFT'):
                launch.verify_display(spec,env)
        args=launch.arguments(spec,123,Path('/config/.chromix'),'about:blank')
        self.assertIn('--uxr-fingerprint-seed=123',args)
        self.assertIn('--uxr-canvas-seed=123',args)
        self.assertIn('--uxr-audio-seed=123',args)
        self.assertFalse(any(v.startswith(('--fingerprint=','--fingerprint-screen-')) for v in args))
        self.assertIn('--proxy-bypass-list=<-loopback>',args)
        self.assertNotIn('--no-sandbox',args)
        self.assertFalse(any('remote-debugging' in v for v in args))
        for mode in ('fixed','native','AUTO',True):
            spec['screen']['mode']=mode
            with self.assertRaises(ValueError):launch.validate(spec,SPEC['browserVersion'])

    def test_fixed_display_still_requires_exact_dimensions(self):
        launch.verify_display(SPEC,{'SELKIES_MANUAL_WIDTH':'1280','SELKIES_MANUAL_HEIGHT':'720'})
        with self.assertRaisesRegex(ValueError,'CHROMIX_DISPLAY_DRIFT'):
            launch.verify_display(SPEC,{'MAX_RES':'3840x2160'})

    def test_font_lock_rejects_missing_and_changed_files(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);font=root/'font';font.write_bytes(b'fixed font')
            lock=root/'lock.json';lock.write_text(json.dumps({'files':{str(font):hashlib.sha256(font.read_bytes()).hexdigest()}}))
            launch.verify_fonts(lock)
            font.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'CHROMIX_FONT_MISMATCH'):launch.verify_fonts(lock)
            font.unlink()
            with self.assertRaisesRegex(ValueError,'CHROMIX_FONT_MISSING'):launch.verify_fonts(lock)

    def test_spec_rejects_unsupported_parameters(self):
        launch.validate(SPEC,SPEC['browserVersion'])
        for mutate in (lambda s:s.update(extraArgs=['--no-sandbox']),lambda s:s.update(browserVersion='1'),lambda s:s.update(locale='--no-sandbox'),lambda s:s['screen'].update(dpr=2),lambda s:s['screen'].update(width=True)):
            with self.subTest(mutate=mutate):
                value=copy.deepcopy(SPEC);mutate(value)
                with self.assertRaises(ValueError):launch.validate(value,SPEC['browserVersion'])

    def test_seed_survives_restart_and_exclusion(self):
        with tempfile.TemporaryDirectory() as raw:
            home=Path(raw);fd,seed,directory=launch.identity(home)
            try:
                with self.assertRaises(BlockingIOError):launch.identity(home)
            finally:os.close(fd)
            fd,next_seed,_=launch.identity(home);os.close(fd)
            self.assertEqual(seed,next_seed)
            self.assertEqual((directory/'identity.json').stat().st_mode & 0o777,0o600)

    def test_identity_symlink_and_corruption_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            home=Path(raw);fd,_,directory=launch.identity(home);os.close(fd)
            p=directory/'identity.json';p.write_text('{"schemaVersion":1,"seed":0}')
            with self.assertRaises(ValueError):launch.identity(home)
            p.unlink();p.symlink_to(home/'outside')
            with self.assertRaises(ValueError):launch.identity(home)

    def test_managed_network_and_no_arbitrary_url(self):
        args=launch.arguments(SPEC,123,Path('/config/.chromix'),'https://example.com/')
        self.assertIn('--proxy-bypass-list=<-loopback>',args)
        self.assertIn('--proxy-server=socks5://profile-relay:1080',args)
        self.assertNotIn('--no-sandbox',args)
        self.assertFalse(any('remote-debugging' in arg for arg in args))
        for url in ('--no-sandbox','file:///etc/passwd','https://user:pass@example.com','javascript:alert(1)'):
            with self.assertRaises(ValueError):launch.arguments(SPEC,123,Path('/config/.chromix'),url)

    def test_duplicate_spec_fields_rejected(self):
        with self.assertRaises(ValueError):launch.decode('{"seed":1,"seed":2}')


class ArchiveTests(unittest.TestCase):
    def test_traversal_and_symlink_rejected_before_target_creation(self):
        for name,mode in [('chromix/../../outside',0o100644),('chromix/link',0o120777)]:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as raw:
                p=Path(raw);archive=p/'bad.zip'
                with zipfile.ZipFile(archive,'w') as z:
                    info=zipfile.ZipInfo(name);info.external_attr=mode<<16;z.writestr(info,b'a')
                with self.assertRaises(ValueError):prepare.extract(archive,p/'output',{'expandedBytes':1,'executables':{}})
                self.assertFalse((p/'output').exists())

    def test_bad_executable_digest_cleans_partial_output(self):
        with tempfile.TemporaryDirectory() as raw:
            p=Path(raw);archive=p/'bad.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('chromix/chrome',b'bad')
            with self.assertRaises(ValueError):prepare.extract(archive,p/'output',{'expandedBytes':3,'executables':{'chromix/chrome':{'size':3,'sha256':'0'*64}}})
            self.assertFalse((p/'output').exists())


if __name__=='__main__':unittest.main()
