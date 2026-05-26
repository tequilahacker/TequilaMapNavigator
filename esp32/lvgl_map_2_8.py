# esp32/lvgl_map_2_8.py  (rewrite — không dùng LVGL)
# Hiển thị bản đồ RGB565 raw + HUD + status bar trên ILI9341 240×320
import machine, time, gc
import config
from ili9341_simple import ILI9341

# ── Màu RGB565 ──
C_BLACK   = 0x0000
C_WHITE   = 0xFFFF
C_DARK    = ILI9341.rgb(15,  15,  25)
C_BLUE    = ILI9341.rgb(0,   85,  255)
C_RED     = ILI9341.rgb(220, 30,  30)
C_YELLOW  = ILI9341.rgb(255, 200, 0)
C_GREEN   = ILI9341.rgb(30,  200, 80)
C_GRAY    = ILI9341.rgb(80,  80,  80)
C_ORANGE  = ILI9341.rgb(255, 140, 0)
C_STATUS  = ILI9341.rgb(10,  10,  20)
C_HUD     = ILI9341.rgb(12,  12,  22)

# ── Vùng màn hình ──
SCREEN_W  = 240
SCREEN_H  = 320
STATUS_H  = 28    # status bar trên cùng
HUD_H     = 40    # HUD bar dưới cùng
MAP_Y     = STATUS_H
MAP_H     = SCREEN_H - STATUS_H - HUD_H  # 252 px

