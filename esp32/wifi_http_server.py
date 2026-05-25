# esp32/wifi_http_server.py
# WiFi + HTTP Server cho ESP32 — thay thế BLE, nhận dữ liệu từ Apple Shortcuts
# MicroPython — dùng socket TCP thuần, không cần thư viện ngoài
#
# ★ CLOUD POLLING MODE (config.USE_CLOUD_SERVER = True):
#   ESP32 kết nối Hotspot iPhone → tự động polling HTTPS tới tequilamap.onrender.com
#   → Nhận GPS, route, voice, alert từ Bộ não Đám mây mỗi 1.5 giây
#
# ★ LOCAL MODE (config.USE_CLOUD_SERVER = False):
#   ESP32 lắng nghe HTTP requests từ Apple Shortcuts / iPhone local
#   → Các endpoints: POST /update, /alert, /voice, /stop, /show-routes, GET /status

import network
import socket
import json
import time
import config

# Kiểm tra có ssl không (MicroPython ESP-IDF có ussl)
try:
    import ussl as ssl
    HAS_SSL = True
except ImportError:
    try:
        import ssl
        HAS_SSL = True
    except ImportError:
        HAS_SSL = False


class WiFiHTTPServer:
    """HTTP server nhẹ chạy trên MicroPython ESP32.

    Kết nối WiFi (iPhone Hotspot), sau đó:
    - Nếu USE_CLOUD_SERVER=True: Polling HTTPS lên tequilamap.onrender.com
    - Nếu USE_CLOUD_SERVER=False: Lắng nghe HTTP local từ Apple Shortcuts
    """

    def __init__(self):
        self.wlan = network.WLAN(network.STA_IF)
        self._sock = None
        self._running = False
        self.ip = None

        # ─── Callbacks — main.py sẽ gán các hàm này ───
        self.on_update = None       # fn(lat, lon, heading, speed, route, cameras)
        self.on_alert  = None       # fn(speed_limit, current_speed, cameras)
        self.on_voice  = None       # fn(text_or_bytes, is_audio)
        self.on_stop   = None       # fn()
        self.on_show_routes = None  # fn(routes)

        # Trạng thái kết nối
        self._is_connected = False

        # Cloud polling state
        self._last_poll_ms = 0
        self._cloud_host   = config.CLOUD_SERVER_HOST
        self._cloud_port   = config.CLOUD_SERVER_PORT
        self._cloud_ssl    = config.CLOUD_SERVER_SSL and HAS_SSL
        self._poll_interval_ms = getattr(config, "CLOUD_POLL_MS", 1500)

        # Trạng thái thiết bị gửi lên Cloud
        self._device_lat     = 0.0
        self._device_lon     = 0.0
        self._device_heading = 0.0
        self._device_speed   = 0.0

    # ═══════════════════════════════════════════════════
    # WIFI
    # ═══════════════════════════════════════════════════
    def connect_wifi(self, retries=5):
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

            # Chờ tối đa 15 giây
            for _ in range(150):
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
    # CLOUD POLLING (HTTPS tới tequilamap.onrender.com)
    # ═══════════════════════════════════════════════════
    def _https_post(self, path, payload_str):
        """Gửi HTTPS POST request tới Cloud server.
        Trả về body string nếu thành công, None nếu thất bại.
        """
        try:
            addr_info = socket.getaddrinfo(self._cloud_host, self._cloud_port)
            if not addr_info:
                return None
            addr = addr_info[0][-1]

            s = socket.socket()
            s.settimeout(5.0)
            s.connect(addr)

            # Wrap SSL nếu HTTPS
            if self._cloud_ssl:
                try:
                    s = ssl.wrap_socket(s, server_hostname=self._cloud_host)
                except Exception as e:
                    print("[Cloud] SSL wrap error:", e)
                    s.close()
                    return None

            body_bytes = payload_str.encode("utf-8") if payload_str else b""
            req = (
                f"POST {path} HTTP/1.1\r\n"
                f"Host: {self._cloud_host}\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(body_bytes)}\r\n"
                f"Connection: close\r\n"
                f"\r\n"
            ).encode() + body_bytes

            s.send(req)

            # Đọc response
            resp = b""
            while True:
                try:
                    chunk = s.recv(2048)
                    if not chunk:
                        break
                    resp += chunk
                except OSError:
                    break
            s.close()

            # Tách body
            if b"\r\n\r\n" in resp:
                return resp.split(b"\r\n\r\n", 1)[1].decode("utf-8", errors="ignore")
            return None
        except Exception as e:
            print("[Cloud] HTTPS POST lỗi:", e)
            return None

    def _https_get(self, path):
        """Gửi HTTPS GET request tới Cloud server. Trả về body string."""
        try:
            addr_info = socket.getaddrinfo(self._cloud_host, self._cloud_port)
            if not addr_info:
                return None
            addr = addr_info[0][-1]

            s = socket.socket()
            s.settimeout(5.0)
            s.connect(addr)

            if self._cloud_ssl:
                try:
                    s = ssl.wrap_socket(s, server_hostname=self._cloud_host)
                except Exception as e:
                    print("[Cloud] SSL wrap error:", e)
                    s.close()
                    return None

            req = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {self._cloud_host}\r\n"
                f"Connection: close\r\n"
                f"\r\n"
            ).encode()

            s.send(req)

            resp = b""
            while True:
                try:
                    chunk = s.recv(2048)
                    if not chunk:
                        break
                    resp += chunk
                except OSError:
                    break
            s.close()

            if b"\r\n\r\n" in resp:
                return resp.split(b"\r\n\r\n", 1)[1].decode("utf-8", errors="ignore")
            return None
        except Exception as e:
            print("[Cloud] HTTPS GET lỗi:", e)
            return None

    def cloud_boot(self):
        """Gửi tín hiệu boot lên Cloud server → nhận lời chào + pending_resume."""
        print("[Cloud] 🚀 Gửi tín hiệu boot lên Cloud...")
        body = self._https_post("/api/boot", "{}")
        if body:
            try:
                data = json.loads(body)
                pending = data.get("pending_resume", False)
                print(f"[Cloud] Boot OK — pending_resume={pending}")
                return data
            except Exception:
                pass
        print("[Cloud] Boot thất bại hoặc server chưa sẵn sàng.")
        return {}

    def cloud_send_gps(self, lat, lon, speed, heading):
        """Gửi GPS realtime lên Cloud server."""
        self._device_lat     = lat
        self._device_lon     = lon
        self._device_heading = heading
        self._device_speed   = speed
        payload = json.dumps({
            "lat": lat, "lon": lon,
            "speed": speed, "heading": heading
        })
        self._https_post("/api/update-gps", payload)

    def cloud_send_voice(self, pcm_bytes):
        """Gửi raw PCM audio từ Mic ESP32 lên Cloud để nhận dạng giọng nói."""
        try:
            addr_info = socket.getaddrinfo(self._cloud_host, self._cloud_port)
            if not addr_info:
                return None
            addr = addr_info[0][-1]

            s = socket.socket()
            s.settimeout(8.0)
            s.connect(addr)

            if self._cloud_ssl:
                try:
                    s = ssl.wrap_socket(s, server_hostname=self._cloud_host)
                except Exception as e:
                    print("[Cloud] SSL wrap error:", e)
                    s.close()
                    return None

            req = (
                f"POST /api/voice-command HTTP/1.1\r\n"
                f"Host: {self._cloud_host}\r\n"
                f"Content-Type: application/octet-stream\r\n"
                f"Content-Length: {len(pcm_bytes)}\r\n"
                f"Connection: close\r\n"
                f"\r\n"
            ).encode() + pcm_bytes

            s.send(req)

            resp = b""
            while True:
                try:
                    chunk = s.recv(1024)
                    if not chunk:
                        break
                    resp += chunk
                except OSError:
                    break
            s.close()

            if b"\r\n\r\n" in resp:
                return resp.split(b"\r\n\r\n", 1)[1].decode("utf-8", errors="ignore")
            return None
        except Exception as e:
            print("[Cloud] Gửi voice error:", e)
            return None

    def cloud_select_route(self, route_index):
        """Gửi lựa chọn tuyến đường lên Cloud."""
        payload = json.dumps({"route_index": route_index})
        body = self._https_post("/api/select-route", payload)
        if body:
            print(f"[Cloud] Đã chọn tuyến {route_index}.")
        return body

    def cloud_stop(self):
        """Gửi lệnh dừng dẫn đường lên Cloud."""
        self._https_post("/api/stop", "{}")
        print("[Cloud] Đã gửi lệnh dừng.")

    def poll_cloud(self):
        """Polling Cloud: lấy trạng thái mới nhất và xử lý callbacks.

        Gọi trong main loop. Non-blocking — chỉ thực hiện nếu đã đủ thời gian
        kể từ lần poll cuối (config.CLOUD_POLL_MS).
        """
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_poll_ms) < self._poll_interval_ms:
            return
        self._last_poll_ms = now

        if not self.wlan.isconnected():
            return

        # GET /api/status để lấy trạng thái tổng hợp từ Cloud
        body = self._https_get("/api/status")
        if not body:
            return

        try:
            data = json.loads(body)
        except Exception:
            return

        # Xử lý dữ liệu nhận về từ Cloud
        lat        = data.get("gps_lat")
        lon        = data.get("gps_lon")
        is_nav     = data.get("is_navigating", False)
        route_poly = data.get("route_polyline", [])
        instruction = data.get("current_instruction", "")
        cam_warning = data.get("camera_warning")
        speed_kmh   = data.get("speed_kmh", 0)
        eta_min     = data.get("eta_min")
        dist_remain = data.get("dist_remain_km")
        selecting   = data.get("selecting_route", False)
        pending_rts = data.get("pending_routes", [])
        voice_reply = data.get("voice_reply")

        # 1. Cập nhật vị trí và route lên màn hình
        if lat and lon and self.on_update:
            cameras_nearby = data.get("cameras_nearby", [])
            self.on_update(lat, lon, self._device_heading,
                           speed_kmh, route_poly, cameras_nearby)

        # 2. Cảnh báo tốc độ / camera
        if self.on_alert:
            speed_limit_now = data.get("speed_limit_now", 60)
            speed_over = speed_kmh > (speed_limit_now + 5) if speed_limit_now else False
            cam_dist   = data.get("camera_dist_m", 9999)
            cam_type   = data.get("camera_type", "speed")
            if cam_warning or speed_over:
                self.on_alert(speed_limit_now, speed_kmh, speed_over, cam_dist, cam_type)

        # 3. Voice reply mới từ Gemini / TTS
        if voice_reply and self.on_voice:
            self.on_voice(voice_reply, is_audio=False)

        # 4. Màn hình chọn 3 tuyến đường
        if selecting and pending_rts and self.on_show_routes:
            self.on_show_routes(pending_rts)

        # 5. Lệnh dừng
        if not is_nav and not selecting:
            # Có thể đã arrive hoặc stop
            pass

    def poll_cloud_audio(self):
        """Tải audio PCM từ Cloud về phát qua loa I2S.
        Gọi sau khi poll_cloud() phát hiện có audio mới.
        """
        body_bytes = None
        try:
            addr_info = socket.getaddrinfo(self._cloud_host, self._cloud_port)
            if not addr_info:
                return None
            addr = addr_info[0][-1]

            s = socket.socket()
            s.settimeout(8.0)
            s.connect(addr)

            if self._cloud_ssl:
                try:
                    s = ssl.wrap_socket(s, server_hostname=self._cloud_host)
                except Exception:
                    s.close()
                    return None

            req = (
                f"GET /api/get-audio HTTP/1.1\r\n"
                f"Host: {self._cloud_host}\r\n"
                f"Connection: close\r\n"
                f"\r\n"
            ).encode()
            s.send(req)

            resp = b""
            while True:
                try:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    resp += chunk
                except OSError:
                    break
            s.close()

            if b"\r\n\r\n" in resp:
                body_bytes = resp.split(b"\r\n\r\n", 1)[1]
            return body_bytes
        except Exception as e:
            print("[Cloud] Tải audio error:", e)
            return None

    # ═══════════════════════════════════════════════════
    # LOCAL HTTP SERVER (dùng khi USE_CLOUD_SERVER = False)
    # ═══════════════════════════════════════════════════
    def start(self):
        """Khởi động HTTP server local. Gọi sau connect_wifi()."""
        if config.USE_CLOUD_SERVER:
            print("[HTTP] Chế độ Cloud — bỏ qua local HTTP server.")
            return True

        if not self._is_connected:
            print("[HTTP] Chưa có WiFi, không thể start local server.")
            return False

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(('0.0.0.0', config.HTTP_PORT))
        self._sock.listen(2)
        self._sock.setblocking(False)
        self._running = True

        print(f"[HTTP] ✅ Server local: http://{self.ip}:{config.HTTP_PORT}/")
        return True

    def poll(self):
        """Gọi trong main loop để xử lý request local (khi USE_CLOUD_SERVER=False)."""
        if config.USE_CLOUD_SERVER:
            # Chuyển sang cloud polling
            self.poll_cloud()
            return

        if not self._running or not self._sock:
            return

        try:
            client, addr = self._sock.accept()
        except OSError:
            return

        client.settimeout(3.0)
        raw = b""

        try:
            while True:
                chunk = client.recv(2048)
                if not chunk:
                    break
                raw += chunk
                if b"\r\n\r\n" in raw:
                    header_part, body_part = raw.split(b"\r\n\r\n", 1)
                    cl = 0
                    for line in header_part.split(b"\r\n"):
                        if line.lower().startswith(b"content-length:"):
                            try:
                                cl = int(line.split(b":", 1)[1].strip())
                            except Exception:
                                pass
                    if len(body_part) >= cl:
                        break
        except OSError:
            pass

        if raw:
            self._handle_request(client, raw)

        try:
            client.close()
        except Exception:
            pass

    # ═══════════════════════════════════════════════════
    # ROUTING (local mode)
    # ═══════════════════════════════════════════════════
    def _handle_request(self, client, raw):
        """Parse HTTP request và route đến handler phù hợp."""
        try:
            first_line = raw.split(b"\r\n")[0].decode()
            parts = first_line.split(" ")
            if len(parts) < 2:
                self._send(client, 400, {"error": "Bad request"})
                return

            method = parts[0].upper()
            path   = parts[1]

            body = b""
            if b"\r\n\r\n" in raw:
                body = raw.split(b"\r\n\r\n", 1)[1]

            if method == "OPTIONS":
                self._send_cors(client)
                return

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
            except Exception:
                pass

    # ═══════════════════════════════════════════════════
    # HANDLERS (local mode)
    # ═══════════════════════════════════════════════════
    def _do_update(self, client, body):
        try:
            data = json.loads(body.decode("utf-8"))
            lat      = float(data.get("lat", 0))
            lon      = float(data.get("lon", 0))
            heading  = float(data.get("heading", 0))
            speed    = float(data.get("speed", 0))
            route    = data.get("route", [])
            cameras  = data.get("cameras", [])
            print(f"[HTTP] /update — GPS ({lat:.5f},{lon:.5f}) spd={speed:.0f}km/h")
            if self.on_update:
                self.on_update(lat, lon, heading, speed, route, cameras)
            self._send(client, 200, {"ok": True})
        except Exception as e:
            self._send(client, 400, {"error": str(e)})

    def _do_alert(self, client, body):
        try:
            data = json.loads(body.decode("utf-8"))
            speed_limit   = int(data.get("speed_limit", 60))
            current_speed = float(data.get("current_speed", 0))
            speed_over    = bool(data.get("speed_over", False))
            camera_dist   = float(data.get("camera_dist", 9999))
            camera_type   = data.get("camera_type", "speed")
            if self.on_alert:
                self.on_alert(speed_limit, current_speed, speed_over, camera_dist, camera_type)
            self._send(client, 200, {"ok": True})
        except Exception as e:
            self._send(client, 400, {"error": str(e)})

    def _do_voice(self, client, body):
        try:
            if body.startswith(b"{"):
                data = json.loads(body.decode("utf-8"))
                text = data.get("text", "")
                if self.on_voice:
                    self.on_voice(text, is_audio=False)
            else:
                if self.on_voice:
                    self.on_voice(body, is_audio=True)
            self._send(client, 200, {"ok": True})
        except Exception as e:
            self._send(client, 400, {"error": str(e)})

    def _do_stop(self, client):
        print("[HTTP] /stop — Dừng dẫn đường.")
        if self.on_stop:
            self.on_stop()
        self._send(client, 200, {"ok": True})

    def _do_status(self, client):
        status = {
            "device": "TequilaMap",
            "ip": self.ip,
            "wifi": self.wlan.isconnected(),
            "cloud_mode": config.USE_CLOUD_SERVER,
            "ok": True
        }
        self._send(client, 200, status)

    def _do_show_routes(self, client, body):
        try:
            data = json.loads(body.decode("utf-8"))
            routes = data.get("routes", [])
            if self.on_show_routes:
                self.on_show_routes(routes)
            self._send(client, 200, {"ok": True})
        except Exception as e:
            self._send(client, 400, {"error": str(e)})

    # ═══════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════
    def _send(self, client, code, data):
        """Gửi HTTP response JSON."""
        body = json.dumps(data).encode("utf-8")
        status_text = {200: "OK", 400: "Bad Request", 404: "Not Found", 500: "Error"}.get(code, "OK")
        response = (
            f"HTTP/1.1 {code} {status_text}\r\n"
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
            except Exception:
                pass
            self._sock = None
