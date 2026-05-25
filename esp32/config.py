# esp32/config.py
# Cấu hình pin và thông số cho ESP32-S3 + 2.8" IPS TFT Compact Board

# ─── WiFi (thay BLE) ───
# ⚠️ Điền đúng tên hotspot và mật khẩu iPhone của bạn vào đây
WIFI_SSID     = "iPhone của Tequila"   # Tên Personal Hotspot trên iPhone
WIFI_PASSWORD = "matkhaucuaban"        # Mật khẩu hotspot (Settings → Personal Hotspot)
HTTP_PORT     = 80                     # Port HTTP server trên ESP32
# IP của ESP32 sẽ in ra Serial khi boot — thường là 172.20.10.2
# Điền IP đó vào Apple Shortcuts (bước 6 trong shortcuts_guide.md)

# ─── CẤU HÌNH CLOUD SERVER (ĐÁM MÂY MIỄN PHÍ) ───
USE_CLOUD_SERVER  = True                 # True = Cloud, False = Local
CLOUD_SERVER_HOST = "tequilamap.onrender.com"
CLOUD_SERVER_PORT = 443
CLOUD_SERVER_SSL  = True
CLOUD_POLL_MS     = 1500

# ─── OPENHAYSTACK / APPLE FIND MY ───
# ESP32 phat BLE → iPhone pickup → Apple server → Server doc GPS tu dong
# SETUP 1 LAN: vao https://tequilamap.onrender.com/api/gen-findmy-key
# Sau do copy public_key_bytes tra ve vao FINDMY_PUBLIC_KEY duoi day
FINDMY_BLE_ENABLED = True
FINDMY_PUBLIC_KEY  = bytes([  # ← KEY THẬT - đã gen ngày 25/05/2026
    74, 65, 168, 22, 50, 46, 153, 59,
    47, 163, 85, 131, 229, 167, 229, 96,
    77, 12, 90, 17, 246, 165, 195, 50,
    215, 173, 253, 53
])


# ─── DISPLAY (SPI) - ILI9341 / ST7789 ───
# ⚠️ Chỉnh lại các pin này theo board thực tế của bạn
DISPLAY_WIDTH    = 320
DISPLAY_HEIGHT   = 240
DISPLAY_ROTATION = 1  # 0=Portrait, 1=Landscape, 2=Portrait Flip, 3=Landscape Flip

TFT_MOSI = 13  # GPIO13 - SPI MOSI
TFT_CLK  = 14  # GPIO14 - SPI CLK
TFT_CS   = 15  # GPIO15 - Chip Select
TFT_DC   = 2   # GPIO2  - Data/Command
TFT_RST  = 4   # GPIO4  - Reset
TFT_BL   = 27  # GPIO27 - Backlight PWM

# ─── TOUCH (I2C) - FT6236 Capacitive Touch ───
I2C_SDA  = 21  # GPIO21
I2C_SCL  = 22  # GPIO22
TOUCH_INT = 39  # GPIO39 - Touch interrupt (optional)

# ─── I2S MICROPHONE - INMP441 ───
MIC_SCK  = 36  # GPIO36 - Serial Clock
MIC_WS   = 37  # GPIO37 - Word Select (L/R)
MIC_SD   = 35  # GPIO35 - Serial Data

# ─── I2S SPEAKER - MAX98357A ───
SPK_SCK  = 17  # GPIO17 - BCLK
SPK_WS   = 16  # GPIO16 - LRC (Word Select)
SPK_SD   = 18  # GPIO18 - DIN (Data In)
SPK_GAIN = 19  # GPIO19 - Gain (để trống = 9dB, kéo LOW = 12dB, HIGH = 6dB)

# ─── POWER ───
BATTERY_ADC_PIN = 34  # GPIO34 - ADC đo điện áp pin (qua voltage divider 1:2)
ACC_PIN         = 32  # GPIO32 - ADC đọc điện áp ACC từ xe (qua voltage divider 1:3)
# ⚠️ Lắp điện trở 10kΩ + 20kΩ từ dây ACC về GND cho ACC_PIN

# ─── BUTTONS ───
WAKE_BUTTON_PIN = 0   # GPIO0 - Nút BOOT/Wake (thường có sẵn trên board)
# GPIO0 LOW = button pressed (nối đất khi nhấn)

# ─── LED STATUS ───
STATUS_LED_PIN  = 38  # GPIO38 - LED xanh status (optional)

# ─── AUDIO ───
SAMPLE_RATE     = 16000   # Hz - 16kHz mono
MIC_GAIN        = 32      # Gain amplifier factor
VOICE_RECORD_MS = 5000    # 5 giây ghi âm tối đa

# ─── MAP DISPLAY ───
MAP_ROUTE_COLOR    = (0, 120, 255)    # Xanh dương - route
MAP_CAM_COLOR      = (255, 50, 50)    # Đỏ - camera
MAP_POS_COLOR      = (46, 204, 113)   # Xanh lá - vị trí hiện tại
MAP_BG_COLOR       = (15, 15, 25)     # Xanh đen - nền bản đồ
CAMERA_ALERT_DIST  = 300              # Mét - cảnh báo khi cách camera <= 300m
