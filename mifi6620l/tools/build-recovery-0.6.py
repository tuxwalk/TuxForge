#!/usr/bin/env python3

from pathlib import Path
import gzip
import hashlib
import struct
import sys

PAGE = 0x1000

# Recovery kernel embedded CPIO gzip discovered by reverse engineering.
ROOTFS_OFF  = 0x6e701c
ROOTFS_SLOT = 0x2da225

W = 220
H = 176
SPLASH_SIZE = W * H * 3


BASE = Path(__file__).resolve().parent.parent

STOCK   = BASE / "stock/recovery.img"
FBFLUSH = BASE / "tuxforge-root/opt/tuxforge/fbflush"
SPLASH  = BASE / "tuxforge-root/opt/tuxforge/splash.raw"
TUXREBOOT = BASE / "tuxforge-root/opt/tuxforge/tuxreboot-bootloader"
TUXUI = BASE / "tuxforge-root/opt/tuxforge/tuxui"
SPLASH_ARGB = BASE / "tuxforge-root/opt/tuxforge/splash.argb"
FONT_ALPHA = BASE / "tuxforge-root/opt/tuxforge/font7x11.alpha"
EARLY_INIT = BASE / "tuxforge-root/init"
OUTPUT  = BASE / "releases/tuxforge-0.6-mifi6620l.img"


START_UPDATE = b"""#!/bin/sh
# TuxForge 0.3
# Novatel firmware updater deliberately disabled.
exit 0
"""


UPGRADE_INTERRUPTED = b"""#!/bin/sh
# TuxForge: stock interrupted-upgrade path disabled.
exit 0
"""


TUXFORGE_INIT = b"""#!/bin/sh

case "${1:-start}" in
    start)
        echo "================================"
        echo "          TuxForge 0.6"
        echo "       Novatel MiFi 6620L"
        echo "================================"

        echo "TuxForge 0.6" > /tmp/tuxforge-version
        echo "ui-pending" > /tmp/tuxforge-status

        if [ -c /dev/ttyHSL0 ]; then
            echo "=== TuxForge 0.6 ===" > /dev/ttyHSL0
        fi

        #
        # Never let the graphical UI block SysV boot.
        #
        (
            echo "TuxForge 0.6 UI launcher"

            #
            # The nodes appear early, but the Novatel LCD hardware
            # needs additional time to settle.
            #
            sleep 6

            if [ ! -c /dev/fb0 ]; then
                echo "ERROR: /dev/fb0 missing"
                echo "ui-failed-fb" > /tmp/tuxforge-status
                exit 0
            fi

            if [ ! -c /dev/input/event1 ]; then
                echo "ERROR: /dev/input/event1 missing"
                echo "ui-failed-input" > /tmp/tuxforge-status
                exit 0
            fi

            echo "starting tuxui"

            /opt/tuxforge/tuxui \
                >/tmp/tuxui.log 2>&1 &

            pid=$!
            echo "$pid" > /tmp/tuxui.pid

            sleep 1

            if kill -0 "$pid" 2>/dev/null; then
                echo "ready" > /tmp/tuxforge-status
                echo "tuxui ready pid=$pid"
            else
                echo "ui-failed" > /tmp/tuxforge-status
                echo "ERROR: tuxui exited"
            fi

        ) >/tmp/tuxui-launch.log 2>&1 &

        exit 0
        ;;

    stop)
        if [ -f /tmp/tuxui.pid ]; then
            pid="$(cat /tmp/tuxui.pid 2>/dev/null)"

            if [ -n "$pid" ]; then
                kill "$pid" 2>/dev/null
            fi

            rm -f /tmp/tuxui.pid
        fi

        echo "stopped" > /tmp/tuxforge-status
        ;;

    restart)
        "$0" stop
        "$0" start
        ;;

    *)
        echo "usage: $0 {start|stop|restart}"
        exit 1
        ;;
esac

exit 0
"""



def align(v, n=4):
    return (v + n - 1) & ~(n - 1)


