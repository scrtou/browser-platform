import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import struct
import zlib
from unittest import mock

HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE.parent/'camoufox')]
def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
artifact=module('native_artifact',HERE/'artifact.py')
chromix=module('native_chromix',HERE.parent/'chromix/launcher.py')
firefox=module('native_firefox',HERE/'firefox_launcher.py')
import native_jobs
from template_sources import write,sha,validate_target_shape

class NativeTests(unittest.TestCase):
    def test_xwd_packed_24_and_padded_32_pixels(self):
        from screenshot import png
        expected=b'\x00\xff\x00\x00\x00\xff\x00\x00\x00\x00\xff\xff\xff\xff'
        for bits in (24,32):
            header=[0]*25
            header[0]=100;header[1]=7;header[4]=2;header[5]=2
            header[11]=bits;header[12]=12;header[14:17]=[0xff0000,0xff00,0xff]
            stride=bits//8
            colors=[[(0,0,255),(0,255,0)],[(255,0,0),(255,255,255)]]
            rows=[b''.join(bytes(color)+b'\x00'*(stride-3) for color in row).ljust(12,b'\xa5') for row in colors]
            raw=struct.pack('>25I',*header)+b''.join(rows)
            data=png(raw);offset=8;pixels=None
            while offset<len(data):
                size=struct.unpack('>I',data[offset:offset+4])[0]
                if data[offset+4:offset+8]==b'IDAT':pixels=zlib.decompress(data[offset+8:offset+8+size])
                offset+=12+size
            self.assertEqual(pixels,expected)
            with self.assertRaises(AssertionError):png(raw[:-1])

    def test_chromix_actual_window_class_overrides_inherited_maximization(self):
        import display_config
        import xml.etree.ElementTree as ET
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            paths=[root/'rc.xml',root/'rc.xml.bak']
            original='<openbox_config><applications><application class="*"><maximized>yes</maximized></application><application class="chromium"><maximized>yes</maximized></application><application class="firefox"><decor>no</decor></application></applications></openbox_config>'
            for p in paths:p.write_text(original)
            with mock.patch.object(display_config,'Path',side_effect=lambda p:root/Path(p).name):
                for automatic in (False,True,False):
                    display_config.configure('chromium',automatic)
                    for p in paths:
                        rules=ET.fromstring(p.read_text()).find('applications')
                        matching=[v for v in rules if v.get('class') in ('*','Chromium-browser')]
                        self.assertEqual(matching[-1].findtext('maximized'),'yes' if automatic else 'no')
                        self.assertEqual(matching[-1].findtext('position/x'),'0')
                        self.assertEqual(len([v for v in rules if v.get('class')=='Chromium-browser']),1)
                        self.assertEqual([v for v in rules if v.get('class')=='firefox'][0].findtext('decor'),'no')

    def spec(self,engine):
        s={'schemaVersion':artifact.SCHEMAS[engine],'id':'custom-test','revision':1,'browserVersion':artifact.VERSIONS[engine],'locale':'zh-CN','languages':['zh-CN','en-US'],'timezone':'Asia/Taipei','screen':{'width':1280,'height':900,'dpr':1},'window':{'width':1280,'height':900},'runtimeImageDigest':'sha256:'+'a'*64}
        if engine=='chromix':s['seed']=123
        return s
    def test_strict_artifact_and_runtime_binding(self):
        for engine in artifact.VERSIONS:
            s=self.spec(engine);artifact.validate(s,engine)
            for key,val in [('extraArgs',['--no-sandbox']),('browserVersion','1'),('languages',['en-US']),('runtimeImageDigest','latest')]:
                bad=copy.deepcopy(s);bad[key]=val
                with self.assertRaises(ValueError):artifact.validate(bad,engine)
            with self.assertRaises(ValueError):artifact.verify(s,engine,json.dumps(s).encode(),{})
    def test_native_flags_and_home_paths(self):
        s=self.spec('chromix');chromix.validate(s,artifact.VERSIONS['chromix'])
        flags=chromix.arguments(s,123,Path('/config/.chromix'),'https://example.com/')
        self.assertIn('--accept-lang=zh-CN,en-US',flags);self.assertIn('--uxr-fingerprint-seed=123',flags)
        self.assertIn('--deny-permission-prompts',flags);self.assertNotIn('--no-sandbox',flags)
        self.assertIn('--disable-font-subpixel-positioning',flags)
        self.assertFalse(any('remote-debugging' in v for v in flags))
        for engine,method in [('chromix',lambda url:chromix.arguments(s,123,Path('/config/.chromix'),url)),('firefox',lambda url:firefox.arguments(self.spec('firefox'),Path('/config/.firefox'),url))]:
            with self.assertRaises(ValueError):method('--no-sandbox')

    def test_chromix_full_screen_size_uses_maximized_geometry(self):
        s=self.spec('chromix');s['screen'].update(width=1920,height=1080);s['window']={'width':1920,'height':1080}
        self.assertTrue(chromix.maximize_window(s))
        s['window']['width']=1000
        self.assertFalse(chromix.maximize_window(s))
        s['screen']['mode']='auto'
        self.assertTrue(chromix.maximize_window(s))
        s=self.spec('chromix');s['schemaVersion']='browser-platform/chromix-environment/v3'
        self.assertFalse(chromix.maximize_window(s))
    def test_auto_runtime_mode_and_display_overrides(self):
        from acceptance import environment
        for engine in artifact.VERSIONS:
            s=self.spec(engine);s['screen'].update(mode='auto',dpr='system')
            raw=json.dumps(s).encode();env=environment(s,hashlib.sha256(raw).hexdigest())
            artifact.verify(s,engine,raw,env)
            for key,value in [('BROWSER_PLATFORM_DISPLAY_MODE','fixed'),('MAX_RES','7680x4320'),('SELKIES_MANUAL_WIDTH','1280')]:
                with self.assertRaises(ValueError):artifact.verify(s,engine,raw,{**env,key:value})
            legacy=copy.deepcopy(s);legacy['schemaVersion']=artifact.LEGACY_SCHEMAS[engine]
            with self.assertRaises(ValueError):artifact.validate(legacy,engine)
        flags=chromix.arguments(self.spec('chromix'),123,Path('/config/.chromix'),'https://example.com/')
        self.assertIn('--force-device-scale-factor=1',flags)
        s=self.spec('chromix');s['screen'].update(mode='auto',dpr='system')
        flags=chromix.arguments(s,123,Path('/config/.chromix'),'https://example.com/')
        self.assertFalse(any('force-device-scale-factor' in f for f in flags))
    def test_targets_are_engine_and_version_exact(self):
        for ident,(engine,version,_) in native_jobs.TARGETS.items():
            v={'browser_template_id':ident,'browser_template_revision':1,'engine':engine,'browser_version':version};validate_target_shape(v)
            v['browser_version']='1'
            with self.assertRaises(ValueError):validate_target_shape(v)
    def test_frozen_sources_isolate_engines_and_display_reuse(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);fp={'version':2,'id':'fp-'+'a'*16,'revision':1,'label':'Generic','created_at':'now','locale':'zh-CN','languages':['zh-CN','en-US'],'timezone':'Asia/Taipei'}
            dp={'id':'display-'+'b'*16,'revision':1,'label':'Desktop','created_at':'now','mode':'fixed','width':1280,'height':900,'dpr':1,'window_width':1280,'window_height':900}
            refs={}
            for key,kind,v in [('fingerprint','fingerprints',fp),('display','displays',dp)]:
                p=root/'templates'/kind/(v['id']+'.json');p.parent.mkdir(parents=True);write(p,v);refs[key+'_id']=v['id'];refs[key+'_sha256']=sha(p)
            req={'version':3,'templates':refs,'spec':{'id':'env-custom-qa','revision':1,'locale':fp['locale'],'languages':fp['languages'],'timezone':fp['timezone'],'screen':{'width':1280,'height':900,'deviceScaleFactor':1},'window':{'width':1280,'height':900}}}
            artifacts=[]
            for index,(ident,engine,version) in enumerate([('chromix-linux-154','chromix','154.0.8037.57'),('firefox-linux-155','firefox','155.0.1')]):
                req['generation']={'browser_template_id':ident,'browser_template_revision':1,'engine':engine,'browser_version':version}
                out=root/str(index);out.mkdir();value,_,_,created=native_jobs.generate(root,req,'sha256:'+'a'*64,out);self.assertEqual(created,1)
                second,_,_,created=native_jobs.generate(root,req,'sha256:'+'a'*64,out);self.assertEqual(second,value);self.assertEqual(created,0)
                with self.assertRaisesRegex(ValueError,'NATIVE_CACHE_CHANGED'):native_jobs.generate(root,req,'sha256:'+'b'*64,out)
                artifacts.append(value)
                if engine=='chromix':
                    canonical=next((root/'fingerprint-cache'/fp['id']).glob('*/device.json'))
                    before=canonical.read_bytes();cached=json.loads(before)
                    variant=canonical.parent/'runtimes'/('b'*64)/'device.json'
                    variant.parent.mkdir(parents=True,mode=0o700)
                    write(variant,{**cached,'image':'sha256:'+'b'*64})
                    newout=root/'upgraded';newout.mkdir()
                    updated,_,_,created=native_jobs.generate(root,req,'sha256:'+'b'*64,newout)
                    self.assertEqual(updated['seed'],value['seed']);self.assertEqual(created,0)
                    self.assertEqual(canonical.read_bytes(),before)
                    self.assertEqual(native_jobs.generate(root,req,'sha256:'+'a'*64,out)[0],value)
                    # An old artifact cannot be overwritten by a new runtime.
                    with self.assertRaisesRegex(ValueError,'NATIVE_ARTIFACT_CHANGED'):native_jobs.generate(root,req,'sha256:'+'b'*64,out)
                    for field,bad in [('seed',cached['seed']+1),('source_sha256','c'*64),('generation',{})]:
                        write(variant,{**cached,'image':'sha256:'+'b'*64,field:bad})
                        with self.assertRaisesRegex(ValueError,'NATIVE_CACHE_CHANGED'):native_jobs.generate(root,req,'sha256:'+'b'*64,newout)
                    variant.unlink()
                    with self.assertRaisesRegex(ValueError,'NATIVE_CACHE_CHANGED'):native_jobs.generate(root,req,'sha256:'+'b'*64,newout)
            self.assertIn('seed',artifacts[0]);self.assertNotIn('seed',artifacts[1])
            self.assertEqual(len(list((root/'fingerprint-cache'/fp['id']).glob('*/device.json'))),2)
    def test_incomplete_or_failed_acceptance_never_publishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'report.json';write(p,{'status':'pass','phase':'all'})
            with self.assertRaises(ValueError):native_jobs.accepted(p,root/'artifact','sha256:'+'a'*64)

    def test_language_preferences_preserve_home_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);profile=home/'profile/Default';profile.mkdir(parents=True)
            p=profile/'Preferences';p.write_text(json.dumps({'intl':{'other':'kept'},'bookmarks':{'kept':True}}))
            chromix.configure_languages(home,['zh-CN','en-US','en'])
            self.assertEqual(json.loads(p.read_bytes()),{'intl':{'other':'kept','accept_languages':'zh-CN,en-US,en','selected_languages':'zh-CN,en-US,en'},'bookmarks':{'kept':True}})

    def test_registry_target_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'targets.json';target={'browser_template_id':'firefox-linux-155','engine':'firefox','browser_version':'155.0.1'}
            for key,value in [('engine','chromix'),('version','154.0'),('image','latest')]:
                entry={'engine':'firefox','version':'155.0.1','image':'sha256:'+'a'*64};entry[key]=value
                write(p,{'version':1,'targets':{'firefox-linux-155':entry}})
                with self.assertRaisesRegex(ValueError,'NATIVE_TARGET_UNSUPPORTED'):native_jobs.target_image(p,target)

if __name__=='__main__':unittest.main()
