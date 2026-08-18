#!/bin/sh

echo "================================"
echo "          TuxForge"
echo "       MiFi 6620L"
echo "================================"

if [ -c /dev/fb0 ]; then
    dd if=/opt/tuxforge/splash.raw \
       of=/dev/fb0 \
       bs=660 count=176 2>/dev/null

    /opt/tuxforge/fbflush
fi

# Stock firmware updater deliberately disabled.
exit 0
