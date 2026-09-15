"""Check pinned asset upgrades, idempotence, and refusal to overwrite unknown JS."""

import argparse
import importlib.util
from pathlib import Path
import tempfile


parser = argparse.ArgumentParser()
parser.add_argument('--frontend', type=Path, required=True)
parser.add_argument('--previous-addon', type=Path, help='optional immutable prior addon for upgrade/rollback verification')
args = parser.parse_args()
script = Path(__file__).resolve().parents[1] / 'enable-screenshot-paste.py'
spec = importlib.util.spec_from_file_location('installer', script)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
source = args.frontend.read_bytes()
assert installer.digest(source) == installer.SOURCE_SHA256
files_only = source.replace(b'g.files=O.ui_sidebar_show_files?.value??!0', b'g.files=!0').replace(
    b'g.fileDownload=Ye?Ye.value.includes("download"):!0', b'g.fileDownload=!1')
assert installer.digest(files_only) == installer.FILES_SHA256

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory) / 'web'
    state = Path(directory) / 'state'
    (root / 'assets').mkdir(parents=True)
    (root / 'assets' / installer.SOURCE).write_bytes(source)
    files_name = 'index-files-upload-' + installer.FILES_SHA256[:16] + '.js'
    (root / 'assets' / files_name).write_bytes(files_only)
    original_html = ('<script type="module" crossorigin src="./assets/' + files_name + '"></script>').encode()
    (root / 'index.html').write_bytes(original_html)
    first = installer.install(root, state)
    installed_html = (root / 'index.html').read_bytes()
    assert (state / 'index.before.html').read_bytes() == original_html

    if args.previous_addon:
        previous_spec = importlib.util.spec_from_file_location('previous_installer',args.previous_addon/'enable-screenshot-paste.py')
        previous = importlib.util.module_from_spec(previous_spec)
        previous_spec.loader.exec_module(previous)
        old = previous.install(root,state)
        assert old['sha256'] != first['sha256']
        assert installer.digest((root/'assets'/old['asset']).read_bytes()) == old['sha256']
        restored = installer.install(root,state)
        assert restored['sha256'] == first['sha256'] and (root/'index.html').read_bytes() == installed_html
        assert (state/'index.before.html').read_bytes() == original_html
    assert (root / 'assets' / installer.SOURCE).read_bytes() == source
    assert installer.digest((root / 'assets' / first['asset']).read_bytes()) == first['sha256']
    second = installer.install(root, state)
    assert second['asset'] == first['asset']
    assert (root / 'index.html').read_bytes() == installed_html
    assert (state / 'index.before.html').read_bytes() == original_html

    # A changed upstream must leave the active page untouched.
    (root / 'assets' / installer.SOURCE).write_bytes(source + b'\n// unknown upstream')
    try:
        installer.install(root, state)
        raise AssertionError('unknown upstream was accepted')
    except RuntimeError:
        assert (root / 'index.html').read_bytes() == installed_html
    (root / 'assets' / installer.SOURCE).write_bytes(source)

    # A modified active asset must also be refused, even with a valid original.
    (root / 'assets' / first['asset']).write_bytes(b'unknown active asset')
    try:
        installer.install(root, state)
        raise AssertionError('unknown active asset was accepted')
    except RuntimeError:
        assert (root / 'index.html').read_bytes() == installed_html

print('pinned_upgrade_idempotence_and_tamper_refusal=pass')
