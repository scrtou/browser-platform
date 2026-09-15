#!/usr/bin/env python3
"""Inspect, toggle, stop or remove one exactly identified temporary endpoint.

SSH uses only the supplied key and pinned host keys. Deployment evidence binds
the host, UID, directory, argv and process start ticks. Detailed output is
private and never printed. No sudo, host firewall or unrelated service changes.
"""

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import time

REMOTE = r'''
import hashlib,json,os,pathlib,re,shutil,signal,sys,time
os.umask(0o077)
expected=json.loads(sys.stdin.read())
action,mode=sys.argv[1:]
root=pathlib.Path(expected['directory'])
assert re.fullmatch('r5c[23]-[a-f0-9]{16}',root.name)
assert root.parent==pathlib.Path.home() and not root.is_symlink() and root.stat().st_uid==expected['uid']==os.getuid()
launch=json.loads((root/'launch.json').read_text())
assert all(launch[key]==expected[key] for key in ('pid','argv','directory','run_id','endpoint','start_ticks'))
manifest=json.loads((root/'manifest.json').read_text())
assert manifest['run_id']==expected['run_id'] and manifest['endpoint']==expected['endpoint']
for name,sha in manifest['files'].items():
 if name not in ('state/mode.json','state/rotation.json'):
  path=root/name
  assert path.is_file() and not path.is_symlink() and path.stat().st_uid==os.getuid()
  assert hashlib.sha256(path.read_bytes()).hexdigest()==sha
def process():
 p=pathlib.Path('/proc')/str(expected['pid'])
 if not p.exists():return None
 assert p.stat().st_uid==expected['uid']
 stat=(p/'stat').read_text().rsplit(')',1)[1].split()
 assert stat[19]==str(expected['start_ticks']), 'PID identity changed'
 if stat[0]=='Z':return None
 assert (p/'cmdline').read_bytes().split(b'\0')[:-1]==[v.encode() for v in expected['argv']]
 return p
before=process()
record={'action':action,'endpoint':expected['endpoint'],'run_id':expected['run_id'],'remote_started_at':time.time(),
        'plan_sha256':manifest['plan_sha256'],'pid':expected['pid'],'start_ticks':expected['start_ticks'],'running_before':before is not None}
if action in ('mode','rotation'):
 assert before is not None
 if action=='rotation':
  assert mode in ('local','peer') and json.loads((root/'config.json').read_text()).get('rotation_enabled') is True
  target,field='rotation','exit'
 else:
  assert mode in ('online','offline')
  target,field='mode','mode'
 temporary=root/('state/'+target+'.tmp')
 with temporary.open('w') as f:
  os.fchmod(f.fileno(),0o600);json.dump({field:mode},f);f.flush();os.fsync(f.fileno())
 os.replace(temporary,root/('state/'+target+'.json'))
 time.sleep(.4)
elif action=='stop':
 if before is not None:
  os.kill(expected['pid'],signal.SIGTERM)
  deadline=time.monotonic()+10
  while process() is not None and time.monotonic()<deadline:time.sleep(.1)
 assert process() is None and (root/'state/metrics.json').is_file(), 'Endpoint did not stop normally'
elif action=='purge':
 assert before is None and (root/'state/metrics.json').is_file(), 'Stop and collect evidence first'
 for path in root.rglob('*'):
  assert not path.is_symlink() and path.stat().st_uid==os.getuid()
 shutil.rmtree(root)
 print(json.dumps({**record,'result':'REMOVED','remote_finished_at':time.time(),'directory_exists':root.exists()}))
 sys.exit(0)
current=process()
record['running_after']=current is not None
record['mode']=json.loads((root/'state/mode.json').read_text())
if (root/'state/rotation.json').exists():record['rotation']=json.loads((root/'state/rotation.json').read_text())
if current is not None:
 status=dict(line.split(':',1) for line in (current/'status').read_text().splitlines() if ':' in line)
 record['memory']={key:status.get(key,'').strip() for key in ('VmRSS','VmHWM','VmSize','Threads')}
if action in ('collect','stop'):
 record['logs']={path.name:path.read_text() for path in sorted((root/'state').glob('events.jsonl*'))}
 record['console']=(root/'state/console.log').read_text()
 record['config']=json.loads((root/'config.json').read_text())
 record['manifest']=manifest
 if (root/'state/metrics.json').exists():record['metrics']=json.loads((root/'state/metrics.json').read_text())
record.update(result='PASS',remote_finished_at=time.time())
print(json.dumps(record))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "collect", "mode", "rotation", "stop", "purge"))
    parser.add_argument("--mode", choices=("online", "offline"), default="online")
    parser.add_argument("--exit", choices=("local", "peer"), default="local", help="Actual egress for a rotation-enabled endpoint")
    parser.add_argument("--deployment", required=True, type=Path)
    parser.add_argument("--ssh-key", required=True, type=Path)
    parser.add_argument("--known-hosts", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    deployment = json.loads(args.deployment.read_text())
    if deployment["exit_code"] != 0 or deployment["remote"]["result"] != "STARTED":
        raise ValueError("Successful endpoint deployment evidence required")
    expected = {**deployment["remote"]["launch"], "uid": deployment["remote"]["uid"]}
    command = ["ssh", "-p", "65522", "-i", str(args.ssh_key.resolve()), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
               "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10", "-o", "UserKnownHostsFile=" + str(args.known_hosts.resolve()),
               "temptest@" + deployment["host"], shlex.join(["python3", "-c", REMOTE, args.action, args.exit if args.action == "rotation" else args.mode])]
    started = time.time()
    result = subprocess.run(command, input=json.dumps(expected), text=True, capture_output=True, timeout=25)
    record = {"local_started_at": started, "local_finished_at": time.time(), "host": deployment["host"],
              "exit_code": result.returncode, "stderr": result.stderr}
    if result.returncode == 0:
        record["remote"] = json.loads(result.stdout)
        logs = record["remote"].pop("logs", {})
        for name, content in logs.items():
            if name not in {"events.jsonl", "events.jsonl.1", "events.jsonl.2"}:
                raise ValueError("Unexpected endpoint log name")
            (args.output / name).write_text(content)
    (args.output / "result.json").write_text(json.dumps(record, indent=2) + "\n")
    if result.returncode:
        raise RuntimeError("Endpoint operation failed; inspect private evidence")
    print(json.dumps({"result": record["remote"]["result"], "action": args.action,
                      "endpoint": expected["endpoint"], "run_id": expected["run_id"]}))


if __name__ == "__main__":
    main()
