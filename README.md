# TuxForge

TuxForge is an experimental recovery environment for the Novatel MiFi 6620L.

## TuxForge 0.2

Target:

- Novatel MiFi 6620L
- Qualcomm MDM9625 / MSM9625 Bengal
- ST7775 220x176 LCD

Current features:

- Boots from the stock Novatel recovery kernel
- TuxForge-modified embedded recovery userspace
- ADB w/root
- Dropbear SSH
- Stock firmware updater disabled
- Interrupted-upgrade path disabled
- 220x176 LCD framebuffer support
- 18-bpp, 660-byte stride framebuffer
- Novatel private LCD update ioctl `0x9999`
- Automatic splash output
- Reproducible recovery image builder

## Building

A stock recovery image dumped from your own MiFi is required.

Expected path:

    mifi6620l/stock/recovery.img

Build with:

    cd mifi6620l
    python3 tools/build-recovery.py

The generated image is written to:

    mifi6620l/releases/tuxforge-0.2-mifi6620l.img

## Warning

TuxForge is experimental low-level software. Prefer temporary booting before
writing anything to NAND flash.
