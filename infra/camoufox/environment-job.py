#!/usr/bin/env python3
"""Run queued custom fingerprint jobs: isolated generation, full acceptance, catalog publication.

The Adapter only writes job requests into a private spool and reads status
files back. This runner (like acceptance.py) holds the Docker group, executes
one job at a time in the pinned Worker image with the same container limits
as the frozen-artifact acceptance, and appends an accepted entry to the
Adapter's environment catalog. A failed job keeps its evidence and is never
published.
"""

import argparse
import fcntl
import hashlib
import importlib.util
import ipaddress
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

from acceptance import docker
from environment import ArtifactError, decode, encode, validate_spec

ROOT = Path(__file__).resolve().parent
REQUEST_VERSION = 1
STATUS_VERSION = 1
CATALOG_VERSION = 1
JOB_ID = re.compile(r"^job-[a-f0-9]{16}$")
NAME = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
QA_LABEL = "io.browser-platform.qa=environment-job"
CAPABILITY_LABELS = {"io.browser-platform.browser-shutdown": "browser_shutdown_version",
                     "io.browser-platform.session-auth": "session_auth_version"}


class JobError(Exception):
    """A stable failure code for the status file; never a credential or a path."""

    def __init__(self, code, message=""):
        self.code, self.message = code, message
        super().__init__(code)


