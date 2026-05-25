# iphone/osm_speed_engine.py
# OpenStreetMap Overpass API - Camera + Giới Hạn Tốc Độ TOÀN QUỐC VIỆT NAM
# Miễn phí, offline-capable, cập nhật từ cộng đồng

import json
import math
import time
import os

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# Overpass API endpoints (mirror để backup)
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# Cache file local (trong iCloud hoặc Documents Pythonista)
CACHE_DIR = os.path.expanduser("~/Documents/tequila_cache")
CAMERA_CACHE_FILE = os.path.join(CACHE_DIR, "osm_cameras_vn.json")
SPEEDLIMIT_CACHE_FILE = os.path.join(CACHE_DIR, "osm_speedlimits_vn.json")
BANNEDWAY_CACHE_FILE = os.path.join(CACHE_DIR, "osm_bannedways_vn.json")

# Bounding box Việt Nam
VN_BBOX = "8.0,102.0,23.5,110.0"  # south,west,north,east


class OSMSpeedEngine:
    """Lấy và cache dữ liệu camera + giới hạn tốc độ từ OpenStreetMap cho VN."""

    def __init__(self):
        self.cameras = []           # List of {lat, lon, type, speed_limit, name}
        self.speed_ways = []        # List of road segments with speed limits
        self.banned_ways = []       # List of road segments banned for motorcycles
        self._ensure_cache_dir()
        self._load_cache()

    # ─────────────────────────────────────────────
    # INIT & CACHE
    # ─────────────────────────────────────────────
    def _ensure_cache_dir(self):
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
        except Exception:
            pass

    def _load_cache(self):
        """Đọc cache từ local file nếu có."""
        try:
            with open(CAMERA_CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.cameras = data.get("cameras", [])
                print(f"[OSM] Đã load {len(self.cameras)} camera từ cache.")
        except (FileNotFoundError, json.JSONDecodeError):
            print("[OSM] Chưa có cache camera. Cần chạy update_from_osm() lần đầu.")

        try:
            with open(SPEEDLIMIT_CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.speed_ways = data.get("ways", [])
                print(f"[OSM] Đã load {len(self.speed_ways)} đoạn đường từ cache.")
        except (FileNotFoundError, json.JSONDecodeError):
            print("[OSM] Chưa có cache speed limits.")

        try:
            with open(BANNEDWAY_CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.banned_ways = data.get("banned_ways", [])
                print(f"[OSM] Đã load {len(self.banned_ways)} đường cấm xe máy từ cache.")
        except (FileNotFoundError, json.JSONDecodeError):
            print("[OSM] Chưa có cache đường cấm xe máy.")

    def _save_cache(self):
        """Lưu data vào cache local."""
        try:
            with open(CAMERA_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    "cameras": self.cameras,
                    "updated": time.strftime("%Y-%m-%d %H:%M")
                }, f, ensure_ascii=False, indent=2)
            with open(SPEEDLIMIT_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    "ways": self.speed_ways,
                    "updated": time.strftime("%Y-%m-%d %H:%M")
                }, f, ensure_ascii=False, indent=2)
            with open(BANNEDWAY_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    "banned_ways": self.banned_ways,
                    "updated": time.strftime("%Y-%m-%d %H:%M")
                }, f, ensure_ascii=False, indent=2)
            print(f"[OSM] Cache đã lưu: {len(self.cameras)} cameras, {len(self.speed_ways)} ways, {len(self.banned_ways)} banned ways")
        except Exception as e:
            print("[OSM] Lỗi lưu cache:", e)

    # ─────────────────────────────────────────────
    # FETCH TỪ OSM OVERPASS API
    # ─────────────────────────────────────────────
    def update_from_osm(self, bbox=VN_BBOX, timeout=120):
        """Fetch toàn bộ camera + speed limit + banned ways từ OSM cho Việt Nam.
        
        Chỉ cần chạy 1 lần, sau đó dùng cache.
        Thời gian: ~30-60 giây cho toàn VN.
        """
        if not HAS_REQUESTS:
            print("[OSM] Không có requests module. Dùng built-in urllib.")
            return self._update_with_urllib(bbox, timeout)

        # Query Overpass QL - lấy camera + speed limit + banned roads
        query = f"""
[out:json][timeout:{timeout}];
(
  node["highway"="speed_camera"]({bbox});
  node["enforcement"="maxspeed"]({bbox});
  node["enforcement"="traffic_signals"]({bbox});
  way["maxspeed"]({bbox});
  way["highway"="motorway"]({bbox});
  way["highway"="motorway_link"]({bbox});
  way["motorcycle"="no"]({bbox});
  way["motor_vehicle"="no"]({bbox});
);
out body geom;
"""
        for endpoint in OVERPASS_ENDPOINTS:
            try:
                print(f"[OSM] Fetching từ {endpoint}...")
                r = requests.post(endpoint, data={"data": query}, timeout=timeout)
                if r.status_code == 200:
                    data = r.json()
                    self._parse_osm_response(data)
                    self._save_cache()
                    print(f"[OSM] ✅ Cập nhật thành công từ OSM!")
                    return True
            except Exception as e:
                print(f"[OSM] Lỗi với {endpoint}: {e}")

        print("[OSM] ❌ Không thể fetch từ Overpass API.")
        return False

    def update_region(self, lat, lon, radius_km=50):
        """Fetch data cho vùng xung quanh vị trí hiện tại (radius_km).
        Dùng khi chỉ cần cập nhật vùng đang đi qua.
        """
        if not HAS_REQUESTS:
            return False
        # Tính bounding box từ center + radius
        dlat = radius_km / 111.0
        dlon = radius_km / (111.0 * math.cos(math.radians(lat)))
        bbox = f"{lat-dlat},{lon-dlon},{lat+dlat},{lon+dlon}"
        return self.update_from_osm(bbox=bbox, timeout=30)

    def _update_with_urllib(self, bbox, timeout):
        """Fallback dùng urllib built-in."""
        try:
            import urllib.request
            import urllib.parse
            query = f'[out:json][timeout:{timeout}];(node["highway"="speed_camera"]({bbox});way["highway"="motorway"]({bbox});way["motorcycle"="no"]({bbox}););out body geom;'
            data = urllib.parse.urlencode({"data": query}).encode()
            req = urllib.request.Request(OVERPASS_ENDPOINTS[0], data=data, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode())
                self._parse_osm_response(result)
                self._save_cache()
                return True
        except Exception as e:
            print("[OSM] urllib fallback error:", e)
            return False

    # ─────────────────────────────────────────────
    # PARSE OSM RESPONSE
    # ─────────────────────────────────────────────
    def _parse_osm_response(self, data):
        """Parse OSM JSON response, tách nodes (cameras), ways (roads), và banned ways."""
        new_cameras = []
        new_ways = []
        new_banned_ways = []

        for element in data.get("elements", []):
            tags = element.get("tags", {})
            elem_type = element.get("type")

            if elem_type == "node":
                lat = element.get("lat")
                lon = element.get("lon")
                if lat is None or lon is None:
                    continue

                highway = tags.get("highway", "")
                enforcement = tags.get("enforcement", "")

                if highway == "speed_camera" or enforcement == "maxspeed":
                    cam = {
                        "lat": lat,
                        "lon": lon,
                        "type": "speed",
                        "speed_limit": int(tags.get("maxspeed", 60)),
                        "name": tags.get("name", "Camera tốc độ"),
                        "source": "osm",
                        "direction": tags.get("camera:direction", "both"),
                        "osm_id": element.get("id"),
                    }
                    # Cap speed limits on camera too
                    if cam["speed_limit"] > 80:
                        cam["speed_limit"] = 80
                    new_cameras.append(cam)
                elif enforcement == "traffic_signals":
                    new_cameras.append({
                        "lat": lat, "lon": lon,
                        "type": "red_light",
                        "speed_limit": 40,
                        "name": "Camera đèn đỏ",
                        "source": "osm",
                        "osm_id": element.get("id"),
                    })

            elif elem_type == "way":
                highway = tags.get("highway", "")
                motorcycle = tags.get("motorcycle", "")
                motor_vehicle = tags.get("motor_vehicle", "")
                
                # Check cấm xe máy
                is_banned = False
                if highway in ("motorway", "motorway_link"):
                    is_banned = True
                elif motorcycle == "no" or motor_vehicle == "no":
                    is_banned = True

                geometry = element.get("geometry", [])
                if geometry:
                    coords = [[g["lat"], g["lon"]] for g in geometry]
                    
                    if is_banned:
                        new_banned_ways.append({
                            "nodes": coords,
                            "road_type": highway,
                            "name": tags.get("name", "Đường cấm xe máy/Cao tốc"),
                            "osm_id": element.get("id"),
                        })

                    maxspeed = tags.get("maxspeed", "")
                    if maxspeed:
                        # Parse speed limit (có thể là "60", "60 mph", "VN:urban", etc.)
                        speed = self._parse_speed(maxspeed)
                        if speed:
                            new_ways.append({
                                "nodes": coords,
                                "speed_limit": speed,
                                "road_type": highway,
                                "name": tags.get("name", ""),
                                "osm_id": element.get("id"),
                            })

        # Merge với existing (dedup by OSM ID)
        existing_ids = {c.get("osm_id") for c in self.cameras}
        added = [c for c in new_cameras if c.get("osm_id") not in existing_ids]
        self.cameras.extend(added)

        existing_way_ids = {w.get("osm_id") for w in self.speed_ways}
        added_ways = [w for w in new_ways if w.get("osm_id") not in existing_way_ids]
        self.speed_ways.extend(added_ways)

        existing_banned_ids = {w.get("osm_id") for w in self.banned_ways}
        added_banned = [w for w in new_banned_ways if w.get("osm_id") not in existing_banned_ids]
        self.banned_ways.extend(added_banned)

        print(f"[OSM] Parsed: +{len(added)} cameras, +{len(added_ways)} road segments, +{len(added_banned)} banned segments")

    def _parse_speed(self, maxspeed_str):
        """Chuyển đổi maxspeed string thành int km/h cho XE MÁY."""
        if not maxspeed_str:
            return None
        # Vietnam default speeds theo loại đường cho xe máy
        vn_defaults = {
            "VN:urban": 50, "VN:rural": 80,
            "VN:living_street": 20, "VN:motorway": 0, # Cấm xe máy
        }
        if maxspeed_str in vn_defaults:
            speed = vn_defaults[maxspeed_str]
        else:
            try:
                # "60 mph" → convert to km/h
                if "mph" in maxspeed_str:
                    speed = int(float(maxspeed_str.replace("mph", "").strip()) * 1.60934)
                else:
                    speed = int(float(maxspeed_str.split()[0]))
            except (ValueError, IndexError):
                return None
                
        # Giới hạn tốc độ xe máy (xe mô tô) tối đa tại VN là 80 km/h
        if speed > 80:
            speed = 80
        return speed

    # ─────────────────────────────────────────────
    # RUNTIME QUERIES
    # ─────────────────────────────────────────────
    def get_nearby_cameras(self, lat, lon, radius_m=500):
        """Trả về cameras trong bán kính, sắp xếp gần → xa."""
        result = []
        for cam in self.cameras:
            dist = self._dist_m(lat, lon, cam["lat"], cam["lon"])
            if dist <= radius_m:
                result.append({**cam, "distance_m": int(dist)})
        result.sort(key=lambda x: x["distance_m"])
        return result

    def get_speed_limit_at(self, lat, lon, search_radius_m=50):
        """Tìm giới hạn tốc độ tại vị trí hiện tại (snap to nearest road).
        
        Trả về (speed_limit_kmh, road_name) hoặc (None, None) nếu không tìm thấy.
        """
        best_dist = float('inf')
        best_speed = None
        best_name = ""

        for way in self.speed_ways:
            nodes = way.get("nodes", [])
            for i in range(len(nodes) - 1):
                a = nodes[i]
                b = nodes[i + 1]
                dist = self._point_to_segment_dist(lat, lon, a[0], a[1], b[0], b[1])
                if dist < best_dist and dist <= search_radius_m:
                    best_dist = dist
                    best_speed = way["speed_limit"]
                    best_name = way.get("name", "")

        return (best_speed, best_name)

    def check_motorcycle_ban(self, lat, lon, search_radius_m=45):
        """Kiểm tra xem vị trí hiện tại có ở trên hoặc rất gần đường cấm xe máy hay không.
        
        Trả về (is_banned, road_name) hoặc (False, "")
        """
        best_dist = float('inf')
        best_name = ""
        is_banned = False

        for way in self.banned_ways:
            nodes = way.get("nodes", [])
            for i in range(len(nodes) - 1):
                a = nodes[i]
                b = nodes[i + 1]
                dist = self._point_to_segment_dist(lat, lon, a[0], a[1], b[0], b[1])
                if dist < best_dist and dist <= search_radius_m:
                    best_dist = dist
                    best_name = way.get("name", "Đường cao tốc/Cấm xe máy")
                    is_banned = True

        if is_banned:
            return True, best_name
        return False, ""

    def get_default_speed_limit(self, road_type="residential"):
        """Giới hạn tốc độ mặc định theo Luật Giao thông Đường bộ VN cho XE MÁY."""
        defaults = {
            "motorway": 0,         # Đường cao tốc cấm xe máy hoàn toàn
            "motorway_link": 0,
            "trunk": 70,           # Quốc lộ ngoài đô thị (xe máy tối đa 70-80 km/h)
            "trunk_link": 60,
            "primary": 60,         # Tỉnh lộ ngoài đô thị
            "secondary": 50,       # Huyện lộ
            "tertiary": 50,
            "residential": 50,     # Đường đô thị (xe máy mặc định 50 km/h)
            "living_street": 20,
            "service": 20,
            "unclassified": 50,
        }
        return defaults.get(road_type, 50)

    # ─────────────────────────────────────────────
    # GEOMETRY UTILS
    # ─────────────────────────────────────────────
    def _dist_m(self, lat1, lon1, lat2, lon2):
        R = 6371000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return 2 * R * math.asin(math.sqrt(max(0, a)))

    def _point_to_segment_dist(self, px, py, ax, ay, bx, by):
        """Khoảng cách từ điểm P đến đoạn thẳng AB (tính bằng độ, không cần chính xác cao)."""
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return self._dist_m(px, py, ax, ay)
        t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx*dx + dy*dy)))
        closest_x = ax + t * dx
        closest_y = ay + t * dy
        return self._dist_m(px, py, closest_x, closest_y)

    # ─────────────────────────────────────────────
    # STATS
    # ─────────────────────────────────────────────
    def get_stats(self):
        return {
            "total_cameras": len(self.cameras),
            "speed_cameras": len([c for c in self.cameras if c["type"] == "speed"]),
            "red_light_cameras": len([c for c in self.cameras if c["type"] == "red_light"]),
            "road_segments": len(self.speed_ways),
            "banned_road_segments": len(self.banned_ways),
        }
