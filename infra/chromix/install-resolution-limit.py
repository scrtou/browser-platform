#!/usr/bin/env python3
"""Patch the exact pinned Selkies layout before framebuffer/capture creation."""
import hashlib
from pathlib import Path

path=Path('/lsiopy/lib/python3.14/site-packages/selkies/selkies.py')
raw=path.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='660a578fc9fca69d2cd06580f1e8bf216ddfe1e2994f3c2eb1acbadeb113d5de'
source=raw.decode()
anchor='                aligned_total_width = (total_width + 7) & ~7\n'
patch='''                # Browser Platform: bound actual layout before Xrandr and capture.
                # No MAX_RES means preserve the original upstream behavior.
                max_res = os.environ.get("MAX_RES", "")
                if not IS_WAYLAND and max_res:
                    max_w, max_h = map(int, max_res.split("x"))
                    scale = min(1.0, max_w / total_width, max_h / total_height)
                    if scale < 1.0:
                        for layout in layouts.values():
                            left = int(layout['x'] * scale) // 8 * 8
                            top = int(layout['y'] * scale) // 2 * 2
                            right = int((layout['x'] + layout['w']) * scale) // 8 * 8
                            bottom = int((layout['y'] + layout['h']) * scale) // 2 * 2
                            layout.update(x=left, y=top, w=right-left, h=bottom-top)
                        total_width = max(r['x'] + r['w'] for r in layouts.values())
                        total_height = max(r['y'] + r['h'] for r in layouts.values())
                        for display_id, layout in layouts.items():
                            self.display_clients[display_id].update(width=layout['w'], height=layout['h'])
                        if 'primary' in layouts:
                            self.app.display_width = layouts['primary']['w']
                            self.app.display_height = layouts['primary']['h']
'''
assert source.count(anchor)==1
source=source.replace(anchor,patch+anchor)
compile(source,str(path),'exec')
path.write_text(source)

# Auto streams can be capped below client DPR * viewport. Map absolute input
# through actual canvas pixels, as the upstream manual/shared paths already do.
asset=Path('/usr/share/selkies/selkies-dashboard/assets/index-BTp9L9Xk.js')
raw=asset.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='12d75adb19371bece1fb077efb9bf198a79f03e3e09255b7a310c08fde3bb088'
source=raw.decode()
old='if((window.is_manual_resolution_mode||this.isSharedMode)&&T){const w=T.getBoundingClientRect();'
new='if(T){const w=T.getBoundingClientRect();'
assert source.count(old)==1
source=source.replace(old,new)

old='else if(K.type==="stream_resolution"){if(E){'
new='else if(K.type==="stream_resolution"){if(!E&&!window.is_manual_resolution_mode&&p&&K.width>0&&K.height>0){const bpParent=p.parentElement,bpW=Number(K.width),bpH=Number(K.height),bpScale=Math.min(bpParent.clientWidth/bpW,bpParent.clientHeight/bpH),bpX=(bpParent.clientWidth-bpW*bpScale)/2,bpY=(bpParent.clientHeight-bpH*bpScale)/2;p.width=bpW;p.height=bpH;for(const bpNode of [p,document.getElementById("overlayInput")])if(bpNode){bpNode.style.position="absolute";bpNode.style.width=`${bpW*bpScale}px`;bpNode.style.height=`${bpH*bpScale}px`;bpNode.style.left=`${bpX}px`;bpNode.style.top=`${bpY}px`;}window.webrtcInput&&window.webrtcInput.resize();}if(E){'
assert source.count(old)==1
asset.write_text(source.replace(old,new))
