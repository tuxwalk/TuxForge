#!/usr/bin/env python3

from pathlib import Path
import argparse
import struct
import hashlib

PAGE = 0x1000

KERNEL_ADDR = 0x00308000
RAMDISK_ADDR = 0x00308000
SECOND_ADDR = 0x01200000
TAGS_ADDR = 0x06800000

PLATFORM_ID = 0x86
VARIANT_ID = 0x11
SOC_REV = 0x00020001

QCDT_VERSION = 1
DTB_SLOT_SIZE = 0xD000


def align(v, a=PAGE):
    return (v + a - 1) & ~(a - 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kernel", required=True)
    ap.add_argument("--dtb", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    kernel = Path(args.kernel).read_bytes()
    dtb = Path(args.dtb).read_bytes()

    if dtb[:4] != b"\xd0\x0d\xfe\xed":
        raise SystemExit("DTB does not begin with FDT magic")

    if len(dtb) > DTB_SLOT_SIZE:
        raise SystemExit(
            f"DTB too large: {len(dtb):#x} > {DTB_SLOT_SIZE:#x}"
        )

    # Android boot header v0
    hdr = bytearray(PAGE)
    hdr[:8] = b"ANDROID!"

    struct.pack_into(
        "<10I",
        hdr,
        8,
        len(kernel),          # kernel_size
        KERNEL_ADDR,         # kernel_addr
        0,                   # ramdisk_size
        RAMDISK_ADDR,        # ramdisk_addr
        0,                   # second_size
        SECOND_ADDR,         # second_addr
        TAGS_ADDR,           # tags_addr
        PAGE,                # page_size
        PAGE + DTB_SLOT_SIZE,# dt_size = QCDT page + DTB slot
        0,                   # unused
    )

    cmdline = (
        b"noinitrd root=/dev/mtdblock15 rw "
        b"rootfstype=yaffs2 console=ttyHSL0,115200,n8 "
        b"androidboot.hardware=qcom ehci-hcd.park=3"
    )

    hdr[0x40:0x40 + len(cmdline)] = cmdline

    # Build complete Qualcomm DT region first.
    qcdt = bytearray(PAGE)
    qcdt[:4] = b"QCDT"
    struct.pack_into("<II", qcdt, 4, QCDT_VERSION, 1)

    struct.pack_into(
        "<5I",
        qcdt,
        12,
        PLATFORM_ID,
        VARIANT_ID,
        SOC_REV,
        PAGE,
        DTB_SLOT_SIZE,
    )

    dt_region = (
        bytes(qcdt)
        + dtb
        + b"\x00" * (DTB_SLOT_SIZE - len(dtb))
    )

    # Novatel/Qualcomm legacy boot ID:
    # SHA1(kernel + kernel_size +
    #      ramdisk + ramdisk_size +
    #      second + second_size +
    #      dt_region + dt_size)
    sha = hashlib.sha1()

    for blob in (kernel, b"", b"", dt_region):
        sha.update(blob)
        sha.update(struct.pack("<I", len(blob)))

    boot_id = sha.digest()
    hdr[0x240:0x254] = boot_id

    out = bytearray(hdr)

    # Kernel immediately after header page.
    out += kernel

    # Pad kernel to next 4 KiB page.
    out += b"\x00" * (align(len(out)) - len(out))

    qcdt_start = len(out)
    out += dt_region

    Path(args.output).write_bytes(out)

    print(f"kernel size : {len(kernel):#x}")
    print(f"kernel off  : {PAGE:#x}")
    print(f"QCDT off    : {qcdt_start:#x}")
    print(f"DTB off     : {qcdt_start + PAGE:#x}")
    print(f"DTB actual  : {len(dtb):#x}")
    print(f"DTB slot    : {DTB_SLOT_SIZE:#x}")
    print(f"dt_size     : {PAGE + DTB_SLOT_SIZE:#x}")
    print(f"boot ID     : {boot_id.hex()}")
    print(f"output size : {len(out):#x}")


if __name__ == "__main__":
    main()
