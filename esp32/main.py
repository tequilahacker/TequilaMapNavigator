# esp32/main.py
# Tequila Motorcycle Navigator - Main Application Entry Point
# MicroPython cho ESP32-S3 + 2.8" IPS TFT + INMP441 + MAX98357
import time
import machine



import config
from greeting import GreetingScreen
from journey_state import JourneyStateManager
from wifi_http_server import WiFiHTTPServer
from voice_handler import VoiceHandler
from lvgl_map_2_8 import MapDisplay, MAP_Y, MAP_H
from battery_manager import BatteryManager

# ═══════════════════════════════════════════════════
# TRẠNG THÁI THIẾT BỊ (State Machine)
# ═══════════════════════════════════════════════════
STATE_BOOTING    = "booting"
STATE_IDLE       = "idle"         # Chờ kết nối WiFi
STATE_READY      = "ready"        # Kết nối OK, chờ lệnh
STATE_LISTENING  = "listening"    # Đang thu giọng nói
STATE_FETCHING   = "fetching"     # Chờ AI xử lý
STATE_NAVIGATING = "navigating"   # Đang dẫn đường
STATE_ARRIVED    = "arrived"      # Đã đến nơi

current_state = STATE_BOOTING
_last_voice_reply = ""

# ═══════════════════════════════════════════════════
# KHỞI TẠO HARDWARE
# ═══════════════════════════════════════════════════
def init_display():
    """Khởi tạo MapDisplay (ILI9341 SPI trực tiếp, không LVGL)."""
    # MapDisplay.init() tự khởi tạo SPI + ILI9341 bên trong
    return True  # display được quản lý bởi MapDisplay object

def init_touch():
    """Khởi tạo XPT2046 resistive touch (ESP32-2432S028 / CYD board).
    
    CYD dùng XPT2046 qua SPI2 riêng (không phải FT6236 I2C).
    GPIO: CLK=25, MOSI=32, MISO=39, CS=33, IRQ=36
    """
    try:
        from xpt2046 import XPT2046
        spi2 = machine.SPI(2,
            baudrate=1000000,
            sck=machine.Pin(config.TOUCH_CLK),
            mosi=machine.Pin(config.TOUCH_MOSI),
            miso=machine.Pin(config.TOUCH_MISO)
        )
        tp = XPT2046(spi=spi2,
                     cs=machine.Pin(config.TOUCH_CS, machine.Pin.OUT),
                     int_pin=machine.Pin(config.TOUCH_IRQ, machine.Pin.IN))
        print("[Touch] XPT2046 resistive touch khởi tạo thành công.")
        return tp
    except ImportError:
        print("[Touch] Thư viện xpt2046 chưa có — touch sẽ không hoạt động.")
        return None
    except Exception as e:
        print("[Touch] Khởi tạo lỗi:", e)
        return None

def check_power_source():
    """Kiểm tra xe đang bật (ACC pin) hay không."""
    try:
        acc_adc = machine.ADC(machine.Pin(config.ACC_PIN))
        acc_adc.atten(machine.ADC.ATTN_11DB)
        raw = acc_adc.read()
        voltage = (raw / 4095.0) * 3.6 * 3
        return voltage > 5.0
    except Exception:
        return True

