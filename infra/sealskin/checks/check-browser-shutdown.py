#!/usr/bin/env python3
"""Test normal browser closure, refusal and immediate storage in isolated QA."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import http.client
import importlib.util
import json
from pathlib import Path
import socket
import time
import uuid

spec = importlib.util.spec_from_file_location("matrix", Path(__file__).with_name("check-proxy-protocols.py"))
matrix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(matrix)
network = matrix.network


def execution(identifier):
    # Read only, through the same isolated Docker proxy used by QA SealSkin.
    connection = http.client.HTTPConnection("localhost", timeout=5)
    connection.sock = socket.socket(socket.AF_UNIX)
    connection.sock.settimeout(5)
    connection.sock.connect("/tmp/browser-platform-network-qa-docker.sock")
    try:
        connection.request("GET", "/exec/" + identifier + "/json")
        response = connection.getresponse()
        assert response.status == 200
        return json.loads(response.read())
    finally:
        connection.close()


STORAGE = """async (write, marker) => {
  const db = await new Promise((resolve, reject) => {
    const req = indexedDB.open('r5a-shutdown', 1);
    req.onupgradeneeded = () => req.result.createObjectStore('values');
    req.onsuccess = () => resolve(req.result); req.onerror = () => reject(req.error);
  });
  if (write) {
    const tx = db.transaction('values', 'readwrite');
    tx.objectStore('values').put(marker, 'resume');
    await new Promise((resolve, reject) => {tx.oncomplete=resolve; tx.onerror=()=>reject(tx.error);});
    document.cookie = 'r5a_shutdown=' + marker + '; Path=/; Max-Age=86400; Secure; SameSite=Lax';
    localStorage.setItem('r5a-shutdown', marker);
  }
  const idb = await new Promise((resolve, reject) => {
    const tx=db.transaction('values', 'readonly'), req=tx.objectStore('values').get('resume');
    tx.oncomplete=()=>resolve(req.result); tx.onerror=()=>reject(tx.error);
  });
  db.close();
  return {href:location.href, localStorage:localStorage.getItem('r5a-shutdown'), indexedDB:idb,
    cookie:document.cookie.split('; ').find(v=>v.startsWith('r5a_shutdown='))?.split('=')[1]};
}"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runner = matrix.Matrix(args.root, args.output)
    first, second = runner.output / "before", runner.output / "after"
    first.mkdir(mode=0o700)
    second.mkdir(mode=0o700)
    before = runner.configure("https", "basic", first)
    worker = runner.info["instance_id"]
    details = json.loads(network.docker("inspect", worker).stdout)[0]
    assert details["Config"]["Labels"].get("io.browser-platform.browser-shutdown") == "1"
    runner.control.navigate("https://entry.leak.qa.test/test")
    assert runner.control.evaluate("window.onbeforeunload=e=>{e.preventDefault();e.returnValue='';};true")
    body = json.loads((runner.qa / "browser-stop.json").read_text())
    start, observed_exec = time.monotonic(), None
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(runner.checks.client.call, "POST", "/api/profile-runtime/" + runner.info["home"] + "/stop", body)
        while not future.done() and time.monotonic() - start < 20:
            current = json.loads(network.docker("inspect", worker).stdout)[0]
            for identifier in current.get("ExecIDs") or []:
                value = execution(identifier)
                process = value.get("ProcessConfig") or {}
                if process.get("arguments") == ["/usr/local/lib/browser-platform/browser-shutdown.py", "--timeout", "12"]:
                    assert value["ContainerID"] == worker and process["user"] == "abc"
                    observed_exec = identifier
            if observed_exec:
                break
            time.sleep(.1)
        status, result = future.result(timeout=25)
    elapsed = time.monotonic() - start
    after_refusal = runner.snapshot()
    record = {"status": status, "result": result, "elapsed": elapsed, "inventory": after_refusal}
    if observed_exec:
        record["execution"] = execution(observed_exec)
    network.write_json(runner.output / "refused.json", record)
    assert status == 503 and observed_exec and 11 <= elapsed < 25
    assert record["execution"]["Running"] is False and record["execution"]["ExitCode"] == 1
    assert after_refusal["workers"][0]["instance_id"] == worker
    assert {v["id"] for v in before["resources"]} == {v["id"] for v in after_refusal["resources"]}
    assert json.loads(network.docker("inspect", worker).stdout)[0]["State"]["Running"]
    print(json.dumps({"check": "beforeunload-refusal", "result": "PASS", "homeRetained": True}), flush=True)

    # Cancel the dialog through the real desktop, then remove the QA handler.
    runner.control.key("Escape")
    assert runner.control.evaluate("window.onbeforeunload=null;true")
    marker = uuid.uuid4().hex
    written = runner.control.evaluate("(" + STORAGE + ")(true," + json.dumps(marker) + ")")
    expected = {"href": "https://entry.leak.qa.test/test", "cookie": marker, "localStorage": marker, "indexedDB": marker}
    assert written == expected
    network.write_json(runner.output / "written.json", written)
    runner.stop()  # No delay after the page's confirmed write/read.
    runner.configure("https", "basic", second)
    assert runner.info["instance_id"] != worker
    runner.control.navigate("https://entry.leak.qa.test/test")
    recovered = runner.control.evaluate("(" + STORAGE + ")(false,null)")
    assert recovered == expected
    network.write_json(runner.output / "recovered.json", recovered)
    runner.stop()
    network.write_json(runner.output / "shutdown-results.json", {
        "result": "PASS", "beforeunloadRefusalRetainsGeneration": True,
        "retryAfterCancel": True, "immediateCookieLocalStorageIndexedDBRestored": True,
        "newWorkerSameHome": True, "verifiedStopReleasedAllResources": True,
        "workerImage": details["Image"], "controller": runner.images["controller"]})
    print(json.dumps({"check": "immediate-storage-stop-new", "result": "PASS"}), flush=True)


if __name__ == "__main__":
    main()
