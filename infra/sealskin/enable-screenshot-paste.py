#!/usr/bin/env python3
"""Install the pinned native-paste client without restarting any service.

Run inside the Worker with screenshot-paste.js beside this script. Known
unpatched, Files-only, and previously recorded native-paste assets are accepted.
The original frontend is never overwritten; index.html is changed atomically.
"""

import hashlib
import json
import os
from pathlib import Path
import re


SOURCE = 'index-BTp9L9Xk.js'
SOURCE_SHA256 = '12d75adb19371bece1fb077efb9bf198a79f03e3e09255b7a310c08fde3bb088'
FILES_SHA256 = '165a23abbbf5bad5b0b1677ab5bdebad4ab72c9c2cf914e7f088baacba77df9d'
BRIDGE = b'''let bpClientSettings=null;
window.browserPlatformPaste.connect({
socket:()=>m,
controls:()=>!E&&T==="controller"&&Ne==="primary",
allowed:()=>!E&&T==="controller"&&Ne==="primary"&&!!window.clipboard_enabled&&jt&&Wt&&bpClientSettings!==null,
copyAllowed:()=>!E&&T==="controller"&&Ne==="primary"&&!!window.clipboard_enabled&&Wt&&bpClientSettings!==null,
settings:()=>({...bpClientSettings}),
resetKeyboard:()=>{window.webrtcInput?.resetKeyboard();if(m?.readyState===WebSocket.OPEN)m.send("kr")}
});'''


def digest(data):
    return hashlib.sha256(data).hexdigest()


