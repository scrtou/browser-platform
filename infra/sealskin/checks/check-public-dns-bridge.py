#!/usr/bin/env python3
"""Verify QA bridge direction and MAC changes on an isolated Docker network.

Synthetic empty UDP frames stay on a new internal bridge. No public address,
existing QA network, browser, Home or production interface is used.
"""

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time
import uuid


def docker(*args, check=True):
    return subprocess.run(["sg", "docker", "-c", shlex.join(["docker", *args])],
                          capture_output=True, text=True, check=check)


def require(value, message):
    if not value:
        raise ValueError(message)


SEND = r'''
import json,socket,struct,time
c=CONFIG
def checksum(raw):
 if len(raw)%2:raw+=b'\0'
 n=sum(struct.unpack('!%dH'%(len(raw)//2),raw))
 while n>>16:n=(n&65535)+(n>>16)
 return (~n)&65535
def packet(family,mac):
 if family==4:
  udp=struct.pack('!HHHH',54322,54321,8,0)
  ip=struct.pack('!BBHHHBBH4s4s',69,0,28,1984,0,64,17,0,socket.inet_aton(c['source']),socket.inet_aton(c['gateway']))
  ip=ip[:10]+struct.pack('!H',checksum(ip))+ip[12:]
  return bytes.fromhex(c['gateway_mac'].replace(':','')+mac.replace(':',''))+b'\x08\x00'+ip+udp
 source=socket.inet_pton(socket.AF_INET6,'fe80::1234');destination=socket.inet_pton(socket.AF_INET6,'ff02::1')
 udp=struct.pack('!HHHH',54322,54321,8,0)
 total=checksum(source+destination+struct.pack('!I3xB',8,17)+udp)
 udp=udp[:6]+struct.pack('!H',total or 65535)
 ip=struct.pack('!IHBB16s16s',6<<28,8,17,64,source,destination)
 return bytes.fromhex('333300000001'+mac.replace(':',''))+b'\x86\xdd'+ip+udp
with socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(3)) as s:
 s.bind((c['interface'],0))
 for family,mac in c['frames']:
  s.send(packet(family,mac));time.sleep(.1)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", args.image), "Immutable probe image ID required")
    os.umask(0o077)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    run = uuid.uuid4().hex[:12]
    names = ["r5c2-wire-" + run + suffix for suffix in ("-sender", "-capture", "-host")]
    net_name, net_id = "r5c2-wire-" + run, None
    labels = ["--label", "io.browser-platform.qa=r5c2-wire-check", "--label", "io.browser-platform.run=" + run]
    caps = ["--cap-drop", "ALL", "--cap-add", "NET_RAW", "--read-only", "--security-opt", "no-new-privileges:true",
            "--memory", "64m", "--pids-limit", "16"]
    result, cleanup = {"result": "FAIL"}, []
    try:
        net_id = docker("network", "create", "--internal", *labels, net_name).stdout.strip()
        sender = docker("run", "-d", "--name", names[0], *labels, "--network", net_id, *caps,
                        "--entrypoint", "python3", args.image, "-c", "import time;time.sleep(60)").stdout.strip()
        net = json.loads(docker("network", "inspect", net_id).stdout)[0]
        require(net["Internal"] and set(net["Containers"]) == {sender}, "Fresh isolated sender network required")
        endpoint = net["Containers"][sender]
        address, mac = endpoint["IPv4Address"].split("/")[0], endpoint["MacAddress"].lower()
        interface = "br-" + net_id[:12]
        gateway = net["IPAM"]["Config"][0]["Gateway"]
        gateway_mac = Path("/sys/class/net", interface, "address").read_text().strip()
        script = Path(__file__).with_name("public-dns-bridge-wire.py").resolve()
        capture = docker("run", "-d", "--name", names[1], *labels, "--network", "host", *caps,
                         "-v", str(script) + ":/run/wire.py:ro", "--entrypoint", "python3", args.image, "/run/wire.py",
                         "--interface", interface, "--relay-ip", address, "--relay-mac", mac, "--seconds", "45").stdout.strip()
        deadline = time.monotonic() + 10
        while '"bridge_capture_ready": true' not in docker("logs", capture).stdout:
            require(time.monotonic() < deadline, "Isolated capture did not become ready")
            time.sleep(.1)
        changed = "02:00:00:aa:bb:cc"
        config = {"source": address, "gateway": gateway, "gateway_mac": gateway_mac, "interface": "eth0",
                  "frames": [[family, source] for family in (4, 6) for source in (mac, changed)]}
        docker("exec", sender, "python3", "-c", SEND.replace("CONFIG", repr(config)))
        host = {**config, "interface": interface, "frames": [[6, gateway_mac]]}
        docker("run", "--name", names[2], *labels, "--network", "host", *caps, "--entrypoint", "python3", args.image,
               "-c", SEND.replace("CONFIG", repr(host)))
        time.sleep(.3)
        docker("stop", "-t", "3", capture)
        raw = docker("logs", capture).stdout
        (args.output / "wire.jsonl").write_text(raw)
        summary = next(json.loads(line) for line in raw.splitlines() if json.loads(line).get("bridge_capture_complete"))
        expected = {(family, source.replace(":", "")) for family in (4, 6) for source in (mac, changed)}
        observed = {(row["family"], row["source_mac_hex"]) for row in summary["flows"]}
        require(expected <= observed, "An IPv4 or IPv6 frame was lost after a source MAC change")
        require(all(row["packet_type"] != 4 for row in summary["flows"]), "Host emission misclassified as Relay ingress")
        require(summary["hostEmitted"]["ipv6"] >= 1 and (6, gateway_mac.replace(":", "")) not in observed,
                "Host IPv6 multicast direction was not distinguished")
        result = {"result": "PASS", "checks": ["IPv4 before/after MAC change", "IPv6 before/after MAC change",
                  "Kernel ingress direction", "Host IPv6 multicast separated"], "network": net,
                  "image": args.image, "observed_flows": len(summary["flows"])}
    except Exception as exc:
        result.update(error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        removed_volumes = []
        for name in reversed(names):
            probe = docker("inspect", name, check=False)
            if probe.returncode:
                continue
            value = json.loads(probe.stdout)[0]
            require(value["Config"]["Labels"].get("io.browser-platform.run") == run, "Refusing foreign cleanup")
            (args.output / (name + "-container.json")).write_text(json.dumps(value, indent=2) + "\n")
            volumes = [mount["Name"] for mount in value["Mounts"] if mount["Type"] == "volume"]
            if value["State"]["Running"]:
                docker("stop", "-t", "2", value["Id"])
            docker("rm", "-v", value["Id"])
            for volume in volumes:
                require(docker("volume", "inspect", volume, check=False).returncode != 0,
                        "Owned test volume survived container cleanup")
            removed_volumes.extend(volumes)
            cleanup.append(value["Id"])
        if net_id:
            value = json.loads(docker("network", "inspect", net_id).stdout)[0]
            require(value["Labels"].get("io.browser-platform.run") == run and not value["Containers"], "Network cleanup scope mismatch")
            docker("network", "rm", net_id)
        result["cleanup"] = {"containers_removed": cleanup, "network_removed": net_id,
                             "anonymous_volumes_removed": removed_volumes}
        (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"result": result["result"], "checks": len(result["checks"]), "cleanup": "PASS"}))


if __name__ == "__main__":
    main()
