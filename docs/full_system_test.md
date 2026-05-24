# docs/full_system_test.md
# Hướng Dẫn Test End-to-End - Tequila Motorcycle Navigator

## Checklist Trước Khi Test

### Hardware cần chuẩn bị
- [ ] ESP32-S3 Development Board
- [ ] 2.8" IPS TFT với Capacitive Touch (ILI9341 hoặc ST7789)
- [ ] INMP441 I2S Microphone
- [ ] MAX98357A I2S Amplifier + Loa nhỏ (0.5W-1W)
- [ ] Buck Converter 12V→5V (LM2596 hoặc MP1584)
- [ ] Cầu chì 2A
- [ ] Dây điện AWG22
- [ ] iPhone 14 Pro với Pythonista 3 đã cài đặt

### Kết nối theo wiring_2.8inch_compact.md

---

## TEST 1: Power Supply

```
1. Không kết nối ESP32 trước
2. Kết nối Buck Converter vào nguồn 12V (hoặc power supply)
3. Đo output bằng đồng hồ volt → phải đọc 5.00V ± 0.1V
4. Nếu không đúng: vặn biến trở Buck Converter
5. Sau khi đúng 5V, kết nối vào ESP32 VIN pin
6. ESP32 LED nguồn phải sáng → PASS ✅
```

## TEST 2: Display & LVGL Boot

```python
# Upload và chạy esp32/boot.py
# Kỳ vọng:
# - Màn hình sáng, hiện màu xanh chào TEQUILA NAVIGATOR
# - Loading bar tăng dần 0% → 100%
# - Text "Sẵn sàng!" xuất hiện
# → PASS ✅
```

## TEST 3: Âm Thanh Chào

```
1. Kết nối MAX98357A đúng wiring
2. Chạy esp32/main.py
3. Nghe âm thanh 2-tone từ loa: "doo-dee"
4. → PASS ✅ nếu nghe rõ 2 âm thanh liên tiếp
```

## TEST 4: BLE Advertising

```
1. Chạy esp32/main.py trên ESP32
2. Mở iPhone Settings → Bluetooth
3. Phải thấy thiết bị "VMN-Compact" trong danh sách
4. Chưa cần kết nối ở bước này
5. → PASS ✅
```

## TEST 5: iPhone Pythonista Setup

```
1. Mở Pythonista 3 trên iPhone 14 Pro
2. Copy toàn bộ folder iphone/ vào Pythonista
3. Điền GOOGLE_MAPS_API_KEY trong ble_helper_ios.py
4. Chạy ble_helper_ios.py
5. Console phải hiện:
   "[iOS] Khởi tạo Navigation Engine..."
   "[iOS] Tìm kiếm ESP32 'VMN-Compact'..."
   "[WebServer] ✅ Đang chạy tại http://localhost:8080"
6. → PASS ✅
```

## TEST 6: BLE Connection

```
1. ESP32 đang chạy main.py (STATE_IDLE, hiện "Đang kết nối iPhone...")
2. Pythonista đang chạy ble_helper_ios.py
3. Sau 5-15 giây, ESP32 màn hình chuyển sang "Sẵn sàng - Nói lệnh"
4. Pythonista console: "[BLE] Đã kết nối VMN-Compact ✅"
5. Loa ESP32 phát: "iPhone đã kết nối. Hệ thống sẵn sàng!"
6. → PASS ✅
```

## TEST 7: Web Companion App

```
1. Trên iPhone, mở Safari
2. Vào địa chỉ: http://localhost:8080
3. Giao diện "🏍️ TEQUILA NAVIGATOR" phải xuất hiện
4. Status bar phải hiện "ESP32 kết nối" (xanh lá)
5. Nhập điểm đến: "Nhà thờ Đức Bà, TPHCM"
6. Nhấn "+ Thêm điểm dừng", nhập "Chợ Bến Thành"
7. Nhấn "🚀 Bắt Đầu Hành Trình"
8. → PASS ✅ nếu ESP32 hiện route trên màn hình
```

## TEST 8: Realtime Navigation

```
1. Sau khi bắt đầu hành trình (TEST 7)
2. Màn hình ESP32 phải hiển thị:
   - Đường route màu xanh
   - Dấu chấm vị trí màu xanh lá
   - Hướng dẫn rẽ ở thanh trên
3. Loa đọc: "Hành trình X km, ước tính Y phút"
4. Sau 8 giây, update vị trí mới
5. → PASS ✅
```

## TEST 9: Camera Alert

```
Mô phỏng camera alert:
1. Trong iphone/navigation_engine.py, thêm đoạn test:
   cam = CameraAlertEngine()
   cam.cameras = [{"lat": GPS_LAT, "lon": GPS_LON+0.002, 
                   "type": "speed", "speed_limit": 60, "distance_m": 200}]
2. Chạy lại navigation
3. Kỳ vọng:
   - ESP32 màn hình: icon camera đỏ nhấp nháy
   - Loa đọc: "Chú ý! Camera tốc độ 200m phía trước. Giới hạn 60 km/h."
4. → PASS ✅
```

## TEST 10: Xi-nhan Reminder

```
1. Khi navigation đang chạy, approach một turn step
2. Cách 300m: Loa đọc "Sau 300 mét, rẽ phải. Bật xi-nhan phải."
3. Cách 50m: Loa đọc "Rẽ phải ngay!"
4. → PASS ✅
```

## TEST 11: Voice Command (Nút GPIO)

```
1. Nhấn nút GPIO 0 trên ESP32
2. Màn hình hiện "🎤 Đang nghe..."
3. Nói: "Đi đến Hồ Con Rùa"
4. Nhả nút
5. Loa đọc: "Đang tìm đường đến Hồ Con Rùa..."
6. Route mới được tính và hiển thị trên màn hình
7. → PASS ✅
```

## TEST 12: Journey Persistence

```
Giả lập tắt điện:
1. Đang trong hành trình
2. Tắt nguồn ESP32 (ngắt power)
3. Bật lại nguồn
4. Kỳ vọng:
   - Boot screen "Tiếp tục hành trình cũ..." xuất hiện
   - Route cũ được reload
   - Navigation tự động resume
5. → PASS ✅
```

---

## Troubleshooting

| Triệu Chứng | Nguyên Nhân | Giải Pháp |
|------------|-------------|-----------|
| Màn hình không sáng | BL pin chưa kết nối | Kiểm tra GPIO27 → BL pin |
| BLE không thấy | Advertising chưa chạy | Kiểm tra ble.start() trong main.py |
| Không có âm thanh | I2S wiring sai | Dùng oscilloscope check BCK, LRC, DIN |
| GPS không accurate | Indoor environment | Test ngoài trời, chờ GPS lock 30s |
| Web app không mở | Pythonista chưa chạy | Chạy ble_helper_ios.py trước |
| Route không cập nhật | API key sai | Kiểm tra GOOGLE_MAPS_API_KEY |
