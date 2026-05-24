# esp32/wifi_http_server.py
# WiFi + HTTP Server cho ESP32 — thay thế BLE, nhận dữ liệu từ Apple Shortcuts
# MicroPython — dùng socket TCP thuần, không cần thư viện ngoài
#
# Endpoints:
#   POST /update  — Nhận GPS + route + camera từ Shortcuts → cập nhật TFT
#   POST /alert   — Nhận cảnh báo tốc độ/camera → flash TFT + beep loa
#   POST /voice   — Nhận text TTS → phát qua loa MAX98357
#   POST /stop    — Dừng dẫn đường
#   GET  /status  — Shortcuts đọc trạng thái ESP32 (pin, IP)

import network
import socket
import json
import time
import config


class WiFiHTTPServer:
    """HTTP server nhẹ chạy trên MicroPython ESP32.
    
    Kết nối WiFi (iPhone Hotspot hoặc WiFi nhà), sau đó lắng nghe
    HTTP request từ Apple Shortcuts để nhận dữ liệu điều hướng.
    """

    def __init__(self):
        self.wlan = network.WLAN(network.STA_IF)
        self._sock = None
        self._running = False
        self.ip = None

        # ─── Callbacks — main.py sẽ gán các hàm này ───
        self.on_update = None   # fn(lat, lon, heading, speed, route, cameras)
        self.on_alert  = None   # fn(speed_limit, current_speed, cameras)
        self.on_voice  = None   # fn(text)
        self.on_stop   = None   # fn()
        self.on_show_routes = None # fn(routes)

        # Trạng thái kết nối (để main.py kiểm tra giống BLE cũ)
        self._is_connected = False

    # ═══════════════════════════════════════════════════
    # WIFI
    # ═══════════════════════════════════════════════════
    def connect_wifi(self, retries=3):
        """Kết nối WiFi. Trả về True nếu thành công."""
        self.wlan.active(True)
        
        if self.wlan.isconnected():
            self.ip = self.wlan.ifconfig()[0]
            print(f"[WiFi] Đã kết nối sẵn. IP: {self.ip}")
            self._is_connected = True
            return True

        for attempt in range(1, retries + 1):
            print(f"[WiFi] Kết nối '{config.WIFI_SSID}' (lần {attempt}/{retries})...")
            self.wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)

            # Chờ tối đa 12 giây
            for _ in range(120):
                if self.wlan.isconnected():
                    break
                time.sleep_ms(100)

            if self.wlan.isconnected():
                self.ip = self.wlan.ifconfig()[0]
                print(f"[WiFi] ✅ Kết nối thành công! IP: {self.ip}")
                self._is_connected = True
                return True
            else:
                print(f"[WiFi] ❌ Lần {attempt} thất bại.")
                self.wlan.disconnect()
                time.sleep(1)

        print("[WiFi] ❌ Không thể kết nối WiFi sau nhiều lần thử.")
        self._is_connected = False
        return False

    def check_wifi(self):
        """Kiểm tra và tự reconnect nếu mất WiFi."""
        if not self.wlan.isconnected():
            self._is_connected = False
            print("[WiFi] Mất kết nối, đang reconnect...")
            return self.connect_wifi(retries=2)
        self._is_connected = True
        return True

    # ═══════════════════════════════════════════════════
    # HTTP SERVER
    # ═══════════════════════════════════════════════════
    def start(self):
        """Khởi động HTTP server. Gọi sau connect_wifi()."""
        if not self._is_connected:
            print("[HTTP] Chưa có WiFi, không thể start server.")
            return False

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(('0.0.0.0', config.HTTP_PORT))
        self._sock.listen(2)
        self._sock.setblocking(False)  # Non-blocking để không block main loop
        self._running = True

        print(f"[HTTP] ✅ Server khởi động: http://{self.ip}:{config.HTTP_PORT}/")
        print(f"[HTTP]   POST /update  — nhận GPS + route từ Shortcuts")
        print(f"[HTTP]   POST /alert   — nhận cảnh báo camera/tốc độ")
        print(f"[HTTP]   POST /voice   — nhận lệnh TTS")
        print(f"[HTTP]   POST /stop    — dừng dẫn đường")
        print(f"[HTTP]   GET  /status  — kiểm tra trạng thái")
        return True

    def poll(self):
        """Gọi trong main loop (mỗi vòng lặp) để xử lý 1 request đến.
        Non-blocking — nếu không có request thì trả về ngay lập tức.
        """
        if not self._running or not self._sock:
            return

        try:
            client, addr = self._sock.accept()
        except OSError:
            return  # Không có kết nối đến, bỏ qua

        # Có client kết nối
        client.settimeout(3.0)
        raw = b""

        try:
            # Đọc request
            while True:
                chunk = client.recv(2048)
                if not chunk:
                    break
                raw += chunk
                # Kiểm tra đã nhận đủ header + body chưa
                if b"\r\n\r\n" in raw:
                    header_part, body_part = raw.split(b"\r\n\r\n", 1)
                    # Tìm Content-Length để biết đã nhận đủ body chưa
                    cl = 0
                    for line in header_part.split(b"\r\n"):
                        if line.lower().startswith(b"content-length:"):
                            try:
                                cl = int(line.split(b":", 1)[1].strip())
                            except:
                                pass
                    if len(body_part) >= cl:
                        break
        except OSError:
            pass

        # Xử lý request
        if raw:
            self._handle_request(client, raw)

        try:
            client.close()
        except:
            pass

    # ═══════════════════════════════════════════════════
    # ROUTING
    # ═══════════════════════════════════════════════════
    def _handle_request(self, client, raw):
        """Parse HTTP request và route đến handler phù hợp."""
        try:
            # Parse dòng đầu: METHOD /path HTTP/1.1
            first_line = raw.split(b"\r\n")[0].decode()
            parts = first_line.split(" ")
            if len(parts) < 2:
                self._send(client, 400, {"error": "Bad request"})
                return

            method = parts[0].upper()
            path   = parts[1]

            # Tách body
            body = b""
            if b"\r\n\r\n" in raw:
                body = raw.split(b"\r\n\r\n", 1)[1]

            # Xử lý CORS preflight (Shortcuts iOS đôi khi gửi OPTIONS)
            if method == "OPTIONS":
                self._send_cors(client)
                return

            # Route
            if path == "/update" and method == "POST":
                self._do_update(client, body)
            elif path == "/alert" and method == "POST":
                self._do_alert(client, body)
            elif path == "/voice" and method == "POST":
                self._do_voice(client, body)
            elif path == "/stop" and method == "POST":
                self._do_stop(client)
            elif path == "/show-routes" and method == "POST":
                self._do_show_routes(client, body)
            elif path == "/status" and method == "GET":
                self._do_status(client)
            else:
                self._send(client, 404, {"error": "Not found", "path": path})

        except Exception as e:
            print("[HTTP] Lỗi xử lý request:", e)
            try:
                self._send(client, 500, {"error": str(e)})
            except:
                pass

    # ═══════════════════════════════════════════════════
    # HANDLERS
    # ═══════════════════════════════════════════════════
    def _do_update(self, client, body):
        """POST /update
        Body JSON:
        {
            "lat": 10.762,
            "lon": 106.660,
            "heading": 90.0,
            "speed": 35.0,
            "route": [[10.762, 106.660], [10.763, 106.661], ...],
            "cameras": [{"lat":10.76, "lon":106.66, "type":"speed"}, ...]
        }
        """
        try:
            data = json.loads(body.decode("utf-8"))
            lat      = float(data.get("lat", 0))
            lon      = float(data.get("lon", 0))
            heading  = float(data.get("heading", 0))
            speed    = float(data.get("speed", 0))
            route    = data.get("route", [])     # [[lat,lon], ...]
            cameras  = data.get("cameras", [])   # [{"lat","lon","type"}, ...]

            print(f"[HTTP] /update — GPS ({lat:.5f},{lon:.5f}) hdg={heading:.0f}° spd={speed:.0f}km/h route={len(route)}pts cams={len(cameras)}")

            if self.on_update:
                self.on_update(lat, lon, heading, speed, route, cameras)

            self._send(client, 200, {"ok": True, "received": {
                "lat": lat, "lon": lon, "route_points": len(route), "cameras": len(cameras)
            }})
        except Exception as e:
            print("[HTTP] /update error:", e)
            self._send(client, 400, {"error": str(e)})

    def _do_alert(self, client, body):
        """POST /alert
        Body JSON:
        {
            "speed_limit": 60,
            "current_speed": 75,
            "speed_over": true,
            "camera_dist": 280,
            "camera_type": "speed"
        }
        """
        try:
            data = json.loads(body.decode("utf-8"))
            speed_limit   = int(data.get("speed_limit", 60))
            current_speed = float(data.get("current_speed", 0))
            speed_over    = bool(data.get("speed_over", False))
            camera_dist   = float(data.get("camera_dist", 9999))
            camera_type   = data.get("camera_type", "speed")

            print(f"[HTTP] /alert — limit={speed_limit} speed={current_speed:.0f} over={speed_over} cam_dist={camera_dist:.0f}m")

            if self.on_alert:
                self.on_alert(speed_limit, current_speed, speed_over, camera_dist, camera_type)

            self._send(client, 200, {"ok": True})
        except Exception as e:
            print("[HTTP] /alert error:", e)
            self._send(client, 400, {"error": str(e)})

    def _do_voice(self, client, body):
        """POST /voice
        Hỗ trợ cả hai dạng:
        1. JSON payload: {"text": "Rẽ phải..."} -> Hiển thị thông báo văn bản.
        2. Binary payload: Raw PCM audio bytes -> Phát trực tiếp ra loa I2S.
        """
        try:
            # Kiểm tra nếu là JSON text payload
            if body.startswith(b"{"):
                data = json.loads(body.decode("utf-8"))
                text = data.get("text", "")
                print(f"[HTTP] /voice — Hộp thoại chữ: '{text}'")
                if self.on_voice:
                    self.on_voice(text, is_audio=False)
            else:
                # Raw audio binary bytes
                print(f"[HTTP] /voice — Nhận {len(body)} bytes âm thanh PCM nhị phân thô")
                if self.on_voice:
                    self.on_voice(body, is_audio=True)
            self._send(client, 200, {"ok": True})
        except Exception as e:
            print("[HTTP] /voice error:", e)
            self._send(client, 400, {"error": str(e)})

    def _do_stop(self, client):
        """POST /stop — Dừng dẫn đường."""
        print("[HTTP] /stop — Dừng dẫn đường.")
        if self.on_stop:
            self.on_stop()
        self._send(client, 200, {"ok": True})

    def _do_status(self, client):
        """GET /status — Trả về trạng thái thiết bị."""
        status = {
            "device": "VMN-Compact",
            "ip": self.ip,
            "wifi": self.wlan.isconnected(),
            "ok": True
        }
        self._send(client, 200, status)

    def _do_show_routes(self, client, body):
        """POST /show-routes
        Nhận danh sách 3 tuyến đường để hiển thị chọn.
        """
        try:
            data = json.loads(body.decode("utf-8"))
            routes = data.get("routes", [])
            print("[HTTP] /show-routes — Nhận %d tuyến đường để lựa chọn." % len(routes))
            if self.on_show_routes:
                self.on_show_routes(routes)
            self._send(client, 200, {"ok": True})
        except Exception as e:
            print("[HTTP] /show-routes error:", e)
            self._send(client, 400, {"error": str(e)})

    # ═══════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════
    def _send(self, client, code, data):
        """Gửi HTTP response JSON."""
        body = json.dumps(data).encode("utf-8")
        status = "OK" if code < 400 else ("Bad Request" if code == 400 else
                  ("Not Found" if code == 404 else "Error"))
        response = (
            f"HTTP/1.1 {code} {status}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Access-Control-Allow-Origin: *\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode() + body
        try:
            client.send(response)
        except OSError:
            pass

    def _send_cors(self, client):
        """Trả về CORS preflight response."""
        response = (
            "HTTP/1.1 200 OK\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
            "Access-Control-Allow-Headers: Content-Type\r\n"
            "Content-Length: 0\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode()
        try:
            client.send(response)
        except OSError:
            pass

    @property
    def is_connected(self):
        """Tương thích API với BLEHandler cũ."""
        return self._is_connected and self.wlan.isconnected()

    def stop(self):
        """Dừng server."""
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except:
                pass
            self._sock = None
