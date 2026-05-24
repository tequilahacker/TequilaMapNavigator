# 📱 Hướng Dẫn Cài Apple Shortcuts — VMN Motorcycle Navigator

> **Không cần Pythonista, không cần cài app nào thêm.**  
> Chỉ dùng **Apple Shortcuts** có sẵn trên iPhone (iOS 16+).

---

## ⚙️ Bước 0: Chuẩn bị

### 0.1 Bật Personal Hotspot trên iPhone
1. **Settings → Personal Hotspot → Allow Others to Join: BẬT**
2. Ghi nhớ tên hotspot và mật khẩu (vd: `"iPhone của Tequila"` / `"matkhau123"`)
3. Điền tên và mật khẩu đó vào `esp32/config.py`:
   ```python
   WIFI_SSID     = "iPhone của Tequila"
   WIFI_PASSWORD = "matkhau123"
   ```

### 0.2 Lấy IP của ESP32
1. Flash code lên ESP32, mở Serial Monitor
2. Bật hotspot iPhone, bật điện ESP32
3. Chờ dòng log: `[WiFi] ✅ Kết nối thành công! IP: 172.20.10.2`
4. **Ghi lại IP đó** — thường là `172.20.10.2`
5. Dùng IP này trong tất cả Shortcuts bên dưới

---

## 🛣️ Shortcut 1: "Dẫn Đường" (Shortcut chính)

**Kích hoạt**: Nói "Hey Siri, Dẫn Đường"

Mở app **Shortcuts** → nhấn **+** (góc phải trên) → đặt tên `Dẫn Đường`

Thêm các action theo thứ tự sau:

---

### Action 1 — Phát giọng hỏi đích
```
[Scripting] → Speak Text
Text: "Bạn muốn đi đâu?"
Language: Vietnamese (vi-VN)
Wait Until Done: ON
```

### Action 2 — Nhận giọng nói đích đến
```
[Scripting] → Dictate Text
Language: Vietnamese (vi-VN)
Stop Listening: After Pause
```
> 💡 Đặt tên output: nhấn vào kết quả → **"Add to Variable"** → đặt tên `diaDiem`

### Action 3 — Lấy GPS hiện tại
```
[Location] → Get Current Location
```
> 💡 Đặt tên output: `viTriHienTai`

### Action 4 — Geocode địa chỉ → Toạ độ (dùng Nominatim miễn phí)
```
[Web] → Get Contents of URL
URL: https://nominatim.openstreetmap.org/search?q=[diaDiem]&format=json&limit=1&countrycodes=vn
Method: GET
Headers:
  User-Agent: VMNMotorcycleNavigator/1.0
```
> 💡 Đặt tên output: `geocodeResult`

### Action 5 — Lấy kết quả đầu tiên
```
[Scripting] → Get Item from List
List: [geocodeResult]
Item: First Item
```
> 💡 Đặt tên: `diemDau`

### Action 6 — Lấy lat/lon đích
```
[Scripting] → Get Dictionary Value
Dictionary: [diemDau]
Key: lat
```
> 💡 Đặt tên: `destLat`

```
[Scripting] → Get Dictionary Value
Dictionary: [diemDau]
Key: lon
```
> 💡 Đặt tên: `destLon`

### Action 7 — Gọi OSRM lấy route (hoàn toàn miễn phí)
```
[Web] → Get Contents of URL
URL: http://router.project-osrm.org/route/v1/driving/[viTriHienTai.longitude],[viTriHienTai.latitude];[destLon],[destLat]?geometries=geojson&overview=full&steps=false
Method: GET
```
> 💡 Đặt tên: `osrmResult`

### Action 8 — Lấy danh sách toạ độ route
```
[Scripting] → Get Dictionary Value
Dictionary: [osrmResult]
Key: routes
```
```
[Scripting] → Get Item from List → First Item
```
```
[Scripting] → Get Dictionary Value → Key: geometry
```
```
[Scripting] → Get Dictionary Value → Key: coordinates
```
> 💡 Đặt tên: `routeCoords`  
> ⚠️ OSRM trả về `[lon, lat]` (ngược). Shortcuts xử lý ở bước 10.

