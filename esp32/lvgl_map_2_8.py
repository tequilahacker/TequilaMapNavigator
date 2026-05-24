# LVGL Map and UI Renderer for 2.8" TFT with capacitive touch
import lvgl as lv
import config
import math

class LVGLMapScreen:
    def __init__(self):
        # Initialize UI Styles and screen
        self.scr = lv.obj()
        lv.scr_load(self.scr)
        
        # Color Palette - Premium Sleek Dark Mode
        self.COLOR_BG = lv.color_make(24, 28, 36)        # Dark Charcoal BG
        self.COLOR_PANEL = lv.color_make(35, 40, 52)     # Steel Blue Panel
        self.COLOR_ROUTE = lv.color_make(0, 168, 255)     # Electric Neon Cyan
        self.COLOR_TEXT = lv.color_make(240, 240, 240)    # Off-White Text
        self.COLOR_GREEN = lv.color_make(46, 204, 113)    # Bright Green
        self.COLOR_RED = lv.color_make(231, 76, 60)      # Neon Alert Red
        self.COLOR_ORANGE = lv.color_make(230, 126, 34)  # Warning Orange
        
        self.scr.set_style_bg_color(self.COLOR_BG, 0)
        
        # Projection/Zoom Parameters
        self.zoom = 1.0  # Scale multiplier (1.0 default)
        self.center_lat = 10.762622  # Ho Chi Minh City default coords
        self.center_lon = 106.660172
        self.heading = 0
        
        # Map dimensions
        self.map_width = config.DISPLAY_WIDTH
        self.map_height = config.DISPLAY_HEIGHT - 90  # 30px top bar + 60px bottom panel
        
        self.camera_markers = []
        self.camera_flash_state = True
        self.points_buffer = []  # Retain point arrays to prevent GC clean-ups
        
        self._init_ui()
        
        # Create 2Hz (500ms) timer for camera flashing and blinking warnings
        self.flash_timer = lv.timer_create(self._toggle_camera_flash, 500, None)
        
    def _init_ui(self):
        # 1. Top Status Bar (30px)
        self.status_bar = lv.obj(self.scr)
        self.status_bar.set_size(config.DISPLAY_WIDTH, 30)
        self.status_bar.align(lv.ALIGN.TOP_MID, 0, 0)
        self.status_bar.set_style_bg_color(self.COLOR_PANEL, 0)
        self.status_bar.set_style_border_width(0, 0)
        self.status_bar.set_style_radius(0, 0)
        
        self.conn_label = lv.label(self.status_bar)
        self.conn_label.align(lv.ALIGN.LEFT_MID, 10, 0)
        self.conn_label.set_text("iPhone ✗")
        self.conn_label.set_style_text_color(self.COLOR_RED, 0)
        
        self.gps_label = lv.label(self.status_bar)
        self.gps_label.align(lv.ALIGN.CENTER, 0, 0)
        self.gps_label.set_text("GPS: Chờ...")
        self.gps_label.set_style_text_color(self.COLOR_TEXT, 0)
        
        self.bat_label = lv.label(self.status_bar)
        self.bat_label.align(lv.ALIGN.RIGHT_MID, -10, 0)
        self.bat_label.set_text("100%")
        self.bat_label.set_style_text_color(self.COLOR_GREEN, 0)
        
        # 2. Main Map Container (clipping mask)
        self.map_container = lv.obj(self.scr)
        self.map_container.set_size(self.map_width, self.map_height)
        self.map_container.align(lv.ALIGN.TOP_MID, 0, 30)
        self.map_container.set_style_bg_color(self.COLOR_BG, 0)
        self.map_container.set_style_border_width(0, 0)
        self.map_container.set_style_radius(0, 0)
        self.map_container.set_style_clip_corner(True, 0)
        # Handle tap to zoom event on map
        self.map_container.add_event_cb(self._handle_map_tap, lv.EVENT.CLICKED, None)
        
        # 2a. Route line (Vector drawing inside container)
        self.route_line = lv.line(self.map_container)
        self.line_style = lv.style_t()
        self.line_style.init()
        self.line_style.set_line_color(self.COLOR_ROUTE)
        self.line_style.set_line_width(6)
        self.line_style.set_line_rounded(True)
        self.route_line.add_style(self.line_style, 0)
        
        # 2b. Current position marker (Green Dot + Direction Arrow)
        self.pos_marker = lv.obj(self.map_container)
        self.pos_marker.set_size(16, 16)
        self.pos_marker.set_style_bg_color(self.COLOR_GREEN, 0)
        self.pos_marker.set_style_radius(lv.RADIUS_CIRCLE, 0)
        self.pos_marker.set_style_border_width(2, 0)
        self.pos_marker.set_style_border_color(lv.color_make(255, 255, 255), 0)
        
        self.dir_arrow = lv.label(self.map_container)
        self.dir_arrow.set_text("▲")
        self.dir_arrow.set_style_text_color(self.COLOR_GREEN, 0)
        
        # 2c. Near Camera alert banner (initially hidden)
        self.camera_warn_banner = lv.label(self.scr)
        self.camera_warn_banner.align(lv.ALIGN.TOP_MID, 0, 40)
        self.camera_warn_banner.set_style_bg_color(self.COLOR_RED, 0)
        self.camera_warn_banner.set_style_text_color(self.COLOR_TEXT, 0)
        self.camera_warn_banner.set_style_bg_opa(lv.OPA.COVER, 0)
        self.camera_warn_banner.set_style_pad_all(6, 0)
        self.camera_warn_banner.set_style_radius(4, 0)
        self.camera_warn_banner.set_text("")
        
        # 3. Bottom Info Panel (60px)
        self.info_panel = lv.obj(self.scr)
        self.info_panel.set_size(config.DISPLAY_WIDTH, 60)
        self.info_panel.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        self.info_panel.set_style_bg_color(self.COLOR_PANEL, 0)
        self.info_panel.set_style_border_width(0, 0)
        self.info_panel.set_style_radius(0, 0)
        
        # Nav Turn Alert / Instruction
        self.alert_label = lv.label(self.info_panel)
        self.alert_label.align(lv.ALIGN.LEFT_MID, 10, 0)
        self.alert_label.set_text("Chờ dẫn đường...")
        self.alert_label.set_style_text_color(self.COLOR_TEXT, 0)

        # Speed display (large number)
        self.speed_label = lv.label(self.info_panel)
        self.speed_label.align(lv.ALIGN.RIGHT_MID, -65, 0)
        self.speed_label.set_text("0")
        self.speed_label.set_style_text_color(self.COLOR_GREEN, 0)

        # Speed limit sign (biển đỏ giới hạn tốc độ - vòng tròn đỏ)
        self.speed_limit_circle = lv.obj(self.info_panel)
        self.speed_limit_circle.set_size(44, 44)
        self.speed_limit_circle.align(lv.ALIGN.RIGHT_MID, -10, 0)
        self.speed_limit_circle.set_style_bg_color(lv.color_make(220, 30, 30), 0)
        self.speed_limit_circle.set_style_radius(lv.RADIUS_CIRCLE, 0)
        self.speed_limit_circle.set_style_border_color(lv.color_make(255, 255, 255), 0)
        self.speed_limit_circle.set_style_border_width(3, 0)

        self.speed_limit_label = lv.label(self.speed_limit_circle)
        self.speed_limit_label.set_text("60")
        self.speed_limit_label.align(lv.ALIGN.CENTER, 0, 0)
        self.speed_limit_label.set_style_text_color(lv.color_make(255, 255, 255), 0)

        # Current speed limit (track for color-coding)
        self._current_speed_limit = 60

    def gps_to_pixels(self, lat, lon):
        """Converts latitude and longitude into 2D map pixel coordinates
        relative to the centered current position.
        """
        d_lat = lat - self.center_lat
        d_lon = lon - self.center_lon
        
        # Local linear projection (HCMC coefficients: 1 deg lat=111120m, 1 deg lon=109150m)
        # Default zoom scale: 1 deg diff = 50,000 pixels (approx ~50m screen radius)
        scale_x = 50000.0 * self.zoom
        scale_y = 50900.0 * self.zoom
        
        px = int(self.map_width / 2 + (d_lon * scale_x))
        py = int(self.map_height / 2 - (d_lat * scale_y))
        return px, py

    def distance_meters(self, lat1, lon1, lat2, lon2):
        """Returns approximate distance in meters between two GPS coordinates."""
        dy = (lat1 - lat2) * 111120.0
        dx = (lon1 - lon2) * 109150.0
        return math.sqrt(dx*dx + dy*dy)

    def get_arrow_char(self, angle):
        """Returns directional arrow character matching motorcycle heading angle."""
        h = angle % 360
        if 337.5 <= h or h < 22.5: return "▲"
        if 22.5 <= h < 67.5: return "↗"
        if 67.5 <= h < 112.5: return "▶"
        if 112.5 <= h < 157.5: return "↘"
        if 157.5 <= h < 202.5: return "▼"
        if 202.5 <= h < 247.5: return "↙"
        if 247.5 <= h < 292.5: return "◀"
        return "↖"

    def _toggle_camera_flash(self, timer):
        """Blinks nearby speed camera markers and banner warnings at 2Hz."""
        self.camera_flash_state = not self.camera_flash_state
        for marker in self.camera_markers:
            if self.camera_flash_state:
                marker.set_style_bg_color(self.COLOR_RED, 0)
            else:
                marker.set_style_bg_color(lv.color_make(80, 0, 0), 0)

    def _handle_map_tap(self, event):
        """Event callback: clicking the map cycles through zoom levels."""
        if self.zoom == 1.0:
            self.zoom = 1.8  # Zoomed In (detail)
        elif self.zoom == 1.8:
            self.zoom = 0.5  # Zoomed Out (overview)
        else:
            self.zoom = 1.0  # Reset
        print(f"[Map] Zoom cycled to: {self.zoom}")
        # Request immediate display redraw by raising a dummy update callback
        self.redraw_map()

    def redraw_map(self):
        """Forces recalculation and redraw of route and camera markers."""
        # Redraw position marker (always in center of coordinate system)
        self.pos_marker.align(lv.ALIGN.CENTER, 0, 0)
        self.dir_arrow.align(lv.ALIGN.CENTER, 0, -20)
        self.dir_arrow.set_text(self.get_arrow_char(self.heading))
        
        # Redraw route points
        if hasattr(self, 'route_coords') and self.route_coords:
            pts = []
            for lat, lon in self.route_coords:
                x, y = self.gps_to_pixels(lat, lon)
                pts.append(lv.point_t({"x": x, "y": y}))
            self.points_buffer = pts  # Prevent garbage collection of point array
            self.route_line.set_points(self.points_buffer, len(self.points_buffer))
            
        # Redraw camera points
        if hasattr(self, 'camera_coords') and self.camera_coords:
            for idx, item in enumerate(self.camera_coords):
                if idx < len(self.camera_markers):
                    lat, lon, cam_type = item
                    x, y = self.gps_to_pixels(lat, lon)
                    self.camera_markers[idx].align(lv.ALIGN.CENTER, x - int(self.map_width/2), y - int(self.map_height/2))

    def update_map(self, current_pos, route_polyline, camera_points, gps_accuracy="3m"):
        """Called dynamically by BLE handler when new GPS/Route info arrives from iPhone.
        
        current_pos: (lat, lon, heading)
        route_polyline: list of (lat, lon) tuples
        camera_points: list of (lat, lon, camera_type) tuples
        """
        # 1. Update centers and parameters
        self.center_lat, self.center_lon, self.heading = current_pos
        self.route_coords = route_polyline
        self.camera_coords = camera_points
        
        # 2. Update top bar status values
        self.gps_label.set_text(f"GPS: {gps_accuracy}")
        
        # 3. Clean up excess camera markers
        while len(self.camera_markers) > len(camera_points):
            old_marker = self.camera_markers.pop()
            old_marker.delete()
            
        # 4. Generate new camera markers if needed
        while len(self.camera_markers) < len(camera_points):
            new_marker = lv.obj(self.map_container)
            new_marker.set_size(12, 12)
            new_marker.set_style_bg_color(self.COLOR_RED, 0)
            new_marker.set_style_radius(lv.RADIUS_CIRCLE, 0)
            new_marker.set_style_border_width(1, 0)
            new_marker.set_style_border_color(lv.color_make(255, 255, 255), 0)
            self.camera_markers.append(new_marker)
            
        # 5. Check if vehicle is near a camera marker to show warnings
        nearest_distance = 9999.0
        nearest_type = ""
        for lat, lon, cam_type in camera_points:
            dist = self.distance_meters(self.center_lat, self.center_lon, lat, lon)
            if dist < nearest_distance:
                nearest_distance = dist
                nearest_type = "Tốc độ" if cam_type == "speed" else "Vượt đèn đỏ"
                
        if nearest_distance < 150.0:  # Within 150 meters
            self.camera_warn_banner.set_text(f"CẢNH BÁO: CAMERA {nearest_type.upper()} - {int(nearest_distance)}m")
            self.camera_warn_banner.set_style_text_color(self.COLOR_TEXT, 0)
            # Alternate warning banner color with flash state
            if self.camera_flash_state:
                self.camera_warn_banner.set_style_bg_color(self.COLOR_RED, 0)
            else:
                self.camera_warn_banner.set_style_bg_color(self.COLOR_ORANGE, 0)
        else:
            self.camera_warn_banner.set_text("")  # Hide banner
            
        # 6. Recalculate coordinates and draw
        self.redraw_map()

    def update_connection_status(self, is_connected):
        """Updates BLE connection UI indicator."""
        if is_connected:
            self.conn_label.set_text("iPhone ✓")
            self.conn_label.set_style_text_color(self.COLOR_GREEN, 0)
        else:
            self.conn_label.set_text("iPhone ✗")
            self.conn_label.set_style_text_color(self.COLOR_RED, 0)
            self.alert_label.set_text("Chờ dẫn đường...")
            self.gps_label.set_text("GPS: Chờ...")

    def update_navigation_data(self, instruction_text, speed=0, dist_to_next=0):
        """Updates turn guidance texts and motorcycle speed reads."""
        self.alert_label.set_text(f"{instruction_text}\n{dist_to_next}m")
        self.speed_label.set_text(f"{int(speed)}")

        # Color-code speed: xanh = đúng tốc độ, cam = gần giới hạn, đỏ = vượt
        limit = self._current_speed_limit
        if speed > limit + 5:
            self.speed_label.set_style_text_color(self.COLOR_RED, 0)
            self.speed_label.set_style_text_font(lv.font_montserrat_28, 0)
        elif speed > limit - 10:
            self.speed_label.set_style_text_color(self.COLOR_ORANGE, 0)
            self.speed_label.set_style_text_font(lv.font_montserrat_22, 0)
        else:
            self.speed_label.set_style_text_color(self.COLOR_GREEN, 0)
            self.speed_label.set_style_text_font(lv.font_montserrat_22, 0)

    def update_speed_limit(self, speed_limit_kmh):
        """Cập nhật biển báo giới hạn tốc độ."""
        self._current_speed_limit = speed_limit_kmh
        self.speed_limit_label.set_text(str(speed_limit_kmh))
        # Biển đỏ thường, vàng khi có đặc biệt (school, hospital)
        if speed_limit_kmh <= 40:
            self.speed_limit_circle.set_style_bg_color(lv.color_make(255, 140, 0), 0)  # cam = cảnh báo
        else:
            self.speed_limit_circle.set_style_bg_color(lv.color_make(220, 30, 30), 0)  # đỏ = bình thường

    def handle_alert_packet(self, alert_str):
        """Xử lý ALERT packet từ iPhone: ALERT|speed_limit|current_speed|speed_over|cams..."""
        try:
            parts = alert_str.split("|")
            if len(parts) >= 4:
                speed_limit = int(parts[1]) if parts[1].isdigit() else 60
                current_speed = int(parts[2]) if parts[2].isdigit() else 0
                speed_over = parts[3] == "1"
                self.update_speed_limit(speed_limit)
                self.update_navigation_data(
                    self.alert_label.get_text().split("\n")[0],
                    current_speed, 0
                )
                # Cameras trong packet
                cam_list = []
                for cam_str in parts[4:]:
                    cam_parts = cam_str.split(",")
                    if len(cam_parts) >= 3:
                        try:
                            cam_list.append((
                                float(cam_parts[0]),
                                float(cam_parts[1]),
                                cam_parts[2]
                            ))
                        except ValueError:
                            pass
                # Cập nhật camera markers (không cần re-route)
                if cam_list and hasattr(self, 'camera_coords'):
                    self.camera_coords = cam_list
                    self.redraw_map()
        except Exception as e:
            print("[Map] ALERT parse error:", e)

    def handle_sign_packet(self, sign_str):
        """Xử lý SIGN packet từ iPhone: SIGN|speed_limit|zone|over|changed"""
        try:
            parts = sign_str.split("|")
            if len(parts) >= 3:
                speed_limit = int(parts[1]) if parts[1].isdigit() else 60
                zone = parts[2]
                speed_over = parts[3] == "1" if len(parts) > 3 else False
                changed = parts[4] == "1" if len(parts) > 4 else False
                self.update_speed_limit(speed_limit)
                if speed_over:
                    # Flash biển tốc độ đỏ khi vượt
                    self.speed_limit_circle.set_style_bg_color(lv.color_make(255, 0, 0), 0)
                    self.speed_limit_circle.set_style_border_color(lv.color_make(255, 200, 0), 0)
                if changed:
                    # Thông báo nhanh khi đổi giới hạn
                    self.show_notification(f"Giới hạn mới: {speed_limit} km/h")
        except Exception as e:
            print("[Map] SIGN parse error:", e)

    def show_camera_alert(self, alert_text):
        """Hiển thị cảnh báo camera to trong 5 giây."""
        self.camera_warn_banner.set_text(alert_text[:40])
        self.camera_warn_banner.set_style_bg_color(self.COLOR_RED, 0)
        # Auto-hide sau 5 giây
        lv.timer_create(lambda t: self.camera_warn_banner.set_text(""), 5000, None)

    def show_notification(self, text, duration_ms=3000):
        """Hiển thị thông báo ngắn trên đầu màn hình, tự tắt sau duration_ms."""
        self.camera_warn_banner.set_text(text[:40])
        self.camera_warn_banner.set_style_bg_color(lv.color_make(30, 100, 200), 0)
        lv.timer_create(lambda t: self.camera_warn_banner.set_text(""), duration_ms, None)
        lv.task_handler()

    def show_screen_state(self, state):
        """Chuyển trạng thái màn hình theo state machine."""
        state_texts = {
            "idle":      "Khởi động... Chờ iPhone kết nối",
            "ready":     "Sẵn sàng - Nói lệnh hoặc nhấn nút",
            "listening": "🎤 Đang nghe...",
            "fetching":  "🔄 Đang tìm đường...",
            "navigating":"Dẫn đường • GPS OK",
            "arrived":   "✅ Đã đến nơi!",
        }
        if state in state_texts:
            self.alert_label.set_text(state_texts[state])
        lv.task_handler()

    def show_routes(self, routes_data, on_select_callback):
        """Hiển thị giao diện chọn 1 trong 3 tuyến đường trên màn hình ESP32 2.8"."""
        # Cleanup trước nếu có
        self.clear_routes_selection()
        
        # Tạo panel phủ toàn bộ màn hình
        self.routes_panel = lv.obj(self.scr)
        self.routes_panel.set_size(config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT)
        self.routes_panel.align(lv.ALIGN.CENTER, 0, 0)
        self.routes_panel.set_style_bg_color(self.COLOR_BG, 0)
        self.routes_panel.set_style_border_width(0, 0)
        
        # Tiêu đề
        title = lv.label(self.routes_panel)
        title.set_text("Chon Tuyen Duong Tequila Map")
        title.align(lv.ALIGN.TOP_MID, 0, 8)
        title.set_style_text_color(self.COLOR_ROUTE, 0)
        
        def make_click_handler(idx):
            def handler(e):
                self.clear_routes_selection()
                on_select_callback(idx)
            return handler
            
        for i, r in enumerate(routes_data[:3]):
            btn = lv.btn(self.routes_panel)
            btn.set_size(280, 42)
            btn.align(lv.ALIGN.TOP_MID, 0, 42 + i * 46)
            
            # Đổi màu button ưu tiên (Tuyến 1) thành xanh lá, các tuyến khác màu panel
            if i == 0:
                btn.set_style_bg_color(self.COLOR_GREEN, 0)
                # Text màu đen để tương phản tốt trên nền xanh lá
                btn.set_style_text_color(lv.color_make(0,0,0), 0)
            else:
                btn.set_style_bg_color(self.COLOR_PANEL, 0)
                btn.set_style_text_color(self.COLOR_TEXT, 0)
                
            lbl = lv.label(btn)
            label_text = "Tuyen %d: %.1f km - %d p" % (i+1, r.get("dist_km", 0), r.get("eta_min", 0))
            if i == 0:
                label_text += " (Uu tien)"
            lbl.set_text(label_text)
            lbl.align(lv.ALIGN.CENTER, 0, 0)
            
            btn.add_event_cb(make_click_handler(r.get("index", i)), lv.EVENT.CLICKED, None)
            
        # Nút Huỷ bỏ
        cancel_btn = lv.btn(self.routes_panel)
        cancel_btn.set_size(280, 32)
        cancel_btn.align(lv.ALIGN.TOP_MID, 0, 185)
        cancel_btn.set_style_bg_color(self.COLOR_RED, 0)
        cancel_btn.set_style_text_color(lv.color_make(255,255,255), 0)
        
        cancel_lbl = lv.label(cancel_btn)
        cancel_lbl.set_text("Huy Bo")
        cancel_lbl.align(lv.ALIGN.CENTER, 0, 0)
        
        cancel_btn.add_event_cb(lambda e: self.clear_routes_selection(), lv.EVENT.CLICKED, None)
        
        lv.task_handler()

    def clear_routes_selection(self):
        """Xoá panel chọn tuyến đường nếu có."""
        if hasattr(self, 'routes_panel') and self.routes_panel:
            try:
                self.routes_panel.delete()
            except:
                pass
            self.routes_panel = None
        lv.task_handler()

    def update_position(self, lat, lon, heading):
        """Wrapper đơn giản cho main.py."""
        self.center_lat = lat
        self.center_lon = lon
        self.heading = heading
        self.pos_marker.align(lv.ALIGN.CENTER, 0, 0)
        self.dir_arrow.set_text(self.get_arrow_char(heading))
        lv.task_handler()

    def update_route(self, polyline):
        """Update route polyline."""
        self.route_coords = polyline
        self.redraw_map()

    def update_cameras(self, cameras):
        """Update camera list từ parsed data."""
        self.camera_coords = [(c["lat"], c["lon"], c.get("type", "speed")) for c in cameras]
        self.redraw_map()

    def update_nav_instruction(self, instruction, dist_m, maneuver):
        """Cập nhật hướng dẫn rẽ."""
        maneuver_arrows = {
            "turn-left": "←", "turn-right": "→",
            "sharp-left": "↰", "sharp-right": "↱",
            "slight-left": "↖", "slight-right": "↗",
            "arrive": "✓", "straight": "↑",
            "uturn": "↺",
        }
        arrow = maneuver_arrows.get(maneuver, "")
        self.alert_label.set_text(f"{arrow} {instruction[:25]}\n{dist_m}m")
        lv.task_handler()

    def update_battery(self, percentage):
        """Updates battery level state on Top Status Bar."""
        self.bat_label.set_text(f"{percentage}%")
        if percentage < 20:
            self.bat_label.set_style_text_color(self.COLOR_RED, 0)
        elif percentage < 50:
            self.bat_label.set_style_text_color(self.COLOR_ORANGE, 0)
        else:
            self.bat_label.set_style_text_color(self.COLOR_GREEN, 0)


# Alias cho main.py (compatibility)
class MapDisplay(LVGLMapScreen):
    """Alias class để main.py có thể import MapDisplay."""
    pass
