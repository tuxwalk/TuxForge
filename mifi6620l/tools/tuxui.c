typedef unsigned char  u8;
typedef unsigned short u16;
typedef unsigned int   u32;

#define FB_W       220
#define FB_H       176
#define FB_STRIDE  660
#define FB_SIZE    (FB_STRIDE * FB_H)

#define EV_KEY      1
#define KEY_LEFT    105
#define KEY_RIGHT   106
#define KEY_POWER   116
#define KEY_SELECT  353
#define KEY_RESET   408

#define SYS_POLL    168
#define POLLIN      0x0001

#define SYS_EXIT    1
#define SYS_READ    3
#define SYS_WRITE   4
#define SYS_OPEN    5
#define SYS_CLOSE   6
#define SYS_LSEEK   19
#define SYS_SYNC    36
#define SYS_IOCTL   54
#define SYS_REBOOT  88

#define REBOOT_MAGIC1       0xfee1dead
#define REBOOT_MAGIC2       0x28121969
#define REBOOT_RESTART      0x01234567
#define REBOOT_RESTART2     0xa1b2c3d4

struct pollfd32 {
    int fd;
    short events;
    short revents;
};

struct input_event32 {
    u32 sec;
    u32 usec;
    u16 type;
    u16 code;
    u32 value;
};

struct lcd_rect {
    u32 x;
    u32 y;
    u32 width;
    u32 height;
};

/*
 * TuxForge software framebuffer:
 *
 *     0xAARRGGBB
 *
 * The UI stays at 32-bit color until push_fb(), where it is
 * dithered down to the MiFi's native 18-bit BGR framebuffer.
 */
static u32 screen[FB_W * FB_H];
static u8 hwfb[FB_SIZE];

static const u8 bayer4[16] = {
     0,  8,  2, 10,
    12,  4, 14,  6,
     3, 11,  1,  9,
    15,  7, 13,  5
};


#define FONT_W       7
#define FONT_H       11
#define FONT_FIRST   32
#define FONT_LAST    126
#define FONT_COUNT   (FONT_LAST - FONT_FIRST + 1)
#define FONT_BYTES   (FONT_COUNT * FONT_W * FONT_H)

static u8 font_alpha[FONT_BYTES];
static int font_ready;

static struct lcd_rect full_rect = {
    0, 0, FB_W, FB_H
};

static const char bootloader[] = "bootloader";

/* ------------------------------------------------------------------ */
/* ARM Linux syscalls                                                  */
/* ------------------------------------------------------------------ */

static int sc0(int nr)
{
    register int r0 asm("r0");
    register int r7 asm("r7") = nr;

    asm volatile(
        "svc 0"
        : "=r"(r0)
        : "r"(r7)
        : "memory"
    );

    return r0;
}

static int sc1(int nr, int a)
{
    register int r0 asm("r0") = a;
    register int r7 asm("r7") = nr;

    asm volatile(
        "svc 0"
        : "+r"(r0)
        : "r"(r7)
        : "memory"
    );

    return r0;
}

static int sc3(int nr, int a, int b, int c)
{
    register int r0 asm("r0") = a;
    register int r1 asm("r1") = b;
    register int r2 asm("r2") = c;
    register int r7 asm("r7") = nr;

    asm volatile(
        "svc 0"
        : "+r"(r0)
        : "r"(r1), "r"(r2), "r"(r7)
        : "memory"
    );

    return r0;
}

static int sc4(int nr, int a, int b, int c, int d)
{
    register int r0 asm("r0") = a;
    register int r1 asm("r1") = b;
    register int r2 asm("r2") = c;
    register int r3 asm("r3") = d;
    register int r7 asm("r7") = nr;

    asm volatile(
        "svc 0"
        : "+r"(r0)
        : "r"(r1), "r"(r2), "r"(r3), "r"(r7)
        : "memory"
    );

    return r0;
}

static int xopen(const char *p, int flags)
{
    return sc3(
        SYS_OPEN,
        (int)(u32)p,
        flags,
        0
    );
}

static int xread(int fd, void *p, int n)
{
    return sc3(
        SYS_READ,
        fd,
        (int)(u32)p,
        n
    );
}

static int xwrite(int fd, const void *p, int n)
{
    return sc3(
        SYS_WRITE,
        fd,
        (int)(u32)p,
        n
    );
}

static int xclose(int fd)
{
    return sc1(SYS_CLOSE, fd);
}


