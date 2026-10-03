#!/usr/bin/env python3
"""Generate once, then replay a complete, version-bound Camoufox artifact.

The verify and launch paths deliberately have no imports from Camoufox or
BrowserForge. Only the explicit generate command may invoke those libraries.
"""

from __future__ import annotations

import argparse
import configparser
import copy
from dataclasses import asdict
from datetime import datetime, timezone
import fcntl
import hashlib
import hmac
from importlib.metadata import PackageNotFoundError, version
import json
import math
import os
from pathlib import Path
import platform
import re
import shlex
import sys
import tempfile
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parent
BROWSER = Path("/opt/camoufox/browser")
EXECUTABLE = BROWSER / "camoufox"
MANIFEST = BROWSER.parent / "browser-manifest.json"
SCHEMA = "browser-platform/camoufox-environment/v1"
AUTO_SCHEMA = "browser-platform/camoufox-environment/v2"
DISPLAY_KEYS = {"screen.width","screen.height","screen.availWidth","screen.availHeight","window.outerWidth","window.outerHeight","window.devicePixelRatio","window.screenX","window.screenY"}

def automatic(spec): return spec.get("screen",{}).get("mode")=="auto"

def fixed_spec(spec):
    value=copy.deepcopy(spec)
    if automatic(value):
        require(value["screen"]=={"mode":"auto","dprMode":"system","width":1280,"height":720},"UNSUPPORTED_CAPABILITY")
        value["screen"]={"width":1280,"height":720,"deviceScaleFactor":1}
        value["requiredCapabilities"]=[{"auto-screen":"fixed-screen","system-dpr":"fixed-dpr"}.get(k,k) for k in value["requiredCapabilities"]]
    return value

CAPABILITIES = {
    "locale", "languages", "timezone", "fixed-screen", "fixed-dpr",
    "frozen-device-config", "webrtc-disabled", "proxy-only",
}
SEEDS = ("fonts:spacing_seed", "audio:seed", "canvas:seed")
EXTRA_PREFS = {
    "webgl.enable-webgl2", "webgl.force-enabled", "browser.sessionhistory.max_entries",
    "browser.sessionhistory.max_total_viewers", "browser.cache.memory.enable",
    "browser.cache.disk_cache_ssl", "browser.cache.disk.smart_size.enabled",
}
BF_FIELDS = {
    "screen", "navigator", "headers", "videoCodecs", "audioCodecs", "pluginsData",
    "battery", "videoCard", "multimediaDevices", "fonts", "mockWebRTC", "slim",
}
BF_SCREEN_FIELDS = {
    "availHeight", "availLeft", "availTop", "availWidth", "clientHeight", "clientWidth",
    "colorDepth", "devicePixelRatio", "hasHDR", "height", "innerHeight", "innerWidth",
    "outerHeight", "outerWidth", "pageXOffset", "pageYOffset", "pixelDepth", "screenX", "width",
}
BF_NAVIGATOR_FIELDS = {
    "appCodeName", "appName", "appVersion", "deviceMemory", "doNotTrack", "extraProperties",
    "hardwareConcurrency", "language", "languages", "maxTouchPoints", "oscpu", "platform",
    "product", "productSub", "userAgent", "userAgentData", "vendor", "vendorSub", "webdriver",
}
REJECTIONS = {
    "missing-artifact", "wrong-sha256", "timezone-drift", "wayland-drift", "version-mismatch",
    "missing-audio-seed", "direct-proxy", "unsupported-capability", "unvalidated-candidate",
    "baseline-randomization", "asynchronous-font-fallback",
}


class ArtifactError(ValueError):
    """Stable, non-sensitive failure code suitable for Worker logs."""


def require(condition, code="ENVIRONMENT_ARTIFACT_INVALID"):
    if not condition:
        raise ArtifactError(code)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def encode(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def decode(raw: bytes):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result)
            result[key] = value
        return result

    def invalid_constant(_):
        raise ArtifactError("ENVIRONMENT_ARTIFACT_INVALID")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ArtifactError("ENVIRONMENT_ARTIFACT_INVALID") from error