### Action 9 — Lấy camera phạt nguội gần đường (Overpass API miễn phí)
```
[Web] → Get Contents of URL
URL: https://overpass-api.de/api/interpreter?data=[out:json];node["highway"="speed_camera"](around:2000,[viTriHienTai.latitude],[viTriHienTai.longitude]);out;
Method: GET
```
> 💡 Đặt tên: `cameraData`

```
[Scripting] → Get Dictionary Value
Dictionary: [cameraData]
Key: elements
```
> 💡 Đặt tên: `danhSachCamera`

### Action 10 — Build JSON gửi ESP32
```
[Scripting] → Text
```
Nhập nội dung (copy nguyên):
```
{"lat":[viTriHienTai.latitude],"lon":[viTriHienTai.longitude],"heading":0,"speed":0,"route":[],"cameras":[]}
```
> 💡 Đặt tên: `jsonPayload`

> ⚠️ **Lưu ý**: Route polyline từ OSRM có nhiều điểm, Shortcuts khó xử lý thành JSON array. Cách đơn giản nhất: **chỉ gửi GPS gốc + đích, để ESP32 hiển thị 2 điểm**. Route đầy đủ là việc nâng cao.

### Action 11 — POST lên ESP32
```
[Web] → Get Contents of URL
URL: http://172.20.10.2/update        ← Thay bằng IP ESP32 của bạn
Method: POST
Headers:
  Content-Type: application/json
Request Body: [jsonPayload]
```

### Action 12 — Mở Waze/Maps dẫn đường chi tiết
```
[Maps] → Show Directions
Destination: [diaDiem]
Mode: Driving
```
Hoặc mở Waze:
```
[Scripting] → Open URL
URL: waze://?q=[diaDiem]&navigate=yes
```

### Action 13 — Thông báo hoàn thành
```
[Scripting] → Speak Text
Text: "Đã gửi route lên màn hình xe! Bắt đầu dẫn đường."
```

---

## 🔄 Shortcut 2: "Cập Nhật Vị Trí" (Automation — tự chạy)

**Mục đích**: Cập nhật GPS lên ESP32 mỗi phút tự động.

Tạo shortcut tên `Cập Nhật Vị Trí`, thêm actions:

### Action 1
```
[Location] → Get Current Location
```
> Đặt tên: `gpsMoi`

### Action 2
```
[Location] → Get Speed  ← (iOS 17+) hoặc dùng 0 nếu không có
```

### Action 3 — Build JSON
```
[Scripting] → Text
{"lat":[gpsMoi.latitude],"lon":[gpsMoi.longitude],"heading":0,"speed":0,"route":[],"cameras":[]}
```
> Đặt tên: `updatePayload`

### Action 4 — POST lên ESP32
```
[Web] → Get Contents of URL
URL: http://172.20.10.2/update
Method: POST
Headers:
  Content-Type: application/json
Request Body: [updatePayload]
```

---

### Cài Automation cho Shortcut 2:
1. Tab **Automation** (biểu tượng đồng hồ) → **+** → **Time of Day**
2. Hoặc: **+** → **Location** (khi di chuyển)
3. Cách đơn giản nhất: **+** → **Time of Day** → chọn mỗi 1 giờ  
   *(Shortcuts không thể dưới 1 phút, nhưng GPS cập nhật mỗi 8 giây qua Shortcut 1 khi đang chạy)*

> 💡 **Mẹo**: Để cập nhật liên tục hơn, chạy Shortcut 1 "Dẫn Đường" — nó sẽ POST ngay và Waze/Maps tự cập nhật màn hình iPhone. Automation 1 phút là backup.

---

## 📸 Shortcut 3: "Cảnh Báo Camera" (Automation)

