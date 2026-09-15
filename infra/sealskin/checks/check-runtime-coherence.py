#!/usr/bin/env python3
"""Explicit QA-only setup and observations for the runtime coherence matrix.

All Session responses and detailed reports go to private, new output files.
Uses the normal encrypted lifecycle API; never replaces a live application's
policy, frozen artifact, production Home or running Worker.
"""

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

spec = importlib.util.spec_from_file_location("coherence_network_checks", Path(__file__).resolve().parent.parent / "lifecycle/check-network-live.py")
network = importlib.util.module_from_spec(spec)
spec.loader.exec_module(network)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Checks:
    def __init__(self, qa):
        self.qa = qa.resolve()
        require(self.qa.name == "qa", "Explicit QA root required")
        self.controller = json.loads(network.docker("inspect", network.SERVER).stdout)[0]
        require(self.controller["Config"]["Labels"].get(network.PREFIX + "qa") == "network-20260913" and
                any(m["Source"] == str(self.qa / "config") and m["Destination"] == "/config" for m in self.controller["Mounts"]),
                "Controller does not belong to this QA root")
        self.scope = hashlib.sha256(str(self.qa / "config/.config/sealskin/sessions.yml").encode()).hexdigest()
        self.client = network.SecureClient(self.qa)
        admin = json.loads((self.qa / "admin.json").read_text())
        self.admin = network.SecureClient(self.qa, username=admin["username"], private=admin["private_key"].encode(),
                                          public=admin["server_public_key"].encode())
        self.state_path = self.qa / "coherence-state.json"
        self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {"version":1,"cases":{}}

    def save(self):
        network.write_json(self.state_path, self.state)

    def snapshot(self, name):
        entry = self.state["cases"][name]
        home = entry["request"]["home_name"]
        require(home.startswith("coherence-qa-"), "QA Home required")
        status, result = self.client.call("GET", "/api/profile-runtime/" + home)
        require(status == 200, "QA inventory unavailable")
        for worker in result["workers"]:
            require(worker["owned"] and worker["profile_id"] == entry["request"]["profile_id"] and
                    worker["operation_id"] == entry["request"]["operation_id"], "QA inventory contains another generation")
        return result

    def journal(self, name):
        request = self.state["cases"][name]["request"]
        values = [json.loads(p.read_text()) for p in (self.qa / "config/.config/sealskin/profile-network-runtime").glob("*.json")]
        matches = [v for v in values if v["identity"]["operation"] == request["operation_id"]]
        require(len(matches) == 1 and matches[0]["identity"]["owner"] == "network-qa", "QA journal mismatch")
        return matches[0]

    def setup(self, args):
        name = args.case
        require(name not in self.state["cases"] and all((args.bundle,args.template,args.geoip,args.nss)), "New case and all setup inputs required")
        endpoint = json.loads((args.bundle / "before/config.json").read_text())
        template = json.loads(args.template.read_text())
        require(template["users"] == ["network-qa"], "Only a validated QA application template is allowed")
        home, profile, app = "coherence-qa-"+name, "coherence-"+name, "camoufox-coherence-"+name
        status, result = self.client.call("POST", "/api/homedirs", {"home_name":home})
        require(status == 201, "A new QA Home is required")
        config = self.qa / "config/.config/sealskin"
        assets = config / "coherence-assets"
        assets.mkdir(mode=0o700, exist_ok=True)
        provider = copy.deepcopy(template["provider_config"])
        def asset(source):
            raw = source.read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            path = assets / (sha + source.suffix)
            if path.exists(): require(path.read_bytes() == raw, "Immutable QA asset changed")
            else: path.write_bytes(raw); path.chmod(0o600)
            return path, "/config/.config/sealskin/coherence-assets/"+path.name, sha
        refs = {}
        for mount in provider["docker_overrides"]["mounts"]:
            key = {"/run/browser-platform/environment.json":"artifact","/run/browser-platform/acceptance.json":"acceptance"}.get(mount["Target"])
            if key:
                path, ref, sha = asset(Path(mount["Source"]))
                mount["Source"] = str(path)
                refs[key+"_file"], refs[key+"_sha256"] = ref, sha
                if key == "artifact": artifact = json.loads(path.read_text())
        _, geo_file, geo_sha = asset(args.geoip)
        nss_profile = self.qa / "storage/network-qa" / home / ".camoufox/profile"
        nss_profile.mkdir(mode=0o700,parents=True,exist_ok=False)
        nss=args.nss.resolve()
        command=["/lib64/ld-linux-x86-64.so.2","--library-path",str(nss/"lib/x86_64-linux-gnu"),str(nss/"bin/certutil")]
        for options in (["-N","--empty-password","-d","sql:"+str(nss_profile)],
                        ["-A","-d","sql:"+str(nss_profile),"-n","Coherence QA CA","-t","C,,","-i",str(args.bundle/"before/ca.pem")]):
            require(subprocess.run(command+options,capture_output=True).returncode==0,"QA CA import failed")
        credentials=json.loads((args.bundle/"before/credentials.json").read_text())
        secret_refs={}
        for key,raw in {"probe_ca":(args.bundle/"before/ca.pem").read_bytes(),"username":credentials["username"].encode(),"password":credentials["password"].encode()}.items():
            path=config/"network-secrets"/("coherence-"+name+"-"+key)
            require(not path.exists(),"Refusing secret replacement")
            path.write_bytes(raw);path.chmod(0o600)
            secret_refs[key+"_file"]="/config/.config/sealskin/network-secrets/"+path.name
            secret_refs[key+"_sha256"]=hashlib.sha256(raw).hexdigest()
        images=json.loads((self.qa/"images.json").read_text())
        countries=args.country or [{"direct":"US","jp":"JP","hk":"HK"}[args.exit]]
        policy={"username":"network-qa","profile_id":profile,"home_name":home,"application_id":app,"relay_image":images["relay"],"probe_image":images["probe"],
                "mode":"direct" if args.exit=="direct" else "proxy_required","upstream_host":"","upstream_port":0,
                "probe_url":f"https://{endpoint['coherence_domain']}:{endpoint['ports']['https']}/health","probe_timeout_seconds":10,
                "probe_ca_file":secret_refs["probe_ca_file"],"probe_ca_sha256":secret_refs["probe_ca_sha256"],
                "coherence":{"mode":args.mode,"allowed_countries":countries,"allowed_timezones":args.allowed_timezone or [],"on_exit_change":args.on_exit_change,
                  "observer_domain":endpoint["coherence_domain"],"observer_port":endpoint["ports"]["https"],"observer_ipv4":endpoint["peer_ipv4"],**refs,
                  "geoip_file":geo_file,"geoip_sha256":geo_sha,"geoip_source":"https://download.db-ip.com/free/dbip-country-lite-2026-09.csv.gz",
                  "geoip_version":"DB-IP Lite Country 2026-09","geoip_published_at":"2026-09-01T06:26:58Z","geoip_max_age_days":62}}
        if args.exit=="direct":policy.update(approved_resolver_id="cloudflare-r5c3",approved_resolver_ip="1.1.1.1")
        else:policy.update(upstream_host=endpoint["peer_ipv4"][0 if args.exit=="jp" else 1],upstream_port=endpoint["ports"]["socks5"],
                           upstream_protocol="socks5",upstream_auth="username_password",**secret_refs)
        source="from app.network_runtime import NetworkPolicy;import json;print(json.dumps(NetworkPolicy.model_validate(json.loads("+repr(json.dumps(policy))+")).model_dump()))"
        policy=json.loads(network.docker("exec","-w","/app",network.SERVER,"python3","-c",source).stdout)
        registry_path=config/"profile-network-policies.json";registry=json.loads(registry_path.read_text())
        policy_id="coherence-"+name+"-r1";require(policy_id not in registry["policies"],"Policy already exists")
        registry["policies"][policy_id]=policy;network.write_json(registry_path,registry)
        template.update(id=app,source_app_id=app,name="Coherence QA "+name)
        provider.update(network_policy_id=policy_id,network_policy_sha256=digest(policy));template["provider_config"]=provider
        allowed=json.loads((self.qa/"allow.json").read_text())
        allowed["images"]=sorted(set(allowed["images"]+[provider["image"]]))
        allowed["readonly_sources"]=sorted(set(allowed["readonly_sources"]+[m["Source"] for m in provider["docker_overrides"]["mounts"]]))
        allowed["coherence_guard_images"]=[images["relay"]]
        observer=self.qa.parent/"build/payload/app/browser_observe.py"
        allowed["coherence_observer_sha256"]=[hashlib.sha256(observer.read_bytes()).hexdigest()]
        network.write_json(self.qa/"allow.json",allowed)
        status,_=self.admin.call("POST","/api/admin/apps/installed",template);require(status==201,"Application registration failed")
        request={"url":policy["probe_url"],"application_id":app,"home_name":home,"profile_id":profile,"operation_id":uuid.uuid4().hex,
                 "network_policy_id":policy_id,"network_policy_sha256":digest(policy),"language":artifact["spec"]["locale"].replace("-","_")+".UTF-8",
                 "timezone":artifact["spec"]["timezone"],"wayland_mode":False,"launch_in_room_mode":False}
        self.state["cases"][name]={"request":request,"policy":policy,"app":template};self.save()
        return {"result":"PREPARED","case":name,"exit":args.exit,"policy_sha256":digest(policy)}

    def run(self, args):
        if args.action=="setup":return self.setup(args)
        output=args.output.resolve();output.mkdir(mode=0o700,parents=True,exist_ok=False)
        entry=self.state["cases"][args.case];request=entry["request"]
        before=self.snapshot(args.case);network.write_json(output/"before.json",before)
        if args.action=="start":
            require(not any(before[key] for key in ("records","workers","resources")),"QA Home is already occupied")
            status,result=self.client.call("POST","/api/launch/url",request)
        elif args.action=="health":status,result=self.client.call("GET","/api/profile-runtime/"+request["home_name"]+"/health?upstream=true")
        else:
            require(len(before["records"])==1 or args.action=="stop" and not before["records"],"An exact QA Session is required")
            stop={key:request[key] for key in ("profile_id","operation_id","application_id","network_policy_id","network_policy_sha256")}
            stop.update(session_id=before["records"][0]["session_id"] if before["records"] else "",bootstrap_url=request["url"])
            action="coherence/"+args.action if args.action in {"access","probe"} else args.action
            status,result=self.client.call("POST","/api/profile-runtime/"+request["home_name"]+"/"+action,stop)
        network.write_json(output/"response.json",{"status":status,"result":result,"at":time.time()})
        after=self.snapshot(args.case);network.write_json(output/"after.json",after)
        if after["resources"]:network.write_json(output/"journal.json",self.journal(args.case))
        if args.action=="stop":require(status==204 and not any(after[key] for key in ("records","workers","resources")),"QA stop not confirmed")
        summary={"case":args.case,"action":args.action,"status":status,"records":len(after["records"]),"workers":len(after["workers"])}
        if isinstance(result,dict):
            report=result.get("report") or result.get("coherence")
            if report:summary.update(overall=report["overall"],allowed=report["allowed"],code=report["code"],
                                     failed=[row["code"] for row in report["checks"] if row["required"] and row["status"]!="pass"])
        network.write_json(output/"summary.json",summary)
        return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("setup","start","access","probe","health","resume","stop"))
    parser.add_argument("--root",required=True,type=Path);parser.add_argument("--case",required=True)
    parser.add_argument("--output",type=Path)
    for name in ("bundle","template","geoip","nss"):parser.add_argument("--"+name,type=Path)
    parser.add_argument("--exit",choices=("direct","jp","hk"),default="direct")
    parser.add_argument("--mode",choices=("strict","advisory"),default="strict")
    parser.add_argument("--country",action="append");parser.add_argument("--allowed-timezone",action="append")
    parser.add_argument("--on-exit-change",choices=("recheck","block"),default="recheck")
    args=parser.parse_args();require(bool(re.fullmatch(r"[a-z0-9-]{1,32}",args.case)),"Invalid QA case")
    require(args.action=="setup" or args.output is not None,"New output directory required")
    os.umask(0o077)
    print(json.dumps(Checks(args.root).run(args)),flush=True)


if __name__=="__main__":main()