def read_u32(buf, off):
    return struct.unpack_from("<I", buf, off)[0]


def parse_newc(blob):
    entries = []
    p = 0

    while True:
        magic = blob[p:p+6]

        if magic not in (b"070701", b"070702"):
            raise RuntimeError(
                f"bad newc magic at {p:#x}: {magic!r}"
            )

        fields = []
        q = p + 6

        for _ in range(13):
            fields.append(int(blob[q:q+8], 16))
            q += 8

        (
            ino, mode, uid, gid, nlink, mtime,
            filesize, devmajor, devminor,
            rdevmajor, rdevminor, namesize, check
        ) = fields

        p = q

        name_raw = blob[p:p+namesize]
        name = name_raw[:-1].decode(
            "utf-8",
            errors="surrogateescape"
        )

        p += namesize
        p = align(p)

        data = bytes(blob[p:p+filesize])

        p += filesize
        p = align(p)

        if name == "TRAILER!!!":
            break

        entries.append({
            "magic": magic,
            "ino": ino,
            "mode": mode,
            "uid": uid,
            "gid": gid,
            "nlink": nlink,
            "mtime": mtime,
            "devmajor": devmajor,
            "devminor": devminor,
            "rdevmajor": rdevmajor,
            "rdevminor": rdevminor,
            "check": check,
            "name": name,
            "data": data,
        })

    return entries


def emit(e):
    name = e["name"].encode(
        "utf-8",
        errors="surrogateescape"
    ) + b"\0"

    data = e["data"]

    fields = (
        e["ino"],
        e["mode"],
        e["uid"],
        e["gid"],
        e["nlink"],
        e["mtime"],
        len(data),
        e["devmajor"],
        e["devminor"],
        e["rdevmajor"],
        e["rdevminor"],
        len(name),
        e["check"],
    )

    out = bytearray(e.get("magic", b"070701"))

    for v in fields:
        out += f"{v & 0xffffffff:08x}".encode()

    out += name

    while len(out) & 3:
        out += b"\0"

    out += data

    while len(out) & 3:
        out += b"\0"

    return bytes(out)


def build_newc(entries):
    out = bytearray()

    for e in entries:
        out += emit(e)

    ino = max((e["ino"] for e in entries), default=0) + 1

    out += emit({
        "magic": b"070701",
        "ino": ino,
        "mode": 0,
        "uid": 0,
        "gid": 0,
        "nlink": 1,
        "mtime": 0,
        "devmajor": 0,
        "devminor": 0,
        "rdevmajor": 0,
        "rdevminor": 0,
        "check": 0,
        "name": "TRAILER!!!",
        "data": b"",
    })

    while len(out) & 511:
        out += b"\0"

    return bytes(out)


def get(entries, name):
    for e in entries:
        if e["name"] == name:
            return e
    return None


def new_ino(entries):
    return max((e["ino"] for e in entries), default=0) + 1


def add_dir(entries, name):
    if get(entries, name):
        return

    entries.append({
        "magic": b"070701",
        "ino": new_ino(entries),
        "mode": 0o040755,
        "uid": 0,
        "gid": 0,
        "nlink": 2,
        "mtime": 0,
        "devmajor": 0,
        "devminor": 0,
        "rdevmajor": 0,
        "rdevminor": 0,
        "check": 0,
        "name": name,
        "data": b"",
    })


def put(entries, name, data, mode):
    e = get(entries, name)

    if e is None:
        e = {
            "magic": b"070701",
            "ino": new_ino(entries),
            "uid": 0,
            "gid": 0,
            "nlink": 1,
            "mtime": 0,
            "devmajor": 0,
            "devminor": 0,
            "rdevmajor": 0,
            "rdevminor": 0,
            "check": 0,
            "name": name,
        }
        entries.append(e)

    e["mode"] = mode
    e["data"] = data


def remove(entries, name):
    entries[:] = [
        e for e in entries
        if e["name"] != name
    ]


