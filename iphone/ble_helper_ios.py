# iphone/ble_helper_ios.py
# Pythonista 3 - BLE Client + Navigation Orchestrator cho iPhone 14 Pro
# PHIÊN BẢN ĐẦY ĐỦ: Google Maps + Vietmap + OSM + WYN + Waze + Biển báo
import time
import json
import threading

try:
    import cb           # CoreBluetooth qua Pythonista
    import speech
    import location
    HAS_PYTHONISTA = True
except ImportError:
    HAS_PYTHONISTA = False
    print("[iOS BLE] Chạy ngoài Pythonista, dùng mock mode.")

from navigation_engine import NavigationEngine
from camera_alert import CameraAlertEngine
from tts_handler import TTSHandler
from gps_tracker import GPSTracker
from web_server import NavigatorWebServer
# ─── Engines mới (multi-source alert system) ───
from osm_speed_engine import OSMSpeedEngine
from waze_scraper import WazeScraper
from multi_alert_engine import MultiAlertEngine
from sign_alert_engine import SignAlertEngine
from wyn_waze_bridge import WYNWazeBridge

# ─── Cấu hình ───
BLE_TARGET_NAME  = "VMN-Compact"
UART_SERVICE     = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
RX_CHAR_UUID     = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  # Ghi vào ESP32
TX_CHAR_UUID     = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  # Nhận từ ESP32

CAMERA_CSV_PATH  = "../data/camera_phat_nguoi.csv"
UPDATE_INTERVAL  = 8  # Giây giữa các lần update GPS+route về ESP32
# Google API Key and Vietmap are not needed anymore! 100% Free OSM/OSRM is used instead.

