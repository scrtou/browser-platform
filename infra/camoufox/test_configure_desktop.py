import importlib.util
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).with_name("configure-desktop.py")
SPEC = importlib.util.spec_from_file_location("configure_desktop", MODULE_PATH)
configure_desktop = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(configure_desktop)


def pinned_root(tmp_path: Path) -> Path:
    for name in ("etc/xdg/openbox/rc.xml", "etc/xdg/openbox/rc.xml.bak"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<openbox><keepBorder>yes</keepBorder><applications></applications></openbox>\n")
    menu = tmp_path / "defaults/menu.xml"
    menu.parent.mkdir(parents=True)
    menu.write_text("<menu>\n" + configure_desktop.FIREFOX_MENU_ITEM + "</menu>\n")
    desktop = tmp_path / "usr/share/applications/firefox.desktop"
    desktop.parent.mkdir(parents=True)
    desktop.write_text("[Desktop Entry]\nExec=firefox %u\nExec=firefox -new-window\n")
    command = tmp_path / "usr/bin/firefox"
    command.parent.mkdir(parents=True)
    command.symlink_to("../lib/firefox/firefox.sh")
    return tmp_path


class ConfigureDesktopTest(unittest.TestCase):
    def test_removes_unmanaged_firefox_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pinned_root(Path(directory))
            configure_desktop.configure(root, existing_rule=False)

            rc = (root / "etc/xdg/openbox/rc.xml").read_text()
            self.assertIn("<keepBorder>no</keepBorder>", rc)
            self.assertEqual(rc.count(configure_desktop.RULE), 1)
            self.assertNotIn("FireFox", (root / "defaults/menu.xml").read_text())
            self.assertFalse((root / "usr/share/applications/firefox.desktop").exists())
            self.assertFalse((root / "usr/bin/firefox").exists())

            configure_desktop.configure(root, existing_rule=True)

    def test_rejects_unexpected_system_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pinned_root(Path(directory))
            (root / "usr/bin/firefox").unlink()
            (root / "usr/bin/firefox").symlink_to("unexpected")
            with self.assertRaisesRegex(SystemExit, "unexpected system Firefox launcher"):
                configure_desktop.configure(root, existing_rule=False)


if __name__ == "__main__":
    unittest.main()
