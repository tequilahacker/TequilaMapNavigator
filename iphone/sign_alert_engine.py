# iphone/sign_alert_engine.py
# Đọc biển báo giao thông Việt Nam: tốc độ, khu dân cư, trường học, cấm vượt
# Kết hợp OSM data + rule-based VN traffic law defaults

import math
import json

# ─── Giới hạn tốc độ mặc định theo Luật GTĐB Việt Nam cho XE MÁY ───
VN_DEFAULT_SPEED_LIMITS = {
    # Trong đô thị (khu dân cư)
    "residential":    50,   # Đường khu dân cư (xe máy mặc định 50-60 km/h)
    "living_street":  20,   # Ngõ, hẻm nhỏ
    "service":        20,   # Đường nội bộ
    # Ngoài đô thị
    "primary":        60,   # Quốc lộ ngoài đô thị (xe máy 60-70 km/h)
    "secondary":      50,   # Tỉnh lộ
    "tertiary":       50,   # Đường huyện
    "unclassified":   50,   # Đường chưa phân loại
    # Cao tốc / đường lớn (CẤM XE MÁY)
    "motorway":       0,    # Cao tốc
    "motorway_link":  0,
    "trunk":          70,   # Đường cao tốc thấp / quốc lộ lớn (xe máy tối đa 70-80 km/h)
    "trunk_link":     60,
    # Đặc biệt
    "school_zone":    40,   # Gần trường học (buffer 100m)
    "hospital_zone":  40,   # Gần bệnh viện
    "market_zone":    40,   # Gần chợ, đông người
}

# ─── Biển báo cần đọc to cho xe máy ───
SIGN_ANNOUNCEMENTS = {
    "school_zone":    "Chú ý! Khu vực trường học, giảm tốc xuống 40 km/h.",
    "hospital_zone":  "Khu vực bệnh viện, giảm tốc độ và không bấm còi.",
    "residential":    "Vào khu dân cư. Giới hạn tốc độ 50 km/h.",
    "highway_enter":  "Cảnh báo! Phía trước là đường cao tốc cấm xe máy, hãy quay lại ngay!",
    "highway_exit":   "Ra khỏi đường cao tốc.",
    "no_overtaking":  "Cấm vượt xe. Giữ nguyên làn đường.",
    "speed_30":       "Khu vực giới hạn 30 km/h.",
    "speed_40":       "Khu vực giới hạn 40 km/h.",
    "speed_60":       "Giới hạn tốc độ 60 km/h.",
    "speed_80":       "Giới hạn tốc độ 80 km/h.",
    "toll_booth":     "Sắp đến trạm thu phí, hãy đi vào làn xe máy bên phải.",
    "roundabout":     "Sắp vào vòng xuyến. Nhường đường xe đang lưu thông trong vòng.",
    "narrow_road":    "Đường hẹp phía trước. Nhường đường xe ngược chiều.",
    "bridge":         "Đang qua cầu. Không dừng đỗ trên cầu.",
    "tunnel":         "Đang vào hầm. Bật đèn pha và giảm tốc độ.",
    "flood_zone":     "Khu vực có thể ngập nước. Chú ý an toàn.",
}


