# esp32/main.py
# Tequila Motorcycle Navigator - Main Application Entry Point
# MicroPython cho ESP32-S3 + 2.8" IPS TFT + INMP441 + MAX98357
import time
import machine
import lvgl as lv

import config
from greeting import GreetingScreen
from journey_state import JourneyStateManager
from wifi_http_server import WiFiHTTPServer   # ← Thay BLEHandler
from voice_handler import VoiceHandler
from lvgl_map_2_8 import MapDisplay
from battery_manager import BatteryManager

# ═══════════════════════════════════════════════════
# TRẠNG THÁI THIẾT BỊ (State Machine)
# ═══════════════════════════════════════════════════
STATE_BOOTING     = "booting"
STATE_IDLE        = "idle"          # Chờ kết nối iPhone
STATE_READY       = "ready"         # iPhone kết nối, chờ lệnh
STATE_LISTENING   = "listening"     # Đang thu giọng nói
STATE_FETCHING    = "fetching"      # Chờ iPhone xử lý
STATE_NAVIGATING  = "navigating"    # Đang dẫn đường
STATE_ARRIVED     = "arrived"       # Đã đến nơi

current_state = STATE_BOOTING

# ═══════════════════════════════════════════════════
# KHỞI TẠO HARDWARE
# ═══════════════════════════════════════════════════
def init_display():
    """Khởi tạo LVGL và display driver."""
    lv.init()
    # Display driver tùy board - phổ biến nhất là ST7789 hoặc ILI9341
    try:
        from ili9xxx import ILI9341
        drv = ILI9341(
            mosi=config.TFT_MOSI, clk=config.TFT_CLK, cs=config.TFT_CS,
            dc=config.TFT_DC, rst=config.TFT_RST,
            width=config.DISPLAY_WIDTH, height=config.DISPLAY_HEIGHT,
            rot=config.DISPLAY_ROTATION
        )
    except ImportError:
        # Fallback nếu không có driver
        print("[Display] ILI9341 driver không có, dùng framebuffer mock.")
        drv = None
    return drv

def init_touch():
    """Khởi tạo capacitive touch controller (FT6236 phổ biến trên 2.8" boards)."""
    try:
        from ft6x36 import FT6x36
        tp = FT6x36(i2c=machine.I2C(0, sda=config.I2C_SDA, scl=config.I2C_SCL, freq=400000))
        return tp
    except Exception as e:
        print("[Touch] Khởi tạo lỗi:", e)
        return None

def check_power_source():
    """Kiểm tra xe đang bật (ACC pin) hay không."""
    try:
        acc_adc = machine.ADC(machine.Pin(config.ACC_PIN))
        acc_adc.atten(machine.ADC.ATTN_11DB)
        raw = acc_adc.read()
        voltage = (raw / 4095.0) * 3.6 * 3  # Voltage divider 1:3
        print(f"[Power] ACC voltage: {voltage:.2f}V")
        return voltage > 5.0  # > 5V = xe đang bật
    except Exception:
        return True  # Assume on nếu không có ACC pin

# ═══════════════════════════════════════════════════
# XỬ LÝ LỆNH GIỌNG NÓI
# ══════════════════════════════════# ═══════════════════════════════════════════════════
# Xử LÝ DỮ LIỆU TỪ HTTP (thay process_ble_message)
# Các callback này được gán vào wifi_server.on_* trong main()
# ═══════════════════════════════════════════════════

def make_on_update(map_display, journey):
    """Tạo callback cho POST /update."""
    def on_update(lat, lon, heading, speed, route, cameras):
        global current_state
        # Chuyển route từ [[lat,lon],...] sang [(lat,lon),...]
        route_tuples = [(r[0], r[1]) for r in route if len(r) >= 2]
        # Chuyển cameras từ [{lat,lon,type},...] sang format map_display
        cam_list = []
        for c in cameras:
            try:
                cam_list.append({"lat": float(c["lat"]), "lon": float(c["lon"]),
                                  "type": c.get("type", "speed")})
            except (KeyError, ValueError):
                pass

        map_display.update_position(lat, lon, heading)
        if route_tuples:
            map_display.update_route(route_tuples)
        if cam_list:
            map_display.update_cameras(cam_list)
        if speed > 0:
            map_display.update_navigation_data(
                map_display.alert_label.get_text().split("\n")[0], speed, 0
            )
        journey.update_position(lat, lon, heading)
        current_state = STATE_NAVIGATING
    return on_update


