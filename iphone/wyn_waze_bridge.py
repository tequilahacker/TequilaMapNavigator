# iphone/wyn_waze_bridge.py
# WYN + Waze Bridge - Mở app qua URL Scheme để chạy song song với Tequila Navigator
# 
# CÁCH HOẠT ĐỘNG:
# 1. Tequila Navigator (Pythonista) xử lý BLE + GPS + AI routing
# 2. WYN chạy nền với tính năng OVERLAY → tự động hiện cảnh báo camera/biển báo
# 3. ESP32 TFT hiển thị bản đồ + alert từ OSM/Waze
# 4. Loa phát cảnh báo qua TTS tiếng Việt
# → Double coverage: WYN phát âm thanh cảnh báo + ESP32 hiển thị + TTS đọc

import time

try:
    from objc_util import ObjCClass, nsurl
    import ui
    HAS_OBJC = True
except ImportError:
    HAS_OBJC = False

try:
    import webbrowser
    HAS_WEBBROWSER = True
except ImportError:
    HAS_WEBBROWSER = False


class WYNWazeBridge:
    """Tích hợp WYN và Waze thông qua iOS URL scheme.
    
    WYN: App điều hướng VN với 6.000+ camera, 12.000+ biển báo
    - Chạy nền với Overlay Mode → tự động hiện alert trên màn hình
    - Không cần API key, hoạt động độc lập
    
    Waze: Navigation app quốc tế
    - Community alerts: police, accidents, cameras
    - URL scheme để mở và navigate
    """

    # ─── iOS URL Schemes ───
    WYN_SCHEME = "wyn://"
    WYN_APPSTORE = "https://apps.apple.com/vn/app/wyn-c%E1%BA%A3nh-b%C3%A1o-giao-th%C3%B4ng/id1286893826"

    WAZE_SCHEME = "waze://"
    WAZE_WEB = "https://waze.com/ul"
    WAZE_APPSTORE = "https://apps.apple.com/app/waze-navigation-live-traffic/id323229106"

    def __init__(self):
        self._wyn_installed = self._check_app("wyn://")
        self._waze_installed = self._check_app("waze://")
        print(f"[Bridge] WYN: {'✅ đã cài' if self._wyn_installed else '❌ chưa cài'}")
        print(f"[Bridge] Waze: {'✅ đã cài' if self._waze_installed else '❌ chưa cài'}")

    def _check_app(self, url_scheme):
        """Kiểm tra app đã được cài trên iPhone chưa."""
        if not HAS_OBJC:
            return False
        try:
            UIApplication = ObjCClass('UIApplication')
            app = UIApplication.sharedApplication()
            url = nsurl(url_scheme)
            return bool(app.canOpenURL_(url))
        except Exception:
            return False

    def _open_url(self, url_string):
        """Mở URL trên iOS."""
        if HAS_OBJC:
            try:
                UIApplication = ObjCClass('UIApplication')
                app = UIApplication.sharedApplication()
                url = nsurl(url_string)
                app.openURL_options_completionHandler_(url, {}, None)
                return True
            except Exception as e:
                print(f"[Bridge] objc_util error: {e}")
        if HAS_WEBBROWSER:
            webbrowser.open(url_string)
            return True
        return False

    # ─────────────────────────────────────────────
    # WYN - CẢNH BÁO GIAO THÔNG VIỆT NAM
    # ─────────────────────────────────────────────
    def launch_wyn_background(self):
        """Mở WYN ở chế độ overlay để chạy song song với Tequila Navigator.
        
        WYN sẽ tự động:
        - Hiện cảnh báo camera lên trên màn hình (overlay)
        - Đọc biển báo giao thông
        - Cảnh báo giới hạn tốc độ
        
        User thao tác: Vào WYN → Bật "Chạy trên ứng dụng khác" → Quay lại Safari/Pythonista
        """
        if self._wyn_installed:
            print("[Bridge] Đang mở WYN...")
            success = self._open_url(self.WYN_SCHEME)
            if success:
                print("[Bridge] ✅ WYN đã mở. Bật Overlay Mode trong WYN settings!")
                return True
        else:
            if not HAS_OBJC:
                print("[Bridge] Simulator: Giả lập khởi động WYN chạy nền thành công!")
                return True
            print("[Bridge] WYN chưa cài. Mở App Store...")
            self._open_url(self.WYN_APPSTORE)
        return False

    def wyn_navigate_to(self, lat, lon, name=""):
        """Mở WYN và điều hướng đến tọa độ cụ thể.
        
        WYN URL scheme format (nếu hỗ trợ):
        wyn://navigate?lat=X&lon=Y
        """
        # WYN chưa công bố URL scheme cụ thể cho navigate
        # Fallback: chỉ mở app
        return self.launch_wyn_background()

    # ─────────────────────────────────────────────
    # WAZE - NAVIGATION QUỐC TẾ
    # ─────────────────────────────────────────────
    def waze_navigate_to(self, lat, lon, nickname=""):
        """Mở Waze và navigate đến tọa độ.
        
        Waze URL scheme: waze://?ll=lat,lon&navigate=yes&nickname=name
        """
        url = f"waze://?ll={lat},{lon}&navigate=yes"
        if nickname:
            url += f"&nickname={nickname}"

        if self._waze_installed:
            print(f"[Bridge] Mở Waze đến {lat},{lon}...")
            return self._open_url(url)
        else:
            # Fallback: Waze web
            web_url = f"https://waze.com/ul?ll={lat},{lon}&navigate=yes"
            print("[Bridge] Waze chưa cài, mở web version...")
            return self._open_url(web_url)

    def waze_show_location(self, lat, lon):
        """Hiển thị vị trí trên Waze (không navigate ngay)."""
        url = f"waze://?ll={lat},{lon}&navigate=no"
        return self._open_url(url)

    def waze_search(self, query):
        """Tìm kiếm địa điểm trên Waze."""
        url = f"waze://?q={query}"
        return self._open_url(url)

    # ─────────────────────────────────────────────
    # GOOGLE MAPS - FALLBACK
    # ─────────────────────────────────────────────
    def google_maps_navigate(self, lat, lon, travel_mode="two-wheeler"):
        """Mở Google Maps app với mode xe máy.
        
        travel_mode: "driving" | "two-wheeler" | "walking" | "transit"
        """
        url = f"comgooglemaps://?daddr={lat},{lon}&directionsmode={travel_mode}"
        if not self._open_url(url):
            # Fallback web
            url = f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}&travelmode=driving"
            self._open_url(url)

    # ─────────────────────────────────────────────
    # ORCHESTRATION - Mở đúng app theo context
    # ─────────────────────────────────────────────
    def start_parallel_navigation(self, dest_lat, dest_lon, dest_name="",
                                  prefer_wyn=True, open_waze=False):
        """Mở WYN/Waze song song với Tequila Navigator.
        
        Strategy:
        - WYN chạy nền overlay (cảnh báo camera VN)
        - Tequila Navigator xử lý BLE + AI routing + ESP32 display
        - Optionally Waze cho traffic alerts
        """
        results = {}

        if prefer_wyn and self._wyn_installed:
            print("\n[Bridge] 🚀 Khởi động WYN ở chế độ overlay...")
            results["wyn"] = self.launch_wyn_background()
            print("[Bridge] ℹ️  Trong WYN: Bật 'Chạy trên ứng dụng khác' (Settings → Display)")
            time.sleep(2)

        if open_waze and self._waze_installed:
            print("[Bridge] 🚀 Mở Waze...")
            results["waze"] = self.waze_navigate_to(dest_lat, dest_lon, dest_name)

        return results

    def get_status(self):
        """Trả về status của các app."""
        return {
            "wyn_installed": self._wyn_installed,
            "waze_installed": self._waze_installed,
        }

    def get_setup_instructions(self):
        """Hướng dẫn thiết lập song song WYN + Tequila Navigator."""
        return """
═══════════════════════════════════════════
  HƯỚNG DẪN SỬ DỤNG WYN + WAZE SONG SONG
═══════════════════════════════════════════

BƯỚC 1: Cài WYN từ App Store (miễn phí)
  → Tìm "WYN - Cảnh báo giao thông"

BƯỚC 2: Thiết lập WYN Overlay Mode
  → Mở WYN → Settings → Display
  → Bật "Chạy trên ứng dụng khác"
  → Cấp quyền "Display over other apps"

BƯỚC 3: Chạy Tequila Navigator (Pythonista)
  → Khi bắt đầu hành trình, WYN tự bật overlay
  → WYN hiện cảnh báo lên trên màn hình iPhone
  → ESP32 hiển thị bản đồ route + camera từ OSM/Waze

BƯỚC 4: iPhone trong túi hoặc gắn trên xe
  → Loa ESP32 đọc hướng dẫn rẽ + cảnh báo camera
  → WYN tự phát âm thanh riêng khi phát hiện camera
  → DOUBLE PROTECTION: 2 nguồn cảnh báo độc lập!

WAZE (tùy chọn):
  → Cài Waze, chạy khi cần traffic report
  → Waze community: police, accidents, hazards
  → Không dùng cho camera VN (database không đầy đủ)
═══════════════════════════════════════════
"""