class SignAlertEngine:
    """Đọc biển báo và cảnh báo tốc độ theo Luật Giao thông Đường bộ Việt Nam.
    
    Tích hợp:
    1. OSM road type → default speed limit theo VN law
    2. OSM node tags → school, hospital, market zones
    3. OSM way tags → no_overtaking, toll, bridge, tunnel
    """

    def __init__(self, osm_engine=None):
        self.osm = osm_engine
        self._current_zone = None        # Zone đang đi qua
        self._last_speed_limit = None    # Speed limit cuối cùng đã announce
        self._last_sign_announced = {}   # sign_type → timestamp

    # ─────────────────────────────────────────────
    # MAIN: LẤY TẤT CẢ BIỂN BÁO TẠI VỊ TRÍ HIỆN TẠI
    # ─────────────────────────────────────────────
    def get_sign_alerts(self, lat, lon, speed_kmh=0, current_road_type="residential"):
        """
        Trả về tất cả biển báo và cảnh báo tốc độ tại vị trí hiện tại.
        
        Returns dict:
        {
          "speed_limit": int,
          "speed_limit_changed": bool,    # Vừa đổi giới hạn tốc độ
          "speed_over": bool,
          "speed_over_kmh": int,
          "zone_type": str,               # "school_zone", "residential", etc.
          "zone_changed": bool,           # Vừa vào zone mới
          "signs": [str, ...],            # List các biển báo cần đọc
          "speak_texts": [str, ...],      # Text TTS cho từng biển
          "ble_sign_packet": str,         # SIGN|speed_limit|zone|over
        }
        """
        result = {
            "speed_limit": 60,
            "speed_limit_changed": False,
            "speed_over": False,
            "speed_over_kmh": 0,
            "zone_type": current_road_type,
            "zone_changed": False,
            "signs": [],
            "speak_texts": [],
            "ble_sign_packet": "",
        }

        # 1. Lấy giới hạn tốc độ
        speed_limit = self._get_speed_limit(lat, lon, current_road_type)
        result["speed_limit"] = speed_limit

        # Check đổi giới hạn tốc độ
        if speed_limit != self._last_speed_limit:
            if self._last_speed_limit is not None:
                result["speed_limit_changed"] = True
                sign_key = f"speed_{speed_limit}"
                if sign_key in SIGN_ANNOUNCEMENTS:
                    result["speak_texts"].append(SIGN_ANNOUNCEMENTS[sign_key])
            self._last_speed_limit = speed_limit

        # 2. Kiểm tra vượt tốc độ
        if speed_kmh > 0 and speed_limit:
            over = speed_kmh - speed_limit
            if over > 3:  # Tolerance nhỏ
                result["speed_over"] = True
                result["speed_over_kmh"] = int(over)
                if over > 15:
                    result["speak_texts"].append(
                        f"CẢNH BÁO! Vượt tốc độ {int(over)} km/h. Giảm tốc ngay!"
                    )

        # 3. Kiểm tra zones đặc biệt
        zone_alerts = self._check_special_zones(lat, lon)
        for zone_type, zone_text in zone_alerts:
            result["signs"].append(zone_type)
            # Chỉ announce mỗi zone 1 lần trong 5 phút
            import time
            last = self._last_sign_announced.get(zone_type, 0)
            if time.time() - last > 300:
                result["speak_texts"].append(zone_text)
                self._last_sign_announced[zone_type] = time.time()

        # 4. Check zone change
        zone = zone_alerts[0][0] if zone_alerts else current_road_type
        if zone != self._current_zone:
            result["zone_changed"] = True
            self._current_zone = zone

        # 5. BLE packet
        over_flag = "1" if result["speed_over"] else "0"
        limit_changed = "1" if result["speed_limit_changed"] else "0"
        result["ble_sign_packet"] = (
            f"SIGN|{speed_limit}|{zone}|{over_flag}|{limit_changed}"
        )

        return result

    # ─────────────────────────────────────────────
    # SPEED LIMIT RESOLUTION
    # ─────────────────────────────────────────────
    def _get_speed_limit(self, lat, lon, road_type="residential"):
        """Lấy giới hạn tốc độ theo thứ tự ưu tiên."""
        limit = None
        # 1. OSM snap-to-road
        if self.osm:
            try:
                limit, _ = self.osm.get_speed_limit_at(lat, lon)
            except Exception:
                pass

        if not limit:
            # 2. VN Law default theo loại đường
            limit = VN_DEFAULT_SPEED_LIMITS.get(road_type, 50)

        if limit > 80:
            limit = 80
        return limit

    # ─────────────────────────────────────────────
    # SPECIAL ZONE DETECTION
    # ─────────────────────────────────────────────
    def _check_special_zones(self, lat, lon):
        """Kiểm tra zones đặc biệt gần vị trí hiện tại.
        
        Trả về list of (zone_type, announcement_text)
        
        TODO: Khi có OSM POI data đầy đủ, query từ cache.
        Hiện tại: Dựa vào rule-based + OSM way tags.
        """
        zones = []
        # Placeholder - trong production query từ OSM POI cache
        # Ví dụ: check school nodes trong 200m
        return zones

    def announce_road_entry(self, road_type, speed_limit):
        """Tạo text thông báo khi bắt đầu đi vào loại đường mới."""
        if road_type == "motorway":
            return SIGN_ANNOUNCEMENTS["highway_enter"]
        elif road_type == "residential":
            return f"Vào khu dân cư. Giới hạn tốc độ {speed_limit} km/h."
        elif road_type in ("primary", "trunk"):
            return f"Vào quốc lộ. Giới hạn tốc độ {speed_limit} km/h."
        return f"Giới hạn tốc độ {speed_limit} km/h."

    def get_speed_limit_display(self, speed_limit):
        """Tạo string hiển thị biển báo trên ESP32 TFT.
        
        Returns: "60" (chỉ số, hiển thị trong vòng tròn đỏ trên màn hình)
        """
        return str(speed_limit) if speed_limit else "?"

    # ─────────────────────────────────────────────
    # VIETNAM TRAFFIC LAW FACTS
    # ─────────────────────────────────────────────
    def get_speed_limit_info(self, road_type):
        """Giải thích quy định tốc độ theo luật VN."""
        limits = VN_DEFAULT_SPEED_LIMITS.get(road_type, 60)
        explanations = {
            "motorway":   f"Cao tốc: tối thiểu 60, tối đa {limits} km/h",
            "primary":    f"Quốc lộ ngoài đô thị: tối đa {limits} km/h",
            "residential":f"Đường đô thị: tối đa {limits} km/h",
            "school_zone":f"Gần trường học: tối đa {limits} km/h",
        }
        return explanations.get(road_type, f"Giới hạn tốc độ: {limits} km/h")
