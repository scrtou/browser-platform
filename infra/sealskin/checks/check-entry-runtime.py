#!/usr/bin/env python3
"""Inspect actual staged R5D Workers, sealed state and error/log boundaries.

All captured raw evidence stays in a new private runtime directory. Secrets
are passed to the controller probe on stdin, never Docker argv or environment.
"""

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
from urllib.parse import quote
import uuid


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


runner = module("entry_runner", Path(__file__).with_name("run-entry-auth.py"))
network = runner.network

PROCESS_PROBE = """import base64,json
from pathlib import Path
result={}
for directory in Path('/proc').iterdir():
 if not directory.name.isdigit(): continue
 entry={}
 try: entry['_uids']=next(line.split()[1:] for line in (directory/'status').read_text().splitlines() if line.startswith('Uid:'))
 except FileNotFoundError: continue
 for field in ('cmdline','environ'):
  try: entry[field]=base64.b64encode((directory/field).read_bytes()).decode()
  except FileNotFoundError: pass
  except PermissionError: entry[field+'_denied']=True
 if entry: result[directory.name]=entry
print(json.dumps(result))
"""

AUTH_PROBE = """import base64,http.client,json,sys
values=json.load(sys.stdin); result=[]
for item in values:
 for kind in ('missing','wrong-user','wrong-password','correct'):
  headers={'User-Agent':item['canary']}
  if kind!='missing':
   user=item['user'] if kind!='wrong-user' else item['canary']
   password=item['password'] if kind!='wrong-password' else item['canary']
   headers['Authorization']='Basic '+base64.b64encode((user+':'+password).encode()).decode()
  connection=http.client.HTTPConnection(item['ip'],item['port'],timeout=5)
  try:
   connection.request('GET','/'+item['session']+'/?probe='+item['canary'],headers=headers)
   response=connection.getresponse(); body=response.read(4<<20)
   result.append({'session':item['session'],'kind':kind,'status':response.status,
                  'body':base64.b64encode(body).decode(),'headers':list(response.getheaders())})
  finally: connection.close()
print(json.dumps(result))
"""