static void led_off(void)
{
    static const char zero[] = "0\n";
    int fd;

    fd = xopen(
        "/sys/class/leds/blue_led/brightness",
        1
    );

    if (fd < 0)
        return;

    xwrite(
        fd,
        zero,
        sizeof(zero) - 1
    );

    xclose(fd);
}

static int xlseek(int fd, int off, int whence)
{
    return sc3(SYS_LSEEK, fd, off, whence);
}

static int xioctl(int fd, int cmd, void *arg)
{
    return sc3(
        SYS_IOCTL,
        fd,
        cmd,
        (int)(u32)arg
    );
}

static void xexit(int status)
{
    sc1(SYS_EXIT, status);

    for (;;)
        ;
}

/* ------------------------------------------------------------------ */
/* Tiny 5x7 TuxForge font                                             */
/* ------------------------------------------------------------------ */

struct glyph {
    char c;
    u8 row[7];
};

static const struct glyph font[] = {
    {' ',{0,0,0,0,0,0,0}},
    {'A',{14,17,17,31,17,17,17}},
    {'B',{30,17,17,30,17,17,30}},
    {'C',{14,17,16,16,16,17,14}},
    {'D',{30,17,17,17,17,17,30}},
    {'E',{31,16,16,30,16,16,31}},
    {'F',{31,16,16,30,16,16,16}},
    {'G',{14,17,16,23,17,17,15}},
    {'H',{17,17,17,31,17,17,17}},
    {'I',{14,4,4,4,4,4,14}},
    {'J',{7,2,2,2,18,18,12}},
    {'K',{17,18,20,24,20,18,17}},
    {'L',{16,16,16,16,16,16,31}},
    {'M',{17,27,21,21,17,17,17}},
    {'N',{17,25,21,19,17,17,17}},
    {'O',{14,17,17,17,17,17,14}},
    {'P',{30,17,17,30,16,16,16}},
    {'Q',{14,17,17,17,21,18,13}},
    {'R',{30,17,17,30,20,18,17}},
    {'S',{15,16,16,14,1,1,30}},
    {'T',{31,4,4,4,4,4,4}},
    {'U',{17,17,17,17,17,17,14}},
    {'V',{17,17,17,17,17,10,4}},
    {'W',{17,17,17,21,21,21,10}},
    {'X',{17,17,10,4,10,17,17}},
    {'Y',{17,17,10,4,4,4,4}},
    {'Z',{31,1,2,4,8,16,31}},

    {'0',{14,17,19,21,25,17,14}},
    {'1',{4,12,4,4,4,4,14}},
    {'2',{14,17,1,2,4,8,31}},
    {'3',{30,1,1,14,1,1,30}},
    {'4',{2,6,10,18,31,2,2}},
    {'5',{31,16,16,30,1,1,30}},
    {'6',{14,16,16,30,17,17,14}},
    {'7',{31,1,2,4,8,8,8}},
    {'8',{14,17,17,14,17,17,14}},
    {'9',{14,17,17,15,1,1,14}},

    {'-',{0,0,0,14,0,0,0}},
    {':',{0,4,0,0,4,0,0}},
    {'.',{0,0,0,0,0,0,4}},
    {'/',{1,2,2,4,8,8,16}},
    {'[',{14,8,8,8,8,8,14}},
    {']',{14,2,2,2,2,2,14}},
    {'>',{16,8,4,2,4,8,16}},
};

static const u8 *glyph_for(char c)
{
    u32 i;

    for (i = 0; i < sizeof(font) / sizeof(font[0]); i++) {
        if (font[i].c == c)
            return font[i].row;
    }

    return font[0].row;
}

/* ------------------------------------------------------------------ */
/* Framebuffer                                                         */
/* ------------------------------------------------------------------ */

static void pixel(
    int x,
    int y,
    u8 b,
    u8 g,
    u8 r
)
{
    if (x < 0 || y < 0 || x >= FB_W || y >= FB_H)
        return;

    screen[y * FB_W + x] =
        0xff000000u |
        ((u32)r << 16) |
        ((u32)g << 8) |
        (u32)b;
}


static void fill_rect(
    int x,
    int y,
    int w,
    int h,
    u8 b,
    u8 g,
    u8 r
)
{
    int xx;
    int yy;

    for (yy = y; yy < y + h; yy++) {
        for (xx = x; xx < x + w; xx++)
            pixel(xx, yy, b, g, r);
    }
}


