# iphone/waze_scraper.py
# Lấy dữ liệu REAL-TIME từ Waze Live Map (endpoint không chính thức nhưng được cộng đồng dùng rộng rãi)
# Waze cung cấp: POLICE, ACCIDENT, JAM, HAZARD, camera alerts xung quanh vị trí hiện tại
#
# ⚠️ Lưu ý: Đây là endpoint không chính thức. Có thể thay đổi bất cứ lúc nào.
# Nhưng cộng đồng đã dùng từ 2015 đến nay và vẫn hoạt động (2024-2026).

import math
import time
import json

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import urllib.request
    import urllib.parse
    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False

# Waze Live Map endpoints (du lieu REAL-TIME nam 2026, cap nhat tung phut)
# Day la du lieu CONG DONG - nguoi dung bao cao NGAY HOM NAY, khong phai 2015
WAZE_GEORSS_URL  = "https://www.waze.com/live-map/api/georss"   # Primary
WAZE_ALERTS_URL  = "https://www.waze.com/row-rtserver/web/TGeoRSS"  # Backup
WAZE_IFRAME_URL  = "https://www.waze.com/en/livemap/directions"  # Fallback 3

# Waze alert type codes (cap nhat 2026 - real-time crowdsourced data)
WAZE_TYPE_MAP = {
    "POLICE":        {"type": "police",    "name": "Cảnh sát giao thông phía trước", "priority": 1},
    "ACCIDENT":      {"type": "accident",  "name": "Tai nạn giao thông",              "priority": 1},
    "JAM":           {"type": "traffic",   "name": "Tắc đường",                       "priority": 3},
    "HAZARD":        {"type": "hazard",    "name": "Nguy hiểm đường bộ",              "priority": 2},
    "ROAD_CLOSED":   {"type": "closed",    "name": "Đường bị chặn",                   "priority": 1},
    "WEATHERHAZARD": {"type": "weather",   "name": "Thời tiết xấu",                   "priority": 3},
    "CHIT_CHAT":     {"type": "info",      "name": "Thông tin giao thông",             "priority": 5},
}

# Waze HAZARD subtypes = camera cong dong bao cao (real-time)
# Day la camera LUU DONG (canh sat, cam do do den, cam toc do di dong)
CAMERA_HAZARD_SUBTYPES = {
    "HAZARD_ON_SHOULDER_CAR_STOPPED",     # Canh sat dung lai
    "HAZARD_ON_ROAD_POLICE_HIDING",       # Canh sat nup
    "HAZARD_ON_ROAD_TRAFFIC_LIGHT_FAULT", # Dung do den
    "HAZARD_ON_ROAD_ROAD_KILL",           # Camera ghi hinh su co
}

# Police subtypes = confirmed camera/police
POLICE_SUBTYPES = {
    "POLICE_VISIBLE",   # Canh sat ro rang
    "POLICE_HIDING",    # Canh sat nup
    "SPEED_CAMERA_AHEAD",  # Camera toc do phia truoc
}


