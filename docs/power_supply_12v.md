# Mạch Nguồn Từ Bình Ắc-Quy Xe Máy (12V DC → 5V DC)

## ⚠️ Cảnh Báo Quan Trọng

> Bình ắc-quy xe máy là **12V DC** (thực tế khi máy chạy có thể lên **13.8-14.4V**). Tuyệt đối KHÔNG nối thẳng vào ESP32 (max 5V). Cần mạch giảm áp.

---

## 1. Module Giảm Áp Khuyến Nghị

### Option A: LM2596 Buck Converter (Khuyến nghị - ổn định, rẻ)
- **Input**: 4.5V–40V DC
- **Output**: 1.25V–37V DC (điều chỉnh bằng biến trở)
- **Current**: tối đa 3A
- **Giá**: ~20,000–30,000 VNĐ (Shopee/Lazada)
- **Điều chỉnh**: Vặn biến trở cho đến khi đo được đúng **5.0V** ở đầu ra

### Option B: MP1584EN Ultra-Small Buck Converter
- **Input**: 4.5V–28V DC
- **Output**: 0.8V–20V DC (điều chỉnh)
- **Current**: tối đa 3A
- **Kích thước**: rất nhỏ (~2cm x 1.5cm), phù hợp lắp trong vỏ compact
- **Giá**: ~15,000–25,000 VNĐ

### Option C: USB Car Charger Module (Nếu có cổng USB)
- Input 12V → Output 5V USB, đơn giản nhất nhưng cồng kềnh hơn

---

## 2. Sơ Đồ Kết Nối

```
[Bình ắc-quy 12V]
      │
      ├── (+) Dương ──── [Cầu chì 2A] ──── [IN+ của Buck Converter]
      └── (-) Âm  ───────────────────────── [IN- của Buck Converter]
                                                      │
                                              [Chỉnh output = 5.0V]
                                                      │
                                     [OUT+] ─── [5V ESP32 / VIN pin]
                                     [OUT-] ─── [GND ESP32]
```

> 💡 **Luôn lắp cầu chì 2A** giữa dương ắc-quy và module để bảo vệ thiết bị khi chập điện.

---

## 3. Lấy Điện Từ Công Tắc ACC (Quan Trọng!)

Để thiết bị **tự tắt khi tắt máy xe** (và lưu trạng thái hành trình), kết nối nguồn vào **dây ACC** thay vì nối thẳng vào bình:

- **Dây ACC** (Accessory): chỉ có điện khi chìa khóa xe ở vị trí ON/ACC. Khi tắt máy → mất điện → ESP32 tự lưu flash và tắt.
- **Cách tìm dây ACC**: Dùng đồng hồ đo điện, bật chìa khóa xe, que đỏ vào từng dây trong bó điện gần khóa, que đen vào mát (GND). Dây nào có 12V khi bật, mất điện khi tắt = dây ACC.

---

## 4. Phát Hiện Tắt Máy Bằng GPIO

Nối thêm dây ACC → **điện trở 10kΩ** → **GPIO 36 (ADC input ESP32-S3)**:

```python
# Trong main.py, kiểm tra liên tục:
acc_pin = machine.ADC(machine.Pin(36))
acc_pin.atten(machine.ADC.ATTN_11DB)

def is_engine_on():
    voltage = (acc_pin.read() / 4095.0) * 3.6 * 2  # Voltage divider 1:2
    return voltage > 6.0  # > 6V = xe đang chạy

# Khi phát hiện mất điện:
if not is_engine_on():
    journey_state.save()  # Lưu hành trình vào flash
    machine.deepsleep()   # Vào deep sleep
```

---

## 5. Vị Trí Gắn Trên Xe

| Vị Trí | Ưu Điểm | Nhược Điểm |
|--------|---------|------------|
| Ghi đông (handlebar) | Nhìn rõ khi lái, dễ thao tác | Rung nhiều, mưa |
| Ốp-tơ giữa xe (instrument cluster) | Bảo vệ tốt hơn | Khó tháo lắp |
| Túi xe (top case) | An toàn nhất | Không thấy màn hình |

**Khuyến nghị**: Gắn ở ghi đông bên phải, dùng vỏ nhựa in 3D có nắp chống nước, lắp nam châm neodymium để tháo nhanh.