static void blend_pixel(
    int x,
    int y,
    u8 r,
    u8 g,
    u8 b,
    u8 a
)
{
    u32 old;
    u32 idx;
    u32 or_;
    u32 og;
    u32 ob;
    u32 nr;
    u32 ng;
    u32 nb;

    if (x < 0 || y < 0 || x >= FB_W || y >= FB_H)
        return;

    idx = y * FB_W + x;
    old = screen[idx];

    ob  = old & 255;
    og  = (old >> 8) & 255;
    or_ = (old >> 16) & 255;

    /*
     * Divide by 255 without libgcc division.
     *
     * For x in our range:
     *   x / 255 ~= (x + 128 + ((x + 128) >> 8)) >> 8
     */
    nr = r * a + or_ * (255 - a);
    ng = g * a + og  * (255 - a);
    nb = b * a + ob  * (255 - a);

    nr = (nr + 128 + ((nr + 128) >> 8)) >> 8;
    ng = (ng + 128 + ((ng + 128) >> 8)) >> 8;
    nb = (nb + 128 + ((nb + 128) >> 8)) >> 8;

    screen[idx] =
        0xff000000u |
        (nr << 16) |
        (ng << 8) |
        nb;
}


static void fill_rect_alpha(
    int x,
    int y,
    int w,
    int h,
    u8 r,
    u8 g,
    u8 b,
    u8 a
)
{
    int xx;
    int yy;

    for (yy = y; yy < y + h; yy++) {
        for (xx = x; xx < x + w; xx++)
            blend_pixel(xx, yy, r, g, b, a);
    }
}


static void load_font(void)
{
    int fd;
    int off;
    int n;

    font_ready = 0;

    fd = xopen(
        "/opt/tuxforge/font7x11.alpha",
        0
    );

    if (fd < 0)
        return;

    off = 0;

    while (off < FONT_BYTES) {
        n = xread(
            fd,
            font_alpha + off,
            FONT_BYTES - off
        );

        if (n <= 0)
            break;

        off += n;
    }

    xclose(fd);

    if (off == FONT_BYTES)
        font_ready = 1;
}


static void draw_char(
    int x,
    int y,
    char c,
    int scale,
    u8 b,
    u8 g,
    u8 r
)
{
    int code = (unsigned char)c;
    int gx;
    int gy;
    int sx;
    int sy;
    int base;
    u8 a;

    if (!font_ready)
        return;

    if (code < FONT_FIRST || code > FONT_LAST)
        code = '?';

    base =
        (code - FONT_FIRST) *
        FONT_W *
        FONT_H;

    for (gy = 0; gy < FONT_H; gy++) {
        for (gx = 0; gx < FONT_W; gx++) {
            a = font_alpha[
                base +
                gy * FONT_W +
                gx
            ];

            /*
             * The Novatel/ST7775 path gives colored fringes with
             * intermediate grayscale AA values. Use the atlas only
             * as a coverage mask and render pure-white pixels.
             */
            if (a < 96)
                continue;

            for (sy = 0; sy < scale; sy++) {
                for (sx = 0; sx < scale; sx++) {
                    pixel(
                        x + gx * scale + sx,
                        y + gy * scale + sy,
                        255, 255, 255
                    );
                }
            }
        }
    }
}


static void draw_text(
    int x,
    int y,
    const char *s,
    int scale
)
{
    while (*s) {
        draw_char(
            x,
            y,
            *s,
            scale,
            255, 255, 255
        );

        x += (FONT_W + 1) * scale;
        s++;
    }
}


static void clear_black(void)
{
    u32 i;

    for (i = 0; i < FB_W * FB_H; i++)
        screen[i] = 0xff000000u;
}


static void load_background(void)
{
    int fd;
    int off;
    int n;
    int total = (int)sizeof(screen);

    clear_black();

    fd = xopen(
        "/opt/tuxforge/splash.argb",
        0
    );

    if (fd < 0)
        return;

    off = 0;

    while (off < total) {
        n = xread(
            fd,
            ((u8 *)screen) + off,
            total - off
        );

        if (n <= 0)
            break;

        off += n;
    }

    xclose(fd);
}


/*
 * Convert one 8-bit channel to the LCD's 6-bit channel.
 *
 * Rather than simply throwing away the lowest two bits,
 * use a 4x4 Bayer matrix to preserve apparent gradients.
 */
static u8 quantize6(u8 v, int x, int y)
{
    int base;
    int remainder;
    int threshold;

    base = v >> 2;
    remainder = v & 3;

    threshold =
        bayer4[((y & 3) << 2) | (x & 3)] >> 2;

    if (remainder > threshold && base < 63)
        base++;

    return (u8)base;
}


