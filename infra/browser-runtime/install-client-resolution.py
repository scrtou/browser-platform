#!/usr/bin/env python3
"""Correct CSS/physical pixel conversion in the exact shipped Selkies client."""
import hashlib
from pathlib import Path

ASSET=Path('/usr/share/selkies/selkies-dashboard/assets/index-BTp9L9Xk.js')
BASE_SHA256='c7a3af93c8d368c0be1605a45f892b016ace21e891de365829b50d0159e0ce1e'
REPLACEMENTS=[
    # Callers convert these CSS measurements to physical pixels once.
    ('getWindowResolution(){const s=document.body?document.body.offsetWidth:window.innerWidth,c=document.body?document.body.offsetHeight:window.innerHeight,f=window.devicePixelRatio||1,p=s*f,y=c*f;return[Math.max(1,parseInt(p-p%2)),Math.max(1,parseInt(y-y%2))]}',
     'getWindowResolution(){const s=document.body?document.body.offsetWidth:window.innerWidth,c=document.body?document.body.offsetHeight:window.innerHeight;return[Math.max(1,s),Math.max(1,c)]}'),
    # Server MAX_RES scales the full requested aspect ratio before allocation.
    ('ae>4080&&(ae=4080),we>4080&&(we=4080),_.initialClientWidth=ae,_.initialClientHeight=we',
     '_.initialClientWidth=ae,_.initialClientHeight=we'),
    ('X>4080&&(X=4080),Z>4080&&(Z=4080);const we=`${X}x${Z}`;',
     'window.is_manual_resolution_mode&&(X>4080&&(X=4080),Z>4080&&(Z=4080));const we=`${X}x${Z}`;'),
    ('let Re=gt(we[0]),qe=gt(we[1]);const Mt=ht?1:window.devicePixelRatio||1,Kt=4080;if(Re*Mt>Kt&&(Re=Math.floor(Kt/Mt),Re=gt(Re)),qe*Mt>Kt&&(qe=Math.floor(Kt/Mt),qe=gt(qe)),Re<=0||qe<=0)',
     'let Re=we[0],qe=we[1];if(Re<=0||qe<=0)'),
]

def patch(raw):
    if hashlib.sha256(raw).hexdigest()!=BASE_SHA256:
        raise ValueError('SELKIES_CLIENT_BASE_MISMATCH')
    source=raw.decode()
    for old,new in REPLACEMENTS:
        if source.count(old)!=1:raise ValueError('SELKIES_CLIENT_ANCHOR_MISMATCH')
        source=source.replace(old,new)
    return source.encode()

def main():
    ASSET.write_bytes(patch(ASSET.read_bytes()))

if __name__=='__main__':main()