def make_on_alert(map_display, voice):
    """Tạo callback cho POST /alert."""
    def on_alert(speed_limit, current_speed, speed_over, camera_dist, camera_type):
        map_display.update_speed_limit(speed_limit)
        map_display.update_navigation_data(
            map_display.alert_label.get_text().split("\n")[0],
            current_speed, 0
        )
        if speed_over:
            map_display.show_notification(f"⚠️ Vượt tốc độ! {int(current_speed)}/{speed_limit}km/h", 4000)
            voice.play_beep(1200, 600)
        if camera_dist < config.CAMERA_ALERT_DIST:
            cam_label = "Tốc độ" if camera_type == "speed" else "Vượt đèn đỏ"
            map_display.show_camera_alert(f"CAMERA {cam_label.upper()} − {int(camera_dist)}m")
            voice.play_beep(880, 400)
    return on_alert


def make_on_voice(map_display, voice):
    """Tạo callback cho POST /voice."""
    def on_voice(data, is_audio=False):
        if is_audio:
            # Ghi trực tiếp dữ liệu nhị phân thô xuống I2S Speaker (MAX98357)
            if hasattr(voice, 'audio_out') and voice.audio_out:
                try:
                    voice.audio_out.write(data)
                except Exception as e:
                    print("[Voice Callback] Lỗi phát âm thanh nhị phân:", e)
        else:
            # Hiển thị thông báo dạng văn bản chữ lên màn hình
            map_display.show_notification(data)
    return on_voice


def make_on_stop(map_display, journey):
    """Tạo callback cho POST /stop."""
    def on_stop():
        global current_state
        current_state = STATE_READY
        map_display.show_screen_state("ready")
        map_display.clear_routes_selection()
        journey.clear()
        print("[HTTP] Dừng dẫn đường.")
    return on_stop


