# iphone/gps_tracker.py
# Pythonista 3 - Realtime GPS tracking + stream về ESP32 qua BLE
import time
import math

try:
    import location
    HAS_LOCATION = True
except ImportError:
    HAS_LOCATION = False
    print("[GPS] Chạy ngoài Pythonista, dùng mock GPS.")

class GPSTracker:
    """Theo dõi vị trí iPhone realtime và stream sang ESP32 qua BLE."""
    
    def __init__(self):
        self._last_loc = None
        self._last_heading = 0
        self._prev_lat = None
        self._prev_lon = None
        self._manual_loc = None
        self._manual_speed = 0
        
        if HAS_LOCATION:
            location.start_updates()
            # Chờ GPS lock ban đầu
            time.sleep(1.5)
            
    def get_current(self):
        """Lấy vị trí hiện tại. Trả về (lat, lon, heading, accuracy_m)."""
        if self._manual_loc is not None:
            return self._manual_loc
        if HAS_LOCATION:
            try:
                loc = location.get_gps()
                if loc:
                    lat = loc['latitude']
                    lon = loc['longitude']
                    accuracy = loc.get('horizontal_accuracy', 5)
                    heading = loc.get('course', -1)  # -1 nếu không available
                    
                    # Tính heading từ 2 vị trí liên tiếp nếu course không có
                    if heading < 0 and self._prev_lat is not None:
                        heading = self._calc_heading(self._prev_lat, self._prev_lon, lat, lon)
                    
                    self._prev_lat, self._prev_lon = lat, lon
                    self._last_heading = max(0, heading)
                    self._last_loc = (lat, lon, self._last_heading, accuracy)
                    return self._last_loc
            except Exception as e:
                print("[GPS] Lỗi:", e)
                
        # Fallback mock GPS (khu vực Quận 1, HCMC)
        import random
        lat = 10.7769 + random.uniform(-0.001, 0.001)
        lon = 106.7009 + random.uniform(-0.001, 0.001)
        return (lat, lon, 45.0, 5.0)
        
    def get_speed_kmh(self):
        """Lấy tốc độ hiện tại (km/h) từ GPS."""
        if self._manual_loc is not None:
            return self._manual_speed
        if HAS_LOCATION:
            try:
                loc = location.get_gps()
                if loc:
                    speed_ms = loc.get('speed', 0)
                    if speed_ms >= 0:
                        return round(speed_ms * 3.6, 1)
            except Exception:
                pass
        return 0
        
    def format_for_ble(self, route_polyline=None, camera_str="", nav_step=None):
        """Tạo MAP packet hoàn chỉnh để gửi về ESP32.
        
        Format: MAP|lat,lon,heading,gps_acc|route_polyline|camera_list
        """
        loc = self.get_current()
        lat, lon, heading, accuracy = loc
        acc_str = f"{int(accuracy)}m"
        
        # Route polyline (tối đa 25 điểm để fit BLE)
        route_str = ""
        if route_polyline:
            pts = route_polyline[:25]
            route_str = ";".join([f"{p[0]:.6f},{p[1]:.6f}" for p in pts])
            
        return f"MAP|{lat:.6f},{lon:.6f},{heading:.1f},{acc_str}|{route_str}|{camera_str}"
        
    def _calc_heading(self, lat1, lon1, lat2, lon2):
        """Tính góc hướng đi (bearing) giữa 2 điểm GPS."""
        import math
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        angle = math.degrees(math.atan2(dlon, dlat))
        return (angle + 360) % 360
        
    def stop(self):
        if HAS_LOCATION:
            try:
                location.stop_updates()
            except Exception:
                pass