def private_bytes(path, value):
    with path.open("wb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(value)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    qa, output = args.root.resolve(), args.output.resolve()
    assert not output.exists() and qa.parent.parent in output.parents
    output.mkdir(mode=0o700)
    coordinator = runner.Coordinator(qa, output)
    source = coordinator.candidate / "build/payload/app/session_secrets.py"
    sealed = module("entry_session_secrets", source)
    database = qa / "config/.config/sealskin/sessions.yml"
    envelope = sealed.read(database)
    assert sealed.sealed(envelope)
    sessions = sealed.decode(envelope, database)
    canary = "R5D_SECRET_" + uuid.uuid4().hex
    secrets = {"error-canary": canary.encode()}
    auth, identities, inspections = [], {}, {}
    for profile in coordinator.profiles:
        worker, binding, _ = coordinator.worker(profile)
        sid = binding["session_id"]
        session = sessions[sid]
        assert session["display_secret_version"] == 1
        for field in ("custom_user", "password", "access_token", "master_token", "controller_token", "viewer_token"):
            if session.get(field):
                secrets[profile + "-" + field] = session[field].encode()
        secrets[profile + "-basic-encoded"] = base64.b64encode((session["custom_user"] + ":" + session["password"]).encode())
        auth.append({"session": sid, "ip": session["ip"], "port": session["port"],
                     "user": session["custom_user"], "password": session["password"], "canary": canary})
        identities[profile] = {"worker": worker["Id"], "started_at": worker["State"]["StartedAt"], "session": sid}
        inspections[profile] = worker
    assert len(sessions) == len(identities) == 2
    for account in coordinator.accounts["accounts"]:
        secrets[account["username"] + "-entry-password"] = account["password"].encode()
    secrets["session-state-key"] = sealed.key_path(database).read_bytes()
    for key, value in list(secrets.items()):
        if key != "session-state-key":
            encoded = quote(value.decode(), safe="").encode()
            if encoded != value:
                secrets[key + "-url-encoded"] = encoded

    leaks, scanned = [], []

    def scan(label, raw):
        scanned.append(label)
        for name, value in secrets.items():
            if value and value in raw:
                leaks.append({"surface": label, "secret_class": name})
        if b"-----BEGIN PRIVATE KEY-----" in raw or b"-----BEGIN RSA PRIVATE KEY-----" in raw:
            leaks.append({"surface": label, "secret_class": "private-key-pem"})

    command = ["docker", "exec", "-i", network.SERVER, "python3", "-c", AUTH_PROBE]
    probe = subprocess.run(["sg", "docker", "-c", shlex.join(command)], input=json.dumps(auth).encode(), capture_output=True)
    private_bytes(output / "worker-auth-probe.json", probe.stdout)
    private_bytes(output / "worker-auth-probe.log", probe.stderr)
    assert probe.returncode == 0, "WORKER_AUTH_PROBE_FAILED"
    responses = json.loads(probe.stdout)
    assert len(responses) == 8
    for response in responses:
        assert response["status"] == (200 if response["kind"] == "correct" else 401)
        scan("worker-http-" + response["session"] + "-" + response["kind"], base64.b64decode(response["body"]))
        scan("worker-http-headers-" + response["kind"], json.dumps(response["headers"]).encode())

    status, _, raw = network.request("POST", "/auth/login", "csrf=" + canary + "&password=" + canary,
        {"Host": "entry.r5d.test:29443", "Origin": "https://wrong.r5d.test", "Content-Type": "application/x-www-form-urlencoded"}, port=29110)
    assert status == 403
    private_bytes(output / "entry-error.txt", raw)
    scan("entry-error-response", raw)
    status, value = coordinator.client.call("POST", "/api/profile-runtime/network-qa-home-entry-a/resume",
                                           {"profile_id": {"value": canary}, "application_id": canary})
    assert status == 422
    network.write_json(output / "api-error.json", value)
    scan("api-error-response", json.dumps(value).encode())

    counts = {}
    for profile, worker in inspections.items():
        captured = json.dumps(worker).encode()
        private_bytes(output / (profile + "-inspect.json"), captured)
        scan(profile + "-docker-inspect", captured)
        assert not any(v.split("=", 1)[0] in {"PASSWORD", "CUSTOM_USER", "SELKIES_MASTER_TOKEN"}
                       or v.startswith("FILE__") for v in worker["Config"]["Env"])
        inputs = [m for m in worker["Mounts"] if m["Destination"] == "/run/browser-platform-session-input"]
        assert len(inputs) == 1 and inputs[0]["RW"] is False
        directory = coordinator.display / ("session-" + identities[profile]["session"])
        assert inputs[0]["Source"] == str(directory)
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        for path in directory.iterdir():
            info = path.lstat()
            assert stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.geteuid()
            assert stat.S_IMODE(info.st_mode) == 0o600
        assert "/run/browser-platform-display" in worker["HostConfig"]["Tmpfs"]

        processes = {}
        pending, queried = {"0"}, set()
        while pending:
            uid = sorted(pending)[0]
            pending.remove(uid)
            queried.add(uid)
            result = network.docker("exec", "--user", uid, worker["Id"], "python3", "-c", PROCESS_PROBE)
            private_bytes(output / (profile + "-processes-" + uid + ".json"), result.stdout.encode())
            for pid, fields in json.loads(result.stdout).items():
                pending.update(set(fields.get("_uids", [])) - queried)
                assert len(pending | queried) <= 16
                observed = processes.setdefault(pid, {})
                for field in ("cmdline", "environ"):
                    if field in fields:
                        observed[field] = fields[field]
        for pid, fields in processes.items():
            for field, encoded in fields.items():
                raw = base64.b64decode(encoded)
                scan(profile + "-process-" + pid + "-" + field, raw)
                if field == "environ":
                    assert not any(v.split(b"=", 1)[0] in {b"PASSWORD", b"CUSTOM_USER", b"SELKIES_MASTER_TOKEN"}
                                   for v in raw.split(b"\0"))
        missing = {pid: sorted({"cmdline", "environ"} - set(fields)) for pid, fields in processes.items() if len(fields) != 2}
        # A short-lived probe can exit between the two reads; only a surviving
        # process with an unreadable surface is an acceptance failure.
        survivor_code = "import json; from pathlib import Path; print(json.dumps([p.name for p in Path('/proc').iterdir() if p.name.isdigit()]))"
        survivors = set(json.loads(network.docker("exec", worker["Id"], "python3", "-c", survivor_code).stdout))
        assert not (set(missing) & survivors), "WORKER_PROCESS_SCAN_INCOMPLETE"
        home = qa / "storage/network-qa" / coordinator.profiles[profile]["home_name"]
        files = 0
        for path in home.rglob("*"):
            info = path.lstat()
            if stat.S_ISREG(info.st_mode):
                assert info.st_size <= 128 << 20, "HOME_FILE_EXCEEDS_SCAN_BOUND"
                scan(profile + "-home/" + str(path.relative_to(home)), path.read_bytes())
                files += 1
        log = network.docker("logs", worker["Id"])
        logs = (log.stdout + log.stderr).encode()
        private_bytes(output / (profile + "-worker.log"), logs)
        scan(profile + "-nginx-selkies-log", logs)
        counts[profile] = {"home_files": files, "processes": len(processes), "missing_surviving_processes": 0}

    for path in (database, qa / "adapter-config.json", qa / "adapter-state.json", qa / "adapter.log", qa / "front-caddy.log"):
        scan("ordinary-" + path.name, path.read_bytes())
    controller_log = network.docker("logs", network.SERVER)
    raw = (controller_log.stdout + controller_log.stderr).encode()
    private_bytes(output / "controller-caddy-python.log", raw)
    scan("controller-caddy-python-log", raw)
    for profile, before in identities.items():
        after, binding, _ = coordinator.worker(profile)
        assert after["Id"] == before["worker"] and after["State"]["StartedAt"] == before["started_at"]
        assert binding["session_id"] == before["session"]
    result = {"status": "pass" if not leaks else "fail", "checked_at": datetime.now(timezone.utc).isoformat(),
        "candidate": str(coordinator.candidate), "sealed_session_state": True, "private_display_mounts": True,
        "real_basic_auth": {"correct": 2, "missing_or_wrong_denied": 6}, "error_response_checks": 2,
        "workers_preserved": True, "scanned_surfaces": len(scanned), "counts": counts, "leaks": leaks}
    network.write_json(output / "result.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "leaks"}), flush=True)
    return 0 if not leaks else 1


if __name__ == "__main__":
    raise SystemExit(main())
