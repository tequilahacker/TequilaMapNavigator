# 🔑 Hướng Dẫn Setup Apple Find My cho Tequila Map

## Tổng Quan

Thiết bị Tequila Map sẽ xuất hiện trong app **Tìm** (Find My) trên iPhone của bạn.
Server tự động đọc GPS từ Apple mỗi 30 giây — không cần mở Safari hay app nào.

```
[ESP32] phát BLE beacon → [iPhone gần đó] pickup → [Apple Server]
                                                           ↓
[Render Server] ← đọc vị trí tự động ← Apple Find My API
```

---

## BƯỚC 1 — Tạo Key Pair (30 giây)

Mỗi thiết bị cần 1 cặp khóa riêng để Apple nhận diện.

1. Mở Safari trên iPhone → vào: **https://tequilamap.onrender.com/api/gen-findmy-key**
2. Sẽ thấy JSON như sau:
   ```json
   {
     "status": "ok",
     "public_key_hex": "02deadbeef...",
     "public_key_bytes": [222, 173, 190, 239, ...]
   }
   ```
3. Copy mảng `public_key_bytes` (28 số)

---

## BƯỚC 2 — Cập Nhật ESP32 (2 phút)

Mở file `esp32/config.py` trên máy tính:

```python
FINDMY_BLE_ENABLED = True
FINDMY_PUBLIC_KEY  = bytes([
    # Dán 28 số từ bước 1 vào đây, ví dụ:
    222, 173, 190, 239, 202, 254, 1, 2,
    3, 4, 5, 6, 7, 8, 9, 10,
    11, 12, 13, 14, 15, 16, 17, 18,
    19, 20, 21, 22
])
```

Flash lại `config.py` và `ble_haystack.py` lên ESP32 bằng Thonny hoặc mpremote.

---

## BƯỚC 3 — Đăng Nhập Apple ID (2 phút, 1 lần duy nhất)

Gọi API từ iPhone Safari:

```
POST https://tequilamap.onrender.com/api/setup-findmy
Body: {"apple_id": "your@apple.com", "password": "matkhau"}
```

> ⚠️ **Khuyến nghị**: Dùng Apple ID phụ (tạo miễn phí) thay vì ID chính.

Nếu Apple yêu cầu **2FA**:
```
POST https://tequilamap.onrender.com/api/findmy-2fa
Body: {"code": "123456"}
```

---

## BƯỚC 4 — Kiểm Tra

1. Bật ESP32 → đèn LED nhấp nháy = BLE đang phát beacon
2. Trên iPhone → app **Tìm** → tab **Vật dụng** → thấy "Tequila Map"
3. Kiểm tra GPS: `GET https://tequilamap.onrender.com/api/findmy-location`

---

## Lưu Ý Quan Trọng

- **Khoảng cách**: GPS chính xác trong ~100m (Apple lấy từ iPhone gần nhất)
- **Tần suất cập nhật**: Mỗi 30 giây hoặc khi có iPhone đi qua
- **Không cần mở Safari**: iPhone chỉ cần Bluetooth bật (luôn bật mặc định)
- **Fallback**: Nếu Find My không hoạt động → Safari vẫn gửi GPS khi mở

---

## Lệnh Quick Test

```bash
# Test doc vi tri tu Find My
curl https://tequilamap.onrender.com/api/findmy-location

# Gen key moi
curl https://tequilamap.onrender.com/api/gen-findmy-key
```
