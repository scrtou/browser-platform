#!/usr/bin/env python3
"""Recreate only the isolated QA controller and verify live generation recovery."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--build", required=True, type=Path)
    args = parser.parse_args()
    qa, build = args.root.resolve(), args.build.resolve()
    assert qa.name == "qa" and build.parent == qa.parent
    project = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location("checks", project / "infra/sealskin/lifecycle/check-network-live.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    checks = mod.Checks(qa)
    release = json.loads((build / "release.json").read_text())
    old = json.loads(mod.docker("inspect", mod.SERVER).stdout)[0]
    assert old["Config"]["Labels"][mod.PREFIX + "qa"] == "network-20260913"
    assert old["HostConfig"]["NetworkMode"] == "browser-platform-network-qa"
    assert any(m["Source"] == str(qa / "config") and m["Destination"] == "/config" for m in old["Mounts"])
    scope = hashlib.sha256(str(qa / "config/.config/sealskin/sessions.yml").encode()).hexdigest()
    identifiers = mod.docker("ps", "-aq", "--no-trunc", "--filter", "label=" + mod.PREFIX + "scope=" + scope).stdout.split()
    assert identifiers, "Requires live QA resources to test controller recovery"
    before = {identifier: checks.identity(identifier) for identifier in identifiers}
    journals = list((qa / "config/.config/sealskin/profile-network-runtime").glob("*.json"))
    live = [json.loads(path.read_text()) for path in journals]
    live = [value for value in live if value.get("phase") == "running"]
    assert live and all(value["identity"]["owner"] == "network-qa" for value in live)
    allocations = {value["identity"]["home_hash"]: value["allocation"] for value in live}
    firefox = None
    worker_path = qa / "browser-worker.json"
    if worker_path.exists():
        worker = json.loads(worker_path.read_text())["instance_id"]
        script = """import json
from pathlib import Path
out=[]
for p in Path('/proc').glob('[0-9]*'):
 try:
  args=p.joinpath('cmdline').read_bytes().split(b'\\0')
  if ((b'--remote-debugging-port' in args and b'9228' in args) or
      (args[0].endswith(b'/camoufox') and b'--profile' in args)):
   out.append([int(p.name),p.joinpath('stat').read_text().split()[21]])
 except (OSError,IndexError):pass
assert len(out)==1
print(json.dumps(out))
"""
        firefox = mod.docker("exec", worker, "python3", "-c", script).stdout
    direct = any(value.get("policy", {}).get("mode") == "direct" for value in live)
    direct_mounts = []
    if direct or any(m.get("Destination") == "/run/browser-platform-host/ipv4-fib-trie" for m in old["Mounts"]):
        source, destination = "/proc/1/net/fib_trie", "/run/browser-platform-host/ipv4-fib-trie"
        assert any(m.get("Source") == source and m.get("Destination") == destination and m.get("RW") is False
                   for m in old["Mounts"]), "DIRECT recovery requires the fixed read-only host evidence mount"
        direct_mounts = ["--mount", "type=bind,src=" + source + ",dst=" + destination + ",readonly"]
    mod.docker("stop", "-t", "10", mod.SERVER)
    mod.docker("rm", mod.SERVER)
    mod.docker(
        "run", "-d", "--name", mod.SERVER, "--label", mod.PREFIX + "qa=network-20260913",
        "--network", "browser-platform-network-qa", "--memory", "512m", "--cpus", "1.5", "--pids-limit", "256",
        "-e", "PUID=1000", "-e", "PGID=1000", "-e", "TZ=Etc/UTC", "-e", "HOST_URL=network.invalid",
        "-v", str(qa / "config") + ":/config", "-v", str(qa / "storage") + ":/storage",
        "-v", "/tmp/browser-platform-network-qa-docker.sock:/var/run/docker.sock",
        "-p", "127.0.0.1:28110:8000", *direct_mounts, release["image"],
    )
    mod.wait(lambda: mod.request("POST", "/api/handshake/initiate")[0] == 200, "recreated QA controller")
    current = json.loads(mod.docker("inspect", mod.SERVER).stdout)[0]
    assert current["Id"] != old["Id"]
    assert before == {identifier: checks.identity(identifier) for identifier in identifiers}
    if firefox:
        assert firefox == mod.docker("exec", worker, "python3", "-c", script).stdout
    for path in journals:
        value = json.loads(path.read_text())
        key = value["identity"]["home_hash"]
        if key not in allocations:
            continue
        allocation = value["allocation"]
        assert allocation == allocations[key] and value["controller_id"] == current["Id"]
        assert current["NetworkSettings"]["Networks"][allocation["internal_name"]]["IPAddress"] == allocation["controller_ip"]
        source = "import socket; s=socket.create_connection((" + repr(allocation["guard_ip"]) + ",3000),timeout=3);s.close()"
        mod.docker("exec", mod.SERVER, "python3", "-c", source)
    images = json.loads((qa / "images.json").read_text())
    images.update(controller=release["image"], build=build.name)
    mod.write_json(qa / "images.json", images)
    report = {"result": "PASS", "controller_recreated": True, "live_generations": len(live),
              "workers_and_network_containers_preserved": True, "firefox_process_preserved": bool(firefox),
              "display_reconnected_at_original_address": True, "direct_host_evidence_preserved": bool(direct_mounts),
              "release": release["release"]}
    mod.write_json(qa.parent / "controller-recreation-results.json", report)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