def setup_wake_button():
    """Cấu hình nút GPIO để kích hoạt voice command."""
    btn = machine.Pin(config.WAKE_BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
    return btn

# ═══════════════════════════════════════════════════
# CALLBACKS: nhận dữ liệu từ Cloud / Local HTTP
# ═══════════════════════════════════════════════════
def make_on_update(map_display, journey):
    """Callback cập nhật GPS + route + camera lên màn hình."""
    def on_update(lat, lon, heading, speed, route, cameras):
        global current_state
        route_tuples = [(r[0], r[1]) for r in route if len(r) >= 2]
        cam_list = []
        for c in cameras:
            try:
                cam_list.append({
                    "lat": float(c["lat"]) if isinstance(c, dict) else float(c[0]),
                    "lon": float(c["lon"]) if isinstance(c, dict) else float(c[1]),
                    "type": c.get("type", "speed") if isinstance(c, dict) else "speed"
                })
            except Exception:
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
        if route_tuples:
            current_state = STATE_NAVIGATING
    return on_update


def make_on_alert(map_display, voice):
    """Callback cảnh báo tốc độ và camera phạt nguội."""
    def on_alert(speed_limit, current_speed, speed_over, camera_dist, camera_type):
        map_display.update_speed_limit(speed_limit)
        map_display.update_navigation_data(
            map_display.alert_label.get_text().split("\n")[0],
            current_speed, 0
        )
        if speed_over:
            map_display.show_notification(
                f"⚠️ Vượt tốc độ! {int(current_speed)}/{speed_limit}km/h", 4000
            )
            voice.play_beep(1200, 600)
        if camera_dist < config.CAMERA_ALERT_DIST:
            cam_label = "Tốc độ" if camera_type == "speed" else "Vượt đèn đỏ"
            map_display.show_camera_alert(f"CAMERA {cam_label.upper()} − {int(camera_dist)}m")
            voice.play_beep(880, 400)
    return on_alert


def make_on_voice(map_display, voice):
    """Callback nhận text/audio từ server → hiện màn hình + phát loa."""
    def on_voice(data, is_audio=False):
        if is_audio:
            if hasattr(voice, "audio_out") and voice.audio_out:
                try:
                    voice.audio_out.write(data)
                except Exception as e:
                    print("[Voice CB] Lỗi phát audio:", e)
        else:
            map_display.show_notification(str(data))
    return on_voice


def make_on_stop(map_display, journey):
    """Callback dừng dẫn đường."""
    def on_stop():
        global current_state
        current_state = STATE_READY
        map_display.show_screen_state("ready")
        map_display.clear_routes_selection()
        journey.clear()
        print("[HTTP] Dừng dẫn đường.")
    return on_stop


def make_on_show_routes(map_display, wifi_server):
    """Callback hiển thị 3 tuyến đường và xử lý chọn lựa."""
    def on_show_routes(routes):
        def select_route_callback(idx):
            try:
                if config.USE_CLOUD_SERVER:
                    # Gửi lên Cloud HTTPS
                    wifi_server.cloud_select_route(idx)
                else:
                    # Gửi về iPhone local
                    import socket, json
                    iphone_ip = wifi_server.wlan.ifconfig()[2]
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
                print("[Main] Đã gửi lựa chọn tuyến %d!" % idx)
            except Exception as e:
                print("[Main] Lỗi gửi lựa chọn tuyến:", e)

        map_display.show_routes(routes, select_route_callback)
    return on_show_routes


# ═══════════════════════════════════════════════════
# CLOUD POLLING — lấy dữ liệu từ tequilamap.onrender.com
# ═══════════════════════════════════════════════════
def process_cloud_status(data, wifi_server, voice, map_display):
    """Xử lý JSON status trả về từ /api/status của Cloud."""
    global current_state

    lat        = data.get("gps_lat")
    lon        = data.get("gps_lon")
    is_nav     = data.get("is_navigating", False)
    route_poly = data.get("route_polyline", [])
    speed_kmh  = data.get("speed_kmh", 0)
    cam_warning = data.get("camera_warning")
    selecting  = data.get("selecting_route", False)
    pending_rts = data.get("pending_routes", [])
    voice_reply = data.get("voice_reply")
    instruction = data.get("current_instruction", "")
    eta_min    = data.get("eta_min")
    dist_remain = data.get("dist_remain_km")
    speed_limit = data.get("speed_limit_now", 60)
    cam_dist   = data.get("camera_dist_m", 9999)
    cam_type   = data.get("camera_type", "speed")
    cameras_nearby = data.get("cameras_nearby", [])

    # 1. Cập nhật GPS + route + camera lên màn hình
    if lat and lon and wifi_server.on_update:
        wifi_server.on_update(lat, lon, 0, speed_kmh, route_poly, cameras_nearby)

    # 2. Cập nhật hướng dẫn dẫn đường
    if instruction and is_nav:
        map_display.update_navigation_data(instruction, speed_kmh, 0)
        if eta_min:
            map_display.update_eta(eta_min, dist_remain)

    # 3. Cảnh báo tốc độ và camera
    speed_over = speed_kmh > (speed_limit + 5) if speed_limit else False
    if (speed_over or cam_warning) and wifi_server.on_alert:
        wifi_server.on_alert(speed_limit, speed_kmh, speed_over, cam_dist, cam_type)

    # 4. Voice reply mới từ AI → hiển thị + phát loa
    global _last_voice_reply
    if voice_reply and voice_reply != _last_voice_reply:
        _last_voice_reply = voice_reply
        if wifi_server.on_voice:
            wifi_server.on_voice(voice_reply, is_audio=False)
        # Kéo audio PCM về phát loa (vô hiệu hóa tạm thời để tránh tràn RAM)
        # pcm = wifi_server.poll_cloud_audio()
        # if pcm and hasattr(voice, "audio_out") and voice.audio_out:
        #     try:
        #         voice.audio_out.write(pcm)
        #     except Exception as e:
        #         print("[Cloud Audio] Lỗi phát:", e)

    # 5. Màn hình chọn 3 tuyến đường
    if selecting and pending_rts and wifi_server.on_show_routes:
        wifi_server.on_show_routes(pending_rts)
        current_state = STATE_FETCHING

    # 6. Đã đến đích
    if not is_nav and not selecting and current_state == STATE_NAVIGATING:
        arr_text = data.get("arrived_text", "")
        if arr_text:
            current_state = STATE_ARRIVED


# ═══════════════════════════════════════════════════
# VÒNG LẶP CHÍNH
# ═══════════════════════════════════════════════════
def main():
    global current_state

    print("\n" + "="*50)
    print("  TEQUILA MAP - BOOTING")
    print("="*50 + "\n")

    # 0. PRE-INIT WiFi driver TRƯỚC TIÊN — phải làm trước khi các module khác chiếm RAM
    # WiFi driver cần ~100KB heap liên tục, nếu init sau map/display thì không còn đủ
    print("[Boot] Pre-init WiFi driver (uu tien RAM)...")
    import gc
    gc.collect()
    try:
        import network as _net
        _wlan_preinit = _net.WLAN(_net.STA_IF)
        _wlan_preinit.active(True)
        print("[Boot] WiFi driver pre-init OK, RAM tu do:", gc.mem_free())
        del _wlan_preinit  # Giai phong object, driver van chay nen
        gc.collect()
    except Exception as _e:
        print("[Boot] WiFi pre-init that bai:", _e)

    # 1. Khởi tạo hardware
    print("[Boot] Khởi tạo màn hình...")
    display_drv = init_display()

    print("[Boot] Khởi tạo touch...")
    touch = init_touch()

    print("[Boot] Khởi tạo battery manager...")
    battery = BatteryManager()

    print("[Boot] Khởi tạo voice handler...")
    voice = VoiceHandler(
        i2s_mic_sck=config.MIC_SCK, i2s_mic_ws=config.MIC_WS, i2s_mic_sd=config.MIC_SD,
        i2s_spk_sck=config.SPK_SCK, i2s_spk_ws=config.SPK_WS, i2s_spk_sd=config.SPK_SD,
    )

    print("[Boot] Khởi tạo journey state manager...")
    journey = JourneyStateManager()

    print("[Boot] Khởi tạo MapDisplay (no-LVGL)...")
    map_display = MapDisplay()
    map_display.init()

    # ── OpenHaystack BLE (phat beacon de iPhone track qua Find My) ──
    haystack = None
    if getattr(config, 'FINDMY_BLE_ENABLED', False):
        print("[Boot] Khoi dong OpenHaystack BLE advertising...")
        try:
            from ble_haystack import HaystackAdvertiser
            key = getattr(config, 'FINDMY_PUBLIC_KEY', None)
            haystack = HaystackAdvertiser(public_key_bytes=key)
            ok = haystack.start()
            if ok:
                print("[Boot] BLE Haystack OK - Thiet bi xuat hien trong app Tim!")
            else:
                print("[Boot] BLE Haystack khoi dong that bai.")
        except Exception as e:
            print("[Boot] Loi BLE Haystack:", e)
            haystack = None

    print("[Boot] Khởi tạo WiFi HTTP/Cloud Server...")
    wifi_server = WiFiHTTPServer()
    # Chi thu 1 lan (8 giay) khi boot - neu that bai, main loop se retry moi 3 giay
    wifi_ok = wifi_server.connect_wifi(retries=1, timeout_ms=8000)

    if wifi_ok:
        # Cloud mode: không cần start local server
        wifi_server.start()

        # Gán callbacks
        wifi_server.on_update     = make_on_update(map_display, journey)
        wifi_server.on_alert      = make_on_alert(map_display, voice)
        wifi_server.on_voice      = make_on_voice(map_display, voice)
        wifi_server.on_stop       = make_on_stop(map_display, journey)
        wifi_server.on_show_routes = make_on_show_routes(map_display, wifi_server)

        map_display.show_notification(f"WiFi OK - {wifi_server.ip}")
        map_display.update_connection_status(True, False)

        # ── Boot handshake lên Cloud / iPhone ──
        if config.USE_CLOUD_SERVER:
            print("[Boot] Gửi tín hiệu boot lên Cloud tequilamap.onrender.com...")
            boot_resp = wifi_server.cloud_boot()
            pending_resume = boot_resp.get("pending_resume", False)
        else:
            # Local iPhone
            pending_resume = False
            try:
                import socket
                iphone_ip = wifi_server.wlan.ifconfig()[2]
                s = socket.socket()
                s.settimeout(2.0)
                s.connect((iphone_ip, 8080))
                req = "POST /api/boot HTTP/1.1\r\nHost: localhost\r\nContent-Length: 0\r\n\r\n"
                s.send(req.encode())
                s.close()
                print("[Boot] Đã gửi boot lên iPhone local!")
            except Exception as e:
                print("[Boot] Lỗi gửi boot local:", e)
    else:
        map_display.show_notification("WiFi that bai! Kiem tra hotspot.")
        map_display.update_connection_status(False, False)
        pending_resume = False

    # 2. Boot greeting (loa xe phát lời chào)
    print("[Boot] Chạy boot greeting...")
    greeting = GreetingScreen(map_display=map_display, audio_out=getattr(voice, 'speaker', None))
    boot_result = greeting.run_boot_sequence(journey, audio_out=getattr(voice, 'speaker', None))

    # 3. Check ACC pin
    engine_on = check_power_source()
    print(f"[Boot] ACC power: {'ON' if engine_on else 'OFF'}")

    # 4. Resume journey nếu có hành trình cũ
    if boot_result == "resume" or pending_resume:
        journey.load()
        current_state = STATE_NAVIGATING
        map_display.show_notification("Đang tiếp tục hành trình cũ...")
        print("[Boot] Resume journey từ flash/cloud.")
    else:
        current_state = STATE_IDLE

    map_display.show_screen_state("idle" if not wifi_ok else "ready")

    # 5. Wake button
    wake_btn = setup_wake_button()
    last_btn_state = 1

    # 6. Timers
    SAVE_INTERVAL_MS   = 30000   # Auto-save mỗi 30 giây
    last_save_ms       = time.ticks_ms()
    last_gps_push_ms   = time.ticks_ms()
    GPS_PUSH_INTERVAL  = 3000    # Đẩy GPS lên Cloud mỗi 3 giây
    last_wifi_check_ms = time.ticks_ms() - 15000  # Cooldown 15 giây kết nối WiFi

    print("\n[Main] ✅ Hệ thống sẵn sàng! Vào vòng lặp chính.\n")

    # ═══════ MAIN LOOP ═══════
    # Map fetch timer (cập nhật bản đồ Google Maps mỗi MAP_UPDATE_SEC giây)
    last_map_fetch_ms  = time.ticks_ms()
    MAP_FETCH_INTERVAL = getattr(config, 'MAP_UPDATE_SEC', 3) * 1000  # ms
    _last_map_lat      = 0.0
    _last_map_lon      = 0.0

    # ═══ Touch zoom + pan state ═══
    _map_zoom          = 17          # Local zoom (14-19)
    _pan_lat           = 0.0        # Offset khỏi GPS center (độ)
    _pan_lon           = 0.0
    _pan_mode          = False      # True = đang xem bản đồ tự do, không follow GPS
    _touch_x0          = None       # Touch start (None = không chạm)
    _touch_y0          = None
    _touch_t0          = 0
    _touch_last_tap_t  = 0          # Double-tap detection
    _touch_x_prev      = None       # Pixel vị trí cuối để tính delta
    _touch_y_prev      = None

    # Turn announcement tracker (tránh thông báo 2 lần cùng 1 đoạn)
    _last_turn_dist = None

    while True:
        now_ms = time.ticks_ms()
        if map_display.tick():  # Trả về True nếu vừa tắt notification
            last_map_fetch_ms = now_ms - MAP_FETCH_INTERVAL  # Force fetch map ngay lập tức

        # ─── Touch Gesture: zoom + pan ───
        # Tap TRAI (<120px)  = Zoom OUT   Tap PHAI (>=120px) = Zoom IN
        # Double-tap         = Reset GPS follow (xoa pan)
        # Keo/Vuot           = Pan ban do (cung chieu ngon tay)
        if touch:
            try:
                t_point = touch.get_touch()  # (x,y) hoac None
            except Exception:
                t_point = None

            if t_point:
                tx, ty = t_point
                if _touch_x0 is None:
                    # Bat dau cham
                    _touch_x0, _touch_y0 = tx, ty
                    _touch_t0 = now_ms
                    _touch_x_prev, _touch_y_prev = tx, ty
                else:
                    # Dang keo -> tinh delta va pan
                    px_scale = 0.000006 * (2 ** (19 - _map_zoom))
                    dx_px = tx - _touch_x_prev
                    dy_px = ty - _touch_y_prev
                    # Pan: keo PHAI -> map dich chuyen ve DONG (lon tang)
                    #      keo LEN  -> map dich chuyen ve NAM  (lat giam)
                    _pan_lon -= dx_px * px_scale
                    _pan_lat += dy_px * px_scale
                    _pan_mode = True
                    _touch_x_prev, _touch_y_prev = tx, ty

            elif _touch_x0 is not None:
                # Nha tay -> xu ly gesture
                total_move = abs(_touch_x_prev - _touch_x0) + abs(_touch_y_prev - _touch_y0)
                dt_ms = time.ticks_diff(now_ms, _touch_t0)

                if total_move < 15 and dt_ms < 300:
                    # TAP (khong vuot)
                    if time.ticks_diff(now_ms, _touch_last_tap_t) < 450:
                        # DOUBLE-TAP -> reset GPS follow mode
                        _pan_lat = 0.0
                        _pan_lon = 0.0
                        _pan_mode = False
                        map_display.show_notification("GPS Follow")
                    else:
                        # SINGLE TAP: TRAI = zoom out, PHAI = zoom in
                        if _touch_x0 < 120:
                            _map_zoom = max(14, _map_zoom - 1)
                            map_display.show_notification("- Zoom {}".format(_map_zoom))
                        else:
                            _map_zoom = min(19, _map_zoom + 1)
                            map_display.show_notification("+ Zoom {}".format(_map_zoom))
                    _touch_last_tap_t = now_ms

                # Reset touch state
                _touch_x0, _touch_y0 = None, None


        # ─── Wake: Vô hiệu hóa ghi âm theo yêu cầu ───
        btn_state = wake_btn.value()
        trigger_recording = False
        last_btn_state = btn_state

        # ─── Ghi âm & gửi lên AI ───
        if trigger_recording:
            current_state = STATE_LISTENING
            map_display.show_screen_state("listening")
            map_display.show_notification("🎤 Đang lắng nghe...")

            audio_data = voice.record_audio(duration_sec=4)

            if audio_data:
                current_state = STATE_FETCHING
                map_display.show_screen_state("fetching")
                map_display.show_notification("🤖 Đang gửi lên AI...")

                try:
                    if config.USE_CLOUD_SERVER:
                        # Gửi PCM trực tiếp lên Cloud
                        resp = wifi_server.cloud_send_voice(audio_data)
                        if resp:
                            map_display.show_notification("✅ AI đang phản hồi...")
                        else:
                            map_display.show_notification("❌ Lỗi gửi Cloud!")
                    else:
                        # Gửi lên iPhone local
                        iphone_ip = wifi_server.wlan.ifconfig()[2]
                        success = voice.post_audio_to_iphone(iphone_ip, audio_data)
                        if success:
                            map_display.show_notification("✅ AI đang phản hồi...")
                        else:
                            map_display.show_notification("❌ Lỗi kết nối iPhone!")
                            voice.play_beep(600, 300)
                except Exception as e:
                    print("[Main] Lỗi gửi audio:", e)
                    map_display.show_notification("❌ Không có mạng!")

            # Khôi phục trạng thái
            current_state = STATE_NAVIGATING if journey.is_active else STATE_READY
            map_display.show_screen_state("navigating" if journey.is_active else "ready")

        # ─── Cloud Polling (thay thế cả poll_cloud_server + play_audio) ───
        if config.USE_CLOUD_SERVER and wifi_server.is_connected:
            # Đẩy GPS lên Cloud định kỳ (từ GPS thật của ESP32 nếu có)
            if time.ticks_diff(now_ms, last_gps_push_ms) >= GPS_PUSH_INTERVAL:
                last_gps_push_ms = now_ms
                # Lấy tốc độ từ màn hình (hiện tại = 0 vì GPS từ iPhone)
                wifi_server.cloud_send_gps(
                    wifi_server._device_lat or 0,
                    wifi_server._device_lon or 0,
                    0, 0
                )

            # Poll /api/status từ Cloud
            import json
            body = wifi_server._https_get("/api/status")
            if body:
                try:
                    cloud_data = json.loads(body)
                    process_cloud_status(cloud_data, wifi_server, voice, map_display)

                    # ── (A) Fetch bản đồ Google Maps mỗi 3 giây ──
                    # Center = GPS hiện tại → bản đồ follow user như Google Maps
                    now_secs = time.ticks_diff(now_ms, last_map_fetch_ms)
                    cur_lat = cloud_data.get('gps_lat') or 10.8541
                    cur_lon = cloud_data.get('gps_lon') or 106.7878
                    gps_moved = (abs(cur_lat - _last_map_lat) > 0.00005 or
                                 abs(cur_lon - _last_map_lon) > 0.00005)

                    if cur_lat and (now_secs >= MAP_FETCH_INTERVAL or gps_moved):
                        last_map_fetch_ms = now_ms
                        _last_map_lat = cur_lat
                        _last_map_lon = cur_lon
                        try:
                            zoom = _map_zoom  # Local zoom (không lấy từ cloud)
                            # Center bản đồ: GPS + offset pan (nếu đang pan mode)
                            gps_lat_c = cloud_data.get('gps_lat') or 10.8541
                            gps_lon_c = cloud_data.get('gps_lon') or 106.7878
                            if not _pan_mode:  # Follow GPS -> reset offset từ từ
                                _pan_lat *= 0.5
                                _pan_lon *= 0.5
                                if abs(_pan_lat) < 0.00001: _pan_lat = 0.0
                                if abs(_pan_lon) < 0.00001: _pan_lon = 0.0
                            map_center_lat = gps_lat_c + _pan_lat
                            map_center_lon = gps_lon_c + _pan_lon
                            path = f"/api/map-image?lat={map_center_lat}&lon={map_center_lon}&zoom={zoom}&format=rgb565&gps_lat={gps_lat_c}&gps_lon={gps_lon_c}"

                            # CS toggle tung chunk, KHONG giu CS LOW suot HTTPS
                            # ILI9341 giu frame buffer position giua cac CS transaction
                            if map_display.drv:
                                drv = map_display.drv
                                import gc; gc.collect()
                                drv.set_window(0, MAP_Y, 239, MAP_Y + MAP_H - 1)

                                def on_map_data(chunk):
                                    if chunk:
                                        drv.dc.value(1)
                                        drv.cs.value(0)
                                        drv.spi.write(chunk)
                                        drv.cs.value(1)

                                ok = wifi_server._https_get_stream(path, on_map_data)
                                if ok:
                                    print("[Map] Ban do OK!")
                                else:
                                    print("[Map] Loi tai ban do.")
                        except Exception as _me:
                            if map_display.drv:
                                map_display.drv.cs.value(1)
                            print("[Map] Loi stream ban do:", _me)

                    # ── (B) Xi nhan ×3 khi quẹo trong 100m ──
                    turn_dist = cloud_data.get('dist_to_turn')
                    turn_dir  = cloud_data.get('turn_direction', '')
                    if (turn_dist and float(turn_dist) <= 100 and turn_dir and
                            turn_dist != _last_turn_dist):
                        _last_turn_dist = turn_dist
                        side = 'phải' if 'right' in str(turn_dir).lower() else 'trái'
                        msg = (f'Phía trước {int(turn_dist)} mét quẹo {side}, '
                               f'hãy bật xi nhan {side}, ' * 3)
                        # Phát local TTS
                        try: voice.speak_tts(msg)
                        except Exception: pass
                    elif not turn_dist or float(turn_dist) > 150:
                        _last_turn_dist = None  # reset khi qua khúc quẹo

                    # ── (C) Đã đến nơi ──
                    arr_text = cloud_data.get('arrived_text', '')
                    if arr_text and current_state == STATE_NAVIGATING:
                        current_state = STATE_ARRIVED
                        map_display.show_screen_state('arrived')
                        map_display.update_connection_status(True, True)
                        journey.is_active = False
                        # Beep thông báo
                        try: voice.play_beep(1200, 500)
                        except Exception: pass

                except Exception as e:
                    print("[Poll] Parse lỗi:", e)

        elif not config.USE_CLOUD_SERVER:
            wifi_server.poll()  # Local HTTP request

        # ─── Reconnect WiFi ───
        if not wifi_server.is_connected:
            map_display.update_connection_status(False, False)
            # Retry nhanh hon: 3 giay khi chua ket noi (thay vi 15 giay)
            retry_interval = 3000
            if time.ticks_diff(now_ms, last_wifi_check_ms) >= retry_interval:
                last_wifi_check_ms = now_ms
                print("[WiFi] Thu ket noi lai...")
                ok = wifi_server.check_wifi()
                if ok:
                    map_display.show_notification(f"WiFi OK - {wifi_server.ip}")
                    map_display.update_connection_status(True, False)
                    if config.USE_CLOUD_SERVER:
                        wifi_server.start()
                        wifi_server.on_update     = make_on_update(map_display, journey)
                        wifi_server.on_alert      = make_on_alert(map_display, voice)
                        wifi_server.on_voice      = make_on_voice(map_display, voice)
                        wifi_server.on_stop       = make_on_stop(map_display, journey)
                        wifi_server.on_show_routes = make_on_show_routes(map_display, wifi_server)
        else:
            # WiFi da ket noi - cap nhat state nhung KHONG xoa ban do
            if current_state == STATE_IDLE:
                current_state = STATE_READY
                # KHONG goi show_screen_state("ready") vi no se xoa ban do!
                map_display.update_connection_status(True, False)

        # ─── Auto-save journey ───
        if journey.is_active:
            if time.ticks_diff(now_ms, last_save_ms) >= SAVE_INTERVAL_MS:
                last_save_ms = now_ms
                journey.save()

        # ─── Battery display ───
        bat_pct = battery.get_percentage()
        if bat_pct is not None:
            map_display.update_battery(bat_pct)
            # Vô hiệu hóa thông báo "Pin yếu" liên tục tránh đè mất bản đồ
            # if bat_pct < 10:
            #     map_display.show_notification("⚠️ Pin yếu, cần sạc!")

        # ─── Tắt máy xe → DeepSleep ───
        if not check_power_source() and engine_on:
            print("[Power] Xe tắt máy! Lưu hành trình và sleep...")
            journey.save()
            map_display.show_notification("Đang lưu hành trình...")
            time.sleep_ms(500)
            map_display.tick()
            machine.deepsleep()

        # ─── Đã đến nơi ───
        if current_state == STATE_ARRIVED:
            voice.play_beep(1200, 1000)
            time.sleep(3)
            current_state = STATE_READY
            map_display.show_screen_state("ready")

        time.sleep_ms(20)  # ~50 FPS


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
        machine.reset()
