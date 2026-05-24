# iphone/wyn_data_extractor.py
# WYN App Data - Cách tiếp cận thực tế để dùng WYN hoàn toàn miễn phí
#
# SỰ THẬT VỀ WYN:
# - WYN lưu toàn bộ database trong file offline BÊN TRONG app
# - Không có server API để gọi
# - Cách dùng WYN miễn phí DUY NHẤT: chạy WYN trực tiếp trên iPhone
#
# CHIẾN LƯỢC TÍCH HỢP WYN MIỄN PHÍ:
# 1. WYN chạy ở chế độ OVERLAY (hiện lên trên mọi app)
# 2. Khi bạn đang dùng Safari/Pythonista, WYN tự hiện cảnh báo
# 3. ESP32 TFT dùng OSM + Waze (nguồn độc lập, miễn phí)
# 4. Loa ESP32 đọc cảnh báo từ OSM + Waze
# 5. WYN phát âm thanh riêng của nó khi phát hiện camera
# → DOUBLE PROTECTION: WYN làm nhiệm vụ của nó, ESP32 làm nhiệm vụ riêng

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


class WYNDataExtractor:
    """Tích hợp WYN miễn phí qua iOS Overlay Mode + URL Scheme.
    
    WYN có 6.000+ camera phạt nguội và 12.000+ biển báo tốc độ cho VN.
    Vì không có API, ta dùng WYN theo đúng cách nó được thiết kế:
    chạy overlay trên các app khác để user luôn thấy cảnh báo.
    """

    WYN_BUNDLE_ID = "com.wynauto.app"  # Bundle ID của WYN (gần đúng)

    # WYN URL scheme (nếu WYN hỗ trợ)
    WYN_OPEN = "wyn://"
    WYN_APPSTORE_URL = "https://apps.apple.com/vn/app/wyn-c%E1%BA%A3nh-b%C3%A1o-giao-th%C3%B4ng/id1286893826"

    def __init__(self):
        self._wyn_installed = self._check_wyn_installed()
        if self._wyn_installed:
            print("[WYN] ✅ WYN đã được cài đặt")
        else:
            print("[WYN] ❌ WYN chưa cài. Mở App Store...")

    def _check_wyn_installed(self):
        if not HAS_OBJC:
            return False
        try:
            UIApplication = ObjCClass('UIApplication')
            app = UIApplication.sharedApplication()
            url = nsurl(self.WYN_OPEN)
            return bool(app.canOpenURL_(url))
        except Exception:
            return False

    def _open_url(self, url_string):
        if HAS_OBJC:
            try:
                UIApplication = ObjCClass('UIApplication')
                app = UIApplication.sharedApplication()
                url = nsurl(url_string)
                app.openURL_options_completionHandler_(url, {}, None)
                return True
            except Exception as e:
                print(f"[WYN] Error opening URL: {e}")
        if HAS_WEBBROWSER:
            webbrowser.open(url_string)
            return True
        return False

    def launch_wyn_overlay(self):
        """Mở WYN để user bật Overlay Mode.
        
        Sau khi bật Overlay, WYN sẽ hiện cảnh báo trên mọi app khác.
        User không cần chuyển app - WYN làm tự động.
        """
        if not self._wyn_installed:
            print("[WYN] Chưa cài WYN. Mở App Store...")
            self._open_url(self.WYN_APPSTORE_URL)
            return False

        success = self._open_url(self.WYN_OPEN)
        if success:
            print("[WYN] ✅ Đã mở WYN")
            print("[WYN] → Vào Settings → Bật 'Chạy trên ứng dụng khác'")
            print("[WYN] → Sau đó quay lại Pythonista")
        return success

    def get_setup_guide(self):
        """Hướng dẫn thiết lập WYN Overlay Mode."""
        return """
╔══════════════════════════════════════════════╗
║          THIẾT LẬP WYN OVERLAY MODE          ║
╠══════════════════════════════════════════════╣
║                                              ║
║  BƯỚC 1: Cài WYN từ App Store (MIỄN PHÍ)    ║
║  → Tìm "WYN - Cảnh báo giao thông"          ║
║                                              ║
║  BƯỚC 2: Bật Overlay Mode trong WYN          ║
║  → Mở WYN → Settings (⚙️)                   ║
║  → "Hiển thị cảnh báo" → Bật                ║
║  → Cấp quyền khi được hỏi                   ║
║                                              ║
║  BƯỚC 3: Quay lại Pythonista / Safari        ║
║                                              ║
║  KẾT QUẢ:                                   ║
║  ✅ WYN tự hiện popup camera khi gần         ║
║  ✅ WYN tự đọc biển báo tốc độ              ║
║  ✅ 6.000+ camera phạt nguội VN              ║
║  ✅ 12.000+ biển báo giao thông VN           ║
║  ✅ Hoàn toàn OFFLINE, không tốn data        ║
║                                              ║
║  ESP32 TFT hiển thị thêm từ OSM + Waze      ║
║  → Hai nguồn độc lập = bảo vệ kép!          ║
╚══════════════════════════════════════════════╝
"""

    def is_installed(self):
        return self._wyn_installed

    def get_status(self):
        return {
            "installed": self._wyn_installed,
            "overlay_mode": "unknown",  # Không thể check từ ngoài app
            "note": "WYN hoạt động độc lập, không có API"
        }
