#!/usr/bin/env python3
"""Recover a retained R6AS QA launch, then verify delayed real launch responses."""
import argparse,copy,hashlib,http.client,http.server,importlib.util,json,os,shutil,threading,time,uuid
from pathlib import Path
spec=importlib.util.spec_from_file_location('direct',Path(__file__).with_name('check-direct-network.py'));direct=importlib.util.module_from_spec(spec);spec.loader.exec_module(direct)
net=direct.network

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--adapter',type=Path,required=True);a=p.parse_args();os.umask(0o077)
 qa=a.root.resolve();assert qa.name=='qa' and qa.parent.name=='firefox' and qa.parent.parent.name.startswith('r6as-') and os.getuid()==1000
 work=qa.parent;out=work/'slow-launch';out.mkdir(mode=0o700)
 c=direct.DirectChecks(qa,out/'setup',native_engine='firefox');c.case=out/'unknown-recovery';c.case.mkdir()
 state=json.loads((qa/'adapter-state.json').read_text());assert state['bindings']['network-qa-browser']['status']=='unknown'
 status,value=c.checks.control('browser','stop');assert status==200 and value['result']['status']=='stopped'
 net.write_json(c.case/'safe-close.json',{'status':status,'result':value})
 for key in ('a','b'):assert all(not c.snapshot(key)[kind] for kind in ('records','workers','resources'))
 c.stop_adapter()
 previous=qa/'bin/profile-adapter';assert hashlib.sha256(previous.read_bytes()).hexdigest()=='8fb90eb29208ccea7ba235c814b6669470af47ba6c026a5f53c03e9f2cf95393'
 candidate_sha=hashlib.sha256(a.adapter.read_bytes()).hexdigest();shutil.copy2(previous,out/'previous-adapter')
 temp=previous.with_name('profile-adapter.new');shutil.copy2(a.adapter,temp);temp.chmod(0o755);os.replace(temp,previous)
 for key in ('a','b'):
  operation=uuid.uuid4().hex;c.state[key]['request']['operation_id']=operation;c.state[key]['stop']['operation_id']=operation;c.state[key]['stop'].pop('session_id',None)
 c.save();c.run('prepare')
 config_path=qa/'adapter-config.json';original=json.loads(config_path.read_text());assert original['sealskin']['api_base_url']=='http://127.0.0.1:28110'
 delayed=[]
 class Proxy(http.server.BaseHTTPRequestHandler):
  protocol_version='HTTP/1.1'
  def log_message(self,*args):pass
  def forward(self):
   assert self.path.startswith('/api/') and len(self.path)<4096
   size=int(self.headers.get('Content-Length','0'));assert 0<=size<=4*1024*1024
   body=self.rfile.read(size) if size else None
   headers={k:v for k,v in self.headers.items() if k.lower() not in ('host','connection','transfer-encoding')}
   started=time.monotonic();conn=http.client.HTTPConnection('127.0.0.1',28110,timeout=200)
   try:
    conn.request(self.command,self.path,body,headers);response=conn.getresponse();data=response.read()
    if self.command=='POST' and self.path=='/api/launch/url':
     assert response.status==200;time.sleep(50);delayed.append({'status':response.status,'elapsed_seconds':time.monotonic()-started,'response_delay_seconds':50})
    self.send_response(response.status)
    for k,v in response.getheaders():
     if k.lower() not in ('connection','transfer-encoding','content-length','server','date'):self.send_header(k,v)
    self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
   finally:conn.close()
  do_GET=do_POST=do_PUT=do_PATCH=do_DELETE=forward
 server=http.server.ThreadingHTTPServer(('127.0.0.1',28112),Proxy);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 checks=direct.DirectChecks(qa,work/'direct',native_engine='firefox');write=net.write_json
 def routed_write(path,value):
  if path==config_path:
   value=copy.deepcopy(value);value['sealskin']['api_base_url']='http://127.0.0.1:28112'
  write(path,value)
 success=False
 try:
  net.write_json=routed_write
  checks.run('entry')
  assert len(delayed)==2 and all(x['elapsed_seconds']>=50 for x in delayed)
  assert hashlib.sha256(Path('/proc',str(json.loads((qa/'adapter-pid.json').read_text())['pid']),'exe').read_bytes()).hexdigest()==candidate_sha
  before={key:checks.checks.identity(checks.worker(key)) for key in ('a','b')}
  success=True
 finally:
  net.write_json=write;checks.stop_adapter()
  current=json.loads(config_path.read_text());current['sealskin']['api_base_url']=original['sealskin']['api_base_url'];write(config_path,current)
  server.shutdown();server.server_close();thread.join(timeout=5)
 if success:
  checks.checks.start_adapter();assert before=={key:checks.checks.identity(checks.worker(key)) for key in ('a','b')}
  write(out/'result.json',{'result':'PASS','adapter_sha256':candidate_sha,'original_unknown_safely_closed':True,'delayed_launch_requests':delayed,'no_duplicate_launch':True,'normal_endpoint_restored':True,'workers_preserved':True})
  print('PASS two real native launches delayed beyond 45 seconds, no duplicate launch, normal endpoint restored')

if __name__=='__main__':main()
