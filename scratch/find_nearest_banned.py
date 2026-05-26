# scratch/find_nearest_banned.py
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../iphone")))

from osm_speed_engine import OSMSpeedEngine

def main():
    engine = OSMSpeedEngine()
    lat, lon = 10.8016, 106.7725
    
    print(f"Total banned ways: {len(engine.banned_ways)}")
    
    best_dist = float('inf')
    best_way = None
    best_node = None
    
    for way in engine.banned_ways:
        nodes = way.get("nodes", [])
        for node in nodes:
            dist = engine._dist_m(lat, lon, node[0], node[1])
            if dist < best_dist:
                best_dist = dist
                best_way = way
                best_node = node
                
    if best_way:
        print(f"Nearest banned node is at ({best_node[0]}, {best_node[1]})")
        print(f"Distance: {best_dist:.1f} meters")
        print(f"Way info: OSM ID: {best_way.get('osm_id')}, Name: '{best_way.get('name')}', Type: '{best_way.get('road_type')}'")
        
        # Test ban checking at that node
        is_banned, name = engine.check_motorcycle_ban(best_node[0], best_node[1])
        print(f"Ban check exactly at nearest node: Banned={is_banned}, Road='{name}'")
    else:
        print("No banned ways found!")

if __name__ == "__main__":
    main()
