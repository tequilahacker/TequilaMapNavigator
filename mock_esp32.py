# mock_esp32.py
# Tequila Motorcycle Navigator - Hardware ESP32 Emulator for macOS
# Dành cho việc kiểm thử hệ thống dẫn đường, quét camera phạt nguội và loa phát âm thanh trực tiếp trên máy Mac!
import time
import socket
import json
import threading
import os
import subprocess
import struct
import sys
import math
import select
import shutil

# ═══════════════════════════════════════════════════
# CẤU HÌNH KẾT NỐI (Mặc định dùng Render Cloud của bạn)
# ═══════════════════════════════════════════════════
SERVER_HOST = "tequilamap.onrender.com"
SERVER_PORT = 443
USE_SSL     = True
POLL_INTERVAL = 1.5

# Chuyển sang chạy local nếu chạy lệnh: python3 mock_esp32.py local
if len(sys.argv) > 1 and sys.argv[1].lower() == "local":
    SERVER_HOST = "localhost"
    SERVER_PORT = 8080
    USE_SSL     = False

try:
    import static_ffmpeg
    HAS_STATIC_FFMPEG = True
except ImportError:
    HAS_STATIC_FFMPEG = False

# Trạng thái giả lập HUD (Mặc định ở Thủ Đức trùng khớp với toạ độ thực tế của bạn)
current_hud = {
    "lat": 10.85417, "lon": 106.78779, "speed": 0, "heading": 0,
    "speed_limit": 60, "camera_dist": 9999, "camera_type": "",
    "instruction": "Đang chờ kết nối...", "eta": 0, "distance_remain": 0.0,
    "motorcycle_banned_warning": ""
}
is_running = True
is_typing = False

# Giả lập di chuyển dọc theo lộ trình (Driving Simulator)
simulated_route = []
sim_index = 0
is_simulating = False
sim_thread = None
available_routes = []

def check_ffmpeg():
    """Kiểm tra xem ffmpeg có sẵn trên hệ thống hay không."""
    return shutil.which("ffmpeg") is not None

def calculate_bearing(lat1, lon1, lat2, lon2):
    """Tính góc hướng đi (bearing) giữa 2 tọa độ GPS."""
    dlon = math.radians(lon2 - lon1)
    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)
    
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    
    bearing = math.atan2(y, x)
    bearing = math.degrees(bearing)
    return int((bearing + 360) % 360)

