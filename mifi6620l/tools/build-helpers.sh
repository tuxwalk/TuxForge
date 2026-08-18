#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

PREFIX="${CROSS_COMPILE:-arm-linux-gnueabi-}"
AS="${PREFIX}as"
LD="${PREFIX}ld"

BUILD="$ROOT/build/helpers"
DEST="$ROOT/tuxforge-root/opt/tuxforge"

mkdir -p "$BUILD" "$DEST"

"$AS" \
    -o "$BUILD/fbflush.o" \
    "$ROOT/tools/fbflush.S"

"$LD" \
    -o "$BUILD/fbflush" \
    "$BUILD/fbflush.o"

"$AS" \
    -o "$BUILD/tuxreboot-bootloader.o" \
    "$ROOT/tools/tuxreboot-bootloader.S"

"$LD" \
    -o "$BUILD/tuxreboot-bootloader" \
    "$BUILD/tuxreboot-bootloader.o"

install -m 0755 \
    "$BUILD/fbflush" \
    "$DEST/fbflush"

install -m 0755 \
    "$BUILD/tuxreboot-bootloader" \
    "$DEST/tuxreboot-bootloader"

echo "Built:"
file \
    "$DEST/fbflush" \
    "$DEST/tuxreboot-bootloader"