# ═══════════════════════════════════════════════════
class TequilaNavigatorIOS:
    """Orchestrator chính chạy trên iPhone, kết nối tất cả services."""
    
    def __init__(self):
        self.peripheral = None
        self.rx_char = None
        self.is_connected = False
        self._msg_buffer = ""
        self._audio_chunks = []
        self._receiving_audio = False
        
        # ─── Engines cơ bản ───
        print("[iOS] Khởi tạo Navigation Engine (OSM/OSRM)...")
        self.nav = NavigationEngine()

        print("[iOS] Khởi tạo Waze Scraper...")
        self.waze = WazeScraper()

        print("[iOS] Khởi tạo OSM Speed Engine...")
        self.osm = OSMSpeedEngine()  # Tự load cache nếu có

        print("[iOS] Khởi tạo Camera Alert Engine (CSV)...")
        self.cam = CameraAlertEngine(csv_path=CAMERA_CSV_PATH)

        print("[iOS] Khởi tạo GPS Tracker...")
        self.gps = GPSTracker()

        self.tts = TTSHandler(ble_handler=self)

        # ─── Multi-source Alert Engine ───
        print("[iOS] Khởi tạo Multi Alert Engine (OSM+Waze+CSV)...")
        self.multi_alert = MultiAlertEngine(
            osm_engine=self.osm,
            waze_scraper=self.waze,
            csv_engine=self.cam,
        )
        self.multi_alert.merge_all_cameras()  # Merge ngay khi khởi động

        print("[iOS] Khởi tạo Sign Alert Engine...")
        self.sign_alert = SignAlertEngine(
            osm_engine=self.osm,
        )

        print("[iOS] Khởi tạo WYN/Waze Bridge...")
        self.wyn_waze = WYNWazeBridge()
        # In hướng dẫn setup WYN
        print(self.wyn_waze.get_setup_instructions())

        # ─── State ───
        self.current_destination = None
        self.current_waypoints = []
        self.current_route = None
        self.is_navigating = False
        self._nav_thread = None
        self._last_speed_limit = None

        # Web server companion app
        print("[iOS] Khởi tạo Web Server...")
        self.server = NavigatorWebServer(
            port=8080, nav_engine=self.nav, ble_handler=self,
            camera_engine=self.cam, gps_tracker=self.gps
        )
        
    # ─────────────────────────────────────────────
    # BLE METHODS
    # ─────────────────────────────────────────────
    def start(self):
        """Bắt đầu BLE scan và khởi động web server."""
        print(f"\n[iOS] Tìm kiếm ESP32 '{BLE_TARGET_NAME}'...")
        
        # Khởi động web server trên background thread
        self.server.start()
        
        if HAS_PYTHONISTA:
            cb.set_central_delegate(self)
            cb.scan_for_peripherals()
        else:
            print("[iOS] Mock mode: Giả lập kết nối BLE.")
            self.is_connected = True
            self._start_nav_loop()
            
    def send_text(self, text):
        """Gửi text message về ESP32 qua BLE UART."""
        if not self.is_connected or not self.rx_char:
            print(f"[BLE] Send (offline): {text[:50]}")
            return
        try:
            data = (text + "\n").encode('utf-8')
            # Chia nhỏ nếu > MTU (thường 244 bytes)
            MTU = 200
            for i in range(0, len(data), MTU):
                chunk = data[i:i+MTU]
                self.peripheral.write_characteristic_value(self.rx_char, chunk, True)
                time.sleep(0.01)
        except Exception as e:
            print("[BLE] Lỗi gửi:", e)
            
    def send_voice_audio(self, audio_base64):
        """Stream audio base64 về ESP32 để phát qua loa."""
        self.send_text("AUDIO_START")
        chunk_size = 180
        for i in range(0, len(audio_base64), chunk_size):
            self.send_text(audio_base64[i:i+chunk_size])
            time.sleep(0.01)
        self.send_text("AUDIO_END")
        
    # ─────────────────────────────────────────────
    # NAVIGATION LOGIC
    # ─────────────────────────────────────────────
    def start_navigation(self, destination_text, extra_waypoints=None):
        """Bắt đầu navigation đến destination."""
        print(f"\n[Nav] Bắt đầu điều hướng đến: {destination_text}")
        
        # Geocode destination
        dest_coords = self.nav.geocode(destination_text)
        if not dest_coords:
            self.send_text("TTS|Không tìm thấy địa điểm. Vui lòng thử lại.")
            return
            
        # Geocode waypoints
        wp_coords = []
        for wp in (extra_waypoints or []):
            coords = self.nav.geocode(wp)
            if coords:
                wp_coords.append(coords)
                
        # Optimize waypoint order
        if len(wp_coords) > 2:
            pos = self.gps.get_current()
            start = (pos[0], pos[1], "Vị trí hiện tại")
            wp_coords = self.nav.optimize_waypoints_locally(start, wp_coords, dest_coords)
            
        self.current_destination = dest_coords
        self.current_waypoints = wp_coords
        self.is_navigating = True
        
        # Gửi thông báo về ESP32
        dest_name = dest_coords[2] if len(dest_coords) > 2 else destination_text
        self.send_text(f"TTS|Đang tìm đường đến {dest_name}. Vui lòng chờ...")
        
        # Lấy route lần đầu
        self._fetch_and_send_route()
        
        # Bắt đầu navigation loop
        if not self._nav_thread or not self._nav_thread.is_alive():
            self._nav_thread = threading.Thread(target=self._nav_loop, daemon=True)
            self._nav_thread.start()
            
    def _fetch_and_send_route(self):
        """Lấy route mới từ Google Maps và gửi về ESP32."""
        try:
            pos = self.gps.get_current()
            lat, lon, heading, acc = pos
            
            route = self.nav.get_route(
                lat, lon,
                self.current_destination,
                self.current_waypoints if self.current_waypoints else None
            )
            
            if route.get("status") != "OK":
                self.send_text(f"TTS|Lỗi tìm đường: {route.get('status', 'Không rõ')}")
                return
                
            self.current_route = route
            
            # Format và gửi MAP packet về ESP32
            polyline = route.get("polyline", [])
            nearby_cams = self.cam.get_nearby_cameras(lat, lon)
            cam_str = self.cam.format_for_ble(nearby_cams)
            
            map_packet = self.gps.format_for_ble(polyline, cam_str)
            self.send_text(map_packet)
            
            # Gửi thông tin ETA và distance
            eta_min = route.get("total_duration_min", 0)
            dist_km = route.get("total_distance_km", 0)
            self.send_text(f"TTS|Hành trình {dist_km}km, ước tính {eta_min} phút.")
            
            # Update web server status
            self.server.update_status(
                is_navigating=True,
                gps_lat=lat, gps_lon=lon,
                eta_min=eta_min,
                dist_remain_km=dist_km,
            )
            
        except Exception as e:
            print("[Nav] _fetch_and_send_route error:", e)
            
    def _nav_loop(self):
        """Navigation update loop đầy đủ - GPS + Route + Camera + Biển báo + Tốc độ."""
        last_instruction_text = ""
        _osm_update_counter = 0

        while self.is_navigating and self.is_connected:
            try:
                pos = self.gps.get_current()
                lat, lon, heading, acc = pos
                speed = self.gps.get_speed_kmh()

                # ─── 1. Hướng dẫn rẽ (Navigation) ───
                instruction = self.nav.get_current_instruction(lat, lon)
                inst_text = instruction.get("instruction", "")
                dist_turn = instruction.get("distance_to_turn_m", 0)
                maneuver = instruction.get("maneuver", "straight")
                self.send_text(f"TURN|{inst_text}|{dist_turn}|{maneuver}")

                # Đọc to hướng dẫn rẽ + xi-nhan reminder
                speak_text = instruction.get("speak_text", "")
                if speak_text and speak_text != last_instruction_text:
                    self.tts.speak_local(speak_text)
                    last_instruction_text = speak_text

                # ─── 2. Multi-source Camera Alert ───
                alert_packet = self.multi_alert.get_full_alert_packet(lat, lon, speed, heading)

                # Gửi ALERT packet về ESP32 (camera + speed limit + over-speed flag)
                ble_alert = alert_packet.get("ble_payload", "")
                if ble_alert:
                    self.send_text(ble_alert)

                # Đọc to cảnh báo camera
                cam_speak = alert_packet.get("speak_text", "")
                if cam_speak:
                    self.tts.speak_local(cam_speak)
                    cam_info = alert_packet.get("camera_alert")
                    if cam_info:
                        cam_text = self.multi_alert._build_camera_alert_text(cam_info, speed)
                        self.send_text(f"CAM_ALERT|{cam_text}")
                        self.server.update_status(camera_warning=cam_text)
                else:
                    self.server.update_status(camera_warning=None)

                # ─── 3. Sign Alert (Biển báo + Giới hạn tốc độ) ───
                sign_data = self.sign_alert.get_sign_alerts(lat, lon, speed)
                speed_limit = sign_data.get("speed_limit", 60)

                # Gửi biển báo về ESP32
                sign_packet = sign_data.get("ble_sign_packet", "")
                if sign_packet:
                    self.send_text(sign_packet)

                # Đọc to biển báo nếu có thay đổi
                for sign_speak in sign_data.get("speak_texts", []):
                    if sign_speak:
                        self.tts.speak_local(sign_speak)

                # Cảnh báo vượt tốc độ qua loa
                if sign_data.get("speed_over") and sign_data.get("speed_over_kmh", 0) > 20:
                    over_text = f"Cảnh báo vượt tốc độ {sign_data['speed_over_kmh']} km/h!"
                    self.send_text(f"SPEED_OVER|{int(speed)}|{speed_limit}")

                # ─── 4. Cập nhật Web Server ───
                self.server.update_status(
                    gps_lat=lat, gps_lon=lon,
                    speed_kmh=speed,
                    current_instruction=inst_text,
                    dist_to_turn=dist_turn,
                    ble_connected=self.is_connected,
                    speed_limit=speed_limit,
                    speed_over=sign_data.get("speed_over", False),
                )

                # ─── 5. STATUS tổng hợp về ESP32 ───
                self.send_text(f"STATUS|100|{int(speed)}|{int(acc)}m")

                # ─── 6. Cập nhật OSM region mỗi 5 phút (background) ───
                _osm_update_counter += 1
                if _osm_update_counter >= 37:  # ~37 * 8s ≈ 5 phút
                    _osm_update_counter = 0
                    threading.Thread(
                        target=lambda: self.osm.update_region(lat, lon, radius_km=20),
                        daemon=True
                    ).start()

                # ─── 7. Kiểm tra đến nơi ───
                if instruction.get("maneuver") == "arrive":
                    self.is_navigating = False
                    self.send_text("ARRIVED")
                    self.tts.speak_local("Bạn đã đến nơi! Chúc bạn một ngày tốt lành.")
                    self.server.update_status(is_navigating=False)
                    break

                # ─── 8. Re-fetch route định kỳ ───
                time.sleep(UPDATE_INTERVAL)
                self._fetch_and_send_route()

            except Exception as e:
                print("[Nav Loop] Lỗi:", e)
                import traceback
                traceback.print_exc()
                time.sleep(2)
                
    # ─────────────────────────────────────────────
    # XỬ LÝ MESSAGES TỪ ESP32
    # ─────────────────────────────────────────────
    def _handle_esp32_message(self, msg):
        """Xử lý message nhận từ ESP32."""
        msg = msg.strip()
        print(f"[BLE ←] {msg[:80]}")
        
        if msg == "REQ_UPDATE":
            # ESP32 yêu cầu update GPS + route
            if self.is_navigating:
                threading.Thread(target=self._fetch_and_send_route, daemon=True).start()
                
        elif msg.startswith("VOICE|"):
            # Nhận text giọng nói đã được STT từ ESP32
            text = msg[6:]
            threading.Thread(target=self._process_voice_command, args=(text,), daemon=True).start()
            
        elif msg.startswith("NAV_REQUEST|"):
            # Yêu cầu điều hướng đến địa điểm
            destination = msg[12:]
            threading.Thread(target=self.start_navigation, args=(destination,), daemon=True).start()
            
        elif msg == "STOP_NAV":
            self.is_navigating = False
            self.send_text("TTS|Hành trình đã dừng.")
            
    def _process_voice_command(self, text):
        """Xử lý text lệnh từ giọng nói (nhận từ ESP32)."""
        text_lower = text.lower().strip()
        print(f"[Voice] Lệnh: '{text}'")
        
        # Parse command
        if any(x in text_lower for x in ["đi đến", "đến", "tới", "navigate to"]):
            # Trích xuất địa điểm
            for keyword in ["đi đến", "đến", "tới", "navigate to"]:
                if keyword in text_lower:
                    destination = text_lower.split(keyword, 1)[1].strip()
                    if destination:
                        self.start_navigation(destination)
                        return
            self.send_text("TTS|Bạn muốn đến đâu? Vui lòng nói lại.")
            
        elif any(x in text_lower for x in ["dừng", "hủy", "thôi"]):
            self.is_navigating = False
            self.send_text("TTS|Đã dừng dẫn đường.")
            
        elif any(x in text_lower for x in ["pin", "bao nhiêu"]):
            self.send_text("TTS|Chức năng đo pin đang cập nhật.")
            
        else:
            self.send_text(f"TTS|Tôi chưa hiểu lệnh: {text[:30]}")

    # ─────────────────────────────────────────────
    # CORLEYBLUETOOTH DELEGATES (Pythonista cb module)
    # ─────────────────────────────────────────────
    def did_discover_peripheral(self, peripheral, adv_data, rssi):
        if BLE_TARGET_NAME in peripheral.name:
            print(f"[BLE] Tìm thấy {peripheral.name} (RSSI: {rssi})")
            cb.stop_scan()
            cb.connect_peripheral(peripheral)
            
    def did_connect_peripheral(self, peripheral):
        print(f"[BLE] Đã kết nối {peripheral.name} ✅")
        self.peripheral = peripheral
        self.is_connected = True
        peripheral.discover_services()
        self.server.update_status(ble_connected=True)
        
    def did_disconnect_peripheral(self, peripheral, error):
        print("[BLE] Mất kết nối, đang tái kết nối...")
        self.is_connected = False
        self.rx_char = None
        self.server.update_status(ble_connected=False)
        time.sleep(3)
        cb.scan_for_peripherals()
        
    def did_discover_services(self, peripheral, error):
        for service in peripheral.services:
            if UART_SERVICE.lower() in str(service.uuid).lower():
                peripheral.discover_characteristics(service)
                
    def did_discover_characteristics(self, service, error):
        for char in service.characteristics:
            uuid = str(char.uuid).lower()
            if TX_CHAR_UUID.lower() in uuid:
                self.peripheral.set_notify_value(char, True)  # Nhận từ ESP32
            elif RX_CHAR_UUID.lower() in uuid:
                self.rx_char = char  # Gửi về ESP32
        print("[BLE] UART characteristics ready!")
        self._start_nav_loop()
        
    def _start_nav_loop(self):
        """Gọi sau khi BLE ready - phát TTS chào và bắt đầu listen."""
        time.sleep(0.5)
        self.send_text("TTS|iPhone đã kết nối. Hệ thống sẵn sàng!")
        
    def did_update_value(self, characteristic, error):
        """Nhận data từ ESP32."""
        if characteristic.value:
            chunk = characteristic.value.decode('utf-8', errors='ignore')
            self._msg_buffer += chunk
            # Xử lý khi nhận được dòng hoàn chỉnh
            while "\n" in self._msg_buffer:
                line, self._msg_buffer = self._msg_buffer.split("\n", 1)
                if line:
                    self._handle_esp32_message(line)