class MapDisplay:
    """Quản lý toàn bộ giao diện màn hình ESP32-2432S028."""

    def __init__(self):
        self.drv = None
        self._notif_until = 0
        self._last_speed  = 0
        self._last_limit  = 0
        self._last_instr  = ""
        self._connected   = False
        self._gps_ok      = False
        self._map_buf     = None  # bytearray RGB565 của bản đồ hiện tại

    def init(self):
        try:
            spi = machine.SPI(
                1,
                baudrate=40_000_000,
                sck=machine.Pin(config.TFT_CLK),
                mosi=machine.Pin(config.TFT_MOSI),
            )
            self.drv = ILI9341(
                spi      = spi,
                cs_pin   = config.TFT_CS,
                dc_pin   = config.TFT_DC,
                rst_pin  = -1,         # RST nối với EN board, không cần GPIO
                bl_pin   = config.TFT_BL,
                width    = SCREEN_W,
                height   = SCREEN_H,
            )
            self.drv.fill(C_DARK)
            self._draw_status_bar()
            self._draw_hud()
            self._draw_map_placeholder()
            print("[Display] MapDisplay sẵn sàng (no-LVGL mode).")
            return True
        except Exception as e:
            print("[Display] Lỗi khởi tạo:", e)
            return False

    # ══════════════════════════════════════════
    #  PUBLIC API (giữ nguyên để main.py dùng)
    # ══════════════════════════════════════════

    def update_map_image(self, rgb565_bytes):
        """Nhận raw RGB565 bytes (240×252×2) từ server và vẽ lên map area."""
        if not self.drv: return
        expected = SCREEN_W * MAP_H * 2
        if len(rgb565_bytes) != expected:
            print(f"[Display] Sai kích thước ảnh: {len(rgb565_bytes)} != {expected}")
            return
        try:
            self._map_buf = rgb565_bytes
            self.drv.blit_rgb565(0, MAP_Y, SCREEN_W, MAP_H, rgb565_bytes)
        except Exception as e:
            print("[Display] blit lỗi:", e)

    def show_notification(self, text, duration_ms=3000):
        """Hiển thị thông báo popup giữa màn hình."""
        if not self.drv: return
        self._notif_until = time.ticks_ms() + duration_ms
        # Box ở giữa map area
        bx, bw, bh = 10, SCREEN_W - 20, 44
        by = MAP_Y + (MAP_H - bh) // 2
        self.drv.fill_rect(bx-2, by-2, bw+4, bh+4, C_BLUE)
        self.drv.fill_rect(bx,   by,   bw,   bh,   C_DARK)
        # Căn text
        max_chars = bw // 12  # scale-2 font = 12px per char
        line = text[:max_chars]
        tx = bx + (bw - len(line)*12) // 2
        self.drv.text(line, tx, by + 14, C_WHITE, C_DARK, scale=1)
        print("[Notif]", text)

    def clear_notification(self):
        """Xóa notification nếu đã hết thời gian."""
        if not self.drv: return
        if self._notif_until and time.ticks_ms() > self._notif_until:
            self._notif_until = 0
            # Vẽ lại vùng map nếu có buffer
            if self._map_buf:
                self.drv.blit_rgb565(0, MAP_Y, SCREEN_W, MAP_H, self._map_buf)
            else:
                self._draw_map_placeholder()

    def update_speed_limit(self, speed_kmh):
        if speed_kmh != self._last_limit:
            self._last_limit = speed_kmh
            self._draw_hud()

    def update_current_speed(self, speed_kmh):
        if speed_kmh != self._last_speed:
            self._last_speed = speed_kmh
            self._draw_hud()

    def show_camera_alert(self, distance_m, cam_type="speed"):
        msg = f"CAM {cam_type.upper()} {int(distance_m)}m"
        self._draw_top_alert(msg, C_RED)

    def clear_camera_alert(self):
        self._draw_status_bar()

    def update_navigation_instruction(self, text):
        if text != self._last_instr:
            self._last_instr = text
            self._draw_hud()

    def update_connection_status(self, wifi_ok, gps_ok):
        changed = (wifi_ok != self._connected) or (gps_ok != self._gps_ok)
        self._connected = wifi_ok
        self._gps_ok    = gps_ok
        if changed:
            self._draw_status_bar()

    def show_routes(self, routes, on_select):
        """Hiển thị danh sách tuyến đường để chọn (tối đa 3)."""
        if not self.drv: return
        # Tô nền map area
        self.drv.fill_rect(0, MAP_Y, SCREEN_W, MAP_H, C_DARK)
        self.drv.text("CHON TUYEN DUONG", 8, MAP_Y + 8, C_BLUE, C_DARK, scale=1)
        self._route_rects = []
        for i, r in enumerate(routes[:3]):
            ry = MAP_Y + 35 + i * 65
            self.drv.fill_rect(8, ry, SCREEN_W-16, 58, C_GRAY)
            self.drv.fill_rect(10, ry+2, SCREEN_W-20, 54, ILI9341.rgb(25,25,40))
            label = f"Tuyen {i+1}: {r.get('distance','?')} - {r.get('duration','?')}"
            self.drv.text(label, 14, ry+8, C_WHITE, ILI9341.rgb(25,25,40), scale=1)
            via = r.get('via', '')[:25]
            self.drv.text(via, 14, ry+26, C_YELLOW, ILI9341.rgb(25,25,40), scale=1)
            self._route_rects.append((8, ry, SCREEN_W-16, 58, i))
        self._route_callback = on_select

    def check_touch_routes(self, tx, ty):
        """Gọi từ vòng lặp main khi có touch — trả về index tuyến hoặc -1."""
        if not hasattr(self, '_route_rects'): return -1
        for (rx, ry, rw, rh, idx) in self._route_rects:
            if rx <= tx <= rx+rw and ry <= ty <= ry+rh:
                if self._route_callback:
                    self._route_callback(idx)
                self._route_rects = []
                return idx
        return -1

    def show_screen_state(self, state_text):
        if not self.drv: return
        self.drv.fill_rect(0, MAP_Y, SCREEN_W, MAP_H, C_DARK)
        cx = (SCREEN_W - len(state_text)*8) // 2
        self.drv.text(state_text, max(0,cx), MAP_Y + MAP_H//2 - 4, C_BLUE, C_DARK)

    def tick(self):
        """Gọi mỗi vòng lặp — xử lý notification hết hạn."""
        self.clear_notification()

    # ══════════════════════════════════════════
    #  PRIVATE
    # ══════════════════════════════════════════

    def _draw_status_bar(self):
        d = self.drv
        d.fill_rect(0, 0, SCREEN_W, STATUS_H, C_STATUS)
        # WiFi icon
        wifi_c = C_GREEN if self._connected else C_RED
        d.fill_rect(4, 6, 14, 14, C_STATUS)
        d.text("W", 4, 7, wifi_c, C_STATUS, scale=1)
        # GPS icon
        gps_c = C_GREEN if self._gps_ok else C_YELLOW
        d.text("G", 20, 7, gps_c, C_STATUS, scale=1)
        # Tên thiết bị
        d.text("TEQUILA MAP", 50, 7, C_BLUE, C_STATUS, scale=1)
        # Thời gian (nếu có)
        try:
            t = time.localtime()
            ts = f"{t[3]:02d}:{t[4]:02d}"
            d.text(ts, SCREEN_W - 46, 7, C_WHITE, C_STATUS, scale=1)
        except:
            pass

    def _draw_hud(self):
        d = self.drv
        y0 = SCREEN_H - HUD_H
        d.fill_rect(0, y0, SCREEN_W, HUD_H, C_HUD)
        # Tốc độ hiện tại (bên trái)
        spd = str(int(self._last_speed))
        d.text(spd, 6, y0 + 4, C_WHITE, C_HUD, scale=2)
        d.text("km/h", 6 + len(spd)*16, y0 + 12, C_GRAY, C_HUD, scale=1)
        # Giới hạn tốc độ (vòng tròn đỏ giả)
        if self._last_limit > 0:
            lx = SCREEN_W - 46
            d.fill_rect(lx, y0+2, 36, 36, C_RED)
            d.fill_rect(lx+2, y0+4, 32, 32, C_WHITE)
            ls = str(int(self._last_limit))
            d.text(ls, lx+4+(3-len(ls))*4, y0+12, C_BLACK, C_WHITE, scale=2)
        # Hướng dẫn (giữa)
        instr = self._last_instr[:16] if self._last_instr else ""
        ix = 56
        d.text(instr, ix, y0+6, C_YELLOW, C_HUD, scale=1)

    def _draw_map_placeholder(self):
        d = self.drv
        d.fill_rect(0, MAP_Y, SCREEN_W, MAP_H, C_DARK)
        d.text("Dang ket noi...", 50, MAP_Y + MAP_H//2 - 4, C_GRAY, C_DARK)

    def _draw_top_alert(self, text, color):
        d = self.drv
        d.fill_rect(0, STATUS_H, SCREEN_W, 20, color)
        d.text(text[:26], 4, STATUS_H + 4, C_WHITE, color, scale=1)
