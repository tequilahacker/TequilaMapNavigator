# iphone/camera_alert.py
# Pythonista 3 - Camera phạt nguội proximity engine
import math
import csv
import io

class CameraAlertEngine:
    """Đọc CSV camera phạt nguội, tính khoảng cách và cảnh báo realtime."""
    
    ALERT_RADIUS_M = 500  # Bán kính cảnh báo (mét)
    
    def __init__(self, csv_path=None, csv_text=None):
        self.cameras = []
        if csv_path:
            self.load_from_file(csv_path)
        elif csv_text:
            self.load_from_text(csv_text)
            
    def load_from_file(self, path):
        """Đọc CSV từ đường dẫn file (iCloud Drive hoặc local)."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self._parse_csv(f)
            print(f"[Camera] Đã tải {len(self.cameras)} camera từ {path}")
        except Exception as e:
            print(f"[Camera] Lỗi đọc file: {e}")
            
    def load_from_text(self, csv_text):
        """Đọc CSV từ string (nhận qua BLE hoặc hardcode)."""
        self._parse_csv(io.StringIO(csv_text))
        print(f"[Camera] Đã tải {len(self.cameras)} camera từ text")
        
    def _parse_csv(self, file_obj):
        """Parse CSV với format: latitude,longitude,camera_type,description,speed_limit"""
        reader = csv.DictReader(file_obj)
        self.cameras = []
        for row in reader:
            try:
                self.cameras.append({
                    "lat": float(row["latitude"]),
                    "lon": float(row["longitude"]),
                    "type": row.get("camera_type", "speed"),
                    "desc": row.get("description", "Camera phạt nguội"),
                    "speed_limit": int(row.get("speed_limit", 60)),
                })
            except (KeyError, ValueError):
                pass  # Bỏ qua dòng lỗi
                
    def get_nearby_cameras(self, current_lat, current_lon, radius_m=None):
        """Trả về danh sách camera trong bán kính radius_m, sắp xếp theo khoảng cách."""
        radius = radius_m or self.ALERT_RADIUS_M
        nearby = []
        for cam in self.cameras:
            dist = self._haversine_m(current_lat, current_lon, cam["lat"], cam["lon"])
            if dist <= radius:
                nearby.append({**cam, "distance_m": int(dist)})
        # Sắp xếp: gần nhất trước
        nearby.sort(key=lambda x: x["distance_m"])
        return nearby
        
    def get_alert_text(self, camera, current_speed_kmh=0):
        """Tạo text cảnh báo tiếng Việt phù hợp cho từng loại camera."""
        dist = camera["distance_m"]
        cam_type = camera.get("type", "speed")
        limit = camera.get("speed_limit", 60)
        
        if cam_type == "speed":
            if dist < 100:
                prefix = "KHẨN CẤP! Camera tốc độ"
            else:
                prefix = "Chú ý! Camera tốc độ"
            return f"{prefix} {dist}m phía trước. Giới hạn {limit} km/h."
        elif cam_type == "red_light":
            return f"Camera vượt đèn đỏ {dist}m phía trước. Chú ý đèn tín hiệu."
        else:
            return f"Camera giám sát {dist}m phía trước."
            
    def format_for_ble(self, nearby_cameras, max_cameras=3):
        """Format danh sách camera thành chuỗi BLE compact.
        
        Format: lat,lon,type;lat,lon,type;...
        """
        cams = nearby_cameras[:max_cameras]
        return ";".join([f"{c['lat']},{c['lon']},{c['type']}" for c in cams])
        
    def _haversine_m(self, lat1, lon1, lat2, lon2):
        R = 6371000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return 2 * R * math.asin(math.sqrt(a))