def is_hash(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def validate_spec(spec):
    require(isinstance(spec, dict))
    spec=fixed_spec(spec)
    require(set(spec) == {
        "id", "revision", "osFamily", "locale", "languages", "timezone", "screen",
        "window", "webrtcPolicy", "geolocationPolicy", "requiredCapabilities",
    })
    require(isinstance(spec["id"], str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,95}", spec["id"]))
    require(type(spec["revision"]) is int and spec["revision"] > 0)
    require(spec["osFamily"] == "linux" and spec["webrtcPolicy"] == "disabled"
            and spec["geolocationPolicy"] == "disabled", "UNSUPPORTED_CAPABILITY")
    languages = spec["languages"]
    require(isinstance(languages, list) and 1 <= len(languages) <= 10)
    require(all(isinstance(item, str) and re.fullmatch(r"[a-zA-Z]{2,8}(?:-[a-zA-Z0-9]{1,8})*", item)
                for item in languages))
    require(spec["locale"] == languages[0] and len(set(languages)) == len(languages))
    require(isinstance(spec["timezone"], str))
    try:
        ZoneInfo(spec["timezone"])
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ArtifactError("ENVIRONMENT_ARTIFACT_INVALID") from error
    screen, window = spec["screen"], spec["window"]
    require(isinstance(screen, dict) and set(screen) == {"width", "height", "deviceScaleFactor"})
    require(isinstance(window, dict) and set(window) == {"width", "height"})
    require(type(screen["width"]) is int and 640 <= screen["width"] <= 3840)
    require(type(screen["height"]) is int and 480 <= screen["height"] <= 2160)
    # This first adapter is verified on X11 at DPR 1 only.
    require(type(screen["deviceScaleFactor"]) in (int, float)
            and screen["deviceScaleFactor"] == 1, "UNSUPPORTED_CAPABILITY")
    require(type(window["width"]) is int and 640 <= window["width"] <= screen["width"])
    require(type(window["height"]) is int and 480 <= window["height"] <= screen["height"])
    requested = spec["requiredCapabilities"]
    require(isinstance(requested, list) and all(isinstance(item, str) for item in requested))
    require(set(requested) <= CAPABILITIES, "UNSUPPORTED_CAPABILITY")


def managed_preferences(spec):
    return {
        **({"layout.css.devPixelsPerPx":"-1.0"} if automatic(spec) else {}),
        "intl.locale.requested": spec["locale"],
        "intl.accept_languages": ",".join(spec["languages"]),
        "network.proxy.type": 1,
        "network.proxy.socks": "profile-relay",
        "network.proxy.socks_port": 1080,
        "network.proxy.socks_version": 5,
        "network.proxy.socks_remote_dns": True,
        "network.proxy.no_proxies_on": "",
        "network.proxy.failover_direct": False,
        "network.proxy.allow_hijacking_localhost": True,
        "network.trr.mode": 5,
        "media.peerconnection.enabled": False,
        "media.peerconnection.ice.proxy_only": True,
        "media.peerconnection.ice.no_host": True,
        "geo.enabled": False,
        "permissions.default.geo": 2,
        "xpinstall.enabled": False,
        "app.update.auto": False,
        # Firefox's independent RFP/FPP layers have their own per-session keys.
        # Keep the device environment under the frozen Camoufox configuration.
        "privacy.baselineFingerprintingProtection": False,
        "privacy.fingerprintingProtection": False,
        "privacy.fingerprintingProtection.pbmode": False,
        "privacy.resistFingerprinting": False,
        "privacy.resistFingerprinting.pbmode": False,
        # Async system-font fallback can snapshot missing CJK glyphs into a
        # canvas before fallback finishes. Use the native synchronous path.
        "gfx.font_rendering.fallback.async": False,
    }


def runtime_metadata(*, verify_files=True):
    pins = decode((ROOT / "versions.json").read_bytes())
    require(platform.machine() == pins["architecture"] and platform.python_version() == pins["pythonVersion"],
            "ENVIRONMENT_VERSION_MISMATCH")
    require(digest(ROOT / "requirements.lock") == pins["requirementsSHA256"], "ENVIRONMENT_VERSION_MISMATCH")
    for name, expected in pins["packages"].items():
        require(version(name) == expected, "ENVIRONMENT_VERSION_MISMATCH")
    manifest = decode(MANIFEST.read_bytes())
    if verify_files:
        actual_files = {str(path.relative_to(BROWSER)) for path in BROWSER.rglob("*") if path.is_file()}
        require(actual_files == set(manifest), "BROWSER_BUNDLE_MISMATCH")
        for name, expected in manifest.items():
            path = BROWSER / name
            require(not path.is_symlink() and is_hash(expected) and digest(path) == expected,
                    "BROWSER_BUNDLE_MISMATCH")
    application = configparser.ConfigParser()
    application.read(BROWSER / "application.ini")
    require(all(application["App"].get(key) == value for key, value in pins["browser"]["application"].items()),
            "ENVIRONMENT_VERSION_MISMATCH")
    return {
        "adapterVersion": pins["adapterVersion"],
        "adapterSHA256": digest(Path(__file__)),
        "pinsSHA256": digest(ROOT / "versions.json"),
        "requirementsSHA256": pins["requirementsSHA256"],
        "pythonVersion": pins["pythonVersion"],
        "packages": pins["packages"],
        "baseImageDigest": pins["baseImageDigest"],
        "browserRelease": pins["browser"]["tag"],
        "browserArchiveSHA256": pins["browser"]["sha256"],
        "browserManifestSHA256": digest(MANIFEST),
    }


def validate_properties(config):
    require(isinstance(config, dict))
    properties = {item["property"]: item["type"] for item in decode((BROWSER / "properties.json").read_bytes())}
    for key, value in config.items():
        require(key in properties, "UNSUPPORTED_CAPABILITY")
        kind = properties[key]
        valid = {
            "str": lambda: isinstance(value, str),
            "int": lambda: type(value) is int,
            "uint": lambda: type(value) is int and 0 <= value <= 4294967295,
            "double": lambda: type(value) in (int, float) and math.isfinite(value),
            "bool": lambda: type(value) is bool,
            "array": lambda: isinstance(value, list),
            "dict": lambda: isinstance(value, dict),
        }
        require(kind in valid and valid[kind](), "ENVIRONMENT_PROPERTY_INVALID")
    for key in SEEDS:
        require(type(config.get(key)) is int and 1 <= config[key] <= 4294967295,
                "ENVIRONMENT_SEED_MISSING")
    require(isinstance(config.get("fonts"), list) and len(config["fonts"]) > 0)
    require(all(isinstance(font, str) and font for font in config["fonts"]))
    require(isinstance(config.get("voices"), list) and config.get("voices:blockIfNotDefined") is True)
    for voice in config["voices"]:
        require(isinstance(voice, dict)
                and all(isinstance(voice.get(key), str) for key in ("lang", "name", "voiceUri"))
                and all(type(voice.get(key)) is bool for key in ("isDefault", "isLocalService")))
    require(isinstance(config.get("webGl:vendor"), str) and bool(config["webGl:vendor"]))
    require(isinstance(config.get("webGl:renderer"), str) and bool(config["webGl:renderer"]))
    require(config.get("addons") == [], "UNSUPPORTED_CAPABILITY")
    require(not any(key.startswith(("geolocation:", "webrtc:")) for key in config), "UNSUPPORTED_CAPABILITY")


def validate_artifact(artifact, metadata):
    require(isinstance(artifact, dict) and set(artifact) == {
        "schemaVersion", "id", "createdAt", "spec", "runtime", "runtimeImageDigest",
        "browserforgeFingerprint", "resolvedConfig", "firefoxUserPrefs",
    })
    require(artifact["schemaVersion"] == (AUTO_SCHEMA if automatic(artifact["spec"]) else SCHEMA))
    require(artifact["runtime"] == metadata, "ENVIRONMENT_VERSION_MISMATCH")
    require(isinstance(artifact["runtimeImageDigest"], str)
            and artifact["runtimeImageDigest"].startswith("sha256:")
            and is_hash(artifact["runtimeImageDigest"][7:]))
    spec = artifact["spec"]
    validate_spec(spec)
    require(artifact["id"] == spec["id"] + "-artifact-1")
    fingerprint = artifact["browserforgeFingerprint"]
    require(isinstance(fingerprint, dict) and set(fingerprint) == BF_FIELDS,
            "BROWSERFORGE_RESULT_INCOMPLETE")
    require(isinstance(fingerprint["navigator"], dict) and isinstance(fingerprint["screen"], dict),
            "BROWSERFORGE_RESULT_INCOMPLETE")
    require(BF_SCREEN_FIELDS <= set(fingerprint["screen"])
            and BF_NAVIGATOR_FIELDS == set(fingerprint["navigator"]), "BROWSERFORGE_RESULT_INCOMPLETE")
    config = artifact["resolvedConfig"]
    validate_properties(config)
    required_config = {
        "navigator.language": spec["locale"],
        "navigator.languages": spec["languages"],
        "timezone": spec["timezone"],
    }
    if automatic(spec):
        require(not DISPLAY_KEYS.intersection(config),"ENVIRONMENT_SPEC_MISMATCH")
    else:
        required_config.update({"screen.width":spec["screen"]["width"],"screen.height":spec["screen"]["height"],"window.devicePixelRatio":spec["screen"]["deviceScaleFactor"],"window.outerWidth":spec["window"]["width"],"window.outerHeight":spec["window"]["height"]})
    for key,value in required_config.items():require(config.get(key)==value,"ENVIRONMENT_SPEC_MISMATCH")
    require("Linux" in config.get("navigator.userAgent", "")
            and "Firefox/152." in config.get("navigator.userAgent", ""), "ENVIRONMENT_VERSION_MISMATCH")
    prefs = artifact["firefoxUserPrefs"]
    required = managed_preferences(spec)
    require(isinstance(prefs, dict) and set(prefs) <= set(required) | EXTRA_PREFS)
    require(all(type(value) in (str, bool, int) for value in prefs.values()))
    network_prefs = {key: value for key, value in required.items() if key.startswith(("network.", "media.peerconnection."))}
    require(all(type(prefs.get(key)) is type(value) and prefs.get(key) == value for key, value in network_prefs.items()),
            "ENVIRONMENT_PROXY_POLICY_MISMATCH")
    require(all(type(prefs.get(key)) is type(value) and prefs.get(key) == value for key, value in required.items()),
            "ENVIRONMENT_PREFERENCE_MISMATCH")


def expected_environment(artifact, sha256):
    spec = artifact["spec"]
    return {
        **({"BROWSER_PLATFORM_DISPLAY_MODE":"auto","MAX_RES":"3840x2160","SELKIES_MANUAL_RESOLUTION":"false"} if automatic(spec) else {"SELKIES_MANUAL_RESOLUTION":"true","SELKIES_MANUAL_WIDTH":str(spec["screen"]["width"]),"SELKIES_MANUAL_HEIGHT":str(spec["screen"]["height"])}),
        "BROWSER_PLATFORM_ENVIRONMENT_ID": spec["id"],
        "BROWSER_PLATFORM_ARTIFACT_SHA256": sha256,
        "BROWSER_PLATFORM_RUNTIME_IMAGE_DIGEST": artifact["runtimeImageDigest"],
        "BROWSER_PLATFORM_LOCALE": spec["locale"],
        "BROWSER_PLATFORM_LANGUAGES": ",".join(spec["languages"]),
        "TZ": spec["timezone"],
        "PIXELFLUX_WAYLAND": "false",
    }


def load_artifact(path, sha256, *, check_environment=True):
    require(is_hash(sha256), "ENVIRONMENT_HASH_REQUIRED")
    with Path(path).open("rb") as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    require(len(raw) <= 2 * 1024 * 1024, "ENVIRONMENT_ARTIFACT_INVALID")
    require(hmac.compare_digest(hashlib.sha256(raw).hexdigest(), sha256), "ENVIRONMENT_ARTIFACT_MISMATCH")
    artifact = decode(raw)
    validate_artifact(artifact, runtime_metadata())
    if check_environment:
        if automatic(artifact["spec"]):require(not any(os.environ.get(k) for k in ("SELKIES_MANUAL_WIDTH","SELKIES_MANUAL_HEIGHT")),"ENVIRONMENT_CONFIG_DRIFT")
        expected = expected_environment(artifact, sha256)
        require(all(os.environ.get(key) == value for key, value in expected.items()), "ENVIRONMENT_CONFIG_DRIFT")
        require(not any(key.startswith("CAMOU_CONFIG") for key in os.environ), "ENVIRONMENT_CONFIG_DRIFT")
    return artifact


def verify_acceptance(artifact, sha256):
    """The normal Worker entrypoint cannot activate an unvalidated candidate.

    Validation Workers explicitly use load_artifact() instead. Publication
    binds the exact successful report bytes through trusted deployment config,
    just as it binds the artifact; a report from another image is not reusable.
    """
    expected = os.environ.get("BROWSER_PLATFORM_ACCEPTANCE_SHA256", "")
    require(is_hash(expected), "ENVIRONMENT_ACCEPTANCE_REQUIRED")
    path = Path(os.environ.get("BROWSER_PLATFORM_ACCEPTANCE_FILE", "/run/browser-platform/acceptance.json"))
    with path.open("rb") as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    require(len(raw) <= 2 * 1024 * 1024 and hashlib.sha256(raw).hexdigest() == expected,
            "ENVIRONMENT_ACCEPTANCE_MISMATCH")
    report = decode(raw)
    if automatic(artifact["spec"]):
        require(report.get("schemaVersion")=="browser-platform/native-acceptance/v1" and report.get("status")=="pass" and report.get("phase")=="all" and report.get("artifactSHA256")==sha256 and report.get("runtimeImageDigest")==artifact["runtimeImageDigest"] and report.get("recreationsPerHome",0)>=10 and len(report.get("observations",[]))>=22 and report.get("offlineBackupRestore")=="pass" and report.get("dynamicDisplay")=="pass","ENVIRONMENT_ACCEPTANCE_INCOMPLETE")
        return
    require(isinstance(report, dict)
            and report.get("schemaVersion") == "browser-platform/camoufox-acceptance/v1"
            and report.get("status") == "pass" and report.get("phase") == "all",
            "ENVIRONMENT_ACCEPTANCE_FAILED")
    require(report.get("artifactSHA256") == sha256
            and report.get("runtimeImageDigest") == artifact["runtimeImageDigest"],
            "ENVIRONMENT_ACCEPTANCE_MISMATCH")
    results = report.get("results", {})
    require(isinstance(results, dict), "ENVIRONMENT_ACCEPTANCE_INCOMPLETE")
    homes = results.get("homeReplay", {})
    require(isinstance(homes, dict), "ENVIRONMENT_ACCEPTANCE_INCOMPLETE")
    require(results.get("artifactTests") == "pass"
            and REJECTIONS <= set(results.get("entrypointRejections", {}))
            and homes.get("homes") == 2
            and type(homes.get("recreationsPerHome")) is int and homes["recreationsPerHome"] >= 10
            and homes.get("observationsStable") is True
            and homes.get("storageRestored") is True
            and homes.get("offlineBackupRestore") == "pass", "ENVIRONMENT_ACCEPTANCE_INCOMPLETE")


def replay_environment(artifact):
    # Build process variables at runtime. Never persist the parent's environment
    # or a wholesale launch_options return value inside the artifact.
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("CAMOU_CONFIG"):
            del env[key]
    config = json.dumps(artifact["resolvedConfig"], ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
    for index, offset in enumerate(range(0, len(config), 32767), 1):
        env[f"CAMOU_CONFIG_{index}"] = config[offset:offset + 32767]
    env["BROWSER_PLATFORM_FIREFOX_PREFS"] = json.dumps(artifact["firefoxUserPrefs"], sort_keys=True, separators=(",", ":"))
    env["FONTCONFIG_FILE"] = str(BROWSER / "fontconfig/browser-platform.conf")
    env["TZ"] = artifact["spec"]["timezone"]
    env["GDK_BACKEND"] = "x11"
    env["MOZ_ENABLE_WAYLAND"] = "0"
    env.pop("WAYLAND_DISPLAY", None)
    return env


def publish(path, artifact):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = encode(artifact)
    fd, temporary = tempfile.mkstemp(prefix=".environment-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # link is atomic and refuses an existing revision, unlike replace.
        os.link(temporary, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.unlink(temporary)
    return hashlib.sha256(raw).hexdigest()


def generate(spec_path, output, image_digest):
    require(not Path(output).exists(), "ENVIRONMENT_REVISION_EXISTS")
    spec = decode(Path(spec_path).read_bytes())
    validate_spec(spec)
    metadata = runtime_metadata()
    # These imports and all random generation are exclusive to this command.
    from browserforge.fingerprints import Screen
    from camoufox.addons import DefaultAddons
    from camoufox.fingerprints import generate_fingerprint
    from camoufox.locales import verify_locale
    from camoufox.utils import launch_options

    for language in spec["languages"]:
        verify_locale(language)
    screen = Screen(min_width=spec["screen"]["width"], max_width=spec["screen"]["width"],
                    min_height=spec["screen"]["height"], max_height=spec["screen"]["height"])
    fingerprint = generate_fingerprint(screen=screen, window=(spec["window"]["width"], spec["window"]["height"]), os="linux")
    complete_fingerprint = asdict(fingerprint)
    options = launch_options(
        fingerprint=fingerprint, screen=screen, os="linux", ff_version=152,
        config={"timezone": spec["timezone"], "window.devicePixelRatio": 1.0},
        locale=spec["languages"], headless=True, geoip=False, humanize=False,
        block_webrtc=True, enable_cache=True, addons=[], exclude_addons=list(DefaultAddons),
        executable_path=EXECUTABLE, env={}, i_know_what_im_doing=True,
    )
    chunks = [options["env"][key] for key in sorted(
        (key for key in options["env"] if re.fullmatch(r"CAMOU_CONFIG_[1-9][0-9]*", key)),
        key=lambda key: int(key.rsplit("_", 1)[1]),
    )]
    config = decode("".join(chunks).encode())
    # Map explicit high-level language requirements through native Camoufox
    # properties. Keep every other resolved device value from the generator.
    config["navigator.language"] = spec["locale"]
    config["navigator.languages"] = spec["languages"]
    config["headers.Accept-Language"] = ",".join(
        language if index == 0 else f"{language};q={1 - index / 10:.1f}"
        for index, language in enumerate(spec["languages"])
    )
    config["addons"] = []
    artifact = {
        "schemaVersion": SCHEMA, "id": spec["id"] + "-artifact-1",
        "createdAt": datetime.now(timezone.utc).isoformat(), "spec": spec,
        "runtime": metadata, "runtimeImageDigest": image_digest,
        "browserforgeFingerprint": complete_fingerprint, "resolvedConfig": config,
        "firefoxUserPrefs": {**options["firefox_user_prefs"], **managed_preferences(spec)},
    }
    validate_artifact(artifact, metadata)
    sha256 = publish(output, artifact)
    print(json.dumps({"artifactId": artifact["id"], "sha256": sha256, "status": "candidate"}))


def launch(artifact, urls):
    if not urls:
        urls = shlex.split(os.environ.get("FIREFOX_CLI", "")) or ["about:blank"]
    for url in urls:
        parsed = urlsplit(url)
        require(url == "about:blank" or (parsed.scheme in ("http", "https") and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None), "BROWSER_URL_INVALID")
    home = Path("/config/.camoufox")
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = os.open(home / "worker.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        os.close(lock)
        raise ArtifactError("PROFILE_ALREADY_RUNNING") from error
    os.set_inheritable(lock, True)
    profile = home / "profile"
    profile.mkdir(mode=0o700, exist_ok=True)
    # The pinned browser's browser-init patch sizes the real window from the
    # frozen native config. Additional width/height CLI flags stall its startup.
    arguments = [str(EXECUTABLE), "--no-remote", "--profile", str(profile), *urls]
    os.execve(EXECUTABLE, arguments, replay_environment(artifact))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("generate")
    create.add_argument("--spec", type=Path, default=ROOT / "spec.tw.json")
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--image-digest", required=True)
    commands.add_parser("verify")
    start = commands.add_parser("launch")
    start.add_argument("urls", nargs="*")
    args = parser.parse_args()
    try:
        if args.command == "generate":
            generate(args.spec, args.output, args.image_digest)
            return
        artifact = load_artifact(os.environ.get("BROWSER_PLATFORM_ARTIFACT_FILE", "/run/browser-platform/environment.json"),
                                 os.environ.get("BROWSER_PLATFORM_ARTIFACT_SHA256", ""))
        verify_acceptance(artifact, os.environ["BROWSER_PLATFORM_ARTIFACT_SHA256"])
        if args.command == "verify":
            if os.getuid()==0:
                from display_config import configure
                configure("camoufox",automatic(artifact["spec"]))
            print("ENVIRONMENT_ARTIFACT_OK")
        else:
            launch(artifact, args.urls)
    except ArtifactError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
    except (OSError, KeyError, TypeError, ValueError, PackageNotFoundError) as error:
        print("ENVIRONMENT_UNAVAILABLE " + type(error).__name__, file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