def send_gps_to_server(lat, lon, speed=0, heading=0):
    """Gửi toạ độ GPS giả lập của xe lên Server để cập nhật vị trí đồng bộ."""
    try:
        addr = socket.getaddrinfo(SERVER_HOST, SERVER_PORT, socket.AF_INET)[0][-1]
        s = socket.socket()
        s.settimeout(2.0)
        s.connect(addr)
        if USE_SSL:
            import ssl
            context = ssl.create_default_context()
            s = context.wrap_socket(s, server_hostname=SERVER_HOST)
            
        payload = json.dumps({
            "lat": lat,
            "lon": lon,
            "speed": speed,
            "heading": heading,
            "accuracy": 5
        }).encode()
        
        request = (
            f"POST /api/update-gps HTTP/1.1\r\n"
            f"Host: {SERVER_HOST}:{SERVER_PORT}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode() + payload
        
        s.send(request)
        s.close()
    except Exception:
        pass

def simulation_loop():
    """Luồng giả lập di chuyển xe dọc theo các điểm tọa độ của tuyến đường."""
    global is_simulating, sim_index, simulated_route
    print("\n🏍️ [MÔ PHỎNG LÁI XE] Đang di chuyển dọc theo tuyến đường...")
    
    while is_simulating and is_running:
        if not simulated_route or sim_index >= len(simulated_route):
            print("\n🏁 [MÔ PHỎNG LÁI XE] Đã đi tới điểm cuối hành trình!")
            current_hud["instruction"] = "Bạn đã đến điểm đích thành công."
            current_hud["speed"] = 0
            is_simulating = False
            break
            
        next_pt = simulated_route[sim_index]
        next_lat, next_lon = next_pt[0], next_pt[1]
        
        curr_lat, curr_lon = current_hud["lat"], current_hud["lon"]
        heading = calculate_bearing(curr_lat, curr_lon, next_lat, next_lon)
        
        # Di chuyển xe tới điểm tiếp theo
        current_hud["lat"] = next_lat
        current_hud["lon"] = next_lon
        current_hud["heading"] = heading
        current_hud["speed"] = 40  # Tốc độ giả định 40km/h
        
        # Gửi toạ độ GPS này lên Server để đồng bộ Web Map & tính khoảng cách camera phạt nguội
        send_gps_to_server(next_lat, next_lon, speed=40, heading=heading)
        
        sim_index += 1
        time.sleep(3.0)  # Cập nhật vị trí mỗi 3 giây

def start_route_simulation(route_points):
    """Bắt đầu mô phỏng lái xe dọc theo các điểm tọa độ của tuyến đường mới."""
    global is_simulating, sim_index, simulated_route, sim_thread
    is_simulating = False
    if sim_thread and sim_thread.is_alive():
        sim_thread.join(timeout=1.0)
        
    simulated_route = route_points
    sim_index = 0
    is_simulating = True
    
    sim_thread = threading.Thread(target=simulation_loop, daemon=True)
    sim_thread.start()

def print_hud():
    """Vẽ giao diện HUD xe máy giả lập lên Terminal."""
    os.system('clear' if os.name == 'posix' else 'cls')
    print("="*60)
    print("   🏍️  TEQUILA MOTORCYCLE NAVIGATOR - ESP32 SIMULATOR (macOS)")
    print("="*60)
    print(f"Trạng thái liên kết: {'ĐÁM MÂY ☁️' if USE_SSL else 'CỤC BỘ 📱'} | Máy chủ: {SERVER_HOST}:{SERVER_PORT}")
    has_mic = check_ffmpeg()
    mic_status = "\033[92mSẴN SÀNG ✅\033[0m" if has_mic else "\033[91mTHIẾU FFMPEG ❌ (Dùng phím 2 để nhập chữ)\033[0m"
    print(f"🎤 Micro máy Mac    : {mic_status}")
    print("-"*60)
    print(f"📍 GPS hiện tại : {current_hud['lat']:.6f}, {current_hud['lon']:.6f}")
    print(f"🧭 Hướng di chuyển: {current_hud['heading']}°")
    print("-"*60)
    
    limit_str = f"{current_hud['speed_limit']} km/h" if current_hud['speed_limit'] < 999 else "Không giới hạn"
    
    if current_hud['speed'] > current_hud['speed_limit']:
        print(f"⚡ Tốc độ hiện tại: \033[91m{current_hud['speed']} km/h\033[0m  |  🛑 Giới hạn tốc độ: {limit_str}")
    else:
        print(f"⚡ Tốc độ hiện tại: \033[92m{current_hud['speed']} km/h\033[0m  |  🛑 Giới hạn tốc độ: {limit_str}")
    
    if current_hud['camera_dist'] <= 300:
        cam_name = "TỐC ĐỘ" if current_hud['camera_type'] == "speed" else "VƯỢT ĐÈN ĐỎ"
        print(f"\033[91m⚠️ [CẢNH BÁO CAMERA PHẠT NGUỘI {cam_name} CÁCH {current_hud['camera_dist']} MÉT!]\033[0m")
    else:
        print("🟢 Hành trình an toàn - Không phát hiện camera phạt nguội phía trước")
        
    if current_hud.get("motorcycle_banned_warning"):
        print(f"\033[91m\033[5m{current_hud['motorcycle_banned_warning'].upper()} - QUAY LẠI NGAY!\033[0m")
        
    print("-"*60)
    print("\033[96m┌────────────────────────────────────────────────────────┐")
    print(f"│ 🗺️ Chỉ dẫn: {current_hud['instruction'][:48].ljust(48)} │")
    print("└────────────────────────────────────────────────────────┘\033[0m")
    
    print(f"🕒 Thời gian còn lại: {current_hud['eta']} phút  |  🏁 Quãng đường: {current_hud['distance_remain']} km")
    print("="*60)
    
    if available_routes:
        print("💡 [NHẤN PHÍM ENTER] để chọn Tuyến đường tối ưu...")
    else:
        print("💡 [NHẤN PHÍM ENTER] để nói 'Hey Tequila' qua Mic MacBook...")
    print("="*60)

def save_and_play_pcm(pcm_data):
    """Bọc PCM thô thành file WAV và phát ra loa máy tính Mac bằng lệnh afplay có sẵn."""
    if not pcm_data:
        return
        
    wav_path = "incoming_audio.wav"
    sample_rate = 16000
    bits = 16
    channels = 1
    
    header = struct.pack('<4sI4s4sIHHIIHH4sI',
        b'RIFF',
        len(pcm_data) + 36,
        b'WAVE',
        b'fmt ',
        16, 1, channels,
        sample_rate,
        sample_rate * channels * bits // 8,
        channels * bits // 8,
        bits,
        b'data',
        len(pcm_data)
    )
    
    try:
        with open(wav_path, "wb") as f:
            f.write(header + pcm_data)
        subprocess.run(["afplay", wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.remove(wav_path)
    except Exception as e:
        print("\n[Loa] Lỗi phát âm thanh cực bộ:", e)

def fetch_audio_from_server():
    """Gửi GET /api/get-audio lên server để kéo luồng âm thanh PCM thô về phát ra loa."""
    try:
        addr = socket.getaddrinfo(SERVER_HOST, SERVER_PORT, socket.AF_INET)[0][-1]
        s = socket.socket()
        s.settimeout(5.0)
        s.connect(addr)
        if USE_SSL:
            import ssl
            context = ssl.create_default_context()
            s = context.wrap_socket(s, server_hostname=SERVER_HOST)
            
        request = (
            f"GET /api/get-audio HTTP/1.1\r\n"
            f"Host: {SERVER_HOST}:{SERVER_PORT}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode()
        s.send(request)
        
        response = bytearray()
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            response.extend(chunk)
        s.close()
        
        parts = response.split(b"\r\n\r\n", 1)
        if len(parts) >= 2:
            pcm_bytes = parts[1]
            if pcm_bytes:
                save_and_play_pcm(pcm_bytes)
    except Exception as e:
        print("\n[Audio pull] Lỗi:", e)

def polling_loop():
    """Vòng lặp kéo dữ liệu từ máy chủ (GET /api/poll-device) định kỳ."""
    global is_running, available_routes, is_simulating
    last_hud_print_time = 0
    
    # Định kỳ gửi GPS hiện tại để đồng bộ hóa ban đầu
    send_gps_to_server(current_hud["lat"], current_hud["lon"], 0, current_hud["heading"])
    
    while is_running:
        try:
            addr = socket.getaddrinfo(SERVER_HOST, SERVER_PORT, socket.AF_INET)[0][-1]
            s = socket.socket()
            s.settimeout(2.0)
            s.connect(addr)
            if USE_SSL:
                import ssl
                context = ssl.create_default_context()
                s = context.wrap_socket(s, server_hostname=SERVER_HOST)
                
            request = (
                f"GET /api/poll-device HTTP/1.1\r\n"
                f"Host: {SERVER_HOST}:{SERVER_PORT}\r\n"
                f"Connection: close\r\n"
                f"\r\n"
            ).encode()
            s.send(request)
            
            response = bytearray()
            while True:
                chunk = s.recv(2048)
                if not chunk:
                    break
                response.extend(chunk)
            s.close()
            
            parts = response.decode('utf-8', 'ignore').split("\r\n\r\n", 1)
            if len(parts) >= 2:
                body = parts[1].strip()
                if body:
                    data = json.loads(body)
                    
                    hud_changed = False
                    
                    # 1. Cập nhật khi nhận được danh sách tuyến đường để chọn
                    if "show_routes" in data and data["show_routes"]:
                        available_routes = data["show_routes"]["routes"]
                        current_hud["instruction"] = "Chọn tuyến đường trên Terminal..."
                        hud_changed = True
                    else:
                        available_routes = []
                    
                    # 2. Cập nhật toạ độ và khởi động mô phỏng lái xe
                    if "update" in data and data["update"]:
                        up = data["update"]
                        
                        # Chỉ cập nhật toạ độ thủ công nếu không tự mô phỏng lái xe
                        if not is_simulating:
                            current_hud["lat"] = up.get("lat", 0.0)
                            current_hud["lon"] = up.get("lon", 0.0)
                            current_hud["speed"] = int(up.get("speed", 0))
                            current_hud["heading"] = up.get("heading", 0)
                        
                        # Khởi động mô phỏng nếu có tuyến đường mới từ server
                        if "route" in up and up["route"] and not is_simulating:
                            start_route_simulation(up["route"])
                        hud_changed = True
                        
                    # 3. Cập nhật cảnh báo tốc độ/camera
                    if "alert" in data and data["alert"]:
                        al = data["alert"]
                        current_hud["speed_limit"] = al.get("speed_limit", 60)
                        current_hud["camera_dist"] = al.get("camera_dist", 9999)
                        current_hud["camera_type"] = al.get("camera_type", "")
                        current_hud["motorcycle_banned_warning"] = al.get("motorcycle_banned_warning", "")
                        hud_changed = True
                        
                    # 4. Cập nhật chỉ đường chữ và âm thanh
                    if "voice" in data and data["voice"]:
                        vo = data["voice"]
                        current_hud["instruction"] = vo.get("text", "Đang chỉ đường...")
                        hud_changed = True
                        
                        # Kéo âm thanh PCM về phát
                        if vo.get("has_audio"):
                            fetch_audio_from_server()
                            
                    if data.get("stop"):
                        current_hud["instruction"] = "Hành trình đã dừng."
                        current_hud["speed"] = 0
                        is_simulating = False
                        hud_changed = True
                        
                    now = time.time()
                    if hud_changed or (now - last_hud_print_time >= 3.0):
                        if not is_typing:
                            print_hud()
                        last_hud_print_time = now
                        
        except Exception:
            pass
            
        time.sleep(POLL_INTERVAL)

def select_route_on_server(index):
    """Gửi lựa chọn tuyến đường lên server."""
    try:
        addr = socket.getaddrinfo(SERVER_HOST, SERVER_PORT, socket.AF_INET)[0][-1]
        s = socket.socket()
        s.settimeout(3.0)
        s.connect(addr)
        if USE_SSL:
            import ssl
            s = ssl.create_default_context().wrap_socket(s, server_hostname=SERVER_HOST)
            
        payload = json.dumps({"route_index": index}).encode()
        request = (
            f"POST /api/select-route HTTP/1.1\r\n"
            f"Host: {SERVER_HOST}:{SERVER_PORT}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode() + payload
        
        s.send(request)
        s.close()
        print(f"✅ Đã gửi lựa chọn: Tuyến đường {index + 1}!")
    except Exception as e:
        print("❌ Lỗi chọn tuyến đường:", e)

def send_raw_audio_to_server(pcm_data):
    """Gửi âm thanh ghi âm dạng nhị phân PCM thô 16kHz lên server."""
    print("📤 Đang gửi file âm thanh ghi âm lên Server...")
    try:
        addr = socket.getaddrinfo(SERVER_HOST, SERVER_PORT, socket.AF_INET)[0][-1]
        s = socket.socket()
        s.settimeout(12.0)
        s.connect(addr)
        if USE_SSL:
            import ssl
            context = ssl.create_default_context()
            s = context.wrap_socket(s, server_hostname=SERVER_HOST)
            
        request = (
            f"POST /api/voice-command HTTP/1.1\r\n"
            f"Host: {SERVER_HOST}:{SERVER_PORT}\r\n"
            f"Content-Type: application/octet-stream\r\n"
            f"Content-Length: {len(pcm_data)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode() + pcm_data
            
        s.sendall(request)
        
        response = bytearray()
        while True:
            chunk = s.recv(1024)
            if not chunk:
                break
            response.extend(chunk)
        s.close()
        print("✅ Đã gửi xong! Đang chờ Server xử lý và dịch...")
    except Exception as e:
        print("❌ Lỗi gửi âm thanh lên Server:", e)

def record_and_send_voice():
    """Ghi âm trực tiếp từ micro MacBook bằng avfoundation."""
    if not check_ffmpeg():
        print("\n❌ Không tìm thấy 'ffmpeg' trên hệ thống của bạn!")
        print("💡 Vui lòng chờ Homebrew cài đặt ffmpeg xong, hoặc sử dụng [NHẤN 2] để nhập bằng bàn phím.")
        input("\nNhấn Enter để quay lại...")
        return False

    if HAS_STATIC_FFMPEG:
        static_ffmpeg.add_paths()
        
    output_path = "simulated_mic.raw"
    if os.path.exists(output_path):
        try: os.remove(output_path)
        except: pass
        
    # Ghi âm 16kHz 16bit Mono s16le PCM dùng ffmpeg từ micro mặc định
    cmd = [
        "ffmpeg", "-y",
        "-loglevel", "quiet",
        "-f", "avfoundation",
        "-i", ":default",
        "-t", "5",
        "-ar", "16000",
        "-ac", "1",
        "-f", "s16le",
        "-acodec", "pcm_s16le",
        output_path
    ]
    
    # Xóa sạch bộ đệm stdin trước khi bắt đầu để tránh Enter cũ kích hoạt dừng sớm
    try:
        while select.select([sys.stdin], [], [], 0.0)[0]:
            sys.stdin.readline()
    except Exception:
        pass
        
    try:
        print("\n🎙️ [ĐANG THU ÂM] Hãy nói câu lệnh thoại vào Micro MacBook của bạn...")
        print("🔴 Ghi âm tối đa 5 giây (hoặc nhấn ENTER để dừng sớm)...")
        
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        stop_event = threading.Event()
        def wait_enter():
            sys.stdin.readline()
            stop_event.set()
            
        t = threading.Thread(target=wait_enter, daemon=True)
        t.start()
        
        # Đợi phím Enter hoặc hết 5 giây
        start_time = time.time()
        while time.time() - start_time < 5.0:
            if stop_event.is_set():
                break
            time.sleep(0.1)
            
        process.terminate()
        try: process.wait(timeout=1.0)
        except: process.kill()
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            with open(output_path, "rb") as f:
                pcm_data = f.read()
            send_raw_audio_to_server(pcm_data)
            try: os.remove(output_path)
            except: pass
            return True
        else:
            print("\n⚠️ Không thu được âm thanh từ Micro hoặc file ghi âm quá nhỏ.")
            print("💡 Hãy kiểm tra quyền truy cập Microphone của Terminal/Python trong System Settings > Privacy & Security > Microphone.")
            input("\nNhấn Enter để quay lại...")
            return False
    except Exception as e:
        print(f"\n❌ Lỗi ghi âm Microphone: {e}")
        input("\nNhấn Enter để quay lại...")
        return False

def simulate_mic_input(user_command_text):
    """Gửi câu lệnh giọng nói giả định bằng text (Nhập từ bàn phím)."""
    print(f"\n🗣️ Bạn nhập câu lệnh: '{user_command_text}'")
    print("🤖 Đang truyền lên Server xử lý...")
    
    try:
        addr = socket.getaddrinfo(SERVER_HOST, SERVER_PORT, socket.AF_INET)[0][-1]
        s = socket.socket()
        s.settimeout(5.0)
        s.connect(addr)
        if USE_SSL:
            import ssl
            context = ssl.create_default_context()
            s = context.wrap_socket(s, server_hostname=SERVER_HOST)
            
        payload = json.dumps({"text": user_command_text, "esp32_ip": "localhost"}).encode()
        request = (
            f"POST /api/voice-command HTTP/1.1\r\n"
            f"Host: {SERVER_HOST}:{SERVER_PORT}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode() + payload
            
        s.send(request)
        s.close()
        print("✅ Đã gửi tín hiệu!")
    except Exception as e:
        print("❌ Lỗi gửi tín hiệu lên Server:", e)

def main():
    global is_running
    try:
        addr = socket.getaddrinfo(SERVER_HOST, SERVER_PORT, socket.AF_INET)[0][-1]
        s = socket.socket()
        s.settimeout(2.0)
        s.connect(addr)
        if USE_SSL:
            import ssl
            s = ssl.create_default_context().wrap_socket(s, server_hostname=SERVER_HOST)
        req = "POST /api/boot HTTP/1.1\r\nHost: localhost\r\nContent-Length: 0\r\n\r\n"
        s.send(req.encode())
        s.close()
        print("[Boot] Đã đồng bộ Boot lên server.")
    except Exception as e:
        print("[Boot] Không thể gửi thông báo Boot:", e)
        
    t = threading.Thread(target=polling_loop, daemon=True)
    t.start()
    
    print_hud()
    
    while is_running:
        try:
            input()
            
            global is_typing
            is_typing = True
            
            # Nếu đang có danh sách tuyến đường để chọn
            if available_routes:
                print("\033[93m🗺️ Chọn tuyến đường (Nhập 1, 2, 3... hoặc gõ 0 để HUỶ):\033[0m")
                sel = input("> ").strip()
                is_typing = False
                
                if sel == "0":
                    try:
                        addr = socket.getaddrinfo(SERVER_HOST, SERVER_PORT, socket.AF_INET)[0][-1]
                        s = socket.socket()
                        s.connect(addr)
                        if USE_SSL:
                            import ssl
                            s = ssl.create_default_context().wrap_socket(s, server_hostname=SERVER_HOST)
                        s.send(f"POST /api/stop HTTP/1.1\r\nhost: {SERVER_HOST}\r\nContent-Length: 0\r\n\r\n".encode())
                        s.close()
                    except: pass
                    print_hud()
                elif sel.isdigit():
                    idx = int(sel) - 1
                    if 0 <= idx < len(available_routes):
                        select_route_on_server(idx)
                    else:
                        print("⚠️ Số thứ tự không hợp lệ.")
                        time.sleep(1.0)
                        print_hud()
                else:
                    print_hud()
                continue
                
            # Trạng thái bình thường: Nhập lệnh thoại
            print("\033[93m🎤 [NHẤN 1] Để nói trực tiếp (Mic MacBook) | [NHẤN 2] Nhập chữ bằng phím:\033[0m")
            choice = input("> ").strip()
            
            if choice == "2":
                print("⌨️ Nhập câu lệnh thoại của bạn:")
                cmd = input("> ")
                is_typing = False
                if cmd.strip():
                    if cmd.lower().strip() in ["exit", "thoát", "stop"]:
                        is_running = False
                        break
                    simulate_mic_input(cmd)
                    time.sleep(2.0)
                    print_hud()
                else:
                    print_hud()
            elif choice == "1" or choice == "":
                # Ghi âm thực tế
                success = record_and_send_voice()
                is_typing = False
                if success:
                    time.sleep(3.0)  # Đợi server dịch
                print_hud()
            else:
                print("⚠️ Lựa chọn không hợp lệ. Nhập 1 hoặc 2!")
                is_typing = False
                time.sleep(1.0)
                print_hud()
                
        except (KeyboardInterrupt, SystemExit):
            is_running = False
            break

if __name__ == "__main__":
    main()
