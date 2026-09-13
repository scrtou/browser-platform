#!/usr/bin/env python3
"""Test daemon restart inside a disposable Docker-in-Docker namespace.

The outer container has no external network and no host Docker socket. Its
privileged initializer operates only on its own network and cgroup namespaces.
This verifies namespace recovery, not VPS reboot or public Internet leakage.
"""

import argparse
import importlib.util
import json
import shutil
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--daemon-image", required=True)
    args = parser.parse_args()
    qa = args.root.resolve()
    assert qa.name == "qa" and "@sha256:" in args.daemon_image
    project = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location("checks", project / "infra/sealskin/lifecycle/check-network-live.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    root = qa.parent / "nested"
    root.mkdir(mode=0o700, exist_ok=True)
    outer = "network-qa-dind"
    label = "io.browser-platform.qa=network-20260913"
    image = json.loads((qa.parent / "guard-image-final.json").read_text())["image"]

    def inner(*command, check=True):
        return mod.docker("exec", outer, "docker", "--host=unix:///var/run/docker.sock", *command, check=check)

    def start_daemon(live):
        command = "exec /usr/local/bin/dind dockerd --host=unix:///var/run/docker.sock --pidfile=/run/qa-dockerd.pid --data-root=/var/lib/docker --exec-root=/run/qa-docker --storage-driver=vfs --ip6tables=false"
        if live:
            command += " --live-restore"
        mod.docker("exec", "-d", outer, "/bin/sh", "-c", command + " >> /qa/daemon.log 2>&1")
        mod.wait(lambda: inner("info", check=False).returncode == 0, "private Docker daemon")

    def stop_daemon():
        mod.docker("exec", outer, "pkill", "-TERM", "-x", "dockerd")
        mod.wait(lambda: mod.docker("exec", outer, "pgrep", "-x", "dockerd", check=False).returncode != 0, "private Docker daemon exit")

    def identity():
        values = json.loads(inner("inspect", "worker", "guard", "relay", "controller", "upstream").stdout)
        return {value["Name"]: {"id": value["Id"], "pid": value["State"]["Pid"], "started": value["State"]["StartedAt"]} for value in values}

    def probe():
        value = inner("exec", "worker", "python3", "/qa/probe.py", "172.31.96.2", "https://probe.qa.invalid/", "4", "/qa/probe-ca.pem")
        assert all(json.loads(value.stdout).values())

    def observations():
        return [json.loads(line) for line in (root / "worker-events.jsonl").read_text().splitlines()]

    present = mod.docker("inspect", outer, check=False)
    if present.returncode:
        mod.docker("run", "-d", "--name", outer, "--label", label, "--privileged", "--cgroupns=private", "--network", "none",
                   "--memory", "768m", "--cpus", "1.5", "--pids-limit", "512", "-e", "DOCKER_TLS_CERTDIR=",
                   "-v", str(root) + ":/qa", "--entrypoint", "/bin/sh", args.daemon_image, "-c", "exec sleep infinity")
        start_daemon(True)
    value = json.loads(mod.docker("inspect", outer).stdout)[0]
    assert value["Config"]["Labels"].get("io.browser-platform.qa") == "network-20260913"
    assert value["HostConfig"]["NetworkMode"] == "none" and value["HostConfig"]["CgroupnsMode"] == "private"
    assert any(m["Source"] == str(root) and m["Destination"] == "/qa" for m in value["Mounts"])
    assert not any(m["Destination"] == "/var/run/docker.sock" for m in value["Mounts"])
    try:
        assert inner("ps", "-aq").stdout.strip() == "", "Requires an empty private daemon"
        assert inner("info", "--format", "{{.LiveRestoreEnabled}}").stdout.strip() == "true"
        mod.docker("image", "save", "-o", str(root / "guard-image.tar"), image)
        inner("load", "-i", "/qa/guard-image.tar")
        upstream = root / "upstream/qa"
        upstream.mkdir(parents=True, mode=0o700)
        for name in ("mock-server.pem", "mock-server-key.pem", "upstream-mode.json"):
            shutil.copy2(qa / name, upstream / name)
        shutil.copy2(qa / "config/.config/sealskin/network-secrets/probe-ca.pem", root / "probe-ca.pem")
        shutil.copy2(project / "infra/sealskin/lifecycle/qa-network-upstream.py", root / "upstream.py")
        build = json.loads((qa / "images.json").read_text())["build"]
        shutil.copy2(qa.parent / build / "payload/app/network_probe.py", root / "probe.py")
        for name, content in (("username", "network-qa-user"), ("password", "network-qa-password")):
            (root / name).write_text(content)
            (root / name).chmod(0o600)
        mod.write_json(root / "worker-network.json", dict(version=1, role="worker", uid=1000, gid=1000, internal_cidr="172.31.96.0/24", relay_ip="172.31.96.2", controller_ip="172.31.96.3", display_port=3000))
        mod.write_json(root / "relay-network.json", dict(version=1, role="relay", uid=1000, gid=1000, internal_cidr="172.31.96.0/24", upstream_ip="172.31.97.3", upstream_port=28181))
        mod.write_json(root / "relay.json", dict(listen_address="0.0.0.0:1080", upstream_host="172.31.97.3", upstream_port=28181, client_cidrs=["172.31.96.0/24"], username_file="/qa/username", password_file="/qa/password", dial_timeout_seconds=4, idle_timeout_seconds=30))
        (root / "worker.py").write_text("""import json,socket,time
while True:
 out={'time':time.time()}
 for label,host,port in [('relay','172.31.96.2',1080),('controller','172.31.96.3',8000),('upstream','172.31.97.3',28181)]:
  with socket.socket() as s:
   s.settimeout(.15);out[label]=s.connect_ex((host,port))==0
 with open('/qa/worker-events.jsonl','a') as f:f.write(json.dumps(out)+'\\n')
 time.sleep(.1)
""")
        (root / "worker-events.jsonl").write_text("")
        inner("network", "create", "--internal", "--subnet", "172.31.96.0/24", "internal")
        inner("network", "create", "--subnet", "172.31.97.0/24", "egress")
        common = ["--cap-drop", "ALL", "--read-only", "--security-opt", "no-new-privileges:true", "--restart", "no", "--memory", "64m"]
        inner("run", "-d", "--name", "upstream", "--network", "egress", "--ip", "172.31.97.3", *common, "--user", "1000:1000", "-v", "/qa:/qa", "--entrypoint", "python3", image, "/qa/upstream.py", "--root", "/qa/upstream/qa", "--bind", "0.0.0.0")
        inner("run", "-d", "--name", "controller", "--network", "internal", "--ip", "172.31.96.3", *common, "--entrypoint", "python3", image, "-m", "http.server", "8000")
        caps = [value for cap in ("NET_ADMIN", "SETUID", "SETGID", "SETPCAP", "DAC_READ_SEARCH") for value in ("--cap-add", cap)]
        inner("create", "--name", "relay", "--network", "internal", "--ip", "172.31.96.2", *common, *caps, "--dns", "127.0.0.1", "-v", "/qa:/qa:ro", image, "--network-config", "/qa/relay-network.json", "--relay-config", "/qa/relay.json")
        inner("network", "connect", "egress", "relay")
        inner("start", "relay")
        inner("run", "-d", "--name", "guard", "--network", "internal", "--ip", "172.31.96.4", *common, *caps, "--dns", "127.0.0.1", "-v", "/qa:/qa:ro", image, "--network-config", "/qa/worker-network.json")
        mod.wait(lambda: "network_guard_ready" in inner("logs", "guard").stdout, "private network guard")
        inner("run", "--rm", "--network", "internal", *common, "--entrypoint", "python3", image, "-c", 'import socket;s=socket.create_connection(("172.31.96.3",8000),timeout=3);s.close()')
        inner("run", "-d", "--name", "worker", "--network", "container:guard", *common, "--user", "1000:1000", "-v", "/qa:/qa", "--entrypoint", "python3", image, "-B", "/qa/worker.py")
        probe()
        before = identity()
        boundary = len(observations())
        stop_daemon()
        time.sleep(2)
        assert len(observations()) > boundary + 2
        start_daemon(True)
        assert identity() == before
        probe()
        assert all(not value["controller"] and not value["upstream"] for value in observations())
        assert all(value["relay"] for value in observations()[boundary:])
        report = dict(result="PASS", docker_version=inner("version", "--format", "{{.Server.Version}}").stdout.strip(),
                      live_restore_preserves_processes_and_proxy=True, management_bypass_blocked_during_restart=True,
                      external_network="none", scope="isolated daemon and synthetic Worker; not VPS reboot")
        # Disable live restore, then perform a second, graceful daemon restart.
        stop_daemon()
        start_daemon(False)
        stop_daemon()
        start_daemon(False)
        values = json.loads(inner("inspect", "worker", "guard", "relay", "controller", "upstream").stdout)
        assert all(not value["State"]["Running"] and value["HostConfig"]["RestartPolicy"]["Name"] == "no" for value in values)
        report["restart_no_keeps_all_generation_processes_stopped"] = True
        inner("start", "upstream", "controller", "relay", "guard")
        mod.wait(lambda: json.loads(inner("inspect", "guard").stdout)[0]["State"]["Running"], "restarted guard")
        # Initializer completion is required before a new workload joins.
        since = json.loads(inner("inspect", "guard").stdout)[0]["State"]["StartedAt"]
        mod.wait(lambda: "network_guard_ready" in inner("logs", "--since", since, "guard").stdout, "reinitialized guard")
        inner("start", "worker")
        probe()
        assert all(not value["controller"] and not value["upstream"] for value in observations())
        report["explicit_guard_first_restart_restores_proxy_and_acl"] = True
        report["observations"] = len(observations())
        mod.write_json(qa.parent / "docker-restart-results.json", report)
        print(json.dumps(report), flush=True)
    finally:
        mod.docker("rm", "-f", "-v", outer)
        for name in ("guard-image.tar", "username", "password", "probe-ca.pem"):
            (root / name).unlink(missing_ok=True)
        if (root / "upstream").exists():
            shutil.rmtree(root / "upstream")


if __name__ == "__main__":
    main()
