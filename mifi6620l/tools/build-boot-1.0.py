#!/usr/bin/env python3
from pathlib import Path
import struct, gzip, hashlib, time

BASE = Path.home() / "tuxforge/mifi6620l"
STOCK = BASE / "stock/apps.img"
TUXUI = BASE / "build/helpers/tuxui-boot"
SPLASH = BASE / "tuxforge-root/opt/tuxforge/splash.argb"
FONT = BASE / "tuxforge-root/opt/tuxforge/font7x11.alpha"

OUT = BASE / "releases/tuxforge-1.0-mifi6620l.img"

RAMDISK_ADDR = 0x01200000
PARTITION_MAX = 0x00a80000

def align4(b):
    return b + b"\0" * ((-len(b)) & 3)

def align(x, n):
    return (x + n - 1) & ~(n - 1)

ino = 1
archive = bytearray()

def add(name, mode, data=b"", rmaj=0, rmin=0):
    global ino, archive

    nameb = name.encode() + b"\0"
    now = int(time.time())

    fields = [
        ino, mode, 0, 0, 1, now,
        len(data),
        0, 0,
        rmaj, rmin,
        len(nameb),
        0,
    ]

    hdr = b"070701" + b"".join(f"{x:08x}".encode() for x in fields)

    archive += hdr
    archive += nameb
    archive = bytearray(align4(bytes(archive)))

    if data:
        archive += data
        archive = bytearray(align4(bytes(archive)))

    ino += 1

# directories
add(".",                 0o040755)
add("dev",               0o040755)
add("dev/input",         0o040755)
add("newroot",           0o040755)
add("opt",               0o040755)
add("opt/tuxforge",      0o040755)

# TuxUI itself is PID 1
add("init",              0o100755, TUXUI.read_bytes())

# assets
add("opt/tuxforge/splash.argb",     0o100644, SPLASH.read_bytes())
add("opt/tuxforge/font7x11.alpha",  0o100644, FONT.read_bytes())

# required character devices
add("dev/console",       0o020600, b"", 5, 1)
add("dev/null",          0o020666, b"", 1, 3)
add("dev/tty0",          0o020600, b"", 4, 0)
add("dev/fb0",           0o020600, b"", 29, 0)
add("dev/input/event0",  0o020600, b"", 13, 64)
add("dev/input/event1",  0o020600, b"", 13, 65)

# stock YAFFS2 root: block major 31, minor 15
add("dev/mtdblock15",    0o060600, b"", 31, 15)

# archive terminator
add("TRAILER!!!", 0, b"")

cpio = bytes(archive)
ramdisk = gzip.compress(cpio, compresslevel=9, mtime=0)

print("=== TINY INITRAMFS ===")
print(f"CPIO   : {len(cpio):#x} ({len(cpio)})")
print(f"GZIP   : {len(ramdisk):#x} ({len(ramdisk)})")

img = bytearray(STOCK.read_bytes())

if img[:8] != b"ANDROID!":
    raise SystemExit("No ANDROID! header")

kernel_size = struct.unpack_from("<I", img, 0x08)[0]
kernel_addr = struct.unpack_from("<I", img, 0x0c)[0]
second_size = struct.unpack_from("<I", img, 0x18)[0]
page_size   = struct.unpack_from("<I", img, 0x24)[0]
dt_size     = struct.unpack_from("<I", img, 0x28)[0]

if second_size:
    raise SystemExit("Unexpected second stage")

kernel = img[page_size:page_size + kernel_size]

old_dt_off = page_size + align(kernel_size, page_size)
dt = img[old_dt_off:old_dt_off + dt_size]

header = bytearray(img[:page_size])

# external initramfs
struct.pack_into("<I", header, 0x10, len(ramdisk))
struct.pack_into("<I", header, 0x14, RAMDISK_ADDR)

oldcmd = header[64:576].split(b"\0", 1)[0].decode("ascii", "replace")

cmd = oldcmd.replace("noinitrd ", "")
cmd = " ".join(cmd.split())

if "rdinit=/init" not in cmd:
    cmd += " rdinit=/init"

enc = cmd.encode()

if len(enc) >= 512:
    raise SystemExit("cmdline too long")

header[64:576] = b"\0" * 512
header[64:64+len(enc)] = enc

out = bytearray(header)

out += kernel
out += b"\0" * (align(len(out), page_size) - len(out))

rd_off = len(out)
out += ramdisk
out += b"\0" * (align(len(out), page_size) - len(out))

dt_off = len(out)
out += dt
out += b"\0" * (align(len(out), page_size) - len(out))

print()
print("=== MEMORY ===")
print(f"kernel : {kernel_addr:#010x} .. {kernel_addr+kernel_size:#010x}")
print(f"ramdisk: {RAMDISK_ADDR:#010x} .. {RAMDISK_ADDR+len(ramdisk):#010x}")

print()
print("=== IMAGE ===")
print(f"ramdisk offset: {rd_off:#x}")
print(f"DT offset     : {dt_off:#x}")
print(f"size          : {len(out):#x}")
print(f"max           : {PARTITION_MAX:#x}")
print(f"free          : {PARTITION_MAX-len(out):#x}")
print(f"cmdline       : {cmd}")

if len(out) > PARTITION_MAX:
    raise SystemExit("IMAGE TOO LARGE")

OUT.write_bytes(out)

print()
print("BUILD OK")
print("output :", OUT)
print("sha256:", hashlib.sha256(out).hexdigest())