Tạo shortcut `Cảnh Báo Camera`:

### Action 1
```
[Location] → Get Current Location
```

### Action 2 — Tìm camera gần (bán kính 500m)
```
[Web] → Get Contents of URL
URL: https://overpass-api.de/api/interpreter?data=[out:json];node["highway"="speed_camera"](around:500,[Vị trí hiện tại.latitude],[Vị trí hiện tại.longitude]);out;
```
> Đặt tên: `camNearby`

### Action 3
```
[Scripting] → Get Dictionary Value
Dictionary: [camNearby]
Key: elements
```
> Đặt tên: `camList`

### Action 4 — Kiểm tra nếu có camera
```
[Scripting] → If
Input: Count of [camList]
Condition: is greater than
Value: 0
```

### Action 5 — Cảnh báo (bên trong If)
```
[Scripting] → Speak Text
Text: "Cảnh báo! Có camera phạt nguội phía trước."
```

```
[Web] → Get Contents of URL
URL: http://172.20.10.2/alert
Method: POST
Headers:
  Content-Type: application/json
Request Body: {"speed_limit":60,"current_speed":0,"speed_over":false,"camera_dist":300,"camera_type":"speed"}
```

### Action 6
```
[Scripting] → End If
```

---

## 🛑 Shortcut 4: "Dừng Dẫn Đường"

Tạo shortcut `Dừng Dẫn Đường`, kích hoạt bằng "Hey Siri, Dừng Dẫn Đường":

### Action 1
```
[Web] → Get Contents of URL
URL: http://172.20.10.2/stop
Method: POST
Headers:
  Content-Type: application/json
Request Body: {}
```

### Action 2
```
[Scripting] → Speak Text
Text: "Đã dừng dẫn đường. Đi đường vui vẻ!"
```

---

## 🧪 Test Kiểm Tra

### Test ESP32 hoạt động (dùng máy tính hoặc Terminal iPhone):
```bash
# Kiểm tra status
curl http://172.20.10.2/status

# Test gửi GPS
curl -X POST http://172.20.10.2/update \
  -H "Content-Type: application/json" \
  -d '{"lat":10.7769,"lon":106.7009,"heading":90,"speed":30,"route":[],"cameras":[]}'

# Test cảnh báo camera
curl -X POST http://172.20.10.2/alert \
  -H "Content-Type: application/json" \
  -d '{"speed_limit":60,"current_speed":75,"speed_over":true,"camera_dist":250,"camera_type":"speed"}'
```

---

## 🔧 Cấu Hình Nhanh Checklist

- [ ] Điền tên hotspot + mật khẩu vào `esp32/config.py`
- [ ] Flash code ESP32, ghi lại IP từ Serial Monitor
- [ ] Thay `172.20.10.2` trong tất cả 4 Shortcuts bằng IP thực tế của ESP32
- [ ] Bật Personal Hotspot trước khi bật điện ESP32
- [ ] Chạy thử Shortcut "Dẫn Đường" — màn hình TFT sẽ hiện "WiFi OK" và GPS

---

## ❓ Lỗi Thường Gặp

| Lỗi | Nguyên nhân | Giải pháp |
|-----|-------------|-----------|
| Shortcut báo "Connection refused" | ESP32 chưa kết nối WiFi | Bật hotspot iPhone trước, chờ 10 giây |
| IP không đúng | ESP32 nhận IP khác | Xem lại Serial Monitor, đổi IP trong Shortcuts |
| Geocode không tìm được địa chỉ | Nominatim không nhận diện tên VN | Thêm thành phố vào: "Quận 1 Hồ Chí Minh" |
| OSRM không trả về route | Địa điểm quá xa hoặc sai tọa độ | Kiểm tra lat/lon có đúng thứ tự không |
| Hotspot tắt sau 90 giây | iOS auto-tắt khi không có thiết bị | ESP32 kết nối = iPhone giữ hotspot mãi |
