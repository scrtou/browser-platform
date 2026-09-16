#!/usr/bin/env python3
"""Keep Openbox from resizing or bordering the frozen native browser window."""

import argparse
from pathlib import Path
import re

RULE = '  <application class="camoufox"><maximized>no</maximized><decor>no</decor></application>\n'

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--existing-rule', action='store_true', help='update the reviewed r4–r7 desktop layer')
args = parser.parse_args()

for path in (Path("/etc/xdg/openbox/rc.xml"), Path("/etc/xdg/openbox/rc.xml.bak")):
    if path.name.endswith(".bak") and not path.exists():
        continue
    source = path.read_text()
    if source.count("</applications>") != 1 or source.count(RULE) != int(args.existing_rule):
        raise SystemExit("unexpected Openbox configuration in the pinned base image")
    border = r'<keepBorder>\s*(?:yes|no)\s*</keepBorder>'
    if len(re.findall(border, source)) != 1:
        raise SystemExit("unexpected Openbox border setting in the pinned base image")
    source = re.sub(border, '<keepBorder>no</keepBorder>', source)
    if not args.existing_rule:
        source = source.replace("</applications>", RULE + "</applications>")
    path.write_text(source)