static void convert_to_lcd(void)
{
    int x;
    int y;
    u32 c;
    u8 r;
    u8 g;
    u8 b;
    u32 d;

    for (y = 0; y < FB_H; y++) {
        for (x = 0; x < FB_W; x++) {
            c = screen[y * FB_W + x];

            b = (u8)(c);
            g = (u8)(c >> 8);
            r = (u8)(c >> 16);

            d = y * FB_STRIDE + x * 3;

            /*
             * Novatel framebuffer storage order:
             *
             *     B G R
             *
             * with each channel in the range 0..63.
             */
            hwfb[d + 0] = quantize6(b, x, y);
            hwfb[d + 1] = quantize6(g, x, y);
            hwfb[d + 2] = quantize6(r, x, y);
        }
    }
}


static void push_fb(int fd)
{
    int off;
    int n;

    convert_to_lcd();

    xlseek(fd, 0, 0);

    off = 0;

    while (off < FB_SIZE) {
        n = xwrite(
            fd,
            hwfb + off,
            FB_SIZE - off
        );

        if (n <= 0)
            break;

        off += n;
    }

    xioctl(
        fd,
        0x9999,
        &full_rect
    );
}


/* ------------------------------------------------------------------ */
/* UI                                                                  */
/* ------------------------------------------------------------------ */

static int selected;
static int info_page;
static int confirm;

static const char *last_event = "READY";

static const char *items[] = {
    "BOOT",
    "SYSTEM INFO",
    "BOOTLOADER"
};

static void draw_log_panel(void)
{
    /*
     * Preserve the upper logo region.
     * Lower screen becomes TuxForge's controlled console/menu.
     */
    fill_rect_alpha(
        0, 52,
        FB_W, FB_H - 52,
        0, 0, 0,
        255
    );

    draw_text(8, 60, "TUXFORGE 1.0", 1);

    draw_text(8, 70, "[OK] LCD 220X176X18", 1);
    draw_text(8, 80, "[OK] INPUT GPIO-KEYS", 1);
    draw_text(8, 90, "[OK] ADB / SSH", 1);

    draw_text(8, 102, "L/R:NAV  PWR:BACK", 1);
    draw_text(8, 112, "SELECT:CHOOSE RESET:MAIN", 1);
}

static void draw_menu(void)
{
    int i;

    draw_log_panel();

    for (i = 0; i < 3; i++) {
        int y = 126 + i * 10;

        if (i == selected)
            draw_text(8, y, ">", 1);

        draw_text(
            20,
            y,
            items[i],
            1
        );
    }

    if (confirm) {
        draw_text(
            8,
            158,
            "SELECT AGAIN TO CONFIRM",
            1
        );
    } else {
        draw_text(
            8,
            158,
            last_event,
            1
        );
    }
}

static void draw_info(void)
{
    fill_rect_alpha(
        0, 52,
        FB_W, FB_H - 52,
        0, 0, 0,
        255
    );

    draw_text(8, 60, "SYSTEM INFO", 1);
    draw_text(8, 74, "NOVATEL MIFI 6620L", 1);
    draw_text(8, 84, "QUALCOMM MDM9625", 1);
    draw_text(8, 94, "KERNEL 3.4", 1);
    draw_text(8, 104, "LCD 220X176X18", 1);
    draw_text(8, 114, "FB /DEV/FB0", 1);
    draw_text(8, 124, "INPUT /DEV/INPUT/EVENT1", 1);
    draw_text(8, 144, "SELECT/POWER: BACK", 1);
}

static void redraw(int fbfd)
{
    load_background();

    if (info_page)
        draw_info();
    else
        draw_menu();

    push_fb(fbfd);
}

static void reboot_normal(int fbfd)
{
    load_background();

    fill_rect_alpha(
        0, 52,
        FB_W, FB_H - 52,
        0, 0, 0,
        255
    );

    draw_text(8, 72, "TUXFORGE", 2);
    draw_text(8, 100, "BOOTING", 1);

    push_fb(fbfd);

    led_off();
    sc0(SYS_SYNC);

    sc4(
        SYS_REBOOT,
        REBOOT_MAGIC1,
        REBOOT_MAGIC2,
        REBOOT_RESTART,
        0
    );

    last_event = "BOOT FAILED";
    confirm = 0;
    redraw(fbfd);
}

