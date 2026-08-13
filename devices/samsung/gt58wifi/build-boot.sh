#!/bin/sh
set -eu

HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(CDPATH= cd -- "$HERE/../../.." && pwd)"

OUT="$ROOT/out/gt58wifi"

KERNEL="$HERE/kernel/zImage-dtb"
INITRAMFS="$HERE/initramfs"

mkdir -p "$OUT"

echo "[TuxForge] Packing gt58wifi initramfs..."

(
    cd "$INITRAMFS"
    find . -print0 |
        cpio --null -o --format=newc 2>/dev/null |
        gzip -9
) > "$OUT/initramfs.cpio.gz"

echo "[TuxForge] Building MSM8916 boot image..."

mkbootimg \
    --kernel "$KERNEL" \
    --ramdisk "$OUT/initramfs.cpio.gz" \
    --base 0x80000000 \
    --kernel_offset 0x00008000 \
    --ramdisk_offset 0x02000000 \
    --second_offset 0x80000000 \
    --tags_offset 0x00000100 \
    --pagesize 2048 \
    --header_version 0 \
    --cmdline "console=tty0" \
    --output "$OUT/tuxforge-smt350-v0.1.0.img"

echo
echo "[TuxForge] Built:"
ls -lh "$OUT/tuxforge-smt350-v0.1.0.img"