def install(root=Path('/usr/share/selkies/web'), state=Path('/var/lib/browser-platform/screenshot-paste')):
    source = (root / 'assets' / SOURCE).read_bytes()
    if digest(source) != SOURCE_SHA256:
        raise RuntimeError('Unrecognized Selkies frontend; refusing to patch')
    for before, after in [
        (b'g.files=O.ui_sidebar_show_files?.value??!0', b'g.files=!0'),
        (b'g.fileDownload=Ye?Ye.value.includes("download"):!0', b'g.fileDownload=!1'),
        # UTF-16 surrogate halves are not Unicode characters or valid X11
        # keysyms. Preserve supplementary CJK/emoji in both committed text and
        # composition updates; Latin modifier handling remains upstream's.
        (b'for(let f=0;f<c.length;f++){const p=c[f];if(p>="A"&&p<="Z")',
         b'for(const p of c){if(p>="A"&&p<="Z")'),
        (b'const y=ds.lookup(p.charCodeAt(0));y&&(this.send("kd,"+y),this.send("ku,"+y))',
         b'const y=ds.lookup(p.codePointAt(0));y&&(this.send("kd,"+y),this.send("ku,"+y))'),
        (b'const c=s.data;for(let f=0;f<c.length;f++){const p=c.charCodeAt(f),y=ds.lookup(p);',
         b'const c=s.data;for(const f of c){const p=f.codePointAt(0),y=ds.lookup(p);'),
        (b'_updateCompositionText(s){const c=this.compositionString,f=s||"";let p=0;',
         b'_updateCompositionText(s){const c=Array.from(this.compositionString),f=Array.from(s||"");let p=0;'),
        (b'const m=f.substring(p);for(let z=0;z<m.length;z++){const T=ds.lookup(m.charCodeAt(z));',
         b'const m=f.slice(p);for(const z of m){const T=ds.lookup(z.codePointAt(0));'),
        (b'this.compositionString=f}_compositionStart(s)',
         b'this.compositionString=s||""}_compositionStart(s)'),
        (b'async function gn(_,x="text/plain"){', BRIDGE + b'async function gn(_,x="text/plain"){'),
        # Use the last actual client settings, not a freshly derived snapshot:
        # initial X11 server-enforced resolution is normalized after its send.
        (b'const x=Xl(),X=`SETTINGS,${JSON.stringify(x)}`;m.send(X)',
         b'const x=Xl(),X=`SETTINGS,${JSON.stringify(x)}`;bpClientSettings={...x};m.send(X)'),
        (b'const _t=`SETTINGS,${JSON.stringify(K)}`;m.send(_t)',
         b'const _t=`SETTINGS,${JSON.stringify(K)}`;bpClientSettings={...K};m.send(_t)'),
        (b'm=new WebSocket(Mt.href),m.binaryType="arraybuffer";',
         b'm=new WebSocket(Mt.href),bpClientSettings=null,m.binaryType="arraybuffer";window.browserPlatformPaste.socketChanged(m);'),
        (b'const Pe=new TextDecoder().decode(et);navigator.clipboard.writeText(Pe)',
         b'const Pe=new TextDecoder().decode(et);window.browserPlatformPaste.remoteClipboard(j.target,Pe);navigator.clipboard.writeText(Pe)'),
        (b'K.text().then(ie=>{navigator.clipboard.writeText(ie)',
         b'K.text().then(ie=>{window.browserPlatformPaste.remoteClipboard(j.target,ie);navigator.clipboard.writeText(ie)'),
        (b'const K=new Blob(xt.data,{type:xt.mimeType});if(xt.mimeType===',
         b'const K=new Blob(xt.data,{type:xt.mimeType});if(xt.mimeType!=="text/plain")window.browserPlatformPaste.remoteClipboard(j.target,null);if(xt.mimeType==='),
        (b'else if(j.data.startsWith("clipboard_binary,")){if(!Ct)',
         b'else if(j.data.startsWith("clipboard_binary,")){window.browserPlatformPaste.remoteClipboard(j.target,null);if(!Ct)'),
    ]:
        if source.count(before) != 1:
            raise RuntimeError('Unexpected frontend structure; refusing to patch')
        source = source.replace(before, after, 1)
    addon = Path(__file__).with_name('screenshot-paste.js').read_bytes()
    source = addon + b'\n' + source
    sha256 = digest(source)
    name = 'index-native-paste-' + sha256[:16] + '.js'
    html_path = root / 'index.html'
    html = html_path.read_bytes()
    references = re.findall(rb'<script type="module" crossorigin src="\./assets/([^"/]+)"', html)
    if len(references) != 1:
        raise RuntimeError('Unexpected index HTML; refusing to patch')
    current = references[0].decode('ascii')
    known = {SOURCE: SOURCE_SHA256, 'index-files-upload-' + FILES_SHA256[:16] + '.js': FILES_SHA256, name: sha256}
    manifest_path = state / 'manifest.json'
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text())
        known[previous['asset']] = previous['sha256']
        if previous.get('previousAsset'):
            known[previous['previousAsset']] = previous['previousSHA256']
    if current not in known or digest((root / 'assets' / current).read_bytes()) != known[current]:
        raise RuntimeError('Unrecognized active frontend; refusing to replace it')
    state.mkdir(parents=True, mode=0o700, exist_ok=True)
    backup = state / 'index.before.html'
    if not backup.exists():
        backup.write_bytes(html)
        backup.chmod(0o600)
    asset_path = root / 'assets' / name
    if asset_path.exists() and asset_path.read_bytes() != source:
        raise RuntimeError('Asset name collision; refusing to overwrite')
    asset_path.write_bytes(source)
    asset_path.chmod(0o644)
    report = {'asset': name, 'sha256': sha256, 'addonSHA256': digest(addon),
              'sourceSHA256': SOURCE_SHA256, 'nativePaste': True, 'nativeTextCopy': True,
              'previousAsset': current, 'previousSHA256': known[current],
              'filesVisible': True, 'downloadButtonVisible': False, 'servicesRestarted': False}
    # Write the manifest before HTML: interruption leaves either known index valid.
    temp_manifest = state / '.manifest.tmp'
    temp_manifest.write_text(json.dumps(report, indent=2) + '\n')
    temp_manifest.chmod(0o600)
    os.replace(temp_manifest, manifest_path)
    temporary = root / '.index-native-paste.tmp'
    temporary.write_bytes(html.replace(('./assets/' + current).encode(), ('./assets/' + name).encode(), 1))
    temporary.chmod(0o644)
    os.replace(temporary, html_path)
    return report


if __name__ == '__main__':
    print(json.dumps(install()))
