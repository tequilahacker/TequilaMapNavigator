# scratch/test_motorcycle_ban.py
import sys
import os

# Add parent and iphone directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../iphone")))

from osm_speed_engine import OSMSpeedEngine

def run_test():
    print("Initializing OSMSpeedEngine...")
    engine = OSMSpeedEngine()
    
    # Mock a banned way (HCMC - Long Thanh Expressway segment)
    # Let's say it's a straight line from (10.7960, 106.7450) to (10.7960, 106.7550)
    mock_banned_way = {
        "nodes": [
            [10.7960, 106.7450],
            [10.7960, 106.7550]
        ],
        "road_type": "motorway",
        "name": "Cao tốc TP.HCM - Long Thành",
        "osm_id": 123456
    }
    engine.banned_ways = [mock_banned_way]
    print(f"Added mock banned way: {mock_banned_way['name']}")
    
    # Test cases: (lat, lon, expected_banned)
    test_cases = [
        # Exactly on the road segment
        (10.7960, 106.7500, True, "On the line"),
        # Very close (within 10 meters)
        (10.79605, 106.7500, True, "Very close"),
        # Within search radius (~33 meters north)
        (10.7963, 106.7500, True, "Within radius"),
        # Outside search radius (~55 meters north)
        (10.7965, 106.7500, False, "Outside radius"),
        # Far away
        (10.8000, 106.7500, False, "Far away")
    ]
    
    print("\n--- Running tests ---")
    all_passed = True
    for lat, lon, expected, desc in test_cases:
        is_banned, name = engine.check_motorcycle_ban(lat, lon, search_radius_m=45)
        # Compute distance to segment for debug info
        dist = engine._point_to_segment_dist(lat, lon, 10.7960, 106.7450, 10.7960, 106.7550)
        
        status = "PASSED" if is_banned == expected else "FAILED"
        if status == "FAILED":
            all_passed = False
            
        print(f"[{status}] {desc}: Coords ({lat}, {lon}) | Dist: {dist:.1f}m | Banned: {is_banned} | Road: '{name}' (Expected: {expected})")
        
    if all_passed:
        print("\n✅ All motorcycle ban unit tests PASSED!")
    else:
        print("\n❌ Some tests FAILED!")
        sys.exit(1)

if __name__ == "__main__":
    run_test()
