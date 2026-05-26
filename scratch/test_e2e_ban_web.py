# scratch/test_e2e_ban_web.py
import requests
import json
import time

def test_integration():
    url_update = "http://localhost:8080/api/update-gps"
    url_status = "http://localhost:8080/api/status"
    url_poll = "http://localhost:8080/api/poll-device"
    
    # 1. Coordinate of a banned road (nearest banned node we found)
    banned_lat = 10.7964355
    banned_lon = 106.773289
    
    print(f"Simulating motorcycle GPS position at banned motorway link: ({banned_lat}, {banned_lon})")
    
    # POST to update-gps
    payload = {
        "lat": banned_lat,
        "lon": banned_lon,
        "speed": 35.0,
        "heading": 90
    }
    
    r_post = requests.post(url_update, json=payload)
    print(f"POST /api/update-gps response: {r_post.status_code} - {r_post.text}")
    
    # Wait for status propagation
    time.sleep(0.5)
    
    # GET status
    r_status = requests.get(url_status)
    status_data = r_status.json()
    warning = status_data.get("motorcycle_banned_warning")
    print(f"GET /api/status response:")
    print(f"  - motorcycle_banned_warning: '{warning}'")
    
    # GET poll-device
    r_poll = requests.get(url_poll)
    poll_data = r_poll.json()
    alert_section = poll_data.get("alert")
    print(f"GET /api/poll-device response:")
    print(f"  - alert section: {json.dumps(alert_section, indent=2)}")
    
    # 2. Test safe coordinate
    safe_lat = 10.7769
    safe_lon = 106.7009
    print(f"\nSimulating motorcycle GPS position at safe road: ({safe_lat}, {safe_lon})")
    
    payload_safe = {
        "lat": safe_lat,
        "lon": safe_lon,
        "speed": 30.0,
        "heading": 180
    }
    r_post_safe = requests.post(url_update, json=payload_safe)
    print(f"POST /api/update-gps response: {r_post_safe.status_code}")
    
    time.sleep(0.5)
    
    r_status_safe = requests.get(url_status)
    status_data_safe = r_status_safe.json()
    warning_safe = status_data_safe.get("motorcycle_banned_warning")
    print(f"GET /api/status response:")
    print(f"  - motorcycle_banned_warning: '{warning_safe}'")

if __name__ == "__main__":
    test_integration()