# ═══════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════
if __name__ == "__main__":
    print("\n" + "="*60)
    print("  TEQUILA NAVIGATOR - iPhone Full Service")
    print("  Camera + Biển báo + Tốc độ + WYN + Waze")
    print("="*60)
    print("\n⚠️  HƯỚNG DẪN THIẾT LẬP:")
    print("1. Cài WYN từ App Store và bật Overlay Mode (miễn phí)")
    print("2. Đảm bảo ESP32 đang bật và advertising 'VMN-Compact'")
    print("3. Mở file này trong Pythonista 3 và nhấn Run (KHÔNG CẦN ĐIỀN API KEY NÀO!)")
    print("4. Mở Safari → http://localhost:8080 để điều khiển")
    print("\nLần đầu chạy: OSM camera VN sẽ được tải về (~30 giây)\n")

    app = TequilaNavigatorIOS()

    # Lần đầu: tải OSM camera data cho VN (background)
    def first_run_osm_update():
        if len(app.osm.cameras) < 10:
            print("[Setup] Tải camera data từ OpenStreetMap VN...")
            app.osm.update_from_osm()  # ~30-60 giây
            app.multi_alert.merge_all_cameras()  # Re-merge sau khi có OSM data
            print(f"[Setup] Hoàn thành! Tổng: {app.multi_alert.get_stats()}")

    threading.Thread(target=first_run_osm_update, daemon=True).start()

    app.start()

    # Giữ chạy
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[iOS] Dừng bởi user.")
        app.gps.stop()
