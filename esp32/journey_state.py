# esp32/journey_state.py
# Lưu và khôi phục trạng thái hành trình vào flash filesystem của ESP32
import json
import os

JOURNEY_FILE = "/journey.json"

class JourneyStateManager:
    """Quản lý trạng thái hành trình persistent - tồn tại qua các lần tắt/bật máy xe."""
    
    def __init__(self):
        self.state = {
            "active": False,
            "waypoints": [],        # Danh sách điểm đến chưa qua: [(lat, lon, name), ...]
            "completed_waypoints": [],  # Điểm đã đến
            "current_route": [],    # Polyline coords hiện tại
            "cameras": [],          # Camera list từ CSV
            "last_position": None,  # (lat, lon, heading) cuối cùng
            "destination_name": "", # Tên điểm đến cuối
            "eta_seconds": 0,       # ETA còn lại (giây)
        }
        
    def has_saved_journey(self):
        """Kiểm tra có hành trình đang dở trong flash không."""
        try:
            os.stat(JOURNEY_FILE)
            with open(JOURNEY_FILE, 'r') as f:
                data = json.load(f)
                return data.get("active", False)
        except (OSError, ValueError):
            return False
    
    def save(self):
        """Ghi trạng thái hành trình vào flash filesystem."""
        try:
            with open(JOURNEY_FILE, 'w') as f:
                json.dump(self.state, f)
            print("[Journey] Trạng thái hành trình đã lưu vào flash.")
        except Exception as e:
            print("[Journey] Lỗi lưu hành trình:", e)
            
    def load(self):
        """Đọc trạng thái hành trình từ flash."""
        try:
            with open(JOURNEY_FILE, 'r') as f:
                self.state = json.load(f)
            print("[Journey] Đã khôi phục hành trình từ flash.")
            return True
        except (OSError, ValueError) as e:
            print("[Journey] Không có hành trình lưu:", e)
            return False
            
    def clear(self):
        """Xóa hành trình khi user yêu cầu dừng hoặc đã đến đích."""
        self.state["active"] = False
        self.state["waypoints"] = []
        self.state["current_route"] = []
        self.state["last_position"] = None
        try:
            os.remove(JOURNEY_FILE)
        except OSError:
            pass
        print("[Journey] Hành trình đã xóa.")
        
    def start_journey(self, waypoints, destination_name):
        """Bắt đầu hành trình mới với danh sách waypoints.
        
        waypoints: [(lat, lon, name), ...]  - từ Google Maps API
        destination_name: str - tên điểm đến cuối
        """
        self.state["active"] = True
        self.state["waypoints"] = [list(wp) for wp in waypoints]
        self.state["completed_waypoints"] = []
        self.state["destination_name"] = destination_name
        self.state["current_route"] = []
        self.save()
        
    def update_position(self, lat, lon, heading):
        """Cập nhật vị trí hiện tại của xe."""
        self.state["last_position"] = [lat, lon, heading]
        # Auto-save mỗi khi update vị trí (bảo vệ khi mất điện đột ngột)
        self.save()
        
    def update_route(self, polyline, cameras, eta_seconds):
        """Cập nhật route mới từ Google Maps API."""
        self.state["current_route"] = polyline
        self.state["cameras"] = cameras
        self.state["eta_seconds"] = eta_seconds
        
    def mark_waypoint_reached(self, index):
        """Đánh dấu một điểm đã đến và chuyển sang điểm tiếp theo."""
        if index < len(self.state["waypoints"]):
            reached = self.state["waypoints"].pop(index)
            self.state["completed_waypoints"].append(reached)
            self.save()
            print(f"[Journey] Đã đến waypoint: {reached[2]}")
            
    def is_journey_complete(self):
        """Kiểm tra đã đến tất cả điểm đến chưa."""
        return self.state["active"] and len(self.state["waypoints"]) == 0
    
    @property
    def next_waypoint(self):
        """Điểm đến tiếp theo (lat, lon, name) hoặc None."""
        wps = self.state.get("waypoints", [])
        return tuple(wps[0]) if wps else None
    
    @property
    def remaining_waypoints(self):
        """Danh sách điểm đến còn lại."""
        return [tuple(wp) for wp in self.state.get("waypoints", [])]
    
    @property
    def last_position(self):
        pos = self.state.get("last_position")
        return tuple(pos) if pos else None
    
    @property
    def is_active(self):
        return self.state.get("active", False)
