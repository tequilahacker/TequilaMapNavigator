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

# ═══════════════════════════════════════════════════
# CẤU HÌNH KẾT NỐI (Chỉnh sang URL Render của bạn nếu test Cloud)
# ═══════════════════════════════════════════════════
SERVER_HOST = "localhost"  # Hoặc tên miền Render của bạn (VD: "tequila-navigator.onrender.com")
SERVER_PORT = 8080         # Cổng local là 8080. Cổng Cloud Render là 443
USE_SSL     = False        # Đổi thành True nếu dùng Render (HTTPS)
POLL_INTERVAL = 1.5        # Poll dữ liệu mỗi 1.5 giây

# Trạng thái giả lập HUD
current_hud = {
    "lat": 10.7769, "lon": 106.7009, "speed": 0, "heading": 0,
    "speed_limit": 60, "camera_dist": 9999, "camera_type": "",
    "instruction": "Đang chờ kết nối...", "eta": 0, "distance_remain": 0.0
}
is_running = True
is_typing = False

def print_hud():
    """Vẽ giao diện HUD xe máy giả lập lên Terminal."""
    os.system('clear' if os.name == 'posix' else 'cls')
    print("="*60)
    print("   🏍️  TEQUILA MOTORCYCLE NAVIGATOR - ESP32 SIMULATOR (macOS)")
    print("="*60)
    print(f"Trạng thái liên kết: {'ĐÁM MÂY ☁️' if USE_SSL else 'CỤC BỘ 📱'} | Máy chủ: {SERVER_HOST}:{SERVER_PORT}")
    print("-"*60)
    print(f"📍 GPS hiện tại : {current_hud['lat']:.6f}, {current_hud['lon']:.6f}")
    print(f"🧭 Hướng di chuyển: {current_hud['heading']}°")
    print("-"*60)
    
    # Hiển thị Tốc độ và Giới hạn tốc độ
    limit_str = f"{current_hud['speed_limit']} km/h" if current_hud['speed_limit'] < 999 else "Không giới hạn"
    
    # Đổi màu cảnh báo nếu chạy quá tốc độ
    if current_hud['speed'] > current_hud['speed_limit']:
        print(f"⚡ Tốc độ hiện tại: \033[91m{current_hud['speed']} km/h\033[0m  |  🛑 Giới hạn tốc độ: {limit_str}")
    else:
        print(f"⚡ Tốc độ hiện tại: \033[92m{current_hud['speed']} km/h\033[0m  |  🛑 Giới hạn tốc độ: {limit_str}")
    
    # Hiển thị Cảnh báo camera phạt nguội trước 100m
    if current_hud['camera_dist'] <= 300:
        cam_name = "TỐC ĐỘ" if current_hud['camera_type'] == "speed" else "VƯỢT ĐÈN ĐỎ"
        print(f"\033[91m⚠️ [CẢNH BÁO CAMERA PHẠT NGUỘI {cam_name} CÁCH {current_hud['camera_dist']} MÉT!]\033[0m")
    else:
        print("🟢 Hành trình an toàn - Không phát hiện camera phạt nguội phía trước")
        
    print("-"*60)
    # Hiển thị Bảng chỉ đường HUD màu xanh teal (mô phỏng bảng Top bar)
    print("\033[96m┌────────────────────────────────────────────────────────┐")
    print(f"│ 🗺️ Chỉ dẫn: {current_hud['instruction'][:48].ljust(48)} │")
    print("└────────────────────────────────────────────────────────┘\033[0m")
    
    # Hiển thị lộ trình (Bottom bar)
    print(f"🕒 Thời gian còn lại: {current_hud['eta']} phút  |  🏁 Quãng đường: {current_hud['distance_remain']} km")
    print("="*60)
    print("💡 [NHẤN PHÍM ENTER] để mô phỏng nói 'Hey Tequila' vào Mic xe...")
    print("="*60)

