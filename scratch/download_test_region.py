# scratch/download_test_region.py
import sys
import os
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../iphone")))

from osm_speed_engine import OSMSpeedEngine

def main():
    # Coords of a segment on HCMC - Long Thanh expressway near An Phu/Dist 2:
    lat = 10.8016
    lon = 106.7725
    
    print(f"Downloading OSM region data around ({lat}, {lon}) with radius 15km...")
    engine = OSMSpeedEngine()
    
    success = engine.update_region(lat, lon, radius_km=15)
    if success:
        print("✅ Successfully downloaded and cached OSM region data!")
        print(f"Stats: {engine.get_stats()}")
        
        # Test direct snapping
        is_banned, name = engine.check_motorcycle_ban(lat, lon, search_radius_m=45)
        print(f"Test ban check at ({lat}, {lon}): Banned={is_banned}, Road='{name}'")
    else:
        print("❌ Failed to download OSM region data.")
        sys.exit(1)

if __name__ == "__main__":
    main()
