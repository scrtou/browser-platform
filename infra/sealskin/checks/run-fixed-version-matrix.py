#!/usr/bin/env python3
"""Orchestrate the isolated native protocol matrix on the independent QA host."""
import argparse,importlib.util,json,os,shutil,signal,subprocess,sys,time
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[3]
CONTROLLER='sha256:33a6d2fcd00502f6df7b8e75a2b3eaa70c0e933077919cbdda5dbe77d5fb7b57'
RELAY='sha256:d57f441789051be7d7a3770d66211f680741a5b413ca8c5dcc765b8ec8bd286d'
def run(args,log,timeout=600):
 with log.open('w') as f:subprocess.run(list(map(str,args)),stdout=f,stderr=subprocess.STDOUT,check=True,timeout=timeout)
def main():
 p=argparse.ArgumentParser();p.add_argument('phase',choices=['prepare','matrix','direct','upgrade','retire']);p.add_argument('--root',type=Path,required=True);p.add_argument('--engine',choices=['camoufox','chromix','firefox'],required=True);p.add_argument('--cases',nargs='+');a=p.parse_args();os.umask(0o077)
 root=a.root.resolve();assert root.name.startswith('r6as-') and 'runtime' in root.parts and os.getuid()==1000
 work=root/a.engine;qa=work/'qa';display=Path('/dev/shm')/('r6as-display-'+a.engine)
 if a.phase=='prepare':
  work.mkdir(mode=0o700);(qa/'bin').mkdir(parents=True,mode=0o700)
  for file in (root/'inputs/bin').iterdir():shutil.copy2(file,qa/'bin'/file.name)
  build=work/'build';build.mkdir();(build/'release.json').write_text(json.dumps({'image':CONTROLLER,'release':'r7g1-fixed-native-qa'}))
  display.mkdir(mode=0o700)
  source=work/'native-source';source.mkdir()
  for name in ['qa-browser.py','browser_client.py']:shutil.copy2(PROJECT/'infra/environment-engines'/name,source/name)
  shutil.copy2(PROJECT/'infra/firefox-proxy/check-bidi.py',source/'check_bidi.py');shutil.copy2(Path(__file__).with_name('native-network-client.py'),source/'native-network-client.py')
  path=source/'qa-browser.py';path.write_text(path.read_text().replace('import sys\n','import sys\nimport os\n').replace("'https://example.com/'","os.environ.get('SEALSKIN_URL','https://example.com/')"))
  shutil.copy2(root/'inputs'/a.engine/'entry.json',work/'entry.json')
  run([sys.executable,PROJECT/'infra/sealskin/lifecycle/prepare-network-qa.py','--root',qa,'--build',build,'--relay-image',RELAY,'--probe-image','sha256:d52c155eb78882b27c7780e77df335939d46cd06a514c9fa310039307542ee6a','--display-runtime-root',display,'--direct-host-evidence'],work/'prepare-base.log')
  run([sys.executable,Path(__file__).with_name('prepare-network-browser.py'),'--root',qa,'--native-catalog-entry',work/'entry.json'],work/'prepare-browser.log')
  print('PASS prepared',a.engine,flush=True)
 elif a.phase=='matrix':
  command=[sys.executable,Path(__file__).with_name('check-proxy-protocols.py'),'--root',qa,'--output',work/('protocols-'+str(int(time.time())))]
  if a.cases:command+=['--cases',*a.cases]
  run(command,work/('matrix-'+str(int(time.time()))+'.log'),timeout=3600);print('PASS native protocols',a.engine,flush=True)
 elif a.phase=='upgrade':
  run([sys.executable,Path(__file__).with_name('check-fixed-program-upgrade.py'),'--root',qa,'--baseline-adapter',root.parent/'r6ap-remote-recovery-20261002/inputs/bin/profile-adapter','--current-adapter',root/'inputs/bin/profile-adapter'],work/'upgrade.log',timeout=3600)
  print('PASS native server upgrade',a.engine,flush=True)
 elif a.phase=='direct':
  (work/'guard-image.json').write_text(json.dumps({'image_id':RELAY}))
  run([sys.executable,Path(__file__).with_name('check-direct-network.py'),'--root',qa,'--output',work/'direct','--native-engine',a.engine],work/'direct.log',timeout=3600)
  print('PASS native DIRECT',a.engine,flush=True)
 else:
  spec=importlib.util.spec_from_file_location('matrix',Path(__file__).with_name('check-proxy-protocols.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  matrix=m.Matrix(qa,work/('retire-'+str(int(time.time()))));matrix.stop()
  for profile in ['network-qa-browser','network-qa-b']:
   home=matrix.checks.definitions[profile]['home_name']
   status,snapshot=matrix.checks.client.call('GET','/api/profile-runtime/'+home)
   assert status==200 and all(not snapshot[key] for key in ['records','workers','resources'])
  assert not (qa/'adapter-pid.json').exists(), 'Retire the owned Adapter first'
  names=['network-qa-observer','network-qa-upstream','sealskin-network-qa']
  if subprocess.run(['docker','inspect','network-qa-direct-dns'],capture_output=True).returncode==0:names.insert(0,'network-qa-direct-dns')
  for name in names:
   info=json.loads(m.network.docker('inspect',name).stdout)[0];assert info['Config']['Labels'].get('io.browser-platform.qa')=='network-20260913'
   m.network.docker('stop','-t','15',name);m.network.docker('rm','-v',name)
  pid=json.loads((qa/'proxy-pid.json').read_text())['pid'];cmd=Path('/proc')/str(pid)/'cmdline';assert cmd.exists() and str(qa).encode() in cmd.read_bytes()
  # The recorded sg process owns the scoped proxy process group. Signal only
  # that new session after its controller has retired.
  assert os.getpgid(pid)==pid;os.killpg(pid,signal.SIGTERM)
  for _ in range(40):
   if not Path('/tmp/browser-platform-network-qa-docker.sock').exists():break
   time.sleep(.1)
  sock=Path('/tmp/browser-platform-network-qa-docker.sock')
  if sock.exists():
   proc=Path('/proc',str(pid),'stat');assert not proc.exists() or proc.read_text().split()[2]=='Z';sock.unlink()
  m.network.docker('network','rm','browser-platform-network-qa');assert not any(display.iterdir());display.rmdir()
  (work/'retired.json').write_text(json.dumps({'result':'PASS','generations_empty':True,'qa_resources_retired':True}));print('PASS retired',a.engine)
if __name__=='__main__':main()