def load_prepare():
    spec = importlib.util.spec_from_file_location("prepare_sealskin", ROOT / "prepare-sealskin.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def now():
    return datetime.now(timezone.utc).isoformat()


def private_directory(path):
    path = Path(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir() or path.stat().st_mode & 0o077 or path.stat().st_uid != os.getuid():
        raise JobError("SPOOL_UNSAFE")
    return path


def write_private(path, raw):
    """0600, fsync and atomic replace; the reader only ever sees complete files."""
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=".job-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_bounded(path, limit):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise JobError("SPOOL_UNSAFE")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise JobError("ENVIRONMENT_JOB_INVALID", "request too large")
    return raw


def read_request(path):
    try:
        request = decode(read_bounded(path, 64 * 1024))
    except (ArtifactError, ValueError) as error:
        raise JobError("ENVIRONMENT_JOB_INVALID", "undecodable request") from error
    if (not isinstance(request, dict) or set(request) != {"version", "job_id", "actor", "requested_at", "spec"}
            or request["version"] != REQUEST_VERSION or not isinstance(request["job_id"], str)
            or not JOB_ID.fullmatch(request["job_id"]) or not isinstance(request["actor"], str)
            or not NAME.fullmatch(request["actor"]) or not isinstance(request["requested_at"], str)):
        raise JobError("ENVIRONMENT_JOB_INVALID", "request fields")
    spec = request["spec"]
    try:
        validate_spec(spec)
    except ArtifactError as error:
        raise JobError(str(error) if str(error) == "UNSUPPORTED_CAPABILITY" else "ENVIRONMENT_JOB_INVALID", "spec") from error
    if spec["id"] != "env-custom-" + request["job_id"][4:] or spec["revision"] != 1:
        raise JobError("ENVIRONMENT_JOB_INVALID", "spec identity")
    return request


class Spool:
    def __init__(self, root):
        self.root = private_directory(root)
        for name in ("queue", "status", "artifacts", "evidence"):
            private_directory(self.root / name)

    def queued(self):
        """Oldest request first; a request with a terminal status is finished."""
        items = []
        for path in sorted((self.root / "queue").glob("job-*.json")):
            status = self.status(path.stem)
            if status and status.get("status") in ("accepted", "failed"):
                continue
            items.append(path)
        items.sort(key=lambda path: path.stat().st_mtime)
        return items

    def status(self, job_id):
        path = self.root / "status" / (job_id + ".json")
        if not path.exists():
            return None
        try:
            return decode(read_bounded(path, 64 * 1024))
        except (ArtifactError, ValueError, JobError):
            return None

    def write_status(self, job_id, **fields):
        value = {"version": STATUS_VERSION, "job_id": job_id, "updated_at": now(), **fields}
        write_private(self.root / "status" / (job_id + ".json"), encode(value))
        return value


def available_memory_mib():
    with open("/proc/meminfo", encoding="ascii") as stream:
        for line in stream:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    raise JobError("HOST_MEMORY_UNKNOWN")


def image_capabilities(image):
    inspected = docker(["image", "inspect", image, "--format", "{{json .Config.Labels}}"], timeout=15)
    if inspected.returncode:
        raise JobError("IMAGE_UNAVAILABLE")
    labels = json.loads(inspected.stdout) or {}
    result = {}
    for label, capability in CAPABILITY_LABELS.items():
        if labels.get(label) == "1":
            result[capability] = 1
    return result


def image_id(image):
    inspected = docker(["image", "inspect", image, "--format", "{{.Id}}"], timeout=15)
    if inspected.returncode or inspected.stdout.strip() != image:
        raise JobError("IMAGE_UNAVAILABLE")
    return image


def generate_once(spec_path, home, output_dir, output_name, image):
    """One isolated generation; the artifact only appears on success."""
    command = ["run", "--rm", "--network", "none", "--read-only", "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--memory", "1536m", "--cpus", "1.5",
               "--pids-limit", "256", "--user", f"{os.getuid()}:{os.getgid()}",
               "--mount", f"type=bind,src={output_dir},dst=/output", "--mount", f"type=bind,src={home},dst=/config",
               "--mount", f"type=bind,src={spec_path},dst=/run/spec.json,readonly",
               "--entrypoint", "/opt/camoufox-python/bin/python", image,
               "/usr/local/lib/browser-platform/environment.py", "generate", "--spec", "/run/spec.json",
               "--output", "/output/" + output_name, "--image-digest", image]
    return docker(command, timeout=300)


def generate(spec, image, artifact_dir, evidence_dir, attempts=3):
    """BrowserForge honours a screen constraint only most of the time; retry a bounded number of times."""
    spec_path = evidence_dir / "spec.json"
    write_private(spec_path, encode(spec))
    home = evidence_dir / "generation-home"
    log = evidence_dir / "generation.log"
    for attempt in range(1, attempts + 1):
        if home.exists():
            shutil.rmtree(home)
        home.mkdir(mode=0o700)
        result = generate_once(spec_path, home, artifact_dir, "environment.json", image)
        with log.open("a", encoding="utf-8") as stream:
            stream.write(f"--- attempt {attempt} exit={result.returncode}\n{result.stdout}{result.stderr}\n")
        if result.returncode == 0 and (artifact_dir / "environment.json").is_file():
            return attempt
        if "ENVIRONMENT_SPEC_MISMATCH" not in result.stdout + result.stderr:
            raise JobError("ENVIRONMENT_GENERATION_FAILED", f"attempt {attempt}")
    raise JobError("ENVIRONMENT_SPEC_MISMATCH", f"{attempts} attempts")


class Fixture:
    """Disposable internal/egress networks plus the QA SOCKS5 fixture aliased as profile-relay."""

    def __init__(self, job_id, image):
        self.suffix = job_id[4:]
        self.image = image
        self.networks = {}
        self.container = None

    def __enter__(self):
        for role in ("internal", "egress"):
            args = ["network", "create", "--label", QA_LABEL]
            if role == "internal":
                args.append("--internal")
            created = docker([*args, f"bp-envjob-{self.suffix}-{role}"], timeout=30)
            if created.returncode:
                raise JobError("QA_NETWORK_UNAVAILABLE")
            self.networks[role] = created.stdout.strip()
        inspected = docker(["network", "inspect", self.networks["internal"]], timeout=15)
        subnet = json.loads(inspected.stdout)[0]["IPAM"]["Config"][0]["Subnet"]
        address = str(ipaddress.ip_network(subnet).network_address + 2)
        proxy = ROOT.parent / "sealskin" / "checks" / "qa-artifact-proxy.py"
        created = docker(["create", "--name", f"bp-envjob-{self.suffix}-proxy", "--label", QA_LABEL,
                          "--network", self.networks["internal"], "--ip", address, "--network-alias", "profile-relay",
                          "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--read-only",
                          "--memory", "64m", "--cpus", "0.3", "--pids-limit", "64",
                          "--user", f"{os.getuid()}:{os.getgid()}",
                          "--mount", f"type=bind,src={proxy},dst=/qa-artifact-proxy.py,readonly",
                          "--entrypoint", "python3", self.image, "/qa-artifact-proxy.py", "--bind", address], timeout=30)
        if created.returncode:
            raise JobError("QA_FIXTURE_UNAVAILABLE")
        self.container = created.stdout.strip()
        if docker(["network", "connect", self.networks["egress"], self.container], timeout=30).returncode or \
                docker(["start", self.container], timeout=30).returncode:
            raise JobError("QA_FIXTURE_UNAVAILABLE")
        for _ in range(40):
            if "ARTIFACT_PROXY_READY" in docker(["logs", self.container], timeout=15).stdout:
                return self
            time.sleep(0.25)
        raise JobError("QA_FIXTURE_UNAVAILABLE", "not ready")

    def __exit__(self, *_):
        if self.container:
            docker(["stop", "-t", "10", self.container], timeout=40)
            docker(["rm", "-v", "--force", self.container], timeout=30)
        for identifier in self.networks.values():
            docker(["network", "rm", identifier], timeout=30)
        return False


def run_acceptance(artifact_path, network, report_path, recreations, log_path):
    command = [sys.executable, "-u", str(ROOT / "acceptance.py"), "--artifact", str(artifact_path), "--network", network,
               "--phase", "all", "--recreations", str(recreations), "--output", str(report_path)]
    with log_path.open("wb") as log:
        completed = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=3600)
    return completed.returncode


def acceptance_summary(report_path, artifact_sha, image):
    try:
        report = decode(read_bounded(report_path, 2 * 1024 * 1024))
    except (ArtifactError, ValueError, JobError):
        raise JobError("ENVIRONMENT_ACCEPTANCE_FAILED", "unreadable report") from None
    if (report.get("schemaVersion") != "browser-platform/camoufox-acceptance/v1" or report.get("status") != "pass"
            or report.get("phase") != "all" or report.get("artifactSHA256") != artifact_sha
            or report.get("runtimeImageDigest") != image):
        raise JobError("ENVIRONMENT_ACCEPTANCE_FAILED")
    return report


def read_catalog(path):
    path = Path(path)
    if not path.exists():
        return {"version": CATALOG_VERSION, "artifacts": []}
    catalog = decode(read_bounded(path, 1 << 20))
    if (not isinstance(catalog, dict) or set(catalog) != {"version", "artifacts"} or catalog["version"] != CATALOG_VERSION
            or not isinstance(catalog["artifacts"], list)):
        raise JobError("CATALOG_INVALID")
    return catalog


def append_catalog(path, entry):
    """Append one accepted entry; an existing ID is never replaced."""
    path = Path(path)
    private_directory(path.parent)
    lock_path = path.parent / (path.name + ".lock")
    with open(lock_path, "a+b") as lock:
        os.fchmod(lock.fileno(), 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        catalog = read_catalog(path)
        if any(isinstance(item, dict) and item.get("id") == entry["id"] for item in catalog["artifacts"]):
            raise JobError("CATALOG_ID_EXISTS")
        catalog["artifacts"].append(entry)
        write_private(path, encode(catalog))


def catalog_entry(*, environment_id, artifact, artifact_sha, report_sha, image, definition, capabilities, source, job_id=""):
    spec = artifact["spec"]
    entry = {
        "id": environment_id, "sha256": artifact_sha, "acceptance_sha256": report_sha, "image": image,
        "source": source, "status": "accepted", "application": definition,
        "required_runtime_capabilities": capabilities,
        "locale": spec["locale"], "languages": spec["languages"], "timezone": spec["timezone"],
        "screen": f'{spec["screen"]["width"]}x{spec["screen"]["height"]}@{spec["screen"]["deviceScaleFactor"]}',
        "accepted_at": now(),
    }
    if job_id:
        entry["job_id"] = job_id
    return entry


def build_template(prepare, *, artifact_path, report_path, artifact, image, args, verify):
    """The catalog template is the SealSkin definition minus the policy reference and final ID."""
    env = prepare.expected_environment(artifact, hashlib.sha256(artifact_path.read_bytes()).hexdigest())
    env["BROWSER_PLATFORM_ACCEPTANCE_SHA256"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
    env.update(SELKIES_ALLOWED_ORIGINS=args.session_origin.rstrip("/"), SELKIES_UI_TITLE="Camoufox", TITLE="Camoufox")
    addon_mounts = []
    if args.clipboard_addon:
        addon_mounts, _ = prepare.clipboard_mounts(args.clipboard_addon)
        env.update(SELKIES_UI_SIDEBAR_SHOW_FILES="true", SELKIES_FILE_TRANSFERS="upload")
    return prepare.build_definition(
        app_id="app-template", artifact_path=artifact_path, report_path=report_path, artifact=artifact, env=env,
        image=image, username=args.username, store=args.store, template=args.template,
        network_overrides={}, policy_reference={}, addon_mounts=addon_mounts, verify=verify)


def process(spool, request_path, args, prepare, *, generator=generate, fixture=Fixture, accept=run_acceptance,
            capabilities=image_capabilities, memory=available_memory_mib, resolve_image=image_id):
    """Run one job end to end. Every failure leaves a status file and retained evidence."""
    job_id = request_path.stem
    try:
        request = read_request(request_path)
    except JobError as error:
        spool.write_status(job_id, status="failed", phase="validate", code=error.code, finished_at=now())
        return "failed"
    free = memory()
    if free < args.min_free_mib:
        spool.write_status(job_id, status="queued", phase="wait", code="HOST_MEMORY_LOW",
                           message=f"available {free} MiB, need {args.min_free_mib} MiB")
        return "queued"
    spec = request["spec"]
    environment_id = spec["id"]
    artifact_dir = private_directory(spool.root / "artifacts" / environment_id)
    evidence_dir = private_directory(spool.root / "evidence" / job_id)
    artifact_path, report_path = artifact_dir / "environment.json", artifact_dir / "acceptance.json"
    started = now()
    progress = {"started_at": started, "image": args.image}
    try:
        image = resolve_image(args.image)
        progress["image"] = image
        spool.write_status(job_id, status="running", phase="generate", **progress)
        attempts = generator(spec, image, artifact_dir, evidence_dir)
        raw = artifact_path.read_bytes()
        artifact = decode(raw)
        artifact_sha = hashlib.sha256(raw).hexdigest()
        progress.update(attempts=attempts, artifact_id=artifact["id"], artifact_sha256=artifact_sha)
        spool.write_status(job_id, status="running", phase="acceptance", **progress)
        with fixture(job_id, image) as active:
            code = accept(artifact_path, active.networks["internal"], report_path, args.recreations, evidence_dir / "acceptance.log")
        if code or not report_path.is_file():
            raise JobError("ENVIRONMENT_ACCEPTANCE_FAILED", f"exit {code}")
        acceptance_summary(report_path, artifact_sha, image)
        report_sha = hashlib.sha256(report_path.read_bytes()).hexdigest()
        progress["acceptance_sha256"] = report_sha
        spool.write_status(job_id, status="running", phase="publish", **progress)
        definition = build_template(prepare, artifact_path=artifact_path, report_path=report_path, artifact=artifact,
                                    image=image, args=args, verify=args.verify_in_image)
        entry = catalog_entry(environment_id=environment_id, artifact=artifact, artifact_sha=artifact_sha, report_sha=report_sha,
                              image=image, definition=definition, capabilities=capabilities(image), source="custom", job_id=job_id)
        append_catalog(args.catalog, entry)
    except JobError as error:
        spool.write_status(job_id, status="failed", phase="failed", code=error.code, message=error.message,
                           finished_at=now(), **progress)
        return "failed"
    except (OSError, ValueError, subprocess.SubprocessError, ArtifactError) as error:
        spool.write_status(job_id, status="failed", phase="failed", code="ENVIRONMENT_JOB_FAILED",
                           message=type(error).__name__, finished_at=now(), **progress)
        return "failed"
    spool.write_status(job_id, status="accepted", phase="done", finished_at=now(), environment_id=environment_id, **progress)
    return "accepted"


def run_next(spool, args, prepare, **hooks):
    """Process the oldest queued job under the spool lock; return its final state or None."""
    with open(spool.root / ".lock", "a+b") as lock:
        os.fchmod(lock.fileno(), 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return "locked"
        queued = spool.queued()
        if not queued:
            return None
        return process(spool, queued[0], args, prepare, **hooks)


def register(args, prepare):
    """Add an already accepted frozen artifact and report to the catalog."""
    artifact_path, report_path = args.artifact.resolve(strict=True), args.acceptance.resolve(strict=True)
    raw = artifact_path.read_bytes()
    artifact = decode(raw)
    validate_spec(artifact["spec"])
    artifact_sha = hashlib.sha256(raw).hexdigest()
    image = image_id(artifact["runtimeImageDigest"])
    acceptance_summary(report_path, artifact_sha, image)
    report_sha = hashlib.sha256(report_path.read_bytes()).hexdigest()
    definition = build_template(prepare, artifact_path=artifact_path, report_path=report_path, artifact=artifact,
                                image=image, args=args, verify=args.verify_in_image)
    entry = catalog_entry(environment_id=artifact["spec"]["id"], artifact=artifact, artifact_sha=artifact_sha, report_sha=report_sha,
                          image=image, definition=definition, capabilities=image_capabilities(image), source="frozen")
    append_catalog(args.catalog, entry)
    print(json.dumps({"registered": entry["id"], "sha256": artifact_sha, "acceptance_sha256": report_sha}))


def add_template_arguments(parser):
    parser.add_argument("--catalog", type=Path, required=True, help="Adapter environment_catalog file (0600)")
    parser.add_argument("--session-origin", required=True, help="trusted HTTPS origin of the SealSkin client")
    parser.add_argument("--username", default="profile-adapter")
    parser.add_argument("--clipboard-addon", type=Path)
    parser.add_argument("--store", default="SealSkin Apps")
    parser.add_argument("--template", default="Default")
    parser.add_argument("--no-verify-in-image", dest="verify_in_image", action="store_false")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="process queued jobs")
    run.add_argument("--spool", type=Path, required=True)
    run.add_argument("--image", required=True, help="complete sha256: digest of the pinned Worker image")
    run.add_argument("--recreations", type=int, default=10)
    run.add_argument("--min-free-mib", type=int, default=2048)
    run.add_argument("--watch", type=int, default=0, help="poll interval in seconds; 0 processes at most one job")
    add_template_arguments(run)
    reg = commands.add_parser("register", help="add a frozen artifact and its successful report to the catalog")
    reg.add_argument("--artifact", type=Path, required=True)
    reg.add_argument("--acceptance", type=Path, required=True)
    add_template_arguments(reg)
    args = parser.parse_args()
    os.umask(0o077)
    prepare = load_prepare()
    if args.command == "register":
        register(args, prepare)
        return
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", args.image) or not 10 <= args.recreations <= 50 or args.min_free_mib < 0:
        parser.error("image must be a complete digest; recreations 10-50")
    spool = Spool(args.spool)
    while True:
        result = run_next(spool, args, prepare)
        if result:
            print(json.dumps({"job": result, "at": now()}), flush=True)
        if not args.watch:
            return
        time.sleep(args.watch if result in (None, "queued", "locked") else 1)


if __name__ == "__main__":
    try:
        main()
    except JobError as error:
        raise SystemExit(error.code)
