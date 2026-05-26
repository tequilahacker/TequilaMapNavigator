# esp32/ili9341_simple.py
# Driver ILI9341 đơn giản cho ESP32-2432S028 (CYD)
# Không cần LVGL — dùng SPI trực tiếp
import machine, time, framebuf

class ILI9341:
    """Driver ILI9341 tối giản: blit ảnh RGB565 + vẽ text + fill rect."""

    # ── Commands ──
    _SWRESET = 0x01
    _SLPOUT  = 0x11
    _DISPON  = 0x29
    _CASET   = 0x2A
    _PASET   = 0x2B
    _RAMWR   = 0x2C
    _MADCTL  = 0x36
    _COLMOD  = 0x3A

    def __init__(self, spi, cs_pin, dc_pin, rst_pin=-1, bl_pin=-1,
                 width=240, height=320):
        self.spi    = spi
        self.cs     = machine.Pin(cs_pin, machine.Pin.OUT, value=1)
        self.dc     = machine.Pin(dc_pin, machine.Pin.OUT, value=0)
        self.width  = width
        self.height = height

        # Reset (optional)
        if rst_pin >= 0:
            self.rst = machine.Pin(rst_pin, machine.Pin.OUT, value=1)
            self.rst.value(0); time.sleep_ms(15)
            self.rst.value(1); time.sleep_ms(120)
        else:
            time.sleep_ms(150)

        # Backlight
        if bl_pin >= 0:
            self.bl = machine.Pin(bl_pin, machine.Pin.OUT, value=1)
        else:
            self.bl = None

        self._init_regs()
        print("[Display] ILI9341 khởi tạo xong.")

    # ── Low-level ──
    def _cmd(self, c):
        self.dc.value(0); self.cs.value(0)
        self.spi.write(bytes([c]))
        self.cs.value(1)

    def _data(self, d):
        self.dc.value(1); self.cs.value(0)
        self.spi.write(d if isinstance(d, (bytes, bytearray)) else bytes([d]))
        self.cs.value(1)

    def _init_regs(self):
        seq = [
            (0xEF, b'\x03\x80\x02'),
            (0xCF, b'\x00\xC1\x30'),
            (0xED, b'\x64\x03\x12\x81'),
            (0xE8, b'\x85\x00\x78'),
            (0xCB, b'\x39\x2C\x00\x34\x02'),
            (0xF7, b'\x20'),
            (0xEA, b'\x00\x00'),
            (0xC0, b'\x23'),          # Power control 1
            (0xC1, b'\x10'),          # Power control 2
            (0xC5, b'\x3E\x28'),      # VCOM control 1
            (0xC7, b'\x86'),          # VCOM control 2
            (0x36, b'\x48'),          # MADCTL: portrait, BGR
            (0x3A, b'\x55'),          # COLMOD: 16-bit RGB565
            (0xB1, b'\x00\x18'),      # Frame rate ~70Hz
            (0xB6, b'\x08\x82\x27'), # Display function
            (0xF2, b'\x00'),          # Gamma disable 3G
            (0x26, b'\x01'),          # Gamma curve 1
            (0xE0, bytes([0x0F,0x31,0x2B,0x0C,0x0E,0x08,
                          0x4E,0xF1,0x37,0x07,0x10,0x03,0x0E,0x09,0x00])),
            (0xE1, bytes([0x00,0x0E,0x14,0x03,0x11,0x07,
                          0x31,0xC1,0x48,0x08,0x0F,0x0C,0x31,0x36,0x0F])),
        ]
        for cmd, data in seq:
            self._cmd(cmd); self._data(data)
        self._cmd(0x11); time.sleep_ms(120)  # Sleep out
        self._cmd(0x29)                       # Display on

    # ── Drawing API ──
    def set_window(self, x0, y0, x1, y1):
        self._cmd(self._CASET)
        self._data(bytes([x0>>8, x0&0xFF, x1>>8, x1&0xFF]))
        self._cmd(self._PASET)
        self._data(bytes([y0>>8, y0&0xFF, y1>>8, y1&0xFF]))
        self._cmd(self._RAMWR)

    def blit_rgb565(self, x, y, w, h, data):
        """Vẽ ảnh raw RGB565 bytes lên màn hình."""
        self.set_window(x, y, x+w-1, y+h-1)
        self.dc.value(1); self.cs.value(0)
        # Gửi theo chunk 4096 bytes để tránh timeout SPI
        mv = memoryview(data)
        chunk = 4096
        for i in range(0, len(mv), chunk):
            self.spi.write(mv[i:i+chunk])
        self.cs.value(1)

    def fill_rect(self, x, y, w, h, color):
        """Tô màu một hình chữ nhật. color = RGB565 int."""
        self.set_window(x, y, x+w-1, y+h-1)
        hi, lo = color >> 8, color & 0xFF
        buf = bytes([hi, lo] * 128)  # 128 pixels/chunk
        self.dc.value(1); self.cs.value(0)
        total = w * h; done = 0
        while done < total:
            n = min(128, total - done)
            self.spi.write(buf[:n*2])
            done += n
        self.cs.value(1)

    def fill(self, color):
        self.fill_rect(0, 0, self.width, self.height, color)

    def text(self, s, x, y, color, bg=0x0000, scale=1):
        """Vẽ text dùng framebuf 8×8 built-in font, scale 1 hoặc 2."""
        fw, fh = 8 * scale, 8 * scale
        buf = bytearray(fw * fh * 2)
        fb  = framebuf.FrameBuffer(buf, fw, fh, framebuf.RGB565)
        for i, ch in enumerate(s):
            fb.fill(bg)
            if scale == 1:
                fb.text(ch, 0, 0, color)
            else:
                # Scale 2× bằng cách vẽ vào 8×8 rồi scale lên
                tmp_buf = bytearray(8 * 8 * 2)
                tmp_fb  = framebuf.FrameBuffer(tmp_buf, 8, 8, framebuf.RGB565)
                tmp_fb.fill(bg)
                tmp_fb.text(ch, 0, 0, color)
                for py in range(8):
                    for px in range(8):
                        px_color = (tmp_buf[(py*8+px)*2]<<8) | tmp_buf[(py*8+px)*2+1]
                        for sy in range(scale):
                            for sx in range(scale):
                                ox = px*scale + sx
                                oy = py*scale + sy
                                idx = (oy * fw + ox) * 2
                                buf[idx]   = px_color >> 8
                                buf[idx+1] = px_color & 0xFF
            self.blit_rgb565(x + i * fw, y, fw, fh, buf)

    @staticmethod
    def rgb(r, g, b):
        """RGB888 → RGB565."""
        return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
