from pathlib import Path
import argparse,json,subprocess,os
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);args=p.parse_args();root=args.root.resolve();os.umask(0o077);assert root.parent.name=='r6au-consistent-20261002' and (root/'RECOVERY_PENDING').is_file()
cfg=json.loads((root/'controller-config/.config/sealskin/profile-secret-store.json').read_text());keyfile=Path(cfg['key_file']);image=json.loads((root/'metadata/controller-container.json').read_text())['Image']
policies=json.loads((root/'controller-config/.config/sealskin/profile-network-policies.json').read_text())['policies'];directory=json.loads((root/'adapter/dependencies/profile_directory.json').read_text());requests=[]
for record in directory['browsers']:
 if record.get('status')=='deleted':continue
 policy=policies.get(record.get('network_policy_id'),{})
 if policy.get('username_secret_ref'):
  requests.append({'grant':{'owner':policy['username'],'profile':policy['profile_id'],'home':policy['home_name'],'app':policy['application_id']},'username_ref':policy['username_secret_ref'],'password_ref':policy['password_secret_ref']})
requestfile=root.parent/'secret-readback-requests.json';requestfile.write_text(json.dumps(requests));requestfile.chmod(0o600);os.chown(requestfile,1000,1000)
code="""from pathlib import Path
from app.secret_store import FileSecretStore,SecretError
import json,os
store=FileSecretStore('/store',os.environ['BP_KEY_FILE']);requests=json.loads(Path('/requests.json').read_text());checked=0;denied=0;revoked=0
for req in requests:
 values=store._resolve(req['grant'],req['username_ref'],req['password_ref'])
 assert values['username'] and values['password'];checked+=1
 bad=dict(req['grant']);bad['home']='r6au-forbidden-home'
 try:store._resolve(bad,req['username_ref'],req['password_ref'])
 except SecretError as e:assert e.code=='SECRET_ACCESS_DENIED';denied+=1
 else:raise AssertionError('wrong grant accepted')
for path in (Path('/store')/'revocations').glob('*.json'):
 v=json.loads(path.read_text());assert v['revoked'] is True
 try:store.require_enabled(v['secret_id'],v['secret_version'])
 except SecretError as e:assert e.code=='SECRET_REVOKED';revoked+=1
 else:raise AssertionError('revocation ignored')
print(json.dumps({'result':'PASS','current_grants_readable':checked,'wrong_grants_denied':denied,'revocations_enforced':revoked,'mode':'offline immutable store; _resolve without writer lock because mount is read-only'}))
"""
cmd=['docker','run','--rm','--network','none','--read-only','--user','1000:1000','--mount','type=bind,src='+str(root/'controller-config/.config/sealskin/proxy-secret-store')+',dst=/store,readonly','--mount','type=bind,src='+str(root/'secret-master')+',dst='+str(keyfile.parent)+',readonly','--mount','type=bind,src='+str(requestfile)+',dst=/requests.json,readonly','-e','BP_KEY_FILE='+str(keyfile),'--entrypoint','python3',image,'-c',code]
r=subprocess.run(cmd,capture_output=True,timeout=80);(root.parent/'secret-readback.log').write_bytes(r.stdout+r.stderr);assert r.returncode==0,'secret readback failed';result=json.loads(r.stdout);assert result['current_grants_readable']==len(requests) and len(requests)>0;(root.parent/'secret-readback-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
