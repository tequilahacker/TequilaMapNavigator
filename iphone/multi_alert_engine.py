# iphone/multi_alert_engine.py  (PHIÊN BẢN MỚI - Hoàn toàn miễn phí)
# Tổng hợp cảnh báo từ: OSM + Waze (real-time) + CSV custom
# KHÔNG dùng Vietmap (có phí)
# WYN chạy riêng ở overlay mode trên iPhone

import math
import time


class MultiAlertEngine:
    """
    Engine tổng hợp tất cả nguồn dữ liệu an toàn giao thông - MIỄN PHÍ HOÀN TOÀN.
    
    NGUỒN 1: OpenStreetMap (osm_engine)
      → Camera cố định toàn VN, offline sau lần đầu tải
      → Speed limit theo từng đoạn đường
    
    NGUỒN 2: Waze Live Map (waze_scraper)  
      → Real-time: cảnh sát (camera lưu động!), tai nạn, tắc đường
      → Cập nhật mỗi 45 giây
      → MIỄN PHÍ, cộng đồng 140 triệu user cập nhật
    
    NGUỒN 3: CSV tự tổng hợp (csv_engine)
      → Database tự cập nhật của user
    
    WYN (NGOÀI HỆ THỐNG):
      → Chạy overlay trên iPhone, tự hiện cảnh báo riêng
      → 6.000+ camera + 12.000+ biển báo offline VN
      → Không có API, dùng qua Overlay Mode
    """

    ALERT_RANGES = [500, 300, 150, 50]  # mét - ngưỡng announce
    DEDUP_RADIUS_M = 40                  # Camera cách nhau < 40m → trùng

    def __init__(self, osm_engine=None, waze_scraper=None, csv_engine=None):
        self.osm = osm_engine
        self.waze = waze_scraper
        self.csv = csv_engine
        self._merged_cameras = []         # Camera cố định (OSM + CSV, đã dedup)
        self._last_merge_time = 0
        self._last_alert_distances = {}   # camera_id → last announced distance
        self._waze_alerts = []            # Real-time Waze alerts (cảnh sát, tai nạn)
        self._last_waze_fetch = 0

    # ─────────────────────────────────────────────
    # MERGE CAMERA CỐ ĐỊNH (OSM + CSV)
    # ─────────────────────────────────────────────
    def merge_all_cameras(self):
        """Gộp camera từ OSM + CSV, xóa trùng lặp."""
        all_cameras = []

        # CSV custom (user tự thêm)
        if self.csv and hasattr(self.csv, 'cameras'):
            for cam in self.csv.cameras:
                all_cameras.append({**cam, "priority": 1, "source": "csv"})

        # OSM (toàn quốc)
        if self.osm and hasattr(self.osm, 'cameras'):
            for cam in self.osm.cameras:
                all_cameras.append({**cam, "priority": 2, "source": "osm"})

        # Dedup
        merged = []
        for cam in sorted(all_cameras, key=lambda x: x["priority"]):
            is_dup = any(
                self._dist_m(cam["lat"], cam["lon"], ex["lat"], ex["lon"]) < self.DEDUP_RADIUS_M
                for ex in merged
            )
            if not is_dup:
                merged.append(cam)

        self._merged_cameras = merged
        self._last_merge_time = time.time()
        print(f"[MultiAlert] Camera cố định: {len(all_cameras)} → {len(merged)} (sau dedup)")
        return merged

    # ─────────────────────────────────────────────
    # MAIN: LẤY TOÀN BỘ CẢNH BÁO
    # ─────────────────────────────────────────────
    def get_full_alert_packet(self, lat, lon, speed_kmh=0, heading=0, warn_dist_m=50):
        """
        Tổng hợp cảnh báo từ TẤT CẢ nguồn cho vị trí hiện tại.
        
        Returns:
        {
          "cameras_nearby": [...],   # Camera cố định gần nhất
          "waze_alerts": [...],      # Real-time Waze alerts (cảnh sát, tai nạn)
          "camera_alert": {...},     # Camera cần announce ngay
          "waze_alert": {...},       # Waze alert cần announce ngay
          "speak_text": str,         # Text đọc lên (ưu tiên cao nhất)
          "speed_limit": int,
          "speed_over": bool,
          "ble_payload": str,        # Gửi về ESP32
        }
        """
        result = {
            "cameras_nearby": [],
            "waze_alerts": [],
            "camera_alert": None,
            "waze_alert": None,
            "speak_text": "",
            "speed_limit": 60,
            "speed_over": False,
            "speed_over_amount": 0,
            "ble_payload": "",
        }

        # Refresh merge nếu lâu
        if time.time() - self._last_merge_time > 300:
            self.merge_all_cameras()

        # ── 1. Camera cố định (OSM + CSV) ──
        nearby_fixed = []
        for cam in self._merged_cameras:
            dist = self._dist_m(lat, lon, cam["lat"], cam["lon"])
            if dist <= 500:
                nearby_fixed.append({**cam, "distance_m": int(dist)})
        nearby_fixed.sort(key=lambda x: x["distance_m"])
        result["cameras_nearby"] = nearby_fixed[:5]

        # Announce camera cố định theo ngưỡng (tính từ warn_dist_m)
        alert_ranges = [warn_dist_m * 10, warn_dist_m * 3, warn_dist_m, warn_dist_m // 2]
        if nearby_fixed:
            closest = nearby_fixed[0]
            cam_id = closest.get("osm_id") or f"{closest['lat']:.4f},{closest['lon']:.4f}"
            dist = closest["distance_m"]
            last_dist = self._last_alert_distances.get(cam_id, 9999)

            for threshold in alert_ranges:
                if dist <= threshold < last_dist:
                    result["camera_alert"] = closest
                    result["speak_text"] = self._camera_text(closest, speed_kmh)
                    self._last_alert_distances[cam_id] = dist
                    break

            if dist > last_dist + 100:
                self._last_alert_distances.pop(cam_id, None)


        # ── 2. Waze real-time alerts (cảnh sát + tai nạn) ──
        if self.waze:
            try:
                waze_fresh = self.waze.fetch_alerts(lat, lon, radius_km=3)
                result["waze_alerts"] = waze_fresh[:5]

                # Announce Waze alerts chưa được nói
                new_waze = self.waze.get_new_alerts(lat, lon, radius_km=2)
                if new_waze:
                    top = new_waze[0]
                    waze_text = self.waze.build_alert_text(top)
                    # Waze cảnh sát ưu tiên hơn camera cố định
                    if top.get("raw_type") == "POLICE" and top["distance_m"] < 500:
                        result["waze_alert"] = top
                        # Override speak_text nếu cảnh sát gần hơn camera
                        if not result["speak_text"] or top["distance_m"] < nearby_fixed[0]["distance_m"] if nearby_fixed else True:
                            result["speak_text"] = waze_text
                    elif top["distance_m"] < 300:
                        result["waze_alert"] = top
                        if not result["speak_text"]:
                            result["speak_text"] = waze_text
                    self.waze.mark_announced(top["id"])
            except Exception as e:
                print("[MultiAlert] Waze error:", e)

        # ── 3. Speed limit ──
        speed_limit = 50
        if self.osm:
            try:
                limit, _ = self.osm.get_speed_limit_at(lat, lon)
                if limit:
                    speed_limit = limit
            except Exception:
                pass
        if speed_limit > 80:
            speed_limit = 80
        result["speed_limit"] = speed_limit

        # ── 3b. Motorcycle ban check ──
        result["motorcycle_banned_warning"] = ""
        if self.osm and hasattr(self.osm, 'check_motorcycle_ban'):
            is_banned, ban_road_name = self.osm.check_motorcycle_ban(lat, lon, search_radius_m=45)
            if is_banned:
                result["motorcycle_banned_warning"] = f"CẤM XE MÁY: {ban_road_name}"
                last_ban_warn = self._last_alert_distances.get("ban_warning", 0)
                if time.time() - last_ban_warn > 20: # 20 seconds cooldown
                    self._last_alert_distances["ban_warning"] = time.time()
                    ban_speak = f"Cảnh báo! Phía trước là đường cấm xe máy {ban_road_name}. Hãy quay lại ngay!"
                    result["speak_text"] = ban_speak
            else:
                self._last_alert_distances.pop("ban_warning", None)

        # ── 4. Speed over check ──
        if speed_kmh > 0:
            over = speed_kmh - speed_limit
            if over > 5:
                result["speed_over"] = True
                result["speed_over_amount"] = int(over)
                if over > 20 and not result["speak_text"]:
                    result["speak_text"] = f"Cảnh báo! Đang vượt tốc độ {int(over)} km/h!"

        # ── 5. BLE payload ──
        # Format: ALERT|speed_limit|current_speed|speed_over|cam1|cam2|...
        cams_str = ";".join([
            f"{c['lat']:.6f},{c['lon']:.6f},{c.get('type','speed')},{c['distance_m']}"
            for c in result["cameras_nearby"][:3]
        ])
        # Thêm Waze alerts (cảnh sát) vào payload với prefix W
        waze_str = ";".join([
            f"W{a['lat']:.6f},{a['lon']:.6f},{a['type']},{a['distance_m']}"
            for a in result["waze_alerts"][:2]
        ])
        all_alerts_str = ";".join(filter(None, [cams_str, waze_str]))

        result["ble_payload"] = (
            f"ALERT|{speed_limit}|{int(speed_kmh)}|"
            f"{'1' if result['speed_over'] else '0'}|{all_alerts_str}"
        )

        return result

    def _camera_text(self, camera, speed_kmh=0):
        """Text cảnh báo camera tiếng Việt."""
        dist = camera["distance_m"]
        cam_type = camera.get("type", "speed")
        limit = camera.get("speed_limit", 60)

        dist_val = 50 if dist <= 55 else dist
        
        if cam_type == "speed":
            text = f"phía trước {dist_val} mét có camera phạt nguội"
            if limit:
                text += f", giới hạn tốc độ là {limit} km/g"
            if speed_kmh > 0 and limit and speed_kmh > limit:
                text += f", yêu cầu chạy đúng tốc độ quy định {limit} km/g"
        elif cam_type == "red_light":
            text = f"phía trước {dist_val} mét có camera phạt nguội vượt đèn đỏ"
        else:
            text = f"phía trước {dist_val} mét có camera phạt nguội giám sát"
        return text

    def _build_camera_alert_text(self, camera, speed_kmh=0):
        """Alias cho tương thích với ble_helper_ios.py cũ."""
        return self._camera_text(camera, speed_kmh)

    def get_stats(self):
        osm_count = len(self.osm.cameras) if self.osm and hasattr(self.osm, 'cameras') else 0
        csv_count = len(self.csv.cameras) if self.csv and hasattr(self.csv, 'cameras') else 0
        return {
            "merged_cameras": len(self._merged_cameras),
            "csv_cameras": csv_count,
            "osm_cameras": osm_count,
            "waze_active": self.waze is not None,
            "total_sources": "OSM + Waze (real-time) + CSV + WYN (overlay)",
        }

    def get_nearby_cameras(self, lat, lon, radius_m=500):
        """Trả về cameras cố định đã gộp trong bán kính radius_m, sắp xếp từ gần đến xa."""
        nearby = []
        for cam in self._merged_cameras:
            dist = self._dist_m(lat, lon, cam["lat"], cam["lon"])
            if dist <= radius_m:
                nearby.append({**cam, "distance_m": int(dist)})
        nearby.sort(key=lambda x: x["distance_m"])
        return nearby

    def _dist_m(self, lat1, lon1, lat2, lon2):
        import math
        R = 6371000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return 2 * R * math.asin(math.sqrt(max(0, a)))