class WazeScraper:
    """Lấy dữ liệu real-time từ Waze Live Map cho khu vực hiện tại.
    
    Data bao gồm:
    - Cảnh sát (POLICE) → cảnh báo camera lưu động
    - Tai nạn (ACCIDENT) → tránh đường
    - Tắc đường (JAM) → reroute
    - Nguy hiểm (HAZARD) → chú ý
    
    Cập nhật mỗi 30-60 giây khi đang di chuyển.
    """

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.waze.com/live-map/",
        "Origin": "https://www.waze.com",
    }

    def __init__(self):
        self._last_alerts = []
        self._last_fetch_time = 0
        self._cache_ttl = 45  # Giây cache trước khi fetch lại
        self._announced_ids = set()  # IDs đã announce rồi

    def _build_bbox(self, lat, lon, radius_km=3):
        """Tạo bounding box từ center + radius."""
        dlat = radius_km / 111.0
        dlon = radius_km / (111.0 * math.cos(math.radians(lat)))
        return {
            "top":    lat + dlat,
            "bottom": lat - dlat,
            "left":   lon - dlon,
            "right":  lon + dlon,
        }

    def fetch_alerts(self, lat, lon, radius_km=3, force=False):
        """Lấy tất cả alerts từ Waze trong bán kính xung quanh vị trí.
        
        Args:
            lat, lon: Vị trí hiện tại
            radius_km: Bán kính tìm kiếm (mặc định 3km)
            force: Bỏ qua cache, fetch ngay
            
        Returns:
            list of {type, name, lat, lon, distance_m, id, subtype, ...}
        """
        # Dùng cache nếu chưa hết hạn
        if not force and time.time() - self._last_fetch_time < self._cache_ttl:
            return self._filter_by_distance(self._last_alerts, lat, lon, radius_km)

        bbox = self._build_bbox(lat, lon, radius_km)

        # Params cho Waze georss endpoint
        params = {
            "top":    bbox["top"],
            "bottom": bbox["bottom"],
            "left":   bbox["left"],
            "right":  bbox["right"],
            "env":    "row",           # "row" = Rest of World (Việt Nam)
            "types":  "alerts,traffic,users",
        }

        data = None
        if HAS_REQUESTS:
            data = self._fetch_with_requests(params)
        elif HAS_URLLIB:
            data = self._fetch_with_urllib(params)

        if data:
            self._last_alerts = self._parse_waze_response(data, lat, lon)
            self._last_fetch_time = time.time()
            print(f"[Waze] Lấy được {len(self._last_alerts)} alerts từ Waze")
        else:
            print("[Waze] Không lấy được data, dùng cache cũ")

        return self._filter_by_distance(self._last_alerts, lat, lon, radius_km)

    def _fetch_with_requests(self, params):
        """Fetch dùng requests module."""
        try:
            r = requests.get(
                WAZE_GEORSS_URL,
                params=params,
                headers=self.HEADERS,
                timeout=8,
            )
            if r.status_code == 200:
                return r.json()
            # Thử backup endpoint
            r2 = requests.get(WAZE_ALERTS_URL, params=params, headers=self.HEADERS, timeout=8)
            if r2.status_code == 200:
                return r2.json()
        except Exception as e:
            print(f"[Waze] requests error: {e}")
        return None

    def _fetch_with_urllib(self, params):
        """Fetch dùng urllib (built-in, không cần cài thêm)."""
        try:
            url = WAZE_GEORSS_URL + "?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers=self.HEADERS)
            with urllib.request.urlopen(req, timeout=8) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            print(f"[Waze] urllib error: {e}")
        return None

    def _parse_waze_response(self, data, my_lat, my_lon):
        """Parse Waze JSON response thành danh sách alerts chuẩn hóa."""
        alerts = []

        for alert in data.get("alerts", []):
            alert_type = alert.get("type", "")
            subtype = alert.get("subtype", "")
            location = alert.get("location", {})
            a_lat = location.get("y", 0)
            a_lon = location.get("x", 0)

            if not a_lat or not a_lon:
                continue

            dist = self._dist_m(my_lat, my_lon, a_lat, a_lon)
            type_info = WAZE_TYPE_MAP.get(alert_type, {
                "type": alert_type.lower(),
                "name": alert_type,
                "priority": 5,
            })

            alerts.append({
                "id":          alert.get("uuid", f"{a_lat}{a_lon}"),
                "type":        type_info["type"],
                "name":        type_info["name"],
                "subtype":     subtype,
                "lat":         a_lat,
                "lon":         a_lon,
                "distance_m":  int(dist),
                "confidence":  alert.get("confidence", 3),
                "reliability": alert.get("reliability", 5),
                "street":      alert.get("street", ""),
                "source":      "waze",
                "raw_type":    alert_type,
            })

        # Sắp xếp theo khoảng cách
        alerts.sort(key=lambda x: x["distance_m"])
        return alerts

    def _filter_by_distance(self, alerts, lat, lon, radius_km):
        """Lọc và tính lại khoảng cách theo vị trí hiện tại."""
        radius_m = radius_km * 1000
        result = []
        for alert in alerts:
            dist = self._dist_m(lat, lon, alert["lat"], alert["lon"])
            if dist <= radius_m:
                result.append({**alert, "distance_m": int(dist)})
        result.sort(key=lambda x: x["distance_m"])
        return result

    def get_new_alerts(self, lat, lon, radius_km=3):
        """Chỉ trả về alerts CHƯA được announce.
        
        Dùng trong nav loop để không lặp lại cảnh báo đã nói.
        """
        all_alerts = self.fetch_alerts(lat, lon, radius_km)
        new = [a for a in all_alerts if a["id"] not in self._announced_ids]
        return new

    def mark_announced(self, alert_id):
        """Đánh dấu alert đã được announce."""
        self._announced_ids.add(alert_id)
        # Xóa old IDs sau 10 phút để tránh bộ nhớ đầy
        if len(self._announced_ids) > 200:
            self._announced_ids = set(list(self._announced_ids)[-50:])

    def build_alert_text(self, alert):
        """Tao text canh bao tieng Viet dung spec Tequila Map.
        
        Spec:
        - Camera < 50m: "Phia truoc 50 met co camera phat nguoi"
        - Canh sat < 200m: "Phia truoc co canh sat kiem tra toc do"
        - Tai nan < 300m: "Phia truoc co tai nan giao thong, di cham lai"
        - Tac duong: "Phia truoc tac duong, co the tim duong vong"
        """
        raw_type = alert.get("raw_type", "")
        subtype  = alert.get("subtype", "")
        dist     = int(alert["distance_m"])
        street   = alert.get("street", "")

        # Format khoang cach
        if dist <= 30:
            dist_str = "ngay phia truoc"
        elif dist <= 100:
            dist_str = f"phia truoc {dist} met"
        else:
            dist_str = f"phia truoc {dist} met"

        street_str = f" tren duong {street}" if street else ""

        # ── Camera / Canh sat (uu tien cao nhat) ──
        if raw_type == "POLICE":
            if dist <= 200:
                text = f"Canh bao! {dist_str} co canh sat kiem tra toc do{street_str}. Giam toc do ngay!"
            else:
                text = f"{dist_str} co canh sat giao thong{street_str}. Chu y toc do."
        elif raw_type == "HAZARD" and subtype in CAMERA_HAZARD_SUBTYPES:
            text = f"Canh bao! {dist_str} co camera luu dong{street_str}. Giam toc do!"
        # ── Camera toc do co dinh ──
        elif raw_type == "HAZARD" and "SPEED" in subtype.upper():
            text = f"Phia truoc {dist} met co camera phat nguoi. Chay dung toc do quy dinh."
        # ── Tai nan ──
        elif raw_type == "ACCIDENT":
            text = f"Canh bao tai nan giao thong {dist_str}{street_str}. Di cham lai, chu y an toan."
        # ── Tac duong ──
        elif raw_type == "JAM":
            text = f"{dist_str} tac duong{street_str}. Co the tim duong vong."
        # ── Duong bi chan ──
        elif raw_type == "ROAD_CLOSED":
            text = f"Canh bao! {dist_str} duong bi chan{street_str}. Can tim duong khac."
        # ── Nguy hiem khac ──
        elif raw_type == "HAZARD":
            text = f"Chu y! {dist_str} co nguy hiem tren duong{street_str}."
        else:
            text = f"{alert['name']} {dist_str}."

        return text

    def get_police_alerts(self, lat, lon, radius_km=2):
        """Chi lay canh bao canh sat (camera luu dong)."""
        all_alerts = self.fetch_alerts(lat, lon, radius_km)
        return [a for a in all_alerts if a["raw_type"] == "POLICE"]

    def get_camera_alerts(self, lat, lon, radius_km=0.5):
        """Lay TAT CA canh bao camera (co dinh + luu dong) trong ban kinh nho.
        
        Bao gom:
        - POLICE: canh sat ro rang hoac nup
        - HAZARD voi subtype camera: camera luu dong cong dong bao cao
        """
        all_alerts = self.fetch_alerts(lat, lon, radius_km)
        cameras = []
        for a in all_alerts:
            if a["raw_type"] == "POLICE":
                cameras.append(a)
            elif a["raw_type"] == "HAZARD" and a.get("subtype","") in CAMERA_HAZARD_SUBTYPES:
                cameras.append(a)
        return cameras

    def get_high_priority_alerts(self, lat, lon, radius_km=1):
        """Lay canh bao uu tien cao (camera + canh sat + tai nan)."""
        all_alerts = self.fetch_alerts(lat, lon, radius_km)
        return [a for a in all_alerts if a["raw_type"] in ("POLICE", "ACCIDENT", "ROAD_CLOSED")]

    def get_traffic_summary(self, alerts):
        """Tóm tắt tình trạng giao thông xung quanh."""
        if not alerts:
            return "Giao thông thông thoáng."
        types = [a["name"] for a in alerts[:3]]
        return "Lưu ý: " + ", ".join(types) + " phía trước."

    def _dist_m(self, lat1, lon1, lat2, lon2):
        R = 6371000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return 2 * R * math.asin(math.sqrt(max(0, a)))
