import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import template_sources as source

class TemplateCompositionTests(unittest.TestCase):
    def test_builtin_sources_and_reserved_ids(self):
        self.generic()
        for fp in source.BUILTIN_FINGERPRINTS.values():
            path=self.root/'templates/fingerprints'/(fp['id']+'.json');source.write(path,fp)
            self.req['templates'].update(fingerprint_id=fp['id'],fingerprint_sha256=source.sha(path))
            self.req['spec'].update({key:fp[key] for key in ('locale','languages','timezone')})
            source.source_records(self.root,self.req)
            for field,value in [('builtin',False),('locale','invalid'),('timezone','UTC'),('id','fp-'+'f'*16)]:
                changed={**fp,field:value};source.write(path,changed)
                self.req['templates']['fingerprint_sha256']=source.sha(path)
                with self.assertRaisesRegex(ValueError,'FINGERPRINT_TEMPLATE_FIELDS'):source.source_records(self.root,self.req)
            source.write(path,fp);self.req['templates']['fingerprint_sha256']=source.sha(path)
        self.dp.update(id='display-0000000000000002',builtin=True,width=1920,height=1080,window_width=1920,window_height=1080)
        path=self.root/'templates/displays'/(self.dp['id']+'.json');source.write(path,self.dp)
        self.req['templates'].update(display_id=self.dp['id'],display_sha256=source.sha(path))
        self.req['spec'].update(screen={'width':1920,'height':1080,'deviceScaleFactor':1},window={'width':1920,'height':1080})
        source.source_records(self.root,self.req)
        for field,value in [('builtin',False),('width',1280),('id','display-'+'f'*16)]:
            source.write(path,{**self.dp,field:value});self.req['templates']['display_sha256']=source.sha(path)
            with self.assertRaises(ValueError):source.source_records(self.root,self.req)

    def test_republication_preserves_installed_builtin_flag(self):
        path=self.root/'catalog.json'
        entry={'browser_template_id':'chromix-linux-154','browser_engine':'chromix','browser_version':'154.0.8037.57','screen':'1920x1080@1','id':'custom-test'}
        display={'id':'display-test','revision':1,'label':'Test','mode':'fixed'}
        source.write(path,{'browser_templates':[{'id':entry['browser_template_id'],'engine':'chromix','version':entry['browser_version']}],'display_templates':[],'compatibility':[]})
        def publish():source.publish_compatibility(path,entry,display,lambda p,b:source.write(p,json.loads(b)),lambda v:json.dumps(v).encode())
        publish();catalog=source.raw_json(path)
        self.assertNotIn('builtin',catalog['compatibility'][0])
        catalog['compatibility'][0]['builtin']=True;source.write(path,catalog);publish()
        self.assertTrue(source.raw_json(path)['compatibility'][0]['builtin'])

    def test_publish_empty_go_catalog_and_reject_non_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'catalog.json'
            entry={'browser_template_id':'chromix-linux-154','browser_engine':'chromix','browser_version':'154.0.8037.57','screen':'1280x900@1','id':'custom-test'}
            display={'id':'display-test','revision':1,'label':'Test','mode':'fixed'}
            catalog={'browser_templates':[{'id':entry['browser_template_id'],'engine':'chromix','version':entry['browser_version']}],'display_templates':None,'compatibility':None}
            source.write(path,catalog)
            source.publish_compatibility(path,entry,display,lambda p,b:p.write_bytes(b),lambda v:json.dumps(v).encode())
            self.assertEqual(len(source.raw_json(path)['compatibility']),1)
            catalog['display_templates']='invalid';source.write(path,catalog)
            with self.assertRaisesRegex(ValueError,'TEMPLATE_CATALOG_INVALID'):
                source.publish_compatibility(path,entry,display,lambda p,b:p.write_bytes(b),lambda v:json.dumps(v).encode())

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.fp={'id':'fp-'+'a'*16,'revision':1,'label':'US','created_at':'2026-10-01','engine':'camoufox','browser_version':'152.0','locale':'en-US','languages':['en-US'],'timezone':'UTC'}
        self.dp={'id':'display-'+'b'*16,'revision':1,'label':'HD','created_at':'2026-10-01','mode':'fixed','width':1280,'height':720,'dpr':1,'window_width':1280,'window_height':720}
        for kind,v in [('fingerprints',self.fp),('displays',self.dp)]:
            d=self.root/'templates'/kind;d.mkdir(parents=True);source.write(d/(v['id']+'.json'),v)
        self.req={'templates':{'fingerprint_id':self.fp['id'],'fingerprint_sha256':source.sha(self.root/'templates/fingerprints'/(self.fp['id']+'.json')),'display_id':self.dp['id'],'display_sha256':source.sha(self.root/'templates/displays'/(self.dp['id']+'.json'))},'spec':{'id':'env-custom-'+'c'*16,'locale':'en-US','languages':['en-US'],'timezone':'UTC','screen':{'width':1280,'height':720,'deviceScaleFactor':1},'window':{'width':1280,'height':720}}}
        self.image='sha256:'+'d'*64
        self.base={'id':'base','createdAt':'before','spec':copy.deepcopy(self.req['spec']),'runtimeImageDigest':self.image,'resolvedConfig':{'canvas:seed':123,'navigator.hardwareConcurrency':8,'screen.colorDepth':24,'screen.width':1280,'screen.height':720},'browserforgeFingerprint':{'original':'retained'},'firefoxUserPrefs':{'network.proxy.type':1}}
    def test_composition_changes_only_display_fields(self):
        spec=copy.deepcopy(self.req['spec']);spec['screen']['width']=1600;spec['window']['width']=1600
        value=source.compose(self.base,spec,self.image)
        self.assertEqual(source.non_display(value),source.non_display(self.base))
        self.assertEqual(value['browserforgeFingerprint'],self.base['browserforgeFingerprint'])
        self.assertEqual(value['firefoxUserPrefs'],self.base['firefoxUserPrefs'])
        self.assertEqual(value['resolvedConfig']['screen.availWidth'],1600)
    def test_revision_mismatch_and_spec_override_fail(self):
        source.source_records(self.root,self.req)
        req=copy.deepcopy(self.req);req['spec']['screen']['width']=1600
        with self.assertRaisesRegex(ValueError,'TEMPLATE_SPEC_MISMATCH'):source.source_records(self.root,req)
        req=copy.deepcopy(self.req);req['templates']['fingerprint_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'TEMPLATE_REVISION_CHANGED'):source.source_records(self.root,req)
        req=copy.deepcopy(self.req);req['templates']['fingerprint_id']='../../outside'
        with self.assertRaises(ValueError):source.source_records(self.root,req)
    def test_second_combination_reuses_source_and_detects_corruption(self):
        calls=[]
        def generator(spec,image,out,evidence):calls.append(1);source.write(out/'environment.json',self.base);return 1
        out=self.root/'out';out.mkdir();evidence=self.root/'evidence';evidence.mkdir()
        source.generate_combination(self.root,self.req,self.image,out,evidence,generator)
        out2=self.root/'out2';out2.mkdir()
        source.generate_combination(self.root,self.req,self.image,out2,evidence,generator)
        self.assertEqual(len(calls),1)
        cache=self.root/'fingerprint-cache'/self.fp['id']/'environment.json';cache.write_text('{}')
        with self.assertRaisesRegex(ValueError,'TEMPLATE_CACHE_CHANGED'):source.generate_combination(self.root,self.req,self.image,out2,evidence,generator)
    def test_different_image_cannot_reuse_source(self):
        with self.assertRaisesRegex(ValueError,'TEMPLATE_IMAGE_CHANGED'):source.compose(self.base,self.req['spec'],'sha256:'+'e'*64)
    def test_auto_removes_overrides_and_reference_generation_is_display_independent(self):
        self.generic()
        self.dp.update(id='display-0000000000000001',mode='auto',builtin=True,dpr_mode='system',dpr=0)
        path=self.root/'templates/displays'/(self.dp['id']+'.json');source.write(path,self.dp)
        self.req['templates'].update(display_id=self.dp['id'],display_sha256=source.sha(path))
        self.req['spec']['screen']={'width':1280,'height':720,'mode':'auto','dprMode':'system'}
        self.req['spec']['requiredCapabilities']=['auto-screen','system-dpr']
        def generator(spec,image,out,evidence):
            self.assertEqual(spec['screen'],{'width':1920,'height':1080,'deviceScaleFactor':1})
            self.assertEqual(spec['window'],{'width':1920,'height':1080})
            source.write(out/'environment.json',self.base);return 1
        out=self.root/'out';out.mkdir();evidence=self.root/'evidence';evidence.mkdir()
        source.generate_combination(self.root,self.req,self.image,out,evidence,generator)
        result=source.raw_json(out/'environment.json')
        self.assertFalse(source.DISPLAY_KEYS & result['resolvedConfig'].keys())
        self.assertEqual(source.non_display(result),source.non_display(self.base))
        self.assertEqual(result['firefoxUserPrefs']['layout.css.devPixelsPerPx'],'-1.0')
        self.assertEqual(result['browserforgeFingerprint'],self.base['browserforgeFingerprint'])
    def generic(self):
        self.fp.pop('engine');self.fp.pop('browser_version');self.fp['version']=2
        path=self.root/'templates/fingerprints'/(self.fp['id']+'.json')
        source.write(path,self.fp);self.req['templates']['fingerprint_sha256']=source.sha(path)
        self.req.update(version=3,generation={'browser_template_id':'camoufox-linux-v152','browser_template_revision':1,'engine':'camoufox','browser_version':'152.0'})

    def test_generic_requires_target_and_rejects_engine_fields(self):
        self.generic();source.source_records(self.root,self.req)
        bad=copy.deepcopy(self.req);bad['version']=2
        with self.assertRaisesRegex(ValueError,'GENERATION_TARGET_REQUIRED'):source.source_records(self.root,bad)
        bad=copy.deepcopy(self.req);bad['generation']['engine']='chromix'
        with self.assertRaisesRegex(ValueError,'GENERATION_TARGET_INVALID'):source.source_records(self.root,bad)
        self.fp['engine']='camoufox';path=self.root/'templates/fingerprints'/(self.fp['id']+'.json');source.write(path,self.fp)
        with self.assertRaisesRegex(ValueError,'FINGERPRINT_TEMPLATE_FIELDS'):source.source_records(self.root,self.req)

    def test_generic_cache_reuses_display_but_separates_target_and_rejects_image_drift(self):
        self.generic();calls=[]
        def generator(spec,image,out,evidence):
            calls.append(1);source.write(out/'environment.json',self.base);return 1
        evidence=self.root/'evidence';evidence.mkdir()
        for n in range(3):
            if n==1:
                self.dp['width']=self.dp['window_width']=1600
                path=self.root/'templates/displays'/(self.dp['id']+'.json');source.write(path,self.dp)
                self.req['templates']['display_sha256']=source.sha(path)
                self.req['spec']['screen']['width']=self.req['spec']['window']['width']=1600
            if n==2:self.req['generation']['browser_template_revision']=2
            out=self.root/str(n);out.mkdir()
            source.generate_combination(self.root,self.req,self.image,out,evidence,generator)
        self.assertEqual(len(calls),2)
        cache=self.root/'fingerprint-cache'/self.fp['id']
        self.assertEqual(len(list(cache.glob('*/environment.json'))),2)
        self.assertFalse((cache/'environment.json').exists())
        with self.assertRaisesRegex(ValueError,'TEMPLATE_CACHE_CHANGED'):
            source.generate_combination(self.root,self.req,'sha256:'+'e'*64,out,evidence,generator)

    def test_target_catalog_drift_and_runner_mismatch(self):
        self.generic();target=self.req['generation']
        b={'id':target['browser_template_id'],'revision':1,'status':'accepted','allow_new_browsers':True,'engine':'camoufox','version':'152.0','os_family':'linux','platform':'Linux x86_64','user_agent_product':'Firefox'}
        path=self.root/'catalog.json';source.write(path,{'browser_templates':[b]})
        source.validate_generation_target(path,target,b['id'])
        with self.assertRaisesRegex(ValueError,'GENERATION_RUNNER_MISMATCH'):source.validate_generation_target(path,target,'other')
        for k,v in [('revision',2),('version','153.0'),('status','rejected'),('allow_new_browsers',False),('platform','Win32')]:
            changed=dict(b);changed[k]=v;source.write(path,{'browser_templates':[changed]})
            with self.assertRaisesRegex(ValueError,'GENERATION_TARGET_CHANGED'):source.validate_generation_target(path,target,b['id'])

if __name__=='__main__':unittest.main()
