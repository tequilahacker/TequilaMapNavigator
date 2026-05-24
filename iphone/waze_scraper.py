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

# Waze Live Map endpoint (không chính thức - cộng đồng)
WAZE_GEORSS_URL = "https://www.waze.com/live-map/api/georss"
WAZE_ALERTS_URL = "https://www.waze.com/row-rtserver/web/TGeoRSS"  # Backup endpoint

# Waze alert type codes
WAZE_TYPE_MAP = {
    "POLICE":     {"type": "police",    "name": "Cảnh sát phía trước", "priority": 1},
    "ACCIDENT":   {"type": "accident",  "name": "Tai nạn giao thông",  "priority": 2},
    "JAM":        {"type": "traffic",   "name": "Tắc đường",           "priority": 3},
    "HAZARD":     {"type": "hazard",    "name": "Nguy hiểm đường",     "priority": 2},
    "ROAD_CLOSED":{"type": "closed",    "name": "Đường bị chặn",       "priority": 1},
    "WEATHERHAZARD": {"type": "weather","name": "Thời tiết xấu",       "priority": 3},
}

# Waze hazard subtypes liên quan đến camera
CAMERA_SUBTYPES = {
    "HAZARD_ON_ROAD_TRAFFIC_LIGHT_FAULT",
    "HAZARD_ON_ROAD_CAR_STOPPED",
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
        """Tạo text cảnh báo tiếng Việt cho Waze alert."""
        name = alert["name"]
        dist = alert["distance_m"]
        street = alert.get("street", "")

        if dist <= 50:
            dist_text = "ngay phía trước"
        elif dist <= 200:
            dist_text = f"{dist} mét"
        else:
            dist_text = f"{dist} mét"

        text = f"{name} {dist_text}."
        if street:
            text += f" Đường {street}."

        # Thêm khuyến nghị theo loại
        raw_type = alert.get("raw_type", "")
        if raw_type == "POLICE":
            text += " Chú ý giảm tốc độ!"
        elif raw_type == "ACCIDENT":
            text += " Chú ý an toàn, đi chậm lại."
        elif raw_type == "JAM":
            text += " Có thể tìm đường vòng."

        return text

    def get_police_alerts(self, lat, lon, radius_km=2):
        """Chỉ lấy cảnh báo cảnh sát (camera lưu động)."""
        all_alerts = self.fetch_alerts(lat, lon, radius_km)
        return [a for a in all_alerts if a["raw_type"] == "POLICE"]

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
