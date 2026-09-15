"""Only the pinned observation programs may execute in owned QA containers."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location("qa_coherence_proxy", Path(__file__).with_name("qa-network-docker-proxy.py"))
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


@pytest.fixture
def handler(tmp_path):
    h = object.__new__(proxy.Handler)
    source = "fixed synthetic observer source"
    allowed = tmp_path / "allow.json"
    allowed.write_text(json.dumps({"coherence_guard_images":["sha256:"+"a"*64],
                                   "coherence_observer_sha256":[hashlib.sha256(source.encode()).hexdigest()]}))
    h.server=SimpleNamespace(allow=allowed)
    values={"worker":{"Image":"qa-worker","Config":{"Env":["MOZ_MARIONETTE=1"],"Labels":{proxy.PREFIX+"role":"worker"}}},
            "guard":{"Image":"sha256:"+"a"*64,"Config":{"Labels":{proxy.PREFIX+"role":"guard"}}}}
    h.owned=lambda instance:instance in values
    h.inspect=lambda category,instance:values.get(instance)
    return h,source,values


@pytest.mark.parametrize("mutation",["source","interpreter","user","owner","flag","length","role"])
def test_worker_exec_cannot_escape_pinned_script(handler,mutation):
    h,source,values=handler
    command=["python3","-c",source,"{}"]
    assert h.coherence_command("worker",command,"abc")
    user,instance="abc","worker"
    if mutation=="source":command[2]+="\nimport os"
    elif mutation=="interpreter":command[0]="bash"
    elif mutation=="user":user="0"
    elif mutation=="owner":instance="production"
    elif mutation=="flag":values["worker"]["Config"]["Env"]=[]
    elif mutation=="length":command[3]="x"*32769
    else:values["worker"]["Config"]["Labels"][proxy.PREFIX+"role"]="probe"
    assert not h.coherence_command(instance,command,user)


@pytest.mark.parametrize("mutation",["path","action","nonce","image","user"])
def test_nft_inspection_requires_exact_image_and_read_only_command(handler,mutation):
    h,_,values=handler;command=[*proxy.INSPECT_COMMAND,"a"*32]
    assert h.coherence_command("guard",command,"0")
    user="0"
    if mutation=="path":command[4]="/tmp/other.json"
    elif mutation=="action":command[5]="--relay-config"
    elif mutation=="nonce":command[-1]="../file"
    elif mutation=="image":values["guard"]["Image"]="other-image"
    else:user="abc"
    assert not h.coherence_command("guard",command,user)


@pytest.mark.parametrize("field",["OpenStdin","OpenStdout","OpenStderr","tty","privileged","user","ContainerID"])
def test_exec_start_rechecks_identity_and_detached_mode(handler,monkeypatch,field):
    h,source,_=handler
    value={"ContainerID":"worker","ProcessConfig":{"entrypoint":"python3","arguments":["-c",source,"{}"],"user":"abc","tty":False,"privileged":False},
           "OpenStdin":False,"OpenStdout":False,"OpenStderr":False}
    monkeypatch.setattr(proxy.base,"upstream",lambda *args:(200,{},json.dumps(value).encode()))
    assert h.coherence_exec("a"*64)
    if field in value:value[field]="production" if field=="ContainerID" else True
    else:value["ProcessConfig"][field]="0" if field=="user" else True
    assert not h.coherence_exec("a"*64)


@pytest.mark.parametrize("role", ["worker", "guard", "relay"])
@pytest.mark.parametrize("fault", [None, "generation", "role", "home", "permissions", "symlink", "readonly", "target", "missing"])
def test_result_bind_is_private_and_matches_the_exact_role_and_generation(tmp_path, role, fault):
    labels = {proxy.PREFIX + "home_hash": "a" * 64, proxy.PREFIX + "operation": "b" * 32,
              proxy.PREFIX + "role": role}
    path = tmp_path / "config/.config/sealskin/profile-network-runtime" / ("a" * 64 + "-" + "b" * 32) / "observations" / role
    path.mkdir(parents=True, mode=0o700)
    target, readonly = proxy.OBSERVATION_TARGET, False
    if fault == "generation": labels[proxy.PREFIX + "operation"] = "c" * 32
    elif fault == "role": labels[proxy.PREFIX + "role"] = "guard" if role != "guard" else "worker"
    elif fault == "home": labels[proxy.PREFIX + "home_hash"] = "d" * 64
    elif fault == "permissions": path.chmod(0o755)
    elif fault == "symlink":
        other = tmp_path / "other"
        path.rename(other)
        path.symlink_to(other, target_is_directory=True)
    elif fault == "readonly": readonly = True
    elif fault == "target": target = "/run/arbitrary"
    elif fault == "missing": path = None
    assert proxy.observation_bind_allowed(tmp_path, labels, path, target, readonly) is (fault is None)
