#!/usr/bin/env python3
"""Keep the frozen browser window stable and remove unmanaged launch paths."""

import argparse
from pathlib import Path
import re

RULE = '  <application class="camoufox"><maximized>no</maximized><decor>no</decor></application>\n'
FIREFOX_MENU_ITEM = '<item label="FireFox" icon="/usr/share/icons/hicolor/48x48/apps/firefox.png"><action name="Execute"><command>/usr/bin/firefox</command></action></item>\n'


def rooted(root: Path, path: str) -> Path:
    return root / path.removeprefix("/")


def remove_unmanaged_firefox(root: Path) -> None:
    menu = rooted(root, "/defaults/menu.xml")
    source = menu.read_text()
    count = source.count(FIREFOX_MENU_ITEM)
    if count not in (0, 1):
        raise SystemExit("unexpected Firefox entry in the pinned Openbox menu")
    if count:
        menu.write_text(source.replace(FIREFOX_MENU_ITEM, ""))

    desktop = rooted(root, "/usr/share/applications/firefox.desktop")
    command = rooted(root, "/usr/bin/firefox")
    if not desktop.exists() and not command.exists() and not command.is_symlink():
        return
    if (not desktop.is_file() or not command.is_symlink()
            or command.readlink() != Path("../lib/firefox/firefox.sh")):
        raise SystemExit("unexpected system Firefox launcher in the pinned base image")
    entries = desktop.read_text()
    if entries.count("Exec=firefox %u") != 1 or "Exec=firefox -new-window" not in entries:
        raise SystemExit("unexpected Firefox desktop entry in the pinned base image")
    desktop.unlink()
    command.unlink()


def configure(root: Path, *, existing_rule: bool) -> None:
    for name in ("/etc/xdg/openbox/rc.xml", "/etc/xdg/openbox/rc.xml.bak"):
        path = rooted(root, name)
        if path.name.endswith(".bak") and not path.exists():
            continue
        source = path.read_text()
        if source.count("</applications>") != 1 or source.count(RULE) != int(existing_rule):
            raise SystemExit("unexpected Openbox configuration in the pinned base image")
        border = r'<keepBorder>\s*(?:yes|no)\s*</keepBorder>'
        if len(re.findall(border, source)) != 1:
            raise SystemExit("unexpected Openbox border setting in the pinned base image")
        source = re.sub(border, '<keepBorder>no</keepBorder>', source)
        if not existing_rule:
            source = source.replace("</applications>", RULE + "</applications>")
        path.write_text(source)
    remove_unmanaged_firefox(root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--existing-rule', action='store_true', help='update the reviewed r4–r9 desktop layer')
    parser.add_argument('--root', type=Path, default=Path("/"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    configure(args.root, existing_rule=args.existing_rule)


if __name__ == "__main__":
    main()
