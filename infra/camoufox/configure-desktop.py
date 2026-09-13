#!/usr/bin/env python3
"""Keep Openbox from overriding Camoufox's frozen native window dimensions."""

from pathlib import Path

RULE = '  <application class="camoufox"><maximized>no</maximized><decor>no</decor></application>\n'

for path in (Path("/etc/xdg/openbox/rc.xml"), Path("/etc/xdg/openbox/rc.xml.bak")):
    if path.name.endswith(".bak") and not path.exists():
        continue
    source = path.read_text()
    if source.count("</applications>") != 1 or RULE in source:
        raise SystemExit("unexpected Openbox configuration in the pinned base image")
    path.write_text(source.replace("</applications>", RULE + "</applications>"))
