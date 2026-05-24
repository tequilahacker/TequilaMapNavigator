# iphone/wifi_navigator_ios.py
# Pythonista 3 - WiFi Client & Navigation Orchestrator cho iPhone 14 Pro
# PHIÊN BẢN ĐẦY ĐỦ: Google Maps + WYN + Waze + Biển báo qua WiFi HTTP
#
# Cách chạy:
# 1. Bật Personal Hotspot trên iPhone 14 Pro.
# 2. Bật ESP32 để kết nối vào Hotspot.
# 3. Chạy file này trên ứng dụng Pythonista 3 trên iPhone.
# 4. Mở Safari trên iPhone truy cập http://localhost:8080 để điều khiển.

import time
import json
import threading
import math

try:
    import speech    # Loa TTS native iOS
    import location  # GPS native iOS
    HAS_PYTHONISTA = True
except ImportError:
    HAS_PYTHONISTA = False
    print("[iOS WiFi] Đang chạy ngoài Pythonista, dùng mock GPS.")

import requests
from navigation_engine import NavigationEngine
from camera_alert import CameraAlertEngine
from tts_handler import TTSHandler
from gps_tracker import GPSTracker
from web_server import NavigatorWebServer

# Engines nạp từ hệ thống alert đa nguồn (miễn phí)
from osm_speed_engine import OSMSpeedEngine
from waze_scraper import WazeScraper
from multi_alert_engine import MultiAlertEngine
from sign_alert_engine import SignAlertEngine
from wyn_waze_bridge import WYNWazeBridge

# Cấu hình IP và chu kỳ
DEFAULT_ESP32_IP = "172.20.10.2"  # Địa chỉ mặc định của ESP32 khi bắt Hotspot
UPDATE_INTERVAL  = 5               # Cập nhật vị trí GPS lên màn hình xe mỗi 5 giây
import os as _os
_BASE_DIR = _os.path.dirname(_os.path.abspath(__file__))
CAMERA_CSV_PATH  = _os.path.join(_BASE_DIR, "..", "data", "camera_phat_nguoi.csv")
GOOGLE_MAPS_KEY  = "AIzaSyB11vo0te9tTtdBZogm3ltE2X7lHN20zfQ"  # Google Maps API Key
CAMERA_WARN_DIST_M = 50           # Cảnh báo camera phạt nguội trước 50 mét


