# TuxForge — Samsung Galaxy Tab A 8.0 (2015)

Initial TuxForge reference device.

## Device

- Model: Samsung SM-T350
- Codename: gt58wifi
- SoC: Qualcomm MSM8916
- Architecture: ARM32
- Kernel family: Linux 7.x / msm8916-mainline

## TuxForge image

The known-working baseline image is named:

    tuxforge-msm8916.img

It was originally developed and tested as `boot-initramfs5.img`.

## Known-working kernel

The kernel payload is stored at:

    kernel/zImage-dtb

SHA256:

    4d2e637abc6baf17794f9376dda03a343f7414c46027224708ee89383f05045c

This is byte-for-byte identical to the kernel extracted from the known-working
`tuxforge-msm8916.img`.

## Initramfs

The initramfs under:

    initramfs/

was recovered directly from the known-working image.

The golden `/init` mounts the Linux root filesystem from:

    /dev/mmcblk0p28

The experimental Buffyboard graphical keyboard changes are NOT part of this
golden initramfs.

## Kernel configuration

    config/kernel-golden.config

is extracted directly from the known-working kernel.

Important options include:

    CONFIG_DEVTMPFS=y
    CONFIG_DEVTMPFS_MOUNT=y
    CONFIG_SERIAL_MSM=y
    CONFIG_SERIAL_MSM_CONSOLE=y
    CONFIG_USB_GADGET=y
    CONFIG_USB_CONFIGFS=y
    CONFIG_USB_CONFIGFS_SERIAL=y
    CONFIG_MMC_SDHCI_MSM=y

The golden kernel does not have UINPUT enabled:

    # CONFIG_INPUT_UINPUT is not set

Development configuration is kept separately as:

    config/kernel-experimental.config

## Android boot image parameters

Known-working parameters:

    base:           0x80000000
    kernel offset:  0x00008000
    ramdisk offset: 0x02000000
    second offset:  0x80000000
    tags offset:    0x00000100
    page size:      2048
    header version: 0
    cmdline:        console=tty0

## Status

Known working:

- ARM32 kernel boot
- Appended gt58wifi DTB
- Initramfs
- devtmpfs
- MSM serial console
- eMMC / SDHCI
- Linux root filesystem mounting

Experimental:

- UINPUT
- Laptop keyboard input
- Buffyboard graphical keyboard

## Goal

The SM-T350 / gt58wifi is the first reference device for TuxForge.

Additional Qualcomm devices and SoCs will be added as they are tested on
real hardware.