def put_symlink(entries, name, target):
    put(
        entries,
        name,
        target.encode(),
        0o120777,
    )


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def main():
    print("=== TuxForge 0.6 builder ===")

    for p in (STOCK, FBFLUSH, SPLASH, TUXREBOOT, TUXUI, SPLASH_ARGB, FONT_ALPHA):
        if not p.exists():
            die(f"missing {p}")

    stock = bytearray(STOCK.read_bytes())

    if stock[:8] != b"ANDROID!":
        die("stock/recovery.img has no ANDROID! header")

    kernel_size = read_u32(stock, 0x08)
    ramdisk_size = read_u32(stock, 0x10)
    second_size = read_u32(stock, 0x18)
    page_size = read_u32(stock, 0x24)
    dt_size = read_u32(stock, 0x28)

    print(f"kernel_size : {kernel_size:#x}")
    print(f"page_size   : {page_size:#x}")
    print(f"dt_size     : {dt_size:#x}")

    if page_size != PAGE:
        die(f"unexpected page size {page_size:#x}")

    if ramdisk_size != 0:
        die("unexpected external ramdisk")

    if second_size != 0:
        die("unexpected second image")

    kernel_off = page_size
    kernel_end = kernel_off + kernel_size

    kernel = bytearray(stock[kernel_off:kernel_end])

    if len(kernel) != kernel_size:
        die("stock recovery kernel is truncated")

    slot_end = ROOTFS_OFF + ROOTFS_SLOT

    if slot_end > len(kernel):
        die("embedded rootfs slot outside kernel")

    stock_gzip = bytes(
        kernel[ROOTFS_OFF:slot_end]
    )

    try:
        stock_cpio = gzip.decompress(stock_gzip)
    except Exception as e:
        die(f"cannot decompress embedded recovery CPIO: {e}")

    print(f"stock CPIO  : {len(stock_cpio):#x}")

    entries = parse_newc(stock_cpio)

    print(f"entries     : {len(entries)}")

    fbflush = FBFLUSH.read_bytes()
    splash = SPLASH.read_bytes()
    tuxreboot = TUXREBOOT.read_bytes()

    tuxui = TUXUI.read_bytes()
    splash_argb = SPLASH_ARGB.read_bytes()
    font_alpha = FONT_ALPHA.read_bytes()
    early_init = EARLY_INIT.read_bytes()

    if len(splash_argb) != 220 * 176 * 4:
        die(
            "splash.argb must be exactly 154880 bytes; "
            f"got {len(splash_argb)}"
        )

    if len(splash) != SPLASH_SIZE:
        die(
            f"splash.raw must be exactly {SPLASH_SIZE} bytes; "
            f"got {len(splash)}"
        )

    add_dir(entries, "opt")
    add_dir(entries, "opt/tuxforge")
    add_dir(entries, "etc/rc5.d")

    put(
        entries,
        "opt/tuxforge/fbflush",
        fbflush,
        0o100755,
    )

    put(
        entries,
        "opt/tuxforge/splash.raw",
        splash,
        0o100644,
    )

    put(
        entries,
        "opt/tuxforge/tuxreboot-bootloader",
        tuxreboot,
        0o100755,
    )

    put(
        entries,
        "opt/tuxforge/tuxui",
        tuxui,
        0o100755,
    )

    put(
        entries,
        "opt/tuxforge/splash.argb",
        splash_argb,
        0o100644,
    )

    put(
        entries,
        "opt/tuxforge/font7x11.alpha",
        font_alpha,
        0o100644,
    )

    # TuxForge 0.6 first-stage PID1 wrapper.
    # put() replaces the stock /init symlink with this regular executable.
    put(
        entries,
        "init",
        early_init,
        0o100755,
    )

    put(
        entries,
        "etc/init.d/tuxforge",
        TUXFORGE_INIT,
        0o100755,
    )

    put(
        entries,
        "etc/init.d/start_update.sh",
        START_UPDATE,
        0o100755,
    )

    put(
        entries,
        "etc/init.d/upgrade_interrupted.sh",
        UPGRADE_INTERRUPTED,
        0o100755,
    )

    # Stop using Novatel's updater as our runlevel entry point.
    remove(
        entries,
        "etc/rc5.d/S40start_update5",
    )

    put_symlink(
        entries,
        "etc/rc5.d/S40tuxforge",
        "../init.d/tuxforge",
    )

    cpio = build_newc(entries)

    gz = gzip.compress(
        cpio,
        compresslevel=9,
        mtime=0,
    )

    free = ROOTFS_SLOT - len(gz)

    print(f"new CPIO    : {len(cpio):#x}")
    print(f"new gzip    : {len(gz):#x}")
    print(f"gzip slot   : {ROOTFS_SLOT:#x}")
    print(f"free        : {free:#x}")

    if free < 0:
        die(
            f"embedded rootfs is {-free} bytes too large"
        )

    kernel[ROOTFS_OFF:slot_end] = (
        gz + bytes(free)
    )

    # QCDT starts after page-aligned kernel.
    dt_off = kernel_off + align(kernel_size, page_size)

    dt_region = bytes(
        stock[dt_off:dt_off + dt_size]
    )

    if len(dt_region) != dt_size:
        die("QCDT/DTB region truncated")

    # Preserve stock boot header.
    header = bytearray(stock[:page_size])

    # Novatel/legacy Android boot image SHA1:
    # kernel + length
    # ramdisk + length
    # second + length
    # dt region + length
    sha = hashlib.sha1()

    for blob in (
        bytes(kernel),
        b"",
        b"",
        dt_region,
    ):
        sha.update(blob)
        sha.update(struct.pack("<I", len(blob)))

    digest = sha.digest()

    # boot_img_hdr id[8]
    header[0x240:0x260] = bytes(32)
    header[0x240:0x254] = digest

    out = bytearray(header)
    out += kernel

    while len(out) % page_size:
        out += b"\0"

    if len(out) != dt_off:
        die(
            f"layout mismatch: {len(out):#x} != {dt_off:#x}"
        )

    out += dt_region

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    OUTPUT.write_bytes(out)

    # Final verification.
    embedded = gzip.decompress(
        bytes(
            kernel[
                ROOTFS_OFF:
                ROOTFS_OFF + len(gz)
            ]
        )
    )

    check_entries = parse_newc(embedded)

    required = (
        "init",
        "opt/tuxforge/fbflush",
        "opt/tuxforge/splash.raw",
        "opt/tuxforge/tuxreboot-bootloader",
        "opt/tuxforge/tuxui",
        "opt/tuxforge/splash.argb",
        "opt/tuxforge/font7x11.alpha",
        "etc/init.d/tuxforge",
        "etc/rc5.d/S40tuxforge",
        "etc/init.d/start_update.sh",
        "etc/init.d/upgrade_interrupted.sh",
    )

    for name in required:
        if get(check_entries, name) is None:
            die(f"verification failed: {name} missing")

    if get(check_entries, "etc/rc5.d/S40start_update5") is not None:
        die("verification failed: stock updater rc5 link still exists")

    link = get(check_entries, "etc/rc5.d/S40tuxforge")

    if (link["mode"] & 0o170000) != 0o120000:
        die("verification failed: S40tuxforge is not a symlink")

    if link["data"] != b"../init.d/tuxforge":
        die("verification failed: incorrect S40tuxforge target")

    if out[dt_off:dt_off + dt_size] != dt_region:
        die("QCDT/DTB changed unexpectedly")

    print()
    print("=== BUILD OK ===")
    print(f"output : {OUTPUT}")
    print(f"size   : {len(out)} ({len(out):#x})")
    print(f"boot ID: {digest.hex()}")
    print(
        "sha256 : "
        + hashlib.sha256(out).hexdigest()
    )


if __name__ == "__main__":
    main()
