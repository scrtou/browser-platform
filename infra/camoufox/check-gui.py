#!/usr/bin/env python3
"""Check a disposable Camoufox desktop created through its normal entrypoint.

This interacts with the desktop and copies a controlled fixture into /tmp.
It refuses the existing Personal/Work Homes and never logs Session credentials.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from acceptance import docker
from environment import encode, expected_environment

ROOT = Path(__file__).resolve().parent


def checked(arguments, **kwargs):
    result = docker(arguments, timeout=kwargs.pop("timeout", 40), **kwargs)
    if result.returncode:
        raise RuntimeError("Docker GUI check failed during " + arguments[0])
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--acceptance", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    artifact_path, report_path = args.artifact.resolve(), args.acceptance.resolve()
    artifact = json.loads(artifact_path.read_bytes())
    acceptance = json.loads(report_path.read_bytes())
    artifact_sha = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    report_sha = hashlib.sha256(report_path.read_bytes()).hexdigest()
    container = json.loads(checked(["inspect", args.container]))[0]
    config, host = container["Config"], container["HostConfig"]
    env = dict(value.split("=", 1) for value in config["Env"])
    assert container["State"]["Running"] and config["Image"] == artifact["runtimeImageDigest"]
    assert config["Entrypoint"] == ["/usr/local/bin/browser-platform-entrypoint"]
    expected = expected_environment(artifact, artifact_sha)
    expected["BROWSER_PLATFORM_ACCEPTANCE_SHA256"] = report_sha
    assert all(env.get(key) == value for key, value in expected.items())
    assert acceptance["status"] == "pass" and acceptance["artifactSHA256"] == artifact_sha
    network = acceptance["network"]
    assert list(container["NetworkSettings"]["Networks"]) == [network]
    assert checked(["network", "inspect", network, "--format", "{{.Internal}}" ]).strip() == "true"
    mounts = {mount["Destination"]: mount for mount in container["Mounts"]}
    for path, destination in ((artifact_path, "/run/browser-platform/environment.json"),
                              (report_path, "/run/browser-platform/acceptance.json")):
        assert mounts[destination]["Source"] == str(path) and not mounts[destination]["RW"]
    home = Path(mounts["/config"]["Source"])
    assert home.name not in ("personal", "work"), "refusing to interact with an existing Personal/Work Home"
    assert host["Memory"] == 1536 * 1024 * 1024 and host["NanoCpus"] == 1500000000
    assert host["ShmSize"] == 256 * 1024 * 1024 and host["PidsLimit"] == 512
    assert "no-new-privileges:true" in host["SecurityOpt"]
    assert "ENVIRONMENT_ARTIFACT_OK" in checked([
        "exec", "--user", "1000", args.container, "/opt/camoufox-python/bin/python",
        "/usr/local/lib/browser-platform/environment.py", "verify"])
    network_script = """
import json,socket
result={}
for name, address in (('directIPv4Blocked',('1.1.1.1',443)),('directIPv6Blocked',('2606:4700:4700::1111',443))):
    try:
        connection=socket.create_connection(address,timeout=2)
    except OSError:result[name]=True
    else:
        connection.close();raise AssertionError('direct connection succeeded')
socket.getaddrinfo('profile-relay',1080)
result['relayAliasResolvable']=True
try:socket.getaddrinfo('example.com',443)
except socket.gaierror:result['publicDNSBlocked']=True
else:raise AssertionError('public DNS resolved')
print(json.dumps(result))
"""
    network_proof = json.loads(checked(["exec", "-i", "--user", "1000", args.container,
                                       "python3", "-"], input=network_script))
    display = checked(["exec", "--user", "1000", "-e", "DISPLAY=:1", args.container, "xrandr"])
    assert re.search(r"current 1920 x 1080", display)
    title = checked(["exec", "--user", "1000", "-e", "DISPLAY=:1", args.container,
                     "xdotool", "getactivewindow", "getwindowname"]).strip()
    assert "Example Domain" in title or "BP-QA" in title, "the configured startup page did not appear"
    voices = len(artifact["resolvedConfig"]["voices"])
    fixture = ("<!doctype html><html><head><meta charset='utf-8'><title>BP-QA-LOADING</title></head>"
               "<body style='height:2400px'><h1>繁體中文互動驗證</h1>"
               "<label>輸入 <input id='input' style='width:600px' oninput='document.title=\"BP-QA-INPUT:\"+this.value'></label>"
               "<textarea id='proof' readonly style='display:block;width:95%;height:600px'></textarea><script>const observe = "
               + (ROOT / "tests/observe.js").read_text() + ";observe({expectedVoiceCount:" + str(voices) + "})"
               ".then(value=>{const field=document.getElementById('proof');field.value=JSON.stringify(value);"
               "field.focus();field.select();document.title='BP-QA-READY';})"
               ".catch(()=>{document.title='BP-QA-ERROR'});</script></body></html>")
    checked(["exec", "-i", "--user", "1000", args.container, "python3", "-c",
             "import sys;open('/tmp/browser-platform-qa.html','w').write(sys.stdin.read())"], input=fixture)
    script = """
import json,subprocess,time
def command(*args):return subprocess.run(args,capture_output=True,text=True,check=True).stdout.strip()
command('xdotool','key','--clearmodifiers','ctrl+l')
command('xdotool','type','--clearmodifiers','--delay','1','file:///tmp/browser-platform-qa.html')
command('xdotool','key','Return')
for _ in range(100):
    title=command('xdotool','getactivewindow','getwindowname')
    if title.startswith('BP-QA-READY'):break
    if title.startswith('BP-QA-ERROR'):raise RuntimeError('fixture failed')
    time.sleep(.2)
else:raise RuntimeError('fixture did not become ready')
command('xdotool','key','--clearmodifiers','ctrl+a','ctrl+c')
time.sleep(.2)
print(json.dumps(json.loads(command('xclip','-selection','clipboard','-o'))))
"""
    observed = json.loads(checked(["exec", "-i", "--user", "1000", "-e", "DISPLAY=:1",
                                   args.container, "python3", "-"], input=script))
    reference = acceptance["results"]["homeReplay"]["observations"][0]["observed"]
    differences = [key for key in reference if reference[key] != observed.get(key)]
    evidence = {
        "schemaVersion": "browser-platform/camoufox-gui-acceptance/v1",
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if not differences else "fail",
        "containerId": container["Id"], "applicationId": config.get("Labels", {}).get("browser-platform.application"),
        "artifactSHA256": artifact_sha, "acceptanceSHA256": report_sha,
        "runtimeImageDigest": artifact["runtimeImageDigest"], "network": network,
        "networkChecks": network_proof,
        "normalEntrypoint": "pass", "artifactAndReportReadOnly": True,
        "homeSeparateFromPersonalAndWork": True, "startupPage": "Example Domain",
        "x11Screen": {"width": 1920, "height": 1080}, "resources": {"memoryMiB": 1536, "cpuQuota": 1.5},
        "observed": observed, "differences": differences,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encode(evidence))
    if differences:
        raise SystemExit("desktop differs from frozen replay: " + ", ".join(differences))
    print("normal_entrypoint_x11_gui=pass")


if __name__ == "__main__":
    main()
