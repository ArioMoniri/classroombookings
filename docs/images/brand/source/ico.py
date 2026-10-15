"""Write a .ico whose entries are the given PNG files verbatim (PNG-in-ICO, Vista+)."""
import struct, sys
out, *pngs = sys.argv[1:]
datas = [open(p, "rb").read() for p in pngs]
def wh(d):
    w, h = struct.unpack(">II", d[16:24]); return w, h
hdr = struct.pack("<HHH", 0, 1, len(datas)); off = 6 + 16 * len(datas); ents = b""
for d in datas:
    w, h = wh(d)
    ents += struct.pack("<BBBBHHII", w % 256, h % 256, 0, 0, 1, 32, len(d), off); off += len(d)
open(out, "wb").write(hdr + ents + b"".join(datas))
print(out, off, "bytes")