def save_and_play_pcm(pcm_data):
    """Bọc PCM thô thành file WAV và phát ra loa máy tính Mac bằng lệnh afplay có sẵn."""
    if not pcm_data:
        return
        
    wav_path = "incoming_audio.wav"
    sample_rate = 16000
    bits = 16
    channels = 1
    
    # Tạo WAV Header 44 bytes
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
        # Ghi file wav
        with open(wav_path, "wb") as f:
            f.write(header + pcm_data)
            
        # Sử dụng lệnh afplay có sẵn trên macOS để phát âm thanh ra loa cực bộ
        subprocess.run(["afplay", wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Cleanup
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
            s = ssl.wrap_socket(s, server_hostname=SERVER_HOST)
            
        request = (
            f"GET /api/get-audio HTTP/1.1\r\n"
            f"Host: {SERVER_HOST}:{SERVER_PORT}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode()
        s.send(request)
        
        # Nhận phản hồi
        response = bytearray()
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            response.extend(chunk)
        s.close()
        
        # Tách Header và Body
        parts = response.split(b"\r\n\r\n", 1)
        if len(parts) >= 2:
            pcm_bytes = parts[1]
            if pcm_bytes:
                # Phát âm thanh ra loa Mac
                save_and_play_pcm(pcm_bytes)
    except Exception as e:
        print("\n[Audio pull] Lỗi:", e)

def polling_loop():
    """Vòng lặp kéo dữ liệu từ máy chủ (GET /api/poll-device) định kỳ."""
    global is_running
    last_hud_print_time = 0
    
    while is_running:
        try:
            addr = socket.getaddrinfo(SERVER_HOST, SERVER_PORT, socket.AF_INET)[0][-1]
            s = socket.socket()
            s.settimeout(2.0)
            s.connect(addr)
            if USE_SSL:
                import ssl
                s = ssl.wrap_socket(s, server_hostname=SERVER_HOST)
                
            request = (
                f"GET /api/poll-device HTTP/1.1\r\n"
                f"Host: {SERVER_HOST}:{SERVER_PORT}\r\n"
                f"Connection: close\r\n"
                f"\r\n"
            ).encode()
            s.send(request)
            
            # Đọc phản hồi
            response = bytearray()
            while True:
                chunk = s.recv(2048)
                if not chunk:
                    break
                response.extend(chunk)
            s.close()
            
            # Parse JSON body
            parts = response.decode('utf-8', 'ignore').split("\r\n\r\n", 1)
            if len(parts) >= 2:
                body = parts[1].strip()
                if body:
                    data = json.loads(body)
                    
                    hud_changed = False
                    
                    # Cập nhật bản đồ/tọa độ
                    if "update" in data and data["update"]:
                        up = data["update"]
                        current_hud["lat"] = up.get("lat", 0.0)
                        current_hud["lon"] = up.get("lon", 0.0)
                        current_hud["speed"] = int(up.get("speed", 0))
                        current_hud["heading"] = up.get("heading", 0)
                        hud_changed = True
                        
                    # Cập nhật cảnh báo tốc độ/camera
                    if "alert" in data and data["alert"]:
                        al = data["alert"]
                        current_hud["speed_limit"] = al.get("speed_limit", 60)
                        current_hud["camera_dist"] = al.get("camera_dist", 9999)
                        current_hud["camera_type"] = al.get("camera_type", "")
                        hud_changed = True
                        
                    # Cập nhật chỉ đường chữ và âm thanh
                    if "voice" in data and data["voice"]:
                        vo = data["voice"]
                        current_hud["instruction"] = vo.get("text", "Đang chỉ đường...")
                        hud_changed = True
                        
                        # Kéo âm thanh PCM về phát nếu có
                        if vo.get("has_audio"):
                            print("\n📢 [Loa xe máy]: Nhận được gói âm thanh, đang tải về phát...")
                            fetch_audio_from_server()
                            
                    if data.get("stop"):
                        current_hud["instruction"] = "Hành trình đã dừng."
                        current_hud["speed"] = 0
                        hud_changed = True
                        
                    # Chỉ vẽ lại HUD khi có thông tin mới
                    now = time.time()
                    if hud_changed or (now - last_hud_print_time >= 3.0):
                        if not is_typing:
                            print_hud()
                        last_hud_print_time = now
                        
        except Exception:
            # Im lặng để không làm vỡ màn hình Terminal HUD
            pass
            
        time.sleep(POLL_INTERVAL)

def simulate_mic_input(user_command_text):
    """Mô phỏng Microphone xe máy bằng cách gửi lệnh thoại giả lập dạng chữ lên Server."""
    print(f"\n🗣️ Bạn nói vào mic xe: '{user_command_text}'")
    print("🤖 Đang truyền lên Server xử lý...")
    
    try:
        addr = socket.getaddrinfo(SERVER_HOST, SERVER_PORT, socket.AF_INET)[0][-1]
        s = socket.socket()
        s.settimeout(5.0)
        s.connect(addr)
        if USE_SSL:
            import ssl
            s = ssl.wrap_socket(s, server_hostname=SERVER_HOST)
            
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
        response = s.recv(1024)
        s.close()
        print("✅ Đã gửi tín hiệu! Đang chờ Server xử lý và truyền âm thanh về...")
    except Exception as e:
        print("❌ Lỗi gửi tín hiệu lên Server:", e)

def main():
    global is_running
    # Bắn tín hiệu Boot thông báo cho iPhone Companion
    try:
        addr = socket.getaddrinfo(SERVER_HOST, SERVER_PORT, socket.AF_INET)[0][-1]
        s = socket.socket()
        s.settimeout(2.0)
        s.connect(addr)
        req = "POST /api/boot HTTP/1.1\r\nHost: localhost\r\nContent-Length: 0\r\n\r\n"
        s.send(req.encode())
        s.close()
        print("[Boot] Đã gửi thông báo Boot lên iPhone thành công!")
    except Exception as e:
        print("[Boot] Không thể gửi thông báo Boot lên iPhone:", e)
        
    # Khởi chạy luồng Polling ngầm kéo dữ liệu từ Server
    t = threading.Thread(target=polling_loop, daemon=True)
    t.start()
    
    # Chào đón lúc boot
    print_hud()
    
    while is_running:
        try:
            # Đợi phím Enter kích hoạt mic
            input()
            
            global is_typing
            is_typing = True
            
            # Cho phép gõ lệnh thoại
            print("\033[93m🎤 Hãy nói điều bạn muốn (Simulator Mic):\033[0m")
            print("Ví dụ: 'Đi đến Nhà thờ Đức Bà' hoặc 'Kể tôi nghe một câu chuyện cười'")
            cmd = input("> ")
            
            is_typing = False
            
            if cmd.strip():
                if cmd.lower().strip() in ["exit", "thoát", "stop"]:
                    is_running = False
                    break
                simulate_mic_input(cmd)
                time.sleep(2.0) # Đợi tín hiệu phản hồi
                print_hud()
            else:
                print_hud()
        except (KeyboardInterrupt, SystemExit):
            is_running = False
            break

if __name__ == "__main__":
    main()
