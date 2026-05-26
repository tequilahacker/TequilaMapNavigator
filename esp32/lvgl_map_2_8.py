# esp32/lvgl_map_2_8.py
# Google Maps JPEG Viewer cho màn hình ESP32 2.8" Portrait (240×320)
# Thay thế vector map bằng JPEG thật từ Google Maps Static API
#
# Layout Portrait 240×320:
#  ┌──────────────────────┐  240px
#  │  [GPS] [WiFi] [Bat]  │   28px ← status bar
#  ├──────────────────────┤
#  │                      │
#  │  Google Maps JPEG    │  252px ← map area (320-28-40=252)
#  │  route xanh + marker │
#  │                      │
#  ├──────────────────────┤
#  │ 🚀 45km/h  ➡ 100m  │   40px ← HUD bar
#  └──────────────────────┘

import lvgl as lv
import config

# Kích thước layout portrait
_W   = 240   # width
_H   = 320   # height
_SB  = 28    # status bar height (top)
_HUD = 40    # HUD bar height (bottom)
_MAP = _H - _SB - _HUD  # bản đồ = 252px

class LVGLMapScreen:
    """Màn hình chính: Google Maps JPEG + HUD bar + Status bar.
    
    Nguyên lý hoạt động:
    - Server gọi Google Maps Static API → trả PNG bytes
    - ESP32 nhận bytes → lưu /map.png → set lv.img src
    - Cập nhật mỗi MAP_UPDATE_SEC giây (bản đồ follow vị trí user)
    """
    
    def __init__(self):
        # ── Màu sắc ──
        self.C_BG     = lv.color_make(15,  15,  25)   # xanh đen nền
        self.C_PANEL  = lv.color_make(22,  26,  38)   # panel tối
        self.C_TEXT   = lv.color_make(230, 230, 230)  # trắng nhẹ
        self.C_GREEN  = lv.color_make(39,  174, 96)   # xanh lá
        self.C_RED    = lv.color_make(231, 76,  60)   # đỏ cảnh báo
        self.C_ORANGE = lv.color_make(230, 126, 34)   # cam
        self.C_BLUE   = lv.color_make(41,  128, 185)  # xanh dương info
        self.C_LIMIT  = lv.color_make(220, 30,  30)   # đỏ biển tốc độ
        
        # ── State ──
        self._speed        = 0
        self._speed_limit  = 60
        self._instruction  = "Xin chào Ngài Tequila"
        self._turn_dist    = 0
        self._eta_min      = 0
        self._wifi_ok      = False
        self._gps_ok       = False
        self._battery      = 100
        self._map_file     = "/map.png"
        self._has_map      = False
        self._notif_timer  = None
        self._flash_state  = True
        
        # ── Khởi tạo UI ──
        self.scr = lv.obj()
        self.scr.set_style_bg_color(self.C_BG, 0)
        lv.scr_load(self.scr)
        
        self._build_status_bar()
        self._build_map_area()
        self._build_hud_bar()
        self._build_notification_layer()
        self._build_route_select_panel()
        
        # Flash timer 1Hz cho camera warning
        self._flash_timer = lv.timer_create(self._on_flash_tick, 1000, None)
    
    # ═══════════════════════════════════════════════════════
    # BUILD UI
    # ═══════════════════════════════════════════════════════
    
    def _build_status_bar(self):
        """Thanh trạng thái trên cùng 28px: WiFi | GPS | Battery."""
        sb = lv.obj(self.scr)
        sb.set_size(_W, _SB)
        sb.align(lv.ALIGN.TOP_MID, 0, 0)
        sb.set_style_bg_color(self.C_PANEL, 0)
        sb.set_style_border_width(0, 0)
        sb.set_style_radius(0, 0)
        sb.set_style_pad_all(0, 0)
        self._sb = sb
        
        # WiFi icon
        self._wifi_lbl = lv.label(sb)
        self._wifi_lbl.align(lv.ALIGN.LEFT_MID, 6, 0)
        self._wifi_lbl.set_text("WiFi")
        self._wifi_lbl.set_style_text_color(self.C_RED, 0)
        
        # GPS label giữa
        self._gps_lbl = lv.label(sb)
        self._gps_lbl.align(lv.ALIGN.CENTER, 0, 0)
        self._gps_lbl.set_text("GPS: Chờ...")
        self._gps_lbl.set_style_text_color(self.C_TEXT, 0)
        
        # Battery phải
        self._bat_lbl = lv.label(sb)
        self._bat_lbl.align(lv.ALIGN.RIGHT_MID, -6, 0)
        self._bat_lbl.set_text("100%")
        self._bat_lbl.set_style_text_color(self.C_GREEN, 0)
    
    def _build_map_area(self):
        """Vùng bản đồ 240×252: hiển thị JPEG từ Google Maps Static API."""
        ma = lv.obj(self.scr)
        ma.set_size(_W, _MAP)
        ma.align(lv.ALIGN.TOP_MID, 0, _SB)
        ma.set_style_bg_color(self.C_BG, 0)
        ma.set_style_border_width(0, 0)
        ma.set_style_radius(0, 0)
        ma.set_style_pad_all(0, 0)
        ma.set_style_clip_corner(True, 0)
        self._map_cont = ma
        
        # ── Placeholder: logo Tequila Map khi chưa có ảnh ──
        self._placeholder = lv.label(ma)
        self._placeholder.set_text("🗺  Tequila Map\n\nĐang tải bản đồ...\nKết nối WiFi iPhone")
        self._placeholder.set_style_text_color(self.C_TEXT, 0)
        self._placeholder.align(lv.ALIGN.CENTER, 0, 0)
        self._placeholder.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        
        # ── Image widget cho JPEG Google Maps ──
        self._map_img = lv.img(ma)
        self._map_img.set_size(_W, _MAP)
        self._map_img.align(lv.ALIGN.TOP_MID, 0, 0)
        self._map_img.add_flag(lv.obj.FLAG.HIDDEN)  # Ẩn cho đến khi có ảnh
        self._map_img.set_zoom(256)  # 1:1 scale
        
        # ── Overlay: thông báo camera (hiện trên đầu bản đồ) ──
        self._cam_banner = lv.label(ma)
        self._cam_banner.set_size(_W - 20, lv.SIZE_CONTENT)
        self._cam_banner.align(lv.ALIGN.TOP_MID, 0, 8)
        self._cam_banner.set_style_bg_color(self.C_RED, 0)
        self._cam_banner.set_style_bg_opa(lv.OPA.COVER, 0)
        self._cam_banner.set_style_text_color(self.C_TEXT, 0)
        self._cam_banner.set_style_pad_all(4, 0)
        self._cam_banner.set_style_radius(6, 0)
        self._cam_banner.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        self._cam_banner.set_text("")
        self._cam_banner.add_flag(lv.obj.FLAG.HIDDEN)
    
    def _build_hud_bar(self):
        """Thanh HUD dưới cùng 40px: tốc độ | chỉ dẫn | biển tốc độ."""
        hud = lv.obj(self.scr)
        hud.set_size(_W, _HUD)
        hud.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        hud.set_style_bg_color(self.C_PANEL, 0)
        hud.set_style_border_width(0, 0)
        hud.set_style_border_top_width(1, 0)
        hud.set_style_border_top_color(lv.color_make(50, 55, 70), 0)
        hud.set_style_radius(0, 0)
        hud.set_style_pad_all(0, 0)
        self._hud = hud
        
        # Tốc độ hiện tại (bên trái)
        self._speed_lbl = lv.label(hud)
        self._speed_lbl.set_text("0")
        self._speed_lbl.align(lv.ALIGN.LEFT_MID, 8, 0)
        self._speed_lbl.set_style_text_color(self.C_GREEN, 0)
        self._speed_lbl.set_style_text_font(lv.font_montserrat_28, 0)
        
        # km/h đơn vị (nhỏ bên dưới tốc độ)
        self._unit_lbl = lv.label(hud)
        self._unit_lbl.set_text("km/h")
        self._unit_lbl.align(lv.ALIGN.LEFT_MID, 40, 8)
        self._unit_lbl.set_style_text_color(lv.color_make(140, 140, 140), 0)
        
        # Chỉ dẫn (giữa)
        self._instr_lbl = lv.label(hud)
        self._instr_lbl.set_size(130, _HUD)
        self._instr_lbl.align(lv.ALIGN.CENTER, -10, 0)
        self._instr_lbl.set_text("Sẵn sàng")
        self._instr_lbl.set_style_text_color(self.C_TEXT, 0)
        self._instr_lbl.set_long_mode(lv.label.LONG.SCROLL_CIRCULAR)
        self._instr_lbl.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        
        # Biển giới hạn tốc độ (vòng tròn đỏ, bên phải)
        self._limit_circle = lv.obj(hud)
        self._limit_circle.set_size(36, 36)
        self._limit_circle.align(lv.ALIGN.RIGHT_MID, -4, 0)
        self._limit_circle.set_style_bg_color(self.C_LIMIT, 0)
        self._limit_circle.set_style_radius(lv.RADIUS_CIRCLE, 0)
        self._limit_circle.set_style_border_color(lv.color_make(255, 255, 255), 0)
        self._limit_circle.set_style_border_width(2, 0)
        self._limit_circle.set_style_pad_all(0, 0)
        
        self._limit_lbl = lv.label(self._limit_circle)
        self._limit_lbl.set_text("60")
        self._limit_lbl.align(lv.ALIGN.CENTER, 0, 0)
        self._limit_lbl.set_style_text_color(lv.color_make(255, 255, 255), 0)
    
    def _build_notification_layer(self):
        """Layer thông báo nổi trên tất cả (giữa màn hình)."""
        self._notif_box = lv.obj(self.scr)
        self._notif_box.set_size(_W - 20, lv.SIZE_CONTENT)
        self._notif_box.align(lv.ALIGN.CENTER, 0, 0)
        self._notif_box.set_style_bg_color(self.C_BLUE, 0)
        self._notif_box.set_style_bg_opa(lv.OPA._90, 0)
        self._notif_box.set_style_border_width(0, 0)
        self._notif_box.set_style_radius(10, 0)
        self._notif_box.set_style_pad_all(10, 0)
        
        self._notif_lbl = lv.label(self._notif_box)
        self._notif_lbl.set_size(_W - 40, lv.SIZE_CONTENT)
        self._notif_lbl.set_text("")
        self._notif_lbl.set_style_text_color(self.C_TEXT, 0)
        self._notif_lbl.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        self._notif_lbl.set_long_mode(lv.label.LONG.WRAP)
        
        self._notif_box.add_flag(lv.obj.FLAG.HIDDEN)
    
    def _build_route_select_panel(self):
        """Panel chọn tuyến đường (ẩn mặc định)."""
        self._route_panel = None  # Tạo động khi cần
    
    # ═══════════════════════════════════════════════════════
    # MAP IMAGE UPDATE (Core feature)
    # ═══════════════════════════════════════════════════════
    
    def update_map_image(self, png_bytes):
        """Nhận PNG bytes từ server và hiển thị lên màn hình.
        
        Server gọi Google Maps Static API với center = GPS user hiện tại
        → bản đồ luôn follow user, giống như Google Maps.
        
        Args:
            png_bytes: bytes object chứa PNG image từ Google Maps Static API
        """
        if not png_bytes or len(png_bytes) < 100:
            return
        try:
            # Ghi file PNG tạm vào filesystem ESP32
            with open(self._map_file, "wb") as f:
                f.write(png_bytes)
            
            # Cập nhật src của lv.img widget
            self._map_img.set_src(self._map_file)
            
            if not self._has_map:
                # Lần đầu có ảnh: ẩn placeholder, hiện map
                self._placeholder.add_flag(lv.obj.FLAG.HIDDEN)
                self._map_img.clear_flag(lv.obj.FLAG.HIDDEN)
                self._has_map = True
            
            lv.task_handler()
        except Exception as e:
            print("[Map] Lỗi update map image:", e)
    
    # ═══════════════════════════════════════════════════════
    # HUD UPDATES
    # ═══════════════════════════════════════════════════════
    
    def update_navigation_data(self, instruction_text, speed=0, dist_to_next=0, eta_min=0):
        """Cập nhật HUD bar: tốc độ + chỉ dẫn quẹo."""
        self._speed = speed
        self._turn_dist = dist_to_next
        self._eta_min  = eta_min
        
        # Tốc độ
        self._speed_lbl.set_text(str(int(speed)))
        
        # Màu tốc độ
        limit = self._speed_limit
        if speed > limit + 5:
            self._speed_lbl.set_style_text_color(self.C_RED, 0)
        elif speed > limit - 10:
            self._speed_lbl.set_style_text_color(self.C_ORANGE, 0)
        else:
            self._speed_lbl.set_style_text_color(self.C_GREEN, 0)
        
        # Chỉ dẫn + khoảng cách
        if dist_to_next and dist_to_next > 0:
            instr_short = instruction_text[:30] if instruction_text else "Thẳng"
            self._instr_lbl.set_text(f"{instr_short} {int(dist_to_next)}m")
        else:
            self._instr_lbl.set_text(instruction_text[:35] if instruction_text else "Sẵn sàng")
        
        lv.task_handler()
    
    def update_speed_limit(self, speed_limit_kmh):
        """Cập nhật biển báo giới hạn tốc độ (vòng tròn đỏ)."""
        self._speed_limit = speed_limit_kmh
        self._limit_lbl.set_text(str(int(speed_limit_kmh)))
        # Vàng cam nếu zone đặc biệt (≤40), đỏ bình thường
        if speed_limit_kmh <= 40:
            self._limit_circle.set_style_bg_color(self.C_ORANGE, 0)
        else:
            self._limit_circle.set_style_bg_color(self.C_LIMIT, 0)
        lv.task_handler()
    
    def update_connection_status(self, wifi_ok, gps_ok=None):
        """Cập nhật status bar: WiFi + GPS."""
        self._wifi_ok = wifi_ok
        if wifi_ok:
            self._wifi_lbl.set_text("WiFi ✓")
            self._wifi_lbl.set_style_text_color(self.C_GREEN, 0)
        else:
            self._wifi_lbl.set_text("WiFi ✗")
            self._wifi_lbl.set_style_text_color(self.C_RED, 0)
        
        if gps_ok is not None:
            self._gps_ok = gps_ok
            if gps_ok:
                self._gps_lbl.set_text("GPS ✓")
                self._gps_lbl.set_style_text_color(self.C_GREEN, 0)
            else:
                self._gps_lbl.set_text("GPS: Chờ...")
                self._gps_lbl.set_style_text_color(self.C_ORANGE, 0)
    
    def update_battery(self, percentage):
        """Cập nhật % pin."""
        self._battery = percentage
        self._bat_lbl.set_text(f"{percentage}%")
        if percentage < 20:
            self._bat_lbl.set_style_text_color(self.C_RED, 0)
        elif percentage < 50:
            self._bat_lbl.set_style_text_color(self.C_ORANGE, 0)
        else:
            self._bat_lbl.set_style_text_color(self.C_GREEN, 0)
    
    def update_gps_label(self, lat, lon):
        """Hiện tọa độ GPS trên status bar."""
        self._gps_lbl.set_text(f"{lat:.4f},{lon:.4f}")
        self._gps_lbl.set_style_text_color(self.C_GREEN, 0)
    
    # ═══════════════════════════════════════════════════════
    # CAMERA & SPEED ALERTS
    # ═══════════════════════════════════════════════════════
    
    def show_camera_alert(self, dist_m, cam_type="speed"):
        """Hiện cảnh báo camera trên bản đồ (overlay banner đỏ nhấp nháy)."""
        type_name = "TỐC ĐỘ" if cam_type == "speed" else "ĐÈN ĐỎ"
        self._cam_banner.set_text(f"⚠ CAMERA {type_name} — {int(dist_m)}m")
        self._cam_banner.clear_flag(lv.obj.FLAG.HIDDEN)
    
    def hide_camera_alert(self):
        """Ẩn banner cảnh báo camera."""
        self._cam_banner.add_flag(lv.obj.FLAG.HIDDEN)
    
    def _on_flash_tick(self, timer):
        """Nhấp nháy banner camera 1Hz."""
        self._flash_state = not self._flash_state
        if not self._cam_banner.has_flag(lv.obj.FLAG.HIDDEN):
            if self._flash_state:
                self._cam_banner.set_style_bg_color(self.C_RED, 0)
            else:
                self._cam_banner.set_style_bg_color(self.C_ORANGE, 0)
    
    # ═══════════════════════════════════════════════════════
    # NOTIFICATIONS
    # ═══════════════════════════════════════════════════════
    
    def show_notification(self, text, duration_ms=3000, color=None):
        """Hiện thông báo nổi giữa màn hình, tự tắt sau duration_ms ms."""
        if color:
            self._notif_box.set_style_bg_color(color, 0)
        else:
            self._notif_box.set_style_bg_color(self.C_BLUE, 0)
        self._notif_lbl.set_text(text)
        self._notif_box.clear_flag(lv.obj.FLAG.HIDDEN)
        lv.task_handler()
        
        # Tự tắt
        if self._notif_timer:
            try: self._notif_timer.del_timer()
            except: pass
        self._notif_timer = lv.timer_create(
            lambda t: self._hide_notification(), duration_ms, None
        )
        self._notif_timer.set_repeat_count(1)
    
    def _hide_notification(self):
        self._notif_box.add_flag(lv.obj.FLAG.HIDDEN)
        lv.task_handler()
    
    def show_screen_state(self, state):
        """Hiện trạng thái trên HUD instruction."""
        texts = {
            "idle":       "Chờ kết nối iPhone...",
            "ready":      "Xin chào Ngài Tequila — Nói lệnh",
            "listening":  "🎤 Đang nghe...",
            "fetching":   "🔄 Đang tìm đường...",
            "navigating": "Đang dẫn đường",
            "arrived":    "✅ Đã đến nơi!",
        }
        if state in texts:
            self._instr_lbl.set_text(texts[state])
            if state == "arrived":
                self.show_notification("✅ Địa điểm của bạn đã đến!\nChúc mừng!", 5000, self.C_GREEN)
        lv.task_handler()
    
    # ═══════════════════════════════════════════════════════
    # ROUTE SELECTION UI
    # ═══════════════════════════════════════════════════════
    
    def show_routes(self, routes_data, on_select_callback):
        """Hiện panel chọn 1 trong 3 tuyến đường trên màn hình 240×320."""
        self.clear_routes_selection()
        
        panel = lv.obj(self.scr)
        panel.set_size(_W, _H)
        panel.align(lv.ALIGN.CENTER, 0, 0)
        panel.set_style_bg_color(self.C_BG, 0)
        panel.set_style_bg_opa(lv.OPA.COVER, 0)
        panel.set_style_border_width(0, 0)
        panel.set_style_radius(0, 0)
        panel.set_style_pad_all(6, 0)
        self._route_panel = panel
        
        # Tiêu đề
        title = lv.label(panel)
        title.set_text("🗺  Chọn Tuyến Đường")
        title.align(lv.ALIGN.TOP_MID, 0, 10)
        title.set_style_text_color(self.C_GREEN, 0)
        
        sub = lv.label(panel)
        sub.set_text("Tuyến 1 = ưu tiên (nhanh nhất)")
        sub.align(lv.ALIGN.TOP_MID, 0, 34)
        sub.set_style_text_color(lv.color_make(160, 160, 160), 0)
        
        def _make_handler(idx):
            def _h(e):
                self.clear_routes_selection()
                on_select_callback(idx)
            return _h
        
        COLORS = [self.C_GREEN, self.C_BLUE, lv.color_make(140, 80, 200)]
        
        for i, r in enumerate(routes_data[:3]):
            y_off = 60 + i * 68
            
            btn = lv.btn(panel)
            btn.set_size(_W - 16, 60)
            btn.align(lv.ALIGN.TOP_MID, 0, y_off)
            btn.set_style_bg_color(COLORS[i], 0)
            btn.set_style_radius(10, 0)
            btn.set_style_border_width(0, 0)
            btn.set_style_pad_all(6, 0)
            
            # Label tuyến đường
            line1 = "Tuyến %d%s" % (i+1, " ⭐ Ưu tiên" if i == 0 else "")
            dist  = r.get("dist_km", 0)
            eta   = r.get("eta_min", 0)
            cams  = r.get("camera_count", 0)
            line2 = "%.1f km • %d phút • %d camera" % (dist, eta, cams)
            
            lbl = lv.label(btn)
            lbl.set_text(f"{line1}\n{line2}")
            lbl.align(lv.ALIGN.CENTER, 0, 0)
            lbl.set_style_text_color(lv.color_make(255, 255, 255), 0)
            lbl.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
            
            btn.add_event_cb(_make_handler(r.get("index", i)), lv.EVENT.CLICKED, None)
        
        # Nút hủy
        cancel = lv.btn(panel)
        cancel.set_size(_W - 16, 32)
        cancel.align(lv.ALIGN.BOTTOM_MID, 0, -8)
        cancel.set_style_bg_color(self.C_RED, 0)
        cancel.set_style_radius(8, 0)
        c_lbl = lv.label(cancel)
        c_lbl.set_text("Hủy")
        c_lbl.align(lv.ALIGN.CENTER, 0, 0)
        c_lbl.set_style_text_color(lv.color_make(255, 255, 255), 0)
        cancel.add_event_cb(lambda e: self.clear_routes_selection(), lv.EVENT.CLICKED, None)
        
        lv.task_handler()
    
    def clear_routes_selection(self):
        """Xóa panel chọn tuyến."""
        if self._route_panel:
            try:
                self._route_panel.delete()
            except Exception:
                pass
            self._route_panel = None
        lv.task_handler()
    
    # ═══════════════════════════════════════════════════════
    # COMPATIBILITY WRAPPERS (cho main.py cũ)
    # ═══════════════════════════════════════════════════════
    
    def update_map(self, current_pos, route_polyline, camera_points, gps_accuracy=""):
        """Compat wrapper: bản đồ thật được update qua update_map_image().
        Hàm này chỉ update HUD."""
        if current_pos and len(current_pos) >= 2:
            self.update_gps_label(current_pos[0], current_pos[1])
    
    def update_position(self, lat, lon, heading=0):
        """Compat wrapper."""
        self.update_gps_label(lat, lon)
        lv.task_handler()
    
    def update_route(self, polyline):
        """Không cần vẽ vector route — JPEG từ server đã có route line."""
        pass
    
    def update_cameras(self, cameras):
        """Compat wrapper — cảnh báo camera qua show_camera_alert()."""
        if cameras:
            nearest = cameras[0]
            dist = nearest.get("dist_m", 9999)
            if dist <= 50:
                self.show_camera_alert(dist, nearest.get("type", "speed"))
            else:
                self.hide_camera_alert()
        else:
            self.hide_camera_alert()
    
    def update_nav_instruction(self, instruction, dist_m, maneuver=""):
        """Compat wrapper."""
        arrows = {
            "turn-left": "← ", "turn-right": "→ ",
            "sharp-left": "↰ ", "sharp-right": "↱ ",
            "arrive": "✓ ", "straight": "↑ ", "uturn": "↺ ",
        }
        arr = arrows.get(maneuver, "")
        self._instr_lbl.set_text(f"{arr}{instruction[:28]} {dist_m}m")
        lv.task_handler()
    
    def handle_alert_packet(self, alert_str):
        """Compat wrapper."""
        pass
    
    def handle_sign_packet(self, sign_str):
        """Compat wrapper."""
        pass


# Alias
class MapDisplay(LVGLMapScreen):
    """Alias để main.py import MapDisplay."""
    pass