static void reboot_bootloader(int fbfd)
{
    load_background();

    fill_rect_alpha(
        0, 52,
        FB_W, FB_H - 52,
        0, 0, 0,
        255
    );

    draw_text(8, 72, "TUXFORGE", 2);
    draw_text(8, 100, "BOOTLOADER", 1);

    push_fb(fbfd);

    led_off();
    sc0(SYS_SYNC);

    sc4(
        SYS_REBOOT,
        REBOOT_MAGIC1,
        REBOOT_MAGIC2,
        REBOOT_RESTART2,
        (int)(u32)bootloader
    );

    last_event = "BOOTLOADER FAILED";
    confirm = 0;
    redraw(fbfd);
}

/* ------------------------------------------------------------------ */

void _start(void)
{
    int fbfd;
    int inputfd;
    int powerfd;
    int eventfd;
    struct pollfd32 pfds[2];
    struct input_event32 ev;

    selected = 0;
    info_page = 0;
    confirm = 0;

    load_font();

    fbfd = xopen(
        "/dev/fb0",
        2
    );

    if (fbfd < 0)
        xexit(10);

    inputfd = xopen(
        "/dev/input/event1",
        0
    );

    if (inputfd < 0)
        xexit(11);

    powerfd = xopen(
        "/dev/input/event0",
        0
    );

    if (powerfd < 0)
        xexit(12);

    pfds[0].fd = powerfd;
    pfds[0].events = POLLIN;
    pfds[0].revents = 0;

    pfds[1].fd = inputfd;
    pfds[1].events = POLLIN;
    pfds[1].revents = 0;

    redraw(fbfd);

    for (;;) {
        int n;
        int pr;

        eventfd = -1;

        pr = sc3(
            SYS_POLL,
            (int)(u32)pfds,
            2,
            -1
        );

        if (pr <= 0)
            continue;

        /*
         * POWER gets priority if both devices have an event
         * queued simultaneously. event1 remains queued and will
         * be handled on the next loop.
         */
        if (pfds[0].revents & POLLIN)
            eventfd = powerfd;
        else if (pfds[1].revents & POLLIN)
            eventfd = inputfd;

        if (eventfd < 0)
            continue;

        n = xread(
            eventfd,
            &ev,
            sizeof(ev)
        );

        if (n != sizeof(ev))
            continue;

        if (ev.type != EV_KEY)
            continue;

        /* Initial press only. */
        if (ev.value != 1)
            continue;

        /*
         * POWER lives on event0.
         *
         * Short press means BACK/CANCEL:
         *   - leave System Info
         *   - cancel boot/bootloader confirmation
         *   - no destructive action from the main menu
         */
        if (eventfd == powerfd) {
            if (ev.code != KEY_POWER)
                continue;

            last_event = "KEY: POWER";

            if (info_page)
                info_page = 0;

            if (confirm)
                confirm = 0;

            redraw(fbfd);
            continue;
        }

        /*
         * RESET is a safe MAIN MENU key.
         *
         * It deliberately does NOT reboot the device.
         */
        if (ev.code == KEY_RESET) {
            last_event = "KEY: RESET";
            selected = 0;
            info_page = 0;
            confirm = 0;
            redraw(fbfd);
            continue;
        }

        if (ev.code == KEY_RIGHT) {
            last_event = "KEY: RIGHT";

            if (info_page) {
                info_page = 0;
            } else {
                confirm = 0;

                selected++;

                if (selected >= 3)
                    selected = 0;
            }

            redraw(fbfd);
            continue;
        }

        /*
         * LEFT remains supported on units where the button works,
         * but TuxForge never requires it.
         */
        if (ev.code == KEY_LEFT) {
            last_event = "KEY: LEFT";

            if (info_page) {
                info_page = 0;
            } else {
                confirm = 0;

                selected--;

                if (selected < 0)
                    selected = 2;
            }

            redraw(fbfd);
            continue;
        }

        if (ev.code == KEY_SELECT) {
            last_event = "KEY: SELECT";

            if (info_page) {
                info_page = 0;
                redraw(fbfd);
                continue;
            }

            if (selected == 1) {
                info_page = 1;
                confirm = 0;
                redraw(fbfd);
                continue;
            }

            /*
             * Destructive-ish navigation gets a second press
             * confirmation to prevent accidental reboots.
             */
            if (!confirm) {
                confirm = 1;
                redraw(fbfd);
                continue;
            }

            if (selected == 2)
                reboot_bootloader(fbfd);

            if (selected == 0)
                reboot_normal(fbfd);
        }
    }
}
