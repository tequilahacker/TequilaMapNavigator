# iphone/navigation_engine.py
# Pythonista 3 - Google Maps + OpenStreetMap Navigation Engine
# Hỗ trợ Google Places API, Foursquare Places v3 để tìm POI chi tiết (quán cafe, nhà hàng, ...)

# ─── Foursquare Places API v3 (100% miễn phí, 100k req/tháng) ───
FOURSQUARE_API_KEY = "NSGAT4LTRTSZ51WNKHLUJQTG423QDM2TH5GFKBSYZE3JHHND"
import json
import time
import math
import urllib.parse

try:
    import requests    # Pythonista có requests built-in
except ImportError:
    requests = None

try:
    import location    # iOS GPS
except ImportError:
    location = None

HAS_LIBS = (requests is not None) and (location is not None)


class NavigationEngine:
    """Xử lý định vị và dẫn đường sử dụng OpenStreetMap Nominatim (Geocoding) và OSRM (Routing)."""

    def __init__(self, api_key=None):
        self.api_key = api_key
        self.current_step_index = 0
        self.current_route_steps = []
        self.blinker_announced = False

    # ─────────────────────────────────────────────
    # 1. GEOCODING: OSM Nominatim (Địa chỉ → Toạ độ)
    # ─────────────────────────────────────────────
    def geocode(self, place_name, region="vn"):
        """Chuyển tên địa điểm tiếng Việt thành (lat, lon, tên đầy đủ).
        
        Ưu tiên: Google Places Text Search → Google Geocoding → OSM Nominatim
        Google Places tốt hơn cho POI cụ thể (quán cafe nhỏ, tiệm ăn, cửa hàng...)
        """
        if not requests:
            # Mock data cho testing ngoài điện thoại
            return (10.7769, 106.7009, place_name)

        # ─── 0. GOOGLE PLACES TEXT SEARCH (Tốt nhất cho POI cụ thể) ───
        if self.api_key:
            places_result = self._places_text_search(place_name, region)
            if places_result:
                return places_result

        # ─── 1. GOOGLE GEOCODING API (Cho địa chỉ, tên đường, quận huyện...) ───
        if self.api_key:
            url = "https://maps.googleapis.com/maps/api/geocode/json"
            params = {
                "address": place_name,
                "key": self.api_key,
                "language": "vi",
                "region": region
            }
            try:
                print(f"[Google Geocode] Đang tìm địa điểm: {place_name}...")
                r = requests.get(url, params=params, timeout=10)
                data = r.json()
                if data.get("status") == "OK" and data.get("results"):
                    loc = data["results"][0]
                    lat = loc["geometry"]["location"]["lat"]
                    lon = loc["geometry"]["location"]["lng"]
                    display_name = loc["formatted_address"].split(",")[0]
                    print(f"[Google Geocode] Thành công: {display_name} -> ({lat}, {lon})")
                    return (lat, lon, display_name)
                else:
                    print(f"[Google Geocode] Google API báo lỗi/không tìm thấy: {data.get('status')}")
            except Exception as e:
                print("[Google Geocode] Lỗi kết nối Google Geocoding, thử fallback OSM...", e)

        # ─── 2. OSM NOMINATIM (Free Fallback) ───
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": place_name,
            "format": "json",
            "accept-language": "vi",
            "countrycodes": region,
            "limit": 1
        }
        headers = {
            "User-Agent": "TequilaMotorcycleNavigator/1.0 (tequila@navigator.local)"
        }

        try:
            print(f"[OSM Geocode] Đang tìm địa điểm: {place_name}...")
            r = requests.get(url, params=params, headers=headers, timeout=10)
            data = r.json()
            if data:
                loc = data[0]
                lat = float(loc["lat"])
                lon = float(loc["lon"])
                display_name = loc["display_name"].split(",")[0]
                print(f"[OSM Geocode] Thành công: {display_name} -> ({lat}, {lon})")
                return (lat, lon, display_name)
            else:
                print(f"[OSM Geocode] Không tìm thấy: {place_name}, thử Overpass...")
        except Exception as e:
            print("[OSM Geocode] Lỗi Nominatim:", e)

        # ─── 3. PHOTON (Komoot) — fuzzy search tốt cho POI tiếng Việt ───
        try:
            print(f"[Photon] Tìm POI fuzzy: '{place_name}'...")
            r3 = requests.get(
                "https://photon.komoot.io/api/",
                params={"q": place_name, "countrycode": "vn", "limit": 3, "lang": "vi"},
                timeout=10,
                headers={"User-Agent": "TequilaMap/2.0"}
            )
            features = r3.json().get("features", [])
            if features:
                f = features[0]
                coords = f["geometry"]["coordinates"]  # [lon, lat]
                lat, lon = coords[1], coords[0]
                props = f.get("properties", {})
                display_name = props.get("name") or props.get("street") or place_name
                print(f"[Photon] Thành công: {display_name} -> ({lat}, {lon})")
                return (lat, lon, display_name)
            else:
                print(f"[Photon] Không tìm thấy: {place_name}, thử Foursquare...")
        except Exception as e3:
            print("[Photon] Lỗi:", e3)

        # ─── 4. FOURSQUARE PLACES v3 (Tìm quán nhỏ, POI ở VN rất tốt) ───
        try:
            fsq_result = self._foursquare_search(place_name, near="Ho Chi Minh City, Vietnam")
            if fsq_result:
                print(f"[Foursquare] ✅ Tìm thấy: {fsq_result[2]} -> ({fsq_result[0]}, {fsq_result[1]})")
                return fsq_result
            else:
                print(f"[Foursquare] Không tìm thấy: {place_name}, thử Overpass...")
        except Exception as e4:
            print("[Foursquare] Lỗi:", e4)

        # ─── 5. OVERPASS API (Fallback cuối) ───
        try:
            import re as _re
            kw = _re.sub(r'(lê văn|nguyễn|trần|đường|quận|phường|huyện|tp\.?|thành phố|hồ chí minh|hà nội).*', '', place_name, flags=_re.IGNORECASE).strip()
            kw = _re.sub(r'(cafe|quán|nhà hàng|tiệm)\s*', '', kw, flags=_re.IGNORECASE).strip()
            if len(kw) < 3:
                kw = place_name
            print(f"[Overpass] Tìm POI: '{kw}'...")
            overpass_q = f'[out:json][timeout:25];area["name"="Việt Nam"]["admin_level"="2"]->.vn;(node(area.vn)["name"~"{kw}",i];way(area.vn)["name"~"{kw}",i];);out center 5;'
            r2 = requests.post(
                "https://overpass-api.de/api/interpreter",
                data=overpass_q, timeout=25,
                headers={"User-Agent": "TequilaMap/2.0"}
            )
            elems = r2.json().get("elements", [])
            if elems:
                best = elems[0]
                lat = float(best.get("lat") or best.get("center", {}).get("lat", 0))
                lon = float(best.get("lon") or best.get("center", {}).get("lon", 0))
                display_name = best.get("tags", {}).get("name", place_name)
                print(f"[Overpass] Thành công: {display_name} -> ({lat}, {lon})")
                return (lat, lon, display_name)
            else:
                print(f"[Overpass] Không tìm thấy: {kw}")
        except Exception as e2:
            print("[Overpass] Lỗi:", e2)

        # ─── Cuối cùng: fallback về trung tâm HCMC ───
        print(f"[Geocode] Tất cả fallback thất bại — dùng trung tâm HCMC cho: {place_name}")
        return (10.7769, 106.7009, place_name)

    def _foursquare_search(self, query, near="Ho Chi Minh City, Vietnam", limit=3):
        """Foursquare Places API v3 — Tìm POI theo tên (quán nhỏ, tiệm ăn, cửa hàng...).
        
        Miễn phí 100k req/tháng. Tốt hơn Overpass cho POI tên tiếng Việt phổ thông.
        Trả về (lat, lon, tên) hoặc None nếu không tìm thấy.
        """
        if not requests or not FOURSQUARE_API_KEY:
            return None
        try:
            r = requests.get(
                "https://api.foursquare.com/v3/places/search",
                params={"query": query, "near": near, "limit": limit, "fields": "name,geocodes,location"},
                headers={"Authorization": FOURSQUARE_API_KEY, "Accept": "application/json"},
                timeout=8
            )
            if r.status_code != 200:
                print(f"[Foursquare] HTTP {r.status_code}")
                return None
            results = r.json().get("results", [])
            if not results:
                return None
            best = results[0]
            geo = best.get("geocodes", {}).get("main", {})
            lat = geo.get("latitude")
            lon = geo.get("longitude")
            name = best.get("name", query)
            loc = best.get("location", {})
            address = loc.get("formatted_address", "")
            display = f"{name}, {address}" if address else name
            if lat and lon:
                return (float(lat), float(lon), display)
            return None
        except Exception as e:
            print(f"[Foursquare] Lỗi _foursquare_search: {e}")
            return None

    def _places_text_search(self, query, region="vn"):
        """Google Places Text Search API - Tìm POI chi tiết (quán cafe, nhà hàng, cửa hàng...).
        
        Tốt hơn Google Geocoding cho các địa điểm cụ thể như tên quán, tên tiệm.
        Trả về (lat, lon, tên_đầy_đủ) hoặc None nếu không tìm thấy.
        """
        if not self.api_key or not requests:
            return None
        
        # Thêm "Việt Nam" vào query để tăng độ chính xác tìm kiếm trong nước
        search_query = query
        if "việt nam" not in query.lower() and "vietnam" not in query.lower():
            search_query = f"{query} Việt Nam"
        
        url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
        params = {
            "query": search_query,
            "key": self.api_key,
            "language": "vi",
            "region": region,
        }
        
        try:
            print(f"[Google Places] Tìm kiếm POI: '{query}'...")
            r = requests.get(url, params=params, timeout=10)
            data = r.json()
            
            if data.get("status") == "OK" and data.get("results"):
                place = data["results"][0]
                lat = place["geometry"]["location"]["lat"]
                lng = place["geometry"]["location"]["lng"]
                name = place.get("name", query)
                address = place.get("formatted_address", "")
                # Hiển thị tên đầy đủ: Tên POI + địa chỉ ngắn
                display = name
                if address:
                    addr_parts = address.split(",")
                    if len(addr_parts) >= 2:
                        short_addr = ",".join(addr_parts[:2]).strip()
                        display = f"{name}, {short_addr}"
                print(f"[Google Places] ✅ Tìm thấy: '{display}' -> ({lat}, {lng})")
                return (lat, lng, display)
            elif data.get("status") == "ZERO_RESULTS":
                print(f"[Google Places] Không tìm thấy POI: '{query}', thử Geocoding...")
                return None
            else:
                print(f"[Google Places] Lỗi API: {data.get('status')}")
                return None
        except Exception as e:
            print(f"[Google Places] Lỗi kết nối: {e}")
            return None

    def search_nearby_places(self, lat, lon, keyword, radius_m=2000, max_results=5):
        """Tìm kiếm địa điểm gần vị trí hiện tại theo từ khóa.
        
        Ưu tiên: Foursquare Places v3 (miễn phí, tốt cho VN) → Google Places Nearby (fallback)
        
        Args:
            lat, lon: Toạ độ vị trí hiện tại
            keyword: Từ khóa tìm kiếm (ví dụ: "cafe", "xăng", "atm", "bệnh viện")
            radius_m: Bán kính tìm kiếm (mét), mặc định 2km
            max_results: Số kết quả tối đa trả về
            
        Returns:
            list of dict: [{name, lat, lon, address, rating, distance_m}, ...]
        """
        if not requests:
            return []

        # ─── 1. FOURSQUARE PLACES v3 Nearby (Miễn phí, rất tốt cho VN) ───
        if FOURSQUARE_API_KEY:
            try:
                print(f"[Foursquare Nearby] Tìm '{keyword}' trong bán kính {radius_m}m...")
                r = requests.get(
                    "https://api.foursquare.com/v3/places/search",
                    params={
                        "query": keyword,
                        "ll": f"{lat},{lon}",
                        "radius": min(radius_m, 100000),
                        "limit": max_results,
                        "fields": "name,geocodes,location,rating,hours",
                    },
                    headers={"Authorization": FOURSQUARE_API_KEY, "Accept": "application/json"},
                    timeout=8
                )
                if r.status_code == 200:
                    fsq_results = r.json().get("results", [])
                    places = []
                    for place in fsq_results:
                        geo = place.get("geocodes", {}).get("main", {})
                        p_lat = geo.get("latitude")
                        p_lon = geo.get("longitude")
                        if not p_lat or not p_lon:
                            continue
                        p_lat, p_lon = float(p_lat), float(p_lon)
                        name = place.get("name", "Không tên")
                        loc = place.get("location", {})
                        address = loc.get("formatted_address", loc.get("address", ""))
                        rating = place.get("rating", 0)
                        dist = self._distance_m(lat, lon, p_lat, p_lon)
                        open_now = None
                        hours = place.get("hours", {})
                        if hours:
                            open_now = hours.get("open_now")
                        places.append({
                            "name": name,
                            "lat": p_lat,
                            "lon": p_lon,
                            "address": address,
                            "rating": rating,
                            "distance_m": int(dist),
                            "open_now": open_now,
                            "source": "foursquare",
                        })
                    places.sort(key=lambda x: x["distance_m"])
                    if places:
                        print(f"[Foursquare Nearby] ✅ Tìm được {len(places)} địa điểm '{keyword}'.")
                        return places
                    else:
                        print(f"[Foursquare Nearby] Không tìm thấy '{keyword}', thử Google...")
                else:
                    print(f"[Foursquare Nearby] HTTP {r.status_code}, thử Google...")
            except Exception as e:
                print(f"[Foursquare Nearby] Lỗi: {e}")

        # ─── 2. GOOGLE PLACES NEARBY (Fallback nếu có API key hợp lệ) ───
        if not self.api_key:
            return []
        
        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        params = {
            "location": f"{lat},{lon}",
            "radius": min(radius_m, 50000),  # Max 50km
            "keyword": keyword,
            "key": self.api_key,
            "language": "vi",
        }
        
        try:
            print(f"[Google Places Nearby] Tìm '{keyword}' trong bán kính {radius_m}m...")
            r = requests.get(url, params=params, timeout=10)
            data = r.json()
            
            if data.get("status") not in ("OK", "ZERO_RESULTS"):
                print(f"[Google Places Nearby] Lỗi: {data.get('status')}")
                return []
            
            results = []
            for place in data.get("results", [])[:max_results]:
                p_lat = place["geometry"]["location"]["lat"]
                p_lng = place["geometry"]["location"]["lng"]
                name = place.get("name", "Không tên")
                address = place.get("vicinity", "")
                rating = place.get("rating", 0)
                dist = self._distance_m(lat, lon, p_lat, p_lng)
                results.append({
                    "name": name,
                    "lat": p_lat,
                    "lon": p_lng,
                    "address": address,
                    "rating": rating,
                    "distance_m": int(dist),
                    "open_now": place.get("opening_hours", {}).get("open_now", None),
                    "source": "google",
                })
            results.sort(key=lambda x: x["distance_m"])
            print(f"[Google Places Nearby] Tìm được {len(results)} địa điểm '{keyword}'.")
            return results
        except Exception as e:
            print(f"[Google Places Nearby] Lỗi: {e}")
            return []


    # ─────────────────────────────────────────────
    # 2. WAYPOINT OPTIMIZER: Sắp xếp thứ tự tối ưu
    # ─────────────────────────────────────────────
    def optimize_waypoints_locally(self, start, waypoints, end):
        """Sắp xếp thứ tự các điểm dừng bằng thuật toán láng giềng gần nhất (Greedy)."""
        if len(waypoints) <= 1:
            return waypoints

        def dist(a, b):
            return math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2)

        remaining = list(waypoints)
        ordered = []
        current = start

        while remaining:
            nearest = min(remaining, key=lambda wp: dist(current, wp))
            ordered.append(nearest)
            remaining.remove(nearest)
            current = nearest

        return ordered

    # ─────────────────────────────────────────────
    # 3. ROUTING: OSRM API (Tìm đường đi miễn phí)
    # ─────────────────────────────────────────────
    def get_route(self, origin_lat, origin_lon, destination, waypoints=None, optimize=True):
        """
        Lấy tuyến đường từ Google Maps Directions API (có tối ưu AI) hoặc OSRM (Miễn phí).
        
        origin: (lat, lon) - Vị trí hiện tại
        destination: (lat, lon, name) hoặc chuỗi địa chỉ
        waypoints: [(lat, lon, name), ...] - Danh sách điểm dừng
        """
        if not requests:
            return self._mock_route(origin_lat, origin_lon)

        # ─── 1. GOOGLE MAPS DIRECTIONS API (Nếu có API Key) ───
        if self.api_key:
            url = "https://maps.googleapis.com/maps/api/directions/json"
            
            # Giải mã destination nếu truyền dạng tên địa điểm
            if isinstance(destination, str):
                coords_dest = self.geocode(destination)
                if not coords_dest:
                    return {"status": "NOT_FOUND", "error": f"Không tìm thấy điểm đến '{destination}'"}
                dest_lat, dest_lon = coords_dest[0], coords_dest[1]
                dest_name = coords_dest[2]
            else:
                dest_lat, dest_lon = destination[0], destination[1]
                dest_name = destination[2] if len(destination) > 2 else "Điểm đến"

            params = {
                "origin": f"{origin_lat},{origin_lon}",
                "destination": f"{dest_lat},{dest_lon}",
                "mode": "two-wheeler",  # Google Maps hỗ trợ tìm đường xe máy tại VN
                "avoid": "tolls|highways",  # Tránh đường cao tốc cấm xe máy & trạm thu phí ô tô
                "key": self.api_key,
                "language": "vi"
            }

            if waypoints:
                # Định dạng toạ độ cho Google: lat,lon nối nhau bằng thanh dọc |
                wp_strs = []
                for wp in waypoints:
                    wp_strs.append(f"{wp[0]},{wp[1]}")
                
                if optimize and len(waypoints) > 1:
                    params["waypoints"] = "optimize:true|" + "|".join(wp_strs)
                else:
                    params["waypoints"] = "|".join(wp_strs)

            try:
                print("[Google Router] Đang tìm tuyến đường với AI tối ưu...")
                r = requests.get(url, params=params, timeout=12)
                data = r.json()

                # Nếu không tìm thấy đường xe máy (VD ở đường cao tốc cấm xe máy), chuyển sang driving
                if data.get("status") == "ZERO_RESULTS" and params["mode"] == "two-wheeler":
                    print("[Google Router] Không hỗ trợ hai bánh ở vùng này, chuyển sang driving...")
                    params["mode"] = "driving"
                    r = requests.get(url, params=params, timeout=12)
                    data = r.json()

                if data.get("status") == "OK" and data.get("routes"):
                    route = data["routes"][0]
                    
                    # Giải mã polyline tổng quát
                    encoded_geom = route["overview_polyline"]["points"]
                    polyline = self._decode_polyline(encoded_geom)
                    
                    # Thứ tự waypoints tối ưu từ AI của Google
                    optimized_order = route.get("waypoint_order", [])
                    print(f"[Google Router] AI đã tối ưu hóa thứ tự các điểm dừng: {optimized_order}")

                    # Trích xuất các chặng đi (steps)
                    steps = []
                    import re
                    for leg in route.get("legs", []):
                        for step in leg.get("steps", []):
                            raw_instruction = step.get("html_instructions", "")
                            # Loại bỏ các thẻ HTML để lấy chỉ dẫn chữ thuần tiếng Việt
                            clean_instruction = re.sub('<[^<]+?>', '', raw_instruction)
                            
                            start_loc = step.get("start_location", {})
                            s_lat = start_loc.get("lat", 0)
                            s_lon = start_loc.get("lng", 0)
                            
                            maneuver = "straight"
                            clean_lower = clean_instruction.lower()
                            if "trái" in clean_lower:
                                maneuver = "turn-left"
                            elif "phải" in clean_lower:
                                maneuver = "turn-right"
                            elif "quay đầu" in clean_lower:
                                maneuver = "uturn"

                            steps.append({
                                "instruction": clean_instruction,
                                "distance_m": int(step.get("distance", {}).get("value", 0)),
                                "duration_s": int(step.get("duration", {}).get("value", 0)),
                                "lat": s_lat,
                                "lon": s_lon,
                                "maneuver": maneuver,
                            })

                    self.current_route_steps = steps
                    self.current_step_index = 0

                    total_dist_km = round(sum(leg.get("distance", {}).get("value", 0) for leg in route.get("legs", [])) / 1000.0, 1)
                    total_dur_min = int(sum(leg.get("duration", {}).get("value", 0) for leg in route.get("legs", [])) // 60)
                    total_dur_sec = int(sum(leg.get("duration", {}).get("value", 0) for leg in route.get("legs", [])))

                    print(f"[Google Router] Thành công: {total_dist_km} km | {total_dur_min} phút (Tối ưu AI)")

                    return {
                        "status": "OK",
                        "polyline": polyline[:50],  # Gửi 50 điểm đầu cho màn hình ESP32 HUD
                        "full_polyline": polyline,   # Toàn bộ polyline cho Web UI hiển thị
                        "steps": steps,
                        "total_distance_km": total_dist_km,
                        "total_duration_min": total_dur_min,
                        "eta_seconds": total_dur_sec,
                        "waypoint_order": optimized_order,
                    }
                else:
                    print(f"[Google Router] Lỗi từ API Google Maps: {data.get('status')}. Thử OSRM...")
            except Exception as e:
                print("[Google Router] Lỗi gọi Google API, đang chuyển sang OSRM fallback...", e)

        # ─── 2. OSRM API (Free Fallback) ───
        # Giải mã destination nếu truyền dạng tên địa điểm
        if isinstance(destination, str):
            coords_dest = self.geocode(destination)
            if not coords_dest:
                return {"status": "NOT_FOUND", "error": f"Không tìm thấy điểm đến '{destination}'"}
            dest_lat, dest_lon = coords_dest[0], coords_dest[1]
        else:
            dest_lat, dest_lon = destination[0], destination[1]

        # Định dạng tọa độ cho OSRM (lon,lat) nối nhau bằng dấu chấm phẩy ;
        coords_list = [f"{origin_lon},{origin_lat}"]
        if waypoints:
            for wp in waypoints:
                coords_list.append(f"{wp[1]},{wp[0]}")
        coords_list.append(f"{dest_lon},{dest_lat}")
        
        coords_str = ";".join(coords_list)
        
        # Gọi OSRM public service (chế độ driving)
        url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}"
        params = {
            "overview": "full",
            "geometries": "polyline",
            "steps": "true",
            "continue_straight": "true"
        }

        try:
            print("[OSRM Router] Đang tìm tuyến đường (Free)...")
            r = requests.get(url, params=params, timeout=12)
            data = r.json()
            
            if data.get("code") != "Ok":
                print(f"[OSRM Router] Lỗi từ server OSRM: {data.get('code')}")
                return {"status": "ZERO_RESULTS", "error": "Không thể tìm thấy tuyến đường phù hợp"}

            route = data["routes"][0]
            
            # Decode polyline của tuyến đường
            encoded_geom = route["geometry"]
            polyline = self._decode_polyline(encoded_geom)
            
            # Parse các chặng rẽ (steps)
            steps = []
            for leg in route.get("legs", []):
                for step in leg.get("steps", []):
                    m_info = step.get("maneuver", {})
                    m_type = m_info.get("type", "turn")
                    modifier = m_info.get("modifier", "straight")
                    street_name = step.get("name", "")
                    
                    # Dịch chỉ dẫn OSRM sang tiếng Việt
                    instruction = self._osrm_maneuver_to_vietnamese(m_type, modifier, street_name)
                    
                    # Tọa độ điểm rẽ của chặng này
                    loc = m_info.get("location", [0, 0])
                    s_lon, s_lat = loc[0], loc[1]
                    
                    steps.append({
                        "instruction": instruction,
                        "distance_m": int(step.get("distance", 0)),
                        "duration_s": int(step.get("duration", 0)),
                        "lat": s_lat,
                        "lon": s_lon,
                        "maneuver": f"{m_type}-{modifier}" if modifier else m_type,
                    })

            self.current_route_steps = steps
            self.current_step_index = 0
            
            total_dist_km = round(route.get("distance", 0) / 1000.0, 1)
            total_dur_min = int(route.get("duration", 0) // 60)
            
            print(f"[OSRM Router] Tuyến đường thành công: {total_dist_km} km | {total_dur_min} phút")
            
            return {
                "status": "OK",
                "polyline": polyline[:50],  # Gửi 50 điểm đầu tiên
                "full_polyline": polyline,
                "steps": steps,
                "total_distance_km": total_dist_km,
                "total_duration_min": total_dur_min,
                "eta_seconds": int(route.get("duration", 0)),
                "waypoint_order": list(range(len(waypoints))) if waypoints else [],
            }

        except Exception as e:
            print("[OSRM Router] Lỗi kết nối hoặc xử lý dữ liệu:", e)
            return {"status": "ERROR", "error": str(e)}

    # ─────────────────────────────────────────────
    # 4. CHUYỂN ĐỔI CHỈ DẪN OSRM SANG TIẾNG VIỆT
    # ─────────────────────────────────────────────
    def _osrm_maneuver_to_vietnamese(self, m_type, modifier, street_name):
        """Chuyển đổi các hành động rẽ của OSRM thành chỉ dẫn tiếng Việt tự nhiên."""
        street_desc = f" vào đường {street_name}" if street_name and street_name != "" else ""
        
        if m_type == "depart":
            return "Bắt đầu xuất phát"
        elif m_type == "arrive":
            return "Đã đến địa điểm"
        elif m_type == "merge":
            return f"Nhập làn{street_desc}"
        elif m_type == "on ramp":
            return f"Đi vào đường nối{street_desc}"
        elif m_type == "off ramp":
            return f"Đi ra khỏi đường nối{street_desc}"
        elif m_type == "fork":
            direction = "bên trái" if "left" in modifier else "bên phải"
            return f"Rẽ ở ngã ba rẽ {direction}{street_desc}"
        elif m_type == "roundabout":
            return "Đi vào vòng xuyến"
        elif m_type == "rotary":
            return "Đi vào vòng xoay lớn"
        elif m_type == "exit roundabout":
            return "Đi ra khỏi vòng xuyến"
        elif m_type == "exit rotary":
            return "Đi ra khỏi vòng xoay"
        elif m_type == "turn":
            direction = {
                "left": "Rẽ trái",
                "right": "Rẽ phải",
                "sharp left": "Rẽ ngoặt sang trái",
                "sharp right": "Rẽ ngoặt sang phải",
                "slight left": "Chếch sang trái",
                "slight right": "Chếch sang phải",
            }.get(modifier, "Rẽ")
            return f"{direction}{street_desc}"
        elif m_type == "new name":
            return f"Tiếp tục đi thẳng{street_desc}"
        elif "continue" in m_type:
            return f"Tiếp tục đi thẳng{street_desc}"
        
        # Fallback
        if modifier and modifier != "straight":
            direction = {
                "left": "rẽ trái",
                "right": "rẽ phải",
                "straight": "đi thẳng",
            }.get(modifier, modifier)
            return f"Đi {direction}{street_desc}"
        return f"Đi thẳng{street_desc}"

    # ─────────────────────────────────────────────
    # 5. REALTIME STEP TRACKER
    # ─────────────────────────────────────────────
    def get_current_instruction(self, current_lat, current_lon):
        """Trả về hướng dẫn rẽ phù hợp dựa trên vị trí GPS hiện tại."""
        if not self.current_route_steps or self.current_step_index >= len(self.current_route_steps):
            return {
                "instruction": "Đã đến nơi!", 
                "distance_to_turn_m": 0,
                "maneuver": "arrive", 
                "announce_blinker": False, 
                "speak_text": "Bạn đã đến nơi!"
            }
            
        step = self.current_route_steps[self.current_step_index]
        dist = self._distance_m(current_lat, current_lon, step["lat"], step["lon"])
        
        # Nếu đã đi qua điểm rẽ (trong bán kính 20 mét), chuyển sang bước tiếp theo
        if dist < 20:
            self.current_step_index += 1
            self.blinker_announced = False
            return self.get_current_instruction(current_lat, current_lon)
            
        # Phát cảnh báo bật xi-nhan trước khi rẽ
        announce_blinker = False
        speak_text = ""
        maneuver = step.get("maneuver", "straight")
        
        if dist <= 120 and not self.blinker_announced:
            if "left" in maneuver:
                announce_blinker = True
                speak_text = "Phía trước 100 mét quẹo trái, hãy bật xi nhan trái, hãy bật xi nhan trái, hãy bật xi nhan trái"
                self.blinker_announced = True
            elif "right" in maneuver:
                announce_blinker = True
                speak_text = "Phía trước 100 mét quẹo phải, hãy bật xi nhan phải, hãy bật xi nhan phải, hãy bật xi nhan phải"
                self.blinker_announced = True
            elif "uturn" in maneuver:
                speak_text = f"Phía trước {int(dist)} mét chuẩn bị quay đầu xe"
                self.blinker_announced = True
                
        if dist < 50 and speak_text == "":
            if "left" in maneuver:
                speak_text = "Rẽ trái ngay!"
            elif "right" in maneuver:
                speak_text = "Rẽ phải ngay!"
                
        return {
            "instruction": step["instruction"],
            "distance_to_turn_m": int(dist),
            "maneuver": maneuver,
            "announce_blinker": announce_blinker,
            "speak_text": speak_text,
        }
    
    # ─────────────────────────────────────────────
    # 6. UTILITIES
    # ─────────────────────────────────────────────
    def _distance_m(self, lat1, lon1, lat2, lon2):
        """Khoảng cách Haversine tính bằng mét."""
        R = 6371000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return 2 * R * math.asin(math.sqrt(max(0, a)))
    
    def _decode_polyline(self, encoded):
        """Google Maps / OSRM encoded polyline decoder."""
        points = []
        index, result, shift, lat, lng = 0, 0, 0, 0, 0
        while index < len(encoded):
            b, shift, result = 0, 0, 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            dlat = ~(result >> 1) if (result & 1) else (result >> 1)
            lat += dlat
            shift, result = 0, 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            dlng = ~(result >> 1) if (result & 1) else (result >> 1)
            lng += dlng
            points.append((lat / 1e5, lng / 1e5))
        return points
    
    def _mock_route(self, origin_lat, origin_lon):
        """Mock route data cho testing không có mạng."""
        mock_poly = [
            (origin_lat, origin_lon),
            (origin_lat + 0.001, origin_lon + 0.001),
            (origin_lat + 0.002, origin_lon + 0.003),
            (origin_lat + 0.004, origin_lon + 0.003),
        ]
        return {
            "status": "OK",
            "index": 0,
            "label": "🏃 Tuyến giả lập",
            "color": "#00bfff",
            "summary": "Tuyến giả lập offline",
            "polyline": mock_poly,
            "full_polyline": mock_poly,
            "dest_name": "Điểm giả lập",
            "steps": [
                {"instruction": "Đi thẳng 200m", "distance_m": 200, "duration_s": 30,
                 "lat": origin_lat + 0.002, "lon": origin_lon + 0.002, "maneuver": "straight"},
                {"instruction": "Rẽ phải vào đường Lê Lợi", "distance_m": 150, "duration_s": 25,
                 "lat": origin_lat + 0.004, "lon": origin_lon + 0.003, "maneuver": "turn-right"},
            ],
            "total_distance_km": 1.5,
            "total_duration_min": 8,
            "eta_seconds": 480,
        }

    # ─────────────────────────────────────────────
    # 7. LẤY 3 TUYẾN ĐƯỜNG TỐI ƯU (Alternatives)
    # ─────────────────────────────────────────────
    def get_route_alternatives(self, origin_lat, origin_lon, destination, waypoints=None):
        """
        Lấy tối đa 3 tuyến đường từ Google Maps (alternatives=true).
        Trả về list tối đa 3 dict, mỗi dict gồm:
          index, label, color, total_distance_km, total_duration_min,
          eta_seconds, summary, polyline (40pt → ESP32), full_polyline, steps, dest_name
        """
        if not requests:
            return [self._mock_route(origin_lat, origin_lon)]

        # Giải mã destination
        if isinstance(destination, str):
            coords_dest = self.geocode(destination)
            if not coords_dest:
                return []
            dest_lat, dest_lon, dest_name = coords_dest
        else:
            dest_lat = destination[0]
            dest_lon = destination[1]
            dest_name = destination[2] if len(destination) > 2 else "Điểm đến"

        alternatives = []

        # ── 1. Google Maps (alternatives=true) ──
        if self.api_key:
            import re
            url = "https://maps.googleapis.com/maps/api/directions/json"
            params = {
                "origin": f"{origin_lat},{origin_lon}",
                "destination": f"{dest_lat},{dest_lon}",
                "mode": "two-wheeler",
                "avoid": "tolls|highways",  # Tránh cao tốc cấm xe máy & trạm thu phí ô tô
                "alternatives": "true",
                "key": self.api_key,
                "language": "vi",
            }
            if waypoints:
                params["waypoints"] = "|".join(f"{wp[0]},{wp[1]}" for wp in waypoints)

            try:
                print("[Google Router] Đang lấy 3 tuyến đường alternatives...")
                r = requests.get(url, params=params, timeout=14)
                data = r.json()

                # Fallback sang driving nếu two-wheeler không hỗ trợ
                if data.get("status") == "ZERO_RESULTS" and params["mode"] == "two-wheeler":
                    print("[Google Router] two-wheeler không hỗ trợ, chuyển sang driving...")
                    params["mode"] = "driving"
                    r = requests.get(url, params=params, timeout=14)
                    data = r.json()

                if data.get("status") == "OK" and data.get("routes"):
                    labels = ["🏃 Nhanh nhất", "🛣️ Ngắn nhất", "🚦 Ít đèn đỏ"]
                    colors = ["#00bfff", "#00ff87", "#ff9900"]

                    raw_routes = data["routes"]

                    # Tuyến 0 = nhanh nhất (Google mặc định)
                    # Tìm tuyến ngắn nhất theo khoảng cách
                    def route_dist(route):
                        return sum(leg.get("distance", {}).get("value", 0)
                                   for leg in route.get("legs", []))
                    def route_dur(route):
                        return sum(leg.get("duration", {}).get("value", 0)
                                   for leg in route.get("legs", []))

                    ordered = [raw_routes[0]]  # index 0 = nhanh nhất
                    if len(raw_routes) > 1:
                        rest = raw_routes[1:]
                        shortest = min(rest, key=route_dist)
                        ordered.append(shortest)
                        others = [rt for rt in rest if rt is not shortest]
                        if others:
                            ordered.append(others[0])  # tuyến còn lại = ít tắc nhất

                    for rank, route in enumerate(ordered[:3]):
                        encoded_geom = route["overview_polyline"]["points"]
                        polyline = self._decode_polyline(encoded_geom)

                        total_dist_m = route_dist(route)
                        total_dur_s  = route_dur(route)
                        total_dist_km = round(total_dist_m / 1000.0, 1)
                        total_dur_min = int(total_dur_s // 60)
                        summary = route.get("summary", f"Tuyến {rank+1}")

                        steps = []
                        for leg in route.get("legs", []):
                            for step in leg.get("steps", []):
                                raw_inst = step.get("html_instructions", "")
                                clean_inst = re.sub('<[^<]+?>', '', raw_inst)
                                sl = step.get("start_location", {})
                                maneuver = "straight"
                                cl = clean_inst.lower()
                                if "trái" in cl:        maneuver = "turn-left"
                                elif "phải" in cl:      maneuver = "turn-right"
                                elif "quay đầu" in cl:  maneuver = "uturn"
                                steps.append({
                                    "instruction": clean_inst,
                                    "distance_m": int(step.get("distance", {}).get("value", 0)),
                                    "duration_s":  int(step.get("duration", {}).get("value", 0)),
                                    "lat": sl.get("lat", 0),
                                    "lon": sl.get("lng", 0),
                                    "maneuver": maneuver,
                                })

                        alternatives.append({
                            "index": rank,
                            "label": labels[rank] if rank < len(labels) else f"Tuyến {rank+1}",
                            "color": colors[rank] if rank < len(colors) else "#ffffff",
                            "total_distance_km": total_dist_km,
                            "total_duration_min": total_dur_min,
                            "eta_seconds": int(total_dur_s),
                            "summary": summary,
                            "polyline": polyline[:40],
                            "full_polyline": polyline,
                            "steps": steps,
                            "dest_name": dest_name,
                        })

                    if alternatives:
                        print(f"[Google Router] ✅ Tìm được {len(alternatives)} tuyến đường.")
                        return alternatives
                else:
                    print(f"[Google Router] Lỗi API: {data.get('status')}. Thử OSRM...")
            except Exception as e:
                print("[Google Router] Lỗi lấy alternatives, thử OSRM...", e)

        # ── 2. OSRM Fallback (chỉ 1 tuyến) ──
        print("[OSRM] Fallback: tìm 1 tuyến duy nhất...")
        result = self.get_route(origin_lat, origin_lon,
                                (dest_lat, dest_lon, dest_name), waypoints)
        if result and result.get("status") == "OK":
            return [{
                "index": 0,
                "label": "🏃 Tuyến tốt nhất",
                "color": "#00bfff",
                "total_distance_km": result.get("total_distance_km", 0),
                "total_duration_min": result.get("total_duration_min", 0),
                "eta_seconds": result.get("eta_seconds", 0),
                "summary": "Tuyến đường tối ưu",
                "polyline": result.get("polyline", [])[:40],
                "full_polyline": result.get("full_polyline", result.get("polyline", [])),
                "steps": result.get("steps", []),
                "dest_name": dest_name,
            }]
        return []

    # ─────────────────────────────────────────────────────────────
    # 7. GOOGLE MAPS STATIC API — Tạo ảnh bản đồ JPEG cho ESP32
    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def polyline_encode(coords):
        """Encode danh sách [(lat, lon)] thành Google Encoded Polyline string.
        
        Dùng cho Google Maps Static API path parameter.
        Thuật toán: https://developers.google.com/maps/documentation/utilities/polylinealgorithm
        """
        def _encode_value(value):
            value = int(round(value * 1e5))
            value = value << 1
            if value < 0:
                value = ~value
            chunks = []
            while value >= 0x20:
                chunks.append(chr((0x20 | (value & 0x1f)) + 63))
                value >>= 5
            chunks.append(chr(value + 63))
            return ''.join(chunks)

        result = []
        prev_lat = 0
        prev_lon = 0
        for lat, lon in coords:
            result.append(_encode_value(lat - prev_lat))
            result.append(_encode_value(lon - prev_lon))
            prev_lat = lat
            prev_lon = lon
        return ''.join(result)

    def get_static_map_jpeg(self, lat, lon, route_polyline=None,
                             heading=0, zoom=17,
                             width=240, height=280,
                             remaining_only=True):
        """Tạo ảnh JPEG bản đồ Google Maps cho màn hình ESP32 2.8" (portrait).
        
        Bản đồ luôn center vào vị trí hiện tại của user (lat, lon).
        Route line màu xanh đậm (#0055ff) nếu có.
        Mũi tên xanh đánh dấu vị trí user.
        Cập nhật theo GPS realtime → bản đồ "di chuyển theo user" như Google Maps.
        
        Args:
            lat, lon: GPS hiện tại của user
            route_polyline: list [(lat,lon)] — chỉ phần còn lại chưa đi (remaining)
            heading: hướng di chuyển (độ) — dùng để rotate marker
            zoom: zoom level (17 = rõ tên đường, 16 = rộng hơn)
            width, height: kích thước ảnh (240×280 cho portrait ESP32)
            remaining_only: True = chỉ vẽ route còn lại (biến mất theo đường đã đi)
            
        Returns:
            bytes: JPEG image data (~15-30KB) hoặc None nếu lỗi
        """
        if not self.api_key or not requests:
            return None

        # ── 1. Xây dựng path parameter từ route polyline ──
        path_str = ""
        if route_polyline and len(route_polyline) >= 2:
            try:
                # Tìm điểm trên route gần user nhất để vẽ từ đó trở đi
                if remaining_only:
                    min_dist = float('inf')
                    start_idx = 0
                    for i, (rlat, rlon) in enumerate(route_polyline):
                        d = math.sqrt((rlat - lat)**2 + (rlon - lon)**2)
                        if d < min_dist:
                            min_dist = d
                            start_idx = i
                    remaining = route_polyline[start_idx:]
                else:
                    remaining = route_polyline

                if len(remaining) >= 2:
                    # Giới hạn số điểm để tránh URL quá dài (max ~150 điểm)
                    if len(remaining) > 150:
                        step = len(remaining) // 150
                        remaining = remaining[::step]
                    encoded = self.polyline_encode(remaining)
                    # Route: màu xanh đậm #0055ff, độ dày 5px, trong suốt 80%
                    path_str = f"&path=color:0x0055ffCC|weight:5|enc:{urllib.parse.quote(encoded)}"
            except Exception as e:
                print(f"[StaticMap] Lỗi encode polyline: {e}")

        # ── 2. Marker vị trí user (mũi tên màu đỏ - dễ nhìn) ──
        # Dùng icon mặc định của Static Maps (không cần hosting icon riêng)
        marker_str = f"&markers=color:red|size:small|{lat},{lon}"

        # ── 3. Gọi Google Maps Static API ──
        # maptype=roadmap: bản đồ đường phố tiếng Việt
        url = (
            f"https://maps.googleapis.com/maps/api/staticmap"
            f"?center={lat},{lon}"
            f"&zoom={zoom}"
            f"&size={width}x{height}"
            f"&maptype=roadmap"
            f"&language=vi"
            f"&scale=1"
            f"{marker_str}"
            f"{path_str}"
            f"&key={self.api_key}"
        )

        try:
            r = requests.get(url, timeout=6)
            if r.status_code == 200:
                content_type = r.headers.get('Content-Type', '')
                if 'image' in content_type:
                    return r.content  # PNG bytes
                else:
                    print(f"[StaticMap] Phản hồi không phải ảnh: {content_type}")
                    print(f"[StaticMap] Body: {r.text[:200]}")
                    return None
            else:
                print(f"[StaticMap] HTTP {r.status_code}: {r.text[:200]}")
                return None
        except Exception as e:
            print(f"[StaticMap] Lỗi kết nối Google Static Maps: {e}")
            return None

