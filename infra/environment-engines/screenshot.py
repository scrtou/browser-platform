"""Convert the fixed 24-bit X11 QA display into PNG without extra packages."""
import struct
import zlib

def png(raw):
    h=struct.unpack('>25I',raw[:100]);width,height=h[4],h[5]
    assert h[11] in (24,32) and h[7]==0 and h[14:17]==(0xff0000,0xff00,0xff)
    pixel_bytes=h[11]//8
    offset=h[0]+12*h[19];rows=[]
    assert width>0 and height>0 and h[12]>=width*pixel_bytes and len(raw)>=offset+height*h[12]
    for y in range(height):
        row=raw[offset+y*h[12]:offset+(y+1)*h[12]]
        rgb=bytearray(width*3)
        rgb[0::3]=row[2:width*pixel_bytes:pixel_bytes];rgb[1::3]=row[1:width*pixel_bytes:pixel_bytes];rgb[2::3]=row[0:width*pixel_bytes:pixel_bytes]
        rows.append(b'\0'+rgb)
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')