def make_on_show_routes(map_display, wifi_server):
    """Tạo callback cho POST /show-routes."""
    def on_show_routes(routes):
        def select_route_callback(idx):
            # Gửi HTTP POST /api/select-route lên iPhone Hotspot Gateway
            try:
                iphone_ip = wifi_server.wlan.ifconfig()[2]
                import socket
                import json
                s = socket.socket()
                s.settimeout(3.0)
                s.connect((iphone_ip, 8080))
                payload = json.dumps({"route_index": idx}).encode("utf-8")
                req = (
                    "POST /api/select-route HTTP/1.1\r\n"
                    "Host: localhost\r\n"
                    "Content-Type: application/json\r\n"
                    "Content-Length: %d\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                ) % len(payload)
                s.send(req.encode() + payload)
                s.close()
                print("[Main] Đã gửi lựa chọn tuyến %d lên iPhone!" % idx)
            except Exception as e:
                print("[Main] Lỗi gửi lựa chọn tuyến đường:", e)
                
        # Hiển thị trình chọn 3 tuyến đường trên màn hình
        map_display.show_routes(routes, select_route_callback)
    return on_show_routes

# ═══════════════════════════════════════════════════
# NÚT WAKE WORD / VOICE TRIGGER
# ═══════════════════════════════════════════════════
def setup_wake_button():
    """Cấu hình nút GPIO để kích hoạt voice command."""
    btn = machine.Pin(config.WAKE_BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
    return btn

# ═══════════════════════════════════════════════════
# Xử LÝ LỆNH GIỌNG NÓI
# ═══════════════════════════════════════════════════
def handle_voice_command(command_text):
    """Xử lý text lệnh nhận được (từ nút vật lý hoặc local STT)."""
    global current_state
    cmd = command_text.strip().lower()
    
    if any(x in cmd for x in ["dừng", "hủy", "thôi"]):
        return "STOP"
    elif any(x in cmd for x in ["đi đến", "đến", "tới", "navigate"]):
        return "NAVIGATE"
    elif any(x in cmd for x in ["thêm điểm", "dừng ở", "ghé"]):
        return "ADD_WAYPOINT"
    elif any(x in cmd for x in ["ở đâu", "vị trí", "where"]):
        return "WHERE_AM_I"
    elif any(x in cmd for x in ["pin", "battery", "bao nhiêu"]):
        return "BATTERY_STATUS"
    else:
        return "UNKNOWN"


def poll_cloud_server(server_ip_or_host):
    """Gửi một HTTP GET request đến Cloud Server để kéo thông tin hành trình và cảnh báo."""
    import socket
    import json
    
    if config.USE_CLOUD_SERVER:
        host = config.CLOUD_SERVER_HOST
        port = config.CLOUD_SERVER_PORT
        use_ssl = config.CLOUD_SERVER_SSL
    else:
        # Fallback local polling nếu cần
        host = server_ip_or_host
        port = 8080
        use_ssl = False
        
    try:
        addr = socket.getaddrinfo(host, port)[0][-1]
        s = socket.socket()
        s.settimeout(2.5) # Giới hạn timeout ngắn tránh đơ UI
        s.connect(addr)
        
        # Nếu dùng HTTPS, bọc socket với SSL
        if use_ssl:
            try:
                import ussl
                s = ussl.wrap_socket(s, server_hostname=host)
            except Exception:
                try:
                    import ssl
                    s = ssl.wrap_socket(s, server_hostname=host)
                except Exception:
                    pass
                    
        # Yêu cầu GET để poll trạng thái của thiết bị
        request = (
            f"GET /api/poll-device HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode()
        s.send(request)
        
        # Nhận toàn bộ phản hồi
        response = bytearray()
        while True:
            chunk = s.recv(1024)
            if not chunk:
                break
            response.extend(chunk)
        s.close()
        
        # Tách Header và Body
        resp_str = response.decode('utf-8', 'ignore')
        parts = resp_str.split("\r\n\r\n", 1)
        if len(parts) < 2:
            return None
            
        body = parts[1].strip()
        if not body:
            return None
        data = json.loads(body)
        return data
    except Exception as e:
        # Giảm thiểu log in ra màn hình để tránh trôi log
        # print("[Poll] Lỗi kết nối đám mây:", e)
        return None


def play_audio_from_cloud(voice_handler, server_ip_or_host):
    """Tải và phát trực tiếp luồng âm thanh PCM nhị phân từ máy chủ đám mây qua Loa xe máy."""
    import socket
    if config.USE_CLOUD_SERVER:
        host = config.CLOUD_SERVER_HOST
        port = config.CLOUD_SERVER_PORT
        use_ssl = config.CLOUD_SERVER_SSL
    else:
        host = server_ip_or_host
        port = 8080
        use_ssl = False
        
    try:
        addr = socket.getaddrinfo(host, port)[0][-1]
        s = socket.socket()
        s.settimeout(5.0)
        s.connect(addr)
        if use_ssl:
            try:
                import ussl
                s = ussl.wrap_socket(s, server_hostname=host)
            except Exception:
                try:
                    import ssl
                    s = ssl.wrap_socket(s, server_hostname=host)
                except Exception:
                    pass
                    
        # Yêu cầu GET tải file pcm thô
        request = (
            f"GET /api/get-audio HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode()
        s.send(request)
        
        # Đọc phản hồi và bỏ qua HTTP headers
        response_started = False
        header_buf = bytearray()
        
        # Đọc từng byte để lọc header \r\n\r\n
        chunk = bytearray(1)
        while not response_started:
            if s.readinto(chunk) > 0:
                header_buf.extend(chunk)
                if header_buf.endswith(b"\r\n\r\n"):
                    response_started = True
            else:
                break
                
        # Phát trực tiếp dữ liệu âm thanh nhị phân còn lại vào I2S Speaker
        audio_chunk = bytearray(512) # Chunk 512 bytes tối ưu cho I2S
        while True:
            bytes_read = s.readinto(audio_chunk)
            if bytes_read > 0:
                if hasattr(voice_handler, 'audio_out') and voice_handler.audio_out:
                    try:
                        voice_handler.audio_out.write(audio_chunk[:bytes_read])
                    except Exception:
                        pass
            else:
                break
        s.close()
    except Exception as e:
        print("[Voice Stream] Lỗi phát âm thanh:", e)


# ═══════════════════════════════════════════════════
# VÒNG LẶP CHÍNH
# ═══════════════════════════════════════════════════
def main():
    global current_state
    
    print("\n" + "="*50)
    print("  TEQUILA MOTORCYCLE NAVIGATOR - BOOTING")
    print("="*50 + "\n")
    
    # 1. Khởi tạo hardware
    print("[Boot] Khởi tạo màn hình...")
    display_drv = init_display()
    
    print("[Boot] Khởi tạo touch...")
    touch = init_touch()
    
    print("[Boot] Khởi tạo battery manager...")
    battery = BatteryManager(config.BATTERY_ADC_PIN)
    
    print("[Boot] Khởi tạo voice handler...")
    voice = VoiceHandler(
        i2s_mic_sck=config.MIC_SCK, i2s_mic_ws=config.MIC_WS, i2s_mic_sd=config.MIC_SD,
        i2s_spk_sck=config.SPK_SCK, i2s_spk_ws=config.SPK_WS, i2s_spk_sd=config.SPK_SD,
    )
    
    print("[Boot] Khởi tạo journey state manager...")
    journey = JourneyStateManager()
    
    print("[Boot] Khởi tạo LVGL map display...")
    map_display = MapDisplay(display_drv, touch)
    
    print("[Boot] Khởi tạo WiFi HTTP Server (thay BLE)...")
    wifi_server = WiFiHTTPServer()
    wifi_ok = wifi_server.connect_wifi()
    if wifi_ok:
        wifi_server.start()
        
        # Bắn tín hiệu Boot thông báo cho iPhone Companion
        try:
            iphone_ip = wifi_server.wlan.ifconfig()[2]
            print("[Boot] Đang gửi thông báo Boot lên iPhone: %s" % iphone_ip)
            import socket
            s = socket.socket()
            s.settimeout(2.0)
            s.connect((iphone_ip, 8080))
            req = "POST /api/boot HTTP/1.1\r\nHost: localhost\r\nContent-Length: 0\r\n\r\n"
            s.send(req.encode())
            s.close()
            print("[Boot] Đã gửi thông báo Boot thành công!")
        except Exception as e:
            print("[Boot] Không thể gửi thông báo Boot lên iPhone:", e)

        # Gán callbacks
        wifi_server.on_update = make_on_update(map_display, journey)
        wifi_server.on_alert  = make_on_alert(map_display, voice)
        wifi_server.on_voice  = make_on_voice(map_display, voice)
        wifi_server.on_stop   = make_on_stop(map_display, journey)
        wifi_server.on_show_routes = make_on_show_routes(map_display, wifi_server)
        map_display.show_notification(f"WiFi OK − IP: {wifi_server.ip}")
        map_display.update_connection_status(True)
    else:
        map_display.show_notification("⚠️ Không có WiFi! Kiểm tra hotspot iPhone.")
        map_display.update_connection_status(False)
    
    # 2. Boot greeting sequence
    print("[Boot] Chạy boot greeting...")
    greeting = GreetingScreen(audio_out=voice.speaker)
    boot_result = greeting.run_boot_sequence(journey, audio_out=voice.speaker)
    
    # 3. Check ACC pin (xe có đang bật không)
    engine_on = check_power_source()
    print(f"[Boot] ACC power: {'ON' if engine_on else 'OFF'}")
    
    # 4. Resume hoặc fresh start
    if boot_result == 'resume':
        journey.load()
        current_state = STATE_NAVIGATING
        map_display.show_notification("Đang tiếp tục hành trình cũ...")
        print("[Boot] Resume journey từ flash.")
    else:
        current_state = STATE_IDLE
        
    # 5. Load màn hình chính
    map_display.show_screen_state("idle")
    
    # 7. Cấu hình wake button
    wake_btn = setup_wake_button()
    last_btn_state = 1
    
    # 8. Timer thực hiện update định kỳ
    last_update_ms = time.ticks_ms()
    last_save_ms = time.ticks_ms()
    last_poll_ms = time.ticks_ms()
    UPDATE_INTERVAL_MS = 8000   # 8 giây request update GPS
    SAVE_INTERVAL_MS = 30000    # 30 giây auto-save journey
    
    print("\n[Main] ✅ Hệ thống sẵn sàng! Vào vòng lặp chính.\n")
    
    # ═══════ MAIN LOOP ═══════
    while True:
        now_ms = time.ticks_ms()
        lv.task_handler()  # Cần gọi liên tục để LVGL render
        
        # ─── Kiểm tra kích hoạt giọng nói (VAD) hoặc nút bấm ───
        btn_state = wake_btn.value()
        trigger_recording = False
        
        # 1. Kích hoạt bằng nút nhấn (GPIO0)
        if btn_state == 0 and last_btn_state == 1:
            print("[Wake] Kích hoạt bằng nút nhấn vật lý!")
            trigger_recording = True
            
        # 2. Kích hoạt tự động bằng giọng nói (VAD) khi đang rảnh tay
        elif current_state in (STATE_READY, STATE_NAVIGATING):
            # Đo cường độ âm thanh trong 80ms
            if voice.detect_vad_trigger(threshold_db=4000, check_duration_ms=80):
                print("[Wake] Kích hoạt rảnh tay bằng tiếng nói (VAD)!")
                trigger_recording = True
                
        last_btn_state = btn_state
        
        # Thực hiện tiến trình ghi âm & đẩy lên AI
        if trigger_recording:
            prev_state = current_state
            current_state = STATE_LISTENING
            map_display.show_screen_state("listening")
            map_display.show_notification("🎤 Đang lắng nghe...")
            
            # Ghi âm 4 giây
            audio_data = voice.record_audio(duration_sec=4)
            
            if audio_data:
                map_display.show_screen_state("fetching")
                map_display.show_notification("🤖 Đang gửi lên AI...")
                
                # Lấy IP gateway iPhone động
                try:
                    iphone_ip = wifi_server.wlan.ifconfig()[2]
                    print(f"[Main] Đang gửi âm thanh lên iPhone: {iphone_ip}")
                    success = voice.post_audio_to_iphone(iphone_ip, audio_data)
                    if success:
                        map_display.show_notification("✅ AI đang phản hồi...")
                    else:
                        map_display.show_notification("❌ Lỗi kết nối iPhone!")
                        voice.play_beep(600, 300)
                except Exception as e:
                    print("[Main] Lỗi lấy IP / gửi audio:", e)
                    map_display.show_notification("❌ Không có kết nối mạng!")
            
            # Khôi phục trạng thái cũ
            if journey.is_active:
                current_state = STATE_NAVIGATING
                map_display.show_screen_state("navigating")
            else:
                current_state = STATE_READY
                map_display.show_screen_state("ready")
        
        # ─── Poll HTTP server hoặc Cloud Server ───
        if config.USE_CLOUD_SERVER:
            # Poll Cloud định kỳ
            elapsed_poll = time.ticks_diff(now_ms, last_poll_ms)
            if elapsed_poll >= config.CLOUD_POLL_MS and wifi_server.is_connected:
                last_poll_ms = now_ms
                iphone_ip = wifi_server.wlan.ifconfig()[2] if (hasattr(wifi_server, 'wlan') and wifi_server.wlan and wifi_server.wlan.isconnected()) else "172.20.10.1"
                cloud_data = poll_cloud_server(iphone_ip)
                if cloud_data:
                    # Kích hoạt các callback tương ứng từ dữ liệu Cloud
                    if "update" in cloud_data and cloud_data["update"] and getattr(wifi_server, 'on_update', None):
                        up = cloud_data["update"]
                        wifi_server.on_update(
                            up.get("lat"), up.get("lon"), up.get("heading", 0),
                            up.get("speed", 0), up.get("route", []), up.get("cameras", [])
                        )
                    if "alert" in cloud_data and cloud_data["alert"] and getattr(wifi_server, 'on_alert', None):
                        al = cloud_data["alert"]
                        wifi_server.on_alert(
                            al.get("speed_limit", 50), al.get("current_speed", 0),
                            al.get("speed_over", False), al.get("camera_dist", 999), al.get("camera_type", "speed")
                        )
                    if "voice" in cloud_data and cloud_data["voice"]:
                        vo = cloud_data["voice"]
                        text_to_show = vo.get("text", "")
                        has_audio = vo.get("has_audio", False)
                        
                        # Hiển thị chữ lên màn hình xe
                        if getattr(wifi_server, 'on_voice', None):
                            wifi_server.on_voice(text_to_show, is_audio=False)
                            
                        # Kéo âm thanh PCM về phát trực tiếp qua Loa xe máy
                        if has_audio:
                            play_audio_from_cloud(voice, iphone_ip)
                    if cloud_data.get("stop") and getattr(wifi_server, 'on_stop', None):
                        wifi_server.on_stop()
        else:
            wifi_server.poll()  # Xử lý 1 HTTP request nếu có ở chế độ Local


        # ─── Reconnect WiFi nếu mất kết nối ───
        if not wifi_server.is_connected:
            map_display.update_connection_status(False)
            map_display.show_screen_state("idle")
            wifi_server.check_wifi()  # Tự reconnect
        else:
            if current_state == STATE_IDLE:
                current_state = STATE_READY
                map_display.show_screen_state("ready")
                map_display.update_connection_status(True)
                
        # ─── Update định kỳ khi đang dẫn đường ───
        # (Không cần gử REQ_UPDATE qua WiFi — Shortcuts tự POST định kỳ)
                    
        # ─── Auto-save journey state ───
        if journey.is_active:
            elapsed_save = time.ticks_diff(now_ms, last_save_ms)
            if elapsed_save >= SAVE_INTERVAL_MS:
                last_save_ms = now_ms
                journey.save()
                
        # ─── Cập nhật battery display ───
        bat_pct = battery.get_percentage()
        if bat_pct is not None:
            map_display.update_battery(bat_pct)
            if bat_pct < 10:
                map_display.show_notification("⚠️ Pin yếu, cần sạc!")
                
        # ─── Kiểm tra xe tắt máy (mất nguồn ACC) ───
        if not check_power_source() and engine_on:
            print("[Power] Phát hiện tắt máy xe! Lưu hành trình và sleep...")
            journey.save()
            map_display.show_notification("Đang lưu hành trình...")
            time.sleep_ms(500)
            lv.task_handler()
            machine.deepsleep()  # Sẽ wake up khi có power lại
            
        # ─── Đã đến nơi ───
        if current_state == STATE_ARRIVED:
            voice.play_beep(1200, 1000)
            time.sleep(3)
            current_state = STATE_READY
            map_display.show_screen_state("ready")
            
        time.sleep_ms(20)  # ~50 FPS LVGL update

# ═══════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Main] Dừng bởi user.")
    except Exception as e:
        import sys
        print("[Main] FATAL ERROR:", e)
        sys.print_exception(e)
        time.sleep(3)
        machine.reset()  # Auto-restart khi có lỗi
