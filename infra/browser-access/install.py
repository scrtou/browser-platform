"""Patch only the reviewed LSIO/Selkies files from the retained r6 image."""

import hashlib
from pathlib import Path

ROOT = Path("/usr/local/lib/browser-platform/access-layer")
INIT = Path("/etc/s6-overlay/s6-rc.d/init-nginx/run")
DEFAULT = Path("/defaults/default.conf")
SETTINGS = Path("/lsiopy/lib/python3.14/site-packages/selkies/settings.py")
NGINX = Path("/etc/nginx/nginx.conf")
EXPECTED = {
    INIT: "ba9a3f4f8f7814b3631e2d3456affca86e0ad50ce11ef62396adc1763da40047",
    DEFAULT: "64646dc572c01c7077ad6aed54465bd8a31b096877f5ec086424e03ecf660385",
    SETTINGS: "55f416b1b6e0def3518273163d4069abb4576e17e9c3f51297360702c31ec493",
    NGINX: "d7be180d12cb332090cf4a0e8de780bd30e7f59fd0ffa4ad42be0e70e6bc6348",
}
for path, expected in EXPECTED.items():
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit("unreviewed Worker access input")

source = INIT.read_text()
begin = source.index('if [ -n "${PASSWORD}" ]; then')
end = source.index("\nfi", begin) + len("\nfi")
source = source[:begin] + source[end:]
source = source.replace('CUSER="${CUSTOM_USER:-abc}"\n', "")
source = source.replace("\n# nginx Path", f"\npython3 {ROOT}/session_access.py || exit 1\n\n# nginx Path", 1)
source = source.replace("/config/ssl", "/run/browser-platform-display/tls")
INIT.write_text(source)

source = DEFAULT.read_text().replace("#auth_basic", "auth_basic")
source = source.replace("/etc/nginx/.htpasswd", "/run/browser-platform-display/basic.htpasswd")
source = source.replace("/config/ssl", "/run/browser-platform-display/tls")
DEFAULT.write_text(source)

source = SETTINGS.read_text()
prefix = f"import sys\nsys.path.insert(0, {str(ROOT)!r})\nimport session_access\nsession_access.install_safe_logging()\n"
source = prefix + source
marker = "            raw_value = cli_val if cli_val is not None else"
assert source.count(marker) == 1
source = source.replace(marker, """            if name == 'master_token':
                if cli_val is not None or std_env_val is not None:
                    raise RuntimeError('SESSION_AUTH_OVERRIDE_FORBIDDEN')
                processed[name] = session_access.master_token()
                continue

""" + marker)
SETTINGS.write_text(source)

source = NGINX.read_text().replace("error_log /var/log/nginx/error.log;", "error_log /dev/null;")
source = source.replace("access_log /var/log/nginx/access.log;", """log_format bp_safe escape=json '{"event":"WORKER_HTTP","status":$status}';
    access_log /dev/stdout bp_safe;""")
NGINX.write_text(source)