class TequilaNavigatorWiFiIOS:
    """Bộ điều phối trung tâm chạy trên iPhone 14 Pro, truyền dữ liệu qua WiFi HTTP."""
    
    def __init__(self, esp32_ip=DEFAULT_ESP32_IP):
        self.esp32_ip = esp32_ip
        self.is_navigating = False
        self._nav_thread = None
        self._last_speed_limit = None
        self._last_instruction_text = ""
        self._announced_blinkers = set()  # Lưu các điểm rẽ đã phát xi-nhan
        
        print("[iOS] Khởi tạo Navigation Engine...")
        self.nav = NavigationEngine(api_key=GOOGLE_MAPS_KEY if GOOGLE_MAPS_KEY else None)
        
        print("[iOS] Khởi tạo Waze Scraper...")
        self.waze = WazeScraper()
        
        print("[iOS] Khởi tạo OSM Speed Engine...")
        self.osm = OSMSpeedEngine()
        
        print("[iOS] Khởi tạo Camera Alert Engine (CSV)...")
        self.cam = CameraAlertEngine(csv_path=CAMERA_CSV_PATH)
        
        print("[iOS] Khởi tạo GPS Tracker...")
        self.gps = GPSTracker()
        
        print("[iOS] Khởi tạo TTS Handler...")
        self.tts = TTSHandler(ble_handler=None)  # Chỉ dùng phát local vào mũ bảo hiểm
        
        print("[iOS] Khởi tạo Multi Alert Engine (OSM+Waze+CSV)...")
        self.multi_alert = MultiAlertEngine(
            osm_engine=self.osm,
            waze_scraper=self.waze,
            csv_engine=self.cam
        )
        self.multi_alert.merge_all_cameras()  # Trộn camera ngay khi boot
        
        print("[iOS] Khởi tạo Sign Alert Engine (Biển báo)...")
        self.sign_alert = SignAlertEngine(osm_engine=self.osm)
        
        print("[iOS] Khởi tạo WYN/Waze Bridge...")
        self.wyn_waze = WYNWazeBridge()
        
        # Cấu hình Web Server Companion
        print("[iOS] Khởi tạo Web Server Companion (Port 8080)...")
        self.server = NavigatorWebServer(
            port=8080,
            nav_engine=self.nav,
            esp32_ip=self.esp32_ip,
            camera_engine=self.multi_alert,
            gps_tracker=self.gps
        )
        # Đồng bộ trạng thái web server ngược lại bộ điều phối
        self.server.nav_engine = self.nav
        self.server.cam_engine = self.multi_alert
        
    def start(self):
        """Khởi động web server và bắt đầu vòng lặp giám sát định vị nền."""
        self.server.start()
        print("\n" + "="*50)
        print("  TEQUILA NAVIGATOR COMPANION - ĐANG HOẠT ĐỘNG")
        print(f"  Web Dashboard: http://localhost:8080")
        print(f"  Kết nối ESP32 tại: http://{self.esp32_ip}")
        print("="*50 + "\n")
        
        # Gửi lời chào xác nhận hệ thống sẵn sàng qua Loa xe máy cực bộ
        saved = self.server._load_journey_state()
        if saved and saved.get("destination"):
            msg = "Xin chào Ngài Tequila, hôm nay Ngài muốn đi đâu. À, tôi thấy Ngài có một hành trình chưa hoàn thành. Ngài có muốn tiếp tục quãng đường cũ không?"
            self.server.status["pending_resume"] = True
        else:
            msg = "Xin chào Ngài Tequila, hôm nay Ngài muốn đi đâu?"
            self.server.status["pending_resume"] = False
            
        self.server.trigger_voice_alert(msg)
        
        # Chạy luồng giám sát thay đổi trạng thái từ Web UI
        threading.Thread(target=self._state_monitor_loop, daemon=True).start()

    def send_to_esp32(self, endpoint, data):
        """Lưu dữ liệu vào trạng thái Cloud hoặc gửi trực tiếp tới HTTP server của ESP32 qua WiFi."""
        # 1. Luôn lưu vào trạng thái Cloud/State để ESP32 có thể poll
        if hasattr(self, 'server') and self.server:
            if endpoint == "update":
                self.server.device_state["update"] = data
            elif endpoint == "alert":
                self.server.device_state["alert"] = data
            elif endpoint == "voice":
                self.server.device_state["voice"] = data
            elif endpoint == "stop":
                self.server.device_state["stop"] = True
                
        # 2. Nếu chạy local, thử gửi trực tiếp ngầm cho nhanh
        self.esp32_ip = self.server.esp32_ip
        url = f"http://{self.esp32_ip}/{endpoint}"
        
        def send_bg():
            try:
                requests.post(url, json=data, timeout=1.0)
            except Exception:
                pass
                
        threading.Thread(target=send_bg, daemon=True).start()
        return True

    def _state_monitor_loop(self):
        """Luồng giám sát trạng thái bắt đầu/dừng dẫn đường từ giao diện Web UI."""
        while True:
            # Kiểm tra trạng thái đồng bộ từ Server Web UI
            web_navigating = self.server.status.get("is_navigating", False)
            
            if web_navigating and not self.is_navigating:
                # Web UI bắt đầu dẫn đường
                print("[State] Phát hiện yêu cầu điều hướng mới từ Web Dashboard!")
                self.is_navigating = True
                
                # Bắt đầu vòng lặp tracking hành trình
                if not self._nav_thread or not self._nav_thread.is_alive():
                    self._nav_thread = threading.Thread(target=self._nav_loop, daemon=True)
                    self._nav_thread.start()
                    
            elif not web_navigating and self.is_navigating:
                # Web UI dừng dẫn đường
                print("[State] Hành trình đã dừng từ Web Dashboard.")
                self.is_navigating = False
                
            time.sleep(1.0)

    def _nav_loop(self):
        """Vòng lặp định vị real-time, quét biển báo, tốc độ, xi-nhan & đẩy lên ESP32."""
        last_announced_speed_warning = 0
        osm_update_counter = 0
        
        # Khởi động ứng dụng WYN và Waze chạy song song/overlay trên iPhone 14 Pro
        try:
            print("[Nav] Khởi động WYN và Waze chạy song song...")
            pos = self.gps.get_current()
            self.wyn_waze.start_parallel_navigation(pos[0], pos[1], "Hành trình Tequila", prefer_wyn=True, open_waze=True)
        except Exception as e:
            print("[Nav] Lỗi khởi động WYN/Waze song song:", e)
            
        while self.is_navigating:
            try:
                # 1. Lấy vị trí và tốc độ GPS hiện tại từ iPhone 14 Pro
                pos = self.gps.get_current()
                lat, lon, heading, acc = pos
                speed = self.gps.get_speed_kmh()
                
                # Đồng bộ tốc độ, GPS lên Web Server
                self.server.update_status(gps_lat=lat, gps_lon=lon, speed_kmh=speed)
                
                # 2. Xử lý dẫn đường Turn-by-Turn & Báo xi-nhan rẽ
                instruction_data = self.nav.get_current_instruction(lat, lon)
                inst_text = instruction_data.get("instruction", "Đi thẳng")
                dist_turn = instruction_data.get("distance_to_turn_m", 0)
                maneuver = instruction_data.get("maneuver", "straight")
                speak_text = instruction_data.get("speak_text", "")
                
                # Phát âm nhắc rẽ + Nhắc bật xi-nhan trực tiếp qua Loa xe máy cực bộ
                if speak_text and speak_text != self._last_instruction_text:
                    print(f"[TTS Audio] Đang đọc ra loa xe máy: {speak_text}")
                    self.server.trigger_voice_alert(speak_text)
                    self._last_instruction_text = speak_text
                
                # 3. Lấy thông tin biển báo & camera phạt nguội đa nguồn (OSM+Waze+CSV)
                alert_packet = self.multi_alert.get_full_alert_packet(lat, lon, speed, heading,
                                                                       warn_dist_m=CAMERA_WARN_DIST_M)
                speed_limit = alert_packet.get("speed_limit", 60)
                speed_over = alert_packet.get("speed_over", False)
                
                # Đọc to cảnh báo camera phạt nguội qua Loa xe máy cực bộ trước 50m
                cam_speak = alert_packet.get("speak_text", "")
                if cam_speak:
                    print(f"[TTS Camera Alert] Đọc ra loa xe máy: {cam_speak}")
                    self.server.trigger_voice_alert(cam_speak)
                
                # Cảnh báo vượt tốc độ quy định qua Loa xe máy cực bộ
                if speed > (speed_limit + 5):
                    now = time.time()
                    if now - last_announced_speed_warning > 300:  # cách 5 phút (300s) thông báo 1 lần
                        over_msg = f"yêu cầu chạy đúng tốc độ quy định {speed_limit} km/g"
                        print(f"[TTS Speed Warning] Đọc ra loa xe máy: {over_msg}")
                        self.server.trigger_voice_alert(over_msg)
                        last_announced_speed_warning = now
                
                # 4. Gửi dữ liệu định vị & bản đồ vector lên ESP32 để render HUD
                # Chuẩn hóa polyline vẽ đường (chỉ lấy 30 điểm gần nhất để tiết kiệm RAM ESP32)
                full_poly = self.nav.current_route_steps
                route_payload = []
                if len(full_poly) > self.nav.current_step_index:
                    # Trích xuất toạ độ các step còn lại
                    route_payload = [[step["lat"], step["lon"]] for step in full_poly[self.nav.current_step_index:self.nav.current_step_index+20]]
                
                # Danh sách camera phạt nguội xung quanh gửi lên map HUD
                cams_nearby = [{"lat": c["lat"], "lon": c["lon"], "type": c["type"]} 
                               for c in alert_packet.get("cameras_nearby", [])]

                update_payload = {
                    "lat": lat,
                    "lon": lon,
                    "heading": heading,
                    "speed": speed,
                    "route": route_payload,
                    "cameras": cams_nearby
                }
                
                # Đẩy GPS & Bản đồ lên ESP32
                self.send_to_esp32("update", update_payload)
                
                # Đẩy dữ liệu tốc độ và cảnh báo bíp lên ESP32
                alert_payload = {
                    "speed_limit": speed_limit,
                    "current_speed": speed,
                    "speed_over": speed_over,
                    "camera_dist": alert_packet.get("camera_alert", {}).get("distance_m", 9999) if alert_packet.get("camera_alert") else 9999,
                    "camera_type": alert_packet.get("camera_alert", {}).get("type", "speed") if alert_packet.get("camera_alert") else "speed"
                }
                self.send_to_esp32("alert", alert_payload)
                
                # Đồng bộ trạng thái web UI
                self.server.update_status(
                    current_instruction=inst_text,
                    dist_to_turn=dist_turn,
                    eta_min=alert_packet.get("eta_seconds", 0) // 60 or self.server.status.get("eta_min"),
                    dist_remain_km=alert_packet.get("dist_remain_km") or self.server.status.get("dist_remain_km"),
                    camera_warning=alert_packet.get("camera_alert", {}).get("desc") if alert_packet.get("camera_alert") else None
                )
                
                # 5. Kiểm tra điều kiện đã đến đích để tự động thoát
                if instruction_data.get("maneuver") == "arrive":
                    print("[Nav] 🎉 Đã đến điểm đích!")
                    self.is_navigating = False
                    self.server.update_status(is_navigating=False)
                    self.server.trigger_voice_alert("Bạn đã đến điểm đích thành công. Hành trình kết thúc.")
                    time.sleep(2)
                    self.send_to_esp32("stop", {})
                    break
                    
                # 6. Tải cập nhật dữ liệu khu vực mới từ OSM định kỳ (mỗi 5 phút)
                osm_update_counter += 1
                if osm_update_counter >= 75:  # 75 * 4s = 300 giây (5 phút)
                    osm_update_counter = 0
                    threading.Thread(
                        target=lambda: self.osm.update_region(lat, lon, radius_km=15),
                        daemon=True
                    ).start()
                
            except Exception as e:
                print(f"[Nav Loop] Lỗi vòng lặp dẫn đường: {e}")
                
            time.sleep(4.0)  # Vòng lặp định vị 4 giây/lần phù hợp tốc độ xe máy và tiết kiệm pin iPhone


if __name__ == "__main__":
    app = TequilaNavigatorWiFiIOS()
    
    # Kiểm tra và tải trước cơ sở dữ liệu biển báo OSM cho Việt Nam
    def first_run_setup():
        if len(app.osm.cameras) < 10:
            print("[Setup] Khởi chạy đầu tiên: Tải danh mục camera/biển báo Việt Nam...")
            app.osm.update_from_osm()
            app.multi_alert.merge_all_cameras()
            print("[Setup] Hoàn tất nạp dữ liệu!")
            
    threading.Thread(target=first_run_setup, daemon=True).start()
    
    # Khởi chạy bộ điều phối
    app.start()
    
    # Giữ luồng chính hoạt động
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Companion] Đang dừng...")
        app.gps.stop()
        app.server.stop()
