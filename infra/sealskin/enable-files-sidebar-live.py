#!/usr/bin/env python3
"""Show upload controls on the pinned legacy Worker without restarting Selkies.

Run inside a Worker. Its backend must already allow uploads. New sessions use
the application environment instead; the custom-init hook covers later starts
of an existing container. This patch changes presentation, not authorization.
"""

import hashlib
import json
import os
from pathlib import Path


def main():
    root = Path('/usr/share/selkies/web')
    source_name = 'index-BTp9L9Xk.js'
    expected = '12d75adb19371bece1fb077efb9bf198a79f03e3e09255b7a310c08fde3bb088'
    source = (root / 'assets' / source_name).read_bytes()
    if hashlib.sha256(source).hexdigest() != expected:
        raise SystemExit('Unrecognized Selkies frontend; refusing to patch')
    replacements = [
        (b'g.files=O.ui_sidebar_show_files?.value??!0', b'g.files=!0'),
        (b'g.fileDownload=Ye?Ye.value.includes("download"):!0', b'g.fileDownload=!1'),
    ]
    for before, after in replacements:
        if source.count(before) != 1:
            raise SystemExit('Unexpected frontend structure; refusing to patch')
        source = source.replace(before, after, 1)
    digest = hashlib.sha256(source).hexdigest()
    name = 'index-files-upload-' + digest[:16] + '.js'
    html_path = root / 'index.html'
    html = html_path.read_bytes()
    old_reference = ('./assets/' + source_name).encode()
    new_reference = ('./assets/' + name).encode()
    if new_reference not in html:
        if html.count(old_reference) != 1:
            raise SystemExit('Unexpected index HTML; refusing to patch')
        backup = Path('/var/lib/browser-platform/files-sidebar')
        backup.mkdir(parents=True, mode=0o700, exist_ok=True)
        original_html = backup / 'index.html'
        if not original_html.exists():
            original_html.write_bytes(html)
            original_html.chmod(0o600)
        asset = root / 'assets' / name
        asset.write_bytes(source)
        asset.chmod(0o644)
        temporary = root / '.index-files-upload.tmp'
        temporary.write_bytes(html.replace(old_reference, new_reference, 1))
        temporary.chmod(0o644)
        os.replace(temporary, html_path)
    if (root / 'assets' / name).read_bytes() != source:
        raise SystemExit('Patched frontend verification failed')
    print(json.dumps({'asset': name, 'sha256': digest, 'filesVisible': True,
                      'downloadButtonVisible': False, 'servicesRestarted': False}))


if __name__ == '__main__':
    main()
