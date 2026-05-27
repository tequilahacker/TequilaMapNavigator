#!/usr/bin/env python3
"""
start_local_server.py - Khoi dong local HTTP server cho ESP32 navigator
ESP32 se ket noi den 172.20.10.3:8080 (HTTP, khong can SSL, nhanh 5-10x)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'iphone'))

from web_server import NavigatorWebServer
from navigation_engine import NavigationEngine
import time, threading

print("=" * 50)
print("TEQUILA MAP LOCAL SERVER")
print("=" * 50)
print("ESP32 ket noi: http://172.20.10.3:8080")
print("Web UI iPhone: http://172.20.10.3:8080")
print()

# Khoi tao NavigationEngine (dung OSM Nominatim + OSRM mien phi)
# Truyen api_key=None se tu dong dung OSM/OSRM thay vi Google Maps
nav_engine = NavigationEngine(api_key=None)
server = NavigatorWebServer(port=8080, nav_engine=nav_engine, esp32_ip="172.20.10.2")
server.start()

# Bat dau GPS tracker gia lap (dung GPS tu iPhone Shortcut webhook)
print("[GPS] Cho GPS tu iPhone qua /api/update-gps...")
print("Nhan Ctrl+C de dung")
print()

try:
    while True:
        time.sleep(10)
        status = server.status
        gps = (status.get('gps_lat'), status.get('gps_lon'))
        nav = "NAVIGATE" if status.get('is_navigating') else "IDLE"
        print(f"[{nav}] GPS: {gps} | Speed: {status.get('speed_kmh')} km/h")
except KeyboardInterrupt:
    print("\nServer dung.")
    server.stop()
